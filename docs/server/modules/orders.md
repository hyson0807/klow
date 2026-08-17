# orders — 주문

- **모듈 경로**: `src/modules/orders/`
- **결제 통화**: USD
- **주문 생성 시 저장**: 약관동의 3종(`agreedToTerms`/`agreedToRefund`/`agreedToPgDataSharing` — 모두
  `Zod literal(true)`, 같은 시각으로 `termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt` 기록) + IP +
  `fxRateSnapshot` (결제 시점 환율 고정용). 라인 단가·정산가·원가는
  `OrderItem`에 주문 시점 스냅샷(`unitPriceUsd`/`settlementPriceKrw`/`costKrw`). 가격은 표시·견적과 동일한 `priceLine` 사용.
- **배송비 + 무료배송**: `shippingFeeUsd = 500g 요율/fx × 청구 대상 브랜드수`(산식 정본은 [pricing-model](../../pricing-model.md)). 배송비는 브랜드 단위(한 브랜드 = 한 송장)라
  **그 브랜드 라인이 전부 무료배송일 때만** 면제된다. 무료배송은 **국가별**(`ProductCountryPrice.freeShipping`,
  목적국 행이 없으면 유료)이라 배송지 국가가 판정의 입력이다 — `chargeableBrandIds(lines, iso2)`
  (`pricing/chargeable-brands.ts`, 생성·견적 공유). create/quote 둘 다 `countryPrices` 를 `where: { iso2 }` 로 필터해 넘긴다.
  브랜드별 금액은 `Order.shippingFeeByBrand`(`{brandId: 센트}`, 무료 브랜드는 0, Σ == `shippingFeeUsd`)에
  스냅샷해 송장 발급이 EFS 27번을 정확히 안분한다.
  `quote` 응답은 `{ shippable, carrier, fxRate, lines, itemsTotalUsd, shippingFeeUsd, chargeableBrands,
  totalUsd }`(금액은 모두 USD 센트)이고 라인은 `{productId, quantity, unitPriceUsd}` 뿐이다. 배송비 표기에 필요한
  `shippingFeeUsd`·`shippable`·`chargeableBrands`(실제 배송비가 붙은 브랜드 수 — 무료배송 브랜드 제외)는
  응답 최상위에 있다 — 무료배송이 국가별이라 클라는 면제 여부를 못 구하므로 "무료" 판정과 "N개 브랜드"
  표기 모두 서버값을 쓴다. 배송 불가(제외국·요율/캐리어 미설정·EFS 제외구역)면 `create` 는 400 으로 차단하지만
  `quote` 는 throw 없이 `shippable:false` + 나머지 0/빈 배열로 응답한다.
  캐리어 분기는 브랜드별 청구중량(`brandChargeableWeights` = Σ max(실무게, L×W×H/6) × 수량)으로 갈리며
  create/quote 가 같은 헬퍼를 공유해 견적 캐리어 == 청구 캐리어가 보장된다.
- **과청구 가드**: 현지통화 핀(`priceLocal`) 상품인데 목적국 통화의 유효 환율이 없으면 `OrdersService.billingRate`가
  주문/견적을 차단한다(1로 폴백해 현지가를 USD로 오인 → 과청구하는 사고 방지). 핀 없는 상품은 영향 없음. 자세히는 [`../../pricing-model.md`](../../pricing-model.md).
- **브랜드당 최대 5개**(`MAX_ITEMS_PER_BRAND`): 한 브랜드 = 한 EFS 송장(박스)이라 클라 중복 productId 를 병합한
  수량 합이 5를 넘으면 400. legacy(`brandId` 없음) 제품은 면제, 현장(onsite) 주문은 박스가 없어 미적용.
- **상태**: `Order.status`(`pending → processing → shipped → completed`, 종착 `cancelled`)와
  `Order.paymentStatus`(`pending / paid / failed / cancelled / refunded`)는 **별개 컬럼**이다.
  status 는 `PATCH /admin/orders/:id/status` 로 **전진만** 가능(역행 400, `cancelled` 는 재전이 불가)하고,
  `cancelled` 로 가는 유일한 경로는 환불/취소 액션(`/refund`, `/cancel`, `guest-cancel`)이다.
  `shipped` / `completed` 는 수동 외에 **송장이 자동으로 구동한다** — 전 라인 발급 시 `shipped`,
  전 라인 배송완료(EFS 추적 코드) 시 `completed`. 판정·주의점은 [`shipments.md`](./shipments.md) 의
  `maybeMarkOrderShipped` / `maybeMarkOrderCompleted` 참고. 이미 배송완료라 cron 폴링 대상에서
  빠진 과거 주문은 `npm run backfill:order-completed`(멱등) 로 한 번 정리한다.
