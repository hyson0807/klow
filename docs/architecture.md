# KLOW Backend Architecture

## Overview

KLOW is a TikTok-style K-beauty commerce platform. The stack is split across **four independent repositories** that communicate over HTTP:

```
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
│  klow_admin          │  │  klaw_web           │  │  Future RN/iOS app   │
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
                │  • Admin/User guards       │
                │  • REST API                │
                └────┬───────────────────┬───┘
                     │                   │
                     ▼                   ▼
           ┌──────────────────┐  ┌─────────────────────┐
           │  Neon Postgres   │  │  Cloudflare R2      │
           │  (via Prisma)    │  │  bucket: klaw       │
           └──────────────────┘  └─────────────────────┘
```

(The legacy `KLOW/` project is a separate Next.js app still wired to `data/mock.ts`; `klaw_web` supersedes it and is the one that actually talks to `/v1/*`.)

The server was extracted from `klow_admin` (which originally owned Prisma directly) for three reasons:

1. **Single source of truth.** Multiple clients (admin + public webapp + future mobile) need the same data and the same validation rules. Duplicating Prisma + zod across three projects was already painful at three; it would be unmanageable at five.
2. **Payment system is coming.** Cart/orders/webhooks need a stable home that's reachable from multiple clients and from third-party services (Toss, Stripe). They belong in the server, not in any one client.
3. **Auth boundary.** Eventually admin will use NextAuth (cookies) and the public app will use user JWTs. Centralizing both behind one server with two URL prefixes (`/admin/*`, `/v1/*`) keeps that clean.

---

## The Four Repositories

| Repo          | Stack                                                       | Role                                                        |
|---------------|-------------------------------------------------------------|-------------------------------------------------------------|
| `klaw_web`    | Next.js 14 + Tailwind + **TanStack Query** + Zustand + Framer Motion | Public mobile webapp (production). Reads `/v1/*`.           |
| `KLOW`        | Next.js 14 + Tailwind + Zustand + Framer Motion             | **Legacy** prototype. Still uses `data/mock.ts`. Phased out. |
| `klow_admin`  | Next.js 14 + Tailwind + react-hook-form                     | Internal admin dashboard, pure UI client                    |
| `klow_server` | NestJS 10 + Prisma 6 + zod                                  | Backend API; owns DB + R2; the only repo with Prisma        |

Each subdirectory under `/Users/hyson/welkit/klow/` is its own git repo with its own commit history. They share no source code (a future improvement is a shared workspace package for types/constants — today `klaw_web/src/lib/types.ts` is a hand-copied mirror of server response shapes).

---

## klow_server Architecture

### Stack
- **Framework:** NestJS 10
- **ORM:** Prisma 6
- **Database:** Neon Postgres (dev branch in Singapore)
- **Object storage:** Cloudflare R2 (S3-compatible) via `@aws-sdk/client-s3`
- **Validation:** zod schemas wrapped in a custom `ZodValidationPipe`
- **Port:** `4000`
- **CORS:** `main.ts` whitelists `http://localhost:*` (regex) so both admin `:3000` and klaw_web `:3001` work in dev.

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
│   │   └── guards/
│   │       ├── admin.guard.ts       # AdminGuard (no-op stub for now)
│   │       └── user.guard.ts        # UserGuard (no-op stub for now)
│   └── modules/
│       ├── products/
│       │   ├── products.module.ts
│       │   ├── products.service.ts          # all Product business logic
│       │   ├── product-selects.ts           # PRODUCT_LIST_SELECT, DISCOVER_SCORING_SELECT
│       │   ├── admin-products.controller.ts → /admin/products (full CRUD)
│       │   └── public-products.controller.ts → /v1/products (GET, with filters)
│       ├── brands/                  # Brand CRUD + Product.brand cache sync on rename
│       ├── creators/                # nested-routine transactions
│       ├── videos/                  # VideoProduct join transactions
│       ├── reviews/                 # auto-aggregates Product.rating/reviewCount
│       ├── concierge/               # user K-beauty concierge requests (public POST + admin list/status)
│       ├── shop/                    # ShopSettings singleton + /v1/shop/today
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

- `PRODUCT_LIST_SELECT` — everything needed to render a product card. Detail-only fields (`ingredients`, `howToUse`, `detailImages`, `recommendedFor`, `concerns`, `sourceUrl`, `totalSold`, `volume`, `step`) are intentionally excluded to keep list payloads small.
- `DISCOVER_SCORING_SELECT` — `PRODUCT_LIST_SELECT` + `concerns` + `recommendedFor`, used by the discover scoring pipeline.

This is the single place to edit if list payload shape needs to change.

---

## URL Surfaces

| Surface  | Prefix     | Caller                  | Methods                       | Guard                   |
|----------|------------|-------------------------|-------------------------------|-------------------------|
| Admin    | `/admin/*` | klow_admin              | GET / POST / PATCH / DELETE   | `AdminGuard` (stub)     |
| Public   | `/v1/*`    | klow_web                | GET + POST (concierge)        | none / `UserGuard` later |

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

