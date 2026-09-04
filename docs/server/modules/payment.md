# payment — Eximbay 결제

- **모듈 경로**: `src/modules/payment/`
- **PG**: Eximbay (USD 결제)
- **흐름 요약**: `POST /v1/orders` (동의 + IP + fxRate snapshot) → `POST /v1/payment/prepare` → 클라 Eximbay JS SDK → **`return_url` = 서버 `POST /payment/return` (여기서 확정)** → klow_web `/checkout/redirect?…&klow_verified=1` 로 303 (화면 라우팅·카트 정리만)
- **보강 경로**: `POST /webhooks/eximbay` (외부 IP 화이트리스트), **`payment-reconcile` 크론 15분 주기**, `PATCH /admin/orders/:id/reconcile-payment` (수동), `POST /v1/payment/report-failure` (pending→failed 멱등)

## 결제 확정의 3중 방어선 (2026-08-17)

`pending → paid` 전이는 `markPaid()` 한 곳에서만 일어난다. 예전엔 거기 도달하는 경로가 둘뿐이었고
**둘 다 실패했을 때 복구하는 장치가 없어서**, 카드는 승인됐는데 주문이 영원히 `pending` 으로 남는
사고가 실제로 발생했다. 특히 **현장(`channel='onsite'`) QR 결제**가 취약했다.

⚠️ 예전 구조의 핵심 결함: `return_url` 이 klow_web 을 가리켰고, 거기서 303 으로 넘어간
`/checkout/redirect` **클라이언트 페이지의 JS** 가 `POST /v1/payment/verify` 를 **한 번 더** 호출해야만
결제가 확정됐다. 게다가 그 호출은 `api.payment.verify(qs).catch(() => {})` — **fire-and-forget 이고
에러를 통째로 삼켰다.** 그래서 확정 실패가 아무 흔적 없이 사라졌고 손님은 언제나 성공 화면을 봤다.

현장결제가 유독 취약했던 이유:
1. QR → 인앱 브라우저(카메라앱·카카오·인스타). 카드앱(3-DS)에서 돌아올 때 컨텍스트가 바뀌면 그 페이지가 아예 안 뜬다.
2. 부스에서 거래가 사회적으로 끝난다 — 카드앱이 "승인" 뜨면 손님은 폰을 집어넣는다.
3. `verify` 가 **IP 기준 5회/분** 스로틀이었다. 부스는 전원이 같은 행사장 Wi-Fi/캐리어 NAT 뒤라 egress IP 가 하나 → 1분에 6번째 결제부터 429.
4. 하류에서 아무도 눈치 못 챈다 — 송장·알림톡 스킵 채널이고, 어드민 목록은 미결제를 기본 숨김하며, 정산(`paymentStatus:'paid'`)에서도 빠져 **브랜드 매출이 통째로 누락**된다.

| # | 방어선 | 언제 동작 |
|---|--------|-----------|
| 1 | **`POST /payment/return`** (서버) | 손님 브라우저가 결제창에서 돌아오는 leg. 그 요청 처리 중에 확정까지 끝낸다 — 브라우저 JS 실행도, 두 번째 fetch 도 필요 없다. 손님이 곧바로 탭을 닫아도 안전. |
| 2 | **`POST /webhooks/eximbay`** (status_url) | Eximbay 서버가 직접 POST. 손님이 브라우저로 아예 안 돌아온 경우를 받는다. |
| 3 | **`payment-reconcile` 크론** (15분) | 1·2 가 모두 실패한 건을 Eximbay 에 직접 재조회해 자동 복구. |

3번은 `POST /v1/payments/retrieve` + `key_field='order_id'` 를 쓴다 — **우리 주문번호만으로 조회**되므로
`pgTid` 를 모르는(= markPaid 가 한 번도 안 돈) 주문에도 쓸 수 있다. `verify` 는 PG 가 돌려준 querystring 을
되돌려주는 방식이라 이 상황엔 못 쓴다. 응답 `payment.status` 가 `SALE`(매출확정) 또는 `AUTH`(승인·매입전)
이면 결제로 보고 **기존 `markPaid` 를 그대로 태운다**(금액 재검증·멱등 전이·onsite completed 전이·카트
정리·주문확인 메일·시딩 확정·송장 발급이 전부 재사용된다 — 경로가 갈리면 곧 어긋난다).
`REGISTERED`(입금대기)·`NONE`(거래없음)은 건드리지 않는다.

