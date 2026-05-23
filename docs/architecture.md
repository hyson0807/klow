# KLOW Backend Architecture

## Overview

KLOW is a TikTok-style K-beauty commerce platform. The stack is split across **four independent repositories** that communicate over HTTP:

```
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
│  klow_admin          │  │  klow_web           │  │  Future RN/iOS app   │
│  Next.js UI client   │  │  Next.js + TanStack │  │  (planned)           │
│  port 3000           │  │  Query, port 3001   │  │                      │
└──────────┬───────────┘  └──────────┬──────────┘  └──────────┬───────────┘
           │ /admin/*                │ /v1/*                  │ /v1/*
           │ (full CRUD)             │ (read-only)            │ (read-only)
           └─────────────────┬───────┴────────────────────────┘
                             ▼
                ┌────────────────────────────┐
                │  klow_server               │
                │  NestJS 10  (port 4000)    │
                │  • zod validation          │
                │  • AdminGuard(stub) /      │
                │    UserGuard(session 쿠키) │
                │  • REST API + /v1/auth/*   │
                └────┬───────────────────┬───┘
                     │                   │
                     ▼                   ▼
           ┌──────────────────┐  ┌─────────────────────┐
           │  Neon Postgres   │  │  Cloudflare R2      │
           │  (via Prisma)    │  │  bucket: klow       │
           └──────────────────┘  └─────────────────────┘
```

(The legacy `KLOW/` project is a separate Next.js app still wired to `data/mock.ts`; `klow_web` supersedes it and is the one that actually talks to `/v1/*`.)

The server was extracted from `klow_admin` (which originally owned Prisma directly) for three reasons:

1. **Single source of truth.** Multiple clients (admin + public webapp + future mobile) need the same data and the same validation rules. Duplicating Prisma + zod across three projects was already painful at three; it would be unmanageable at five.
2. **Payment system already lives here.** Cart/orders/payment/webhooks need a stable home that's reachable from multiple clients and from external payment-provider callbacks (Eximbay `status_url`). They belong in the server, not in any one client — admin + public webapp + future mobile all read/write through the same `/v1/*` and `/admin/*` surfaces. (Today: **Eximbay** sandbox merchant — `payment-integration.md` 참고.)
3. **Auth boundary.** Eventually admin will use NextAuth (cookies) and the public app will use user JWTs. Centralizing both behind one server with two URL prefixes (`/admin/*`, `/v1/*`) keeps that clean.

---

## The Four Repositories

| Repo          | Stack                                                       | Role                                                        |
|---------------|-------------------------------------------------------------|-------------------------------------------------------------|
| `klow_web`    | Next.js 14 + Tailwind + **TanStack Query** + Zustand + Framer Motion | Public mobile webapp (production). Reads `/v1/*`.           |
| `KLOW`        | Next.js 14 + Tailwind + Zustand + Framer Motion             | **Legacy** prototype. Still uses `data/mock.ts`. Phased out. |
| `klow_admin`  | Next.js 14 + Tailwind + react-hook-form                     | Internal admin dashboard, pure UI client                    |
| `klow_server` | NestJS 10 + Prisma 6 + zod                                  | Backend API; owns DB + R2; the only repo with Prisma        |

Each subdirectory under `/Users/hyson/welkit/klow/` is its own git repo with its own commit history. They share no source code (a future improvement is a shared workspace package for types/constants — today `klow_web/src/lib/types.ts` is a hand-copied mirror of server response shapes).

---

## klow_server Architecture

### Stack
- **Framework:** NestJS 10
- **ORM:** Prisma 6
- **Database:** Neon Postgres (dev branch in Singapore)
- **Object storage:** Cloudflare R2 (S3-compatible) via `@aws-sdk/client-s3`
- **Validation:** zod schemas wrapped in a custom `ZodValidationPipe`
- **Port:** `4000`
- **CORS:** `main.ts` whitelists `http://localhost:*` (regex) so both admin `:3000` and klow_web `:3001` work in dev.

### Project Tree

```
klow_server/
├── prisma/
│   ├── schema.prisma                # source of truth for the data model
│   └── migrations/                  # `prisma migrate` history
├── src/
│   ├── main.ts                      # bootstrap, CORS, port
│   ├── app.module.ts                # imports all feature modules
│   ├── prisma/
│   │   ├── prisma.module.ts         # @Global() module
│   │   └── prisma.service.ts        # PrismaClient singleton
│   ├── common/
│   │   ├── constants.ts             # PRODUCT_CATEGORY_KEYS, VIDEO_THEMES, CONCERNS, ...
│   │   ├── validation.ts            # zod schemas (ProductInput, BrandInput, ShopSettingsInput, ...)
│   │   ├── zod-validation.pipe.ts   # ZodValidationPipe<T> generic pipe
│   │   ├── prisma-utils.ts          # orNotFound() helper for P2025
│   │   ├── decorators/
│   │   │   └── current-user.decorator.ts  # @CurrentUser() — UserGuard가 붙은 라우트 전용
│   │   └── guards/
│   │       ├── admin.guard.ts       # AdminGuard (no-op stub for now)
│   │       └── user.guard.ts        # UserGuard — klow_sid 쿠키 → Session 검증 → req.user
│   └── modules/
│       ├── auth/                    # 이메일/비밀번호(OTP) + Google OAuth + 세션
│       ├── products/
│       │   ├── products.module.ts
│       │   ├── products.service.ts          # all Product business logic
│       │   ├── product-selects.ts           # PRODUCT_LIST_SELECT, DISCOVER_SCORING_SELECT
│       │   ├── admin-products.controller.ts → /admin/products (full CRUD)
│       │   └── public-products.controller.ts → /v1/products (GET, with filters)
│       ├── brands/                  # Brand CRUD + Product.brand cache sync on rename
│       ├── creators/                # Creator CRUD
│       ├── videos/                  # VideoProduct join transactions
│       ├── reviews/                 # auto-aggregates Product.rating/reviewCount
│       ├── concierge/               # user K-beauty concierge requests (public POST + admin list/status)
│       ├── orders/                  # public POST + admin list/detail/status/cancel/refund; paid 환불은 Eximbay PG cancel 호출 → DB refunded 전이
│       ├── payment/                  # /v1/payment/{prepare,verify,report-failure} + /webhooks/eximbay (status_url)
│       ├── shop/                    # ShopSettings singleton + /v1/shop/today + /v1/shop/fx-rate
│       ├── discover/                # read-only personalized recommendations (/v1/discover)
│       ├── upload/                  # R2Service + presigned URL endpoint
│       └── stats/                   # /admin/stats counts
```

### The Module Pattern (load-bearing convention)

Each entity follows the same shape, and this is the convention to preserve when adding new entities:

- **One service** per entity. All Prisma calls and business logic live here. The service is the single source of truth.
- **Two controllers** per entity:
  - `admin-{entity}.controller.ts` mounted at `/admin/{entity}` — full CRUD, `@UseGuards(AdminGuard)`.
  - `public-{entity}.controller.ts` mounted at `/v1/{entity}` — GET only (no writes, no guard yet).
