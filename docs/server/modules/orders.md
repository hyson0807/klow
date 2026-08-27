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
| GET    | `/admin/orders`               | 주문 목록 — 쿼리 `status` / `paymentStatus` / `excludePaymentStatus`(CSV) / `type` / `excludeZeroTotal`(bool) / `brandId` / `yearMonth`(`YYYY-MM`) / `withRevenue`(bool) / `take`(1~200, 기본 100) / `skip`. 정렬 `createdAt desc, id desc`. 응답 `{ data, total, pendingTotal, revenue }` — `pendingTotal` 은 **status/type/brand 필터와 무관한 미결제 건수**로, 어드민이 미결제를 기본 숨김하므로 "숨겨진 N건" 배너에 쓴다(같은 `$transaction` 에 얹어 별도 왕복이 없다). ⚠️ 단 **`yearMonth` 창은 따라간다** — 배너가 "클릭하면 보이는 건수"를 약속하는데 클릭이 설정하는 건 `paymentStatus` 뿐이고 월 창은 그대로 남으므로, 무시하면 "12건 숨겨져 있음"을 눌러 3건만 보이는 상태가 된다. `revenue` 는 `yearMonth` 또는 `withRevenue` 를 보냈을 때만 채워지는 **매출액**(아래 항목) |
| GET    | `/admin/orders/:id`           | 주문 상세                                           |

> ⚠️ 위 두 조회만 `ADMIN_ORDER_INCLUDE`(= `items` + `seedingClaim`)를 쓴다. `seedingClaim` 은 **고객 선택 시딩의 표시 제품명**용이다 — `OrderItem.productName` 이 실제 제품명이 아니라 발급 시 동결된 영문 통관 품명이라, 어드민 화면이 바이어가 고른 제품으로 갈아끼우려면 필요하다(→ [seeding](./seeding.md), 클라 미러는 `klow_admin/src/lib/seeding-display.ts`). 공용 `ORDER_INCLUDE` 를 넓히지 않은 이유는 그게 create/quote/고객 조회까지 공유해 결제 경로에 불필요한 조인이 얹히기 때문이다.

| PATCH  | `/admin/orders/:id/status`    | 주문 상태 변경 — `{ status: 'pending'\|'processing'\|'shipped'\|'completed' }`. 역행·`cancelled` 주문 변경은 400 |
| PATCH  | `/admin/orders/:id/reconcile-payment` | **결제 재확인** — 미결제로 남은 주문을 Eximbay 에 직접 조회(`/v1/payments/retrieve`, `key_field='order_id'`)해 실제 승인(`SALE`/`AUTH`)이면 `markPaid` 로 확정. 응답 `{ result: 'paid'\|'not_paid'\|'not_found'\|'mismatch', order }` (확정 성공 시에만 `order` 동봉 — 어드민이 재조회하지 않게, `refund` 와 같은 관례). 15분 주기 `payment-reconcile` 크론과 **같은 경로**이고 운영자가 즉시 처리하기 위한 수동 트리거다. ⚠️ **임의로 `paid` 를 찍는 엔드포인트가 아니다** — 반드시 PG 재조회를 거치고 금액이 어긋나면(`mismatch`) 전이하지 않는다. 손으로 결제완료를 찍게 하면 미결제 주문이 정산에 섞인다 |
| PATCH  | `/admin/orders/:id/refund`    | 환불/취소 처리 — `{ reason: 1~500자 }`. `paid` 면 Eximbay cancel 호출 후 `refunded`, `pending` 이면 결제 없이 `cancelled`. 이미 취소·환불·실패 주문은 400 |
| PATCH  | `/admin/orders/:id/recipient` | 수화인(배송) 정보 수정 — EFS 송장 인쇄 필드만(`fullName`/`phone`/`email`/주소/`state`/영문명·영문주소/`recipientTaxId`). 국가·품목·금액은 불변이고, 국가별 필수(US→state, JP→영문, CN·MX→세금식별코드)는 주문의 기존 `countryCode` 로 `assertEfsCountryFields` 가 강제(세금식별코드는 형식까지 검사). 발급된 송장 반영은 `POST /admin/shipments/:id/cancel-reissue`(취소+재발급, 송장번호가 바뀐다) 별도 호출 — EFS `ChangeCnee` 의 city 칸이 좁아 US "City, State" 를 못 담아 우회하는 것이라 `change-cnee` 라우트는 존재하지 않는다 |

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
- **`excludeZeroTotal`** (bool) — 청구액이 `$0` 인 주문(`Order.totalUsd = 0`)을 뺀다. 대부분은
  **브랜드 결제(무료) 시딩 링크의 신청 건**이라 고객 청구가 애초에 0인데, 그게 처리해야 할 유상
  주문 사이에 섞여 목록을 덮는다. 어드민 주문 목록의 **`주문금액` 필터** 전용이다.
  ⚠️ `where` 를 목록·총건수·매출 집계가 공유하므로 **매출 카드의 `결제 건수`·`평균 주문액`도
  같은 모집단으로 함께 좁혀진다** — 표에서 검산하는 관계가 유지된다(합계는 어차피 불변).
  ⚠️ **`pendingTotal` 도 따라간다** — 아래 `yearMonth` 와 같은 이유다. 배너 클릭이 바꾸는 건
  `paymentStatus` 뿐이라 금액 필터가 그대로 남고, 무시하면 배너 건수와 실제로 보이는 건수가 갈린다.
  ⚠️ **`.default()` 금지** + zod 가 `z.coerce.boolean()` 이라 **`excludeZeroTotal=false` 도 `true`**
  다(아래 `withRevenue` 와 같은 함정). 끄려면 파라미터를 **보내지 않는다**.