⚠️ **금액이 어긋나면 자동 확정하지 않는다** (`mismatch`). 통화 데싱크 등 사람이 판단할 문제라
자동으로 밀어붙이면 잘못된 금액으로 정산된다. Sentry 로 올라가고 어드민이 직접 확인한다.

세 진입점(크론·백필·어드민)은 **판정 함수 하나**(`reconcileOrder`)와 **대상 술어 하나**
(`findReconcilableOrderIds`)를 공유한다. 백필의 dry-run 도 `reconcileOrder(id, { dryRun: true })`
로 **같은 판정**을 거치고 쓰기만 건너뛴다 — 따로 분류하면 dry-run 집계와 `--apply` 결과가 갈린다.
배치 루프는 `reconcilePendingOrders()` 가 갖고(기존 cron 관례대로 `*.cron.ts` 는 얇은 래퍼),
외부 PG 호출은 5-wide 로 끊으며(`RECONCILE_CONCURRENCY`, shipments 의 EFS 일괄 갱신과 같은 값),
크론에는 재진입 가드가 있다 — `@nestjs/schedule` 은 겹침을 막아주지 않아 한 실행이 주기를 넘기면
다음 실행이 같은 주문을 중복 조회한다.

과거에 이미 굳은 주문은 `npm run backfill:reconcile-payments`(기본 dry-run, `-- --apply`, 멱등,
`--onsite`/`--days N`/`--order <id>`)로 일괄 복구한다.

⚠️ **`/payment/return` 은 `main.ts` 의 Origin CSRF 가드 예외 목록에 반드시 있어야 한다.** Eximbay 의
form POST 에는 브라우저 Origin 이 없어서 예외가 빠지면 **모든 결제가 403** 이 된다.
같은 이유로 `/payment/return` 과 `/webhooks/eximbay` 는 `@SkipThrottle()` 이다 — 결제 확정 경로가
자기 rate limit 에 걸리면 되살린 버그가 그대로 재발한다.
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
| POST   | `/v1/payment/verify`              | public (60/분)                 | 결제 결과 검증 — 바디 `{ querystring }`. Eximbay 재조회 + `pgCurrency` 기준 금액 검증(KRW ±1 / USD ±0.01) + `paymentStatus` 멱등 전이. 성공 시 게스트 주문 쿠키 정리, 응답 `{ orderId }`. **이제는 구 결제창 호환용 폴백** — 주 경로는 `/payment/return` 이다. ⚠️ 예전 5회/분은 **IP 기준**이라 부스(공용 NAT) 결제를 429 로 죽였다 |
| POST   | `/v1/payment/report-failure`      | OptionalUser + 게스트 쿠키     | 결제 실패 보고 — 바디 `{ orderId, reason? ≤500자 }`. `pending → failed` 멱등 전이(다른 상태면 현재 상태 그대로 반환), 사유는 타임스탬프와 함께 `paymentFailureReason` 에 저장. 응답 `{ status }` |

### 국내(KR) 카드 결제 분기

`prepare` 에 `issuerCountry: 'KR'` 을 주면 **국내 전용 MID + KRW 정수 금액**(`totalUsd/100 × fxRateSnapshot` 반올림,
`settings.issuer_country='KR'`, `tax` 동봉)으로, 생략하면 **해외 MID + USD**(`totalUsd/100` 을 `"26.30"` 형태로)로
결제창을 연다. 어느 쪽으로 열렸는지는 `Order.pgCurrency` 에 영속화되고 `verify`/webhook/환불이 그 값으로 MID·통화·
금액을 복원한다(재-prepare 시 덮어써 "마지막 prepare == 실제 결제창"). `totalUsd` 가 없는 legacy 주문은 400.

## public-payment-return.controller.ts (`@Controller('payment')`)

