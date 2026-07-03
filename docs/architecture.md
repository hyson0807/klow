# KLOW Backend Architecture

## Overview

KLOW is a TikTok-style K-beauty commerce platform. The stack is split across **five independent repositories** that communicate over HTTP — there is no shared source code, only shared HTTP contracts.

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  klow_admin  │  │  klow_web    │  │  klow_brand  │  │  klow_search_server  │
│  Next.js UI  │  │  Next.js +   │  │  Next.js     │  │  NestJS  (port 4100) │
│  port 3000   │  │  TanStack Q  │  │  brand self- │  │  자체 Neon + R2      │
│  admin CRUD  │  │  port 3001   │  │  service     │  │  (influencer search) │
│              │  │  public app  │  │  port 3002   │  │                      │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘
       │ /admin/*        │ /v1/*           │ /v1/brand/*         │ (별도 백엔드,
       │                 │                 │                     │  admin 인플루언서
       └─────────────────┴────────┬────────┘                     │  탭이 프록시 소비)
                                  ▼                              │
                     ┌────────────────────────────┐             │
                     │  klow_server               │◄────────────┘
                     │  NestJS 10  (port 4000)    │   CuratedInfluencer 스냅샷
                     │  • zod validation          │
                     │  • Admin/User/BrandGuard   │
                     │  • /admin /v1 /v1/brand     │
                     │    /webhooks 4 surfaces    │
                     └────┬───────────────────┬───┘
                          │                   │
                          ▼                   ▼
                ┌──────────────────┐  ┌─────────────────────┐
                │  Neon Postgres   │  │  Cloudflare R2      │
                │  (via Prisma)    │  │  bucket: klow       │
                └──────────────────┘  └─────────────────────┘
```

`klow_server` (NestJS) is the single source of truth for the database (Neon Postgres via Prisma) and file storage (Cloudflare R2). It was extracted from `klow_admin` (which originally owned Prisma directly) for three reasons that still hold:

1. **Single source of truth.** Multiple clients (admin + public webapp + brand portal + future mobile) need the same data and the same validation rules. Duplicating Prisma + zod across every frontend was already painful at three and would be unmanageable at five.
2. **Payment & fulfilment live here.** Cart/orders/payment/webhooks/shipments need a stable home reachable from multiple clients and from external provider callbacks (Eximbay `return_url`/`status_url`, NicePay billing). They belong in the server, not in any one client.
3. **Auth boundary.** Three separate session systems (user, admin, brand) live behind one server with distinct URL prefixes and guards, keeping each surface's authorization rules in one place.

`klow_search_server` is a **separate NestJS backend** (port 4100) with its own Neon DB and its own R2 bucket (`search`). It powers influencer discovery/scraping; the frontend for it is the **인플루언서 tab inside klow_admin**, and curated results are snapshotted back into `klow_server`'s `CuratedInfluencer` models. It has its own docs at `klow_search_server/docs/`.

---

## The Five Repositories

| Repo                 | Stack                                                                 | Role                                                                       |
|----------------------|-----------------------------------------------------------------------|----------------------------------------------------------------------------|
| `klow_server`        | NestJS 10 + Prisma 6 + zod                                            | Backend API; owns DB + R2; the only repo with Prisma. Port 4000.           |
| `klow_web`           | Next.js 14 + Tailwind + **TanStack Query** + Zustand + Framer Motion  | Public mobile webapp (production). Reads/writes `/v1/*`. Port 3001.         |
| `klow_admin`         | Next.js 14 + Tailwind + react-hook-form                              | Internal admin dashboard, pure UI client. Reads/writes `/admin/*`. Port 3000. |
| `klow_brand`         | Next.js 14 + Tailwind                                                | Brand self-service portal (signup, product studio, campaigns, seeding). Posts `/v1/brand/*`. Port 3002. |
| `klow_search_server` | NestJS + Prisma (separate Neon DB + R2 bucket `search`)             | Influencer search/scraping backend. Port 4100. Frontend = admin 인플루언서 tab. |

Each subdirectory under `/Users/hyson/welkit/klow/` is its own git repo with its own commit history. They share no source code (a future improvement is a shared workspace package for types/constants — today `klow_web/src/lib/types.ts` is a hand-copied mirror of server response shapes). The legacy `KLOW/` mock-based prototype has been **removed** — `klow_web` is the sole public client.

---

## klow_server Architecture

### Stack
- **Framework:** NestJS 10
- **ORM:** Prisma 6
- **Database:** Neon Postgres (dev branch in Singapore)
- **Object storage:** Cloudflare R2 (S3-compatible) via `@aws-sdk/client-s3`
- **Validation:** zod schemas wrapped in a custom `ZodValidationPipe`
- **Port:** `4000`
- **CORS / origin guard:** `main.ts` validates `Origin` against an allowlist (localhost regex in dev), skips OAuth callbacks and `/webhooks/*`, and refuses to boot in production without `EXIMBAY_WEBHOOK_IPS` set.

### Project Tree

```
klow_server/
├── prisma/
│   ├── schema.prisma                # 43 models — source of truth for the data model
│   ├── migrations/                  # `prisma migrate dev` history
│   └── data/                        # seed payloads (seeding_rates.json, product logistics, …)
├── src/
│   ├── main.ts                      # bootstrap, origin guard, CORS, webhook IP boot-gate, port
│   ├── app.module.ts                # imports all feature modules
│   ├── prisma/                      # @Global() PrismaModule + PrismaService singleton
│   ├── common/
│   │   ├── constants.ts             # PRODUCT_CATEGORY_KEYS, VIDEO_THEMES, CONCERNS, ...
│   │   ├── validation.ts            # zod schemas (ProductInput, BrandInput, ...)
│   │   ├── zod-validation.pipe.ts   # ZodValidationPipe<T> generic pipe
│   │   ├── decorators/              # @CurrentUser() / @CurrentAdmin() / @CurrentBrandUser()
│   │   └── guards/                  # user.guard / admin.guard / super-admin.guard / brand.guard
│   └── modules/                     # 28 feature modules (see below)
```

The **28 feature modules** under `src/modules/`:

| Domain              | Modules                                                                            |
|---------------------|------------------------------------------------------------------------------------|
| Catalog             | `products`, `brands`, `creators`, `videos`, `reviews`, `shop`, `discover`, `stats` |
| Commerce            | `cart`, `orders`, `payment`, `concierge`                                            |
| Fulfilment          | `shipments`, `shipping`, `seeding`, `settlement`                                    |
| User auth           | `auth`                                                                              |
| Admin auth          | `admin-auth`, `audit-logs`                                                          |
| Brand               | `brand-auth`, `brand-applications`, `brand-scraper`, `subscription`                |
| Growth / catalog-in | `campaigns`, `curated-influencers`, `customers`, `translation`                     |
| Infra               | `upload`                                                                            |

### The Module Pattern (load-bearing convention)

Each entity follows the same shape, and this is the convention to preserve when adding new entities:

- **One service** per entity. All Prisma calls and business logic live here — the single source of truth.
- **Multiple thin controllers** per entity, one per URL surface:
  - `admin-{entity}.controller.ts` at `/admin/{entity}` — full CRUD, `@UseGuards(AdminGuard)`.
  - `public-{entity}.controller.ts` at `/v1/{entity}` — read + user flows, `UserGuard` where a session is required.
  - `brand-{entity}.controller.ts` at `/v1/brand/{entity}` — brand self-service, `@UseGuards(BrandGuard)`, scoped to the caller's own `brandId`.
- **All controllers delegate to the same service.** A bug fix or feature change flows to every surface automatically.
- **Adding a new client** (mobile app, internal tool) means adding a controller, never duplicating logic.

Some modules intentionally diverge from the multi-controller shape: `stats`/`upload` are admin-only, `discover` is read-only public, `payment` splits `PublicPaymentController` (UserGuard) from `WebhookPaymentController` (IP-whitelisted, no guard), and `brand-scraper`/`subscription` add brand-scoped controllers under `/v1/brand/*`.

### Shared product selects & pricing

`klow_server/src/modules/products/product-selects.ts` is the single place that owns product read shape **and** customer-facing price computation:

- `PRODUCT_LIST_SELECT` — the lean field set for cards (detail-only fields excluded to keep list payloads small); `DISCOVER_SCORING_SELECT` adds `concerns`/`recommendedFor` for the discover pipeline.
- `PUBLIC_PRODUCT_WHERE` / `PURCHASABLE_PRODUCT_WHERE` — the **single visibility+purchasability gate** (they are identical: subscription-gated for self-signup brands, exempt for admin-created/legacy brands).
- `priceLine(row, cp, rateKrw, fx)` — the one function that turns a product row + optional `ProductCountryPrice` + FX into the customer price line, so **display price == charged price** across cards, order creation, and quotes. See the Pricing section.

---

## URL Surfaces

The server exposes **four URL surfaces**, each with its own caller and guard. The full per-endpoint reference now lives in the per-module docs — see [`server/README.md`](./server/README.md) and `docs/server/modules/*.md`. This document only covers the surface conventions.

| Surface   | Prefix         | Caller               | Guard                                                            |
|-----------|----------------|----------------------|-----------------------------------------------------------------|
| Admin     | `/admin/*`     | klow_admin           | `AdminGuard` (real session; `SuperAdminGuard` for privileged ops) |
| Public    | `/v1/*`        | klow_web             | none for reads; `UserGuard` for cart/orders/`PATCH /auth/me`     |
| Brand     | `/v1/brand/*`  | klow_brand           | `BrandGuard` (scoped to caller's own `brandId`)                  |
| Webhooks  | `/webhooks/*`  | external PG (Eximbay/NicePay) | no CSRF/CORS; source-IP whitelist (`EXIMBAY_WEBHOOK_IPS`) |

Guard mechanics:

- **`UserGuard`** reads the `klow_sid` httpOnly cookie → validates the DB `Session` → attaches `PublicUser` to `request.user` (`@CurrentUser()`).
- **`AdminGuard`** reads `klow_admin_sid` → validates `AdminSession` (24h TTL, 30-min idle) → `@CurrentAdmin()`. `SuperAdminGuard` additionally requires `role='super'`. Every admin mutation is logged by `AdminAuditInterceptor`.
- **`BrandGuard`** reads `klow_brand_sid` → validates `BrandSession` → `@CurrentBrandUser()`, and services further scope every query to that user's `brandId`.
- **Webhooks** carry no session; they are gated purely by source-IP whitelist and idempotent state transitions.

---

## Data Model

Source of truth: `klow_server/prisma/schema.prisma` (43 models, 18 native enums). Migrations: `klow_server/prisma/migrations/` — always via `npx prisma migrate dev --name <이름>`.

### 카탈로그 (Catalog)

- **`Product`** — 판매 제품 마스터. 가격 필드 `salePrice`(KRW 정산가=원가+마진), `costKrw`(원가), `discount`(글로벌 취소선), 공개·판매 게이트 `status`/`hidden`, 통관 `hsCode`/`customsCategoryEn`, FOMO/머천다이징/페르소나 태그(`concerns`, `recommendedFor`) + 상세 콘텐츠. `brand` 는 `Brand.name` 의 denormalized 캐시(권위는 `brandId` FK). `rating`/`reviewCount` 는 `Review` 에서 서버가 파생.
- **`ProductCountryPrice`** — 제품×국가 가격 오버라이드(`iso2`, `marginKrw?`, `discountPct`). 행 없으면 전국가 기본 상속. `@@unique([productId, iso2])`, Product cascade.
- **`Brand`** — 브랜드 storefront + 정산/발송/입점상태/구독 마스터. `slug`, `status`(BrandStatus), 로고 레이아웃, 송화인/계좌 정산 정보, `pgCustomerKey`(결제 준비 게이트). Product·Shipment·Campaign·SeedingLink·BrandUser·BrandSubscription·BillingKey·BrandTranslation 소유.
- **`Creator`** — 콘텐츠 크리에이터 프로필. `handle`(unique), `skinType`/`concerns`/`country`, `followers`, SNS 핸들. Video[] 소유.
- **`Video`** — 크리에이터 릴스. `videoUrl`/`thumbnailUrl`, `themes`, `forSkinTypes`. Creator(N:1, cascade), VideoProduct 경유 Product(N:M).
- **`VideoProduct`** — Video↔Product 명시 조인 + `order`(드래그 정렬용). 복합 PK `(videoId, productId)`, 양쪽 cascade. (extra 컬럼 때문에 implicit N:M 대신 명시 조인.)
- **`Review`** — 제품 리뷰(한국어 원문). mutation 이 같은 트랜잭션에서 `Product.rating`/`reviewCount` 재계산. Product(cascade)·User(nullable)·ReviewTranslation[].
- **`ShopSettings`** — 전역 상점 설정 싱글턴(`id="default"`, lazy-create). `usdKrwRate`(KRW→USD 표시 환산), `todaysPickConcern`(`/v1/shop/today`).

### 주문 / 결제 (Orders & Payment)

- **`Order`** — 체크아웃 + Eximbay 결제. **고객측 금액은 USD 정본** — `totalUsd`(센트 정수 = PG 청구액), `shippingFeeUsd`(센트), `itemCount`. (구 KRW 원장 `subtotal`/`shippingFeeKrw` 는 2026-06 USD 마이그레이션에서 **드롭** — [`archive/pricing-usd-migration.md`](./archive/pricing-usd-migration.md).) 배송지/수취인(`email`, `fullName`, `phone @VarChar(20)`, `country`+`countryCode @VarChar(2)`, 주소, EFS 전용 `recipientState`/`recipientNameEn`/`addressLine1En`/`recipientTaxId`), `OrderStatus`+`PaymentStatus`, 결제 메타(`paymentMethod`, `pgProvider`, `pgTid @unique`, `pgCurrency`, `paidAt`), PG 심사 audit(`termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`/`agreementIp`/`fxRateSnapshot`), 캐리어 스냅샷(`shippingCarrier`, `shippingCarrierByBrand` JSON), 무가 시딩 플래그 `isSeeding`. User(nullable)·OrderItem[]·Shipment[]·SeedingLink.
- **`OrderItem`** — 주문 라인. `productId` 는 FK 아님(스냅샷이 제품 삭제/개명 후에도 생존) — 시딩 직접입력 라인에선 NULL. `productName/productImage/productBrand` + `unitPriceUsd`(센트, 고객 단가 정본) + `quantity` + `settlementPriceKrw?`(브랜드 정산 단가 스냅샷). `ShipmentItem` 1:1. Order cascade.

### 유저 인증 (User auth)

- **`User`** — 일반 고객. `email`(unique), `passwordHash?`(Google-only 는 null), `googleId?`(unique), `nickname`, `emailVerifiedAt`, 스킨 프로필(`country?`/`skinType?`/`concerns[]`). Order·Review 와 nullable 관계, CartItem·Session 소유.
- **`Session`** — 유저 DB 세션. `token`(opaque, unique), `expiresAt`, `userAgent`/`ip`. `klow_sid` 쿠키. User cascade.
- **`EmailVerification`** — 이메일 OTP + signup token(웹 + 브랜드 공용, `purpose` 로 분기). `codeHash`(argon2), `expiresAt`, `attempts`(5회 잠금). 독립 테이블.
- **`PhoneVerification`** — 브랜드 전화 SMS OTP. `phone`, `codeHash`, `purpose`, `expiresAt`, `attempts`, `lastSentAt`(60초 재발송 쿨다운). 독립 테이블.
- **`CartItem`** — 로그인 카트 라인. `(userId, productId)` unique + `quantity`. User·Product cascade.

### 어드민 인증 (Admin auth)

- **`Admin`** — 어드민 계정. `email`(unique), `passwordHash`(argon2id), `role`(operator/super), AES-GCM 암호화 TOTP secret, `invitedById`(자기참조). AdminSession·AdminAuditLog·Shipment(created/settled) 관계.
- **`AdminSession`** — 어드민 세션(24h, 30분 idle). `token`(unique), `expiresAt`, `lastSeenAt`, `ip`. Admin cascade.
- **`AdminInvitation`** — 초대 토큰(공개 가입 없음). `email`, `tokenHash`(unique), `role`, `expiresAt`, `consumedAt`.
- **`AdminLoginAttempt`** — 로그인 시도 감사(5회 실패 → 15분 락). `email`, `ip`, `success`, `@@index([email, createdAt])`.
- **`AdminAuditLog`** — 모든 admin mutation 자동 기록. `action`, `resource`/`resourceId`, `payload`(JSON, password/token redact), `ip`. Admin cascade.

### 브랜드 인증 / 구독 (Brand auth & subscription)

- **`BrandUser`** — 브랜드 운영자. `email`/`phone`/`googleId` 모두 nullable + unique(세 방식 독립 가입 정책), `passwordHash?`(phone-only 는 없음), `contactName`, `brandId`. BrandSession·제출 Brand/Product·SeedingServiceAgreement·ManualSeedingRecord.
- **`BrandSession`** — 브랜드 세션(7일 기본). `token`(unique), `expiresAt`, `ip`. `klow_brand_sid`. BrandUser cascade.
- **`BrandSubscription`** — 브랜드 SaaS 구독(1 brand=1). `planCode`, `billingInterval`, `status`(active/past_due/canceled), `currentPeriodStart/End`, `cancelAtPeriodEnd`. Brand(unique)·BillingKey·SubscriptionInvoice[].
- **`BillingKey`** — NicePay 발급 빌키 토큰. `pgBillingKey`(unique), `cardCompany`/`cardLast4`, `isDefault`, `deletedAt`(soft delete). **카드 원문은 저장 안 함(PCI).**
- **`SubscriptionInvoice`** — 구독 청구서(사이클당 1건). `amountKrw`, `status`, `pgTid`(unique), `periodStart/End`, dunning `attemptCount`/`lastAttemptAt`.

### 배송 / 시딩 (Shipping & Seeding)

- **`Shipment`** — 브랜드 단위 EFS 송장(주문×브랜드, `(orderId, brandId)` → 최대 1). `carrier`/`efsServiceType`(스냅샷), `efsTrackingNumber @unique`, 로컬 캐리어/추적번호, `status`(ShipmentStatus), 트래킹 캐시, `brandConfirmedShippedAt`, `settledAt`, `requestPayload`/`responseRaw`(audit). Order·Brand·Admin(created/settled)·ShipmentItem[].
- **`ShipmentItem`** — 송장↔OrderItem 조인. `orderItemId @unique`(한 라인 최대 1 송장, 동시 발급 race 방지). Shipment cascade.
- **`ShippingCountry`** — 국가별 지원 화이트리스트 + 물류비/캐리어 정본(PK `iso2`). `enabled`, `productLogisticsCostKrw`, `productCarrier`(직통 EFS / 나머지 EMS). ShippingExclusion[].
- **`ShippingRate`** — 국가×캐리어×무게 티어 요율(시딩 EMS/DHL 비교가; `rateKrw` = 업로드 요율표의 통합 최종가). `@@unique([carrier, iso2, weightG])`.
- **`ShippingExclusion`** — EFS 배송불가 지역(`kind`: zip/city/state + 범위). ShippingCountry cascade. (해당 구역은 구매 차단.)
- **`SeedingRate`** — 시딩 배송비 표(국가×무게 정본, 무게 올림 조회). `iso2`, `weightG`(상한), `costKrw`. `@@unique([iso2, weightG])`.
- **`SeedingLink`** — 무가 시딩 1회용 공개 링크(브랜드→바이어 무료샘플). `token`(unique), `countryCode`, 결제/선택 주체 매트릭스(`paymentBy`/`selectionMode`/`selectionSkus`), `status`(SeedingLinkStatus), `orderId`(unique, claim 시 생성). Brand·Order.
- **`SeedingServiceAgreement`** — 시딩 서비스 이용계약 전자서명(BrandUser 1:1). `version`, `signerName`, `signatureImageUrl`, `acceptedAt`.
- **`ManualSeedingRecord`** — KLOW 도입 전 브랜드 자체 시딩 기록 수기 적재(중복 수령자 cross-check). `data`(JSON), `reviewCompleted`. Brand·BrandUser(createdBy).

### 캠페인 (Campaigns)

- **`Campaign`** — 브랜드 인플루언서 캠페인. `name`, `description?`, 표시용 `startDate`/`endDate`(자유 텍스트), `status`(active/ended). Brand cascade, CampaignLink[].
- **`CampaignLink`** — 인플루언서별 공개 단축링크(`/r/{code}`). `influencerName`, `platform`(IG/YT/TT), `handle`, `code @unique`, `clickCount`, `enabled`(off 면 폴백+미집계), denormalized `brandId`. Campaign cascade, CampaignLinkDailyStat[].
- **`CampaignLinkDailyStat`** — 링크×일자 클릭 버킷(KST `YYYY-MM-DD`). `clicks`. `@@unique([linkId, date])`. CampaignLink cascade.

### 번역 (Translation — MT 캐시)

- **`BrandTranslation`** — 브랜드 storefront 텍스트 기계번역 캐시(소스=영어). `locale`, `tagline`/`description`, `sourceUpdatedAt`(캐시 무효화). `@@unique([brandId, locale])`.
- **`ProductTranslation`** — 제품 마케팅 텍스트 MT 캐시(소스=영어). `locale`, `name`/`detailDescription`/`keyIngredients`/`empathyCards`, `sourceUpdatedAt`. `@@unique([productId, locale])`.
- **`ReviewTranslation`** — 리뷰 본문 MT 캐시(소스=한국어). `locale`, `content`, `sourceUpdatedAt`. `@@unique([reviewId, locale])`.

### 인플루언서 (Influencer — from klow_search_server)

- **`CuratedInfluencer`** — 어드민이 검색서버에서 선별 저장한 인플루언서 스냅샷. `username`(unique upsert 키), 팔로워/engagement 지표, `categories`, `isPublished`(브랜드 노출 게이트). CuratedInfluencerPost[].
- **`CuratedInfluencerPost`** — 게시물 스냅샷. `shortcode`, `caption`, `likesCount`/`commentsCount`, `postUrl`, `takenAt`. CuratedInfluencer cascade.

### 기타 (Misc)

- **`ConciergeRequest`** — 고객 제품 컨시어지("대신 찾기") 요청. `imageUrl?`/`product?`/`brand?`/`note?`, `status`(ConciergeStatus). `imageUrl` 또는 `product` 중 최소 하나 필수(Zod). 독립 테이블.

### Enums (Postgres-native, 18개)

`ProductCategoryKey`(cleanser/toner/serum/cream/mist/suncream/mask) · `ProductStatus`(pending/approved/rejected) · `BrandStatus`(pending/approved/rejected/draft/withdrawal_pending/withdrawn) · `BrandLogoLayout`(circle/wide/tall/rounded) · `ConciergeStatus`(pending/replied/completed) · `OrderStatus`(pending/processing/shipped/completed/cancelled) · `PaymentStatus`(pending/paid/failed/cancelled/refunded) · `AdminRole`(operator/super) · `ShippingCarrier`(EFS/EMS/DHL) · `ShipmentStatus`(pending/submitted/failed/cancelled) · `ShippingExclusionKind`(zip/city/state) · `SeedingLinkStatus`(pending/claimed/cancelled) · `SeedingPaymentBy`(brand/customer) · `SeedingSelectionMode`(brand/customer) · `BrandSubscriptionStatus`(active/past_due/canceled) · `SubscriptionInvoiceStatus`(pending/paid/failed/refunded) · `CampaignStatus`(active/ended) · `CampaignPlatform`(IG/YT/TT). The string-based `CONCERNS` constant lives in `src/common/constants.ts`.

---

## Subsystems

Each subsystem has a dedicated deep-dive doc; these are the one-screen summaries.

### Pricing (cost + margin + per-country) → [`pricing-model.md`](./pricing-model.md)

브랜드/어드민이 **원가(`Product.costKrw`) + 마진**을 입력 → **정산가(`salePrice`) = 원가 + 마진**. **판매가(USD 센트) = `ceil((정산가 + 국가별 2kg 물류비/2) / (1−0.05) / fx × 100)`** — PG 5% 수수료를 `÷0.95` 로 net 회수, 제품 무게는 가격에 영향 없음. 국가별 차등은 `ProductCountryPrice(iso2, marginKrw?, discountPct)` — 국가별 마진 오버라이드 + 국가별 할인(기간 없음, 있으면 글로벌 `Product.discount` 대신 우선, 스택 안 함). 물류비 정본은 `ShippingCountry.productLogisticsCostKrw`(어드민 **물류비용** 탭). **서버가 목적국별 최종가를 계산해 응답에 싣는다** — 공개 read 는 `?country=`(미지정 US 베스트케이스), 응답 `customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`. 단일 계산 출처는 `product-selects.ts priceLine()` — 표시·주문·견적이 모두 거쳐 **표시가 == 청구가** 보장. 미설정국·EFS 제외구역은 구매 차단.

### Payment — Eximbay consumer checkout → [`payment-integration.md`](./payment-integration.md)

소비자 결제는 **Eximbay**(해외 카드 acquiring, 통화 USD). 흐름: `POST /v1/orders`(동의 3종 + IP + fxRate 스냅샷) → `POST /v1/payment/prepare`(ownership·동의 재검증, fgkey echo) → klow_web Eximbay JS SDK → `return_url` → `/checkout/redirect` → `POST /v1/payment/verify`(Eximbay 재조회 + `fxRateSnapshot` 기준 금액 검증 + `paymentStatus` 멱등 전이). 보강 경로 `POST /webhooks/eximbay`(IP 화이트리스트), 실패 보고 `POST /v1/payment/report-failure`(pending→failed 멱등). 환불은 `payment.refundOrder` 가 Eximbay cancel API 호출. **금액 진실은 서버** — 클라 금액 불신, `Order.totalUsd` 정본. 전체 상태머신·엣지케이스·안전망은 payment-integration.md 참고(별도로 확장 중).

### Brand subscription — NicePay billing → [`brand-subscription.md`](./brand-subscription.md)

브랜드 입점은 **구독 게이트**. `klow_brand` OnboardingGate 에서 송화인 4 + 계좌 3 필드를 저장하면 `submitForReview()` 가 `pgCustomerKey` 발급 → **NicePay 포스타트 빌링**(결제창 없음, `CardEntryForm` 카드 입력) → 카드정보를 `POST /v1/brand/subscription/start` 로 전송 → 서버가 secretKey AES 암호화 `encData` 로 빌키발급(`/v1/subscribe/regist`) + 첫 결제 + `approveApplication()` 한 트랜잭션. 빌키=`BillingKey.pgBillingKey`, 거래=`SubscriptionInvoice.pgTid`, `provider='nicepay'`. 정기 청구는 KST 자정 cron(`subscription-billing.cron.ts`), dunning 0/1/3/7일(4회 실패 → `past_due`). **카드 원문은 저장/로깅 안 함(PCI).** 결제=자동 승인이라 검수 큐 없음 — 대신 어드민 `/brand-subscriptions/*` 로 관찰·강제해지·환불·차단.

### Shipping & EFS invoices

**한 브랜드 = 한 EFS 송장.** 한 주문이 N 개 브랜드 제품을 담으면 결제 배송비도 브랜드별 요율의 합(`shippingFeeUsd`), EFS 송장도 N 장(`Shipment` 1 + `ShipmentItem` N). payload-builder 가 24번 itemCapsule 을 `{...},{...}` multi-item 으로 묶고, 배송비는 송장별 균등 안분. 주문 캐리어는 국가 고정값 `ShippingCountry.productCarrier`(직통 EFS / 나머지 EMS), 요율은 `resolveFixedRate(iso2, addr)`(EFS 제외구역/EMS 반영), 표시는 베스트케이스. **EFS 제외구역·미설정국은 구매 차단.** 어드민 발급은 `(orderId, brandId)` 그룹 단위(`/admin/shipments/order/:orderId/brand/:brandId`). 자세히는 `klow_server/docs/modules/shipping.md` + [`server/modules/shipments.md`](./server/modules/shipments.md).

### Seeding (무가 시딩)

크리에이터 시딩 배송비는 **`SeedingRate(iso2, weightG, costKrw)`** 표(운영팀이 원가·캐리어·할증·마진 선반영, 98국×71무게티어)에서 **무게 올림 조회한 값을 그대로** 쓴다 — 캐리어 비교·할증 가산 없음. 어드민 **시딩비용** 탭(`/seeding-cost`)에서 수기 편집 + 엑셀 업로드, 초기 시드 `npm run seed:seeding-rates`. 무가 시딩 주문은 `SeedingLink` 공개 링크 클레임으로 생성 — `Order.isSeeding=true`, `totalUsd=0`, `paymentStatus=paid`. 캐리어는 `shipping.service.resolveCarrier`(EFS 제외구역이면 차단). 상세: [`server/modules/seeding.md`](./server/modules/seeding.md).

### Campaigns → [`server/modules/campaigns.md`](./server/modules/campaigns.md)

브랜드가 인플루언서별 공개 단축링크(`/r/{code}`)를 발급해 유입을 추적한다. `Campaign` → `CampaignLink`(플랫폼·핸들·`code`·`enabled`·`clickCount`) → `CampaignLinkDailyStat`(KST 일자 버킷). 리다이렉트마다 `clickCount` +1 + 일자 stat upsert, 링크가 `enabled=false` 면 홈으로 폴백 + 미집계. 프론트는 브랜드 포털 `(authed)/campaigns` (생성·토글·클릭 통계) + 어드민 campaigns 탭(관찰).

### Translation / i18n

**콘텐츠 번역**(브랜드/제품/리뷰 텍스트)은 `translation` 모듈 + `BrandTranslation`/`ProductTranslation`/`ReviewTranslation` MT 캐시로 처리 — 소스 텍스트가 바뀌면 `sourceUpdatedAt` 로 캐시를 무효화하고 재번역한다. **앱 UI 문구 i18n 은 별개** — `klow_web/src/i18n/` 이 en 단일 원본에서 ja/zh/vi/th/id/ru 를 생성하고 `useT`/`useLabels` 훅으로 렌더한다(가이드 `klow_web/docs/i18n.md`). 두 시스템은 서로 독립.

### Influencer search

인플루언서 검색/스크래핑은 **별도 백엔드 `klow_search_server`**(port 4100, 자체 Neon DB + R2 bucket `search`)가 담당한다. 프론트엔드는 **klow_admin 의 인플루언서 탭**이고, 어드민이 선별한 결과는 klow_server 의 `CuratedInfluencer`/`CuratedInfluencerPost` 스냅샷으로 저장돼 `isPublished` 게이트로 브랜드에 노출된다. 검색서버 자체 문서는 `klow_search_server/docs/`.

### Auth — three separate session systems

세 개의 독립 세션 시스템이 각자 쿠키·가드·테이블을 갖는다:

- **User**(`klow_web`) — 이메일+비밀번호(이메일 OTP) + Google OAuth. `Session` + `klow_sid`. `UserGuard`. klow_web 은 `useSession`/`useAuthGate` 게이트.
- **Admin**(`klow_admin`) — 이메일+비밀번호(argon2id) + TOTP 2FA. `AdminSession` + `klow_admin_sid`(24h, 30분 idle). `AdminGuard`/`SuperAdminGuard`. 초대 기반 프로비저닝(공개 가입 없음), 5회 실패 15분 락, 모든 mutation `AdminAuditLog` 기록.
- **Brand**(`klow_brand`) — **전화+SMS OTP(Solapi) 가 메인**, 이메일+비밀번호·Google 은 보조. `BrandSession` + `klow_brand_sid`(7일). `BrandGuard`. 공개 자체 가입, TOTP 없음(마찰 최소화), `email`/`phone`/`googleId` 각 독립.

자세한 규칙은 workspace `CLAUDE.md` 의 Key Facts + [`server/modules/auth.md`](./server/modules/auth.md)·`admin-auth.md`·`brand-auth.md`.

---

## Cloudflare R2 Upload Pipeline

Browser-direct two-step upload, used for both images and videos:

```
1. Browser → POST /admin/upload (or /v1/brand/upload)  { kind, filename, contentType }
            ← server returns                            { uploadUrl, publicUrl, key }
2. Browser → PUT uploadUrl                              (binary file body)
            ← R2 returns 200
3. Form    → POST/PATCH {entity}                        { ..., image: publicUrl, ... }
```

**Why direct (not proxied):** Next.js API routes have a 4 MB body limit; product/creator videos are routinely 50–500 MB. A presigned URL bypasses Next entirely — the file goes straight from the browser to R2.

- **Bucket:** `klow` · **Public URL base:** `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev` · **Presigned TTL:** 10 min
- **Allowed content types:** `image/{webp,jpeg,png,gif}`, `video/{mp4,quicktime,webm}`. SVG intentionally rejected (XSS risk).

### Critical R2 quirk

`klow_server/src/modules/upload/r2.service.ts` sets `requestChecksumCalculation: 'WHEN_REQUIRED'` (and `responseChecksumValidation: 'WHEN_REQUIRED'`). `@aws-sdk/client-s3` v3.729+ adds automatic CRC32 checksum headers on every PUT that R2 cannot validate; because they're signed, the presigned URL signature breaks. Disabling them is the official escape hatch. **If presigned uploads ever break, check this first.**

### CORS

`klow_server/src/main.ts` validates `Origin` against an allowlist (localhost regex in dev — replace with an explicit origin list before deploy), skipping OAuth callbacks and `/webhooks/*`. The R2 bucket also has its own CORS policy allowing PUT from dev ports; if a browser PUT shows `No 'Access-Control-Allow-Origin' header`, update it in the Cloudflare dashboard (R2 → klow → Settings → CORS Policy).

---

## Admin UI Conventions

### Toast feedback for all mutations

`klow_admin` must surface **every create / update / delete** and **every error** via a toast — not silent redirects, not inline-only `error` text. (Motivation: a product save returned `400 brand too_small` but only rendered a quiet red line, so the user blamed the server instead of the missing brand selection.)

- Toast context: `klow_admin/src/components/Toast.tsx`, mounted once in `app/layout.tsx` via `<ToastProvider>`, consumed via `useToast()` → `success/error/info/show`.
- The shared CRUD hook `klow_admin/src/hooks/useFormState.ts` already emits the right toasts — form-based flows get it for free.
- Ad-hoc flows that bypass `useFormState` (e.g. `shop-settings`, `concierge-requests`, `reviews` moderation) call `useToast()` directly.
- Server errors are thrown by `api.ts` as `Error(message)`; forwarding `e.message` into the toast is enough.
- **Not** for background list fetches (use inline placeholders) or field-validation hints (use inline helper text). Toasts are for _actions the user just took_.

---

## Request Flow Examples

### Example 1: Admin creates a product

```
ProductForm.tsx (klow_admin)  → api.products.create(state)   // klow_admin/src/lib/api.ts
  ↓ POST http://localhost:4000/admin/products
AdminProductsController.create()   // klow_server
  ↓ AdminGuard.canActivate() → validates klow_admin_sid session
  ↓ ZodValidationPipe(ProductInput) → 400 if invalid
  ↓ AdminAuditInterceptor logs the mutation
ProductsService.create(dto)
  ↓ syncBrandName() — if dto.brandId, overwrite dto.brand from Brand row
  ↓ prisma.product.create({ data })
  ← row JSON back to admin → router.push('/products')
```

### Example 2: klow_web renders the TikTok-style feed

```
klow_web/src/app/videos  → useVideosQuery() → api.videos.list()   // TanStack Query
  ↓ GET http://localhost:4000/v1/videos
PublicVideosController.list() → VideosService.findAll()   // same method admin uses
  ↓ prisma.video.findMany({ orderBy: updatedAt desc, take: 200, include: creator + _count })
  ← latest 200 videos (creator info + tagged-product counts, no product objects)
  For each visible card: useVideoQuery(id) → GET /v1/videos/:id → products[] with order
  (usePrefetchVideo warms the next 1–2 cards on activeIdx change)
```

Key points: `VideosService.findAll()` serves both `AdminVideosController` and `PublicVideosController` (same code, two URLs); the list endpoint omits the products array to keep payloads small; **klow_web never uses `useEffect + fetch`** — all server state flows through TanStack Query hooks in `klow_web/src/hooks/` (a hard convention).

### Example 3: klow_web consumer checkout (USD)

```
klow_web /checkout  → POST /v1/orders   (UserGuard; cart + address + 4 동의 literal(true))
  ↓ server snapshots unitPriceUsd/totalUsd via priceLine(), stamps fxRateSnapshot + agreementIp
  → POST /v1/payment/prepare   → Eximbay /payments/ready → fgkey (echoed for anti-tamper)
  → Eximbay JS SDK (klow_web/src/lib/eximbay.ts) → return_url → /checkout/redirect
  → POST /v1/payment/verify   → Eximbay re-query + fxRateSnapshot amount check
  → order.updateMany({where:{paymentStatus:'pending'}}) idempotent → paid
  ↖ (reinforced by POST /webhooks/eximbay, IP-whitelisted)
```

Amount truth is always server-side (`Order.totalUsd`); the client's numbers are never trusted. Full state machine and edge cases: [`payment-integration.md`](./payment-integration.md).

---

## Cron & Background Jobs

The server runs scheduled work (the old "no cron jobs" claim is obsolete):

- **`subscription-billing.cron.ts`** (`subscription` module) — runs at **KST midnight**, charges due `BrandSubscription`s via NicePay (`POST /v1/subscribe/{bid}/payments`), and runs dunning on **days 0/1/3/7** (4 failures → `past_due`). See [`brand-subscription.md`](./brand-subscription.md).

Still absent (genuinely future): expired-`Session`/`EmailVerification`/`PhoneVerification` cleanup, abandoned-pending-order cleanup, and daily FX auto-refresh (`usdKrwRate` is still updated manually by admin). Add via the same `PrismaService` when needed.

---

## Local Development

```bash
# Terminal 1 — backend
cd klow_server && npm run start:dev    # http://localhost:4000

# Terminal 2 — admin
cd klow_admin && npm run dev           # http://localhost:3000

# Terminal 3 — public webapp
cd klow_web && npm run dev             # http://localhost:3001

# Terminal 4 — brand portal
cd klow_brand && npm run dev           # http://localhost:3002

# (influencer search backend, if needed)
cd klow_search_server && npm run start:dev   # http://localhost:4100
```

### Environment files (partial)

| File | Notable vars |
|------|--------------|
| `klow_server/.env` | `DATABASE_URL`, `R2_*`, `SESSION_COOKIE_NAME`, `GOOGLE_*`, `RESEND_API_KEY`, `SOLAPI_*`, `EXIMBAY_*` + `EXIMBAY_WEBHOOK_IPS`, NicePay `*`, `ADMIN_TOTP_ENCRYPTION_KEY`, `TRUST_PROXY_HOPS` |
| `klow_admin/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |
| `klow_web/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |
| `klow_brand/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |

### Prisma migrations

Always `npx prisma migrate dev --name <이름>` — never `migrate deploy`, manual SQL, or `db push`. The command needs an interactive prompt; in non-interactive shells, ask the user to run it. Inspect the DB with `npx prisma studio` (GUI at `:5555`). Admin seed: `npm run seed:admin`; seeding rates: `npm run seed:seeding-rates`.

---

## Frontend Surfaces (route map)

- **klow_web** (`src/app/`): `[brandSlug]`, `brand`, `cart`, `checkout`, `concierge`, `creator`, `customer-center`, `discover`, `faq`, `feed`, `legal`, `login`, `my`, `orders`, `product`, `seed`, `shop`, `signup`, `track`, `videos`.
- **klow_admin** (`src/app/(authed)/`): `admins`, `audit-logs`, `brand-subscriptions`, `brand-withdrawals`, `brands`, `campaigns`, `concierge-requests`, `creators`, `customers`, `influencers`, `orders`, `product-logistics-cost`, `products`, `refunds`, `returns`, `reviews`, `sales-report`, `seeding-cost`, `settlement`, `shipments`, `shipping-countries`, `shipping-rates`, `shop-settings`, `tracking`. Public: `login`, `accept-invite/[token]`.
- **klow_brand** (`src/app/`): landing `/`, `signup`, `legal`, and `(authed)/{campaigns, creators, seeding, settings, studio}` — product management lives under **studio** (the old onboarding/dashboard structure is gone).

---

## Out of Scope / Future

- **Type sharing across repos** — `klow_admin/src/lib/constants.ts`, `klow_server/src/common/constants.ts`, and `klow_web/src/lib/types.ts` are intentional hand-mirrored copies; a future shared workspace package will replace this.
- **Pagination** — list endpoints clamp to `take ≤ 200` with no cursor/page params. Add a cursor API before catalogs grow past that.
- **Payment/refund hardening** — partial refunds, outbox-based refund (PG↔DB drift is a known v1 gap), and abandoned-pending-order cleanup are not yet built.
- **Auth hardening** — password reset, reCAPTCHA/rate-limit on signup, and expired-session cleanup crons remain TODO.
- **Production deployment / CI/CD** — Railway (server) is being stood up; frontends are local dev today.
