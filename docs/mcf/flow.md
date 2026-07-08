# ③ 전체 Amazon MCF 플로우

> 연결부터 정산까지 end-to-end. v1 결정(도메스틱 MCF · 브랜드 all-or-nothing · 시딩 지원 · 고객가 불변)
> 기준. 코드 참조는 `klow_server/` 기준.

## 0. 한눈에

```mermaid
flowchart LR
  A[브랜드: Amazon 계정 연결<br/>OAuth] --> B[제품 ↔ Amazon SKU 매핑]
  B --> C[FBA 재고 동기화<br/>크론/수동]
  C --> D{주문·시딩 결제 확정}
  D --> E[executeCreate<br/>채널 라우팅 판정]
  E -->|도착국 창고에 전 제품 재고| F[Amazon MCF<br/>createFulfillmentOrder]
  E -->|아니면| G[EFS 송장<br/>기존 경로]
  F -->|실패: 재고부족·부적격| G
  F --> H[Amazon 자동 출고·배송]
  G --> I[브랜드→EFS 창고 발송]
  H --> J[추적 갱신 → 배송완료]
  I --> J
  J --> K[정산: Shipment 기반 월 1회]
```

## 1. 연결 (OAuth)

- 브랜드가 klow_brand `Amazon 창고` 페이지에서 리전(북미/유럽/극동) 마켓플레이스 `연결` →
  `GET /v1/brand/amazon/connect?region=..` → Amazon Seller Central consent → `callback` 에서
  authorization code → **refresh token** 교환 → `BrandAmazonConnection` 에 암호화 저장.
- 같은 리전의 다른 마켓플레이스는 재인증 없이 `바로 추가`(목업 로직과 동일).
- 토큰 만료(365일) → `status=reauth_required` → 카드에 `재연결 필요`.

## 2. 제품 ↔ SKU 매핑

- 브랜드가 KLOW 제품마다 그 마켓플레이스의 **Amazon 상품(sellerSku)** 을 연결 → `ProductAmazonListing`.
- 매핑 없는 제품은 항상 EFS. (목업의 `제품` 탭이 이 UI)

## 3. 재고 동기화 (기능 ①)

```mermaid
sequenceDiagram
  participant Cron as fba-inventory-sync.cron
  participant Svc as FbaInventoryService
  participant SP as Amazon SP-API
  participant DB as FbaInventoryCache
  Cron->>Svc: syncBrand(brandId) (시간별)
  Svc->>SP: getInventorySummaries(marketplace)
  SP-->>Svc: [{sellerSku, available, reserved, inbound}]
  Svc->>DB: upsert(marketplaceId, sellerSku, ...)
  Svc->>DB: BrandAmazonConnection.lastSyncedAt = now
```
- 수동 동기화: `POST /v1/brand/amazon/sync` (브랜드 페이지 '지금 동기화').

## 4. 결제 → 발급 라우팅 (기능 ②) — 공통 chokepoint

**트리거는 이미 한 곳으로 수렴**: 일반주문·고객결제 시딩은 `payment.markPaid`(:442), 무료/브랜드결제
시딩은 `seeding.claim`(:440) → 둘 다 `shipments.createForOrder(orderId, null)` → 브랜드별 `executeCreate`.