- **현장(onsite) 주문**: 박람회 부스 QR 결제 — `channel='onsite'`, 배송지·캐리어·배송비 없음(`shippingFeeUsd=0`),
  `onsiteExcluded` 제품은 차단. 결제 성공 시 송장 없이 바로 `completed` 로 전이된다(`payment.markPaid`).
  - 단가는 **`onsitePriceLine()`** — 표시 경로(`products.service` 의 `mode=onsite`)와 같은 함수라 표시가==청구가.
    우선순위·$0 폴백 규칙은 [`products.md`](./products.md) 의 `mode=onsite` 항목 참고.
  - **`countryCode` 는 배송지가 아니라 가격 기준국**이다(현장은 배송이 없다). 브랜드가 그 나라에 현장가를
    핀해뒀으면 그 값으로 청구된다. optional 이며 미지정 시 `US`(표시 경로 기본값과 같아 일치가 유지된다).
    파생은 `pricingIso2()` 단일 출처. 이 값은 감사 추적을 위해 `Order.countryCode` 에 저장된다 — 현장주문은
    송장을 만들지 않으므로 `countryCode` 의 유일한 소비처인 shipments 경로와 무관하다.
  - ⚠️ 국가 핀이 있는데 그 통화의 FX 행이 없으면 **`billingRate` 가 차단**한다(일반 주문과 공유하는 가드).
    안 막으면 `¥3,420` 을 `$3,420` 로 청구한다.
- **관련 파일**: `orders.service.ts`, `admin-orders.controller.ts`, `public-orders.controller.ts`, `chargeable-brands.ts`(청구 대상 브랜드·배송비 스냅샷·읽기 짝), `brand-weights.ts`(브랜드별 청구중량 → 캐리어 분기), `guest-order-token.ts`(비회원 주문 HMAC 토큰)

## admin-orders.controller.ts (`@Controller('admin/orders')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                          | 기능                                                |
|--------|-------------------------------|-----------------------------------------------------|
| GET    | `/admin/orders`               | 주문 목록 — 쿼리 `status` / `paymentStatus` / `excludePaymentStatus`(CSV) / `type` / `brandId` / `take`(1~200, 기본 100) / `skip`. 정렬 `createdAt desc, id desc`. 응답 `{ data, total, pendingTotal }` — `pendingTotal` 은 **필터와 무관한 전체 미결제 건수**로, 어드민이 미결제를 기본 숨김하므로 "숨겨진 N건" 배너에 쓴다(같은 `$transaction` 에 얹어 별도 왕복이 없다) |
| GET    | `/admin/orders/:id`           | 주문 상세                                           |

> ⚠️ 위 두 조회만 `ADMIN_ORDER_INCLUDE`(= `items` + `seedingClaim`)를 쓴다. `seedingClaim` 은 **고객 선택 시딩의 표시 제품명**용이다 — `OrderItem.productName` 이 실제 제품명이 아니라 발급 시 동결된 영문 통관 품명이라, 어드민 화면이 바이어가 고른 제품으로 갈아끼우려면 필요하다(→ [seeding](./seeding.md), 클라 미러는 `klow_admin/src/lib/seeding-display.ts`). 공용 `ORDER_INCLUDE` 를 넓히지 않은 이유는 그게 create/quote/고객 조회까지 공유해 결제 경로에 불필요한 조인이 얹히기 때문이다.

| PATCH  | `/admin/orders/:id/status`    | 주문 상태 변경 — `{ status: 'pending'\|'processing'\|'shipped'\|'completed' }`. 역행·`cancelled` 주문 변경은 400 |
| PATCH  | `/admin/orders/:id/reconcile-payment` | **결제 재확인** — 미결제로 남은 주문을 Eximbay 에 직접 조회(`/v1/payments/retrieve`, `key_field='order_id'`)해 실제 승인(`SALE`/`AUTH`)이면 `markPaid` 로 확정. 응답 `{ result: 'paid'\|'not_paid'\|'not_found'\|'mismatch', order }` (확정 성공 시에만 `order` 동봉 — 어드민이 재조회하지 않게, `refund` 와 같은 관례). 15분 주기 `payment-reconcile` 크론과 **같은 경로**이고 운영자가 즉시 처리하기 위한 수동 트리거다. ⚠️ **임의로 `paid` 를 찍는 엔드포인트가 아니다** — 반드시 PG 재조회를 거치고 금액이 어긋나면(`mismatch`) 전이하지 않는다. 손으로 결제완료를 찍게 하면 미결제 주문이 정산에 섞인다 |
| PATCH  | `/admin/orders/:id/refund`    | 환불/취소 처리 — `{ reason: 1~500자 }`. `paid` 면 Eximbay cancel 호출 후 `refunded`, `pending` 이면 결제 없이 `cancelled`. 이미 취소·환불·실패 주문은 400 |
| PATCH  | `/admin/orders/:id/recipient` | 수화인(배송) 정보 수정 — EFS 송장 인쇄 필드만(`fullName`/`phone`/`email`/주소/`state`/영문명·영문주소/`recipientTaxId`). 국가·품목·금액은 불변이고, 국가별 필수(US→state, JP→영문, CN→신분증)는 주문의 기존 `countryCode` 로 강제. 발급된 송장 반영은 `POST /admin/shipments/:id/change-cnee` 별도 호출 |

