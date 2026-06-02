# Payment Integration — Eximbay (Sandbox)

본 문서는 KLOW 워크스페이스의 결제 통합을 설명한다. 현재 상태는 **Eximbay 테스트 머천트**로 한 시퀀스의 결제(USD)가 cart → checkout → SDK 팝업 → return_url → verify → success 까지 끝까지 통과하고, 어드민 환불도 한 번 돌아가는 수준이다. 운영 배포 단계에서 추가해야 할 항목은 [TODO](#todo) 섹션에 별도로 정리한다.

---

## Stack 요약

| 항목 | 값 |
|------|------|
| PG | **Eximbay** (테스트 머천트 `1849705C64`) |
| API base | `https://api-test.eximbay.com` (운영: `https://api.eximbay.com`) |
| SDK | `https://api-test.eximbay.com/v2/javascriptSDK.js` (`EXIMBAY.request_pay`) |
| 인증 | `Authorization: Basic base64(api_key:)` (콜론 포함, password 빈 문자열) |
| 결제 모드 | **통합 결제창** (`transaction_type=PAYMENT` — 인증·승인·매입 자동) |
| 노출 방식 | **`display_type='R'`** — 팝업 대신 같은 탭에서 Eximbay 결제 화면으로 이동 |
| 통화 | **USD** (Order.subtotal customer-KRW → `subtotal/usdKrwRate` 소수 2자리) |
| 검증 경로 | **return_url + `/v1/payment/verify`** 메인, `/webhooks/eximbay`(status_url) 보조 |
| return_url 라우팅 | Eximbay 가 form POST 로 도착 → `klow_web/src/app/api/eximbay/return/route.ts` 가 querystring 으로 정규화 → `/checkout/redirect` 로 303 redirect |
| DB 매핑 | `Order.pgProvider='eximbay'` · `pgTid=transaction_id` · `paymentMethod=Eximbay 코드` |

테스트 머천트와 API key 는 Eximbay 개발자센터(<https://developer.eximbay.com>) 에서 공개로 제공하는 sandbox 자격증명. 운영 라이브 키로 전환 시 `klow_server/.env`의 `EXIMBAY_API_BASE`/`EXIMBAY_SDK_URL`/`EXIMBAY_MID`/`EXIMBAY_API_KEY` 4개만 교체하면 된다.

---

## 결제 시퀀스

```
사용자             klow_web                  klow_server                Eximbay
  │                  │                          │                          │
  │ /checkout 진입   │                          │                          │
  │ ─Place order───► │                          │                          │
  │                  │ ─POST /v1/orders───────► │                          │
  │                  │ ◄────{id} 201─────────── │                          │
  │                  │ ─POST /v1/payment/                                   │
  │                  │      prepare {orderId}─► │                          │
  │                  │                          │ ─POST /v1/payments/─────►│
  │                  │                          │      ready (settings:R)  │
  │                  │                          │ ◄────{fgkey} 200─────────│
  │                  │ ◄──{fgkey, sdkUrl, ...}──│                          │
  │ same-tab 이동    │ ─SDK request_pay({display_type:'R'})───────────────►│
  │ ◄──────────────  Eximbay 결제 화면 (같은 탭) ──────────────────────────│
  │ 결제 완료        │                          │                          │
  │ ◄──────  Eximbay form POST → /api/eximbay/return ◄────────────────────│
  │                  │ /api/eximbay/return                                  │
  │                  │   (route handler) → 303 → /checkout/redirect?<qs>    │
  │                  │ ─POST /v1/payment/                                   │
  │                  │      verify {qs}────────►│                          │
  │                  │                          │ ─POST /v1/payments/─────►│
  │                  │                          │      verify              │
  │                  │                          │ ◄────{rescode:0000}──────│
  │                  │                          │ Order.paymentStatus=paid │
  │                  │ ◄────{orderId} 200───────│                          │
  │                  │ clearCart() + → /checkout/success                    │
  │ ◄ /checkout/success                         │                          │
  │                  │                          │ ◄── /webhooks/eximbay ───│ (보조 — 외부 IP)
```

---

## 엔드포인트

### `POST /v1/payment/prepare` (UserGuard)

요청: `{ orderId: string }`. 응답:
```json
{
  "fgkey": "0E9B...",
  "sdkUrl": "https://api-test.eximbay.com/v2/javascriptSDK.js",
  "payment": { "transaction_type":"PAYMENT","order_id":"...","currency":"USD","amount":"1.00","lang":"EN" },
  "merchant": { "mid": "1849705C64" },
  "buyer": { "name": "...", "email": "..." },
  "url": { "return_url": "...", "status_url": "..." }
}
```

서버 동작:
1. `Order.userId` 일치 + `paymentStatus='pending'` 검증.
2. `ShopSettings.usdKrwRate` 로 `amountUsd = (Order.subtotal / fxRate).toFixed(2)`.
3. Eximbay `/v1/payments/ready` 호출 → fgkey 수령.
4. **요청 본문과 fgkey 를 함께 echo**.

**fgkey echo 정책** — SDK 호출 시 `request_pay()` 의 인자(payment·merchant·buyer·url)가 prepare 시점의 본문과 정확히 같아야 fgkey 검증이 통과한다. 클라이언트는 `EximbayPreparePayload` 를 그대로 인자로 넘긴다. amount 등을 클라이언트가 임의 조작하면 SDK 가 거부 → 위변조 자동 방지.

### `POST /v1/payment/verify` (UserGuard)

요청: `{ querystring: string }` (return_url 의 raw querystring 그대로).

서버 동작:
1. Eximbay `/v1/payments/verify` 에 `{data: querystring}` POST → rescode 검증.
2. `transaction_id`, `order_id`, `amount`, `payment_method` 파싱.
3. **금액 재검증** — `expectedUsd = order.subtotal / fxRate`, `|paidUsd - expectedUsd| > 0.01` 이면 throw.
4. **race-free 전이** — `prisma.order.updateMany({ where:{id, paymentStatus:'pending'}, data:{ paymentStatus:'paid', paidAt:now, pgProvider:'eximbay', pgTid:transaction_id, paymentMethod }})`. count=0 도 정상(이미 status_url 로 처리된 케이스).

응답: `{ orderId: string }`. 클라이언트(`/checkout/redirect`)는 응답 수신 후 `useCartStore.clearCart()` 를 호출해 로컬·서버 카트를 비우고 `/checkout/success` 로 이동한다.

### `POST /webhooks/eximbay` (no guard, IP whitelist 미구현)

Eximbay 가 server-side로 같은 querystring 을 form-urlencoded POST. `verify` 와 동일한 멱등 update 호출. 응답 본문에 `rescode=0000&resmsg=Success` 텍스트 — 이 형식이 아니면 Eximbay 가 retry. `klow_server/src/main.ts` 의 CSRF 가드는 `/webhooks/` prefix 를 통과시킴.

### `PATCH /admin/orders/:id/refund` (AdminGuard)

기존 엔드포인트. paid 주문은 `OrdersService.refundByAdmin` 이 `PaymentService.refundOrder` 를 거쳐 Eximbay `/v1/payments/{tid}/cancel` 을 먼저 호출 → 성공 시 DB 를 `paymentStatus='refunded'`, `status='cancelled'` 로 전이. PG 호출과 DB 사이 race(서버 크래시) 시 inconsistency 가능 — 운영 단계에서 outbox 로 보강.

> Eximbay cancel API body 는 nested 구조다:
> ```json
> { "mid": "...",
>   "refund": { "refund_type": "F", "refund_amount": "1.00", "refund_id": "<order.id>", "reason": "..." },
>   "payment": { "order_id": "...", "currency": "USD", "amount": "1.00", "balance": "1.00", "lang": "EN" } }
> ```

`PATCH /v1/orders/:id/cancel` (UserGuard) 도 동일 패턴이지만 reason 은 `'user requested cancel'`. shipped/completed 주문은 가드로 차단.

### 어드민 주문 목록 — 필터

`GET /admin/orders` 는 `?status=...` 와 `?paymentStatus=...` 를 동시 지원한다 (둘 다 optional). klow_admin `/orders` 페이지가 두 필터를 별도 ribbon 으로 노출 — 결제 상태별로 환불 대상 주문을 빠르게 찾을 수 있다.

---

## DB 컬럼 매핑

| 컬럼 | 값 |
|------|------|
| `Order.paymentStatus` | `'pending'` → `'paid'` (verify) → `'refunded'`/`'cancelled'` |
| `Order.pgProvider` | `'eximbay'` |
| `Order.pgTid` | Eximbay `transaction_id` (unique 인덱스) |
| `Order.paymentMethod` | Eximbay payment_method 코드 (예: `P101` 카드) |
| `Order.paidAt` | verify 성공 시점 |
| `Order.cancelledAt` | refund/cancel 시점 |
| `Order.subtotal` | customer KRW (변경 없음 — Eximbay amount 는 `subtotal/fxRate` 로 USD 환산) — 이 환산을 없애고 USD 정본으로 옮기는 풀 전환 설계는 [`pricing-usd-migration.md`](./pricing-usd-migration.md) 참고 |

스키마/마이그레이션 변경 없음.

---

## 환경변수

`klow_server/.env`(gitignored) 와 `.env.example` 양쪽에 동기:

```
EXIMBAY_API_BASE=https://api-test.eximbay.com
EXIMBAY_SDK_URL=https://api-test.eximbay.com/v2/javascriptSDK.js
EXIMBAY_MID=1849705C64
EXIMBAY_API_KEY=test_1849705C642C217E0B2D
EXIMBAY_RETURN_BASE_SERVER=http://localhost:4000
```

`return_url` 의 host (klow_web) 는 기존 `FRONTEND_URL` 을 재사용한다. `klow_web` 은 별도 env 추가 없음 — SDK URL 은 백엔드 echo 로 받는다.

---

## 로컬 테스트 절차

### 사전 준비

- Neon dev DB 에 brand/product 1개. amount 가 정확히 $1 이 되어야 한다면 임시로 `klow_server/src/common/pricing.ts` 의 `SHIPPING_USD=0`, `PAYMENT_FEE_RATE=0` 으로 두고 `salePrice=1380` (fx=1380 가정) 단일 상품을 카트에 1개 추가.
- 3 터미널: `klow_server` (4000), `klow_admin` (3000), `klow_web` (3001).
- `.env` 에 EXIMBAY_* 6개 키 채우고 `npm run start:dev` 재시작.

### Step-by-step

1. **Cart**: klow_web 로그인 → 상품 → Add to cart → /cart 라인 표시.
2. **Checkout 진입**: `/checkout`. Place order 버튼 활성화 확인. 폼 채움.
3. **Place order**:
   - DevTools Network: `POST /v1/orders` → 201 `{id}`. Prisma Studio 에서 그 row `paymentStatus='pending'`.
   - `POST /v1/payment/prepare` → 200 (`fgkey`, `sdkUrl`, payment.amount='1.00').
   - `javascriptSDK.js` 200 → Eximbay 팝업.
4. **결제 진행**: 팝업에서 Eximbay 테스트 카드 입력 → 결제 성공.
5. **Return**: `/checkout/redirect?rescode=0000&order_id=...&transaction_id=...` 로 이동.
6. **Verify**:
   - `POST /v1/payment/verify` → 200 `{orderId}`.
   - klow_server 콘솔: Eximbay `/v1/payments/verify` rescode=0000.
   - Prisma Studio: 그 order 의 `paymentStatus='paid'`, `paidAt`, `pgProvider='eximbay'`, `pgTid`, `paymentMethod`.
7. **Success page**: `/checkout/success?id=...&email=...` 도달.
8. **/orders 확인**: klow_web `/orders` 목록에 그 주문이 paid 로 표시.
9. **status_url 비도달 OK**: 로컬에서 외부에서 localhost 도달 안되니 `/webhooks/eximbay` 호출 0회 — 정상.
10. **Admin 환불**: klow_admin `/orders/<id>` → 환불 버튼 → 사유 입력.
    - `PATCH /admin/orders/:id/refund` → 200.
    - 콘솔: Eximbay `/v1/payments/<tid>/cancel` rescode=0000.
    - Prisma Studio: `paymentStatus='refunded'`, `status='cancelled'`, `cancelledAt`.
11. **재시도 차단**: 같은 orderId 로 prepare 재호출 → 400 `'order is not payable'`.

---

## TODO (운영 배포 단계)

- **`/webhooks/eximbay` source IP whitelist** — Eximbay 운영 `15.165.144.33`, 테스트 `43.203.92.211`/`3.34.20.184`/`3.37.76.229`/`52.79.143.149`.
- **Outbox / idempotency_key** — PG cancel 호출 성공 후 DB updateMany 사이 서버 크래시로 인한 inconsistency(PG 환불 됐지만 DB 는 paid) 차단.
- **`Order.paidFxRate` 컬럼** — prepare/verify/refund 사이 `ShopSettings.usdKrwRate` 가 변경되면 amount 계산이 어긋날 수 있음. Order 에 시점 fx 를 박아두면 race 차단.
- **라이브 키 + 운영 도메인** — `EXIMBAY_API_BASE`/`EXIMBAY_SDK_URL`/`EXIMBAY_MID`/`EXIMBAY_API_KEY` 4개를 교체하고 `FRONTEND_URL`(return_url host)과 `EXIMBAY_RETURN_BASE_SERVER`(status_url host)를 운영 도메인의 https URL 로 변경.
- **결제수단별 UI 분기** — 현재는 통합 결제창 자동 노출. 카드/PayPal/Alipay 라디오 노출이 필요하면 `payment_method` 코드를 채워 prepare 호출.
- **product[]/ship_to/bill_to** — PayPal·Klarna 결제 시 필수. `Order` 의 배송지/아이템에서 채울 수 있음.