- **Both controllers delegate to the same service.** A bug fix or feature change in the service flows to both surfaces automatically.
- **Adding a new client** (mobile app, internal tool) means adding a controller, never duplicating logic.

Some modules intentionally diverge from the two-controller shape:

- `stats/` — admin-only, has a single `StatsController` at `/admin/stats`.
- `discover/` — read-only personalization, has only `PublicDiscoverController` at `/v1/discover`.
- `upload/` — admin-only presign endpoint, no public surface.
- `concierge/` — public controller accepts POST only (user submits request); admin controller handles list/status/delete.
- `orders/` — public controller accepts POST (checkout submit) + GET mine/[id] + PATCH cancel; admin controller handles list/detail/status + POST refund. No DELETE (use `cancelled` status). `paid` 주문의 cancel/refund 는 `OrdersService` 가 `PaymentService.cancelByPg` 로 Eximbay 환불 API 를 먼저 호출하고 성공 시 DB `paymentStatus='refunded'` + `status='cancelled'` 로 전이한다. 외부 I/O 라 transaction 밖. PG 호출과 DB updateMany 사이 race 는 운영 단계에서 outbox 로 보강 예정. (자세한 흐름은 Payment system 섹션 참고.)
- `payment/` — Eximbay 통합. `PublicPaymentController` at `/v1/payment/{prepare,verify,report-failure}` (UserGuard) — `prepare`(FGKey 발급 + echo 본문) / `verify`(return_url 의 querystring 을 백엔드로 흘려 받아 Eximbay verify API 호출 후 DB `pending → paid` race-free 전이) / `report-failure`(pending → failed 멱등 전이). `WebhookPaymentController(/webhooks/eximbay)` 가 status_url 을 받아 동일 멱등 update 를 호출 (no guard, IP whitelist instead). 모두 `PaymentService` 로 위임 — Eximbay API client + markPaid/reportFailure/refundOrder 보유. Imports `AuthModule`. PG 통화는 USD (subtotal/usdKrwRate). `pgProvider='eximbay'`, `pgTid=transaction_id` 매핑.

Example (`products` module):

```ts
// products.service.ts — single source of truth
@Injectable()
export class ProductsService {
  constructor(private prisma: PrismaService) {}
  findAll(params: { q?, categoryKey?, minDiscount?, sort?, take? }) { /* one Prisma call */ }
  findOne(id: string) { /* ... */ }
  create(data: ProductInputT) { /* syncs brand name from brandId, then create */ }
  update(id: string, data: Partial<ProductInputT>) { /* ... */ }
  remove(id: string) { /* ... */ }
}

// admin-products.controller.ts — full CRUD, AdminGuard
// public-products.controller.ts — list (with filters) + detail, no guard yet
```

### Shared product selects

`klow_server/src/modules/products/product-selects.ts` centralizes the lean field set used by list/card views:

- `PRODUCT_LIST_SELECT` — everything needed to render a product card. Detail-only fields (`detailImages`, `recommendedFor`, `concerns`, `sourceUrl`, `totalSold`, `volume`, `step`) are intentionally excluded to keep list payloads small.
- `DISCOVER_SCORING_SELECT` — `PRODUCT_LIST_SELECT` + `concerns` + `recommendedFor`, used by the discover scoring pipeline.

This is the single place to edit if list payload shape needs to change.

---

## URL Surfaces

| Surface  | Prefix     | Caller                  | Methods                       | Guard                                                |
|----------|------------|-------------------------|-------------------------------|-------------------------------------------------------|
| Admin    | `/admin/*` | klow_admin              | GET / POST / PATCH / DELETE   | `AdminGuard` (stub)                                   |
| Public   | `/v1/*`    | klow_web                | GET + POST + PATCH + PUT + DELETE | 엔드포인트별 — 읽기 계열은 없음, 주문 / `PATCH /auth/me` / `/cart/*`는 `UserGuard` |
| Auth     | `/v1/auth/*` | klow_web              | GET + POST + PATCH            | 쿠키 기반 세션(쓰기 엔드포인트는 자체적으로 검증)      |

### Endpoints

**Stats**
- `GET /admin/stats` → `{ products, creators, videos }` counts

**Products** — full CRUD, with filterable public list
- `GET    /admin/products` (search via `?q=`, plus the filter params below)
- `GET    /admin/products/:id`
- `POST   /admin/products` (server auto-syncs `brand` string from `brandId` if supplied)
- `PATCH  /admin/products/:id`
- `DELETE /admin/products/:id`
- `GET    /v1/products` — supports `?q=`, `?categoryKey=<cleanser|toner|serum|cream|mist|suncream|mask>`, `?minDiscount=N`, `?sort=discount_desc`, `?take=N` (clamped 1..200, default 200)
- `GET    /v1/products/:id`

**Brands** — full CRUD with denormalized cache sync
- `GET    /admin/brands` (search via `?q=`)
- `GET    /admin/brands/:id`
- `POST   /admin/brands`
- `PATCH  /admin/brands/:id` — on rename, cascades the new name into `Product.brand` inside one transaction
- `DELETE /admin/brands/:id` — detaches products (`brandId → null`) before deleting
- `GET    /v1/brands` (list only)

**Creators** — full CRUD
- `GET    /admin/creators`
- `GET    /admin/creators/:id`
- `POST   /admin/creators`
- `PATCH  /admin/creators/:id`
- `DELETE /admin/creators/:id`  (cascade deletes videos)
- `GET    /v1/creators` + `GET /v1/creators/:id`
- `GET    /v1/creators/:id/products` — 해당 크리에이터의 모든 릴스에 태그된 제품을 중복 제거하여 최신 Video.updatedAt 순으로 반환 (`PRODUCT_LIST_SELECT` 필드, take 200)

**Videos** — full CRUD with VideoProduct join
- `GET    /admin/videos`
- `GET    /admin/videos/:id`    (includes creator + tagged products in order)
- `POST   /admin/videos`        (creates video + VideoProduct join rows in one transaction)
- `PATCH  /admin/videos/:id`    (delete + recreate join rows transactionally)
- `DELETE /admin/videos/:id`
- `GET    /v1/videos` (supports `?creatorId=`) + `GET /v1/videos/:id`

**Reviews** — full CRUD with auto-aggregation
- `GET    /admin/reviews`       (filters: `?productId=`, `?minRating=`, `?q=`; includes parent product summary)
- `GET    /admin/reviews/:id`
- `POST   /admin/reviews`       (recomputes `Product.rating` / `reviewCount` in same tx)
- `PATCH  /admin/reviews/:id`   (recomputes aggregates)
- `DELETE /admin/reviews/:id`   (recomputes aggregates)
- `GET    /v1/reviews` (supports `?productId=`) + `GET /v1/reviews/:id`