| Method     | Path              | Guard                          | 기능                                                                 |
|------------|-------------------|--------------------------------|----------------------------------------------------------------------|
| GET / POST | `/payment/return` | 없음 (`@SkipThrottle`, Origin 가드 예외) | Eximbay `return_url`. 결과를 querystring 으로 정규화 → `handleReturn` 으로 확정(`rescode=0000` 이면 `parseAndMarkPaid`, 아니면 소유권 검증 없이 pending→failed) → klow_web `/checkout/redirect?<원본qs>&klow_verified=1` 로 **303** |

- **절대 throw 하지 않는다.** 여기서 던지면 결제를 마친 손님이 에러 화면을 보는데 승인이 취소되지도 않는다. 확정 실패는 Sentry 로 올리고 웹훅·크론이 주워 담는다.
- **원본 querystring 을 그대로 넘겨 303** 한다 — klow_web 의 기존 분기(시딩 링크 복귀·현장 부스 성공화면·결제한 상품만 카트에서 제거)가 브라우저 `sessionStorage` 에만 있는 정보를 쓰기 때문에 서버가 대신 판단할 수 없다. `klow_verified=1` 은 "서버가 이미 확정했으니 다시 verify 하지 말라"는 신호.
- 실패 전이에 게스트 쿠키를 요구하지 않는 이유: `klow_order` 쿠키는 크로스사이트 `SameSite=None` 이라 Safari ITP 등에서 자주 사라져 `report-failure` 가 404 로 죽었다. Eximbay 가 우리 서버에 직접 준 결과에는 쿠키가 필요 없다.

## webhook-payment.controller.ts (`@Controller('webhooks')`)

| Method | Path                              | Guard                                       | 기능                                                  |
|--------|-----------------------------------|---------------------------------------------|-------------------------------------------------------|
| POST   | `/webhooks/eximbay`               | IP 화이트리스트 (`EXIMBAY_WEBHOOK_IPS`)     | Eximbay 비동기 알림(status_url). verify 누락 케이스 보강 처리 |

- `@HttpCode(200)` + 본문 `rescode=0000&resmsg=Success` 를 text/plain 으로 회신해야 Eximbay 가 retry 를 멈춘다.
  처리 중 예외가 나면 `rescode=9999&resmsg=<urlencoded>` 로 회신(= retry 유도).
- 소스 IP 는 `req.ip`(main.ts 의 trust proxy 기준 해석)로 판정 — XFF 스푸핑으로 화이트리스트를 우회할 수 없다.
  화이트리스트가 비어 있으면(dev) 검사를 건너뛰고, 미허용 IP 는 **403**(+ Sentry).
  ⚠️ 양쪽 다 `::ffff:` 접두(IPv4-mapped IPv6)를 벗겨 비교한다 — 문자열 정확 일치라 정규화 없이는 정상 콜백이 403 난다.
- ⚠️ **화이트리스트 오설정은 안전망을 통째로 없앤다.** `.env.example` 에 커밋된 기본값은 **샌드박스 IP 4개**이고
  운영은 `15.165.144.33` 하나다. 예전 부팅 가드는 "비어있지 않은가"만 봐서 샌드박스 값이 그대로 통과했다 —
  그러면 진짜 콜백이 전부 403 인데 로그는 warn 한 줄뿐이다. 이제 **운영에서 샌드박스 IP 가 있으면 부팅을 거부**한다.
  같은 이유로 `EXIMBAY_RETURN_BASE_SERVER`/`FRONTEND_URL` 도 운영에서 절대 https URL 이 아니면 부팅을 거부한다
  (미설정이면 `status_url`/`return_url` 이 상대경로가 되어 콜백이 아무 데도 도달하지 않는다).
- `verify` 와 동일한 `parseAndMarkPaid` 를 타되 `order_id`/`transaction_id` 가 없으면 조용히 무시한다.

## 결제 완료(pending→paid) 부수효과

`markPaid()` 의 진짜 전이(`count === 1`) 분기에서만, 멱등하게 순차 실행 — 모두 실패 격리(에러가 결제 전이를 롤백하지 않음):