- **`yearMonth`** (`YYYY-MM`, KST 캘린더월) — 어드민 목록의 월 선택기. zod 프리미티브
  `KstYearMonth`(`common/validation/shared.ts`)가 `parseKstYearMonth` 로 달력 유효성까지 본다.
  ⚠️ **`.default()` 를 주지 않는다** — 기본값을 주면 `yearMonth` 를 안 보내는 환불 페이지가 조용히
  한 달로 잘린다(`excludePaymentStatus`·`take` 와 같은 함정). 미전달 = 전체 기간 = 종전 동작.
- **`withRevenue`** (bool) — `yearMonth` 없이도 `revenue` 를 계산한다. 어드민 주문 목록의
  **`전체 기간` 토글** 전용이다(월을 해제해도 매출 카드가 `—` 로 비지 않게).
  ⚠️ 마찬가지로 **`.default(true)` 금지** — 매출 카드가 없는 환불 페이지에 `groupBy` + fx 조회
  왕복이 조용히 얹힌다. ⚠️ zod 가 `z.coerce.boolean()` 이라 **`withRevenue=false` 도 `true`** 로
  읽힌다(문자열 `'false'` 가 truthy). 끄려면 파라미터를 **보내지 않는다** — klow_admin 클라이언트가
  그렇게 한다.

### 매출액 (`revenue`)

`yearMonth` **또는** `withRevenue` 를 보내면 응답에 `revenue: { usdCents, krw, paidCount, fxFallbackRate }`
가 실린다(둘 다 미전달 시 `null` — 집계 쿼리도 fx 조회도 하지 않으므로 환불 페이지는 추가 비용이
0 이다). 어드민 주문 목록 상단의 매출 카드 3개(매출액 / 결제 건수 / 평균 주문액)가 이걸 쓴다.
집계 창은 목록 창을 그대로 따라간다 — `yearMonth` 면 그 달, `withRevenue` 단독이면 **전체 기간**
(`where` 에 `createdAt` 이 안 붙는 것 말고는 경로가 같아서 표로 검산하는 관계가 유지된다).