**Shop** — singleton settings + "Today's Pick" feed
- `GET    /admin/shop/settings` → current `ShopSettings` (lazy-created on first read)
- `PATCH  /admin/shop/settings` → set `todaysPickConcern` (one of the `CONCERNS` enum values)
- `GET    /v1/shop/today?take=N` → `{ concern, products }`: latest products whose `concerns` array contains the configured Today's Pick concern (take clamped 1..50, default 10)

**Discover** — personalized recommendations (read-only)
- `GET    /v1/discover?skinType=&concerns=` → `{ persona, recommended, bestsellers, skinTwinCreators, fallback }`
  - `concerns` is a CSV of concern keywords (e.g. `concerns=hydration,acne,pore`). Legacy single `concern` query param is still accepted for backward compatibility.
  - When no params are supplied, returns a **non-personalized fallback** (`fallback: true`): latest products + bestsellers, no creators.
  - Otherwise scores products (skin-type match, concern overlap × 14, review-count social proof) and ranks creators whose `skinType`/`concerns` match the persona. More overlap → higher rank.
  - `CONCERN_EXPANSION` (e.g. `hydration → [hydration, soothing]`) is applied **only when a single concern is supplied**. With multi-select, the user's exact choices are honored without broadening.

**Orders** — checkout + Eximbay PG integration (가격은 모두 KRW 정수, 자세한 결제 흐름은 Payment system 섹션 참고)
- `POST   /v1/orders` — **requires `UserGuard`**. Body: `{ fullName, phone, country, addressLine1, addressLine2?, city, postalCode, items: [{productId, quantity}], agreedToTerms: true, agreedToRefund: true, agreedToPgDataSharing: true }`. `phone` 은 유통 사양상 숫자와 `+`, `-`, `(`, `)` 만 허용(공백 불가), 길이 4~20 — Zod 정규식 `/^[+\-()0-9]+$/` 로 강제하고 `Order.phone` 컬럼 `VARCHAR(20)` 와 길이 일치. `email` / `userId` 는 세션에서, `agreementIp` 는 `x-forwarded-for` 첫 hop 에서 서버가 직접 채운다. Zod 가 동의 3종을 `literal(true)` 로 강제. Server re-looks up each `productId`, rejects unknown ones with 400, snapshots `productName/productImage/productBrand/unitPrice` from the DB (ignoring any client-side prices), merges duplicate productIds, computes `subtotal` + `itemCount`, and stamps `termsAgreedAt` / `refundAgreedAt` / `pgDataSharingAgreedAt` (same Date) + `fxRateSnapshot` (당시 `ShopSettings.usdKrwRate`). Lookup + insert share a `$transaction`. Returns `{ id }`.
- `GET    /v1/orders/mine` — **requires `UserGuard`**. Returns the caller's 50 most recent orders (`createdAt desc, id desc`) with `items[]` included. `paymentStatus` 포함.
- `GET    /v1/orders/:id` — **requires `UserGuard`**. Ownership-checked: returns 404 when `order.userId !== currentUser.id`.
- `PATCH  /v1/orders/:id/cancel` — **requires `UserGuard`**. Ownership-checked. `pending` 이면 단순 상태 변경, `paid` 이면 Eximbay `/v1/payments/{tid}/cancel` 환불 호출 후 `paymentStatus='refunded'` + `status='cancelled'` 전이. `shipped`/`completed`/`cancelled` 는 가드로 차단(400) — 발송 이후엔 RMA(반품) 절차로 안내.
- `GET    /admin/orders` (filters: `?status=...`, `?paymentStatus=...`, `?take=N`, `?skip=N`; orders with `items[]` included, sorted `createdAt desc, id desc` for stable pagination)
- `GET    /admin/orders/:id`
- `PATCH  /admin/orders/:id/status` — body `{ status }`, enum `pending → processing → shipped → completed | cancelled`
- `POST   /admin/orders/:id/refund` — body `{ reason }`. paid 주문에 대해 운영자가 직접 환불 (사용자 취소 외 케이스). 사유는 필수, `AdminAuditLog` 자동 기록.

**Payment** — Eximbay 연동. 자세한 내용은 `payment-integration.md` 참고.

- `POST   /v1/payment/prepare` — **requires `UserGuard`**. body `{ orderId }`. 주문 소유자 + `paymentStatus='pending'` 검증 후 `subtotal/usdKrwRate` 를 USD 소수 2자리로 변환해 Eximbay `/v1/payments/ready` 호출 → `fgkey` 수령. 응답으로 `{ fgkey, sdkUrl, payment, merchant, buyer, url }` 을 echo (SDK 호출 시 동일 인자가 다시 와야 fgkey 검증 통과 — 위변조 방지).
- `POST   /v1/payment/verify` — **requires `UserGuard`**. body `{ querystring }` (return_url 의 raw qs). Eximbay `/v1/payments/verify` 호출 → 금액 재검증 → `prisma.order.updateMany({where:{id, paymentStatus:'pending'}, data:{paymentStatus:'paid', paidAt, pgProvider:'eximbay', pgTid, paymentMethod}})` 멱등 전이. 응답 `{ orderId }`.
- `POST   /webhooks/eximbay` — Eximbay status_url. `verify` 와 같은 멱등 update 를 한 번 더 호출. 응답 본문 `rescode=0000&resmsg=Success`. CSRF 가드 통과(`/webhooks/`). source IP whitelist 는 운영 단계 TODO.

**Shop**
- `GET    /v1/shop/today` — `ShopSettings.todaysPickConcern` 에 매칭되는 제품 N개 반환.
- `GET    /v1/shop/fx-rate` — `{ usdKrwRate, updatedAt }`. klow_web 부팅 시 가져가서 USD 표시 환산에 사용.
- `GET    /admin/shop/settings`, `PATCH /admin/shop/settings` — partial 업데이트. `todaysPickConcern` 와 `usdKrwRate` 를 독립 갱신 가능.

**Concierge Requests** — user K-beauty product sourcing requests
- `POST   /v1/concierge-requests` — public, no guard. Requires `imageUrl` or `product` (at least one). Creates a pending request.
- `GET    /admin/concierge-requests` (filter: `?status=pending|replied|completed`)
- `PATCH  /admin/concierge-requests/:id` — update status (`pending` → `replied` → `completed`)
- `DELETE /admin/concierge-requests/:id`

**Cart** — 로그인 사용자 장바구니 (전 엔드포인트 `UserGuard` 필수)
- `GET    /v1/cart` → `{ items: CartLine[] }`. `CartLine`은 `{ productId, quantity, name, brand, image, price, salePrice, discount }` — 현재 Product 값으로 조인하여 반환한다(저장된 가격이 아니라 서버의 최신 가격이 기준).
- `POST   /v1/cart` — body `{ productId, quantity }`. `(userId, productId)` upsert. FK 위반(`P2003`)은 `404 product not found`로 변환. 응답은 `{ ok: true }`(클라이언트가 낙관적 업데이트로 선반영하므로 전체 리스트를 돌려주지 않는다).
- `DELETE /v1/cart/:productId` — 단일 라인 삭제. 없어도 조용히 통과. `{ ok: true }`.
- `DELETE /v1/cart` — 전체 비우기. `{ ok: true }`.
- `PUT    /v1/cart/merge` — body `{ items: [{productId, quantity}] }` (최대 100). 로그인 직후 로컬 카트를 서버로 끌어올릴 때 사용. 존재하지 않는 productId는 무시, 동일 productId는 중복 제거, 수량은 `max(local, server)`로 병합(다른 기기에서 추가한 아이템이 덮어쓰여 사라지지 않도록). 단일 `$transaction`으로 실행 후 최종 카트 `{ items }`를 반환.

