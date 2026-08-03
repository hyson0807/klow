# payment — Eximbay 결제

- **모듈 경로**: `src/modules/payment/`
- **PG**: Eximbay (USD 결제)
- **흐름 요약**: `POST /v1/orders` (동의 + IP + fxRate snapshot) → `POST /v1/payment/prepare` → 클라 Eximbay JS SDK → `return_url 303` → `/checkout/redirect` → `POST /v1/payment/verify`
- **보강 경로**: `POST /webhooks/eximbay` (외부 IP 화이트리스트), `POST /v1/payment/report-failure` (pending→failed 멱등)
- **pending 주문 유효기간 (24h)**: `prepare()` 는 `paymentStatus === pending` 에 더해 `createdAt` 이 24시간 이내인지 검사하고, 넘으면 400 으로 거부한다(`PENDING_ORDER_TTL_MS`). `report-failure` 는 브라우저가 호출하는 구조라 결제창에서 탭을 닫으면 발생하지 않고, 그 행은 `pending` 으로 영구히 남는다. 청구액은 주문 시점의 `totalUsd`/`fxRateSnapshot` 으로 고정되므로 가드가 없으면 몇 달 묵은 주문이 그때의 가격·환율로 결제된다. 만료된 행을 별도 상태로 정리하는 크론은 없다 — 결제가 막히면 충분하고, 동의 시각·IP 기록은 보존한다.
- **상품 명세 (`product`/`surcharge`)**: 네이버페이는 상품명·수량·단가를 필수로 요구하고 누락 시 **X059**(`NaverPay payment fail`)로 거절한다. `buildOrderLines()` 가 `OrderItem` 을 최대 3줄로 전개하고(4개 이상이면 앞 2줄 + `"기타 N건"` 합산줄), 배송비·반올림 오차는 `surcharge` **잔차** 한 줄이 흡수해 `Σ(product) + Σ(surcharge) === payment.amount`(Eximbay Note 5)를 항상 만족시킨다. 국내·해외 양쪽 scope 모두 전송.
- **`tax` (국내 전용)**: 네이버페이 **포인트** 결제가 전 필드를 필수로 요구해 `scope==='kr'` 일 때만 붙인다. 전액 과세 역산(`amount_taxable = round(amount/1.1)`, `amount_vat` 는 뺄셈 잔차), `receipt_status='N'`(현금영수증 발급은 수취정보 UI 필요 — 미지원).
- **환불**: `payment.refundOrder` 가 `POST /v1/payments/{pgTid}/cancel` 호출
- **관련 파일**: `payment.service.ts`, `public-payment.controller.ts`, `webhook-payment.controller.ts`

## public-payment.controller.ts (`@Controller('v1/payment')`)

> **`UserGuard` 는 쓰지 않는다** — 회원/비회원 공용이다. `prepare`/`report-failure` 는 `OptionalUserGuard` 뒤에서
> 회원은 세션 소유권(`order.userId === user.id`), 게스트는 `klow_order` 쿠키 HMAC 이 그 `orderId` 에 대해 유효한지로
> 가드한다(둘 다 실패면 **404** `order not found` — 존재 oracle 회피). `verify` 는 가드 없는 public 이고 Eximbay
> 재조회 + 금액 검증으로 보호되며 `@Throttle(5회/분)` 이 걸려 있다.

| Method | Path                              | Guard                          | 기능                                                                       |
|--------|-----------------------------------|--------------------------------|-----------------------------------------------------------------------------|
| POST   | `/v1/payment/prepare`             | OptionalUser + 게스트 쿠키     | 결제 준비 — 바디 `{ orderId, issuerCountry?: 'KR' }`. 동의 3종 + ownership + 24h 유효기간 재검증 후 Eximbay `/v1/payments/ready` 로 `fgkey` 발급, 클라 SDK 가 그대로 되돌려 보낼 payload(`payment`/`merchant`/`buyer`/`url`/`settings`/`product`/`surcharge?`/`tax?`)를 echo 반환 |
| POST   | `/v1/payment/verify`              | public (`THROTTLE_TIGHT` 5/분) | 결제 결과 검증 — 바디 `{ querystring }`. Eximbay 재조회 + `pgCurrency` 기준 금액 검증(KRW ±1 / USD ±0.01) + `paymentStatus` 멱등 전이. 성공 시 게스트 주문 쿠키 정리, 응답 `{ orderId }` |
| POST   | `/v1/payment/report-failure`      | OptionalUser + 게스트 쿠키     | 결제 실패 보고 — 바디 `{ orderId, reason? ≤500자 }`. `pending → failed` 멱등 전이(다른 상태면 현재 상태 그대로 반환), 사유는 타임스탬프와 함께 `paymentFailureReason` 에 저장. 응답 `{ status }` |

### 국내(KR) 카드 결제 분기