⚠️ **용어 주의 — 이 숫자는 `stats.service.gmvKrw`(대시보드 라벨 `거래액`)를 월·필터 범위로 좁힌
값이다.** 같은 저장소에서 `매출`은 이미 세 가지를 가리킨다(`subscriptionRevenueKrw` 구독매출 /
`shippingBilledKrw` 수출 매출액 / `totalRevenueKrw` 총매출 = 앞 둘의 합). 주문 화면 라벨이
`{YYYY-MM} 매출액` / `전체 기간 매출액` 인 것은 UI 결정이고, 그래서 카드에 `결제완료 주문 총액(배송비 포함) · 환불 제외` 를
병기한다 — 안 적으면 같은 공식이 대시보드에서는 `거래액`, 여기서는 `매출`로 보여 버그로 신고된다.
배송비 포함 · 시딩(₩0)·현장 결제 포함이고, **환불이 나면 `paymentStatus` 가 `refunded` 로 바뀌어
그 달 숫자가 소급 감소한다**(`gmvKrw` 와 같은 정책).

- **월 경계는 `createdAt`(주문일) 기준**이고 목록 필터와 **같은 창**이다. 목록의 '주문일' 열·정렬
  키와 같은 축이라 카드 숫자를 표에서 검산할 수 있고, 모든 주문이 가진 유일한 시각이므로
  미결제·실패·취소 주문이 목록에서 사라지지 않는다("숨겨진 미결제 N건" 배너가 그에 의존한다).
  ⚠️ 그래서 대시보드 `GET /admin/stats/kpi` 의 **`거래액`(`gmvKrw`, `paidAt` 기준)과 월경계에서
  소폭 다르다** — 월말 주문 ↔ 월초 결제 건이 서로 다른 달에 잡힌다. 의도된 차이다.
- **필터를 반영한다** — `buildAdminOrderWhere()` 가 만든 **같은 `where` 객체**를 재사용한다
  (브랜드 필터가 2단계 조회라 조건을 다시 적으면 카드와 표가 조용히 갈린다). 단 **결제상태만
  `paid` 로 덮는다** — 매출 정의가 결제완료 고정이기 때문이고, 반영하면 운영자가 '환불완료'를
  고른 순간 카드가 "환불 주문 중 결제완료" = $0 이 되어 오해를 만든다.
- **화면 표시 통화는 `usdCents`(USD)** 다 — `Order.totalUsd` 단순 합이라 **환율이 개입하지
  않는다**(PG 청구 정본 통화). 그래서 카드에 주문 시점 환율 각주가 없다. `krw` 는 같은 집합의
  원화 환산으로 응답에 남아 대시보드 `거래액`과의 검산에 쓰인다.
- **원화 환산은 `Order.fxRateSnapshot`(주문 시점 환율)**, 없는 legacy 주문만 `resolveFxRate`
  라이브 환율로 폴백하고 그 값을 `fxFallbackRate` 로 함께 내린다(`stats.service` 와 같은 규약).
  라이브 환율로 통일하면 과거 달 숫자가 매일 바뀐다.
- 집계는 `groupBy(by: ['fxRateSnapshot'], _sum: { totalUsd })` + 순수 함수
  `order-revenue.ts foldRevenue()`. `Σ(usdᵢ×fx) = fx×Σusdᵢ` 라 환율별로 묶어 곱하는 것이 행
  단위 곱셈과 대수적으로 동일하면서 행 수가 유한하다(원시 SQL 은 where 복제, `findMany` 는 행
  수 무제한이라 둘 다 탈락 — 자세한 근거는 그 파일 상단 주석). 반올림은 `gmvKrw` 의
  `ROUND(SUM(line))` 과 맞춰 **총합에 한 번만**. 회귀 잠금 `__tests__/order-revenue.spec.ts`.
  (인덱스는 `Order` 의 단일 컬럼 `createdAt`·`paymentStatus` 로 충분한 규모다 — 트래픽이 커지면
  `@@index([paymentStatus, createdAt])` 이 다음 선택지이고, 지금 마이그레이션을 넣을 이유는 없다.)

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

- `countryCode`(ISO alpha-2) 필수. `US` → `state`, `JP` → `recipientNameEn` + `addressLine1En`,
  `CN`/`MX` → `recipientTaxId`(EFS 31번 세금식별코드 — 아래 참고).
