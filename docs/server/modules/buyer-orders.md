# buyer-orders — 바이어 제품 샘플 주문 (KLOW 직접 조달)

- **모듈 경로**: `src/modules/buyer-orders/`
- **목적**: 바이어 공간 제품 상세의 **"Get N samples"** — 어드민이 정한 샘플 개수·단가 그대로 엑심베이(USD)로 결제한다. KLOW 가 그 제품을 직접 사서 포장해 보낸다(브랜드는 이 주문을 모른다). 송장은 어드민 '바이어 주문' 상세의 **KLOW 송장**(진행표 61행 C).
- **설계 정본**: [`docs/plan/buyer-sample-checkout/`](../../plan/buyer-sample-checkout/README.md) — 결정 D1~D12 는 `README.md`, 게이트 G1~G8 은 `implementation-plan.md §1`.
- **관련 파일**: `buyer-orders.service.ts`(국가·견적·생성·바이어 조회 + `buyerSampleStatus`) · `buyer-orders-admin.service.ts` · `buyer-sample-pricing.ts`(7kg · 총액 규칙) · `buyer-sample-paid.ts`(결제 확정 후속효과 — **함수 파일**, `payment.service#markPaid` 가 부른다) · `buyer-sample-email.ts`(메일 2종) · 검증 `common/validation/buyer-order.ts`
- **마이그레이션**: `20261102143319_add_buyer_sample_checkout` — enum `OrderKind`(consumer·buyer_sample) · `Order.kind`(기본 consumer)·`buyerUserId`(FK SetNull) · `OrderItem.buyerProductId`·`majorProductId`(FK SetNull) · `BuyerProduct`·`BuyerMajorProduct` 의 `sampleQty`·`sampleUnitUsdCents` + 같은 SQL 안의 멱등 백필(인디 구간표 `minQty=1` 행 단가 → `sampleUnitUsdCents`, 개수는 비움). 전부 ADD 라 롤링 안전.
- **의존**: BuyerAuthModule(BuyerGuard) · ShippingModule(`resolveCarrier`·`LogisticsRateService`) · PaymentModule(`prepareForBuyer`). PaymentModule 은 이 모듈을 import 하지 않는다 — 결제 후속효과는 함수 파일로 받는다. cron 없음. env 없음(메일 수신함은 바이어 문의와 같은 `BUYER_INQUIRY_EMAIL` → `CONTACT_INBOX_EMAIL` → `team@klow.kr`).

## 규칙

- **주문 1건 = 제품 1개 · 줄 1개.** 개수·단가는 어드민 값 그대로(수량 선택 없음 — D3). 샘플 칸(`sampleQty`·`sampleUnitUsdCents`)이 **둘 다** 있고 공개 화면과 같은 노출 판정(인디 `evaluate().visible` · 메이저 `majorVisible`)을 통과해야 한다. 아니면 **404 `sample not available`** 하나(이유를 흘리지 않는다).
- **금액은 서버만 계산한다(G1).** 총액 = `단가 × 개수 + 배송비`. 배송비 = 목적국 `SeedingRate` **7,000g 티어**(무게 올림 조회)의 원화 1회를 소비자 주문과 같은 함수(`perBrandShippingFeeUsdCents`, 현재 KRW 환율)로 USD 센트 환산. 주문에 `fxRateSnapshot` 을 저장하므로 결제 검증은 소비자와 같은 `totalUsd` 대조다.
- **국가 = 시딩 가능 국가**(`LogisticsRateService.supportedCountries()` — 요율표 + 국가 고정 캐리어) − 국내 자체배송국 − 7kg 티어 없는 국가. 배송지원(`enabled`) 화이트리스트와 **무관**하다. 캐리어·EFS 제외구역은 시딩과 같은 `ShippingService.resolveCarrier`(enabled 게이트 없음). 국내(DOMESTIC)·7kg 티어 없음은 **400 `no_sample_rate`**.
- **배송지 검증**은 소비자 체크아웃과 같은 `recipientAddressFields` + `checkRecipientCountryFields`(US 주 · JP 영문 주소 · CN/MX 세금번호 · EFS 바이트 캡). ⚠️ zod 문구는 한국어다(소비자와 공유) — 화면이 클라 검증으로 먼저 막는다.
- ⚠️⚠️ **줄은 브랜드에 묶지 않는다(G7).** `OrderItem.productId`·`brandId` NULL, 대신 `buyerProductId`(인디 — `BuyerProduct.id`) 또는 `majorProductId`. 이름·이미지·브랜드명은 스냅샷. 묶으면 브랜드 알림톡·스튜디오 주문현황·3PL 발송 대기·리뷰 요청으로 새어 나간다. 정산 단가·원가 스냅샷도 null.
- 주문 생성 값: `kind=buyer_sample` · `buyerUserId` · `userId=null` · `isSeeding=false` · `channel=web` · `shippingCarrier`=국가 고정 캐리어 · 동의 3종 시각 + IP · `email` 생략 시 바이어 계정 이메일. 브랜드별 스냅샷(`shippingCarrierByBrand`·`shippingFeeByBrand`)은 비운다.