**Upload**
- `POST   /admin/upload` → `{ uploadUrl, publicUrl, key }` (R2 presigned PUT URL, valid 10 min). Allowed content types: `image/{webp,jpeg,png,gif}` or `video/{mp4,quicktime,webm}` — SVG is intentionally rejected (XSS risk).

**Auth** — 이메일/비밀번호(OTP 인증) + Google OAuth, DB 세션 + httpOnly 쿠키
- `POST   /v1/auth/send-verification` — body `{ email }`. 6자리 OTP를 해시해 `EmailVerification`에 저장하고 Resend로 발송. `RESEND_API_KEY`가 없으면 서버 콘솔에 코드 로깅(dev 폴백).
- `POST   /v1/auth/verify-email` — body `{ email, code }`. OTP 검증 성공 시 15분짜리 `signupToken`(opaque)을 발급. 5회 실패 시 해당 OTP 레코드 잠금.
- `POST   /v1/auth/signup` — body `{ email, password, nickname, emailVerificationToken, country?, skinType?, concerns? }`. 비밀번호는 `argon2id` 해시. 비로그인 상태에서 수집한 스킨 프로필(`country/skinType/concerns`)이 있으면 가입과 동시에 저장. 성공 시 `Session` 생성 + `klow_sid` 쿠키 설정 + `{ user }` 반환.
- `POST   /v1/auth/login` — body `{ email, password }`. argon2 검증 후 세션 쿠키 설정 + `{ user }` 반환.
- `POST   /v1/auth/logout` — 현재 세션 쿠키를 읽어 DB `Session` 삭제 + 쿠키 클리어.
- `GET    /v1/auth/me` — `UserGuard` 없이 쿠키만 확인. 세션 있으면 `{ user }`(스킨 프로필 포함), 없으면 401.
- `PATCH  /v1/auth/me` — **`UserGuard` 필수**. body `{ nickname?, country?, skinType?, concerns? }`. 각 필드는 `undefined`면 유지, `null`이면 초기화, 값이 있으면 덮어쓰기. `concerns`는 `CONCERNS` enum으로 검증.
- `GET    /v1/auth/google?returnTo=/...` — returnTo를 서버 쿠키(`klow_return_to`, 10분)에 임시 저장 후 `/v1/auth/google/authorize`로 302. passport-google-oauth20이 Google 동의 화면으로 리다이렉트.
- `GET    /v1/auth/google/callback` — Google에서 돌아온 code 검증 → `findOrCreateGoogleUser` (googleId 우선, 없으면 email 매칭, 없으면 신규) → 세션 쿠키 설정 → `FRONTEND_URL + returnTo`로 302.

`SESSION_COOKIE_NAME` (기본 `klow_sid`), `SESSION_TTL_DAYS` (기본 30), `GOOGLE_CLIENT_ID/SECRET/CALLBACK_URL`, `FRONTEND_URL`, `RESEND_API_KEY`, `EMAIL_FROM`은 `klow_server/.env`에서 설정. Google 자격증명이 비어 있으면 부팅은 되지만 `/v1/auth/google`에 들어가면 passport가 실패한다.

---

## Data Model

### Relationship Diagram

```
Brand (1) ──< Product (N) ──< Review (N) >── User (1, nullable)
                 │
                 └──< VideoProduct (N) ── Video (N) ──> Creator (1)

User (1) ──< Session (N)           (Session.token은 opaque, 쿠키로 전달)
User (1) ──< Order (N, nullable)   (신규 주문은 userId 필수; 기존 게스트 주문은 null 보존)
User (1) ──< Review (N, nullable)
User (1) ──< CartItem (N) >── Product (1)   (userId+productId 유니크, 양쪽 cascade)

Order (1) ──< OrderItem (N)       (OrderItem.productId is NOT a FK — snapshots survive product deletion)
ShopSettings (singleton, id = "default")
ConciergeRequest (standalone — no FK relations)
EmailVerification (standalone — purpose-tagged OTP/signupToken 레코드)
```

### Entities