### 목록 쿼리 (`OrderAdminListQueryInput`)

쿼리 검증은 `common/validation/order.ts` 의 zod 스키마 + `ZodValidationPipe` 가 한다(예전엔
컨트롤러가 원시 문자열을 그대로 캐스팅해 `?status=zzz` 가 Prisma 까지 흘러 500 이 났다).
목록과 총건수는 `buildAdminOrderWhere()` 가 만든 **같은 where** 를 쓴다 — 갈라지면 총계가
조용히 거짓말을 한다. `ADMIN_ORDER_TYPES` 는 이 스키마가 쓰기 때문에 `modules/orders` 가 아니라
`common/validation/order.ts` 에 있다(`common/` 은 `modules/` 를 import 할 수 없다).

- **`brandId`** — 그 브랜드 제품이 한 줄이라도 든 주문. ⚠️ **`OrderItem` 에는 `Product` relation 이
  없어**(`productId` 는 순수 스칼라) `items.some.product.brandId` 를 못 쓴다. 그래서 브랜드의
  `productIds` 를 먼저 조회하는 2단계 패턴(settlement 와 동일)을 쓰고, 브랜드 소속 경로가 둘이라
  `OR` 로 함께 잡는다 — 일반 라인은 `Product.brandId`, 제품 없는 시딩 직접입력 라인은
  `OrderItem.brandId` 스냅샷. 한쪽만 걸면 시딩 주문이 조용히 빠진다.
- **`excludePaymentStatus`** — 어드민 목록이 버려진 체크아웃(미결제)을 기본으로 감추는 용도.
  ⚠️ **서버 기본값이 아니라 klow_admin 이 명시적으로 보내는 값**이다 — 기본값으로 만들면 같은
  엔드포인트를 쓰는 환불 페이지 등 다른 소비자까지 조용히 필터링된다. `paymentStatus` 가 함께
  오면 그쪽이 이긴다(어드민은 결제 상태 필을 고르면 제외를 안 보내 숨김이 자동 해제된다).
  ⚠️ 감추는 축은 `paymentStatus` 뿐이고 **`status='pending'`(대기중)은 감추지 않는다** — 일반
  주문은 결제에 성공해도 발송 전까지 `status` 가 `pending` 이라(위 **상태** 항목) 그걸 감추면
  "결제완료·미발송" 처리 큐가 통째로 사라진다.

**`type` 쿼리 (주문 유형 필터)** — `Order.isSeeding` + `Order.channel` 두 컬럼을 한 축으로 접은
값이라 DB enum 이 아니다. `seeding`(무가 시딩) / `onsite`(부스 QR 현장결제, 배송 없음) /
`general`(그 외 일반 결제 주문) 셋은 배타적이라 합집합이 전체다. ⚠️ **시딩 주문도 `channel` 은
기본값 `web`** 이므로 `isSeeding` 을 먼저 걸러야 `general` 에 섞이지 않는다. 화이트리스트 밖 값은
필터를 걸지 않고 무시한다(무검증인 `status`/`paymentStatus` 와 달리 Prisma 에러로 새지 않는다).
어드민 주문 목록의 **유형 컬럼 배지**(일반/시딩/현장)와 상단 필터 pill 이 이 축을 쓴다.

## public-orders.controller.ts (`@Controller('v1/orders')`)

> 가드는 라우트별 상이 — 회원 전용은 `UserGuard`, 회원/비회원 공용은 `OptionalUserGuard`, 비회원 흐름은 public + `THROTTLE_TIGHT`.