**Creators** — full CRUD with nested routines
- `GET    /admin/creators`
- `GET    /admin/creators/:id`  (includes routines + their products in order)
- `POST   /admin/creators`      (creates creator + nested routines + RoutineProduct join rows in one transaction)
- `PATCH  /admin/creators/:id`  (replaces nested routines transactionally)
- `DELETE /admin/creators/:id`  (cascade deletes videos + routines)
- `GET    /v1/creators` + `GET /v1/creators/:id`

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
- `GET    /v1/discover?skinType=&concern=` → `{ persona, recommended, bestsellers, skinTwinCreators, fallback }`
  - When neither param is supplied, returns a **non-personalized fallback** (`fallback: true`): latest products + bestsellers, no creators.
  - Otherwise scores products (skin-type match, concern overlap, review-count social proof) and ranks creators whose `skinType`/`concerns` match the persona. Concerns are expanded through `CONCERN_EXPANSION` (e.g. `hydration → [hydration, soothing]`) before querying.

**Concierge Requests** — user K-beauty product sourcing requests
- `POST   /v1/concierge-requests` — public, no guard. Requires `imageUrl` or `product` (at least one). Creates a pending request.
- `GET    /admin/concierge-requests` (filter: `?status=pending|replied|completed`)
- `PATCH  /admin/concierge-requests/:id` — update status (`pending` → `replied` → `completed`)
- `DELETE /admin/concierge-requests/:id`

**Upload**
- `POST   /admin/upload` → `{ uploadUrl, publicUrl, key }` (R2 presigned PUT URL, valid 10 min). Allowed content types: `image/{webp,jpeg,png,gif}` or `video/{mp4,quicktime,webm}` — SVG is intentionally rejected (XSS risk).

---

## Data Model

### Relationship Diagram

```
Brand (1) ──< Product (N) ──< Review (N)
                 │
                 ├──< VideoProduct (N) ── Video (N) ──> Creator (1)
                 │                                         │
                 └──< RoutineProduct (N) ── Routine (N) ───┘

ShopSettings (singleton, id = "default")
ConciergeRequest (standalone — no FK relations)
```

### Entities

| Model           | Purpose                                                                 |
|-----------------|-------------------------------------------------------------------------|
| `Product`       | K-beauty product. Carries FOMO fields (`stockLeft`, `viewersNow`, `totalSold`), merchandising flags (`isHero`, `isLoss`, `tip`), persona tags (`recommendedFor`, `concerns`), and detail-page content (`detailImages`, `ingredients`, `howToUse`, `detailDescription`, `volume`, `videoClipUrl`, `sourceUrl`). `brand` is a denormalized string cache of the linked `Brand.name`; `brandId` is the authoritative FK. `rating` and `reviewCount` are **server-managed aggregates** computed from `Review` — never accepted from admin input. |
| `Brand`         | K-beauty brand. `name` is unique; `initial`, `tagline`, `logoUrl`, `order` power the admin's brand directory. Renames cascade into `Product.brand` inside a transaction. Delete detaches products (`brandId → null`) rather than blocking. |
| `ShopSettings`  | Singleton row (`id = "default"`) storing merchandising config. Today only `todaysPickConcern` (a `CONCERNS` value). Created lazily on first read. Powers `/v1/shop/today`. |
| `Creator`       | Influencer profile: handle, story, profile/hero images, social URLs, follower count, `skinType`, `concerns`, `country`, `heroVideoUrl`. |
| `Video`         | Short-form reel. References one `Creator` (N:1) and N `Product`s (N:M) via `VideoProduct`. Carries `themes` (enum array) and `forSkinTypes` for discovery. |
| `Routine`       | Bundle of products belonging to one `Creator` (morning/evening/weekend). `savedAmount` is auto-derived from `originalTotal − bundlePrice` server-side. |
| `Review`        | Per-product user review. Mutations recompute `Product.rating` (avg) and `reviewCount` in the same Prisma transaction. |
| `VideoProduct`  | Explicit join table. Composite PK `(videoId, productId)` + `order` field for drag-reorder. Cascades on delete. |
| `RoutineProduct`| Same pattern for `Routine` ↔ `Product`.                                 |
| `ConciergeRequest` | User-submitted K-beauty product sourcing request. Standalone (no FK). Fields: `imageUrl?`, `product?`, `brand?`, `note?`, `status` (`ConciergeStatus` enum: `pending` → `replied` → `completed`). At least `imageUrl` or `product` is required (enforced by Zod). |

### Enums (Postgres-native)

`schema.prisma` declares three native enums used throughout the model:

