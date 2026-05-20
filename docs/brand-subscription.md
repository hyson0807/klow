# Brand Subscription — 설계 초안

> **상태:** Draft / TBD 다수.
> 이 문서는 결정이 늘어날 때마다 채워나가는 **살아있는 설계 문서**다. 현 시점에는 의사결정 프레임과 잠정 결론만 박아두고, 실제 구현 전에 PG·요금제·UX 결정이 굳어질 때마다 섹션을 보강한다.

---

## Context & 결정 배경

klow_brand 에 "브랜드가 자기 입점 멤버십을 매달 결제" 하는 **구독(SaaS 형태) 기능**을 추가할 예정.

- **결제 대상:** 국내 브랜드만 (KRW). 해외 브랜드 구독은 현 단계 범위 밖.
- **결제 주체:** `BrandUser` (전화번호+SMS OTP / 이메일 / Google 어떤 방식으로 가입했든 동일) — `Brand` 자체가 아니다. BrandUser 는 자기 `brandId` 와 묶여 있으므로 결제 영수증·계약은 `Brand` 단위로 발행.
- **klow_web 결제(소비자 일회성 주문, 글로벌 카드, Eximbay) 와는 완전히 다른 도메인이다.**
  - 소비자 결제: 일회성, 글로벌 카드, 주문 단위, 환불 워크플로우 존재
  - 브랜드 구독: 정기결제(빌링키 기반), 국내 KRW, 멤버십 단위, dunning(연체 자동 재시도)·플랜 변경·청구서 발행 워크플로우 필요
- 따라서 **PG·DB 모델·webhook·관리자 UI 모두 분리**한다. 같은 모듈에 욱여넣지 않는다.

---

## 서버 공유 정책

> 핵심 질문이었던 "klow_web 과 같은 klow_server 인스턴스를 그대로 써도 되나?" 에 대한 답.

### 같은 서버 공유 — OK

- **라우팅 분리되어 있음**
  - 소비자: `/v1/*` (klow_server `main.ts` 글로벌 prefix, UserGuard)
  - 브랜드: `/v1/brand/*` (`brand-auth`, `brand-applications` 모듈, BrandGuard)
  - 구독 추가 시: `/v1/brand/billing/*`, `/v1/brand/subscription/*` 으로 같은 prefix 아래 추가하면 충돌 없음
- **세션 쿠키 분리되어 있음**
  - 소비자: `klow_sid`
  - 브랜드: `klow_brand_sid` (7일 TTL, 독립 도메인 정책)
- **CORS 이미 두 origin 수용** — `klow_web:3001`, `klow_brand:3002` 모두 `localhost:*` regex 로 통과 (`klow_server/src/main.ts`)
- **DB 도 같이 써도 안전** — Prisma 스키마에 새 테이블 추가(`BrandSubscription` 등)만 하면 됨. 기존 `Order` 와 FK 충돌 없음.

### 결제 모듈은 분리

현재 `klow_server/src/modules/payment/` (Eximbay) 는 다음 가정 위에 짜여있다:

- `transaction_type='PAYMENT'` (일회성 전용, recurring 모드 없음)
- `Order` 모델을 1:1 로 가정한 `markPaid` 단일 상태 전이
- 단일 webhook `POST /webhooks/eximbay` 가 consumer `order_id` 형식 가정

자세한 흐름은 [`payment-integration.md`](./payment-integration.md) 참고.