| Model           | Purpose                                                                 |
|-----------------|-------------------------------------------------------------------------|
| `Product`       | K-beauty product. Carries FOMO fields (`stockLeft`, `viewersNow`, `totalSold`), merchandising flags (`isHero`, `isLoss`, `tip`), persona tags (`recommendedFor`, `concerns`), and detail-page content (`detailImages`, `detailDescription`, `volume`, `videoClipUrl`, `sourceUrl`). Two JSON arrays power the detail page's ingredient tab (each capped at 3): `keyIngredients` (`{name, effect}[]` — Core Ingredients 카드) and `empathyCards` (`{title, subtitle, ingredients[]}[]` — "이런 사람들!" 탭. 비어 있으면 `klow_web` 상세에서 탭 자체가 숨겨지고 Core Ingredients만 노출). 화장품법 상품정보제공고시용 8개 문자열 필드(`manufacturer`, `countryOfOrigin`, `expiryInfo`, `ingredients`, `precautions`, `qualityAssuranceStandard`, `functionalCertification`, `customerServicePhone`, 모두 기본값 `""`) — 상세 페이지 하단 접이식 섹션에 노출, 자세한 내용은 Future Expansion > PG 심사 섹션. `brand` is a denormalized string cache of the linked `Brand.name`; `brandId` is the authoritative FK. `rating` and `reviewCount` are **server-managed aggregates** computed from `Review` — never accepted from admin input. |
| `Brand`         | K-beauty brand. `name` is unique; `tagline`, `logosCircle`/`logosWide`/`logosTall` + `logoLayout`, `order` power the admin's brand directory. Renames cascade into `Product.brand` inside a transaction. Delete detaches products (`brandId → null`) rather than blocking. |
| `ShopSettings`  | Singleton row (`id = "default"`) storing merchandising config. `todaysPickConcern` (a `CONCERNS` value, powers `/v1/shop/today`) + `usdKrwRate` (Float, default 1380, 운영 중 어드민이 갱신; klow_web 가 KRW→USD 환산 표시에 사용). 두 필드는 partial PATCH 로 독립 갱신. Created lazily on first read. |
| `Creator`       | Influencer profile: handle, story, profile/hero images, social URLs, follower count, `skinType`, `concerns`, `country`, `heroVideoUrl`. |
| `Video`         | Short-form reel. References one `Creator` (N:1) and N `Product`s (N:M) via `VideoProduct`. Carries `themes` (enum array) and `forSkinTypes` for discovery. |
| `Review`        | Per-product user review. Mutations recompute `Product.rating` (avg) and `reviewCount` in the same Prisma transaction. |
| `VideoProduct`  | Explicit join table. Composite PK `(videoId, productId)` + `order` field for drag-reorder. Cascades on delete. |
| `ConciergeRequest` | User-submitted K-beauty product sourcing request. Standalone (no FK). Fields: `imageUrl?`, `product?`, `brand?`, `note?`, `status` (`ConciergeStatus` enum: `pending` → `replied` → `completed`). At least `imageUrl` or `product` is required (enforced by Zod). |
| `Order` | Checkout + Eximbay 결제. 고객 정보·배송지 (`email`, `fullName`, `phone @db.VarChar(20)`, `country`, `addressLine1/2`, `city`, `postalCode`), 서버 계산값 `subtotal` (**KRW 정수** — customer KRW) + `itemCount`, `OrderStatus` enum + `PaymentStatus` enum (`pending/paid/failed/cancelled/refunded`). 결제 메타 (`paymentMethod`, `pgProvider='eximbay'`, `pgTid @unique` = Eximbay transaction_id, `paidAt`, `cancelledAt`). 결제 실패 사유는 `paymentFailureReason @db.VarChar(500)` 컬럼에 운영 디버그용으로 분리 보관(고객 메모는 제거). PG 심사 audit 필드 — 약관 동의 시점 `termsAgreedAt` / `refundAgreedAt` / `pgDataSharingAgreedAt` + `agreementIp` + 시점 환율 스냅샷 `fxRateSnapshot` (Float?). Eximbay 청구 통화는 USD 라 `subtotal/fxRateSnapshot` 으로 호출 시점에 환산. 배송비는 `shippingFeeKrw` + `shippingFeeUsdSnapshot` = 캐리어 단가 × 카트의 distinct `brandId` 수 — 한 브랜드 = 한 EFS 송장이라 브랜드별로 배송비가 곱해서 청구된다. 인덱스: `status`, `paymentStatus`, `createdAt`, `email`, `userId`. |
| `OrderItem` | Line item on an `Order`. `productId` is stored as a plain string (no FK) and `productName/productImage/productBrand/unitPrice`(**KRW 정수**) are snapshotted at order time so the row survives product rename/delete. `shipmentItem` 1:1 으로 한 `Shipment` 그룹에 묶일 수 있다. Cascades on Order delete. |
| `Shipment` | 브랜드 단위 EFS 송장 (= 한 주문 안에서 같은 brand 의 `OrderItem` 들이 묶인 발송 단위). 1 (orderId, brandId) → 최대 1 active Shipment. `carrier`/`efsServiceType`(요청 시점 스냅샷), `efsTrackingNumber @unique`, `localCarrierName`/`localTrackingNumber`(EFS newCreateShipment 회신), `status` (`pending`/`submitted`/`failed`), `requestPayload` JSON + `responseRaw`(audit). 어드민 발급/재시도(`/admin/shipments/*`)는 모두 그룹 단위. 브랜드는 자기 `brandId` 의 송장만 조회. |
| `ShipmentItem` | `Shipment` ↔ `OrderItem` 1:N 조인. `orderItemId @unique` 가 한 라인은 최대 1 송장에만 속함을 강제 + 동시 발급 race 방지. Shipment delete 시 cascade. EFS 24번 itemCapsule `{...},{...}` 의 각 캡슐이 1 ShipmentItem 에 대응. |
| `User` | 공개 사용자 계정. `email` unique, `passwordHash?`(Google-only 사용자는 null), `googleId?`(unique), `nickname`, `emailVerifiedAt`. 스킨 프로필 필드(`country?`, `skinType?`, `concerns: String[]`)는 비로그인 상태에서 입력된 값을 로그인 시 `PATCH /v1/auth/me` 또는 회원가입 payload로 끌어올려 저장한다. `Order.userId` / `Review.userId`와 nullable 관계(기존 레코드 보존). |
| `Session` | DB 기반 세션. `token`(opaque 32-byte base64url) unique, `expiresAt`, `userAgent`/`ip`. `klow_sid` 쿠키로 전달. 로그아웃은 행 삭제로 즉시 무효화. User 삭제 시 cascade. |
| `EmailVerification` | 회원가입용 OTP와 `signupToken`을 둘 다 담는 임시 테이블(`purpose` 컬럼으로 구분: `signup-otp` / `signup-token`). 코드/토큰은 argon2로 해시. `expiresAt`(OTP 10분, 토큰 15분), `consumedAt`, `attempts`(5회 초과 시 잠금). 현재 만료 로우 정리 크론은 없음. |
| `CartItem` | 로그인 사용자의 장바구니 라인. `(userId, productId)` 유니크 + `quantity`. `User` / `Product` 삭제 시 cascade. 비로그인 카트는 클라이언트 `useCartStore`(localStorage) 에만 존재하고, 로그인 직후 `PUT /v1/cart/merge`가 수량을 `max(local, server)`로 병합해 서버로 승격한다. 이후 `add/remove/update`는 낙관적 로컬 업데이트 + 백그라운드 `/v1/cart/*` 호출로 단일 소스를 유지. |

### Enums (Postgres-native)

`schema.prisma` declares three native enums used throughout the model:

- `ProductCategoryKey` — `cleanser | toner | serum | cream | mist | suncream | mask`
- `ConciergeStatus` — `pending | replied | completed`
- `OrderStatus` — `pending | processing | shipped | completed | cancelled`
- `PaymentStatus` — `pending | paid | failed | cancelled | refunded`

The string-based `CONCERNS` constant lives in `src/common/constants.ts` and is shared by `ShopSettings.todaysPickConcern` and `CreatorInput.concerns`.

### Why explicit join tables?

`VideoProduct` carries an `order: Int` column so the admin can reorder which products appear first inside a video. Implicit Prisma N:M relations don't support extra columns, so we use an explicit join table. This also lets us add fields like `timestamp`, `mentionType`, or `isPrimary` later without a migration headache.

### Schema location

Source of truth: `klow_server/prisma/schema.prisma`. Migrations: `klow_server/prisma/migrations/`.

---

## Cloudflare R2 Upload Pipeline

Browser-direct two-step upload, used for both images and videos:

```
1. Browser → POST /admin/upload         { kind, filename, contentType }
            ← server returns            { uploadUrl, publicUrl, key }

2. Browser → PUT uploadUrl              (binary file body)
            ← R2 returns 200

3. Form    → POST/PATCH /admin/{entity} { ..., image: publicUrl, ... }
```

**Why direct (not proxied through the server):**
Next.js API routes have a 4 MB body limit. Product/creator videos are routinely 50–500 MB. A presigned URL bypasses Next entirely; the file goes straight from the browser to R2.

