# Payment Integration — Eximbay (Sandbox)

본 문서는 KLOW 워크스페이스의 **고객 체크아웃 결제(Eximbay)** 통합을 설명한다. 현재 상태는 **Eximbay 테스트 머천트**로 cart → checkout → 주문 생성 → prepare → SDK → return_url → verify → success 까지 회원·비회원(게스트) 모두 통과하고, 결제 실패 보고·webhook 안전망·어드민/사용자 환불까지 구현되어 있다. 운영 배포 단계에서 추가해야 할 항목은 [TODO](#todo-운영-배포-단계) 섹션에 정리한다.

- 가격 계산(원가+마진+국가별 물류비) 상세는 [`./pricing-model.md`](./pricing-model.md).
- 고객측 금액이 KRW 원장에서 **USD 정본**으로 넘어온 전환 이력은 [`./archive/pricing-usd-migration.md`](./archive/pricing-usd-migration.md).
- 엔드포인트 레퍼런스(요청/응답 스키마)는 [`./server/modules/payment.md`](./server/modules/payment.md).

---

## Stack 요약

| 항목 | 값 |
|------|------|
| PG | **Eximbay** (해외 테스트 머천트 `1849705C64`) |
| API base | `https://api-test.eximbay.com` (운영: `https://api.eximbay.com`) |
| SDK | `https://api-test.eximbay.com/v2/javascriptSDK.js` (`EXIMBAY.request_pay`) |
| 인증 | `Authorization: Basic base64(api_key:)` (콜론 포함, password 빈 문자열) — **scope(글로벌/국내)별로 다른 API 키** |
| 결제 모드 | **통합 결제창** (`transaction_type=PAYMENT` — 인증·승인·매입 자동) |
| 노출 방식 | **`settings.display_type='R'`** — 팝업 대신 같은 탭에서 Eximbay 결제 화면으로 이동 |
| 통화 (2-track) | **USD**(해외 MID, `amount="26.30"`) 기본 / **KRW**(국내 전용 MID, `settings.issuer_country='KR'`, `amount` 정수) — 체크아웃의 `paymentScope` 토글로 선택 |
| 금액 정본 | **`Order.totalUsd`(USD 센트 정수)** 가 단일 정본. USD 는 `totalUsd/100`, KRW 는 `round(totalUsd/100 × fxRateSnapshot)` 로 파생 (round-trip 없음) |
| 검증 경로 | **return_url + `POST /v1/payment/verify`** 메인, `POST /webhooks/eximbay`(status_url) 보조(외부 IP 화이트리스트) |
| return_url 라우팅 | Eximbay 가 form POST 로 도착 → `klow_web/src/app/api/eximbay/return/route.ts` 가 querystring 으로 정규화 → `/checkout/redirect` 로 303 redirect |
| 실패 처리 | rescode≠0000 → `POST /v1/payment/report-failure` (pending→failed 멱등) → `/checkout/failed` |
| DB 매핑 | `Order.pgProvider='eximbay'` · `pgTid=transaction_id`(@unique) · `pgCurrency`('USD'/'KRW') · `paymentMethod=Eximbay 코드` |

테스트 머천트와 API key 는 Eximbay 개발자센터(<https://developer.eximbay.com>) 가 공개로 제공하는 sandbox 자격증명이다. sandbox 에는 국내 전용 MID 가 없어 `EXIMBAY_DOMESTIC_*` 를 비워두면 국내(KRW) 결제는 비활성 상태로 남는다. 운영 전환 시 [환경변수](#환경변수) 표의 키를 라이브 값으로 교체한다.

---

## 결제 시퀀스

```
사용자             klow_web                     klow_server                  Eximbay
  │                  │                             │                            │
  │ /cart → /checkout│                             │                            │
  │                  │ ─POST /v1/orders/quote────► │ (배송지 기준 라인/배송비/합계, cent-exact)
  │                  │ ◄──{lines, totalUsd, ...}── │                            │
  │ ─Place order───► │                             │                            │
  │                  │ ─POST /v1/orders───────────►│ 동의3종(literal true)+IP+fxRate snapshot
  │                  │ ◄────{id} 201───────────────│ (게스트면 klow_order 쿠키 발급)
  │                  │ ─POST /v1/payment/                                       │
  │                  │      prepare {orderId, issuerCountry?}─►│                 │
  │                  │                             │ 소유권·동의·pending 재검증  │
  │                  │                             │ pgCurrency 저장(USD/KRW)    │
  │                  │                             │ ─POST /v1/payments/ready──►│
  │                  │                             │ ◄────{fgkey} 0000──────────│
  │                  │ ◄──{fgkey, sdkUrl, payment, merchant, buyer, url, settings}
  │ same-tab 이동    │ ─SDK request_pay(echo payload, display_type:'R')────────►│
  │ ◄──────────────  Eximbay 결제 화면 (같은 탭) ──────────────────────────────│
  │ 결제 완료        │                             │                            │
  │ ◄──────  Eximbay form POST → /api/eximbay/return ◄─────────────────────────│
  │                  │ /api/eximbay/return (route handler) → 303 → /checkout/redirect?<qs>
  │                  │  ├ rescode=0000 → optimistic /checkout/success           │
  │                  │  │   + (background) ─POST /v1/payment/verify {qs}────────►│
  │                  │  │                        │ ─POST /v1/payments/verify───►│
  │                  │  │                        │ ◄──{rescode:0000}────────────│
  │                  │  │                        │ 금액 재검증 → markPaid 멱등  │
  │                  │  │                        │ (paid + 카트정리·메일·시딩·송장)
  │                  │  └ rescode≠0000 → ─POST /v1/payment/report-failure──────►│
  │                  │                        │ pending→failed → /checkout/failed
  │                  │                             │ ◄── POST /webhooks/eximbay ─│ (보조 — 외부 IP 화이트리스트)
```

**낙관적 success + 백그라운드 verify** — `/checkout/redirect` 는 rescode=0000 이면 verify 응답을 기다리지 않고 즉시 `/checkout/success` 로 이동한다(성공 화면은 query 의 `id`/`email` 만으로 렌더). paymentStatus 의 권위는 서버 verify + webhook 이 가지므로, 클라이언트 verify 가 실패해도 결제 확정에는 영향이 없다.

---

## 엔드포인트

### `POST /v1/orders/quote` (guard 없음, read-only)

배송지(목적국) 기준 라인 단가/배송비/합계를 **주문 생성과 1센트도 안 어긋나게** 미리 계산해 돌려준다. 체크아웃이 표시가로 쓰고, 그대로 결제된다(`priceLine()` 단일 출처 — 표시가 == 청구가).

요청: `{ countryCode, city?, postalCode?, items:[{productId, quantity}] }`. 응답:
```json
{ "shippable": true, "carrier": "EFS", "fxRate": 1380,
  "lines": [{ "productId": "...", "quantity": 1, "unitPriceUsd": 2630 }],
  "itemsTotalUsd": 2630, "shippingFeeUsd": 500, "totalUsd": 3130 }
```
배송 불가(미설정국·EFS 제외구역)면 `shippable:false` + 빈 lines/0 합계를 **throw 없이** 반환한다. 금액은 모두 USD 센트(정수).

### `POST /v1/orders` (OptionalUserGuard — 회원/게스트 공용)

체크아웃 폼 전체 + 결제 직전 동의를 받아 `pending` 주문을 만든다.

서버 동작:
1. **동의 3종 강제** — Zod 가 `agreedToTerms`/`agreedToRefund`/`agreedToPgDataSharing` 를 `literal(true)` 로 요구(false 면 400). 세 값을 같은 `agreedAt` 시각으로 `termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt` 에 박고, 클라이언트 IP 를 `agreementIp` 에 저장(분쟁 트레이서빌리티). (체크아웃 UI 는 "주문 내용 확인"까지 4개 체크박스지만, 서버로 넘어와 시각으로 남는 건 이 3종.)
2. **fxRate 스냅샷** — 주문 시점 `ShopSettings.usdKrwRate` 를 `fxRateSnapshot` 에 저장. 이후 prepare/verify/refund 가 이 값을 재사용해 admin 의 환율 변경으로부터 금액을 보호한다.
3. 한 트랜잭션 안에서 배송사·요율 결정(`resolveFixedRate`), 제품 구매가능 검증(`isPurchasable` — 검수중/미승인/구독 미납 차단), 브랜드당 최대 5개 제한, `priceLine()` 로 라인 단가 산출.
4. USD 센트 정본 산출: `totalUsd = Σ(unitPriceUsd × qty) + shippingFeeUsd`. `OrderItem.unitPriceUsd`(고객 단가) + `settlementPriceKrw`(브랜드 정산 단가) 를 함께 스냅샷.
5. 게스트(userId=null)면 그 주문 id 에 바인딩된 HMAC 토큰을 `klow_order` httpOnly 쿠키로 내려준다(prepare/report-failure/tracking 이 검증).

응답: `{ id }`.

### `POST /v1/payment/prepare` (OptionalUserGuard)

요청: `{ orderId, issuerCountry?: 'KR' }`. 응답:
```json
{
  "fgkey": "0E9B...",
  "sdkUrl": "https://api-test.eximbay.com/v2/javascriptSDK.js",
  "payment": { "transaction_type":"PAYMENT","order_id":"...","currency":"USD","amount":"26.30","lang":"EN" },
  "merchant": { "mid": "1849705C64" },
  "buyer": { "name": "...", "email": "..." },
  "url": { "return_url": ".../api/eximbay/return", "status_url": ".../webhooks/eximbay" },
  "settings": { "display_type": "R" }
}
```

서버 동작:
1. **소유권** — 회원은 `order.userId === user.id`, 게스트는 `userId === null` + `klow_order` 쿠키 HMAC 이 이 orderId 에 유효할 때만. 실패는 404(존재 oracle 회피).
2. `paymentStatus === 'pending'` 아니면 400 `'order is not payable'`.
3. **동의 재검증** — `termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt` 중 하나라도 null 이면 400. legacy/API 직접호출 우회로도 동의 없이는 결제창이 안 뜬다.
4. **통화/MID 선택** — `issuerCountry==='KR'` → 국내 전용 MID + `currency:'KRW'`(정수 amount) + `settings.issuer_country:'KR'`, 그 외 → 해외 MID + `currency:'USD'`(`"26.30"`). 금액은 `totalUsd` 정본에서 파생(USD 는 `/100`, KRW 는 `× fxRateSnapshot` 반올림).
5. Eximbay `/v1/payments/ready`(선택된 scope 의 API 키) 호출 → fgkey 수령.
6. **`Order.pgCurrency` 저장**('USD'/'KRW') — verify/webhook/refund 가 이 값으로 MID·통화·금액을 복원한다. 재-prepare(통화 변경) 시 덮어쓰기 = 마지막 prepare 가 실제 결제창.
7. **요청 본문과 fgkey 를 함께 echo**.

**fgkey echo 정책** — SDK `request_pay()` 인자(payment·merchant·buyer·url·settings)가 prepare 시점 본문과 정확히 같아야 fgkey 검증이 통과한다. 클라이언트는 응답 payload 를 그대로 인자로 넘긴다. amount 등을 임의 조작하면 SDK 가 거부 → 위변조 자동 방지.

### `POST /v1/payment/verify` (guard 없음 — Eximbay 재조회로 보호, rate-limit 5/분)

요청: `{ querystring }` (return_url 의 raw querystring 그대로).

서버 동작(`parseAndMarkPaid`):
1. `order_id`·`transaction_id` 파싱(없으면 400). `order_id` 로 주문의 `totalUsd`/`fxRateSnapshot`/`pgCurrency` 1회 read → **scope 복원**.
2. Eximbay `/v1/payments/verify` 에 `{data: querystring}` POST(복원한 scope 의 키) → rescode≠0000 이면 502.
3. **금액 재검증** — prepare 와 동일 공식으로 `expected` 산출(KRW=정수 ±1, USD=$0.01 tolerance). 초과하면 400 `'amount mismatch'`.
4. **멱등 전이(markPaid)** — `updateMany({ where:{id, paymentStatus:'pending'}, data:{ paymentStatus:'paid', paidAt, pgProvider:'eximbay', pgTid, paymentMethod }})`.
   - `count===1`(진짜 pending→paid) 에서만 부수효과 실행: **주문 카트항목 삭제 → 주문확인 메일 → 유료 시딩링크 claimed 전이 → EFS 송장 자동발급**. 모두 try/catch 로 격리(실패해도 결제 전이는 롤백 안 됨).
   - `count===0` 이면 현재 상태를 다시 읽어 분기: 같은 `pgTid` 로 이미 paid → 멱등 성공(보통 webhook 이 먼저), 그 외(다른 tid/ failed/cancelled/refunded) → 400 충돌.

응답: `{ orderId }`. 성공 시 컨트롤러가 게스트 `klow_order` 쿠키를 정리한다. 클라이언트(`/checkout/redirect`)는 이 호출을 백그라운드로 던지고 결과를 기다리지 않는다.

### `POST /v1/payment/report-failure` (OptionalUserGuard)

요청: `{ orderId, reason? }`. `/checkout/redirect` 가 rescode≠0000(사용자 취소·승인 거절 등)을 감지하면 호출. 소유권 검증 후 `pending → failed` 를 단일 `updateMany` 로 멱등 전이하고, `reason`(≤500자, `[payment-failed @ ISO]` 접두)을 `Order.paymentFailureReason` 에 저장한다. 이미 paid/refunded/cancelled 면 현재 상태를 그대로 회신(무변경). 이후 `/checkout/failed` 페이지로 이동.

### `POST /webhooks/eximbay` (no auth guard, **IP 화이트리스트 적용**)

Eximbay 가 status_url 로 같은 결과를 form-urlencoded POST 하는 server-side 안전망. `verify` 와 동일한 `parseAndMarkPaid` 를 호출한다(멱등).
- **IP 화이트리스트** — `EXIMBAY_WEBHOOK_IPS`(comma 구분)가 채워져 있으면 `req.ip` 가 목록에 없을 때 403. 비어 있으면 dev 편의로 미적용. `req.ip` 는 `main.ts` 의 trust proxy(신뢰 홉 수) 기준으로 XFF 를 해석하므로 헤더 스푸핑으로 우회 불가.
- 응답 본문에 `rescode=0000&resmsg=Success` 텍스트(실패 시 `rescode=9999&resmsg=<encoded>`) — 이 형식이 아니면 Eximbay 가 retry. `main.ts` CSRF 가드는 `/webhooks/` prefix 를 통과시킨다.
- 로컬에서는 외부에서 localhost 에 도달하지 못하므로 호출되지 않는다(정상).

### 환불 — `payment.refundOrder` → Eximbay `/v1/payments/{pgTid}/cancel`

DB 전이는 호출자(어드민/사용자/게스트)가 각자 where 절로 수행하고, `PaymentService.refundOrder` 는 **PG 취소만** 책임진다. `Order.pgCurrency` 로 scope 를 복원해 결제한 MID·통화·금액(prepare/markPaid 와 동일 helper)으로 전액 취소(`refund_type:'F'`)한다.

> Eximbay cancel body 는 nested 구조:
> ```json
> { "mid": "...",
>   "refund": { "refund_type": "F", "refund_amount": "26.30", "refund_id": "<order.id>", "reason": "..." },
>   "payment": { "order_id": "...", "currency": "USD", "amount": "26.30", "balance": "26.30", "lang": "EN" } }
> ```

호출 경로:
- `PATCH /admin/orders/:id/refund` (AdminGuard) → `OrdersService.refundByAdmin` — paid 주문은 PG 취소 성공 후 `paymentStatus='refunded'`, `status='cancelled'`. pending 주문은 PG 호출 없이 `cancelled`.
- `PATCH /v1/orders/:id/cancel` (UserGuard) → `cancelByUser` — 동일 패턴(reason `'user requested cancel'`), shipped/completed/cancelled 는 차단.
- `POST /v1/orders/guest-cancel` — 게스트가 주문번호+이메일 OTP 검증 후 `cancelByGuest`(reason `'guest requested cancel'`).

> PG 취소 성공과 DB `updateMany` 사이에 서버 크래시가 나면 PG↔DB 불일치 가능(v1 허용). 운영 단계에서 outbox/idempotency 로 보강 예정 — [TODO](#todo-운영-배포-단계).

### 어드민 주문 목록 — 필터

`GET /admin/orders` 는 `?status=` 와 `?paymentStatus=` 를 동시 지원(둘 다 optional). klow_admin `/orders` 페이지가 두 필터를 별도 ribbon 으로 노출 — 결제 상태별로 환불 대상 주문을 빠르게 찾는다.

---

## DB 컬럼 매핑

고객측 금액은 **USD 정본** — 구 KRW 원장 컬럼(`Order.subtotal`, `OrderItem.unitPrice`, `shippingFeeKrw`)은 드롭됐다(이력: [`./archive/pricing-usd-migration.md`](./archive/pricing-usd-migration.md)).

| 컬럼 | 값 |
|------|------|
| `Order.totalUsd` | **USD 센트(정수) 정본** = Σ(`unitPriceUsd`×qty) + `shippingFeeUsd`. PG 청구액과 1:1 (2630 = $26.30) |
| `Order.shippingFeeUsd` | USD 센트 — 배송비(= Σ_브랜드 요율/2). `totalUsd` 에 포함 |
| `Order.fxRateSnapshot` | 주문 시점 USD-KRW 환율. prepare/verify/refund 가 KRW 파생·환산에 재사용 |
| `Order.pgCurrency` | prepare 가 기록 — `'USD'`(해외 MID) / `'KRW'`(국내 전용 MID). null = 아직 prepare 안 됨(USD 로 간주) |
| `Order.paymentStatus` | `'pending'` → `'paid'`(verify/webhook) / `'failed'`(report-failure) → `'refunded'`/`'cancelled'`(환불) |
| `Order.pgProvider` | `'eximbay'` |
| `Order.pgTid` | Eximbay `transaction_id` (@unique) |
| `Order.paymentMethod` | Eximbay payment_method 코드 (예: 카드) |
| `Order.paidAt` / `cancelledAt` | verify 성공 / refund·cancel 시점 |
| `Order.termsAgreedAt` · `refundAgreedAt` · `pgDataSharingAgreedAt` | 결제 직전 동의 3종 시각(주문 생성 시 동일 시점). prepare 가 non-null 재검증 |
| `Order.agreementIp` | 동의를 누른 클라이언트 IP (분쟁 트레이서빌리티) |
| `Order.paymentFailureReason` | report-failure 가 저장하는 운영 디버깅용 사유(≤500자) |
| `OrderItem.unitPriceUsd` | USD 센트 — 주문 시점 고객 결제 단가 스냅샷(마크업+수수료 포함) |
| `OrderItem.settlementPriceKrw` | KRW — 주문 시점 브랜드 정산 단가. 청구 USD 에서 주문 시점 환율로 역산(`= 청구USD × fx × 0.95 − 물류비/2`, `settlementKrwFromCustomerUsd`) — `Product.salePrice`(정산가)와 별개 스냅샷 |

스키마는 USD 전환 마이그레이션 이후 안정 — 이 통합 자체가 추가한 신규 마이그레이션은 없다.

---

## 환경변수

`klow_server/.env`(gitignored) 와 `.env.example` 양쪽에 동기(server config.get 이 읽는 키):

```
# 해외(USD) MID — 기본 결제창
EXIMBAY_API_BASE=https://api-test.eximbay.com
EXIMBAY_SDK_URL=https://api-test.eximbay.com/v2/javascriptSDK.js
EXIMBAY_MID=1849705C64
EXIMBAY_API_KEY=test_1849705C642C217E0B2D

# 국내(KRW) 전용 MID — 국내카드(issuer_country=KR) 결제창. sandbox 엔 없어 비우면 국내결제 비활성.
EXIMBAY_DOMESTIC_MID=
EXIMBAY_DOMESTIC_API_KEY=

# status_url host (klow_server origin) — webhook 에 박힌다.
EXIMBAY_RETURN_BASE_SERVER=http://localhost:4000

# webhook 허용 IP (comma 구분). 비우면 dev 편의로 미적용. 운영 필수.
# 운영: 15.165.144.33 / sandbox: 43.203.92.211,3.34.20.184,3.37.76.229,52.79.143.149
EXIMBAY_WEBHOOK_IPS=43.203.92.211,3.34.20.184,3.37.76.229,52.79.143.149
```

- `return_url` 의 host(klow_web)는 별도 키 없이 기존 **`FRONTEND_URL`** 을 재사용한다.
- `klow_web` 은 결제 관련 env 추가 없음 — SDK URL·payload 를 백엔드 prepare echo 로 받는다.

---

## 로컬 테스트 절차

### 사전 준비

- Neon dev DB 에 **배송지원 국가 1개**(`ShippingCountry.enabled=true` + `productLogisticsCostKrw` + `productCarrier` 세팅 — 어드민 물류비용/국가 설정 탭 또는 `seed:product-logistics-cost`)와 **승인된 제품(브랜드) 1개**. 어드민 물류비용/국가 미설정 국가는 `quote` 가 `shippable:false` 를 돌려주고 주문이 차단된다.
- 금액은 `totalUsd`(센트) 정본으로 계산되며, 어떤 값이든 흐름 검증엔 무방하다(정확히 $1 을 맞출 필요 없음).
- 3 터미널: `klow_server`(4000), `klow_admin`(3000), `klow_web`(3001).
- `.env` 에 EXIMBAY_* 키(해외 MID 는 sandbox 기본값)를 채우고 `npm run start:dev` 재시작. 국내(KRW) 결제까지 보려면 `EXIMBAY_DOMESTIC_*` 도 채운다(sandbox 엔 없으므로 보통 USD 만 검증).

### Step-by-step

1. **Cart**: klow_web 로그인(또는 게스트) → 상품 → Add to cart → `/cart` 라인 표시.
2. **Checkout 진입**: `/checkout`. 배송지 입력 시 `POST /v1/orders/quote` 가 라인 단가/배송비/`totalUsd` 를 채우는지 Network 확인(표시가 == 이후 청구가).
3. **Place order** — 동의 체크박스(주문확인/약관/환불/개인정보 공유) 모두 체크해야 활성화:
   - `POST /v1/orders` → 201 `{id}`. Prisma Studio 에서 그 row `paymentStatus='pending'`, `totalUsd`, `fxRateSnapshot`, `termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`, `agreementIp` 확인. 게스트면 `klow_order` 쿠키 세팅.
   - `POST /v1/payment/prepare` → 200 (`fgkey`, `sdkUrl`, `payment.amount`, `payment.currency`). 그 order 의 `pgCurrency` 가 'USD'(또는 국내카드면 'KRW') 로 저장됐는지 확인.
   - `javascriptSDK.js` 200 → Eximbay 결제 화면(같은 탭).
4. **결제 진행**: Eximbay 테스트 카드 입력 → 결제 성공.
5. **Return**: Eximbay form POST → `/api/eximbay/return` → 303 → `/checkout/redirect?rescode=0000&order_id=...&transaction_id=...`. rescode=0000 이면 즉시 `/checkout/success` 로 이동.
6. **Verify(백그라운드)**:
   - `POST /v1/payment/verify` → 200 `{orderId}`. 서버 콘솔에 Eximbay `/v1/payments/verify` rescode=0000.
   - Prisma Studio: 그 order `paymentStatus='paid'`, `paidAt`, `pgProvider='eximbay'`, `pgTid`, `paymentMethod`. 카트 항목 삭제 + (송화인 세팅 시) `Shipment` 자동 발급 확인.
7. **Success page**: `/checkout/success?id=...&email=...` 도달.
8. **/orders 확인**: 회원은 klow_web `/orders`, 게스트는 `/orders/lookup`(주문번호+이메일)에서 paid 로 표시.
9. **실패 경로**: 결제창에서 취소 → `/checkout/redirect?rescode=<非0000>` → `POST /v1/payment/report-failure` → order `paymentStatus='failed'` + `paymentFailureReason` → `/checkout/failed` 도달.
10. **status_url 비도달 OK**: 로컬은 외부에서 localhost 도달 불가 → `/webhooks/eximbay` 호출 0회(정상). 운영에선 `EXIMBAY_WEBHOOK_IPS` 로 화이트리스트.
11. **환불**: klow_admin `/orders/<id>` → 환불(사유 입력) → `PATCH /admin/orders/:id/refund` 200. 콘솔에 Eximbay `/v1/payments/<tid>/cancel` rescode=0000. Prisma Studio: `paymentStatus='refunded'`, `status='cancelled'`, `cancelledAt`.
12. **재시도 차단**: 같은 orderId 로 prepare 재호출 → 400 `'order is not payable'`.

---

## TODO (운영 배포 단계)

- **Outbox / idempotency_key** — 환불(`refundOrder`)의 PG cancel 성공 후 DB `updateMany` 사이 서버 크래시로 인한 불일치(PG 환불됐지만 DB 는 paid) 차단. markPaid 부수효과(메일/송장)도 outbox 로 재시도 보장하면 더 견고.
- **라이브 키 + 운영 도메인** — `EXIMBAY_API_BASE`/`EXIMBAY_SDK_URL`/`EXIMBAY_MID`/`EXIMBAY_API_KEY` 를 라이브 값으로, `FRONTEND_URL`(return_url host)·`EXIMBAY_RETURN_BASE_SERVER`(status_url host)를 운영 https 도메인으로 교체. `EXIMBAY_WEBHOOK_IPS` 를 운영 IP(`15.165.144.33`)로 좁힌다.
- **국내(KRW) MID 라이브 값** — sandbox 엔 국내 전용 MID 가 없다. `EXIMBAY_DOMESTIC_MID`/`EXIMBAY_DOMESTIC_API_KEY` 에 실 국내 MID 를 세팅해야 국내카드(issuer_country=KR) 결제가 열린다.
- **결제수단별 UI 분기 확장** — 현재는 통합 결제창 + global/kr 2-track 토글. 카드/PayPal/Alipay 라디오까지 노출하려면 `payment_method` 코드를 prepare payload 에 채운다.
- **product[]/ship_to/bill_to** — PayPal·Klarna 결제 시 필수 필드. `Order` 의 배송지/아이템에서 채울 수 있음(현재 미전송).
```