- **세금식별코드(EFS 31번)는 배송국별 규칙 테이블 `TAX_ID_RULES`(`common/validation/shared.ts`)가
  단일 출처**다: `CN` = 거민신분증 18자리(숫자 17 + 마지막 숫자 또는 X), `MX` = RFC 12~13자
  (`^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$`. RFC 없는 개인은 제네릭 `XAXX010101000` / 외국인 `XEXX010101000`).
  ⚠️ **zod 필드에 정규식을 걸지 않는다** — 국가마다 형식이 달라 필드 레벨 정규식은 배송국이 바뀌는
  순간 오탐이 된다(실제로 CN 정규식이 박혀 있어 멕시코 RFC 가 무조건 400 이었다). 값은
  `recipientAddressFields` 가 `.trim().toUpperCase()` 정규화만 해서 받고, 판정은 배송국을 아는 두
  소비자가 같은 테이블로 한다 — `CreateOrderInput.superRefine`(body 에 `countryCode` 가 있는 흐름)과
  `assertEfsCountryFields`(시딩 claim/checkout·어드민 수화인 수정처럼 국가가 body 에 없는 흐름.
  ⚠️ 이쪽은 존재 여부뿐 아니라 **형식까지** 봐야 그 세 경로만 검증 없이 새지 않는다).
  국가를 늘릴 땐 테이블에만 추가하고, klow_web `src/lib/tax-id.ts` · klow_admin `src/lib/constants.ts`
  미러를 함께 맞춘다(어긋나면 클라가 통과시킨 값을 서버가 400 으로 막는다).
  `required` 는 "값이 아예 없을 때 막느냐"만 가른다(false 여도 값이 오면 형식은 검사). 현재 CN·MX 둘 다 true.
  klow_web 미러는 이 플래그를 갖지 않는다 — 입력 화면은 규칙이 있으면 언제나 필수로 걷는다.

  ⚠️ **배포 순서: klow_server → klow_web → klow_admin, 연달아.** 구 프론트는 RFC 를 보내지 않으므로
  서버가 먼저 올라간 창 동안 멕시코 건이 400 이 된다. 실제 노출은 **시딩 claim 하나**뿐이다 —
  일반 체크아웃은 `ShippingCountry.enabled` 화이트리스트(현재 13개국)에 MX 가 없어 애초에 차단돼
  있고, 시딩은 `enabled` 를 안 보고 요율표(MX 71티어)로만 판정하기 때문이다. 그래서 **MX 를 어드민
  '국가 설정' 탭에서 켜는 건 세 배포가 끝난 뒤**에 한다 — 그러면 체크아웃 경로는 창을 아예 겪지 않는다.
  ⚠️ 서버 배포 직후 klow_admin 배포 전까지는 **기존 MX 주문의 수화인 정보 수정도 400** 이다
  (구 어드민이 `recipientTaxId` 를 안 보내는데 서버는 필수로 본다). 고객 대면 경로는 아니다.
- `email` 은 게스트 필수(회원은 생략 시 세션 이메일 폴백, 입력값 우선). 둘 다 없으면 400.
- `shippingCarrier` 는 구버전 클라 호환용으로만 받고 **서버가 무시**한다(캐리어는 목적국·무게로 서버 결정).
- `promotion`(≤16자)은 서버가 목적국 기준으로 재검증해 **그 링크에 세일가가 정해진 제품만** 그 가격으로
  청구하고(국가 핀·국가 할인을 이긴다 — max 병합 아님), 세일가 적용 여부와 무관하게 `Order.promotionId`
  로 귀속만 기록한다. ⚠️ 세일가도 현지통화 값이라 `billingRate` 가드가 국가 핀과 **함께** 검사한다
  (안 그러면 FX 미해결국에서 `¥3,000` 이 `$3,000` 으로 청구된다 — `modules/orders/billing-rate.ts`).

## 참고

- 결제 흐름 전체는 [payment](./payment.md) 참고. 게스트(비회원) 주문은 `guest-order-token.ts` 의 HMAC 토큰 쿠키로 `prepare`/`report-failure` 를 인증한다.
- 배송 송장/추적 발급은 [shipments](./shipments.md) 참고.
- 약관 동의 텍스트는 `/legal/[slug]?lang=ko` (이중언어 약관) 에서 제공.
