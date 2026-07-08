# ② Amazon MCF 실제 구현 계획 (living doc)

> 이 문서는 피드백으로 계속 업데이트한다. 현재 버전: **v1 초안 (2026-07-08)**.
> 모든 경로는 `klow_server/` 기준(별도 표기 제외). 프론트는 `klow_brand/`.

## 0. 스코프

**해야 할 것 (v1)**
1. 브랜드 Amazon 계정 OAuth 연결 + 마켓플레이스별 SKU 매핑 + FBA 재고 주기 동기화.
2. 주문/시딩 **결제 확정 시**, 도착국 Amazon 창고에 브랜드 전 제품 재고가 있으면 **`createFulfillmentOrder`**
   로 Amazon 출고(= 자동 발송), 아니면 기존 EFS.
3. Amazon 출고 상태·추적 갱신, 정산 파이프라인 편입.

**안 할 것 (v1)**
- 크로스보더 MCF(재고국≠도착국). 도메스틱만.
- 라인 분할(브랜드 내 Amazon+EFS 혼합). 브랜드 all-or-nothing.
- Notifications 이벤트 구독(폴링으로 대체).
- Amazon 마켓플레이스에 리스팅/판매(무관).

## 1. 데이터 모델 (Prisma)

### 신규 모델
```prisma
// 브랜드 Amazon 계정 연결 — BillingKey 선례 미러. refresh token 은 암호화 저장.
model BrandAmazonConnection {
  id             String    @id @default(cuid())
  brandId        String
  region         String    // 'na' | 'eu' | 'fe' (SP-API 리전)
  marketplaceIds String[]  // 이 계정으로 커버되는 마켓플레이스들
  sellerId       String
  refreshToken   String    // AES-256-GCM 암호화 (ADMIN_TOTP 방식 재사용/신규 키)
  status         String    @default("active") // active | reauth_required | disconnected
  lastSyncedAt   DateTime?
  createdAt      DateTime  @default(now())
  deletedAt      DateTime?
  brand          Brand     @relation(fields: [brandId], references: [id])
  @@index([brandId])
}

// 제품 ↔ Amazon SKU (마켓플레이스별). ProductCountryPrice 에 얹지 않음(그건 replace-all).
model ProductAmazonListing {
  id            String  @id @default(cuid())
  productId     String
  marketplaceId String  // 'US' | 'JP' | ... (iso2 또는 Amazon marketplaceId — 아래 열린질문)
  sellerSku     String
  asin          String?
  fnSku         String?
  createdAt     DateTime @default(now())
  product       Product  @relation(fields: [productId], references: [id])
  @@unique([productId, marketplaceId])
  @@index([marketplaceId, sellerSku])
}

// FBA 재고 동기화 스냅샷 — 라우팅 1차 판정 소스.
model FbaInventoryCache {
  id            String   @id @default(cuid())
  brandId       String
  marketplaceId String
  sellerSku     String
  available     Int
  reserved      Int      @default(0)
  inbound       Int      @default(0)
  syncedAt      DateTime
  @@unique([marketplaceId, sellerSku])
  @@index([brandId])
}
```

### 기존 모델 확장
- **`Shipment`**: 채널·Amazon 식별자·수수료 추가.
  ```prisma
  channel                 String   @default("EFS") // 'EFS' | 'AMAZON_MCF'
  amazonFulfillmentOrderId String? @unique
  amazonShipmentId        String?
  amazonTrackingNumber    String?
  mcfFeeKrw               Int?     // efsChargeKrw 대응(정산 원가 라인)
  ```
  - `efsTrackingNumber`/`efsServiceType` 등 EFS 전용 컬럼은 MCF 행에선 null.
  - 종료상태: EFS 는 `latestStatusCode='33'`. MCF 는 `getFulfillmentOrder` 상태를 `latestStatusCode`
    (또는 공용 상태 필드)로 매핑해 정산 게이트가 인식하게 함.
- **`OrderItem`**: 시딩 라인에도 productId 를 실을 수 있게 유지(현재 nullable). 시딩 발급 경로가 productId
  를 채우도록 seeding 서비스 수정(§5).
- **`ShippingCountry`**: (열린질문) 도착국→마켓플레이스 판정을 위해 `amazonMarketplaceId` 추가할지, 아니면
  `ProductAmazonListing` 존재 여부로만 판정할지 결정.
- **`ShippingCarrier` enum**: MCF 는 `Shipment.channel` 판별자로 분리하므로 enum 에 값 추가는 하지 않는
  방향(권장). `carrierForBrand`/`buildPayload` 가 EFS service type 을 전제하기 때문.