| Method | Path                                | Guard            | 기능                                                                          |
|--------|-------------------------------------|------------------|-------------------------------------------------------------------------------|
| POST   | `/v1/orders`                        | OptionalUser     | 주문 생성 (약관 3종 동의 + IP + fxRateSnapshot 저장, `Zod literal(true)` 검증). 비회원이면 `userId=null` + 해당 주문 한정 HMAC 게스트 쿠키 발급. 응답은 `{ id }` |
| POST   | `/v1/orders/onsite`                 | OptionalUser     | 현장(박람회 부스) QR 주문 생성 — 배송지 없이 `email` + `items` + `countryCode?`(가격 기준국, 미지정 US) + 동의 2종(`agreedToTerms`·`agreedToPgDataSharing`). 게스트면 동일하게 주문 바인딩 쿠키 발급. 응답 `{ id }` |
| POST   | `/v1/orders/quote`                  | public           | 결제 전 가격 견적 — 목적국 기준 라인 단가/배송비/합계(read-only). 주문 생성과 **동일 `priceLine`** 이라 견적가 == 청구가. 배송 불가면 `shippable:false` |
| GET    | `/v1/orders/mine`                   | User             | 내 주문 목록 — `paymentStatus ∈ {paid, refunded}` 만, 최근 50건. (미결제·실패 주문은 `/v1/orders/:id` 직접 접근으로만) |
| POST   | `/v1/orders/lookup`                 | public (TIGHT)   | 비회원 주문 조회 — `orderId`(cuid) + `email` 매칭                              |
| POST   | `/v1/orders/guest-cancel/request-otp` | public (TIGHT) | 비회원 취소 1단계 — 주문/이메일 매칭 시에만 OTP 발송. 응답은 항상 `{ ok: true }`(존재 oracle 차단) |
| POST   | `/v1/orders/guest-cancel`           | public (TIGHT)   | 비회원 취소 2단계 — 주문 바인딩 OTP 검증 후 취소/환불                          |
| GET    | `/v1/orders/:id/tracking`           | OptionalUser     | 고객용 배송추적 — 결제완료 메일 서명 토큰(`?t=`) / 회원 세션 / 게스트 쿠키 중 하나로 인증, 캐시된 추적 데이터 반환. 고객 선택 시딩 주문은 표시 제품명을 `SeedingClaim.selectedSkus` 로 파생(→ [seeding](./seeding.md) 고객 대면 제품명). ⚠️ `shipmentTrackingStatus` 는 **국내 자체배송(`carrier='DOMESTIC'`)에 별도 분기**가 있다 — EFS 송장번호가 영영 없어 기본 `!trackingNumber → preparing` 규칙을 그대로 태우면 발송 후에도 "배송 준비 중"에 갇힌다 |
| GET    | `/v1/orders/:id`                    | User             | 주문 상세 (본인 ownership 확인)                                               |
| PATCH  | `/v1/orders/:id/cancel`             | User             | 주문 취소 — `paid` 면 Eximbay 환불 후 `refunded`, `pending` 이면 `cancelled`. `shipped`/`completed`/`cancelled` 는 400(반품 절차로) |

### `POST /v1/orders` 국가별 필수 필드 (`CreateOrderInput` refine)

- `countryCode`(ISO alpha-2) 필수. `CN` → `recipientTaxId`(18자리 거민신분증), `US` → `state`,
  `JP` → `recipientNameEn` + `addressLine1En`.
- `email` 은 게스트 필수(회원은 생략 시 세션 이메일 폴백, 입력값 우선). 둘 다 없으면 400.
- `shippingCarrier` 는 구버전 클라 호환용으로만 받고 **서버가 무시**한다(캐리어는 목적국·무게로 서버 결정).
- `campaign`(≤16자)은 서버가 목적국 기준으로 재검증해 **그 링크에 세일가가 정해진 제품만** 그 가격으로
  청구하고(국가 핀·국가 할인을 이긴다 — max 병합 아님), 세일가 적용 여부와 무관하게 `Order.campaignId`
  로 귀속만 기록한다. ⚠️ 세일가도 현지통화 값이라 `billingRate` 가드가 국가 핀과 **함께** 검사한다
  (안 그러면 FX 미해결국에서 `¥3,000` 이 `$3,000` 으로 청구된다 — `modules/orders/billing-rate.ts`).

## 참고

- 결제 흐름 전체는 [payment](./payment.md) 참고. 게스트(비회원) 주문은 `guest-order-token.ts` 의 HMAC 토큰 쿠키로 `prepare`/`report-failure` 를 인증한다.
- 배송 송장/추적 발급은 [shipments](./shipments.md) 참고.
- 약관 동의 텍스트는 `/legal/[slug]?lang=ko` (이중언어 약관) 에서 제공.
