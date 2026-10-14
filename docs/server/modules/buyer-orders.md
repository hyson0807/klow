# buyer-orders — 바이어 샘플 주문 · 결제 (klow.kr/ 바이어 공간)

- **모듈 경로**: `src/modules/buyer-orders/`
- **목적**: 바이어 공간([buyer](./buyer.md))의 샘플박스를 **실주문 + 엑심베이 실결제**로 만든다. 결제가 끝나면 브랜드별 입고 행이 생기고 브랜드·바이어·운영팀에 메일이 간다.
- **설계 정본**: [`docs/plan/buyer-sample-order/`](../../plan/buyer-sample-order/README.md) — 결정 D1~D8 은 `README.md`, 불변식 G1~G10 은 `implementation-plan.md §1`.
- **관련 파일**: `buyer-orders.service.ts`(견적·생성·목록·상세 + 상태 판정 `buyerSampleStatus`) · `public-buyer-orders.controller.ts` · `buyer-sample-pricing.ts`(배송비 규칙 — 순수) · `buyer-sample-paid.ts`(결제 완료 후속효과 — **함수 파일**, `payment.service#markPaid` 가 부른다) · `buyer-sample-email.ts`(메일 3종 — 순수) · 검증 `common/validation/buyer-order.ts`(+ `order.ts#checkRecipientCountryFields` 공용) · 결제 `payment/payment.service.ts#prepareForBuyer`·`resultRedirectUrl`
- **마이그레이션**: `20261014063926_add_buyer_sample_order` — enum 2(`OrderKind`·`OrderBrandIntakeStatus`) + 테이블 2(`OrderBrandIntake`·`OrderPartialRefund`) + `Order.kind`(기본 `consumer`)·`buyerUserId`·`buyerNote` · `OrderItem.cancelledAt` · `ShopSettings.klowSender*` 4칸. 전부 ADD/CREATE 라 **롤링 안전 · 백필 없음**(기존 주문은 기본값 `consumer`).
- **env**: 새 env 없음. 운영팀 수신함은 바이어 문의와 같은 `BUYER_INQUIRY_EMAIL` → `CONTACT_INBOX_EMAIL` → `team@klow.kr`. 브랜드 메일 링크는 `BRAND_FRONTEND_URL`. cron 없음.

⚠️⚠️ **소비자 `Order` 를 재사용한다**(`kind = buyer_sample`, G1). 송장·트래킹·엑심베이 return/webhook/재확인 크론·환불이 전부 `Order.id` 기준이기 때문이다. 대가로 **소비자 집계는 `kind: consumer` 로 걸러야 한다**(G4) — 걸러 둔 곳은 `implementation-plan.md §5`. 새 소비자 집계를 만들면 거기에 추가할 것.

⚠️⚠️ **브랜드 정산 없음**(D2) — KLOW 가 미리 사입한 재고를 샘플가로 판다. 주문 라인의 `settlementPriceKrw`·`costKrw` 는 항상 `null`.

## 공개 API (`@Controller('v1/buyer')`, 전부 `BuyerGuard`)

로그인한 바이어 전원(검수 상태 무관 — D1). 소비자 쿠키(`klow_sid`)·게스트 쿠키로는 닿지 않는다(G6).

| 메서드 · 경로 | 동작 |
|---|---|
| `POST orders/quote` `{productIds, countryCode}` | 견적. 공개 화면과 **같은 노출 판정**(`BuyerPublicService.visibleByProductIds`)을 통과하고 샘플가(구간표 1행)가 있는 제품만 계산. 내려간 제품은 거절하지 않고 `unavailableProductIds` 로 알린다(금액은 남은 것 기준). 응답 `{lines, subtotalUsdCents, shippingUsdCents, totalUsdCents, freeShipping, freeShippingSkus, unavailableProductIds}`. 국가 게이트(배송지원 제외·요율 미설정·EFS 제외구역)는 소비자와 같은 `shipping.resolveProductShipping` 이 400 |
| `POST orders` | 주문 생성(pending). 본문 = 소비자 주문의 수화인 칸(`recipientAddressFields` — 국가별 필수 규칙 공용) + `country`·`countryCode`·`productIds`·`note?`(≤500, **운영팀만 본다**)·`email?`(생략 시 계정 이메일)·동의 3종 `literal(true)`. **내려간 제품이 하나라도 있으면 400 `samples_unavailable` + `productIds`** — 바이어가 담은 것과 다른 걸 결제시키지 않는다. 가격·배송비는 서버가 재계산(G5). → `{orderId, totalUsdCents}` |
| `GET orders` | 내 요청 목록(최근 50) — **결제창을 연 적 없는 pending 은 뺀다**(실패·환불은 남긴다) |
| `GET orders/:id` | 상세. 남의 주문·소비자 주문은 404. 응답의 `status` 는 서버가 계산한다(아래) |
| `POST payment/prepare` `{orderId}` | 엑심베이 결제창 준비 — 소비자 `v1/payment/prepare` 와 **같은 payload**. 해외 카드(USD)만(국내 MID 없음). 상품 링크는 `/shop/products/:id` |

