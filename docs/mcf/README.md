# Amazon MCF (멀티채널 풀필먼트) 통합 문서

KLOW 입점 브랜드 중 **이미 Amazon FBA 창고에 재고를 둔 브랜드**의 KLOW 주문·시딩을, 브랜드가 EFS
창고로 택배를 보내는 대신 **Amazon 창고에서 고객에게 바로 출고**(Amazon MCF, Multi-Channel
Fulfillment)되게 하는 기능의 설계·구현 문서 모음.

> **현재 상태: 📄 문서 = 구현 착수 준비 완료.** klow_brand 의 `Amazon 창고` 페이지는 목업(프론트)까지 완성됐고,
> 백엔드는 미구현. 설계·통합 지점은 실측 코드와 대조해 확정했다 → 이 문서만 보고 바로 구현에 들어갈 수 있다.

## 목표 동작 (한 줄)

주문 **결제가 확정되면 → 도착국 Amazon 창고에 그 제품 재고가 있으면 Amazon 송장 발급(=Amazon 이
자동 출고), 없으면 기존 EFS 송장**. (v1 시딩은 항상 EFS — 아래 결정표)

## 문서 · 읽는 순서 · 구현 시작점

**읽는 순서**: ① 이 README(결정 요약) → ② `sp-api-capabilities`(무슨 API 를 왜 쓰는지) → ③ `flow`(전체 흐름 그림) →
④ `implementation-plan`(**정본 — 실제 빌드 스펙**).

| 문서 | 역할 | 정본 |
|---|---|---|
| [`sp-api-capabilities.md`](./sp-api-capabilities.md) | Amazon SP-API 기능·인증·제약·비용 조사 (배경) | API 범위 |
| [`flow.md`](./flow.md) | 연결→동기화→결제→발급→출고→추적→정산 서사·시퀀스 다이어그램 (개요) | 흐름 |
| [`implementation-plan.md`](./implementation-plan.md) | 데이터 모델·발급 분기·정산·**단계별 로드맵(§10)**·**통합 불변식(§13)** | **구현·스키마 정본** |

> **구현 시작점**: `implementation-plan.md` **§10 로드맵을 순서대로**. 각 단계 착수 전 **§13 통합 불변식 체크리스트**(F1~F7·R5~R7)를
> 반드시 먼저 읽는다 — 여길 어기면 mock 에서 컴파일은 되어도 플로우가 조용히 멈춘다.
>
> **⚠️ 라인번호 주의**: 문서의 `file:line`(예: `executeCreate` :630, settlement `:100/:193`)은 **2026-07-08 스냅샷**이다.
> 구현 시점엔 밀려 있을 수 있으니 **심볼명(함수/상수)으로 재확인** 후 편집한다. §13 의 "근거" 열이 심볼명을 함께 준다.

## 확정된 핵심 결정 (2026-07-08)

| 항목 | 결정 |
|---|---|
| 아키텍처 | **klow_server 내부 모듈** `src/modules/amazon/` (별도 마이크로서비스 아님) |
| 혼합 주문 | **브랜드 단위 all-or-nothing** — 브랜드 라인 중 하나라도 재고 부족 시 그 브랜드 전체 EFS |
| 배송 범위(v1) | **도메스틱 MCF 만** — 도착국 == Amazon 마켓플레이스 창고국 (크로스보더 미시도) |
| 시딩 | **v1 에서 항상 EFS (MCF 는 v2 연기)** — 시딩 라인은 `OrderItem.productId` 가 null 이고, `SeedingLink.selectedSkus`/`selectionSkus` 는 **제품 ID 가 아니라 자유텍스트 제품명 라벨**이라 현 스키마로는 SKU/재고 판정 경로를 못 탄다. 시딩 MCF 는 선택 필드에 실제 productId 를 심는 스키마 변경(v2) 이후로 미룬다 |
| 가격(판매가·2벌) | **일반·MCF 판매가 2벌.** 일반=`원가+마진+물류비/2`, MCF=`원가+MCF마진`. **MCF마진 기본값=`마진+물류비/2`** → MCF 판매가가 일반가와 같은 값으로 시작하고, **MCF마진으로 독립 조절** 가능(Amazon 은 EFS 물류비가 안 드니 그 몫이 마진으로 흡수). 정확한 식은 `product-selects.ts priceLine()`·배송비 라인·÷0.95 와 대조 확정 |
| refresh token | **암호화 저장** (Admin TOTP AES-256-GCM 선례 — 단, 키는 신규 `AMAZON_TOKEN_ENCRYPTION_KEY` 로 분리해 독립 회전) |
| 정산(매출) | 브랜드 정산가도 **채널별 2벌**(일반=`원가+마진`, MCF=`원가+MCF마진`). **실제 나간 채널**로 골라 `Σ 정산가 × qty`. delivered gate(`latestStatusCode='33'`, Prisma where 4곳)를 `settleableDeliveredWhere(): Prisma.ShipmentWhereInput`(EFS `'33'`+MCF 종료상태) where-빌더로 4곳 치환 |
| MCF 수수료 | **브랜드가 자기 Amazon 계정에서 부담**(MCF마진에 미리 반영해 값 책정 — Amazon 이 셀러 계정에서 차감). KLOW 는 조회·보전 안 함 → Amazon fee 조회(getFulfillmentPreview/Finances)·Finance Role **불필요**. `mcfChargeKrw` 는 분석용(옵션) |
| 표시가격·폴백 | Amazon 적격 제품은 MCF 판매가 표시, 아니면 일반가. MCF 가격 표시 후 재고부족으로 **EFS 폴백** 시 가격차는 **KLOW 흡수**(기본값 동일이면 무영향) |
| 재고 판정 | 동기화 캐시 1차 판정 + `createFulfillmentOrder` 실패 시 EFS 자동 폴백 |

## 관련 코드 (현재)

- 프론트 목업: `klow_brand/src/app/(authed)/amazon/`, `klow_brand/src/lib/amazon-mock.ts`,
  `amazon-marketplaces.ts`
- 발급 엔진(분기 지점): `klow_server/src/modules/shipments/shipments.service.ts` `executeCreate`
- 결제/시딩 트리거: `klow_server/src/modules/payment/payment.service.ts` `markPaid`,
  `klow_server/src/modules/seeding/seeding.service.ts` `claim`
