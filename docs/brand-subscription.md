# Brand Subscription — 설계

> **상태:** **Phase 1~4 + Phase 5 어드민 운영 도구 구현 완료.**
> - Phase 1 (결합 트랜잭션): `POST /v1/brand/subscription/start` 가 빌링키 발급 + 첫 결제 + 자동 입점 승인
> - Phase 2 (노출 게이트): `PURCHASABLE_PRODUCT_WHERE` 3분기 (가입 brand 의 active 구독 / 어드민 brand 면제 / legacy 통과)
> - Phase 3 (셀프 관리): `/settings/subscription` 페이지 + `GET / cancel / change-card` endpoint
> - Phase 4 (정기 청구): 일일 KST 자정 cron + dunning(0/1/3/7일, 4회 정책) + 어드민 progress bar
> - Phase 5 일부 (운영 도구): `/admin/brand-subscriptions` 어드민 페이지 + 강제 해지 + 강제 환불(토스 cancel API) + 정책 위반 차단(brand reject + 구독 자동 종료 묶음)
> - **남은 Phase 5:** webhook (`/webhooks/subscription/toss`) + 세금계산서 + 운영자 알림 채널 (Slack/이메일)
>
> 본 문서는 결정이 굳어질 때마다 섹션을 보강해나가는 **살아있는 설계 문서**다. 토스페이먼츠 빌링키 + 단일 플랜(₩30,000/월) + 입점 신청과 결제의 결합으로 운영된다.

---

## Context & 결정 배경

klow_brand 에 "브랜드가 자기 입점 멤버십을 매달 결제" 하는 **구독(SaaS 형태) 기능**을 추가한다. 결제는 단순 부가 기능이 아니라 **판매 활성화의 게이트** 다 — 결제가 없으면 노출도 판매도 되지 않는다.

- **결제 대상:** 국내 브랜드만 (KRW). 해외 브랜드 구독은 현 단계 범위 밖.
- **결제 주체:** `BrandUser` (전화번호+SMS OTP / 이메일 / Google 어떤 방식으로 가입했든 동일) — `Brand` 자체가 아니다. BrandUser 는 자기 `brandId` 와 묶여 있으므로 결제 영수증·계약은 `Brand` 단위로 발행.
- **klow_web 결제(소비자 일회성 주문, 글로벌 카드, Eximbay) 와는 완전히 다른 도메인.**
  - 소비자 결제: 일회성, 글로벌 카드, 주문 단위, 환불 워크플로우 존재
  - 브랜드 구독: 정기결제(빌링키 기반), 국내 KRW, 멤버십 단위, dunning(연체 자동 재시도)·해지·청구서 워크플로우 필요
- 따라서 **PG·DB 모델·webhook·관리자 UI 모두 분리**한다.

### 왜 입점 신청과 결제를 묶는가

- **어드민 수동 승인 부담 제거.** 현재는 어드민이 `/admin/brand-applications` 에서 `approveApplication()` 을 직접 눌러야 판매가 열린다. 결제를 게이트로 두면 어드민 개입 없이 자동 승인.
- **무자격 신청자 자연 차단.** 결제 의사가 있는 브랜드만 자체 진입한다.
- **첫달 매출 즉시 확보.** 입점 = 결제 = 활성화 한 흐름.
- **정책 일관성.** 결제·노출·판매를 단일 게이트(`subscription.status='active'`)로 통일.

### ★ 기존 정책 변경 (Phase 2 완료)

> 기존 KLOW 는 "노출(공개 surface)은 rejected 만 차단, 구매(`isPurchasable`)는 approved-only" 의 **분리 정책** 이었음.
>
> 본 라운드에 **노출·판매 모두 단일 게이트로 통일** — `PURCHASABLE_PRODUCT_WHERE = PUBLIC_PRODUCT_WHERE` alias 의 OR 3분기:
> 1. **가입 brand** (`Brand.submittedById !== null`) — `BrandSubscription.status='active'` 동안만 통과
> 2. **어드민이 만든 brand** (`Brand.submittedById === null`) — 구독 무관 통과 (KLOW 자체 사입 제품)
> 3. **legacy** (`Product.brandId === null`) — 통과 (안전 통과)
>
> `CLAUDE.md` 의 Brand 입점 워크플로우 단락도 동기화 완료. `isPurchasable()` (cart/orders 의 in-memory 게이트) 도 동일 3분기로 갱신.

---

## 서버 공유 정책

> 핵심 질문이었던 "klow_web 과 같은 klow_server 인스턴스를 그대로 써도 되나?" 에 대한 답.

### 같은 서버 공유 — OK

- **라우팅 분리되어 있음**
  - 소비자: `/v1/*` (klow_server `main.ts` 글로벌 prefix, UserGuard)
  - 브랜드: `/v1/brand/*` (`brand-auth`, `brand-applications` 모듈, BrandGuard)
  - 구독 추가 시: `/v1/brand/subscription/*` + `/webhooks/subscription/toss` 로 같은 prefix 아래 추가하면 충돌 없음
- **세션 쿠키 분리되어 있음**
  - 소비자: `klow_sid`
  - 브랜드: `klow_brand_sid` (7일 TTL, 독립 도메인 정책)
- **CORS 이미 두 origin 수용** — `klow_web:3001`, `klow_brand:3002` 모두 `localhost:*` regex 로 통과 (`klow_server/src/main.ts`)
- **DB 도 같이 써도 안전** — Prisma 스키마에 새 테이블 추가만 하면 됨. 기존 `Order` 와 FK 충돌 없음.

### 결제 모듈은 분리

현재 `klow_server/src/modules/payment/` (Eximbay) 는 다음 가정 위에 짜여있다:

- `transaction_type='PAYMENT'` (일회성 전용, recurring 모드 없음)
- `Order` 모델을 1:1 로 가정한 `markPaid` 단일 상태 전이
- 단일 webhook `POST /webhooks/eximbay` 가 consumer `order_id` 형식 가정

자세한 흐름은 [`payment-integration.md`](./payment-integration.md) 참고.