### 요청 상태 (`buyerSampleStatus`)

| status | 조건 |
|---|---|
| `awaiting_payment` | `paymentStatus=pending` |
| `payment_failed` | `failed` |
| `requested` | 결제완료 · 아직 어느 브랜드도 발송 전(입고 행 생성 전 포함) |
| `preparing` | 한 브랜드라도 `brand_shipped`/`received` |
| `packed` | 취소 안 된 전 브랜드 `received` |
| `cancelled` | `refunded`/`cancelled` 또는 전 브랜드 `cancelled` |

발송·배송완료는 합포장 송장 단계(진행표 33행)가 더한다.

## 배송비 (`buyer-sample-pricing.ts`, D3)

SKU(= 품목 — 샘플은 제품당 1개) **5개 이상이면 0**, 그 미만은 **목적국 500g 티어 요율 1회**(`customerShippingRate` · `perBrandShippingFeeUsdCents` — 소비자의 브랜드당 기본 배송비와 같은 값·같은 환산). 브랜드 수와 무관하다(한 박스·한 송장). 주문에는 `shippingFeeUsd` 하나만 남고 브랜드별 스냅샷(`shippingFeeByBrand`·`shippingCarrierByBrand`)은 비운다. `shippingCarrier` = 목적국 고정 캐리어.

## 결제 (payment 모듈과의 경계)

- **확정 경로는 소비자와 같다** — `/payment/return` · `/webhooks/eximbay` · `v1/payment/verify` · 재확인 크론. `parseAndMarkPaid` 의 rescode 게이트·금액 재검증·조건부 update 는 **손대지 않았다**(G2).
- `markPaid` 의 pending→paid 전이 직후 `kind=buyer_sample` 이면 **소비자 후속효과를 전부 건너뛰고**(스토어 통계·카트·확인 메일·시딩·**자동 송장 발급**·브랜드 알림톡) `onBuyerSamplePaidSafe` 만 부른다(G3). 이게 새면 브랜드 송화인 명의 EFS 송장이 브랜드별로 자동 발급된다.
- `/payment/return` 의 303 목적지(`resultRedirectUrl`): 바이어 주문 → `{FRONTEND_URL}/shop/checkout/complete?order=<id>`(그 화면은 querystring 이 아니라 서버 상태를 읽는다), 그 외 → 기존 `/checkout/redirect?…&klow_verified=1`.
- 순환 없음: `BuyerOrdersModule → PaymentModule`(prepare). 반대 방향은 DI 가 아니라 함수 import(`buyer-sample-paid.ts`).

## 결제 완료 후속효과 (`onBuyerSamplePaidSafe` — 절대 throw 안 함)

1. 브랜드별 `OrderBrandIntake` 행(`createMany skipDuplicates`). 실패하면 Sentry(어드민 입고 화면이 비므로)
2. 브랜드 메일 — 그 브랜드의 이메일 있는 `BrandUser` 전원. 보냈으면 `brandEmailedAt`, 받을 사람이 없으면 운영팀 메일에 "이메일 없음" 경고. ⚠️ **바이어 신원·메모를 싣지 않는다**(국가만 — G7). 보낼 곳 = `ShopSettings.klowSender*`, 비었으면 `efs-billing/klow-company.ts` 회사 주소. replyTo = 운영팀
3. 바이어 결제 확인 메일(영어) · 운영팀 알림 메일(바이어 신원·메모 포함, replyTo = 바이어)

## 소비자 쪽에서 바뀐 것

- `common/validation/order.ts` — 국가별 수화인 필수 규칙을 `checkRecipientCountryFields` 로 뽑았다(`CreateOrderInput` 동작 동일).
- `kind: consumer` 필터 — `orders/contact-population.ts#CONTACT_ORDER_WHERE`(브랜드 CRM·어드민 컨택트·리뷰 요청) · 어드민 주문 목록 · 송장 대기 그룹 · 정산 대상 · 브랜드관 판매 통계 · 주별 주문 유형 추이. 전체 목록과 판단은 트랙 문서 §5.