```mermaid
sequenceDiagram
  participant Pay as payment.markPaid / seeding.claim
  participant Ship as shipments.executeCreate
  participant Route as resolveFulfillmentChannel
  participant Inv as FbaInventoryCache
  participant MCF as mcf-fulfillment.service
  participant EFS as efs.client

  Pay->>Ship: createForOrder → executeCreate(order, brandGroup)
  Ship->>Route: 채널 판정(order, group)
  Route->>Inv: 도착국 마켓플레이스 + 전 라인 재고 확인
  alt 브랜드 연결됨 & 전 라인 매핑+재고 충분
    Route-->>Ship: AMAZON_MCF
    Ship->>MCF: createFulfillmentOrder(주소, 라인들) [RDT]
    alt 성공
      MCF-->>Ship: fulfillmentOrderId
      Ship->>Ship: Shipment(channel=AMAZON_MCF, submitted) 저장
    else 재고부족·부적격 실패
      Ship->>EFS: newCreateShipment(sendData)  // EFS 자동 폴백
      EFS-->>Ship: efsTrackingNumber
      Ship->>Ship: Shipment(channel=EFS, submitted) 저장
    end
  else 미연결/미매핑/재고부족
    Route-->>Ship: EFS
    Ship->>EFS: newCreateShipment(sendData)
    Ship->>Ship: Shipment(channel=EFS) 저장
  end
```

**라우팅 규칙 (도메스틱 · 브랜드 all-or-nothing)**
1. 도착국(`order.countryCode`)에 대응하는 Amazon 마켓플레이스에 브랜드가 연결돼 있어야 함.
2. 그 브랜드의 **모든 라인**이 (productId 존재) + (해당 마켓플레이스 SKU 매핑 존재) + (재고 ≥ 수량) 을
   만족해야 Amazon. 하나라도 불만족 → 브랜드 전체 EFS.
3. `createFulfillmentOrder` 가 재고/적격 문제로 실패하면 **같은 발급 트랜잭션에서 EFS 로 폴백** — 주문은
   절대 멈추지 않는다.

## 5. 시딩 분기

- 시딩도 §4 와 동일 경로. 단, 시딩 라인이 **productId 를 실어야** SKU 매핑이 가능(seeding 서비스 수정).
- 시딩 라인에 productId 없음 → EFS. 있으면 도착국 재고에 따라 Amazon/EFS.

## 6. 자동 출고·추적 (기능 ③)

```mermaid
sequenceDiagram
  participant AZ as Amazon FBA
  participant Poll as 추적 갱신 크론
  participant SP as getFulfillmentOrder
  participant DB as Shipment
  Note over AZ: createFulfillmentOrder 시점부터<br/>Amazon 이 자동 피킹·포장·발송
  Poll->>SP: getFulfillmentOrder(fulfillmentOrderId)
  SP-->>Poll: 상태 + 패키지 + trackingNumber
  Poll->>DB: amazonTrackingNumber / 상태 갱신
  Note over DB: 종료상태(배송완료) → 정산 후보 편입
```
- KLOW 는 별도 발송 작업 없음 — `createFulfillmentOrder` 자체가 출고 지시.
- blank-box(무지 박스) 설정으로 Amazon 브랜딩 없이 배송.

## 7. 정산

- MCF `Shipment` 도 EFS 와 동일하게 `settlement.service` 후보에 편입(EFS `'33'` 게이트에 MCF 종료상태
  매핑 추가).
- 브랜드 정산액 = `Σ OrderItem.settlementPriceKrw × qty` (채널 무관).
- 출고 원가 라인: EFS=`efsChargeKrw`, MCF=`mcfFeeKrw`. **고객 결제가는 어느 채널이든 동일**(결제 시점
  `productLogisticsCostKrw` 기반으로 이미 확정).

## 8. 취소·환불 (후속)

- 발송 전 주문 취소/환불 → `cancelFulfillmentOrder` 연동(연동 시점은 열린 질문).

## 9. 채널 판정 요약표

| 조건 | 결과 |
|---|---|
| 브랜드가 도착국 마켓플레이스 미연결 | EFS |
| 브랜드 라인 중 SKU 미매핑 존재 | EFS (브랜드 전체) |
| 매핑됐지만 재고 < 수량인 라인 존재 | EFS (브랜드 전체) |
| 전 라인 매핑 + 재고 충분 | **Amazon MCF** |
| MCF 발급 호출 실패(재고/적격) | EFS 자동 폴백 |
| 시딩 라인 productId 없음 | EFS |
