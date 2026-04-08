# KLOW Workspace

This directory is the **workspace root** for the KLOW K-beauty platform. It contains three sibling projects, each operated as **its own independent git repository**.

## Workspace Layout

```
/Users/hyson/welkit/klow/
├── KLOW/          ← Mobile webapp     (Next.js 14, public-facing, TikTok-style feed)
├── klow_admin/    ← Admin dashboard   (Next.js 14, internal CRUD, pure UI client)
├── klow_server/   ← Backend API       (NestJS 10, owns Prisma + Neon + R2)
├── docs/          ← Workspace docs    (architecture.md and friends)
├── CLAUDE.md      ← This file
└── .gitignore     ← Excludes the 3 subprojects from the workspace repo
```

## Repo Independence — IMPORTANT

**Each subdirectory is its own git repository with its own history.** The workspace root may be a (separate, lightweight) git repo for docs/CLAUDE.md only.

- **NEVER** stage or commit files inside `KLOW/`, `klow_admin/`, or `klow_server/` from the workspace root.
- The workspace `.gitignore` already excludes these three folders.
- When working on a specific subproject, **`cd` into that subdir first**. Its own `CLAUDE.md` (if any) takes precedence over this one.
- When making cross-cutting changes, do them in each repo's own commit/branch — don't try to coordinate via the workspace root.

## Architecture in One Paragraph

`klow_server` (NestJS, port 4000) is the single source of truth for the database (Neon Postgres via Prisma) and file storage (Cloudflare R2). It exposes two URL surfaces: `/admin/*` for full CRUD by `klow_admin`, and `/v1/*` for read-only access by the public KLOW webapp (and later, mobile/native apps). Both `klow_admin` and `KLOW` are pure UI clients — neither has Prisma installed. See `docs/architecture.md` for the full picture, including module conventions, data model, and request flow examples.

## Where Things Live

| What | Where |
|------|-------|
| Database schema | `klow_server/prisma/schema.prisma` |
| Migrations | `klow_server/prisma/migrations/` |
| Server modules | `klow_server/src/modules/` |
| Server validation (zod) | `klow_server/src/common/validation.ts` |
| Admin pages | `klow_admin/src/app/` |
| Admin API client | `klow_admin/src/lib/api.ts` |
| Admin upload helper | `klow_admin/src/lib/upload.ts` |
| KLOW mock data (legacy) | `KLOW/data/mock.ts` |
| KLOW mobile pages | `KLOW/app/` |

## Key Facts

- **Server port:** `4000` (NestJS)
- **Admin port:** `3000` (Next.js dev)
- **DB:** Neon Postgres dev branch (Singapore region) — credentials in `klow_server/.env`
- **Object storage:** Cloudflare R2 bucket `klaw`, public base `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk:** AWS SDK v3.729+ adds CRC32 checksums that R2 cannot validate. `r2.service.ts` sets `requestChecksumCalculation: 'WHEN_REQUIRED'` to disable this. If presigned uploads break, check this first.
- **Auth:** Currently NONE (admin and user guards are no-op stubs in `klow_server/src/common/guards/`). Will be added later.

## Local Development

```bash
# Terminal 1 — backend
cd klow_server && npm run start:dev    # http://localhost:4000

# Terminal 2 — admin
cd klow_admin && npm run dev           # http://localhost:3000

# Terminal 3 (later) — public webapp
cd KLOW && npm run dev                 # http://localhost:3001 or wherever
```

## When Working Here

- **Documentation tasks** (architecture, planning, cross-repo design notes) → write in `docs/` from this workspace root.
- **Code changes** → `cd` into the relevant subproject first. Treat each subproject as a fully isolated repo.
- **Verifying changes across repos** → run each project independently; they communicate over HTTP, not shared imports.

For the full backend architecture, see [`docs/architecture.md`](./docs/architecture.md).