`prepare` 에 `issuerCountry: 'KR'` 을 주면 **국내 전용 MID + KRW 정수 금액**(`totalUsd/100 × fxRateSnapshot` 반올림,
`settings.issuer_country='KR'`, `tax` 동봉)으로, 생략하면 **해외 MID + USD**(`totalUsd/100` 을 `"26.30"` 형태로)로
결제창을 연다. 어느 쪽으로 열렸는지는 `Order.pgCurrency` 에 영속화되고 `verify`/webhook/환불이 그 값으로 MID·통화·
금액을 복원한다(재-prepare 시 덮어써 "마지막 prepare == 실제 결제창"). `totalUsd` 가 없는 legacy 주문은 400.

## webhook-payment.controller.ts (`@Controller('webhooks')`)

| Method | Path                              | Guard                                       | 기능                                                  |
|--------|-----------------------------------|---------------------------------------------|-------------------------------------------------------|
| POST   | `/webhooks/eximbay`               | IP 화이트리스트 (`EXIMBAY_WEBHOOK_IPS`)     | Eximbay 비동기 알림(status_url). verify 누락 케이스 보강 처리 |

- `@HttpCode(200)` + 본문 `rescode=0000&resmsg=Success` 를 text/plain 으로 회신해야 Eximbay 가 retry 를 멈춘다.
  처리 중 예외가 나면 `rescode=9999&resmsg=<urlencoded>` 로 회신(= retry 유도).
- 소스 IP 는 `req.ip`(main.ts 의 trust proxy 기준 해석)로 판정 — XFF 스푸핑으로 화이트리스트를 우회할 수 없다.
  화이트리스트가 비어 있으면(dev) 검사를 건너뛰고, 미허용 IP 는 **403**.
- `verify` 와 동일한 `parseAndMarkPaid` 를 타되 `order_id`/`transaction_id` 가 없으면 조용히 무시한다.

## 결제 완료(pending→paid) 부수효과

`markPaid()` 의 진짜 전이(`count === 1`) 분기에서만, 멱등하게 순차 실행 — 모두 실패 격리(에러가 결제 전이를 롤백하지 않음):

1. `clearCartItemsForOrder` — 주문에 포함된 카트 항목 서버측 삭제.
2. `sendOrderConfirmationSafe` — 구매자에게 주문 확인 이메일(Resend).
3. `claimSeedingLinkSafe` — 유료 시딩 링크 pending→claimed.
4. `createShipmentsForOrderSafe` — EFS 송장 자동 발급(onsite 제외).
5. `notifyBrandsOfPaidOrderSafe` — **주문에 담긴 제품의 브랜드(들)에게 "새 주문 접수" 카카오 알림톡**(onsite 제외). 브랜드가 스튜디오 주문현황 탭에서 발송처리를 놓치지 않도록. 브랜드 집합은 송장과 동일 규칙(productId→`Product.brandId`, 없으면 `OrderItem.brandId`), 수신번호는 `Brand.senderPhone` 우선·없으면 `BrandUser.phone` 폴백. 발송은 `KakaoService`(`auth/kakao.service.ts`). 승인 템플릿("브랜드 일반주문 발생") 변수는 **`#{country}`(주문국)·`#{products}`("제품명 x 개수, ..." 목록)** 2개뿐 — 본문/버튼(KLOW)/고객센터 문구는 템플릿 고정 텍스트. 알림톡 설정(`SOLAPI_KAKAO_PFID`/`SOLAPI_KAKAO_TEMPLATE_ORDER_PAID`)이 없으면 `[DEV kakao]` 콘솔 로그로 폴백.

현장(`channel='onsite'`) 주문은 배송이 없어 4·5를 건너뛰고, `paid` 전이와 동시에 `status='completed'` 로 확정된다.

## 환경변수

- `EXIMBAY_API_BASE` / `EXIMBAY_API_KEY` / `EXIMBAY_MID` (해외·USD MID)
- `EXIMBAY_DOMESTIC_API_KEY` / `EXIMBAY_DOMESTIC_MID` (국내·KRW 전용 MID — 해외 MID 는 한국카드 차단이라 `issuer_country=KR` 만으로는 PC04)
- `EXIMBAY_SDK_URL` (클라 SDK 스크립트) / `EXIMBAY_RETURN_BASE_SERVER` (`status_url` base)
- `EXIMBAY_WEBHOOK_IPS` (CSV — 비면 dev 로 간주해 검사 생략)
- `FRONTEND_URL` (klow_web origin — `return_url` = `{FRONTEND_URL}/api/eximbay/return`)
- `SOLAPI_KAKAO_PFID` / `SOLAPI_KAKAO_TEMPLATE_ORDER_PAID` (카카오 알림톡; 미설정 시 dev 콘솔 로그. 선행조건: 채널 심사 통과 + 발신프로필 + 템플릿 승인)

## PG 심사 안전망

- 약관 동의 `Zod.literal(true)`(일반 주문 3종 / 현장 주문 2종) + `prepare()` 단 재가드 — 세 동의 시각
  (`termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`) 중 하나라도 비면 결제창이 열리지 않는다.
- 동의 시각·IP·fxRate 모두 `Order` 에 저장.
- 이중언어 약관 페이지 `/legal/[slug]?lang=ko`.
