# Payment Integration

KLOW 의 결제 흐름. 외국인 타깃 K-beauty 커머스에서 한국 PG 사로 단일 routed 처리하는 구조와, 서버가 진실의 출처가 되는 검증·환불·웹훅 흐름을 정리.

## 채택 사양

- **PG사:** 포트원(PortOne) V2 + 나이스정보통신(NICE) 채널
- **결제 수단:** 카드 (외국인 발급 카드는 NICE 해외결제 MID, 한국 카드는 도메스틱 MID 로 라우팅)
- **결제 통화:** **KRW only.** NICE 가 KRW 외 통화로 settle 하지 않는다.
- **DB 저장 통화:** `Product.price/salePrice`, `Order.subtotal`, `OrderItem.unitPrice` 모두 **KRW 정수**. (마이그레이션 `20260505120000_price_to_krw_backfill` 이 기존 USD-scale 값을 ×1380 후 100원 단위 스냅으로 백필)
- **표시 통화:** klow_web 은 외국인 타깃이라 기본 USD (`formatPrice(krw)` = KRW÷rate). 카트 합계, 체크아웃 Total, "Place order" 버튼, 주문 상세 Total 처럼 **실제 청구 금액이 중요한 자리**에는 `formatKrw` 부제 동시 표시. 환율은 어드민이 `/shop-settings` 에서 실시간 갱신 (ShopSettings.usdKrwRate, default 1380) → klow_web 부팅 시 `GET /v1/shop/fx-rate` 로 가져와 zustand persist store 캐싱.
- **결제창 locale:** `requestPayment` 에 `locale: 'EN_US'` 명시 → 외국인이 PortOne overlay 를 영어로 본다.
- **모바일 결제창:** `redirectUrl: ${origin}/checkout/redirect` 지정. PortOne SDK 가 환경에 맞춰 PC 는 popup, 모바일은 redirect 로 자동 분기.

---

## 결제 플로우

```
[사용자]                [klow_web]              [klow_server]              [PortOne / NICE]
                            │
   ① "Place order" 클릭 ──▶ │
                            │
                            ├─ POST /v1/orders ───────────▶ Order 생성
                            │                              (status=pending,
                            │                               paymentStatus=pending,
                            │                               subtotal in KRW)
                            │◀─────── { orderId } ─────────┤
                            │
                            ├─ POST /v1/payment/prepare ──▶ Order 금액 조회
                            │   { orderId, cardType }        cardType 으로 도메스틱/해외 채널 선택
                            │                                paymentId 발급, pgTid 저장
                            │◀── { paymentId, totalAmount, ─┤
                            │     storeId, channelKey,
                            │     orderName, customer }
                            │
                            ├─ PortOne.requestPayment() ─────────────────────▶ NICE 결제창
                            │   currency: 'CURRENCY_KRW'                       (locale=EN_US,
                            │   payMethod: 'CARD'                              모바일은 redirect)
                            │   locale: 'EN_US'
                            │   redirectUrl: /checkout/redirect
   ② 카드 결제 ────────────────────────────────────────────────────────────▶ 표시
                            │◀────────── 성공 콜백 ──────────────────────────┤
                            │
                            ├─ POST /v1/payment/complete ─▶ PortOne REST 조회 ─▶ GET /payments/{id}
                            │   { paymentId }              ↓                  ◀┤
                            │                              order.subtotal ===
                            │                              PortOne.amount.total?
                            │                               ├ 같음+PAID: paid 전이
                            │                               └ 불일치: cancel 호출 + failed
                            │◀──── { status: 'paid' } ─────┤
                            │
   ③ 주문 완료 페이지 ─────◀
                                                          ▲
                                                          │ ④ (비동기 보강)
                                                          │   웹훅 멱등 처리
                                                          │   Transaction.Paid/Cancelled/Failed
                                                          ◀──────────────────┤
```

### 상태 전이

| Order.status | paymentStatus | 의미 |
|---|---|---|
| pending | pending | 주문 생성, 결제 시도 전 |
| pending | paid | 결제 완료, 운영자 출고 준비 시작 |
| processing → shipped → completed | paid | 정상 진행 |
| cancelled | cancelled | paid 이전 단계에서 취소 (PG 호출 없음) |
| cancelled | refunded | paid 이후 환불 완료 (PortOne cancel 호출됨) |
| pending | failed | `complete` 에서 amount mismatch 또는 비-PAID 상태 감지 |

---

## 구현 — 어디 무엇이 있는지

### klow_server