**Bucket:** `klow`
**Public URL base:** `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
**Presigned URL TTL:** 10 minutes
**Allowed content types:** `image/webp`, `image/jpeg`, `image/png`, `image/gif`, `video/mp4`, `video/quicktime`, `video/webm`. SVG is intentionally rejected.

### Critical R2 quirk

`klow_server/src/modules/upload/r2.service.ts` sets:

```ts
requestChecksumCalculation: 'WHEN_REQUIRED',
responseChecksumValidation:  'WHEN_REQUIRED',
```

`@aws-sdk/client-s3` v3.729+ added automatic CRC32 checksum headers (`x-amz-checksum-crc32`, `x-amz-sdk-checksum-algorithm`) on every PUT. R2 does not yet validate these the same way AWS S3 does, and because they're part of the signed headers, the presigned URL signature breaks. Disabling them is the official escape hatch. **If presigned uploads ever break, check this first.**

### CORS

`klow_server/src/main.ts` whitelists `http://localhost:*` via regex so both the admin (`:3000`) and klow_web (`:3001`) dev servers work out of the box. Replace with an explicit origin list before deployment.

The R2 bucket itself also has a CORS policy allowing PUT from local dev ports. If you ever see `No 'Access-Control-Allow-Origin' header` on the browser PUT, update the CORS policy in the Cloudflare dashboard (R2 → klow → Settings → CORS Policy).

---

## Admin UI Conventions

### Toast feedback for all mutations

`klow_admin` must surface **every create / update / delete** and **every error** via a toast — not with silent redirects, not with inline-only `error` text. The original motivation was a support ticket where a product save returned `400 brand too_small`, but the form only rendered a quiet red line below the button and the user blamed the server instead of the missing brand selection.

- The toast context lives at `klow_admin/src/components/Toast.tsx`. It is mounted once in `app/layout.tsx` via `<ToastProvider>` and consumed via `useToast()` — returning `success(msg)`, `error(msg)`, `info(msg)`, and the lower-level `show(kind, msg)`.
- The shared CRUD hook `klow_admin/src/hooks/useFormState.ts` already emits the right toasts for forms built on top of it (ProductForm, BrandForm, CreatorForm, VideoForm). Create/edit/delete success and failure all flow through there — you should not have to wire it per-form.
- For **ad-hoc admin flows that bypass `useFormState`** (e.g. `shop-settings`, `concierge-requests`, `reviews` moderation, `ReviewManager`), call `useToast()` directly in the page/component. Error toasts replace the old inline `error` state; success toasts replace silent list-refreshes.
- Errors from the server are thrown by `api.ts` as `Error(message)`. The message is usually the server's JSON body (e.g. `API 400: {"error":"validation failed",…}`), so forwarding `e.message` into the toast is enough — no extra parsing required.
- **Not** to be used for: background list fetches (use inline `불러오는 중…` placeholders), form field validation hints (use inline `<Field>` helper text), or anything truly silent. Toasts are for _actions the user just took_.

The goal: no admin action ever happens in silence, and every failure tells the user why.

---

## Request Flow Examples

### Example 1: Admin creates a product

```
ProductForm.tsx (klow_admin)
  ↓ form submit
api.products.create(state)             // klow_admin/src/lib/api.ts
  ↓ POST http://localhost:4000/admin/products
AdminProductsController.create()       // klow_server
  ↓ AdminGuard.canActivate() → true (stub)
  ↓ ZodValidationPipe(ProductInput) → throws 400 if invalid
ProductsService.create(dto)
  ↓ syncBrandName() — if dto.brandId, overwrite dto.brand from Brand row
  ↓ prisma.product.create({ data })
  ← row JSON back to admin → router.push('/products')
```

### Example 2: Admin uploads a creator's profile image

```
FileUpload.tsx (klow_admin)
  ↓ user picks file
uploadFile(file, 'image')              // klow_admin/src/lib/upload.ts
  ↓ api.upload.presign('image', name, contentType)
  ↓ POST /admin/upload
R2Service.getPresignedUploadUrl()       // klow_server
  ← { uploadUrl, publicUrl, key }
  ↓ XHR PUT (binary body) → uploadUrl  // direct to R2
  ← 200 OK
  ← publicUrl returned to caller
[publicUrl saved into form state]
[on form submit, the publicUrl ends up on Creator.profileImage in Postgres]
```

### Example 3: klow_web renders the TikTok-style feed

```
klow_web/src/app/page.tsx
  ↓ useVideosQuery() → api.videos.list()         // TanStack Query caches keyed by queryKeys
  ↓ GET http://localhost:4000/v1/videos
PublicVideosController.list()            // klow_server
  ↓ delegates to:
VideosService.findAll()                  // ← same method admin uses
  ↓ prisma.video.findMany({ orderBy: updatedAt desc, take: 200, include: creator + _count })
  ← JSON of latest 200 videos (creator info + tagged-product counts, no product objects)

  For each visible card:
VideoFeedCard                            // klow_web/src/components/video
  ↓ useVideoQuery(id) → api.videos.detail(id)    // lazy-load detail only for visible cards
  ↓ GET /v1/videos/:id → products[] with order
  [on activeIdx change, usePrefetchVideo warms next 1–2 cards]
```

The key things to notice in Example 3:

- `VideosService.findAll()` is called by both `AdminVideosController` and `PublicVideosController`. Same code, two URLs.
- The list endpoint deliberately omits the products array to keep the payload small; klow_web fetches detail per-card on demand. A future optimization is to add `products` to the list include on the server and drop the per-card round-trip.
- **klow_web never uses `useEffect + fetch` directly** — all server state flows through TanStack Query hooks in `klow_web/src/hooks/`. This is a hard convention.

### Example 4: klow_web fetches discover recommendations

```
klow_web/src/app/discover/page.tsx
  ↓ useDiscoverQuery({ skinType, concern })      // reads persona from zustand store
  ↓ GET /v1/discover?skinType=oily&concern=hydration
PublicDiscoverController.get()           // klow_server
  ↓ DiscoverService.getRecommendations()
  ↓ CONCERN_EXPANSION expands "hydration" → ["hydration", "soothing"]
  ↓ parallel Prisma queries: candidates, bestsellers, creatorPool
  ↓ scoreProduct / scoreCreator → top 10 + top 6
  ← { persona, recommended[], bestsellers[], skinTwinCreators[], fallback: false }
```