구독을 여기에 얹으면 webhook 라우팅·상태 enum·환불 흐름이 전부 꼬인다. → **새 모듈 `klow_server/src/modules/subscription/` 으로 분리** (아래 [서버 모듈 구조](#서버-모듈-구조) 참고).

---

## PG 후보 비교

> **결정 미정.** 아래 후보 중 1개를 선택해 본 문서에 확정 표기한다.

국내 KRW 정기결제 → 빌링키 기반 PG 가 필요.

| 항목 | Toss Payments 빌링키 | 나이스페이먼츠 정기결제 | Eximbay (참고) |
|------|---------------------|------------------------|----------------|
| 빌링키 발급 흐름 | 카드 등록 → `billingKey` 발급 → 서버 보관 → 매월 서버에서 결제 호출 | 최초인증 후 발급된 빌링키로 자동결제 호출 | **정기결제 모드 자체 미지원 (현 통합 기준).** docs/payment-integration.md 에 recurring 흐름 없음 |
| 멱등성 / webhook | 결제 결과 webhook + `orderId` 기반 멱등 | webhook 있음, 멱등키 별도 운영 필요 | 일회성 콜백 위주, 구독 갱신 이벤트 라우팅 추가 작업 큼 |
| 가맹점 심사 | 비교적 빠름 (스타트업 친화) | 전통 PG, 사업자 서류 요구사항 보수적 | 이미 가맹점 보유 (재활용 가능성은 있으나 정기결제 별도 신청 필요할 가능성) |
| KR 카드 커버리지 | 전 카드사 | 전 카드사 | 전 카드사 (해외 발급 카드까지) |
| SDK / DX | TS SDK 양호, 문서 깔끔 | 레거시 문서 일부, JSON/XML 혼재 | REST, 정기결제 별도 채널 필요 |
| 권장도 | **1순위 (잠정)** | 2순위 | 비권장 — consumer 결제와 같은 PG 에 두 흐름 섞이면 webhook 라우팅 부담 큼 |

**잠정 선택:** Toss Payments 빌링키.
**확정 전 TBD:**
- 가맹점 심사 기간·필요 서류 → 영업일정 확인
- 빌링키 보관 위치 (자체 DB vs PG 토큰 vault 위임) → 보안 정책 확정
- 부가세 / 세금계산서 자동발행 PG 부가서비스 사용 여부

---

## 도메인 모델 초안

> 모두 신규 Prisma 모델. 기존 `Order` / `OrderItem` 은 손대지 않는다.

```prisma
// 요금제 정의 (운영자가 admin 에서 관리)
model SubscriptionPlan {
  id           String   @id @default(cuid())
  code         String   @unique  // e.g. "brand_basic", "brand_pro"
  name         String
  priceKrw     Int                // 월 정가 (VAT 포함 여부는 정책 확정 후)
  billingCycle String             // "monthly" | "yearly" (초기엔 monthly 만)
  features     Json               // 표시용 메타 (인입·노출 한도 등)
  isActive     Boolean  @default(true)
  createdAt    DateTime @default(now())

  subscriptions BrandSubscription[]
}

// 브랜드의 구독 인스턴스
model BrandSubscription {
  id              String   @id @default(cuid())
  brandId         String   @unique          // 1 brand = 1 active subscription (초기 정책)
  planId          String
  status          String                    // "trialing" | "active" | "past_due" | "paused" | "canceled"
  currentPeriodStart DateTime
  currentPeriodEnd   DateTime
  cancelAtPeriodEnd  Boolean @default(false)
  canceledAt         DateTime?
  trialEndsAt        DateTime?
  billingKeyId       String?                // FK → BillingKey
  createdAt          DateTime @default(now())
  updatedAt          DateTime @updatedAt

  brand     Brand              @relation(fields: [brandId], references: [id])
  plan      SubscriptionPlan   @relation(fields: [planId], references: [id])
  billingKey BillingKey?       @relation(fields: [billingKeyId], references: [id])
  invoices  SubscriptionInvoice[]
}

// PG 가 발급한 빌링키 (카드 토큰)
model BillingKey {
  id          String   @id @default(cuid())
  brandId     String                          // 소유 브랜드 (조회 권한 체크용)
  provider    String                          // "toss" | "nice" 등
  pgBillingKey String  @unique                // PG 가 발급한 실제 키 (암호화 저장 검토)
  cardBrand   String?                          // 표시용 (e.g. "신한카드")
  cardLast4   String?
  isDefault   Boolean  @default(true)
  createdAt   DateTime @default(now())
  deletedAt   DateTime?

  subscriptions BrandSubscription[]
}

// 청구서 (매 결제 사이클마다 1건 생성)
model SubscriptionInvoice {
  id              String   @id @default(cuid())
  subscriptionId  String
  amountKrw       Int
  status          String                       // "pending" | "paid" | "failed" | "refunded"
  pgProvider      String?
  pgTid           String?  @unique             // PG 거래 ID, 멱등 키로도 사용
  periodStart     DateTime
  periodEnd       DateTime
  attemptCount    Int      @default(0)         // dunning 재시도 횟수
  lastAttemptAt   DateTime?
  paidAt          DateTime?
  failReason      String?
  createdAt       DateTime @default(now())

  subscription BrandSubscription @relation(fields: [subscriptionId], references: [id])
}
```

기존 모델 영향:

- `Brand` 에 역방향 relation `subscription BrandSubscription?` 만 추가 (옵셔널)
- `Order` / `Payment` / `OrderItem` 변경 없음
- **결제 상태 enum 을 공유하지 않는다.** 소비자 주문의 `pending|paid|failed|cancelled|refunded` 와 구독의 `trialing|active|past_due|paused|canceled` 는 의미가 다르므로 enum/문자열을 분리해서 혼선 방지.

---

## 서버 모듈 구조

```
klow_server/src/modules/
├── payment/                  ← (기존) consumer 일회성 결제, 손대지 않음
├── orders/                   ← (기존) consumer 주문, 손대지 않음
└── subscription/             ← (신규)
    ├── subscription.module.ts
    ├── subscription.service.ts            // 도메인 로직 (구독 생성/취소/플랜 변경)
    ├── billing-key.service.ts             // 빌링키 등록·삭제, PG 토큰 vault 위임
    ├── invoice.service.ts                 // 청구서 생성, dunning 재시도 큐
    ├── providers/
    │   ├── toss-billing.adapter.ts        // PG 어댑터 (인터페이스 뒤로 PG 교체 가능)
    │   └── billing-provider.interface.ts
    ├── controllers/
    │   ├── brand-subscription.controller.ts   // @Controller('v1/brand/subscription') + BrandGuard
    │   ├── brand-billing-key.controller.ts    // @Controller('v1/brand/billing-keys') + BrandGuard
    │   └── admin-subscription.controller.ts   // @Controller('admin/subscriptions') + AdminGuard (요금제·해지 운영)
    └── webhooks/
        └── subscription-webhook.controller.ts // @Controller('webhooks/subscription/:provider')
```

### Webhook 라우팅 분리 (중요)

- 기존: `POST /webhooks/eximbay` — consumer order 가정
- 신규: `POST /webhooks/subscription/:provider` — provider 별 분기 (`toss`, 향후 추가 시 `nice` 등)
- **두 webhook 절대 합치지 않는다.** 멱등 키·서명 검증 정책·실패 처리 흐름이 다르다.

### 인증 가드

- 브랜드 API: 기존 `BrandGuard` 그대로 사용 (`klow_server/src/common/guards/brand.guard.ts`). 자기 `brandId` 에 묶인 구독·청구서만 조회 가능하도록 service 레벨에서 ownership 체크.
- 어드민 API: `AdminGuard` + `AdminAuditInterceptor` 로 plan 수정·강제 해지·환불을 자동 audit log 에 기록.

---

## klow_brand UI 진입점

> UX 위치는 잠정. 디자인 확정 시 보강.

- **온보딩 직후 게이트:** 가입·브랜드 등록 후 대시보드 진입 시점에 "플랜 선택" 화면 노출. 무료 체험(trial)을 둘지는 TBD.
- **대시보드 좌측 메뉴 → "결제/구독"**
  - `/dashboard/billing` — 현재 플랜·다음 결제일·청구서 히스토리
  - `/dashboard/billing/payment-methods` — 카드 등록/삭제 (Toss SDK iframe 또는 hosted page)
  - `/dashboard/billing/plan` — 플랜 업/다운그레이드
  - `/dashboard/billing/cancel` — 해지 (현재 사이클 끝까지 사용 후 만료)
- **랜딩(`/`) 의 가격표** — 비로그인 상태에서 플랜·금액 안내. 가입 CTA 와 자연스럽게 연결.

`klow_brand/src/lib/api.ts` 에 `/v1/brand/subscription/*` 호출 헬퍼만 추가. 결제수단 등록은 PG SDK 가 직접 카드 인증을 처리한 뒤 발급된 빌링키 토큰만 서버로 POST.

---

## 환경변수 & 보안

- **신규 환경변수 (klow_server/.env):**
  - `TOSS_BILLING_CLIENT_KEY` — 프론트 SDK 용 (klow_brand 빌드타임에 노출 가능한 publishable key)
  - `TOSS_BILLING_SECRET_KEY` — 서버 전용
  - `TOSS_BILLING_WEBHOOK_SECRET` — webhook 서명 검증
  - `BRAND_SUBSCRIPTION_RETURN_BASE` — 카드 등록/결제 결과 후 redirect 할 klow_brand URL (e.g. `http://localhost:3002/dashboard/billing/return`)
- **빌링키 저장 정책 (확정 필요):**
  - 옵션 A: PG 가 발급한 `pgBillingKey` 문자열을 평문 저장 (PG 측에서 이미 토큰화된 값이므로 자체 카드번호는 아님)
  - 옵션 B: 한 번 더 AES-256-GCM 으로 암호화해 DB 에 저장 (admin TOTP secret 처럼 — `ADMIN_TOTP_ENCRYPTION_KEY` 와 별도 키)
  - → 잠정 옵션 B 권장 (이중 방어, 키 노출 시에도 한 단계 더 필요)
- **콜백 서명 검증:** 모든 PG webhook 은 IP allowlist + 서명 검증 둘 다. 멱등 키는 `pgTid` 사용.
- **PCI scope:** 카드 번호는 절대 서버로 들어오지 않는다 (PG SDK 가 PG 도메인에서 입력받음). klow_server 는 token / billing key 만 다룬다.

---

## 단계별 마일스톤 (placeholder)

> 각 phase 가 시작될 때 세부 작업·담당·일정 채우기.

- **Phase 0 — 결정 (현재 단계)**
  - [ ] PG 확정 (Toss vs 나이스)
  - [ ] 요금제 구조·가격·플랜 수 확정
  - [ ] 무료 체험 / 환불 / 부가세 정책 확정
- **Phase 1 — 스키마 & 빌링키 등록**
  - [ ] Prisma 마이그레이션 추가 (`npx prisma migrate dev --name brand_subscription_init`)
  - [ ] 빌링키 등록/삭제 API + klow_brand 카드 등록 UI
- **Phase 2 — 구독 라이프사이클**
  - [ ] 구독 생성·플랜 변경·취소 API
  - [ ] 첫 결제 수행 + Invoice 생성
- **Phase 3 — 정기 청구 자동화**
  - [ ] 매일 도는 batch / cron 으로 `currentPeriodEnd` 도래분 결제
  - [ ] dunning (실패 시 재시도 정책: 1일 / 3일 / 7일 등)
- **Phase 4 — Webhook & 멱등**
  - [ ] `POST /webhooks/subscription/toss` 서명 검증·멱등 처리
  - [ ] 결제 실패 webhook → 구독 status `past_due` 전이
- **Phase 5 — 운영 도구**
  - [ ] `klow_admin` 에 구독·청구서 뷰, 강제 환불·해지, 플랜 CRUD
  - [ ] 세금계산서 발급 (자동 vs 수동)

---

## 미해결 질문 / TBD

> 결정될 때마다 위 섹션에 반영하고 여기서 줄 삭제.

- [ ] PG 최종 선택 (Toss / 나이스 / 기타)
- [ ] 요금제 SKU — 몇 개 플랜, 각 플랜의 가격·기능 한도(브랜드 노출 한도, 제품 수, 인입 제한 등)
- [ ] 무료 체험 제공 여부 및 기간
- [ ] 미결제 시 정책 — 어느 시점부터 `Brand.status` 를 다시 pending 으로 내릴지, 아니면 노출은 유지하고 신규 제품 등록만 막을지
- [ ] 부가세 처리 — 표기 가격이 VAT 포함인지 별도인지, 세금계산서 자동 발행 여부
- [ ] 환불 정책 — 월중 해지 시 일할 환불 vs 사이클 만료 정책
- [ ] 플랜 다운그레이드 시점 — 즉시 vs 다음 사이클
- [ ] 결제수단 다중 등록 허용 여부 (기본 카드 1장 vs 여러 장)
- [ ] 영수증 / 세금계산서 발행자 (PG 부가서비스 vs 자체)
- [ ] 운영자 알림 — 결제 실패·해지 시 Slack/이메일 통지 채널
