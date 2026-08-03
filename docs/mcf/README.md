# Amazon MCF (멀티채널 풀필먼트) 통합 문서

KLOW 입점 브랜드 중 **이미 Amazon FBA 창고에 재고를 둔 브랜드**의 KLOW 주문·시딩을, 브랜드가 EFS
창고로 택배를 보내는 대신 **Amazon 창고에서 고객에게 바로 출고**(Amazon MCF, Multi-Channel
Fulfillment)되게 하는 기능의 설계·구현 문서 모음.

> **현재 상태: 📄 문서 = 구현 착수 준비 완료.** klow_brand 의 `Amazon 창고` 페이지는 목업(프론트)까지 완성됐지만
> **`klow_brand` 브랜치 `develop/mcf2` 에만 있다**(staging/main 미머지 — 현 HEAD 엔 `amazon/` 페이지도 `amazon-mock.ts` 도 없다).
> 백엔드는 미구현. 설계·통합 지점은 실측 코드와 대조해 확정했다 → 이 문서만 보고 바로 구현에 들어갈 수 있다.
>
> **🔄 2026-08-01 가격 로직 최신화**: 2026-07-28-30 전환(판매가에서 물류비 완전 분리 + 고객 결제 배송비 별도 + 500g 기준)
> 으로 **채널별 가격 2벌 설계가 통째로 불필요해졌다**. 옛 "MCF = 물류비/2 차감 생략 역산 / `mcfMarginKrw` / MCF 표시가
> / 폴백 가격차 KLOW 흡수" 는 **전부 폐기**됐고, 그 자리에 **"가격·정산가는 채널 무관 1벌, 채널이 갈리는 건 배송비 선결제
> 처리 하나뿐"** 이 들어왔다(README 결정표 · `flow.md` §7 · `implementation-plan.md` §8). 새로 생긴 **유일한 미확정 정책**은
> **MCF 주문의 고객 배송비 선결제분을 누가 갖는가**(A/B 안 — `flow.md` §7-3 · `implementation-plan.md` §8-4).

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

> **구현 시작점**: `implementation-plan.md` **§10 로드맵을 순서대로**. 각 단계 착수 전 **§13 통합 불변식 체크리스트**(F1~F10·R5~R8)를
> 반드시 먼저 읽는다 — 여길 어기면 mock 에서 컴파일은 되어도 플로우가 조용히 멈춘다.
>
> **⚠️ 라인번호 주의**: 문서의 `file:line`(예: `executeCreate` :644, settlement `:216/:390/:470/:527`)은 **2026-08-01 재확인 스냅샷**이다.
> 구현 시점엔 밀려 있을 수 있으니 **심볼명(함수/상수)으로 재확인** 후 편집한다. §13 의 "근거" 열이 심볼명을 함께 준다.

## 확정된 핵심 결정 (2026-07-08 · 가격 항목은 2026-08-01 갱신)

