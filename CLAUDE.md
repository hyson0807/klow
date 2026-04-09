# KLOW Workspace

This directory is the **workspace root** for the KLOW K-beauty platform. It contains four sibling projects, each operated as **its own independent git repository**.

## Workspace Layout

```
/Users/hyson/welkit/klow/
├── KLOW/          ← Legacy mobile webapp (Next.js 14, still uses data/mock.ts; superseded by klow_web)
├── klow_web/      ← Public mobile webapp   (Next.js 14, port 3001, reads /v1/* via TanStack Query)
├── klow_admin/    ← Admin dashboard        (Next.js 14, port 3000, internal CRUD, pure UI client)
├── klow_server/   ← Backend API            (NestJS 10, port 4000, owns Prisma + Neon + R2)
├── docs/          ← Workspace docs         (architecture.md and friends)
├── CLAUDE.md      ← This file
└── .gitignore     ← Excludes the 4 subprojects from the workspace repo
```

## Repo Independence — IMPORTANT

**Each subdirectory is its own git repository with its own history.** The workspace root may be a (separate, lightweight) git repo for docs/CLAUDE.md only.

- **NEVER** stage or commit files inside `KLOW/`, `klow_web/`, `klow_admin/`, or `klow_server/` from the workspace root.
- The workspace `.gitignore` already excludes these four folders.
- When working on a specific subproject, **`cd` into that subdir first**. Its own `CLAUDE.md` or `README.md` (if any) takes precedence over this one.
- When making cross-cutting changes, do them in each repo's own commit/branch — don't try to coordinate via the workspace root.

## Architecture in One Paragraph

`klow_server` (NestJS, port 4000) is the single source of truth for the database (Neon Postgres via Prisma) and file storage (Cloudflare R2). It exposes two URL surfaces: `/admin/*` for full CRUD by `klow_admin`, and `/v1/*` for read-only access by `klow_web` (and later, mobile/native apps). Both `klow_web` and `klow_admin` are pure UI clients — neither has Prisma installed. The legacy `KLOW/` project is still wired to `data/mock.ts` and is being phased out in favor of `klow_web`. See `docs/architecture.md` for the full picture, including module conventions, data model, and request flow examples.

## Where Things Live

| What                          | Where                                                                                                   |
|-------------------------------|---------------------------------------------------------------------------------------------------------|
| Database schema               | `klow_server/prisma/schema.prisma`                                                                      |
| Migrations                    | `klow_server/prisma/migrations/`                                                                        |
| Server modules                | `klow_server/src/modules/` (products, brands, creators, videos, reviews, shop, discover, stats, upload) |
| Server validation (zod)       | `klow_server/src/common/validation.ts`                                                                  |
| Shared product field selects  | `klow_server/src/modules/products/product-selects.ts`                                                   |
| Admin pages                   | `klow_admin/src/app/` (products, brands, creators, videos, reviews, shop-settings)                      |
| Admin API client              | `klow_admin/src/lib/api.ts`                                                                             |
| Admin upload helper           | `klow_admin/src/lib/upload.ts`                                                                          |
| klow_web pages                | `klow_web/src/app/` (feed, product, creator, shop, discover, my)                                        |
| klow_web API client           | `klow_web/src/lib/api.ts`                                                                               |
| klow_web TanStack Query hooks | `klow_web/src/hooks/`                                                                                   |
| Legacy KLOW mock data         | `KLOW/data/mock.ts`                                                                                     |
| Legacy KLOW pages             | `KLOW/app/`                                                                                             |

## Key Facts

- **Server port:** `4000` (NestJS)
- **Admin port:** `3000` (Next.js dev)
- **klow_web port:** `3001` (Next.js dev, chosen to avoid the admin)
- **DB:** Neon Postgres dev branch (Singapore region) — credentials in `klow_server/.env`
- **Object storage:** Cloudflare R2 bucket `klow`, public base `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk:** AWS SDK v3.729+ adds CRC32 checksums that R2 cannot validate. `r2.service.ts` sets `requestChecksumCalculation: 'WHEN_REQUIRED'` to disable this. If presigned uploads break, check this first.
- **CORS:** `klow_server/src/main.ts` already whitelists `http://localhost:*` via regex, so both admin (3000) and klow_web (3001) work out of the box. Swap to an explicit origin list before deploy.
- **Auth:** Currently NONE (admin and user guards are no-op stubs in `klow_server/src/common/guards/`). Will be added later.

## Local Development

```bash
# Terminal 1 — backend
cd klow_server && npm run start:dev    # http://localhost:4000

# Terminal 2 — admin
cd klow_admin && npm run dev           # http://localhost:3000

# Terminal 3 — public webapp
cd klow_web && npm run dev             # http://localhost:3001
```

## When Working Here

- **Documentation tasks** (architecture, planning, cross-repo design notes) → write in `docs/` from this workspace root.
- **Code changes** → `cd` into the relevant subproject first. Treat each subproject as a fully isolated repo.
- **Verifying changes across repos** → run each project independently; they communicate over HTTP, not shared imports.

For the full backend architecture, see [`docs/architecture.md`](./docs/architecture.md).