If neither `skinType` nor `concern` is present (user hasn't completed onboarding), the service short-circuits to a non-personalized response with `fallback: true` and an empty `skinTwinCreators`.

---

## Local Development

```bash
# Terminal 1 — backend
cd klow_server
npm run start:dev          # nest start --watch  →  http://localhost:4000

# Terminal 2 — admin
cd klow_admin
npm run dev                # next dev            →  http://localhost:3000

# Terminal 3 — public webapp
cd klow_web
npm run dev                # next dev -p 3001    →  http://localhost:3001
```

### Environment files

| File | Required vars |
|------|---------------|
| `klow_server/.env` | `DATABASE_URL`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE`, `PORT` |
| `klow_admin/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |
| `klow_web/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |

### Re-seeding the dev DB

```bash
cd klow_server
npx tsx prisma/seed.ts     # re-imports KLOW/data/mock.ts → Postgres
```

The seed is idempotent (uses upserts keyed on the original mock IDs) so it's safe to re-run.

### Inspecting the DB

```bash
cd klow_server
npx prisma studio          # opens GUI at http://localhost:5555
```

---

## Future Expansion (Designed-In)

The module pattern was chosen specifically so that the next four things are additive, not refactors:

### Authentication

**User-side 인증은 구축 완료** — `klow_server/src/modules/auth/`가 이메일+비밀번호(OTP 인증) + Google OAuth를 제공하고, DB `Session` + httpOnly 쿠키(`klow_sid`)로 세션을 관리한다. `UserGuard`는 쿠키에서 세션을 조회해 `request.user`에 `PublicUser`를 실어주며, `@CurrentUser()` 데코레이터로 핸들러가 꺼내 쓴다. klow_web은 네 진입점(Cart 탭, Me 탭, 상품 상세의 Add to cart / Buy now)에 `useAuthGate` / `useRequireAuth` 훅으로 게이트를 건다.

아직 남은 것:
- **AdminGuard**: 여전히 no-op 스텁. klow_admin 쪽 NextAuth 등으로 붙일 예정.
- **비밀번호 재설정**: `/login` 페이지에 링크만 있고 실제 reset 플로우는 미구현.
- **reCAPTCHA / rate limit**: 회원가입 요청 스팸 방지책은 현재 없음.
- **만료 Session / EmailVerification 정리 크론**: 현재 없음. 테이블이 무한히 늘지 않도록 주기 작업 추가 필요.

### PG 심사 / 전자상거래법 compliance

결제 연동 + PG사(Eximbay) 심사에 요구되는 표시·동의·정보제공·트레이서빌리티 요소를 모두 구축한 상태. 자세한 결제 흐름은 Payment system 섹션 참고.

- **전역 푸터** (`klow_web/src/components/layout/Footer.tsx`) — 사업자정보, 고객센터(운영시간 포함), 법적 페이지 링크, ftc.go.kr 통신판매업 조회 링크. 로그인 / 회원가입에서만 숨김(fullscreen 레이아웃). 메인(`/`)·체크아웃 포함 모든 일반 라우트에서 노출 — PG 심사 가이드의 "메인+결제 페이지 상시 노출" 요건 대응. `BottomTabBar`의 `VISIBLE_PATHS`를 import해 탭 바가 있는 라우트에는 `mb-[64px]`, 체크아웃의 fixed `Place order` CTA가 있는 라우트에는 `mb-[96px]` 처리해 겹치지 않게 한다.
- **사업자 정보 단일 소스** — `klow_web/src/app/legal/_content/documents.ts`가 `BUSINESS_INFO` / `CONTACT_EMAIL` / `CONTACT_PHONE` / `CS_HOURS` / `COMPANY` 를 export. Footer, FAQ, 상품 상세 StatutoryInfo 모두 여기서 import. 같은 파일에 5개 약관 문서(`terms` / `privacy` / `youth` / `refund` / `business`)를 `{ en, ko }` 번들로 보관 — `LegalDocumentBundle` 타입.
- **이중언어 약관** — `/legal/[slug]?lang=ko` (한국어), 기본 영문. 상단 EN/KO 토글이 같은 슬러그 내에서 언어만 전환. PG 심사원이 직접 확인하는 한국어 본문(이용약관·개인정보처리방침·환불정책 등)을 운영 약관과 동일 데이터 소스로 제공. `LEGAL_MENU` 의 label 도 `{ en, ko }` 객체.
- **체크아웃 동의** (`/checkout`) — 주문 검토 · 이용약관(`/legal/terms`) · 환불정책 · 결제/배송 처리자(Eximbay) 개인정보 제공 4개 체크박스 필수. 모두 체크해야 "Place order" 버튼 활성. 서버는 `agreedToTerms` / `agreedToRefund` / `agreedToPgDataSharing` 를 Zod `literal(true)` 로 강제하고 `Order.termsAgreedAt` / `refundAgreedAt` / `pgDataSharingAgreedAt` / `agreementIp` 4 컬럼에 동의 시각·IP 를 박아 분쟁 증거로 보관. `payment.prepare()` 가 동일 가드를 한 번 더 적용해 어떤 우회 경로로도 동의 없이는 결제창이 안 뜬다.
- **주문 상세 고객 지원 카드** (`klow_web/src/app/orders/[id]/page.tsx` "Need help?") — 이메일 · 고객센터 전화 · `/legal/refund` 진입을 한 카드에 묶어 결제 후 분쟁 시 사용자 진입점을 제공.
- **FAQ 페이지** (`/faq`) — 주문·배송·환불·결제 4개 카테고리 아코디언. `/my` Help center 메뉴에서 링크.
- **상품 상세 환불·배송 안내 카드** (`klow_web/src/app/product/[id]/_components/ShippingRefundInfo.tsx`) — 배송(국제배송 포함·2–3주)·반품/교환(7일 청약철회)·환불(영업일 3일) 요약 + `/legal/refund` 본문 링크. 가이드의 "실물 상품에 환불 정보, 배송/교환 정보 노출" 요건 대응.
- **상품정보제공고시** (화장품법 대응) — `Product` 모델에 `manufacturer`, `countryOfOrigin`, `expiryInfo`, `ingredients`, `precautions`, `qualityAssuranceStandard`, `functionalCertification`, `customerServicePhone` 8개 String 필드(기본값 `""`) 추가. klow_admin 상품 폼에서 입력, klow_web 상품 상세 하단 접이식 "Product information notice" 섹션에서 표시. 비워두면 "contact seller" fallback.
- **위탁업체 표기** — Privacy Policy §5 (entrustment) 에 Amazon Web Services, Inc. / Cloudflare, Inc. / Eximbay Co., Ltd.(주식회사 엑심베이) 를 법인명으로 명시 — 개인정보보호법 §26 의무.

### Payment system (Eximbay)

현재 결제 시스템은 **Eximbay 테스트 머천트**로 동작한다. 자세한 내용은 `payment-integration.md` 참고. 요약:

PG 는 **Eximbay** (해외 카드 acquiring, 결제 통화 USD). `orders/` + `payment/` 모듈이 결제 흐름 전체를 담당한다. 카트는 클라이언트 zustand(`klow-web-cart` localStorage) + 로그인 후 서버 `cart/` 모듈로 replicate.

흐름:
1. `POST /v1/orders` — 카트 + 배송지 + 동의 3 boolean (`literal(true)`) 으로 Order 생성. 서버는 동의 시점·IP 와 시점 `ShopSettings.usdKrwRate` 를 `Order.fxRateSnapshot` 으로 박는다. `Order.subtotal` 은 customer KRW (settlement→customer 환산 후) 정수.
2. `POST /v1/payment/prepare` — Order ownership + paymentStatus=pending + 동의 3종 재검증. Eximbay `/v1/payments/ready` 호출 후 `fgkey` 발급, SDK 호출에 필요한 payment/merchant/buyer/url/settings 를 echo. `amountUsd` 는 `subtotal / fxRateSnapshot` 으로 산출 — admin 이 환율을 갱신해도 이 주문의 USD 금액은 흔들리지 않는다.
3. klow_web 이 Eximbay JS SDK 를 동적 로드(`klow_web/src/lib/eximbay.ts`)해 `EXIMBAY.request_pay()` 호출. `settings.display_type='R'` 으로 같은 탭 결제창.
4. Eximbay 가 `return_url` (`klow_web/api/eximbay/return` route handler) 로 GET 또는 form POST. handler 가 querystring 으로 정규화 후 `/checkout/redirect` (page) 로 303 redirect.
5. `/checkout/redirect` 가 rescode 분기 — 결과를 3 state 로 구분한다:
   - **결제 성공 확정** (`rescode='0000'` + `POST /v1/payment/verify` 성공): 서버가 Eximbay `/v1/payments/verify` 로 재조회 + `fxRateSnapshot` 기준 amount mismatch (≤ $0.01) 검증 + `markPaid` 가 `updateMany({where: paymentStatus=pending})` 의 count 를 확인. count=1 이면 정상 전이, count=0 이면 DB 상태 재조회해서 `paid + 같은 pgTid` 면 멱등 성공, 그 외 상태(failed/cancelled/refunded/다른 pgTid)는 error 로그 + throw. 성공 시 카트 clear → `/checkout/success`.
   - **PG 명시 실패** (`rescode≠'0000'`): 사용자가 결제창을 닫았거나 카드 승인이 거절된 경우. `POST /v1/payment/report-failure` → paymentStatus `pending→failed` (`paymentFailureReason` 컬럼에 사유·시각 부착, 고객 메모와 분리된 운영 디버그용) → `/checkout/failed` (단정적 실패 안내). 재시도는 새 Order 생성으로 강제.
   - **결과 불명** (`rescode='0000'` + verify 실패: 네트워크/서버 장애/상태 충돌): 카드는 청구됐을 가능성이 있으므로 `report-failure` 호출 금지. 사용자를 `/orders/{id}?awaitingVerification=1` 로 라우팅 → 페이지가 실제 `paymentStatus` 를 보여주고 webhook 으로 늦게 paid 확정될 시간을 허용. amber 배너로 "결제 확인 중" 안내.
6. (보강) `POST /webhooks/eximbay` — Eximbay 가 외부 IP 에서 직접 POST. `EXIMBAY_WEBHOOK_IPS` env 화이트리스트 통과만 처리(운영에서 비어있으면 부팅 시 console.warn). 같은 `parseAndMarkPaid` 경로 공유 — verify 와 동시 도착해도 markPaid 의 count 분기로 멱등 처리. 응답 본문 `rescode=0000&resmsg=Success` 안 보내면 Eximbay 가 retry 한다. 상태 충돌(failed/cancelled 로 이미 전이된 주문에 paid webhook) 은 9999 회신 + error 로그 — 운영자 수동 정리 필요.

환불은 `payment.refundOrder({id, pgProvider, pgTid, subtotal, fxRateSnapshot}, reason)` 가 Eximbay `/v1/payments/{pgTid}/cancel` (refund_type='F', 전액) 호출. 호출자(`orders.cancelByUser` / `orders.refundByAdmin`) 가 PG 성공 후 자체 where 절(updateMany)로 paid→refunded 전이 — PG 호출 성공 후 DB 갱신 직전 크래시 시 PG↔DB drift 가능성 있음 (v1 허용, 운영 단계 outbox/idempotency_key 도입 예정).

핵심 안전망:
- **금액 진실은 서버** — 클라가 보낸 금액은 일체 신뢰 안 함. prepare/verify/refund 모두 `Order.subtotal` + `Order.fxRateSnapshot` 기준.
- **fxRateSnapshot** — admin 환율 변경과 주문 결제 시점 사이의 drift 차단.
- **동의 이중 가드** — Zod literal(true) + service 재검증.
- **Webhook IP 화이트리스트** — 위조 webhook 으로 markPaid 트리거 차단. 운영 IP 변경 시 `EXIMBAY_WEBHOOK_IPS` 갱신.
- **paid 전이 정합성** — `updateMany({where: paymentStatus=pending})` 의 count 를 검사. count=1 정상, count=0 + (paid + 같은 pgTid) 멱등, 그 외 throw. "성공 응답은 나갔는데 DB 는 실패/취소" 같은 거짓 성공을 차단.
- **결제 실패 분리** — PG 명시 실패만 `failed` 로 확정 마킹. verify 자체 실패는 결과 불명으로 두고 `/orders/{id}` 의 paymentStatus 가 진실. 카드 청구됐는데 DB 만 failed 가 되는 데이터 부정합 방지.

To-do (not blocking review): partial refund, abandoned-pending order cleanup cron, outbox 기반 환불, payment 모듈 unit test (markPaid 정상 전이 / count=0 멱등 / count=0 충돌 / amount mismatch / webhook IP 차단).

### Mobile native app (RN / iOS)
Calls the same `/v1/*` endpoints. No new server code unless mobile needs new endpoints. If mobile needs auth, the same `UserGuard` works.

### Background jobs
Add `@nestjs/bull` (Redis) or Temporal worker. Same `PrismaService`, same module imports. Use case: send notification when a low-stock product is sold out, recalculate trending feed every N minutes, etc.

---

## Out of Scope (For Now)

- **Admin auth** — `AdminGuard`는 아직 no-op 스텁(사용자 인증은 구축 완료).
- **비밀번호 재설정 / reCAPTCHA / auth rate-limit / 만료 세션 정리 크론** — Authentication 섹션 참고.
- **다중 결제수단 (간편결제·해외 PG):** 현재 Eximbay 통합 결제창(`transaction_type=PAYMENT`)을 단일 노출하며 카드/PayPal/Alipay/WeChat 등은 Eximbay 가 자동 라우팅한다. 결제수단별 UI 분기는 prepare 호출 시 `payment_method` 코드를 채워 확장.
- **FX 자동 갱신:** `usdKrwRate` 는 어드민이 수동으로 갱신. 매일 오전에 외부 FX API 로 자동 업데이트하는 cron 은 미구축.
- **Legacy `KLOW/` retirement** — still shipping its mock-based prototype; `klow_web` is the real public client going forward.
- **Production deployment / CI/CD** — local dev only
- **Type sharing across repos** — `klow_admin/src/lib/constants.ts`, `klow_server/src/common/constants.ts`, and `klow_web/src/lib/types.ts` are intentional hand-mirrored copies. A future shared workspace package will replace this.
- **Pagination** — list endpoints clamp to `take ≤ 200` but have no cursor/page params. klow_web's feed is hard-capped at 200 videos until a cursor API lands. Add when catalogs grow.
