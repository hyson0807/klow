# KLOW Backend Architecture

## Overview

KLOW is a TikTok-style K-beauty commerce platform. The backend is split across **three independent repositories** that communicate over HTTP:

```
┌──────────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
│  klow_admin          │  │  KLOW (mobile web)  │  │  Future RN/iOS app   │
│  Next.js UI client   │  │  Next.js UI client  │  │  (planned)           │
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

The server was extracted from `klow_admin` (which originally owned Prisma directly) for three reasons:

1. **Single source of truth.** Multiple clients (admin + public webapp + future mobile) need the same data and the same validation rules. Duplicating Prisma + zod across three projects was already painful at three; it would be unmanageable at five.
2. **Payment system is coming.** Cart/orders/webhooks need a stable home that's reachable from multiple clients and from third-party services (Toss, Stripe). They belong in the server, not in any one client.
3. **Auth boundary.** Eventually admin will use NextAuth (cookies) and the public app will use user JWTs. Centralizing both behind one server with two URL prefixes (`/admin/*`, `/v1/*`) keeps that clean.

---

## The Three Repositories

| Repo          | Stack                                              | Role                                              |
|---------------|----------------------------------------------------|---------------------------------------------------|
| `KLOW`        | Next.js 14 + Tailwind + Zustand + Framer Motion    | Public-facing mobile webapp (TikTok-style feed)   |
| `klow_admin`  | Next.js 14 + Tailwind + react-hook-form            | Internal admin dashboard, pure UI client          |
| `klow_server` | NestJS 10 + Prisma 6 + zod                         | Backend API; owns DB + R2; the only repo with Prisma |

Each subdirectory under `/Users/hyson/welkit/klow/` is its own git repo with its own commit history. They share no source code (a future improvement is a shared workspace package for types/constants).

---

## klow_server Architecture

### Stack
- **Framework:** NestJS 10
- **ORM:** Prisma 6
- **Database:** Neon Postgres (dev branch in Singapore)
- **Object storage:** Cloudflare R2 (S3-compatible) via `@aws-sdk/client-s3`
- **Validation:** zod schemas wrapped in a custom `ZodValidationPipe`
- **Port:** `4000`

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
│   │   ├── constants.ts             # PRODUCT_CATEGORY_KEYS, VIDEO_THEMES, ...
│   │   ├── validation.ts            # zod schemas (ProductInput, CreatorInput, ...)
│   │   ├── zod-validation.pipe.ts   # ZodValidationPipe<T> generic pipe
│   │   ├── prisma-utils.ts          # orNotFound() helper for P2025
│   │   └── guards/
│   │       ├── admin.guard.ts       # AdminGuard (no-op stub for now)
│   │       └── user.guard.ts        # UserGuard (no-op stub for now)
│   └── modules/
│       ├── products/
│       │   ├── products.module.ts
│       │   ├── products.service.ts          # ALL business logic
│       │   ├── admin-products.controller.ts → /admin/products (full CRUD)
│       │   └── public-products.controller.ts → /v1/products (GET only)
│       ├── creators/                # nested-routine transactions
│       ├── videos/                  # VideoProduct join transactions
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

Example (`products` module):

```ts
// products.service.ts — single source of truth
@Injectable()
export class ProductsService {
  constructor(private prisma: PrismaService) {}
  findAll(q?: string) { /* one Prisma call */ }
  findOne(id: string) { /* ... */ }
  create(data: ProductInputT) { /* ... */ }
  update(id: string, data: Partial<ProductInputT>) { /* ... */ }
  remove(id: string) { /* ... */ }
}

// admin-products.controller.ts — full CRUD
@Controller('admin/products')
@UseGuards(AdminGuard)
export class AdminProductsController {
  constructor(private products: ProductsService) {}
  @Get()    list(@Query('q') q?: string) { return this.products.findAll(q); }
  @Get(':id') detail(@Param('id') id: string) { return this.products.findOne(id); }
  @Post()   create(@Body(new ZodValidationPipe(ProductInput)) dto: ProductInputT) { ... }
  @Patch(':id') update(...) { ... }
  @Delete(':id') remove(...) { ... }
}