마이그레이션: `npx prisma migrate dev --name add_amazon_mcf` (interactive → 사용자 실행).

## 2. 모듈 구성 — `src/modules/amazon/`

`EfsClient`/`TrackingRefreshCron`/`shipments.module` 패턴을 미러.

```
src/modules/amazon/
  amazon.module.ts              // app.module.ts imports 에 추가
  amazon-spapi.client.ts        // EfsClient 미러: ConfigService, 빈 크레드→mock
  amazon-connection.service.ts  // OAuth 연결/해제/재연결, 토큰 암복호화
  amazon-listing.service.ts     // 제품↔SKU 매핑 CRUD
  fba-inventory.service.ts      // 재고 동기화(수동+크론 공용)
  fba-inventory-sync.cron.ts    // TrackingRefreshCron 미러(시간별, env kill-switch)
  mcf-fulfillment.service.ts    // createFulfillmentOrder / getFulfillmentOrder 래핑
  brand-amazon.controller.ts    // /v1/brand/amazon/* (브랜드 페이지 API)
  amazon.types.ts
```

`shipments.service.ts` 는 `McfFulfillmentService` + `FbaInventoryService` + `AmazonListingService` 를
주입받아 `executeCreate` 안에서 라우팅/발급을 호출한다.

## 3. SP-API 클라이언트 & 인증

- **app 크레드**: `requireConfig(config, 'AMAZON_LWA_CLIENT_ID')` / `..._SECRET`, 리전별 엔드포인트.
  `.env.example` 에 `# ===== Amazon SP-API / MCF =====` 블록 추가. **빈 값 → mock 모드**(dev).
- **per-brand refresh token**: `BrandAmazonConnection.refreshToken` (암호화). LWA access token(1h)은
  메모리 캐시.
- **RDT**: `createFulfillmentOrder`(배송지 PII) 전 Tokens API 로 발급.
- **OAuth 연결 플로우**:
  - `GET /v1/brand/amazon/connect?region=na` → Amazon consent URL 리다이렉트.
  - `GET /v1/brand/amazon/callback` → authorization code → refresh token 교환 → 저장.
  - 목업 `ConnectModal` 자리를 실제 OAuth 리다이렉트로 교체.

## 4. 발급 분기 (핵심) — `shipments.service.ts executeCreate`

현재 `executeCreate(order, group, shippingFeeShareUsd, adminId)` (:630–749): `carrierForBrand`(:656) →
`buildPayload` → `Shipment` 저장 → `efs.newCreateShipment`(:719).

**변경**: `carrierForBrand` 직후 채널 판정.
```
const channel = await resolveFulfillmentChannel(order, group);
if (channel === 'AMAZON_MCF') {
  try {
    const res = await this.mcf.createFulfillmentOrder(order, group.lines); // RDT 사용
    // Shipment 저장: channel=AMAZON_MCF, amazonFulfillmentOrderId, 상태=submitted
    return;
  } catch (e) {
    // 재고부족/부적격 등 → EFS 폴백 (아래 기존 경로로 진행)
  }
}
// 기존 EFS 경로(buildPayload → efs.newCreateShipment) 그대로
```

`resolveFulfillmentChannel(order, group)` (신규, `mcf-fulfillment.service` 또는 shipments 내부 헬퍼):
1. `order.countryCode` 로 도착국 마켓플레이스 결정. 브랜드가 그 마켓플레이스에 **연결**돼 있나
   (`BrandAmazonConnection`)? 아니면 EFS.
2. **브랜드 all-or-nothing**: group.lines 전부가
   - `productId` 존재(시딩 포함) &&
   - `ProductAmazonListing(productId, marketplaceId)` 존재 &&
   - `FbaInventoryCache.available ≥ line.quantity`
   를 만족? → `AMAZON_MCF`, 아니면 `EFS`.
3. 도메스틱 전제이므로 창고국 == 도착국 자동 성립.

`sellerFulfillmentOrderId` = `klow-{orderId}-{brandId}` (멱등키 — 재시도 안전).

## 5. 시딩 특수 처리 (결정: 지원)

- 현재 시딩 `OrderItem.productId = null` (커스텀 스냅샷만) → SKU 매핑 불가.
- **수정**: `seeding.service.ts` `claim()`/`checkout()` 이 시딩 라인에 **productId(또는 sellerSku)** 를
  채우도록 확장. `SeedingLink` 가 제품을 참조하도록(단일 제품 시딩) 또는 고객선택 제품의 productId 를
  라인에 반영.