## public-buyer-orders.controller.ts (`@Controller('v1/buyer')`, **BuyerGuard** — 로그인 바이어 전원, 검수 상태 무관 D6)

| Method | Path | 스로틀 | 기능 |
|---|---|---|---|
| GET | `/v1/buyer/sample-countries` | 전역 | `{ countries: [{iso2, nameEn}] }` — 주문서 국가 드롭다운(위 규칙, 영문명 순) |
| GET | `/v1/buyer/sample-quote?type=indie\|major&id=&country=&city?=&postalCode?=` | 전역 | `{ qty, unitUsdCents, subtotalUsdCents, shippingUsdCents, totalUsdCents }`. `id` = 바이어 공간 PDP 주소의 id(인디 = 원본 `Product.id`, 메이저 = `BuyerMajorProduct.id`). 404 `sample not available` · 400 `no_sample_rate` |
| POST | `/v1/buyer/sample-orders` | **10회/분/IP** | 바디 `{ type, id, fullName, phone, country, countryCode, state?, addressLine1, addressLine2?, city, postalCode, recipientTaxId?, recipientNameEn?, addressLine1En?, email?, agreedToTerms: true, agreedToRefund: true, agreedToPgDataSharing: true }` → `{ orderId, totalUsdCents }`(결제 대기 주문) |
| GET | `/v1/buyer/sample-orders/:id` | 전역 | 바이어 **본인** 주문만(남의 것·소비자 주문 404). `{ id, createdAt, paidAt, status, item: {type, name, brandName, image, qty, unitUsdCents}, subtotalUsdCents, shippingUsdCents, totalUsdCents, shipTo }` — 결제 결과 화면이 읽는다 |
| POST | `/v1/buyer/sample-orders/:id/prepare` | 전역 | 엑심베이 결제창 준비 — **해외 카드(USD)만**. 응답은 소비자 `POST /v1/payment/prepare` 와 같은 echo payload([payment](./payment.md)). 소유권 = `kind=buyer_sample && buyerUserId == 세션` |

`status` = `awaiting_payment`(결제 전·결제창 이탈) / `payment_failed` / `paid`(KLOW 구매·포장 중) / `shipped` / `delivered`(주문 `completed`) / `cancelled`(환불·취소).

**결제 확정**은 소비자와 **같은 경로**(`/payment/return` · `/webhooks/eximbay` · 재조정 cron)를 탄다 — Eximbay `order_id` 가 곧 `Order.id` 다. 차이는 둘뿐: ① `/payment/return` 의 303 목적지가 **`{FRONTEND_URL}/shop/sample-orders/:id`**(바이어 공간 결과 화면 — querystring 없이 서버 상태를 읽는다) ② `markPaid` 의 pending→paid 블록이 맨 앞에서 갈라져 **소비자 후속효과(브랜드관 통계 · 카트 · 소비자 확인 메일 · EFS 송장 자동 발급 · 브랜드 알림톡)를 전부 건너뛰고** `onBuyerSamplePaidSafe` 만 돈다(G8 — 바이어 결제 확인 메일(영어) + 운영팀 알림(한국어), 절대 throw 안 함). 바이어 `report-failure` 엔드포인트는 두지 않았다 — 실패는 서버 return 이 직접 `failed` 로 전이한다.