0. `storefrontStats.recordPurchase` — 브랜드관 방문 퍼널의 **'결제' 단계** 기록([storefront-stats](./storefront-stats.md)). ⚠️ **일부러 이 목록의 맨 앞**이다 — 뒤(EFS 송장 왕복·알림톡)에 두면 그쪽이 느려지거나 프로세스가 죽었을 때 결제 집계만 조용히 사라진다. 현장·시딩·`visitorId` 없음 제외와 예외 흡수는 전부 그쪽이 소유한다(절대 throw 하지 않음).
1. `clearCartItemsForOrder` — 주문에 포함된 카트 항목 서버측 삭제.
2. `sendOrderConfirmationSafe` — 구매자에게 주문 확인 이메일(Resend).
3. `claimSeedingLinkSafe` — 유료 시딩 링크 pending→claimed.
4. `createShipmentsForOrderSafe` — EFS 송장 자동 발급(onsite 제외).
5. `notifyBrandsOfPaidOrderSafe` — **주문에 담긴 제품의 브랜드(들)에게 "새 주문 접수" 카카오 알림톡**(onsite 제외). 브랜드가 스튜디오 주문현황 탭에서 발송처리를 놓치지 않도록. 조회·조립·발송의 정본은 **`orders/brand-order-alimtalk.ts` 의 `notifyBrandsOfOrderSafe`** 이고 여기 있는 건 `sendOrderConfirmationSafe` 와 같은 **얇은 래퍼**다 — 무가 시딩 claim·재발송(`seeding.service`)이 같은 함수를 쓰므로 문자 내용이 갈리지 않는다. ⚠️ 이 래퍼의 **이름을 바꾸지 말 것** — `payment-reconcile.spec.ts` 가 인스턴스 프로퍼티로 덮어써 스텁하므로 이름이 바뀌면 스텁이 조용히 안 먹고 결제 스펙이 실제 알림 경로를 탄다. 브랜드 집합은 송장과 동일 규칙(productId→`Product.brandId`, 없으면 `OrderItem.brandId`), 수신번호는 같은 파일의 **`resolveBrandAlertPhone`**(`Brand.senderPhone` 우선·없으면 `BrandUser.phone` 폴백) — ⚠️ 그 함수를 브랜드 알림 토글의 "켤 수 있는가" 검증도 **함께 쓴다**(각자 구현하면 "토글은 켜졌는데 알림은 안 가는" 상태가 생긴다). ⚠️⚠️ **시딩 주문의 제품명은 `OrderItem.productName` 이 아니다** — 그건 EFS 통관 신고용 일반 품명(`Korean Skincare Toner` 류)이라, 고객 대면 경로 4곳이 쓰는 `seedingItemNames()`+`displayLines()` 파생을 여기서도 태운다(2026-09-04. 그전까지 브랜드는 자기가 보내야 할 제품을 알 수 없는 문자를 받았다). 일반 주문은 파생이 `[]` 라 원본 라인 그대로다. ⚠️ **opt-in 축은 인자로 받는다** — `requireSeedingOptIn: false`(여기, 매출 주문이라 항상 발송) vs `true`(무가 시딩·재발송 — `Brand.seedingAlertEnabled` 를 켠 브랜드에게만). **비대칭이 의도다.** 승인 템플릿("브랜드 일반주문 발생") 변수는 **`#{country}`(주문국)·`#{products}`("제품명 x 개수, ..." 목록)** 2개뿐 — 본문/버튼(KLOW)/고객센터 문구는 템플릿 고정 텍스트. ⚠️ `#{products}` 는 `kakao.service.ts` 의 `renderProducts` 가 **8개까지만 싣고 나머지를 `외 N건`** 으로 접는다(브랜드 지정 시딩은 박스당 수량이 1~99라 그만큼 펼쳐지는데, 치환 후 본문이 카카오 상한을 넘으면 발송이 통째로 거절되고 catch 가 삼켜 아무도 모른다 — 접는 건 문자열 길이뿐이고 통 수는 1건당 1통 그대로다). 알림톡 설정(`SOLAPI_KAKAO_PFID`/`SOLAPI_KAKAO_TEMPLATE_ORDER_PAID`)이 없으면 `[DEV kakao]` 콘솔 로그로 폴백.

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