- 그 뒤엔 §4 라우팅이 일반주문과 동일하게 적용. productId 없으면 EFS.
- 트리거는 이미 공통(`payment.markPaid` / `seeding.claim` → `createForOrder`) — **추가 배선 불필요.**

## 6. 동기화 (기능 ①)

- `FbaInventoryService.syncBrand(brandId)` — `getInventorySummaries` → `FbaInventoryCache` upsert +
  `BrandAmazonConnection.lastSyncedAt` 갱신.
- `fba-inventory-sync.cron.ts` — `@Cron('0 * * * *', { timeZone: 'Asia/Seoul' })` 전 브랜드 순회
  (env `AMAZON_SYNC_CRON_ENABLED` kill-switch).
- 수동: `POST /v1/brand/amazon/sync` — 브랜드 페이지 '지금 동기화' 버튼.

## 7. 출고 상태·추적 (기능 ③)

- `createFulfillmentOrder` 성공 = Amazon 이 자동 발송. 별도 발송 작업 없음.
- `getFulfillmentOrder` 폴링 크론(또는 기존 tracking-refresh 확장)으로 상태·`amazonTrackingNumber` 를
  `Shipment` 에 갱신. MCF 종료상태(배송완료)를 정산 게이트가 인식하도록 매핑.

## 8. 정산 reconciliation

- `settlement.service.ts` 의 후보 게이트가 EFS `latestStatusCode='33'` 하드코딩 → **MCF 종료상태도
  포함**하도록 확장.
- 정산 금액은 그대로 `Σ OrderItem.settlementPriceKrw×qty` (채널 무관, 브랜드 net).
- 출고 원가: EFS 는 `efsChargeKrw`(efs-billing), MCF 는 `mcfFeeKrw`. 고객 결제가는 불변.

## 9. 프론트 연결 (mock → real)

`klow_brand/src/lib/api.ts` 의 `api.amazon.*` 목업 함수 본문만 실제 엔드포인트로 교체:
| 목업 | 실제 |
|---|---|
| `connections()` | `GET /v1/brand/amazon/connections` |
| `inventory()` | `GET /v1/brand/amazon/inventory` |
| `mappings()` / `catalog()` | `GET /v1/brand/amazon/products` / `.../catalog` |
| `fulfillments()` | `GET /v1/brand/amazon/fulfillments` |
| (연결) | `GET /v1/brand/amazon/connect` (OAuth 리다이렉트) |
| (동기화) | `POST /v1/brand/amazon/sync` |
| (SKU 매핑) | `PUT /v1/brand/amazon/products/:productId/listing` |

타입(`api-types.ts`)·쿼리키(`query-keys.ts`)·컴포넌트는 그대로. `amazon-mock.ts` 는 제거.

## 10. 단계별 로드맵

1. **문서·결정 확정** (현재).
2. Prisma 모델 + 마이그레이션, `.env` 블록, `amazon.module` 스캐폴딩.
3. `AmazonSpApiClient`(mock 모드) + OAuth 연결 + 토큰 암복호화.
4. SKU 매핑 CRUD + FBA 재고 동기화(수동→크론).
5. `executeCreate` 라우팅 분기 + `createFulfillmentOrder`(mock) + EFS 폴백.
6. 시딩 productId 배선.
7. 출고 추적 갱신 + 정산 게이트 확장.
8. 프론트 mock→real 배선.
9. dynamic sandbox 실검증 → 파일럿 브랜드 실계정.

## 11. 열린 질문 (피드백으로 확정)

- 도착국→마켓플레이스 판정: `ShippingCountry.amazonMarketplaceId` 신설 vs `ProductAmazonListing` 존재.
- MCF 수수료 취득 경로(`getFulfillmentPreview` 예상치 vs Finances API 실비).
- 시딩 라인 product 참조를 `SeedingLink` 스키마 어디에 둘지(단일제품 vs 고객선택).
- refresh token 암호화 키 관리(ADMIN_TOTP 키 재사용 vs 신규 `AMAZON_TOKEN_ENCRYPTION_KEY`).
- 취소·환불 시 `cancelFulfillmentOrder` 연동 시점.
- 파일럿 브랜드 재고 리전 확정(도메스틱 lane 성립 확인).

## 12. 검증

- **mock 모드**(빈 크레드) e2e: 결제→라우팅→합성 fulfillment order id→`Shipment(channel=AMAZON_MCF)`→
  정산 후보 노출. EFS 폴백(재고 0 케이스)도 확인.
- **dynamic sandbox**: `createFulfillmentOrder`→`getFulfillmentOrder` 실호출 검증.
- 마이그레이션은 `npx prisma migrate dev` (interactive — 사용자 실행 요청).