// public-products.controller.ts — read-only
@Controller('v1/products')
export class PublicProductsController {
  constructor(private products: ProductsService) {}
  @Get()    list(@Query('q') q?: string) { return this.products.findAll(q); }
  @Get(':id') detail(@Param('id') id: string) { return this.products.findOne(id); }
}
```

---

## URL Surfaces

| Surface  | Prefix     | Caller                  | Methods                       | Guard                   |
|----------|------------|-------------------------|-------------------------------|-------------------------|
| Admin    | `/admin/*` | klow_admin              | GET / POST / PATCH / DELETE   | `AdminGuard` (stub)     |
| Public   | `/v1/*`    | KLOW webapp (planned)   | GET only                      | none / `UserGuard` later |

### Endpoints (22 routes)

**Stats**
- `GET /admin/stats` → `{ products, creators, videos }` counts

**Products** — full CRUD
- `GET    /admin/products` (search via `?q=`)
- `GET    /admin/products/:id`
- `POST   /admin/products`
- `PATCH  /admin/products/:id`
- `DELETE /admin/products/:id`
- `GET    /v1/products` + `GET /v1/products/:id`

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
- `GET    /v1/videos` + `GET /v1/videos/:id`

**Upload**
- `POST   /admin/upload` → `{ uploadUrl, publicUrl, key }` (R2 presigned PUT URL, valid 10 min)

---

## Data Model

### Relationship Diagram

```
Creator (1) ──< Video (N)
   │              │
   │              └── VideoProduct (N) ── Product
   │                                         │
   └── Routine (N) ── RoutineProduct (N) ────┘
```

### Entities

| Model           | Purpose                                                                 |
|-----------------|-------------------------------------------------------------------------|
| `Product`       | K-beauty product. Includes FOMO fields: `stockLeft`, `viewersNow`, `totalSold`, `rating`, `reviewCount`. |
| `Creator`       | Influencer profile: handle, story, profile/hero images, social URLs, follower count. |
| `Video`         | Short-form reel. References one `Creator` (N:1) and N `Product`s (N:M). |
| `Routine`       | Bundle of products belonging to one `Creator` (morning/evening/weekend). |
| `VideoProduct`  | Explicit join table. Composite PK `(videoId, productId)` + `order` field for drag-reorder. Cascades on delete. |
| `RoutineProduct`| Same pattern for `Routine` ↔ `Product`.                                 |

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

### Critical R2 quirk

`klow_server/src/modules/upload/r2.service.ts` sets:

```ts
requestChecksumCalculation: 'WHEN_REQUIRED',
responseChecksumValidation:  'WHEN_REQUIRED',
```

`@aws-sdk/client-s3` v3.729+ added automatic CRC32 checksum headers (`x-amz-checksum-crc32`, `x-amz-sdk-checksum-algorithm`) on every PUT. R2 does not yet validate these the same way AWS S3 does, and because they're part of the signed headers, the presigned URL signature breaks. Disabling them is the official escape hatch. **If presigned uploads ever break, check this first.**

### CORS

The R2 bucket has a CORS policy that allows PUT from `http://localhost:3000-3003`. If you ever see `No 'Access-Control-Allow-Origin' header` on the browser PUT, update the CORS policy in the Cloudflare dashboard (R2 → klaw → Settings → CORS Policy).

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

### Example 3: KLOW webapp lists videos (planned)

```
KLOW/app/page.tsx (server component)
  ↓ fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/videos`)
PublicVideosController.list()           // klow_server
  ↓ delegates to:
VideosService.findAll()                 // ← same method admin uses
  ↓ prisma.video.findMany({ orderBy: updatedAt desc, take: 200, include: creator + _count })
  ← JSON of latest 200 videos with creator info + tagged-product counts
[KLOW renders the feed]
```

The key thing to notice in Example 3: `VideosService.findAll()` is called by both `AdminVideosController` and `PublicVideosController`. Same code, two URLs. That's the pattern.

---

## Local Development

```bash
# Terminal 1 — backend
cd klow_server
npm run start:dev          # nest start --watch  →  http://localhost:4000

# Terminal 2 — admin
cd klow_admin
npm run dev                # next dev            →  http://localhost:3000

# Terminal 3 (later) — public webapp
cd KLOW
npm run dev                # next dev            →  http://localhost:3001
```

### Environment files

| File | Required vars |
|------|---------------|
| `klow_server/.env` | `DATABASE_URL`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE`, `PORT` |
| `klow_admin/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:4000` |
| `KLOW/.env.local` | (future) `NEXT_PUBLIC_API_URL=http://localhost:4000` |

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
- `UserGuard` → verify user JWT from KLOW webapp

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
- **KLOW webapp wiring to `/v1/*`** — endpoints exist, KLOW still uses `data/mock.ts`
- **Production deployment / CI/CD** — local dev only
- **Type sharing across repos** — `klow_admin/src/lib/constants.ts` and `klow_server/src/common/constants.ts` are intentional duplicates. A future shared workspace package will replace this.
- **Pagination** — list endpoints have `take: 200` floors but no cursor/page params. Add when catalogs grow.