| 항목 | 결정 |
|---|---|
| 아키텍처 | **klow_server 내부 모듈** `src/modules/amazon/` (별도 마이크로서비스 아님) |
| 혼합 주문 | **브랜드 단위 all-or-nothing** — 브랜드 라인 중 하나라도 재고 부족 시 그 브랜드 전체 EFS |
| 배송 범위(v1) | **도메스틱 MCF 만** — 도착국 == Amazon 마켓플레이스 창고국 (크로스보더 미시도) |
| 시딩 | **v1 에서 항상 EFS (MCF 는 v2 연기)** — 시딩 라인은 `OrderItem.productId` 가 null 이고, `SeedingLink.selectedSkus`/`selectionSkus` 는 **제품 ID 가 아니라 자유텍스트 제품명 라벨**이라 현 스키마로는 SKU/재고 판정 경로를 못 탄다. 시딩 MCF 는 선택 필드에 실제 productId 를 심는 스키마 변경(v2) 이후로 미룬다 |
| 가격(판매가·정산가) | **채널 무관 1벌 — MCF 전용 가격 트랙 없음.** 2026-07-28 전환으로 판매가·정산가에서 물류비가 완전히 빠졌다(`판매가USD = ceil(salePrice/0.95/basePriceFxRate ×100)`, `정산가 = floor(청구USD × fx × 0.95)` — `product-selects.ts priceLine()`). 물류비가 애초에 안 들어가니 **MCF 라고 뺄 게 없다** → 옛 "2벌·`mcfMarginKrw`·물류비/2 차감 생략" 설계 **폐기**. 고객 표시가·결제가·브랜드 정산가가 EFS/MCF 동일 |
| 고객 결제 배송비 | **채널과 무관하게 주문 시점에 확정**(`500g 요율/fx × 청구 대상 브랜드수`, 무료배송은 국가별 `ProductCountryPrice.freeShipping`). 라우팅은 **결제 이후**라 MCF 로 나가도 고객이 낸 배송비는 그대로다 — MCF 는 배송비 계산·견적·카트 경로를 **전혀 건드리지 않는다** |
| refresh token | **암호화 저장** (Admin TOTP AES-256-GCM 선례 — 단, 키는 신규 `AMAZON_TOKEN_ENCRYPTION_KEY` 로 분리해 독립 회전) |
| 정산(매출) | **채널 판별 불필요** — `OrderItem.settlementPriceKrw`(주문 시점 역산 스냅샷)를 그대로 `Σ × qty`. **발급 시 정산가를 다시 쓰지 않는다**(F8). 남는 작업은 delivered gate(`latestStatusCode='33'`, Prisma where 4곳)를 `settleableDeliveredWhere(): Prisma.ShipmentWhereInput`(EFS `'33'`+MCF 종료상태) where-빌더로 치환하는 것뿐 |
| **배송비 선결제 처리(MCF)** | ⚠️ **유일한 미확정 정책.** EFS 면 고객 선결제분이 실측 물류비의 **선납금**이 되어 브랜드 후청구에서 차감되는데(`efs-billing` 일반주문 = `max(0, 실비+수수료 − 선결제)`), MCF 는 EFS 청구서 자체가 없다. **(A)** KLOW 보유(코드 변경 0, v1 파일럿) vs **(B)** 정산 시 브랜드 크레딧(`perBrandShareUsd(order, brandId, n) × fxRateSnapshot`). 상세·권고는 `flow.md` §7-3 |
| MCF 수수료 | **브랜드가 자기 Amazon 계정에서 부담**(Amazon 이 셀러 계정에서 차감). 가격에 미리 반영하는 게 아니라 **MCF 를 쓸지 말지의 브랜드 판단 요소**다(가격은 채널 무관 1벌이므로). KLOW 는 조회·보전 안 함 → getFulfillmentPreview/Finances·Finance Role **불필요**. `mcfChargeKrw` 는 분석용(옵션) |
| 표시가격·폴백 | **분기 없음** — 표시가가 채널과 무관해 "MCF 가격으로 결제됐는데 EFS 로 나감" 문제 자체가 성립하지 않는다(옛 KLOW 흡수 정책 폐기). 폴백은 순수 물류 이벤트 |
| 재고 판정 | 동기화 캐시 1차 판정 + `createFulfillmentOrder` 실패 시 EFS 자동 폴백 |
| 구매 가능 국가 | **MCF 가 EFS 게이트를 넓히지 않는다** — 배송지원(`enabled`) 제외국·500g 요율/캐리어 미설정국·EFS 제외구역은 주문 생성 단계에서 막히고, 라우팅은 그 뒤라 Amazon 창고가 커버하는 나라여도 구매가 안 된다(R8) |

## 관련 코드 (현재)

- 프론트 목업: `klow_brand` **브랜치 `develop/mcf2`** 의 `src/app/(authed)/amazon/`, `src/lib/amazon-mock.ts`,
  `amazon-marketplaces.ts` (⚠️ staging/main 미머지 — 배선 전에 리베이스 필요)
- 발급 엔진(분기 지점): `klow_server/src/modules/shipments/shipments.service.ts` `executeCreate`(:644)
- 결제/시딩 트리거: `klow_server/src/modules/payment/payment.service.ts` `markPaid`(→ `createForOrder` :571),
  `klow_server/src/modules/seeding/seeding.service.ts` `claim`(→ :653)
- **가격 정본(변경 금지 · MCF 는 읽기만)**: `products/product-selects.ts` `priceLine()`,
  `common/pricing.ts`(`settlementKrwFromCustomerUsd`/`perBrandShippingFeeUsdCents`),
  `orders/chargeable-brands.ts`(`chargeableBrandIds`/`shippingFeeByBrand`/`perBrandShareUsd`) — 전체 모델은
  [`../pricing-model.md`](../pricing-model.md)
- 정산 게이트: `settlement/settlement.service.ts`(`EFS_STATUS_DELIVERED` 4곳) ·
  배송비 후청구: `efs-billing/efs-billing.service.ts`(일반+시딩 공용, MCF 는 `efsTrackingNumber` 필터로 자연 제외 — F10)
