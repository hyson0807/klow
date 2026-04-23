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
| Server modules                | `klow_server/src/modules/` (products, brands, creators, videos, reviews, shop, discover, stats, upload, concierge, orders, auth, cart) |
| Server validation (zod)       | `klow_server/src/common/validation.ts`                                                                  |
| Shared product field selects  | `klow_server/src/modules/products/product-selects.ts`                                                   |
| Admin pages                   | `klow_admin/src/app/` (products, brands, creators, videos, reviews, concierge-requests, shop-settings)  |
| Admin API client              | `klow_admin/src/lib/api.ts`                                                                             |
| Admin upload helper           | `klow_admin/src/lib/upload.ts`                                                                          |
| klow_web pages                | `klow_web/src/app/` (feed, videos, product, creator, shop, discover, concierge, cart, checkout, my)     |
| klow_web API client           | `klow_web/src/lib/api.ts`                                                                               |
| klow_web TanStack Query hooks | `klow_web/src/hooks/`                                                                                   |
| klow_web 인증 훅              | `klow_web/src/hooks/useSession.ts`, `klow_web/src/hooks/useAuthGate.ts`                                 |
| klow_web 세션 동기화          | `klow_web/src/hooks/useSessionSync.ts` (+ `components/common/SessionSyncMount.tsx` 레이아웃 마운트)      |
| klow_web 장바구니 스토어      | `klow_web/src/store/useCartStore.ts` (`syncedUserId` 기반 자동 서버 replication)                        |
| klow_web 로그인/가입 화면     | `klow_web/src/app/login/`, `klow_web/src/app/signup/`, `klow_web/src/components/auth/`                  |
| 서버 인증 모듈                | `klow_server/src/modules/auth/` (service, controller, password/session/email, google strategy)         |
| UserGuard + CurrentUser       | `klow_server/src/common/guards/user.guard.ts`, `klow_server/src/common/decorators/current-user.decorator.ts` |
| Admin toast feedback          | `klow_admin/src/components/Toast.tsx` (`useToast()`) + wired into `klow_admin/src/hooks/useFormState.ts` |
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
- **Auth (user):** 이메일+비밀번호(OTP 이메일 인증) + Google OAuth. DB `Session` + httpOnly 쿠키(`klow_sid`). `UserGuard`는 실제 세션 검증(klow_server `src/modules/auth/`). klow_web은 `useSession` / `useAuthGate` 훅으로 게이트한다. 자세한 규칙은 `docs/architecture.md`의 **User Authentication** 섹션 참고.
- **User profile & cart 영속화:** `User`에 `country/skinType/concerns` + `CartItem` 테이블. 비로그인 상태에서 입력된 온보딩/카트는 클라이언트 `localStorage`에만 있다가, 로그인 직후 `SessionSyncMount` 훅이 `PATCH /v1/auth/me` + `PUT /v1/cart/merge`(수량 max-merge)로 서버에 승격하고 이후에는 카트 스토어 mutation이 자동으로 `/v1/cart/*`에 replicate된다. Me 탭은 닉네임·국가·피부타입·고민 편집을 `PATCH /v1/auth/me`로 처리한다.
- **Auth (admin):** `AdminGuard`는 여전히 no-op 스텁. 이후 NextAuth 등으로 배선 예정.

## Admin UI Convention — Toast Feedback (required)

어드민(`klow_admin`)의 모든 **등록 / 수정 / 삭제 / 오류**는 반드시 토스트로 사용자에게 표시한다. 조용히 리다이렉트하거나 인라인 텍스트로만 표시하지 않는다. (배경: 브랜드 미선택으로 서버가 `400 brand too_small`을 돌려줬는데 인라인 에러만 떠서 원인 파악이 늦어졌던 사례.)

- 토스트 시스템: `klow_admin/src/components/Toast.tsx` — `<ToastProvider>`가 `app/layout.tsx`에 이미 붙어있고, 컴포넌트에서는 `useToast()`로 `success / error / info`를 호출한다.
- CRUD 폼은 `klow_admin/src/hooks/useFormState.ts`가 이미 토스트를 자동으로 띄우므로 폼마다 따로 배선할 필요 없음.
- `useFormState`를 쓰지 않는 플로우(예: `shop-settings`, `concierge-requests`, `reviews` 목록, `ReviewManager`)는 `useToast()`를 직접 호출해 동일한 규칙을 지킨다.
- 서버 에러 메시지는 `api.ts`가 `Error`로 던지므로 `e.message`를 그대로 토스트에 넘기면 충분(추가 파싱 불필요).

자세한 규칙은 `docs/architecture.md`의 **Admin UI Conventions** 섹션 참고.

## Local Development

```bash
# Terminal 1 — backend
cd klow_server && npm run start:dev    # http://localhost:4000

# Terminal 2 — admin
cd klow_admin && npm run dev           # http://localhost:3000

# Terminal 3 — public webapp
cd klow_web && npm run dev             # http://localhost:3001
```

## Prisma Migrations

- **반드시 `npx prisma migrate dev --name <이름>`만 사용한다.** `migrate deploy`, 수동 SQL 파일 생성, `db push` 등은 사용하지 않는다.
- 이 명령은 interactive 프롬프트가 필요하므로, non-interactive 환경에서 실패하면 사용자에게 직접 실행을 요청한다.

## When Working Here

- **Documentation tasks** (architecture, planning, cross-repo design notes) → write in `docs/` from this workspace root.
- **Code changes** → `cd` into the relevant subproject first. Treat each subproject as a fully isolated repo.
- **Verifying changes across repos** → run each project independently; they communicate over HTTP, not shared imports.

For the full backend architecture, see [`docs/architecture.md`](./docs/architecture.md).