구독을 여기에 얹으면 webhook 라우팅·상태 enum·환불 흐름이 전부 꼬인다. → **새 모듈 `klow_server/src/modules/subscription/` 으로 분리** (아래 [서버 모듈 구조](#서버-모듈-구조) 참고).

---

## PG 결정: 토스페이먼츠 빌링키

국내 KRW 정기결제 → **토스페이먼츠 자동결제(빌링키)** 로 확정.

### 왜 토스 빌링키인가

- **SDK + 자동결제 승인 API 가 분리되어 있음** — 빌링키 발급(SDK) 과 매월 결제 호출(서버) 의 책임이 분리되어 자체 스케줄러 구현이 자연스럽다.
- **한국 카드 자동결제 표준** — 전 카드사 커버리지, 도큐먼트·SDK 가 정돈되어 있음.
- **본 도메인 모델과 정합** — `SubscriptionInvoice.pgTid = paymentKey` 멱등 키로 자연스럽게 매핑.
- **테스트 키로 통합 가능** — 운영 계약 전에도 빌링키 발급/승인/취소 전 흐름을 테스트 머천트로 검증 가능.

### 계약 트랙 분리

자동결제는 **추가 리스크 검토 + 계약 필요** 하다 (토스 영업팀 별도 신청). 운영 배포 전에 영업 트랙으로 진행해야 하므로, 본 문서의 구현 작업과 병렬로 계약 트랙을 시작해두는 게 좋다.

### 키와 인증

- `TOSS_BILLING_CLIENT_KEY` — 브라우저 SDK 용 (publishable)
- `TOSS_BILLING_SECRET_KEY` — 서버 전용
- 서버 API 호출 시 `Authorization: Basic base64("{secretKey}:")` 형식. **시크릿 키 뒤에 콜론 포함** 후 base64 인코딩 (토스 규칙).

---

## 요금제

- **단일 플랜 / 월 ₩30,000 (KRW) / VAT 포함 표시 (잠정)**
- **무료 체험 없음** — 가입·심사 직후 즉시 결제
- **결제 주기:** 매월, 최초 결제일 기준 같은 날 (예: 1/15 첫 결제 → 2/15, 3/15 …)
- **단일 플랜이므로 `SubscriptionPlan` 테이블을 생성하지 않는다.** 코드 상수 + 환경변수로 시작:
  - `SUBSCRIPTION_MONTHLY_PRICE_KRW=30000`
  - `SUBSCRIPTION_PLAN_CODE=brand_standard`
  - `SUBSCRIPTION_ORDER_NAME_PREFIX=KLOW 브랜드 멤버십`
  - 추후 멀티 플랜 시 테이블로 분리한다 (premature abstraction 회피).

---

## 도메인 모델

> 모두 신규 Prisma 모델. 기존 `Order` / `OrderItem` 은 손대지 않는다.

```prisma
// 브랜드의 구독 인스턴스
model BrandSubscription {
  id                 String                  @id @default(cuid())
  brandId            String                  @unique           // 1 brand = 1 active subscription
  planCode           String                  @default("brand_standard")
  status             BrandSubscriptionStatus
  currentPeriodStart DateTime
  currentPeriodEnd   DateTime
  cancelAtPeriodEnd  Boolean                 @default(false)
  canceledAt         DateTime?
  billingKeyId       String?
  createdAt          DateTime                @default(now())
  updatedAt          DateTime                @updatedAt

  brand      Brand                 @relation(fields: [brandId], references: [id])
  billingKey BillingKey?           @relation(fields: [billingKeyId], references: [id])
  invoices   SubscriptionInvoice[]

  @@index([status])
  @@index([currentPeriodEnd])
}

// PG 가 발급한 빌링키 (카드 토큰)
model BillingKey {
  id           String    @id @default(cuid())
  brandId      String
  provider     String    @default("toss")
  pgBillingKey String    @unique               // 평문 저장 — 토큰 자체로 customerKey 없이는 결제 불가
  cardCompany  String?
  cardLast4    String?   @db.VarChar(4)
  isDefault    Boolean   @default(true)
  createdAt    DateTime  @default(now())
  deletedAt    DateTime?

  brand         Brand               @relation(fields: [brandId], references: [id])
  subscriptions BrandSubscription[]

  @@index([brandId])
}

// 청구서 (매 결제 사이클마다 1건 생성). 멱등 키 = pgTid (토스 paymentKey).
model SubscriptionInvoice {
  id             String                    @id @default(cuid())
  subscriptionId String
  amountKrw      Int
  status         SubscriptionInvoiceStatus @default(pending)
  pgProvider     String?
  pgTid          String?                   @unique
  periodStart    DateTime
  periodEnd      DateTime
  attemptCount   Int                       @default(0)        // dunning 재시도 횟수 (Phase 4)
  lastAttemptAt  DateTime?
  paidAt         DateTime?
  failReason     String?                   @db.VarChar(500)
  createdAt      DateTime                  @default(now())

  subscription BrandSubscription @relation(fields: [subscriptionId], references: [id])

  @@index([subscriptionId])
  @@index([status])
}

enum BrandSubscriptionStatus {
  active
  past_due
  canceled
}

enum SubscriptionInvoiceStatus {
  pending
  paid
  failed
  refunded
}
```

> **enum vs string 선택:** 다른 status 필드 (`BrandStatus`, `ProductStatus`, `OrderStatus`, `PaymentStatus`) 가 모두 enum 인 일관성 + DB 레벨 검증을 위해 enum 채택. 단일 플랜 정책상 추가 status 가 거의 없을 것이라 enum 추가 부담도 작음.

기존 모델 영향:

- `Brand` 에 다음 추가·변경:
  - 역방향 relation `subscription BrandSubscription?` (옵셔널)
  - **`tossCustomerKey String? @unique`** 신규 — 토스 자동결제의 매핑 키, brand 1:1 영구 식별자
  - **`approvedById String?`** 로 ALTER (기존 non-null → nullable, 시스템 자동 승인 시 null 허용)
- `Order` / `Payment` / `OrderItem` 변경 없음
- **결제 상태 enum 을 공유하지 않는다.** 소비자 주문의 `pending|paid|failed|cancelled|refunded` 와 구독의 `active|past_due|canceled` 는 의미가 다르므로 enum/문자열을 분리해서 혼선 방지.

### 토스 customerKey 정책

- **소유 위치:** `Brand.tossCustomerKey` (BrandSubscription 이 아닌 Brand 에 둔다). 해지·재가입을 반복해도 같은 customerKey 를 재사용해야 토스 측 customer history 가 이어진다.
- **생성 시점:** **`POST /v1/brand/applications/submit-for-review` 응답에서 null 이면 즉시 발급해 박는다** (Stage 1 보다 한 단계 앞). 응답 DTO 에 `tossCustomerKey` 를 포함해 클라에 전달 → 클라가 `tossPayments.payment({ customerKey })` 초기화에 사용. 한 번 박힌 뒤로는 변경 금지.
- **카드 변경:** 새 빌링키 발급 시에도 customerKey 는 동일. 토스 입장에서 "같은 customer 의 다른 카드".
- **형식:** UUID v4 (36자, 영숫자+하이픈) — 토스 규격(영문대소+숫자+`-_=.@`, 2~300자) 통과. 추측 불가능해야 함 (BrandUser email/phone 같은 유추 가능 값 절대 사용 금지 — 공식 문서 권고).

### 노출/판매 게이트 코드 영향 (Phase 2 — 실 구현)

`klow_server/src/modules/products/product-selects.ts`:

```ts
export const PURCHASABLE_PRODUCT_WHERE = {
  status: ProductStatus.approved,
  OR: [
    // (1) 가입 brand — 구독 active 필요
    {
      brandRef: {
        is: {
          status: BrandStatus.approved,
          submittedById: { not: null },
          subscription: { is: { status: BrandSubscriptionStatus.active } },
        },
      },
    },
    // (2) 어드민이 만든 brand — 구독 무관 (KLOW 자체 사입)
    {
      brandRef: {
        is: {
          status: BrandStatus.approved,
          submittedById: null,
        },
      },
    },
    // (3) legacy 안전망
    { brandId: null },
  ],
};
export const PUBLIC_PRODUCT_WHERE = PURCHASABLE_PRODUCT_WHERE;
```

`isPurchasable()` 도 동일 3분기로 in-memory 검증. **호출처 (cart/orders) 의 `brandRef` include 에 `submittedById` + `subscription { status }` 까지 select 보강 필수** — 안 되면 isPurchasable 의 type 가드가 깨짐.

**결과:** 가입 brand 의 `subscription is null` (결제 미완료) 또는 `status='past_due'` (연체) 모두 노출·판매 차단. 어드민이 만든 brand 의 제품은 구독 무관 노출/판매 가능 (KLOW 자체 사입 케이스).

---

## 서버 모듈 구조

실제 구조 (단일 디렉토리, providers/controllers/webhooks/cron 서브폴더 없음 — 오버엔지니어링 회피):

```
klow_server/src/modules/
├── payment/                  ← (기존) consumer 일회성 결제, 손대지 않음
├── orders/                   ← (기존) consumer 주문, 손대지 않음
├── brand-applications/       ← (기존) approveApplication 시그니처 확장 + submitForReview 멱등 정책 변경
│   └── public-brand-applications.controller.ts  (어드민 컨트롤러는 subscription 모듈로 이전)
└── subscription/
    ├── subscription.module.ts
    ├── subscription.service.ts              // 도메인 로직 (start/getMine/cancelByOwner/changeCard/runDueBilling/chargeOne/forceCancel/refundInvoice 등)
    ├── toss-billing.adapter.ts              // 토스 API 래퍼 (request() private helper + issueBillingKey/chargeBilling/cancelPayment/deleteBillingKey)
    ├── brand-subscription.controller.ts     // @Controller('v1/brand/subscription') + BrandGuard
    ├── admin-subscription.controller.ts     // @Controller('admin/brand-subscriptions') + AdminGuard
    └── subscription-billing.cron.ts         // @Cron('0 0 * * *', { timeZone: 'Asia/Seoul' }) → runDueBilling 위임
```

> **단일 service 패턴 선택 이유:** Phase 1~5 의 모든 service 메서드 (start/getMine/cancel/changeCard/forceCancel/refundInvoice/runDueBilling/chargeOne/listSubscriptions/getSubscriptionDetail) 가 SubscriptionService 한 클래스에 모임 (~600줄). billing-key.service / invoice.service 분리는 메서드가 더 늘면 검토.

### 엔드포인트

**Brand 측 (`BrandGuard`, prefix `/v1/brand/subscription`):**

| 메서드·경로 | 역할 | 상태 |
|---|---|---|
| `POST /start` | 토스 `authKey` → 빌링키 교환 + 최초 결제(₩30,000) + `approveApplication()` 자동 호출. 신규/재가입 처리 | ✅ |
| `GET /` | 자기 구독 + billingKey + 최근 12 invoices | ✅ |
| `POST /cancel` | `cancelAtPeriodEnd=true` (현재 사이클 끝까지 active 유지, cron 이 만료 시 canceled 로 전환) | ✅ |
| `POST /change-card` | 새 빌링키 발급 + 기존 키 soft delete + 토스 키 삭제. past_due 면 즉시 1회 재시도해 active 복귀 시도 | ✅ |

**Admin 측 (`AdminGuard` + `AdminAuditInterceptor`, prefix `/admin/brand-subscriptions`):**

| 메서드·경로 | 역할 | 상태 |
|---|---|---|
| `GET /` | 구독 목록 — status 필터 (active/past_due/canceled/none/rejected) + paging | ✅ |
| `GET /:id` | brand + subscription(billingKey + 모든 invoices) + products + submittedBy | ✅ |
| `PATCH /:id/reject` | **정책 위반 차단** — `brand.status='rejected'` + 활성 구독 있으면 자동 `forceCancelIfActive` 같이 호출. 환불 없음 (분쟁 환불은 별도) | ✅ |
| `PATCH /:id/force-cancel` | 단순 강제 해지 — 구독만 즉시 canceled. brand.status 는 그대로. 환불 없음 | ✅ |
| `PATCH /:id/invoices/:invoiceId/refund` | 분쟁 환불 — 토스 cancel API 호출 + invoice refunded + 구독 canceled | ✅ |
| `PATCH /:id/products/:productId/approve` | 제품 단위 차단 해제 | ✅ |
| `PATCH /:id/products/:productId/reject` | 제품 단위 차단 | ✅ |

**Webhook (`POST /webhooks/subscription/toss`)** — 미구현 (Phase 5). Stage 2↔3 사고 복구 채널 + 정기 결제 결과 1차 신호 겸용.

**Cron (`subscription-billing.cron.ts`)** — `@Cron('0 0 * * *', { timeZone: 'Asia/Seoul' })` 일일 KST 자정, `runDueBilling` 위임.

### 사전 조건 가드 (`start` 진입 전)

`POST /v1/brand/subscription/start` 는 다음 조건을 모두 만족할 때만 통과:

- **(`Brand.status='pending'` && `subscription is null`)** — 신규 결제 케이스
- 또는 **(`Brand.status='approved'` && `subscription.status='canceled'`)** — 재가입 케이스. 해지 시 Brand.status 는 그대로 `approved` 유지되고 `BrandSubscription.status` 만 `canceled` 로 전이되므로 이 조합이 정상.
- 그 외 모든 케이스 차단: `draft|rejected`(먼저 submitForReview 통과 필요), `withdrawal_pending|withdrawn`(탈퇴 진행 중), `subscription.status='active'`(이미 결제 중 → 409), `subscription.status='past_due'`(dunning cron 이 처리)
- **OnboardingGate 7필드 모두 `trim()` 후 non-empty** (`klow_brand/src/components/studio/OnboardingGate.tsx` L41-49 와 `klow_server/src/common/validation.ts` 의 `BrandSubmitForReviewInputT` 가 동일 규칙 적용):
  - 송화인 4: `senderName`(40자), `senderAddress`(200자), `senderPostalCode`(10자), `senderMobile`(KR 폰 정규식 — `klow_brand/src/lib/phone.ts` 의 `isValidKrPhone`, `010-XXXX-XXXX` 형태)
  - 계좌 3: `bankName`(40자), `bankAccountHolder`(40자), `bankAccountNumber`(40자, `/^[0-9-]+$/`)
- 미달 시 `400 brand_not_ready_for_payment` + 비어있는 필드 목록을 응답에 명시 (어드민·디버그용)

**Brand 의 다른 필드는 결제 게이트 아님.** `name`, `slug`, `logoUrl`, `description`, `tagline`, `accentColor`, `homepageUrl`, `targetCountries` 등은 결제 시점에 비어있어도 결제 가능. 결제 후 활성화된 상태에서 BrandTab/DesignTab 등으로 채워나가는 흐름. **OnboardingGate 의 7필드만이 결제 자격의 게이트.**

**검증 일관성:** OnboardingGate 의 클라 검증과 서버 `BrandSubmitForReviewInputT` 가 이미 동일한 7필드를 검증하므로, submit-for-review 가 통과한 brand 는 사실상 모두 이 가드를 통과한다. 가드는 방어선이지 1차 검증이 아님.

### Webhook 라우팅 분리 (중요)

- 기존: `POST /webhooks/eximbay` — consumer order 가정
- 신규: `POST /webhooks/subscription/toss`
- **두 webhook 절대 합치지 않는다.** 멱등 키·검증 정책·실패 처리 흐름이 다르다.

### 인증 가드

- 브랜드 API: 기존 `BrandGuard` 그대로 사용 (`klow_server/src/common/guards/brand.guard.ts`). 자기 `brandId` 에 묶인 구독·청구서만 조회 가능하도록 service 레벨에서 ownership 체크.
- 어드민 API: `AdminGuard` + `AdminAuditInterceptor` 로 강제 환불·해지를 자동 audit log 에 기록.

---

## 입점 신청 ↔ 구독 결제 통합 흐름

이 문서의 핵심 단락. 결제 모듈 자체보다도 **"submitForReview → 결제 → approveApplication 자동 호출"** 의 결합이 본 작업의 차별점이다.

### 현재 흐름 (변경 전)

```
OnboardingGate 입력 ─► submitForReview() ─► Brand.status='pending'
                                              ▼
                                            어드민이 /admin/brand-applications 에서
                                            approveApplication() 수동 호출
                                              ▼
                                            Brand.status='approved'
                                            (선택 Product.status='approved' 일괄)
```

### 신규 흐름 (시퀀스)

```
brand        klow_brand           klow_server                       Toss
 │              │                      │                              │
 │ OnboardingGate                      │                              │
 │ 폼 입력 ───► │                      │                              │
 │              │ ─POST submit-for-review─►                            │
 │              │                      │ Brand.status='pending'        │
 │              │                      │ tossCustomerKey 발급 (null이면)│
 │              │ ◄─ {brand, tossCustomerKey} ─                        │
 │              │ 결제 안내 화면        │                              │
 │              │ ─requestBillingAuth({customerKey}) ─────────────────►│
 │              │ ◄────── successUrl?authKey&customerKey ──────────────│
 │              │ ─POST subscription/start {authKey,customerKey}─►     │
 │              │                      │ ┌─ Stage 1 (DB read) ─────┐  │
 │              │                      │ │ 사전 조건 가드 +         │  │
 │              │                      │ │ customerKey 일치 검증    │  │
 │              │                      │ │ orderId = sha256(authKey)│  │
 │              │                      │ └─────────────────────────┘  │
 │              │                      │ ┌─ Stage 2 (tx 밖) ────────┐ │
 │              │                      │ │ POST /v1/billing/       │ │
 │              │                      │ │   authorizations/issue ─┼─►│
 │              │                      │ │ ◄─ billingKey ──────────┼──│
 │              │                      │ │ POST /v1/billing/{key}  │ │
 │              │                      │ │   amount:30000 ─────────┼─►│
 │              │                      │ │ ◄─ status:DONE ─────────┼──│
 │              │                      │ └─────────────────────────┘  │
 │              │                      │ ┌─ Stage 3 (단일 tx) ──────┐ │
 │              │                      │ │ BillingKey create       │ │
 │              │                      │ │ Subscription upsert     │ │
 │              │                      │ │  (active, period)       │ │
 │              │                      │ │ Invoice create (paid,   │ │
 │              │                      │ │   pgTid=paymentKey)     │ │
 │              │                      │ │ approveApplication({    │ │
 │              │                      │ │   actor:{type:'system'}})│ │
 │              │                      │ │ → Brand=approved        │ │
 │              │                      │ │   Product=approved      │ │
 │              │                      │ │ return brand 직접 ──────┐ │
 │              │                      │ └────────────────────────│┘ │
 │              │ ◄─ {subscription, brand.status='approved'} ─         │
 │              │ → /studio + 활성화 토스트                            │
 │              │                      │ ◄─ /webhooks/subscription/toss ─│ (보조: 멱등 무시)
```

### 트랜잭션 단위 — 외부 호출 분리 패턴

**PG 호출은 절대 DB 트랜잭션 안에서 하지 않는다.** 외부 API 응답 대기로 트랜잭션이 길어지면 DB 락 + connection 풀 고갈 + timeout 시 unknown state 위험. `start` 의 실행은 3단계로 명확히 분리한다.

**Stage 1 — 사전 조건 + customerKey 일치 (DB read only)**

- 사전 조건 가드 (status 분기 + 7필드) 통과 확인
- `Brand.tossCustomerKey` 가 클라가 보낸 `dto.customerKey` 와 정확히 일치하는지 검증 (불일치 시 BadRequest)
- 정상 흐름에선 [`submit-for-review` 응답 시 customerKey 가 이미 발급](#토스-customerkey-정책) 되어 있다. null 이면 BadRequest (submit-for-review 누락 케이스)

**Stage 2 (트랜잭션 밖) — 토스 PG 호출 순차 2건**

- `orderId = sha256(authKey).slice(0, 32)` 미리 계산
- `POST /v1/billing/authorizations/issue` ({authKey, customerKey} → billingKey 교환)
- `POST /v1/billing/{billingKey}` ({customerKey, amount: 30000, orderId, orderName}) — 자동결제 승인
- 응답이 `status='DONE'` 인 경우만 Stage 3 진입. 그 외(에러)는 [결제 실패 시 정책](#결제-실패-시-정책-최초-결제) 분기.
- **`orderId` 가 `sha256(authKey)`** — authKey 는 일회성 + unique 이므로 같은 호출이 두 번 도달해도 토스가 `DUPLICATED_ORDER_ID` 로 멱등 처리해 이중 결제 차단. 사용자 더블탭 / React Strict-Mode 의 effect 더블 발화 양쪽 방어.

**Stage 3 (단일 짧은 Prisma 트랜잭션) — DB 일괄 생성·전이**

- `BillingKey` create (`isDefault=true`, `provider='toss'`)
- `BrandSubscription` upsert (`brandId @unique` 가 멱등 키): `status='active'`, `currentPeriodStart=now`, `currentPeriodEnd=now+1month`, `billingKeyId`
- `SubscriptionInvoice` create with `status='paid'`, `pgTid=paymentKey`, `paidAt=now` — 사전 insert 없음. **결제 실패 시 DB 에 아무 row 도 만들지 않는다** (Stage 3 진입 전에 throw → 깨끗한 재시도)
- `approveApplication({ brandId, actor: { type: 'system', reason: 'subscription_started' }, tx })` — 같은 트랜잭션 안에서 호출되어 `Brand.status='approved'` + 선택 `Product.status='approved'` 일괄 전이
- 트랜잭션 callback 의 return 값으로 최신 brand (`include: { subscription: { include: { billingKey } } }`) 를 직접 반환 — 트랜잭션 밖 별도 fetch round-trip 불필요

### 멱등성 보장

- **`orderId = sha256(authKey).slice(0, 32)`** — Stage 2 의 토스 호출이 deterministic 한 orderId 를 갖는다. 사용자가 더블탭하거나 return 페이지가 React Strict-Mode 로 effect 를 두 번 돌려도 토스가 `DUPLICATED_ORDER_ID` 로 막아 이중 결제 차단. authKey 는 일회성 + unique.
- **`BrandSubscription.brandId @unique`** — 같은 brand 의 동시 두 번 호출 시 Stage 3 의 upsert 가 직렬화 → 두 번째는 conflict 또는 no-op.
- **`start` 진입 시 상태별 분기:**
  - `subscription is null` (최초 결제) → Stage 1~3 정상 진행
  - `status='active'` → `409 subscription_already_active` (재호출 차단)
  - `status='canceled'` → 같은 row 의 `status`, `currentPeriodStart/End`, `canceledAt`, `cancelAtPeriodEnd`, `billingKeyId` 를 모두 갱신해 신규 사이클로 복귀
  - `status='past_due'` → `start` 직접 호출 차단. 사용자가 카드를 바꾸면 dunning cron 이 다음 사이클에서 자동 재시도해 `active` 로 복귀.

### Stage 2 ↔ Stage 3 사이의 사고

토스 결제 성공(DONE) 직후 Stage 3 가 실패하는 경우(서버 크래시·DB 일시 장애)가 가장 위험한 시나리오. 방어는 두 줄로 충분:

- **Stage 2 응답의 `paymentKey` 를 DB write 전에 구조화 로그로 남긴다** → 운영자가 사후 추적 가능
- Stage 3 는 짧은 쿼리만이라 실패율 매우 낮음. 발생 시 Phase 5 의 webhook 핸들러가 같은 `paymentKey` 에 대해 Stage 3 만 멱등 재실행해 회수한다 (webhook 이 결과적으로 retry 채널)

### `approveApplication()` 새 시그니처 (확정)

**변경 전 (현재 코드 — `klow_server/src/modules/brand-applications/brand-applications.service.ts` L438):**

```ts
async approveApplication(params: { brandId: string; adminId: string }) { ... }
// trx: Brand.update({ status:'approved', approvedAt, approvedById: adminId })
//      Product.updateMany({ where:{brandId, status:'pending'}, data:{ status:'approved' } })
```

**변경 후:**

```ts
type ApproveActor =
  | { type: 'admin'; adminId: string }
  | { type: 'system'; reason: 'subscription_started' };

async approveApplication(params: {
  brandId: string;
  actor: ApproveActor;
  tx?: Prisma.TransactionClient;   // start() 가 자기 트랜잭션 안에서 호출할 때 주입
}) {
  // brand.update({
  //   status:'approved', approvedAt:now,
  //   approvedById: params.actor.type === 'admin' ? params.actor.adminId : null,
  //   rejectionReason: null,
  // })
  // product.updateMany({ where:{ brandId, status:'pending' }, data:{ status:'approved' } })
}
```

**Prisma 스키마 변경:** `Brand.approvedById` 를 nullable 로 ALTER (단순 마이그레이션, 데이터 손실 없음).

**호출처 두 곳:**

- 어드민 UI: `admin-brand-applications.controller.ts` → `actor: { type: 'admin', adminId: req.admin.id }`
- 구독 결제 성공: `subscription.service.ts` 의 `start()` Stage 3 → `actor: { type: 'system', reason: 'subscription_started' }, tx: subscriptionTx`

**audit log 표기:** `AdminAuditInterceptor` 는 어드민 컨트롤러에서만 작동하므로 시스템 액터 호출은 자동 audit 에 안 잡힌다. `subscription.service.ts` 내부에서 구조화 로그(`console.info({ event: 'brand_auto_approved', brandId, paymentKey })`)로 남기고, Phase 5 에서 별도 `SystemAuditLog` 테이블 도입 검토.

### `submitForReview()` 멱등 정책 변경

현재 코드(`brand-applications.service.ts` L209)는 `draft|rejected` 에서만 통과하고 `pending` 은 `BadRequestException` 을 던진다. 결제 실패 후 사용자가 정보(주소·계좌 등)를 수정하려고 다시 제출하면 막힘. 다음과 같이 완화:

| 진입 시 `Brand.status` | 현재 동작 | **변경 후 동작** |
|---|---|---|
| `draft` | status→pending + 필드 저장 | 동일 (그대로) |
| `rejected` | status→pending + 필드 저장 + rejectionReason clear | 동일 (그대로) |
| **`pending` && `subscription is null`** | `BadRequestException` | **필드 저장만, status 전이 없음** (재제출로 정보 수정) |
| `pending` && active 구독 있음 | `BadRequestException` | 동일 (있을 수 없는 케이스이지만 방어) |
| `approved|withdrawal_pending|withdrawn` | `BadRequestException` | 동일 |

**OnboardingGate 의 `needsOnboarding()` 도 같이 확장:**

```ts
export function needsOnboarding(
  brand: BrandDTO,
  subscription: BrandSubscriptionDTO | null,   // 새 인자
): boolean {
  if (brand.status === 'draft' || brand.status === 'rejected') return true;
  if (brand.status === 'pending' && !subscription) return true;  // 결제 미완료 → 정보 수정 가능
  return false;
}
```

→ 결제 미완료 brand 가 주문/배송 탭 또는 정산 탭에 다시 들어가면 OnboardingGate 가 prefill 된 상태로 다시 노출되어 수정 + 재저장 가능. 저장 후 상단에 결제 진입 CTA 가 같이 떠야 한다 ([klow_brand UI 진입점](#klow_brand-ui-진입점) 참조).

### 결제 실패 시 정책 (최초 결제)

`start` 트랜잭션이 PG 에러로 실패하면 트랜잭션 롤백, Brand 는 `pending` 그대로. **자동 거부 없음** → 사용자 재시도 유도.

토스 자동결제 승인 API 에러 코드 분기 (공식 문서 기준):

| 분류 | HTTP | 대표 코드 | 사용자 안내 |
|---|---|---|---|
| **영구 실패 (카드 자체)** | 400 | `INVALID_CARD_NUMBER`, `INVALID_CARD_EXPIRATION`, `INVALID_STOPPED_CARD`, `INVALID_REJECT_CARD`, `INVALID_BILL_KEY_REQUEST` | "카드를 변경해주세요" + 카드 등록 화면으로 |
| **일시 실패 (재시도 가능)** | 403 | `REJECT_CARD_PAYMENT` (한도/잔액), `REJECT_ACCOUNT_PAYMENT`, `REJECT_CARD_COMPANY`, `EXCEED_MAX_AUTH_COUNT` | "잠시 후 다시 시도해주세요" + 카드사 문의 권고 |
| **PG 일시 오류** | 500 | `FAILED_CARD_COMPANY_RESPONSE`, `FAILED_INTERNAL_SYSTEM_PROCESSING` | "PG 일시 오류, 잠시 후 재시도" |

이 분류는 [정기 결제 dunning](#정기-결제-2회차-이후-실패--dunning) 의 자동 재시도 정책과 동일한 기준으로 사용한다.

### 정기 결제 cron 동작 (Phase 4 — 실 구현)

**`subscription-billing.cron.ts`** — 일일 KST 00:00 실행, `runDueBilling()` 호출. 참고 패턴: `brand-withdrawals.service.ts` 의 `@Cron('0 3 * * *', { timeZone:'Asia/Seoul' })`.

#### `runDueBilling()` 3 대상 분리

```ts
const chargeReady = {
  billingKeyId: { not: null },
  brand: { tossCustomerKey: { not: null } },
};

const [dueActive, pastDue] = await Promise.all([
  prisma.brandSubscription.findMany({
    where: { status: 'active', currentPeriodEnd: { lte: now }, ...chargeReady },
    include: { billingKey: true, brand: true, invoices: { orderBy:{createdAt:'desc'}, take: 1 } },
  }),
  prisma.brandSubscription.findMany({
    where: { status: 'past_due', ...chargeReady },
    include: subInclude,
  }),
]);
```

분기:
1. **갱신** — `dueActive.filter(s => !s.cancelAtPeriodEnd)` → `chargeOne(s)`
2. **종료** — `dueActive.filter(s => s.cancelAtPeriodEnd)` → 결제 안 함, `status='canceled', canceledAt=now()`
3. **dunning 재시도** — `pastDue.filter(s => lastAttemptAt + retryGap(attemptCount) <= now)` → `chargeOne(s)`

각 brand 는 `Promise.allSettled` 격리 — 한 brand 실패가 cron 전체 막지 않음.

#### `chargeOne(sub: ChargeOneInput)` 시그니처

cron 의 N+1 reload 회피를 위해 시그니처가 **brandId 가 아니라 이미 로드된 sub 객체**:

```ts
type ChargeOneInput = BrandSubscription & {
  billingKey: BillingKey | null;
  brand: Brand;
  invoices: SubscriptionInvoice[];   // 최근 1건 (재시도 invoice 재사용용)
};
```

흐름:
1. 활성(failed) invoice 가 있으면 재사용 (재시도), 없으면 새 pending invoice insert (갱신)
2. `orderId = sha256(invoice.id).slice(0, 32)` 멱등키
3. tx 밖에서 `toss.chargeBilling()`
4. **성공 (DONE)** — 단일 tx 로 invoice paid + subscription active + 사이클 갱신
5. **실패 (`TossBillingError`)** — invoice `failed` + attemptCount++ + lastAttemptAt + failReason. subscription → `past_due` (이미 past_due 인 경우 유지)

#### retryGap 표

| 이전 `attemptCount` | 다음 시도까지 gap |
|---|---|
| 0 → 1 | 즉시 (다음 cron 도래 시) |
| 1 → 2 | 1일 |
| 2 → 3 | 3일 |
| 3 → 4 | 7일 |
| 4+ | 재시도 없음 (`past_due` 확정) |

`permanent` 분류 (카드 자체 문제) 는 분류 구분 없이 attemptCount 만 보고 재시도. 4회 안에 active 복귀 못 하면 운영자가 force-cancel 로 정리.

#### 사용자 카드 교체 → 즉시 복귀

`POST /v1/brand/subscription/change-card` 호출 시 service 가 새 빌링키 설정 후 `past_due` 였다면 **즉시 1회 `chargeOne` 재시도**. 성공 시 다음 cron 까지 안 기다리고 active 복귀.

### 라이프사이클 운영

- **카드 변경:** `POST /v1/brand/subscription/change-card` 호출 → 새 빌링키 발급 → `BillingKey` row 교체 → 기존 키는 토스 빌링키 삭제 API 호출 + soft delete. 다음 결제일에 새 카드로 자동 사용.
- **해지:** `cancel` → `cancelAtPeriodEnd=true` → 현재 사이클 끝까지 active → 만료 시 `canceled`. **현재 사이클 동안은 노출·판매 유지**, 만료 직후 게이트가 자동 차단. 환불 없음.
- **재가입:** 해지된 brand 가 다시 `start` 호출 → 새 사이클로 active. `approveApplication` 은 이미 approved 면 no-op (멱등).

---

## 토스 webhook 통합

### 이벤트 구독

- **`PAYMENT_STATUS_CHANGED` 하나만 구독한다.** 빌링키 삭제 권한은 우리 서버에만 있으므로 `BILLING_DELETED` 는 불필요.

### 검증 정책 (중요)

토스는 **공식적으로 webhook 서명 헤더를 제공하지 않고 발신 IP allowlist 도 공개하지 않는다.** 따라서:

- **webhook body 만 믿지 않는다.** 도착 시 반드시 `GET /v1/payments/{paymentKey}` 로 토스 조회 API 를 재호출해 신뢰.
- 멱등 키 = `paymentKey` (= `SubscriptionInvoice.pgTid`). 이미 처리된 `paymentKey` 는 200 응답 후 무시.
- 멱등성과 조회 재검증이 곧 보안 모델이다. 임시 토큰이나 자체 서명은 운영 단계에서도 추가하지 않는다.

### 응답 / 재시도

- **10초 이내 200 응답 필수**
- 5xx 또는 timeout 시 토스가 자동 재시도: 1m → 4m → 16m → 64m → 256m → 1024m → 4096m (총 7회, 약 3일 19시간)
- 별도 자체 큐 불필요 — 토스 재시도 + 일일 cron polling 으로 2중 안전망 충분

### 활용 위치

- **최초 결제 (`start`):** API 응답이 동기적으로 결제 결과를 반환 → webhook 은 보조 채널 (멱등 처리만)
- **정기 결제 (2회차+):** cron 이 결제 호출 → webhook 이 결과 1차 신호. cron 후속 polling 으로 보강.

### 로컬 테스트

토스 webhook URL 등록은 개발자센터의 "웹훅" 메뉴에서. 로컬 개발 시 `ngrok` 등 터널링이 필요하다.

---

## 환불 정책 & 토스 cancel API

### 기본 정책: 환불 없음

- 월중 해지 시 **사이클 만료 시점까지 사용 후 자동 종료** (`cancelAtPeriodEnd=true`)
- 단일 ₩30,000 플랜이라 일할 정산·세금 계산 부담 대비 가치 낮음

### 운영 예외 환불 경로 (구현 완료)

분쟁·고객 응대 등으로 예외 환불이 필요한 경우만 어드민이 사용:

- 엔드포인트: `PATCH /admin/brand-subscriptions/:id/invoices/:invoiceId/refund` (AdminGuard + AdminAudit)
- 내부적으로 토스 `POST /v1/payments/{paymentKey}/cancel` 호출
- body: `{ reason: string (1~200자), cancelAmount?: number }` — `cancelAmount` 생략 시 전액 환불
- 성공 시 단일 트랜잭션:
  - `SubscriptionInvoice.status='refunded'`
  - `BrandSubscription.status='canceled'`, `canceledAt=now` (사이클 만료 안 기다림)
  - 게이트가 자동으로 노출·판매 차단

세금계산서 처리는 Phase 5 운영 도구에서 다룸.

---

## 어드민 운영 도구 (`/admin/brand-subscriptions`)

기존 "브랜드 신청" 검수 큐가 **결제 = 자동 승인** 흐름 도입으로 의미를 잃어, 어드민의 책임이 **구독 관찰 + 정책 위반·분쟁 강제 종료** 로 재정의됨. 페이지·라우트·service 모두 `brand-subscriptions` 도메인으로 갈아엎음.

### 페이지 구조

- **List** (`/admin/brand-subscriptions`): brand row 카드. 상태 필터 chip 6종 (전체/구독중/연체/해지/결제 미완료/강제 차단). 각 row 에 **사이클 progress bar** (currentPeriodStart~End 사이 now 위치 시각화) + D-day + `cancelAtPeriodEnd=true` 면 "취소 예약" 라벨. 자동 결제 성공 시 currentPeriodStart 갱신 → progress 자연 리셋.
- **Detail** (`/admin/brand-subscriptions/:id`): 헤더 + 구독 패널 + 청구서 히스토리 테이블 (paid 행에 환불 버튼) + 위험 액션 패널 + 송화인/계좌 + 제품 리스트 (개별 차단/해제).

### 3가지 위험 액션 비교

| 액션 | 대상 | 효과 | 토스 호출 | 사용자 돈 |
|---|---|---|---|---|
| **정책 위반 차단** | Brand 자체 | `brand.status='rejected'` + **활성 구독 자동 종료**(forceCancelIfActive) | ❌ | 안 돌려줌 |
| **강제 해지** | Subscription | `status='canceled', canceledAt=now`. brand.status 그대로 | ❌ | 안 돌려줌 |
| **환불 (청구서 행)** | Invoice + Subscription | invoice `refunded` + subscription `canceled` | ✅ cancel API | 돌려줌 |

#### 정책 위반 차단 = brand reject + 자동 force-cancel 묶음

운영자 1클릭으로 brand 자격 박탈 + 구독 종료 + 다음 cron 결제 시도 차단. 분리해 두 액션을 누르게 강제하지 않고 한 묶음으로:

```ts
@Patch(':id/reject')
async reject(@Param('id') id, @CurrentAdmin() admin, @Body() body) {
  await this.brandAppsSvc.rejectApplication({ brandId: id, reason: body.reason });
  await this.subSvc.forceCancelIfActive({
    brandId: id, adminId: admin.id,
    reason: `정책 위반 차단: ${body.reason}`,
  });
  return this.subSvc.getSubscriptionDetail(id);
}
```

`forceCancelIfActive` 는 활성 구독 없거나 이미 canceled 면 silent skip — brand reject 만 진행. (명시적 `forceCancel` 은 구독 없을 때 BadRequest 던짐 — 직접 액션은 명확한 피드백 필요).

환불은 별도 의사결정 (분쟁 합의 시 청구서 환불 버튼).

---

## klow_brand UI 진입점

### 결제 진입점 — OnboardingGate 직후

`klow_brand/src/components/studio/OnboardingGate.tsx` 의 "저장" 버튼 클릭 후:

1. `submitForReview()` (또는 pending 재제출이면 정보 갱신만) 성공 응답을 받으면
2. 같은 화면 (또는 모달) 에서 토스 결제창 (`tossPayments.payment().requestBillingAuth`) 진입 CTA 노출
3. 카드 등록 → 토스 successUrl → `/studio/billing/return` 라우트에서 `POST /v1/brand/subscription/start` 호출
4. 응답 받으면 `/studio` 복귀 + "심사 통과! 판매가 시작됩니다" 토스트
5. **결제 실패 시:** 토스 에러 코드를 [결제 실패 시 정책](#결제-실패-시-정책-최초-결제) 분류표대로 안내 메시지 표시 + 같은 CTA 로 재시도 가능. brand 는 `pending` 그대로.

### 결제 미완료 상태로 이탈한 brand

- **`needsOnboarding(brand, subscription)` 가 `true`** (`pending` && `subscription=null`) → OnboardingGate 가 **prefill 된 채로 다시 노출** 되어 사용자가 송화인/계좌 정보를 수정·재저장 가능 ([submitForReview 멱등 정책 변경](#submitforreview-멱등-정책-변경) 참조).
- 폼 저장 후 같은 화면 상단(또는 IdlePanel 모든 탭 위) 에 결제 진입 CTA 배너 노출:
  - 문구: "결제를 완료해야 판매가 시작됩니다"
  - CTA → 결제 모달 진입 (위 1~4 단계 중 2번부터)

### 연체 brand (`subscription.status='past_due'`)

- 배너 문구: "결제가 처리되지 않았습니다. 카드를 확인해주세요."
- CTA → `/studio/billing/payment-methods` 에서 카드 교체 → dunning cron 이 다음 사이클에서 새 카드로 자동 재시도

### 셀프 구독 관리 (Phase 3 — 실 구현)

`/settings` 페이지에 **"구독 관리" 카드** 1개 (`SubscriptionLinkCard`) 추가 — 상태 뱃지 + 다음 결제일 + 카드 last4 요약. 카드 자체가 `<Link href="/settings/subscription">`.

`/settings/subscription` 전체 페이지 — **4 패널 구조**:

1. **구독 정보 패널**: planCode·월 결제액·시작일/다음 결제일·`cancelAtPeriodEnd=true` 면 강조 박스
2. **결제 카드 패널**: cardCompany + `****last4` + **[카드 변경]** 버튼 → 토스 SDK 재진입 (`requestBillingAuth({ successUrl: '/settings/subscription/return' })`)
3. **청구서 히스토리**: 최근 12 invoice 리스트 (날짜·금액·상태 뱃지)
4. **해지 패널** (`status='active'` && `!cancelAtPeriodEnd` 일 때만): **[해지 예약]** 버튼 → confirm → `api.subscription.cancel()`

`/settings/subscription/return` 라우트 — 카드 변경용 토스 successUrl. `useTossBillingReturn` 훅 (lib/toss-billing.ts) 으로 신규 결제 return (`/studio/billing/return`) 과 공통 흐름 공유.

> 기존 plan 의 `/studio/billing` 대시보드 메뉴 분리는 폐기. settings 페이지에 카드 1개 → 전체 페이지 1개 구조로 단순화.

### 클라이언트 헬퍼

`klow_brand/src/lib/api.ts` 의 `subscription.*` namespace:

- `subscription.start({ authKey, customerKey })` — 신규/재가입
- `subscription.get()` — 현재 상태 + 청구서 12건 (단일 endpoint 응답에 invoices 포함)
- `subscription.cancel()` — 사이클 만료 후 해지 예약
- `subscription.changeCard({ authKey, customerKey })` — 카드 교체

---

## 환경변수 & 보안

### 신규 환경변수

**`klow_server/.env`:**

```
TOSS_BILLING_API_BASE=https://api.tosspayments.com  # sandbox/live 동일 (키로만 구분)
TOSS_BILLING_CLIENT_KEY=test_ck_...                 # 브라우저 SDK (클라에 노출 OK)
TOSS_BILLING_SECRET_KEY=test_sk_...                 # 서버 전용, Basic base64("{key}:") 콜론 포함
SUBSCRIPTION_MONTHLY_PRICE_KRW=30000                # 미설정 시 코드 기본값 30000
SUBSCRIPTION_PLAN_CODE=brand_standard
SUBSCRIPTION_ORDER_NAME_PREFIX=KLOW 브랜드 멤버십
```

**`klow_brand/.env.local`:**

```
NEXT_PUBLIC_TOSS_BILLING_CLIENT_KEY=test_ck_...   # klow_server 의 CLIENT_KEY 와 동일 값
```

> 토스 자동결제용 키는 [개발자센터 > API 키](https://developers.tosspayments.com/my/api-keys) 에서 발급. **자동결제(빌링) 계약된 MID** 의 키여야 `NOT_SUPPORTED_METHOD` 에러를 피할 수 있다. 가입 전에도 문서 페이지의 공개 테스트 키로 테스트 가능.

### webhook 시크릿은 없다

토스가 서명 검증을 미제공하므로 환경변수에 webhook secret 항목이 없다. 멱등 + 토스 조회 API 재검증 모델이 보안 모델 자체다. ([토스 webhook 통합](#토스-webhook-통합) 참고)

### 빌링키와 PCI scope

- **빌링키는 평문 저장.** PG 가 발급한 토큰이고, 도용되어도 매핑된 `customerKey` 없이는 결제 불가. 추가 암호화는 키 노출 시 customerKey 도 같이 노출되므로 이중 방어 가치 낮음. admin TOTP secret(서버 단독으로 OTP 검증) 과 위협 모델 다름.
- **카드 번호는 절대 서버로 들어오지 않는다** — 토스 SDK 가 토스 도메인에서 입력받고 클라엔 `authKey` 만 온다. klow_server 는 `billingKey` 토큰만 다룸. PCI scope 밖.

---

## 단계별 마일스톤

### Phase 0 — 결정 (완료)

- [x] PG 확정 (토스페이먼츠 빌링키)
- [x] 요금제 구조·가격·플랜 수 확정 (단일, 월 ₩30,000)
- [x] 무료 체험 정책 (없음)
- [x] 환불 정책 (사이클 만료, 환불 없음)
- [x] 노출 게이트 정책 (구독 active 단일 게이트로 통일)
- [x] 결제 통합 시점 (입점 신청 직후 자동 승인 게이트)

### Phase 1 — 결합 트랜잭션 (★ 본 문서의 핵심) — **완료**

- [x] Prisma 마이그레이션 `brand_subscription_init`: `BrandSubscription` / `BillingKey` / `SubscriptionInvoice` 모델 + `Brand.tossCustomerKey @unique` + `BrandSubscriptionStatus` / `SubscriptionInvoiceStatus` enum (`Brand.approvedById` 는 이미 nullable 이어서 ALTER 불필요)
- [x] `submitForReview()` 멱등 정책 변경 + 응답에 `tossCustomerKey` 사전 발급
- [x] `approveApplication()` 새 시그니처 (`actor: ApproveActor`, `tx?: Prisma.TransactionClient` 주입, `approved` 멱등 처리)
- [x] `getMyApplication()` 응답에 `subscription` include (결제 미완료 brand UX 지원)
- [x] `POST /v1/brand/subscription/start` — Stage 1/2/3 분리 패턴 + idempotent `orderId = sha256(authKey)`
- [x] `subscription` 모듈 (`subscription.module.ts` / `subscription.service.ts` / `brand-subscription.controller.ts` / `toss-billing.adapter.ts` + 에러 분류 매트릭스)
- [x] `OnboardingGate` 의 `needsOnboarding` 확장 (결제 미완료 brand 재노출) + 결제 진입점 + `/studio/billing/return` 라우트
- [x] `IdlePanel` 배너 (결제 미완료 / 연체) + `onContinuePayment` 핸들러
- [x] 토스 SDK lazy `import('@tosspayments/tosspayments-sdk')` — studio 초기 번들 제외
- [x] `ApiError.classification` 필드 + `explainTossPaymentError` 가 서버 분류 사용 (코드 리스트 클라 중복 제거)

### Phase 2 — 노출/판매 게이트 적용 — **완료**

- [x] `PURCHASABLE_PRODUCT_WHERE` OR 3분기 재구성 (가입 brand=구독 active / 어드민 brand=면제 / legacy 통과). `PUBLIC_PRODUCT_WHERE` 는 alias 유지
- [x] `isPurchasable()` 동기화 + cart/orders 의 `brandRef` include 에 `submittedById` + `subscription { status }` 보강
- [x] `CLAUDE.md` Brand 입점 단락 동기화

### Phase 3 — 셀프 라이프사이클 운영 — **완료**

- [x] `GET /v1/brand/subscription` (getMine + invoices 12건)
- [x] `POST /v1/brand/subscription/cancel` (cancelAtPeriodEnd=true)
- [x] `POST /v1/brand/subscription/change-card` (새 빌링키 + 기존 키 soft delete + 토스 키 삭제 + past_due 면 즉시 재시도)
- [x] `TossBillingAdapter.deleteBillingKey()` + 공통 `request()` private helper (post/del 통합)
- [x] `/settings/subscription` 페이지 (4 패널) + `/settings/subscription/return` 라우트 + SubscriptionLinkCard
- [x] `useTossBillingReturn` 훅 (두 return 페이지 공통)

### Phase 4 — 정기 청구 & dunning — **완료**

- [x] `subscription-billing.cron.ts` (`@Cron('0 0 * * *', { timeZone:'Asia/Seoul' })`)
- [x] `runDueBilling`: 3 대상 분리 (갱신/종료/dunning 재시도). Promise.all + Promise.allSettled 격리
- [x] `chargeOne(sub: ChargeOneInput)` 시그니처 — 사전 로드된 sub 받음 (N+1 reload 회피)
- [x] dunning `retryGap [0, 1, 3, 7]` 일, 4회 이상 past_due 확정
- [x] `BrandSubscription.status='past_due'` 전이 + 사용자 배너 (`IdlePanel`)
- [x] `cancelSubscriptionData()` 공유 헬퍼 (forceCancel + refundInvoice + 종료 분기 lockstep)
- [x] 어드민 list 의 `CycleProgress` 컴포넌트 — 사이클 진척 시각화 + 취소 예약 라벨

### Phase 5 — Webhook & 운영 도구 — **부분 완료**

- [x] `klow_admin` 의 `/admin/brand-subscriptions` 페이지 (list + detail + 다이얼로그)
- [x] `AdminSubscriptionController` — list/detail/reject/force-cancel/refund/product 액션
- [x] 정책 위반 차단 + 구독 자동 종료 묶음 (`forceCancelIfActive` 위임)
- [x] 강제 환불 (`/invoices/:invoiceId/refund` — 토스 cancel API + invoice refunded + subscription canceled)
- [ ] `POST /webhooks/subscription/toss` (멱등 + 토스 조회 API 재검증) — Stage 2↔3 사고 복구 채널 겸용
- [ ] 세금계산서 발행 (토스 부가서비스 vs 자체)
- [ ] 운영자 알림 채널 (Slack/이메일)

---

## 미해결 질문 / TBD

> 결정될 때마다 위 섹션에 반영하고 여기서 줄 삭제.

- [ ] VAT 포함/별도 표기 (잠정 포함)
- [ ] 세금계산서 발행 채널 (토스 부가서비스 vs 자체)
- [ ] 운영자 알림 채널 (Slack 채널명 / 이메일 목록)
- [ ] `BrandSubscription.status='past_due'` 진입 시 사용자 알림 채널 — 현재 인앱 배너 (`IdlePanel`) + 카드 변경 CTA. 이메일/SMS 추가 여부는 운영 데이터 보고 결정
- [ ] `approveApplication()` 의 system 액터 audit log 표기 — 현재 `logger.log(subscription_payment_done ...)` 구조화 로그로 처리. 별도 `SystemAuditLog` 테이블 도입 필요 시 Phase 5 후속