## admin-buyer-orders.controller.ts (`@Controller('admin/buyer/orders')`, AdminGuard)

| Method | Path | 기능 |
|---|---|---|
| GET | `/admin/buyer/orders?paymentStatus=&q=&take=&skip=` | `{ total, orders: [{id, createdAt, paidAt, paymentStatus, status, countryCode, country, totalUsdCents, buyer: {id,email,name,company,country,status}, item}] }`. **기본은 `pending`(결제창 이탈) 숨김** — `paymentStatus` 를 주면 그것만. `q` = 주문 id·이메일·수령인·회사·제품명 부분일치 |
| GET | `/admin/buyer/orders/:id` | 상세 — `buyer` · `shipTo`(영문 주소·세금번호 포함) · `items[]`(`type`·`publicProductId`(PDP 주소 id, 제품이 지워졌으면 null)·스냅샷) · `payment`(status·provider·tid·currency·method·failureReason·fx·금액 3종) · `carrier` · `shipments[]` · `canRefund`. 소비자 주문 id 는 404 |

`item` = `{ id, type: 'indie'|'major', publicProductId, name, brandName, image, qty, unitUsdCents }`.

**환불**은 기존 `POST /admin/orders/:id/refund`([orders](./orders.md) — 전액 `refundOrder`)를 그대로 쓴다(줄이 하나라 부분환불이 없다). ⚠️ KLOW 송장 발급 뒤 환불 400 은 C(61행)에서 서버에 건다 — 지금은 상세 응답 `canRefund` 로만 가린다.

## 소비자·브랜드 축에서 빠지는 곳 (G2 — 두 겹)

구조: 줄에 브랜드가 없어 `OrderItem.productId`/`brandId` 로 브랜드를 찾는 경로(스튜디오 주문현황 · 3PL 발송 대기 · 리뷰 요청 · 알림톡 · 브랜드관 판매 통계의 `Product` 조인)는 저절로 빠진다. 그 위에 **명시 `kind: consumer` 필터**:

| 자리 | 파일 |
|---|---|
| 브랜드 정산 후보·원장 | `settlement/settlement.service.ts` `SETTLEABLE_ORDER_WHERE` |
| 연락처 모집단(브랜드 CRM · 어드민 컨택트) | `orders/contact-population.ts` `CONTACT_ORDER_WHERE` |
| 소비자 주문 조회·게스트 취소(OTP) | `orders/orders.service.ts` `findConsumerOrder`(`findOneForUser`·`findOneForGuest` 가 거친다 — 바이어 주문은 404) |
| 어드민 주문 목록 `type=general` | `orders.service.ts` `buildAdminOrderWhere`(새 `type=buyerSample` = `kind=buyer_sample`, 유형 미지정이면 둘 다 보인다) |
| 소비자 결제 prepare | `payment.service.ts` `prepare`(소유권에 `kind=consumer`) |
| 송장 대기 그룹 + 브랜드 단위 송장 미리보기·발급(G3) | `shipments.service.ts` `listPendingGroups` · `assertBrandShipmentOrder`(400) |
| 대시보드 주문 유형 추세 | `stats/stats.service.ts` `orderTypeTrend`(거래액 `gmvKrw` 은 '전체 결제'라 **포함**) |
| 브랜드관 판매 통계 | `storefront-stats/storefront-sales.service.ts` |
| 엑심베이 정산서 업로드 | `settlement/pg-settlement.service.ts` — 미리보기 사유 **`buyer_sample`**(+ `buyerSampleCount`), `apply` 가 저장하지 않는다 |

⚠️ `/v1/orders/:id/tracking`(`getTracking`)은 아직 막지 않았다 — C 의 추적 메일이 이 화면을 게스트 토큰으로 연다(트랙 문서 C ③).