- `ProductCategoryKey` — `cleanser | toner | serum | cream | mist | suncream | mask`
- `VideoTheme` — `acne | whitening | brightening | antiaging | glow | hydration | pore`
- `TimeOfDay` — `morning | evening | weekend`
- `ConciergeStatus` — `pending | replied | completed`

The string-based `CONCERNS` constant lives in `src/common/constants.ts` and is shared by `ShopSettings.todaysPickConcern` and `CreatorInput.concerns`.

### Why explicit join tables?

Both `VideoProduct` and `RoutineProduct` carry an `order: Int` column so the admin can reorder which products appear first inside a video or routine. Implicit Prisma N:M relations don't support extra columns, so we use explicit join tables. This also lets us add fields like `timestamp`, `mentionType`, or `isPrimary` later without a migration headache.

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

**Bucket:** `klaw`
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

`klow_server/src/main.ts` whitelists `http://localhost:*` via regex so both the admin (`:3000`) and klaw_web (`:3001`) dev servers work out of the box. Replace with an explicit origin list before deployment.

The R2 bucket itself also has a CORS policy allowing PUT from local dev ports. If you ever see `No 'Access-Control-Allow-Origin' header` on the browser PUT, update the CORS policy in the Cloudflare dashboard (R2 → klaw → Settings → CORS Policy).

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

### Example 3: klaw_web renders the TikTok-style feed

```
klaw_web/src/app/page.tsx
  ↓ useVideosQuery() → api.videos.list()         // TanStack Query caches keyed by queryKeys
  ↓ GET http://localhost:4000/v1/videos
PublicVideosController.list()            // klow_server
  ↓ delegates to:
VideosService.findAll()                  // ← same method admin uses
  ↓ prisma.video.findMany({ orderBy: updatedAt desc, take: 200, include: creator + _count })
  ← JSON of latest 200 videos (creator info + tagged-product counts, no product objects)

  For each visible card:
VideoFeedCard                            // klaw_web/src/components/video
  ↓ useVideoQuery(id) → api.videos.detail(id)    // lazy-load detail only for visible cards
  ↓ GET /v1/videos/:id → products[] with order
  [on activeIdx change, usePrefetchVideo warms next 1–2 cards]
```

The key things to notice in Example 3:

- `VideosService.findAll()` is called by both `AdminVideosController` and `PublicVideosController`. Same code, two URLs.
- The list endpoint deliberately omits the products array to keep the payload small; klaw_web fetches detail per-card on demand. A future optimization is to add `products` to the list include on the server and drop the per-card round-trip.
- **klaw_web never uses `useEffect + fetch` directly** — all server state flows through TanStack Query hooks in `klaw_web/src/hooks/`. This is a hard convention.

### Example 4: klaw_web fetches discover recommendations

```
klaw_web/src/app/discover/page.tsx
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
cd klaw_web
npm run dev                # next dev -p 3001    →  http://localhost:3001
```

### Environment files

| File | Required vars |
|------|---------------|
| `klow_server/.env` | `DATABASE_URL`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE`, `PORT` |
| `klow_admin/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |
| `klaw_web/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |

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
Replace the no-op stubs in `klow_server/src/common/guards/`:
- `AdminGuard` → verify NextAuth cookie / session token from klow_admin
- `UserGuard` → verify user JWT from klaw_web

Route signatures don't change. Only the guard implementations change.

### Payment system
Add new modules under `klow_server/src/modules/`:
- `cart/` — `GET/POST/DELETE /v1/cart` (user JWT)
- `orders/` — `POST /v1/orders` (create), `GET /admin/orders` (admin view)
- `payment/` — `POST /v1/payment/checkout` (Toss/Stripe session)
- `webhooks/` — `POST /webhooks/toss`, `POST /webhooks/stripe` (signature-verified, no auth guard)

All four modules share the same `PrismaService` and the same database. Order state is updated by webhooks and read by both admin and user surfaces.

### Mobile native app (RN / iOS)
Calls the same `/v1/*` endpoints. No new server code unless mobile needs new endpoints. If mobile needs auth, the same `UserGuard` works.

### Background jobs
Add `@nestjs/bull` (Redis) or Temporal worker. Same `PrismaService`, same module imports. Use case: send notification when a low-stock product is sold out, recalculate trending feed every N minutes, etc.

---

## Out of Scope (For Now)

- **Auth implementation** — guards are no-op stubs
- **Payment integration** — modules planned but not built
- **Legacy `KLOW/` retirement** — still shipping its mock-based prototype; `klaw_web` is the real public client going forward.
- **Production deployment / CI/CD** — local dev only
- **Type sharing across repos** — `klow_admin/src/lib/constants.ts`, `klow_server/src/common/constants.ts`, and `klaw_web/src/lib/types.ts` are intentional hand-mirrored copies. A future shared workspace package will replace this.
- **Pagination** — list endpoints clamp to `take ≤ 200` but have no cursor/page params. klaw_web's feed is hard-capped at 200 videos until a cursor API lands. Add when catalogs grow.