```
src/modules/
├── orders/
│   ├── orders.service.ts          # 주문 생성/조회/취소; cancel 시 paid → PortOne refund
│   ├── public-orders.controller   # POST /v1/orders, GET /v1/orders/mine, /v1/orders/:id, PATCH /:id/cancel
│   └── admin-orders.controller    # GET /admin/orders, /admin/orders/:id, PATCH /:id/status, POST /:id/refund
└── payment/
    ├── payment.service.ts          # prepare / complete / refundByOrderId / mark*ByPaymentId
    ├── payment.controller.ts       # POST /v1/payment/prepare, /v1/payment/complete (UserGuard)
    └── payment-webhook.controller.ts  # POST /webhooks/portone (signature-verified)
```

**핵심 원칙 (절대 지킬 것):**

1. **금액은 서버가 진실** — `prepare` 도 `complete` 도 `Order.subtotal` 만 신뢰. 클라이언트가 보낸 금액은 어디서도 받지 않는다.
2. **`complete` 에서 PG 직접 조회** — 클라이언트의 "성공" 응답만 믿지 말고 서버가 `GET /payments/{id}` 한 번 더 확인하고, `payment.amount.total !== order.subtotal` 이면 즉시 PortOne `cancel` 호출 + `failed` 전이.
3. **웹훅은 보강용** — `complete` 가 메인 경로. 웹훅은 멱등 (이미 paid 면 skip). 처리 실패 시 5xx 로 응답해 PortOne 재시도(최대 5회 exponential backoff) 유도.
4. **취소·환불은 서버 → PG** — 클라이언트가 직접 PG 호출 금지. `PATCH /v1/orders/:id/cancel` 이 paid 면 서버가 PortOne cancel + `refunded` 전이; pending 이면 단순 상태 변경. 어드민 `POST /admin/orders/:id/refund` 도 같은 경로 재사용.
5. **TID 멱등 키** — `Order.pgTid @unique` 가 paymentId. 재결제 시 새 paymentId 로 덮어써서 동일 주문이 두 번 PG 측 결제를 만들지 않게 한다.

**환경 변수 (klow_server/.env):**

```
PORTONE_STORE_ID=store-xxxxx
PORTONE_CHANNEL_KEY=channel-key-NICE-xxxxx        # 도메스틱 카드 (한국 발급)
PORTONE_CHANNEL_KEY_INTL=channel-key-NICE-xxxxx   # 해외 카드 (외국 발급)
PORTONE_API_SECRET=xxxxx
PORTONE_WEBHOOK_SECRET=whsec_xxxxx
PORTONE_API_BASE=https://api.portone.io           # 선택, 기본값
```

### klow_web

- `/checkout/page.tsx` — 4단계 흐름 (`POST /v1/orders` → `POST /v1/payment/prepare` → `PortOne.requestPayment()` → `POST /v1/payment/complete`). 도메스틱/해외 카드 토글(`cardType`)이 prepare body 에 실린다.
- `/checkout/redirect/page.tsx` — 모바일 redirect 흐름의 콜백 랜딩.
- `/checkout/success/page.tsx`, `/checkout/failed/page.tsx` — 결과 분기. 실패 페이지는 `?reason=` 쿼리로 사유 표시 후 재시도 버튼.
- `/orders/[id]/page.tsx` — `paymentStatus` 뱃지 + Total 의 USD/KRW 듀얼 표시 + cancel 버튼.
- `useFxRateStore` (zustand persist) + `<FxRateMount/>` (layout) — 부팅 시 + 탭 visibility 회복 시 환율 갱신.

### klow_admin

- `/orders` 목록에 결제 상태 컬럼.
- `/orders/[id]` 상세에 PG 결제 정보 패널 (`paymentStatus`, `paymentMethod`, `pgProvider`, `pgTid`, `paidAt`) + 환불 버튼 (사유 필수, AdminAuditLog 자동 기록).
- `/shop-settings` 의 "USD ↔ KRW 환율" 섹션에서 운영자가 환율 직접 갱신.

---

## PG 심사 표시 / 전자상거래법 요건

결제 연동 전에 미리 구축한 표시·동의·정보제공 요소들. 자세한 위치는 `architecture.md`의 PG 심사 섹션 참고.

- 전역 푸터 사업자정보 + ftc.go.kr 통신판매업 조회 링크
- 체크아웃 4종 동의 체크박스 (필수 모두 체크해야 Place order 활성)
- 상품 상세 환불·배송 안내 카드 + 화장품법 상품정보제공고시 8개 필드
- 주문 상세 고객지원 카드 + FAQ 페이지

이 요소들은 카드사 심사 요건 그대로 유지해야 한다 (특히 메인+결제 페이지 푸터 상시 노출).
