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
  (`orders/chargeable-brands.ts`, 생성·견적 공유). create/quote 둘 다 `countryPrices` 를 `where: { iso2 }` 로 필터해 넘긴다.
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
- **현장(onsite) 주문**: 박람회 부스 QR 결제 — `channel='onsite'`, 배송지·캐리어·배송비 없음(`shippingFeeUsd=0`),
  단가는 `Product.onsitePriceUsd ?? basePriceUsd`, `onsiteExcluded` 제품은 차단. 결제 성공 시 송장 없이 바로
  `completed` 로 전이된다(`payment.markPaid`).
- **관련 파일**: `orders.service.ts`, `admin-orders.controller.ts`, `public-orders.controller.ts`, `chargeable-brands.ts`(청구 대상 브랜드·배송비 스냅샷·읽기 짝), `brand-weights.ts`(브랜드별 청구중량 → 캐리어 분기), `guest-order-token.ts`(비회원 주문 HMAC 토큰)

## admin-orders.controller.ts (`@Controller('admin/orders')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                          | 기능                                                |
|--------|-------------------------------|-----------------------------------------------------|
| GET    | `/admin/orders`               | 주문 목록 — 쿼리 `status` / `paymentStatus` / `take`(1~200, 기본 100) / `skip`. 정렬 `createdAt desc, id desc` |
| GET    | `/admin/orders/:id`           | 주문 상세                                           |
| PATCH  | `/admin/orders/:id/status`    | 주문 상태 변경 — `{ status: 'pending'\|'processing'\|'shipped'\|'completed' }`. 역행·`cancelled` 주문 변경은 400 |
| PATCH  | `/admin/orders/:id/refund`    | 환불/취소 처리 — `{ reason: 1~500자 }`. `paid` 면 Eximbay cancel 호출 후 `refunded`, `pending` 이면 결제 없이 `cancelled`. 이미 취소·환불·실패 주문은 400 |
| PATCH  | `/admin/orders/:id/recipient` | 수화인(배송) 정보 수정 — EFS 송장 인쇄 필드만(`fullName`/`phone`/`email`/주소/`state`/영문명·영문주소/`recipientTaxId`). 국가·품목·금액은 불변이고, 국가별 필수(US→state, JP→영문, CN→신분증)는 주문의 기존 `countryCode` 로 강제. 발급된 송장 반영은 `POST /admin/shipments/:id/change-cnee` 별도 호출 |

## public-orders.controller.ts (`@Controller('v1/orders')`)

> 가드는 라우트별 상이 — 회원 전용은 `UserGuard`, 회원/비회원 공용은 `OptionalUserGuard`, 비회원 흐름은 public + `THROTTLE_TIGHT`.

| Method | Path                                | Guard            | 기능                                                                          |
|--------|-------------------------------------|------------------|-------------------------------------------------------------------------------|
| POST   | `/v1/orders`                        | OptionalUser     | 주문 생성 (약관 3종 동의 + IP + fxRateSnapshot 저장, `Zod literal(true)` 검증). 비회원이면 `userId=null` + 해당 주문 한정 HMAC 게스트 쿠키 발급. 응답은 `{ id }` |
| POST   | `/v1/orders/onsite`                 | OptionalUser     | 현장(박람회 부스) QR 주문 생성 — 배송지 없이 `email` + `items` + 동의 2종(`agreedToTerms`·`agreedToPgDataSharing`). 게스트면 동일하게 주문 바인딩 쿠키 발급. 응답 `{ id }` |
| POST   | `/v1/orders/quote`                  | public           | 결제 전 가격 견적 — 목적국 기준 라인 단가/배송비/합계(read-only). 주문 생성과 **동일 `priceLine`** 이라 견적가 == 청구가. 배송 불가면 `shippable:false` |
| GET    | `/v1/orders/mine`                   | User             | 내 주문 목록 — `paymentStatus ∈ {paid, refunded}` 만, 최근 50건. (미결제·실패 주문은 `/v1/orders/:id` 직접 접근으로만) |
| POST   | `/v1/orders/lookup`                 | public (TIGHT)   | 비회원 주문 조회 — `orderId`(cuid) + `email` 매칭                              |
| POST   | `/v1/orders/guest-cancel/request-otp` | public (TIGHT) | 비회원 취소 1단계 — 주문/이메일 매칭 시에만 OTP 발송. 응답은 항상 `{ ok: true }`(존재 oracle 차단) |
| POST   | `/v1/orders/guest-cancel`           | public (TIGHT)   | 비회원 취소 2단계 — 주문 바인딩 OTP 검증 후 취소/환불                          |
| GET    | `/v1/orders/:id/tracking`           | OptionalUser     | 고객용 배송추적 — 결제완료 메일 서명 토큰(`?t=`) / 회원 세션 / 게스트 쿠키 중 하나로 인증, 캐시된 추적 데이터 반환 |
| GET    | `/v1/orders/:id`                    | User             | 주문 상세 (본인 ownership 확인)                                               |
| PATCH  | `/v1/orders/:id/cancel`             | User             | 주문 취소 — `paid` 면 Eximbay 환불 후 `refunded`, `pending` 이면 `cancelled`. `shipped`/`completed`/`cancelled` 는 400(반품 절차로) |

### `POST /v1/orders` 국가별 필수 필드 (`CreateOrderInput` refine)

- `countryCode`(ISO alpha-2) 필수. `CN` → `recipientTaxId`(18자리 거민신분증), `US` → `state`,
  `JP` → `recipientNameEn` + `addressLine1En`.
- `email` 은 게스트 필수(회원은 생략 시 세션 이메일 폴백, 입력값 우선). 둘 다 없으면 400.
- `shippingCarrier` 는 구버전 클라 호환용으로만 받고 **서버가 무시**한다(캐리어는 목적국·무게로 서버 결정).
- `campaign`(≤16자)은 서버가 재검증해 대상 브랜드·국가일 때만 할인을 반영하고, 할인 여부와 무관하게
  `Order.campaignId` 로 귀속만 기록한다.

## 참고

- 결제 흐름 전체는 [payment](./payment.md) 참고. 게스트(비회원) 주문은 `guest-order-token.ts` 의 HMAC 토큰 쿠키로 `prepare`/`report-failure` 를 인증한다.
- 배송 송장/추적 발급은 [shipments](./shipments.md) 참고.
- 약관 동의 텍스트는 `/legal/[slug]?lang=ko` (이중언어 약관) 에서 제공.
