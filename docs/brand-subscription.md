# Brand Subscription — 브랜드 입점 멤버십 (NicePay 포스타트 빌링)

> **현재 PG: NicePay 포스타트(NEW v2 REST) 빌링.** 브랜드가 자기 입점 멤버십을 정기결제하는
> 구독(SaaS) 기능이며, **결제가 곧 노출·판매의 게이트**다. 결제가 없으면 상품이 공개되지도 팔리지도 않는다.
> 초기 설계는 토스페이먼츠였고 NHN KCP 를 거쳐 NicePay 로 교체됐다 — 경위는 문서 끝 [변경 이력](#변경-이력) 참고.
>
> 코드 정본: `klow_server/src/modules/subscription/` · Prisma `BrandSubscription`/`BillingKey`/`SubscriptionInvoice`.

---

## 1. 개요 & 결정 배경

- **결제 주체:** `BrandUser`(전화·이메일·Google 어느 방식으로 가입했든 동일) — 영수증·계약은 `Brand` 단위.
- **결제 대상:** 국내 브랜드(KRW). 해외 브랜드 구독은 범위 밖.
- **klow_web 소비자 결제(Eximbay, 일회성·글로벌 카드)와는 완전히 다른 도메인**이라 PG·DB 모델·관리자 UI 모두 분리했다.
  - 소비자 결제: 일회성·글로벌 카드·주문 단위
  - 브랜드 구독: 빌링키 기반 정기결제·국내 KRW·멤버십 단위·dunning(연체 자동 재시도)·해지 워크플로우
- **입점 신청과 결제를 묶은 이유:** 어드민 수동 승인 부담 제거(결제=자동 승인), 무자격 신청자 자연 차단,
  첫달 매출 즉시 확보, 결제·노출·판매를 단일 게이트(`subscription.status='active'`)로 통일.
- **같은 klow_server / 같은 DB 를 공유해도 안전:** 라우팅(`/v1/brand/subscription/*`)·세션 쿠키(`klow_brand_sid`)·
  CORS·Prisma 테이블이 모두 소비자 결제와 분리돼 있다. 결제 로직만 별도 모듈(`subscription/`).

## 2. 요금제

**단일 플랜 (`brand_standard`) · 월/연 주기만 선택.**

| 주기 | 공급가(KRW) | 실청구액(VAT 10% 포함) | 월 환산 |
|---|---|---|---|
| 월납 (`monthly`) | ₩45,000 | **₩49,500** | ₩49,500 |
| 연납 (`annual`)  | ₩456,000 | **₩501,600** | ₩41,800 (연 ₩92,400 절약) |

- **무료 체험 없음** — 심사 정보 제출 직후 즉시 결제.
- 결제 주기(`BrandSubscription.billingInterval`)가 금액과 다음 결제일(월 +1개월 / 연 +12개월)을 가른다.
- 단일 플랜이라 `SubscriptionPlan` 테이블을 만들지 않고 **코드 상수 + 환경변수**로 관리한다:
  - `SUBSCRIPTION_MONTHLY_PRICE_KRW=49500` (미설정·비정상 시 코드 기본값 49500 + WARN 로그)
  - `SUBSCRIPTION_ANNUAL_PRICE_KRW=501600`
  - `SUBSCRIPTION_PLAN_CODE=brand_standard`
  - `SUBSCRIPTION_ORDER_NAME_PREFIX=KLOW 브랜드 멤버십`

> **금액 정본은 env(→ `amountKrw()`)다.** 어드민 detail 응답은 `monthlyPriceKrw` 를 함께 내려
> "현금결제 발급" 다이얼로그가 하드코딩 없이 기본값을 채운다. (schema/validation 주석에 남은 구 금액 표기는 무시.)

## 3. 도메인 모델

모두 신규 Prisma 모델. 기존 `Order`/`OrderItem`/`Payment` 는 손대지 않는다. 소비자 주문의
`PaymentStatus(pending|paid|failed|cancelled|refunded)` 와 구독 상태 enum 은 의미가 달라 **분리**한다.

```prisma
model BrandSubscription {
  id                 String   @id @default(cuid())
  brandId            String   @unique          // 1 brand = 1 subscription (upsert 멱등 키)
  planCode           String   @default("brand_standard")
  billingInterval    String   @default("monthly")   // 'monthly' | 'annual'
  status             BrandSubscriptionStatus         // active | past_due | canceled
  currentPeriodStart DateTime
  currentPeriodEnd   DateTime
  cancelAtPeriodEnd  Boolean  @default(false)
  canceledAt         DateTime?
  billingKeyId       String?                         // null = 수동 발급(무료/현금) 구독
  billingKey  BillingKey?           @relation(...)
  invoices    SubscriptionInvoice[]
  @@index([status]) @@index([currentPeriodEnd])
}

model BillingKey {
  id           String   @id @default(cuid())
  brandId      String
  provider     String   @default("nicepay")
  pgBillingKey String   @unique          // NicePay bid — 평문 저장(토큰, secretKey 없이는 결제 불가)
  cardCompany  String?
  cardLast4    String?  @db.VarChar(4)
  isDefault    Boolean  @default(true)
  deletedAt    DateTime?                  // 카드 변경 시 soft delete
  @@index([brandId])
}

model SubscriptionInvoice {
  id            String @id @default(cuid())
  subscriptionId String
  amountKrw     Int
  status        SubscriptionInvoiceStatus @default(pending)  // pending | paid | failed | refunded
  pgProvider    String?                    // 'nicepay' | 'cash'
  pgTid         String?  @unique            // NicePay 빌키승인 tid (환불 시 사용). 현금은 null
  periodStart   DateTime
  periodEnd     DateTime
  attemptCount  Int      @default(0)        // dunning 재시도 횟수
  lastAttemptAt DateTime?
  paidAt        DateTime?
  failReason    String?  @db.VarChar(500)
  @@index([subscriptionId]) @@index([status])
}
```

### planCode 로 갈리는 3종 구독

| planCode | billingKeyId | 발급 경로 | cron 취급 |
|---|---|---|---|
| `brand_standard` | 있음 | 브랜드 카드 결제 (`start`) | 만료 시 자동 청구(갱신) |
| `brand_comp`     | null | 어드민 **무료 구독권** (`grant`) | 만료 시 자동 `canceled` (청구 안 함) |
| `brand_cash`     | null | 어드민 **현금결제 발급** (`grant-cash`, 받은 금액 paid invoice 기록) | 만료 시 자동 `canceled` |

### Brand 상태 연동

- `Brand.pgCustomerKey`(String?) — **결제 준비 게이트 플래그 + cron 청구 대상 필터**. NicePay 엔 고객 식별 개념이
  없지만, `submit-for-review` 시 발급해 두고 cron 은 `pgCustomerKey != null` 인 구독만 청구한다.
- `Brand.status` (draft/pending/approved/rejected/withdrawal_pending/withdrawn) — 결제 성공 시 시스템 액터가
  `approved` 로 승인. **해지·환불은 `Brand.status` 를 건드리지 않는다**(구독만 `canceled`) → 재가입 가능.
- `Brand.submittedById` — null 이면 어드민/legacy 브랜드(구독 게이트 면제, [§7](#7-노출-게이트) 참고).

## 4. 가입 · 첫 결제 흐름 (`POST /v1/brand/subscription/start`)

핵심은 **PG 호출을 DB 트랜잭션 밖으로 분리**하는 것이다. 외부 API 대기로 트랜잭션이 길어지면 DB 락·커넥션
고갈·타임아웃 unknown state 위험이 있어, `start` 를 4단계로 나눈다.

```
브랜드      klow_brand               klow_server                         NicePay
 │  송화인4+계좌3 입력                    │                                  │
 │────────► submit-for-review ──────────►│ Brand.status='pending'            │
 │          (OnboardingGate)             │ pgCustomerKey 발급(null이면)       │
 │◄──────── {brand} ─────────────────────│                                  │
 │  CardEntryForm 카드입력                │                                  │
 │  (cardNo/expYear/expMonth/idNo/cardPw) │                                  │
 │────────► POST subscription/start ─────►│                                  │
 │          {카드필드, billingInterval}    │                                  │
 │                              ┌─ Stage 1 (DB read) ───────────────┐        │
 │                              │ assertEligibleForStart            │        │
 │                              │ assertOnboardingFieldsFilled(7)   │        │
 │                              │ seedingAgreement 존재 확인         │        │
 │                              └───────────────────────────────────┘        │
 │                              ┌─ Stage 2 (tx 밖, PG) ─────────────┐        │
 │                              │ AES 암호화 encData                 │        │
 │                              │ POST /v1/subscribe/regist ────────┼───────►│ bid
 │                              │ POST /v1/subscribe/{bid}/payments ┼───────►│ tid, status:paid
 │                              │ (실패 시 netCancel + expire 정리)   │        │
 │                              └───────────────────────────────────┘        │
 │                              ┌─ Stage 3 (단일 tx) ───────────────┐        │
 │                              │ BillingKey create (bid)            │        │
 │                              │ BrandSubscription upsert (active)  │        │
 │                              │ Invoice create (paid, pgTid=tid)   │        │
 │                              │ pgCustomerKey 박기(없으면)          │        │
 │                              └───────────────────────────────────┘        │
 │                              ┌─ Stage 4 (tx 밖, 멱등) ───────────┐        │
 │                              │ approveApplication(system)         │        │
 │                              │ → Brand=approved, Product=approved │        │
 │                              └───────────────────────────────────┘        │
 │◄──────── {brand: 승인·구독 포함} ──────│                                  │
 │  /studio 복귀 + "판매 시작" 토스트       │                                  │
```

**Stage 1 — 사전 조건 (DB read only)**
- `assertEligibleForStart`: **(pending && 구독 없음)** = 신규, 또는 **((approved|pending) && 구독 canceled)** = 재가입.
  그 외는 차단 — `active` → **409**, `past_due` → 400(카드 교체 후 자동 재시도), `draft|rejected` → 심사 제출 먼저, `withdrawal_pending|withdrawn` → 결제 불가.
- `assertOnboardingFieldsFilled`: 송화인·정산 **7필드**(`senderName`, `senderAddress`, `senderPostalCode`,
  `senderPhone`, `bankName`, `bankAccountHolder`, `bankAccountNumber`) 모두 `trim()` 후 non-empty. 미달 시
  `400 brand_not_ready_for_payment` + `missing[]`. (OnboardingGate 클라 검증과 서버 zod 가 동일 규칙이라 방어선 역할.)
- **시딩 이용계약서 서명**(`seedingAgreement`) 존재 필수 — 없으면 `400 seeding_agreement_required`(프론트 우회 차단).

**Stage 2 — NicePay PG 호출 (tx 밖, 순차 2건)**
- `registerBillingKey`: 카드정보를 AES-256-CBC 로 암호화한 `encData`(encMode `A2`) + `signData` 로
  `POST /v1/subscribe/regist` → **bid**. `regOrderId = sha256("reg-{brandId}-{now}")`.
- `chargeBilling`: `POST /v1/subscribe/{bid}/payments` (amount, `cardQuota:'0'`, `useShopInterest:false`) → **tid**,
  `status:'paid'`. `chargeOrderId = sha256("start-{bid}")`. 성공 즉시 `subscription_payment_done ... tid=` 로그.
- **첫 결제 실패 시 orphan 정리:** 네트워크/타임아웃(NicePay 에러 아님)이면 `netCancel`(1h 내 망취소) → 그리고
  `deleteBillingKey`(bid expire, best-effort). DB 엔 아무 row 도 안 만든다.

**Stage 3 — 결제기록 커밋 (단일 짧은 tx)**
- `BillingKey` create(`provider:'nicepay'`, bid, cardCompany/last4) → `BrandSubscription` upsert(`active`, period,
  billingInterval, `planCode` 갱신) → `SubscriptionInvoice` create(`paid`, `pgTid=tid`, `pgProvider:'nicepay'`) →
  pgCustomerKey 박기.
- 커밋 실패 시(돈만 빠진 위험 상태) `subscription_start_db_commit_failed ... tid=` **ERROR** 로그로 운영자 수동 환불 유도.

**Stage 4 — 브랜드 승인 (tx 밖, 멱등)**
- `approveApplication({ actor:{type:'system', reason:'subscription_started'} })` → `Brand.status='approved'` +
  pending 제품 `approved`. **결제 커밋 뒤 별도 호출**이라 승인 로직 throw 가 방금 청구된 결제기록을 롤백하지 않는다.
  실패해도 active 구독·paid invoice 는 남으므로 결제는 성공 응답, 노출 누락은 ERROR 로그 기반 어드민 재승인.

### 멱등성

- `assertEligibleForStart` 가 이미 `active` 면 409 → 중복 결제 1차 차단. 프론트 busy 상태가 2차.
- `orderId` 는 매 시도 고유(reg=시각, charge=bid 기반)라 **같은 달 강제해지→재구독 같은 정상 재시도는 막지 않는다.**
- `BrandSubscription.brandId @unique` 로 동시 upsert 는 직렬화.

> 시스템 액터 approve 는 `AdminAuditInterceptor`(어드민 컨트롤러 전용)에 안 잡혀 `logger`로만 기록된다 — 별도
> `SystemAuditLog` 테이블은 미도입([§10 TODO](#10-todo)).

## 5. 정기 청구 & dunning (cron)

**`subscription-billing.cron.ts`** — `@Cron('0 0 * * *', { timeZone:'Asia/Seoul' })` 일일 KST 자정,
`runDueBilling()` 위임. 각 brand 는 `Promise.allSettled` 격리(한 brand 실패가 cron 전체를 막지 않음).

`runDueBilling` 은 `Promise.all` 로 3 대상을 한 번에 뽑는다(`chargeReady = billingKeyId≠null && brand.pgCustomerKey≠null`):

1. **갱신** — `active && currentPeriodEnd≤now && !cancelAtPeriodEnd` → `chargeOne(sub)`
2. **종료** — `active && currentPeriodEnd≤now && cancelAtPeriodEnd` → 결제 없이 `canceled`
3. **dunning 재시도** — `past_due` 중 최근 invoice 가 `failed` 이고 `retryGap(attemptCount)` 도래 → `chargeOne(sub)`
4. **수동 구독 만료** — `active && billingKeyId=null && currentPeriodEnd≤now` → `updateMany` 로 일괄 `canceled`
   (무료/현금 구독은 청구 대상이 아니라 만료 시 자동 종료. chargeReady 와 정확히 상보적이라 겹치지 않음)

### `chargeOne(sub)` — N+1 회피용으로 이미 로드된 sub 객체를 받음

1. 최근 invoice 가 `failed` 면 재사용(재시도), 없으면 새 `pending` invoice 생성(갱신)
2. `orderId = sha256(invoice.id)` (멱등)
3. tx 밖에서 `chargeBilling`
4. **성공** — 단일 tx: invoice `paid`(pgTid) + subscription `active` + 사이클 전진 + (비어있으면) cardLast4 backfill
   — 빌키발급 응답엔 카드번호가 없어 첫 승인 응답에서 끝4자리를 채운다.
5. **실패** — invoice `failed` + `attemptCount++` + `failReason` + subscription `past_due`.
   네트워크/타임아웃이면 `netCancel` 로 orphan 승인 방지.

### retryGap (dunning 스케줄)

| 직전 `attemptCount` | 다음 재시도 |
|---|---|
| 0 | 즉시(다음 cron) |
| 1 | +1일 |
| 2 | +3일 |
| 3 | +7일 |
| 4+ | 없음 — `past_due` 확정 |

카드 자체 문제(permanent)든 일시 실패(transient)든 **분류 구분 없이 attemptCount 만 보고** 재시도한다
(분류는 사용자 메시지용). 4회 소진 시 운영자 force-cancel 또는 사용자 카드 교체로 정리.

## 6. 해지 · 재개 · 환불 · 카드 변경

**Brand 셀프 (`/v1/brand/subscription/*`, BrandGuard):**

| 경로 | 역할 |
|---|---|
| `GET /` | 자기 구독 + billingKey + 최근 invoice 12건 |
| `POST /start` | 신규/재가입 결제 ([§4](#4-가입--첫-결제-흐름-post-v1brandsubscriptionstart)) |
| `POST /cancel` | 해지 예약 — `cancelAtPeriodEnd=true`. 현재 사이클 끝까지 active(노출 유지), 만료 시 cron 이 `canceled` |
| `POST /resume` | 해지 예약 취소 — 만료 전 `cancelAtPeriodEnd=false` 로 복구(다음 사이클 자동 갱신 부활) |
| `POST /resume-existing-card` | 해지된 구독을 **기존 빌키로 즉시 재결제**해 active 복귀 (카드 재입력 없음) |
| `POST /change-card` | 새 빌키 발급 + 기존 키 soft delete + NicePay expire. `past_due` 면 즉시 1회 `chargeOne` 재시도 |

- **해지:** 환불 없음. 사이클 만료 시점까지 사용 후 자동 종료.
- **카드 변경:** 무료 구독권(`brand_comp`)엔 불가(유료 재결제 유도). 새 `registerBillingKey` → BillingKey 교체
  (new `isDefault`, old `deletedAt`) → 이전 bid `expire`(log-only) → `past_due` 였으면 즉시 재결제 시도.

**환불 (어드민 전용, `PATCH /:id/invoices/:invoiceId/refund`):**
- **기본 정책은 환불 없음** — 월중 해지도 사이클 만료까지 사용. 분쟁·고객 응대 예외만 어드민이 처리.
- 카드 결제(`pgProvider≠'cash'`): NicePay `POST /v1/payments/{tid}/cancel`(전액 또는 `cancelAmount` 부분환불,
  결제액 초과 차단) 호출 → invoice `refunded` + subscription `canceled` (단일 tx).
- 현금 invoice(`pgProvider='cash'`): PG 호출 없이 `refunded` 표시만(환불은 오프라인). 부분환불은 카드 전용.

## 7. 노출 게이트

`product-selects.ts` 의 **`PURCHASABLE_PRODUCT_WHERE = PUBLIC_PRODUCT_WHERE`** — 노출·판매를 단일 게이트로 통일.
`status='approved'` + OR 3분기:

1. **가입 brand** (`submittedById≠null`) — `subscription.status='active'` 동안만 통과
2. **어드민이 만든 brand** (`submittedById=null`) — 구독 무관 통과 (KLOW 자체 사입)
3. **legacy** (`brandId=null`) — 안전 통과

`isPurchasable()`(cart/orders in-memory 게이트)도 동일 3분기. 호출처 `brandRef` include 에 `submittedById` +
`subscription{status}` 를 select 해야 타입 가드가 성립한다. → 가입 brand 의 구독이 없거나(결제 미완료)
`past_due`(연체)면 노출·판매 모두 차단.

## 8. 어드민 운영 도구

어드민 책임이 "신청 검수"에서 **"구독 관찰 + 정책 위반·분쟁 강제 종료 + 수동 발급"** 으로 재정의됨.

- **목록:** 구 `/admin/brand-subscriptions` 목록은 통합 **`/admin/brands`** 로 흡수됐다
  (`brands.service.listForAdmin` — brand + subscription summary + billingKey + 제품수, `subStatus` 필터
  active/past_due/canceled/none).
- **상세·액션:** `admin/brand-subscriptions/:id` (`AdminGuard` + `AdminAuditInterceptor`):

| 경로 | 역할 | NicePay 호출 | 환불 |
|---|---|---|---|
| `GET /:id` | 상세 — brand + 구독(billingKey + 전체 invoices) + submittedBy + 제품 + `monthlyPriceKrw` | — | — |
| `PATCH /:id/reject` | **정책 위반 차단** — brand `rejected` + 활성 구독 `forceCancelIfActive`(silent) 묶음 | ❌ | ❌ |
| `PATCH /:id/force-cancel` | 즉시 강제 해지 — 구독만 `canceled`, brand.status 유지 | ❌ | ❌ |
| `PATCH /:id/grant` | **무료 구독권** — 결제 없이 N개월(1~24) active + brand 승인 (`brand_comp`) | ❌ | — |
| `PATCH /:id/grant-cash` | **현금결제 발급** — 받은 금액 paid invoice + N개월 active (`brand_cash`) | ❌ | — |
| `PATCH /:id/invoices/:invoiceId/refund` | **분쟁 환불** — cancel API + invoice refunded + subscription canceled | ✅ | ✅ |
| `PATCH /:id/products/:productId/approve` \| `/reject` | 제품 단위 차단 해제 / 차단 | ❌ | — |

- `forceCancelIfActive` 는 활성 구독이 없거나 이미 canceled 면 silent skip(brand reject 만 진행). 명시적
  `forceCancel` 은 구독 없을 때 400(직접 액션은 명확한 피드백 필요).
- 수동 발급(`grant`/`grant-cash`)은 draft(7필드 미입력) brand 를 막고(EFS 송장 불가), 결제로 만든 활성/연체
  구독을 덮어쓰지 않는다.

## 9. 환경변수 & 보안 (PCI)

**`klow_server/.env`:**

```
NICEPAY_API_BASE=https://sandbox-api.nicepay.co.kr   # 운영: https://api.nicepay.co.kr
NICEPAY_CLIENT_KEY=            # Basic 인증 앞부분
NICEPAY_SECRET_KEY=            # Basic 인증 + encData AES 키 + signData. 서버 전용, 노출 금지
SUBSCRIPTION_MONTHLY_PRICE_KRW=49500
SUBSCRIPTION_ANNUAL_PRICE_KRW=501600
SUBSCRIPTION_PLAN_CODE=brand_standard
SUBSCRIPTION_ORDER_NAME_PREFIX=KLOW 브랜드 멤버십
```

**`klow_brand/.env.local`:** PG 키 불필요(`NEXT_PUBLIC_API_URL` 만). 결제창/JS SDK 가 없어 public 키가 없다.

**인증·암호화 (`nicepay-billing.adapter.ts`):**
- **인증:** `Authorization: Basic Base64(clientKey:secretKey)`.
- **카드 암호화:** `encData` = AES-256-CBC(key=`secretKey[:32]`, iv=`secretKey[:16]`, hex, encMode `A2`).
  평문 `cardNo=..&expYear=..&expMonth=..&idNo=..&cardPw=..`.
- **위변조 검증:** `signData` = `hex(sha256(parts.join('') + secretKey))`.
- **성공 판정:** HTTP 200 + `resultCode==='0000'`(청구는 `status:'paid'` 동반). 실패는 `classifyNicepayError`
  로 permanent(3xxx 카드/Fxxx 빌링) / transient / upstream 분류해 400 으로 노출.
- **망취소:** `POST /v1/payments/netcancel` — 승인 타임아웃 시 1h 내 orphan 승인 방지(best-effort).

**웹훅 없음:** NicePay 빌링 API 는 **동기 응답(`resultCode`)** 이라 별도 webhook·서명 검증이 필요 없다.
멱등(`orderId`) + 동기 코드 검증 + `signData` 위변조 검증이 보안 모델. (구 토스 설계의 webhook TODO 는 폐기.)

**PCI scope (NicePay 교체로 변경됨):**
- **빌키(bid)는 평문 저장** — PG 토큰, secretKey 없이는 결제 불가.
- **카드 원문이 서버를 경유한다(변경점).** 포스타트엔 결제창 빌키발급이 없어 카드 원문이 브라우저→klow_server(TLS)
  로 전달된다. 서버는 즉시 AES 암호화해 NicePay 로 보내고 **원문을 저장·로깅하지 않는다**(DB엔 bid+카드사명+끝4자리).
  → 운영 전 **TLS 강제 · 요청 본문 로깅 금지 · NicePay 고정 egress IP · PCI-DSS SAQ A-EP 범위 인지** 필요.
- `NICEPAY_SECRET_KEY` 는 admin TOTP secret 급으로 관리(노출 시 임의 결제·취소 가능).

**코드 외 의존성:** NicePay 포스타트 가맹점 + **빌링(정기결제) 사용 신청**(미신청=F117 거절) + 가맹점관리자에서
clientKey/secretKey 발급. 샌드박스(`sandbox-api.nicepay.co.kr`)로 실청구 없이 발급·승인·삭제 TEST 가능.

## 10. klow_brand / klow_admin UI 진입점

### klow_brand

- **카드 입력 폼:** `src/components/CardEntryForm.tsx` (결제창 없음) — `cardNo`(14~16) / `expMonth`(MM) /
  `expYear`(YY) / `idNo`(생년월일6 또는 사업자10) / `cardPw`(앞2자리)를 받는다. 카드 원문은 klow_server 로
  보내고 클라에 저장하지 않는다. **재사용 2곳:** 첫 결제 `PaymentWallPanel`, 카드 변경 `settings/subscription`.
- **가입 진입 흐름** (`studio/page.tsx` 오케스트레이션):
  1. `OnboardingGate`(`studio/_components/`) 가 송화인4+계좌3 을 저장 → `api.applications.submitForReview`.
     응답이 `brand.pgCustomerKey` 를 박는다. `needsOnboarding(brand)` = draft/rejected 또는 `pending && !subscription`.
  2. `PaymentWallPanel` 의 `needsPaymentWall(brand)` = `needsOnboarding && !!pgCustomerKey` → 같은 탭이 자동으로
     paywall 로 전환. KLOW PRO 플랜(월 ₩45,000 / 연 월환산 ₩41,800, `billingInterval` 토글) + 자동결제 동의
     체크박스 + 약관 → CTA 로 `CardEntryForm` 모달 → `api.subscription.start({...card, billingInterval})`.
  3. paywall 은 `ShippingTab` / `SettlementTab` 안에서도(IdlePanel 통해) `forcePaymentWall` 로 노출된다.
  - **재가입:** `ResubscribeChoiceModal` — "기존 카드" → `resumeExistingCard()`, "새 카드" → PaymentWall 강제 진입.
- **셀프 관리 페이지** `settings/subscription/page.tsx` (패널 `_components/`): `SubscriptionPanel`(상태·플랜) /
  `CardPanel`(카드 + 변경) / `InvoicesPanel`(청구서) / `ResumePanel`(active && cancelAtPeriodEnd → 해지 예약 취소) /
  `CancelPanel`(active && !cancelAtPeriodEnd → 해지 예약). 설정 홈엔 `SubscriptionLinkCard`.
- **클라 helper** `src/lib/api.ts` `subscription.*`: `start` / `get` / `cancel` / `resume` / `resumeExistingCard` /
  `changeCard`. 에러 문구는 `src/lib/nicepay-billing.ts` `explainNicepayPaymentError` 가 서버 `classification`
  (permanent/transient/upstream)을 한국어로 변환.

### klow_admin

- **구 라우트는 리다이렉트만 남았다:** `(authed)/brand-subscriptions/page.tsx` → `/brands`,
  `.../[id]/page.tsx` → `/brands/[id]`. 기능이 **brands 영역으로 병합**됨.
- **목록** `(authed)/brands/page.tsx` — 브랜드 표(브랜드 상태 + 구독 상태 컬럼). `FilterPills` 로 브랜드 상태 +
  구독 상태(`active`/`past_due`/`canceled`/`none`) 필터 + 이름 검색. (사이클 progress bar 는 없다 — 현재 사이클은
  `currentPeriodStart — currentPeriodEnd` 텍스트로 표시.)
- **상세** `(authed)/brands/[id]/page.tsx` → `BrandDetailTabs` 의 **"구독 관리"** 탭 = `BrandSubscriptionPanel`
  (`api.brandSubscriptions.get(brandId)` 로 self-fetch). 액션: 강제 해지 / 정책 위반 차단(reject) / 청구서 환불
  (paid 행) / 제품 단위 차단·해제 / **무료 구독권 발급**(`GrantSubscriptionDialog`, reason+months) /
  **현금결제 발급**(`GrantCashSubscriptionDialog`, reason+months+amountKrw, 기본값 `monthlyPriceKrw×months`).
  grant 두 버튼은 활성/연체 구독이 없고 가입 brand 이며 7필드가 채워졌을 때만 활성.
  어드민 클라 `brandSubscriptions.*` 는 모두 서버 `/admin/brand-subscriptions/...` 를 호출한다(페이지 위치와 무관).

## 11. TODO

코드 대비 아직 미구현이거나 결정 대기 중인 항목:

- [ ] **세금계산서 발행** (NicePay 부가서비스 vs 자체) — 미구현.
- [ ] **운영자 알림 채널** (Slack/이메일) — 현재 `logger` 구조화 로그만. 알림 채널 없음.
- [ ] **연체/결제 실패 사용자 알림** — 현재 인앱 배너 + 카드 변경 CTA 뿐. 이메일/SMS 추가는 운영 데이터 보고 결정.
- [ ] **시스템 액터 audit** — `approveApplication(system)` 은 `logger` 로만 기록. `SystemAuditLog` 테이블 미도입.

> 웹훅은 TODO 가 아니다 — NicePay 동기 응답이라 **불필요**([§9](#9-환경변수--보안-pci)).

---

## 변경 이력

PG 는 두 번 교체됐다. 도메인 모델(BrandSubscription/BillingKey/SubscriptionInvoice)·cron/dunning·환불·해지·
카드교체·재가입 로직은 매번 그대로 두고 **PG 호출 계층(어댑터)·결제 입력 UI·에러 분류만** 갈아끼웠다.

- **토스페이먼츠 빌링키 (초기 설계)** — 국내 KRW 정기결제 표준, SDK(빌링키 발급)와 서버 승인 API 분리가 자체
  스케줄러와 잘 맞아 선택. `requestBillingAuth`→`authKey`→빌링키 교환, webhook 재검증 모델.
  → **교체 이유: 토스 자동결제 심사·계약 대기 기간이 길어짐.**
- **NHN KCP 자동결제(배치키) — 2026-05** — 토스 심사 대기를 우회하려 교체. 서비스 인증서(PEM)+RSA 서명,
  결제창(`kcp_spay_hub.js`) → `enc_data` 콜백, `batch_key` 발급 / `POST /gw/hub/v1/payment` 청구.
  → **교체 이유: KCP 가 구독(정기)결제를 지원하지 않는다고 회신.**
- **NicePay 포스타트(NEW v2 REST) 빌링 — 2026-06 (현재)** — 결제창 없이 카드 입력 폼 → 서버 AES 암호화
  `encData` → `POST /v1/subscribe/regist`(bid) + `/payments`(tid). Basic 인증, 동기 `resultCode`(웹훅 불필요),
  `classifyNicepayError` 에러 분류. 카드 원문이 서버를 경유해 **PCI SAQ A-EP 범위 진입**(§9).
