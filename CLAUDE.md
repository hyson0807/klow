# KLOW Workspace

This directory is the **workspace root** for the KLOW K-beauty platform. It contains five sibling projects, each operated as **its own independent git repository**.

## 작업 시작 — docs/PROGRESS.md

**세션 경계를 넘는 작업은 [`docs/PROGRESS.md`](./docs/PROGRESS.md) 가 관리한다.** 진행 중인 단계,
다음에 할 일, 세션 절차, 진입/퇴출 기준이 거기 있고 **상태의 정본은 그 파일 하나**다.

사용자가 새 세션에 아래 한 줄을 보내면 그 문서를 열어 `§1` 을 따른다.

```
docs/PROGRESS.md 를 읽고 다음 단계를 진행해 줘.       ← 실행: 다음 단계 하나
docs/PROGRESS.md 를 읽고 <할 일>을 계획에 추가해 줘.   ← 계획: 트랙을 만들고 단계로 쪼갠다
```

**계획 세션은 코드를 건드리지 않는다.** 조사 → 단계 분할 → `docs/<트랙>/` 폴더에 계획 문서 작성 →
진행표 등록까지만 하고 멈춘다. 계획도 한 단계이므로 방금 만든 단계를 이어서 실행하지 않는다.

사용자가 표에 없는 일을 바로 시키면 **막지 말고 그냥 한다** — 진행표는 입구가 아니라 출구에서
작동한다. 끝날 때 `§2 진입 기준`(2세션 이상 · 레포 2개 이상 순서 배포 · 마이그레이션 · 외부 대기 ·
스테이징 완료 후 운영 배포 대기)에 걸리는지 판정해서, 걸리면 행을 만들고 아니면 모듈 문서와
커밋으로 닫는다.

## Workspace Layout

```
/Users/hyson/welkit/klow/
├── klow_web/      ← Public mobile webapp     (Next.js 14, port 3001, reads /v1/* via TanStack Query)
├── klow_admin/    ← Admin dashboard          (Next.js 14, port 3000, internal CRUD, pure UI client)
├── klow_brand/    ← Brand self-onboarding    (Next.js 14, port 3002, posts /v1/brand/*)
├── klow_server/   ← Backend API              (NestJS 10, port 4000, owns Prisma + Neon + R2)
├── klow_search_server/ ← 인플루언서 검색 백엔드 (NestJS :4100, 자체 Neon DB + R2 bucket `search`; 프론트는 klow_admin 인플루언서 탭 — 자세히는 klow_search_server/CLAUDE.md)
├── docs/          ← Workspace docs (PROGRESS.md 진행표 ← 작업 시작점 · README.md 인덱스 · decisions/ = 과거 결정 본문 · reference/ = 현행 시스템 · server/ = API 엔드포인트 문서 · plan/ = 만드는 중 · archive/ = 완료 노트)
├── CLAUDE.md      ← This file
└── .gitignore     ← Excludes the subprojects from the workspace repo
```

## Repo Independence — IMPORTANT

**Each subdirectory is its own git repository with its own history.** The workspace root may be a (separate, lightweight) git repo for docs/CLAUDE.md only.

- **NEVER** stage or commit files inside `klow_web/`, `klow_admin/`, `klow_brand/`, `klow_server/`, or `klow_search_server/` from the workspace root.
- The workspace `.gitignore` already excludes these folders.
- When working on a specific subproject, **`cd` into that subdir first**. Its own `CLAUDE.md` or `README.md` (if any) takes precedence over this one.
- When making cross-cutting changes, do them in each repo's own commit/branch — don't try to coordinate via the workspace root.

## Architecture in One Paragraph

`klow_server` (NestJS, port 4000) is the single source of truth for the database (Neon Postgres via Prisma) and file storage (Cloudflare R2). It exposes four URL surfaces: `/admin/*` for full CRUD by `klow_admin`, `/v1/*` for read access + user flows by `klow_web` (and later, mobile/native apps), `/v1/brand/*` for self-service write access by `klow_brand` (BrandGuard-protected, scoped to the caller's own brand), and `/webhooks/*` for external PG callbacks. All three frontends are pure UI clients — none have Prisma installed. See `docs/reference/architecture.md` for the full picture, and `docs/server/README.md` for the per-module API endpoint reference.

## Where Things Live

| What                          | Where                                                                                                   |
|-------------------------------|---------------------------------------------------------------------------------------------------------|
| Database schema               | `klow_server/prisma/schema.prisma`                                                                      |
| Migrations                    | `klow_server/prisma/migrations/`                                                                        |
| API 엔드포인트 문서           | `docs/server/README.md` (모듈 색인) + `docs/server/modules/<module>.md` — 컨트롤러 변경 시 함께 갱신     |
| Server modules                | `klow_server/src/modules/` (admin-auth, audit-logs, auth, brand-applications, brand-auth, brand-crm, brand-domains, brand-notices, brand-scraper, brands, cart, contact, curated-influencers, customers, fulfillment, instagram, orders, payment, products, promotions, reviews, seeding, settlement, shipments, shipping, shop, stats, subscription, translation, upload) |
| Server validation (zod)       | `klow_server/src/common/validation/` (도메인별 파일 + index.ts 배럴 — import 경로는 `common/validation` 유지)     |
| 가격 커널 (공유)              | `klow_server/src/pricing/` (배럴 — formulas/fx/country-price/promotion/price-line/chargeable-brands). **`modules/` 의 형제**이고 6개 모듈이 의존한다 |
| 3PL 풀필먼트(콜로세움)        | `klow_server/src/modules/fulfillment/` (재고 + 출고신청 + 엑셀 2종 — **EFS·`Shipment` 와 별개 축**) · 어드민 `klow_admin /fulfillment` + 브랜드 상세 `?tab=inventory` · 브랜드 스튜디오 홈 `재고` 탭. 엔드포인트: `docs/server/modules/fulfillment.md` |
| 제품 카탈로그 게이트          | `klow_server/src/modules/products/product-selects.ts` (노출·구매 가능 판정만 — 가격 계산은 위 `src/pricing/`)  |
| 제품 텍스트 로케일화           | `klow_server/src/modules/products/product-translation.service.ts` (MT 캐시 + overlay) · `product-translation-overrides.ts` (브랜드 수동 번역 순수 로직) · klow_brand `studio/_hooks/useProductTranslations.ts` + `_components/TranslationDriftModal.tsx` |
| Admin pages (보호)            | `klow_admin/src/app/(authed)/` (products, brands, brand-subscriptions, brand-withdrawals, reviews, orders, refunds, returns, shipments, tracking, sales-report, settlement, promotions, influencers, customers, seeding-cost, shipping-countries, shipping-rates, fulfillment, audit-logs, admins) |
| Admin pages (공개)            | `klow_admin/src/app/login/`, `klow_admin/src/app/accept-invite/[token]/`                                |
| Admin API client              | `klow_admin/src/lib/api/` (도메인별 파일 + index.ts 배럴 — import 경로는 `@/lib/api` 유지). 하부 `client.ts` 가 `BASE`·`fetchJson`·`postMultipart`·`downloadFile`·`extractApiError` 소유 (credentials:'include' + 401 자동 /login 리다이렉트, 단 `/admin/auth/*` 는 자체 처리) |
| Admin upload helper           | `klow_admin/src/lib/upload.ts`                                                                          |
| Admin 인증 클라이언트         | `klow_admin/src/lib/admin-auth.ts`, `klow_admin/src/hooks/useCurrentAdmin.ts`, `klow_admin/src/hooks/useIdleLogout.ts` |
| Admin 인증 모듈               | `klow_server/src/modules/admin-auth/` (service, controller, admins controller, totp, invitation, audit interceptor) |
| AdminGuard + CurrentAdmin     | `klow_server/src/modules/admin-auth/admin.guard.ts`, `klow_server/src/modules/admin-auth/super-admin.guard.ts`, `klow_server/src/modules/admin-auth/current-admin.decorator.ts` |
| Admin 시드 스크립트           | `klow_server/prisma/seed/seed-admin.ts` (`npm run seed:admin`, env `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`) |
| klow_web pages                | `klow_web/src/app/` (product, `[brandSlug]`, brand, shop, cart, checkout, orders, track, seed, my, login, signup, legal, faq, customer-center) |
| klow_web UI i18n (앱 전역)    | `klow_web/src/i18n/` (en 단일 원본 → `npm run i18n:fill` 로 ja/zh/vi/th/id/ru/ar 생성) + `useT`/`useLabels` 훅. 가이드: [`klow_web/docs/i18n.md`](./klow_web/docs/i18n.md) |
| klow_brand pages              | `klow_brand/src/app/` (랜딩 `/`, signup, legal, `(authed)/`{studio(제품 관리), promotions, creators, seeding, instagram, crm, settings}) |
| Instagram 연동 모듈           | `klow_server/src/modules/instagram/` (client, service, connect/resource 컨트롤러, refresh cron, token crypto) + `klow_brand/src/app/(authed)/instagram/`. 가이드: `docs/instagram-integration.md`, 엔드포인트: `docs/server/modules/instagram.md` |
| klow_brand API client         | `klow_brand/src/lib/api.ts` + `klow_brand/src/lib/upload.ts`                                            |
| klow_brand 인증 훅            | `klow_brand/src/hooks/useBrandSession.ts`, `klow_brand/src/hooks/useRequireBrandAuth.ts`                |
| klow_brand 로그인/가입 UI     | `klow_brand/src/app/signup/` + `klow_brand/src/components/{LoginModal,SignupModal,Modal,OtpCodeInput}.tsx` + `klow_brand/src/hooks/useCountdown.ts` + `klow_brand/src/lib/phone.ts` (/login 페이지 없음 — 헤더/CTA에서 모달로 처리) |
| Brand 인증 모듈               | `klow_server/src/modules/brand-auth/` (service, controller, brand-session 쿠키 헬퍼)                    |
| klow_brand 설정 > 로그인 번호 | `klow_brand/src/app/(authed)/settings/_components/PhoneSection.tsx` (계정당 번호 N개 추가/삭제/대표지정) |
| klow_brand 설정 > 이메일 연결 | `klow_brand/src/app/(authed)/settings/_components/EmailSection.tsx` (전화 계정에 이메일+비번 연결 / 구글 계정 비번 설정) |
| Brand 신청 / 제품 모듈        | `klow_server/src/modules/brand-applications/` (public + admin 컨트롤러, 승인/거부 트랜잭션)              |
| BrandGuard + CurrentBrandUser | `klow_server/src/modules/brand-auth/brand.guard.ts`, `klow_server/src/modules/brand-auth/current-brand.decorator.ts` |
| klow_web API client           | `klow_web/src/lib/api.ts`                                                                               |
| klow_web TanStack Query hooks | `klow_web/src/hooks/`                                                                                   |
| klow_web 인증 훅              | `klow_web/src/hooks/useSession.ts`, `klow_web/src/hooks/useAuthGate.ts`                                 |
| klow_web 세션 동기화          | `klow_web/src/hooks/useSessionSync.ts` (+ `components/common/SessionSyncMount.tsx` 레이아웃 마운트)      |
| klow_web 장바구니 스토어      | `klow_web/src/store/useCartStore.ts` (`syncedUserId` 기반 자동 서버 replication)                        |
| klow_web 로그인/가입 화면     | `klow_web/src/app/login/`, `klow_web/src/app/signup/`, `klow_web/src/components/auth/`                  |
| 서버 인증 모듈                | `klow_server/src/modules/web-auth/` (service, controller, password/session, email/phone OTP, Solapi SMS, google strategy) |
| UserGuard + CurrentUser       | `klow_server/src/modules/web-auth/user.guard.ts`, `klow_server/src/modules/web-auth/current-user.decorator.ts` |
| Admin toast feedback          | `klow_admin/src/components/Toast.tsx` (`useToast()`) + wired into `klow_admin/src/hooks/useFormState.ts` |

## klow_server 코드 구조 규칙 (2026-08 정리에서 확정)

`src/` 를 정리하면서 세운 불변식이다. 어기면 정리 전 상태로 되돌아간다.

1. **`src/` 는 정확히 3레벨: `src/<area>/<module>/<file>.ts`.** 모듈 안에 `__tests__/` 외 하위 폴더를 만들지 않는다. 이 깊이를 지키기 때문에 소스 파일의 상대경로가 최대 `../../` 로 끝나고(`__tests__/` 만 한 단계 더 깊어 `../../../`) **`@/` 경로 별칭이 필요 없다** (별칭은 의도적으로 도입하지 않았다 — `nest build` 가 순수 tsc 라 `tsc-alias` 없이는 `dist/main` 이 `MODULE_NOT_FOUND` 로 죽는다).
2. **`src/common/` 은 `src/modules/` 를 절대 import 하지 않는다.** 지금 0건이고, `eslint.config.mjs` 의 `no-restricted-imports` 가 `src/common/**` 에서 이걸 막는다(위반 시 에러 + 이 문서를 가리키는 메시지). ⚠️ **tsc 는 이걸 못 잡는다** — 경로가 문법적으로 맞으면 방향이 틀려도 통과한다. 그래서 규칙으로 못박았다.
3. **`common/` 입주 조건 — 순서가 있다.**
   - **(불변식, 우선)** `common/` 안의 파일이 import 하는 것은 반드시 `common/` 에 있어야 한다. 이게 규칙 2를 성립시킨다.
   - **(휴리스틱, 차선)** 그 밖에는 **서로 다른 모듈 2개 이상이 쓰고 + 도메인 로직이 없을 때**만 올린다. 둘 중 하나라도 안 되면 소비자 모듈 안에 둔다. 도메인 상수(쿠키 이름 등)는 소유 모듈이 갖는다 — `common/cookies.ts`(배관) vs `modules/web-auth/session.ts`(`klow_sid`) 가 그 예다.
   - ⚠️ **소비자를 셀 때 `common/` 내부 소비자도 센다.** 안 세면 규칙이 스스로 규칙 2를 깨뜨린다 — `common/reserved-slugs.ts` 는 모듈 소비자가 `brand-auth` 하나지만 `common/validation/shared.ts` 도 쓰므로 내리면 `validation` 이 `modules/` 를 import 하게 된다(2026-08 정리에서 실제로 내렸다가 되돌렸다).
   - ⚠️ 기존 예외: `common/constants.ts` 는 도메인 그 자체(HS 코드·EFS 필드길이)라 휴리스틱상 내려가야 하지만 `klow_admin/src/lib/constants.ts` 와의 **의도된 크로스 레포 미러**라 남는다. 새 파일에 이 예외를 확대 적용하지 말 것.
4. **모듈 파일은 평면.** 분류는 폴더가 아니라 **파일명 접미사**가 한다: `.controller` / `.service` / `.module` / `.cron` / `.client` / `.strategy` / `.adapter` / `.mapper` / `.types` / `.prompts`. 컨트롤러는 여기에 **URL surface 접두**를 더 붙인다: `admin-` / `brand-` / `public-` / `webhook-`. 순수 헬퍼는 접미사 없는 명사(`brand-weights.ts`). `helpers/` 같은 폴더를 새로 만들면 분류 축이 둘이 되어 더 나빠진다.
5. **`@Cron` 은 서비스 메서드가 아니라 `*.cron.ts` 파일에.** 파일 목록만으로 스케줄 작업 전체가 보여야 한다.
6. **가격 계산은 `src/pricing/`, 카탈로그 게이트는 `modules/products/product-selects.ts`.** 경계를 흐리지 말 것.
7. **배럴 패턴**(`common/validation/`, `src/pricing/`)은 `index.ts` 에 re-export 만 두고 새 코드는 도메인 파일에 넣는다.

**검증 3층** (파일을 옮기거나 모듈 배선을 바꾼 뒤 반드시):

1. **`npm run typecheck`** — `tsconfig.json`(src + 스펙) **과 `tsconfig.scripts.json`(prisma/·scripts/·test/) 둘 다** 돌린다. ⚠️ **`npx tsc --noEmit` 만 쓰면 안 된다** — `tsconfig.json` 은 `rootDir: ./src` + `exclude: [prisma, test]` 라 `src/` 밖을 구조적으로 못 본다. 그래서 `src/` 를 리팩터링하면 거기서 import 하는 seed/backfill 스크립트가 조용히 깨지고 나머지 검증이 전부 초록불로 통과한다(2026-08 정리에서 백필 3개가 실제로 이렇게 죽었다).
2. **`npm run test:e2e`** — `test/app.e2e-spec.ts` 가 **DB 없이**(PrismaService 를 스텁으로 override — ⚠️ `onModuleInit` 을 가진 provider 가 하나 더 있다: `BrandDomainsService` 가 오리진 스냅샷을 프라이밍하는데, 스텁에는 `brandDomain` 이 없어 **부팅마다 ERROR 로그 한 줄씩(현재 3줄) 남는다**. 그건 의도된 fail-closed 경로이고 스펙은 그대로 통과한다) `AppModule` 을 `init()` 까지 띄운다. 세 가지를 잡는다: ① 35개 모듈 DI 그래프(provider 미등록·미export·순환 모듈), ② **cron 10개 등록 여부**, ③ `CRON_ENABLED='false'` 면 0개. ⚠️ `@Cron` 클래스를 모듈 providers 에 안 넣으면 **조용히 실행되지 않는다** — typecheck 는 통과하고 로그도 안 남는다. 새 cron 을 추가하면 그 스펙의 기대 목록에 이름을 넣을 것.
3. **`npm run start`** — env 가드 + 실제 DB 연결 + 라우트 매핑(현재 361개 — 2026-09-22 실측. 아래 항목들의 기재가 서로 어긋나므로 부팅 로그를 정본으로 볼 것). 1·2 가 커버하지 못하는 건 `main.ts` 의 fail-closed env 검사와 실 DB 접속뿐이다.

⚠️ `npm run lint` 는 `--fix` 를 물고 있어 **리팩터링과 무관한 파일의 기존 포맷 부채까지 건드린다.** diff 를 깨끗하게 유지하려면 `npx eslint <바꾼 파일>` 로 좁혀 쓸 것.

⚠️ `nest-cli.json` 이 `deleteOutDir: false` + `incremental: true` 라 **파일을 대량 이동한 뒤 증분 빌드가 `dist/` 를 반쪽만 남긴다**. 이동 후 첫 빌드 전엔 `rm -rf dist *.tsbuildinfo`.

## Key Facts

- **Server port:** `4000` (NestJS)
- **Admin port:** `3000` (Next.js dev)
- **klow_web port:** `3001` (Next.js dev, chosen to avoid the admin)
- **klow_brand port:** `3002` (Next.js dev, chosen to avoid web/admin)
- **DB:** Neon Postgres dev branch (Singapore region) — credentials in `klow_server/.env`
- **Object storage:** Cloudflare R2 bucket `klow`, public base `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk:** AWS SDK v3.729+ adds CRC32 checksums that R2 cannot validate. `r2.service.ts` sets `requestChecksumCalculation: 'WHEN_REQUIRED'` to disable this. If presigned uploads break, check this first.
- **CORS:** `klow_server/src/main.ts` already whitelists `http://localhost:*` via regex, so both admin (3000) and klow_web (3001) work out of the box. Swap to an explicit origin list before deploy.
- **Auth (user):** 이메일+비밀번호(OTP 이메일 인증) + Google OAuth. DB `Session` + httpOnly 쿠키(`klow_sid`). `UserGuard`는 실제 세션 검증(klow_server `src/modules/web-auth/`). klow_web은 `useSession` / `useAuthGate` 훅으로 게이트한다. 자세한 규칙은 `docs/reference/architecture.md`의 **User Authentication** 섹션 참고.
- **User profile & cart 영속화:** `User`에 `country` + `CartItem` 테이블. 비로그인 상태에서 고른 배송 국가/카트는 클라이언트 `localStorage`에만 있다가, 로그인 직후 `SessionSyncMount` 훅이 `PATCH /v1/auth/me` + `PUT /v1/cart/merge`(수량 max-merge)로 서버에 승격하고 이후에는 카트 스토어 mutation이 자동으로 `/v1/cart/*`에 replicate된다. Me 탭은 닉네임·국가 편집을 `PATCH /v1/auth/me`로 처리한다.
- **Auth (admin):** Email + Password (argon2id) + TOTP 2FA. `Admin` / `AdminSession` / `AdminInvitation` / `AdminLoginAttempt` / `AdminAuditLog` 테이블 + httpOnly 쿠키(`klow_admin_sid`, 24h, 60분 idle — `ADMIN_SESSION_TTL_HOURS`/`ADMIN_IDLE_TIMEOUT_MINUTES` 로 조정). `AdminGuard`가 실제 세션 검증(klow_server `src/modules/admin-auth/`). 슈퍼관리자 초대 기반 프로비저닝 (공개 가입 없음, 시드로 첫 super → `/admins`에서 초대). 로그인 실패 5회 → 15분 락. 모든 admin mutation은 `AdminAuditInterceptor`가 `AdminAuditLog`에 자동 기록(GET 제외, password/code/token 류 redact). TOTP secret은 AES-256-GCM 암호화(`ADMIN_TOTP_ENCRYPTION_KEY` 환경변수, 회전 금지).
- **Auth (brand):** **전화번호 + SMS OTP (Solapi) 가 메인 인증**이고, Email + Password (argon2id) + 이메일 OTP, Google OAuth 는 보조 옵션이다. `BrandUser` / `BrandSession` 테이블 + httpOnly 쿠키(`klow_brand_sid`, 7일 기본). `BrandGuard`가 세션 검증(klow_server `src/modules/brand-auth/`). 공개 자체 가입(invitation 없음, TOTP 없음 — 마찰 최소화). klow_brand 가 `/v1/brand/auth/*` 호출. **`BrandUser.email` / `phone` / `googleId` 모두 nullable + @unique** — 같은 사람이 세 방식으로 따로 가입하면 별개 BrandUser 가 생긴다(완전 독립 정책). 비밀번호는 phone-only 가입자에겐 없음(`passwordHash` nullable). OTP 인증은 `EmailVerification`(이메일) + 신규 `PhoneVerification`(전화) 두 테이블 분리 — `purpose` 로 분기(`brand-signup-otp` / `brand-signup-token` / `brand-signup-phone-otp` / `brand-signup-phone-token` / `brand-login-phone-otp` / `brand-login-phone-token`). 코드는 6자리 / 10분 TTL / 5회 시도제한 / 60초 재발송 쿨다운(phone 전용, `PhoneVerification.lastSentAt`). KR `010` only — 클라(`klow_brand/src/lib/phone.ts`)는 010-1234-5678 자동 포맷, 서버(`brand-auth.service.ts` `normalizePhone`)는 digits 만 저장. SMS 발송은 `klow_server/src/modules/web-auth/sms.service.ts` 가 `solapi` SDK 의 `send()` 호출 — `SOLAPI_API_KEY` / `SOLAPI_API_SECRET` / `SOLAPI_SENDER` 환경변수(운영 전 솔라피 콘솔에서 발신번호 사전등록 필수). dev 에서 key 가 비어있으면 콘솔로 OTP 로깅(`[DEV sms] ...`). SMS 발송 엔드포인트는 `THROTTLE_TIGHT` (5회/분 per IP) — 솔라피 비용 폭주 + enumeration 동시 차단. 클라 모달은 6자리 입력 컴포넌트 `OtpCodeInput` + 카운트다운 훅 `useCountdown` 으로 공통 추출 (signup 페이지·LoginModal·SignupModal 3곳 재사용). Google OAuth 는 `klow_web` 과 동일한 `GOOGLE_CLIENT_ID/SECRET` 을 공용으로 쓰고 callback URL 만 `GOOGLE_BRAND_CALLBACK_URL` 로 분리 (`/v1/brand/auth/google` → `/google/authorize` → `/google/callback`). 콜백 후 `BRAND_FRONTEND_URL` 로 redirect. **로그인 수단 사후 연결 (2026-07)**: 가입 시점엔 세 방식이 별개 계정이지만, **가입 후 설정 페이지에서 서로 붙일 수 있다** — 전화 가입 계정이 `POST /v1/brand/auth/email/{send-otp,verify-otp,link}` 로 **이메일 OTP + 비밀번호를 한 흐름에** 붙이면(`EmailSection`) 기존 `login()`·`ForgotPasswordFlow`·`changePassword` 가 추가 코드 없이 살아난다. 구글 가입 계정(이메일 有·비번 無)은 OTP 없이 `POST /v1/brand/auth/set-password` 로 비밀번호만 설정하면 구글+이메일 둘 다 된다. 이메일은 계정당 1개(`BrandUser.email @unique`, 스키마 변경 없음), purpose `brand-link-email-otp`/`-token` + 전용 메일 템플릿(`sendEmailLinkCode`). 에러코드 `email_already_linked`/`email_required`/`password_already_set`. 자격 추가일 뿐이라 **다른 세션을 무효화하지 않는다**. 부수효과: 비번이 생기면 `removePhone` 의 `last_login_method` 가드가 풀리고, 어드민 담당자 표기가 전화번호→이메일로 바뀐다. **로그인 전화번호 N개 (2026-07)**: `BrandUserPhone(brandUserId, phone @unique, isPrimary, verifiedAt)` 로 **계정당 번호 최대 5개** — 등록된 어느 번호로 OTP 를 받아도 같은 BrandUser 로 로그인된다(번호 변경·담당자 폰 분리에도 계정 유지). **`BrandUserPhone.phone` 이 "이 번호를 누가 쓰는가"의 단일 진실**이라 가입 중복검사·로그인 조회가 전부 이 테이블을 보고(A 계정 보조번호로 B 계정 신규가입 차단), **`BrandUser.phone` 은 `isPrimary` 행의 비정규화 미러**로 남아 알림톡 수신번호 폴백(`payment.service`)·NicePay `buyerTel`(`subscription.service`)·`senderPhone` prefill·어드민 `submittedBy.select` 가 무수정으로 계속 읽는다. 추가/삭제/대표지정은 설정 페이지 `PhoneSection` 에서만(`/v1/brand/auth/phones/*`, BrandGuard, purpose `brand-add-phone-otp`/`-token`). 이메일·구글 가입 계정이 첫 번호를 붙이면 그 즉시 전화 로그인이 열린다. 마지막 번호인데 비번·구글도 없으면 삭제 차단(400 `last_login_method`), 대표 삭제 시 최고참 번호 자동 승계. 마이그레이션 `20260728050713_add_brand_user_phones` + 백필 `npm run backfill:brand-user-phones` (**배포 순서: migrate → 백필 → 코드 → 백필 재실행** — 마지막 재실행이 배포 창에서 구 코드로 가입해 미러만 가진 계정을 주워 담는다). **비밀번호 변경/찾기 (2026-07)**: `passwordHash` 있는 계정만 — 설정 페이지 `change-password`(현재 비밀번호 확인, 현재 세션 제외 전 세션 무효화) + LoginModal 내 `password-reset/{send-otp,verify-otp,confirm}`(이메일 OTP 3스텝, purpose `brand-password-reset-*`, confirm 시 전 세션 무효화 후 자동 로그인). 미가입 404 `user_not_found` / 구글·전화 계정 400 `password_not_set`. `me` 응답에 `hasPassword` 포함(설정 섹션 노출 분기). 자세히는 `docs/server/modules/brand-auth.md`.
- **가격 관련 나머지:** **제품 무게는 판매가·고객 결제 배송비에 영향 없음**(캐리어 분기에만 쓰임 — 아래 배송비 항목). 배송비 정본은 **`SeedingRate(iso2, weightG, costKrw)` 국가×무게 요율표 하나**(어드민 **배송비용** 탭 `/seeding-cost`) — **2026-07-29 통합**으로 구 `ShippingCountry.productLogisticsCostKrw`·어드민 물류비용 탭·`seed:product-logistics-cost` 는 제거됐다(컬럼만 dormant 잔존 — 과거 백필 스크립트가 참조). 주문은 `shipping.service.resolveProductShipping(iso2, addr, brandWeights)` 가 `{customerShippingRateKrw(500g), 브랜드별 캐리어}` 를 1회 산출하고, 공개 응답 `GET /v1/shipping-countries` 는 거기서 파생한 `customerShippingKrw`(구 `productLogisticsCostKrw` 자리)를 싣는다. 미설정국·**배송지원(enabled) 제외국**·EFS 제외구역은 **구매 차단**, 캐리어는 `Order.shippingCarrierByBrand`(JSON) 스냅샷. 프론트: **klow_web 은 서버값 직접 렌더**, **klow_brand·klow_admin** 은 `src/lib/cost-pricing.ts`(÷0.95 미러, 물류비 없음)로 판매가/마진/손익 미리보기. 마이그레이션 `20260718062503_add_product_base_price_fx`(basePriceFxRate) + `20260728063909_pricing_free_shipping`(무료배송·박스규격·브랜드별 배송비) + `country_free_shipping`(무료배송 국가별 전환 — `ProductCountryPrice.freeShipping` 추가 / `Product.freeShipping`·`Brand.freeShippingAll` 드롭. ⚠️ DROP COLUMN 이라 롤링 배포 비안전 — 단일 레플리카 컷오버 또는 2단계 배포). 백필 `npm run backfill:drop-logistics-markup`(**멱등 아님** — 기본 dry-run, `-- --apply` 로만 반영. 기준국 US 기준으로 판매가를 보존하므로 다른 국가는 판매가가 이동한다 — dry-run 델타 표 확인 필수). (구 미러 컬럼 `{efs,ems,dhl}RateKrw`·`efsFuelSurchargePerKgKrw` 는 2026-06-23 드롭. `ShippingRate` 는 시딩 EMS/DHL 비교가 전용, 구 `emsSpecialFeePerKgKrw`·`dhlFuelSurchargeRate` 는 dormant.) 자세히는 [`docs/reference/pricing-model.md`](./docs/reference/pricing-model.md) + [`docs/server/modules/shipping.md`](./docs/server/modules/shipping.md).
- **배송비 요율표 (국가×무게, 시딩·일반주문 공용):** `SeedingRate(iso2, weightG, costKrw)` 표(운영팀이 원가·캐리어·할증·마진을 미리 반영한 `KLOW_시딩_가격표` 고객_가격표, 98개국×71무게티어 0.1~30kg)에서 **무게 올림 조회한 값을 그대로 쓴다** — 런타임 캐리어 비교·할증 가산 없음. **시딩**은 발급 무게의 티어 값이 곧 배송비, **일반 주문**은 **500g 티어 값 그대로**가 고객 결제 배송비(청구 대상 브랜드당 1회)다. 서비스는 `shipping/logistics-rate.service.ts` `LogisticsRateService`(`resolveCost`/`quoteByWeight`/`customerShippingRateByIso2`) — ShippingModule 소유·export(SeedingModule→ShippingModule 의존이 이미 있어 반대면 순환). **캐리어 무게 분기**(`ShippingCountry.seedingCarrierSplitWeightG`: 무게≤분기값 EFS / 초과 EMS, 미설정 시 국가 고정 `productCarrier`)도 2026-07-29 부터 **시딩·일반주문 공용**. 국가 고정 캐리어는 `EFS`/`EMS`/**`EMS_PREMIUM`**(2026-08 추가, 표시명 `EMS-PREMIUM` — prisma enum 값에 하이픈을 못 써 정본은 언더스코어이고 프론트 `carrierLabel()` 이 변환) 중 하나이며 DHL 은 zod 에서 선택 불가다. ⚠️ **무게 분기는 EFS/EMS 로만 갈리므로 `EMS_PREMIUM` 은 분기를 해제한 국가에서만 적용**된다(고정 캐리어 전용). 캐리어는 외부 API 라우팅이 아니라 **EFS 송장 3번 필드 문자열**로만 번역된다(`payload-builder.ts` `CARRIER_TO_EFS_SERVICE_TYPE`: EFS→`Premium`/EMS→`EMS`/EMS_PREMIUM→`EMSPREMIUM`/DHL→`DHL`, `Shipment.efsServiceType` 은 `VarChar(20)`). ⚠️ **이 토큰은 EFS 가 정하므로 추측 금지** — 모르는 값이면 필드가 다 맞아도 `Service type is invalid` 로 발급이 거절된다(EMS_PREMIUM 을 `EMS Premium` 으로 보냈다가 거절당해 EFS 확인 후 공백 없는 대문자로 정정한 선례) — 일반 주문은 **브랜드별 박스 청구중량**(`orders/brand-weights.ts` `brandChargeableWeights` = Σ max(실무게, L×W×H/6)×수량)으로 갈리므로 **한 주문 안에서 브랜드마다 캐리어가 다를 수 있다**(한 브랜드=한 송장). 어드민 **배송비용** 탭(`klow_admin /seeding-cost`)에서 무게×비용 수기 편집 + 엑셀 업로드 + 캐리어(고정값·무게분기) 관리, 초기 적재 시드 `npm run seed:seeding-rates`(`prisma/data/seeding_rates.json`). 엑셀 업로드는 **두 경로가 병존**한다 — 목록 페이지는 `고객_가격표`(국가×무게 매트릭스) **고정 포맷 전용** 파서고, 국가 상세(`/seeding-cost/[iso2]`)는 캐리어에서 받은 **국가 하나짜리 임의 포맷** 요율표를 AI 로 읽는다(2026-08). 목록 페이지는 **왕복**을 지원한다(2026-08) — `GET /admin/seeding-rates/export` 가 `고객_가격표`(배송비) + `청구수수료`(`ShippingCountry.efsBillingFeeKrw`) 2시트를 **임포트 파서가 그대로 읽는 포맷**으로 내보내고, 고쳐서 같은 업로드 입력에 되올리면 반영된다. 수수료 시트는 **선택**이라 없는 파일(운영팀 원본)은 종전과 동일하게 동작하고, **빈 수수료 칸은 미변경**이다(인라인 편집의 "빈 값→1000" 폴백과 의도적으로 다름). 적용이 국가 단위 전체 교체라 엑셀에서 지운 무게는 사라지므로 미리보기가 삭제될 티어를 먼저 보여주고, ⚠️ **티어가 안 온 국가(수수료만 고친 경우)에는 replace 를 걸지 않는다**(걸면 그 국가 요율표가 전멸). 후자는 **AI 에게 레이아웃(어느 시트·어느 열이 무게/가격·단위·통화)만 묻고 금액은 서버가 원본 셀에서 직접 읽어** 자릿수 환각을 원천 차단하고(`shipping/rate-sheet-ai.service.ts`), 열을 잘못 짚으면 미리보기에서 후보 열을 골라 **AI 재호출 없이** 재추출한다. 적용은 `PUT /admin/seeding-rates/:iso2/tiers`(`replace`/`merge`)이고, 전체 교체가 지울 기존 티어(표준 소형 100g/250g/750g 등)는 미리보기에 먼저 띄운다. **이 AI 추출은 어드민 '해외배송 비교요율' 국가 상세(`/shipping-rates/[iso2]?carrier=EMS|DHL`)에도 같은 엔진·같은 모달(`klow_admin/src/components/AiRateImportModal.tsx`)로 붙어 있다**(`POST|PUT /admin/shipping-rates/:carrier/:iso2/…`, `ShippingRateService.aiImportPreview`/`replaceTiers`) — ⚠️ 이쪽은 캐리어 축이 하나 더 있어 **조회·삭제 범위에 carrier 가 반드시 들어가야** 반대 캐리어 요율이 안 지워진다. **비교요율 목록 페이지도 왕복을 지원한다**(2026-08) — `GET /admin/shipping-rates/export?carrier=` 가 **캐리어당 파일 1개**(시트 1장, 이름은 `xlsx-grid.ts` 의 `CARRIER_SHEET_NAMES`)를 내보내고 같은 업로드 입력에 되올리면 반영되며, 미리보기가 삭제될 티어를 먼저 보여준다. 매트릭스 라이터는 배송비용 export 와 공용(`shipping/rate-matrix-xlsx.ts`)이다. ⚠️ **세 탭(EMS·DHL·배송비용)의 내보내기 파일은 시트명만 다르고 형태가 같다** — 그래서 **탭을 잘못 고른 업로드는 리더가 `WrongSheetError`(400)로 거절**한다(안 막으면 미매칭 0건으로 미리보기가 완벽해 보이는 채 EMS 요율이 DHL 로, 혹은 비교요율이 고객 결제 배송비로 저장된다). 2026-08-13 부터 **국가 설정 탭의 `시딩신고가`가 네 번째 내보내기**로 합류했다 — 이쪽은 매트릭스가 아니라 국가=행 목록형이라 형태는 다르지만, **모든 내보내기 시트명은 `xlsx-grid.ts` 의 `EXPORT_SHEET_NAMES` 한 곳에 모아** 네 탭이 서로를 거절한다. ⚠️ **새 내보내기를 추가하면 반드시 그 배열에도 넣을 것** — 빠뜨리면 그 파일이 다른 탭에서 첫 시트 폴백으로 조용히 먹힌다. 단 **아는 시트명일 때만** 거절하고 시트명이 제각각인 운영팀 원본은 종전대로 첫 시트 폴백을 탄다 — 폴백은 그쪽을 받으려고 있는 것이다. ⚠️ **비교요율의 임포트 리더만 SheetJS 가 아니라 자체 OOXML 파서**(`xlsx-grid.ts` — 한컴셀 `x:` 접두사 파일 대응)라 SheetJS 가 쓴 파일을 그게 되읽는 구조다. 라이터를 건드리면 왕복 스펙(`shipping/__tests__/shipping-rate-export.spec.ts`)이 먼저 깨진다. xlsx 다운로드 응답 헤더는 `common/xlsx-download.ts` `sendXlsx()` 공용(`xlsx-upload.ts` 의 반대 방향 짝, 4곳 사용). **'국가 설정'** 탭은 enabled(배송지원 화이트리스트 — 일반 주문만 게이트, 시딩은 무관)·EFS 제외구역 + **시딩 통관 신고가**(인라인 편집 + 엑셀 왕복 — 아래 별도 항목) 담당.
- **Shipping & EFS 송장:** 한 브랜드 = 한 EFS 송장. 한 주문이 N 개 브랜드 제품을 담으면 결제 배송비도 브랜드별 무게 요율의 합(위 무게별 요율 참고), EFS 송장도 N 장(`Shipment` 1개 + `ShipmentItem` N개 라인). 각 브랜드가 자기 송장만 EFS 창고로 발송하기 위함. payload-builder 가 24번 itemCapsule 을 `{...},{...}` multi-item 으로 묶고, 27번 배송비는 송장별 균등 안분(총 / brandCount). 어드민 발급은 `(orderId, brandId)` 그룹 단위(`/admin/shipments/order/:orderId/brand/:brandId`). 자세히는 `docs/reference/architecture.md` Shipment 섹션 참고.
- **Payment (Eximbay):** 결제 통화는 USD. 흐름은 `POST /v1/orders` (동의 3종 + IP + 시점 fxRate snapshot 저장) → `POST /v1/payment/prepare` (동의·ownership 재검증, fgkey echo) → klow_web 에서 Eximbay JS SDK → `return_url` 303 → `/checkout/redirect` → `POST /v1/payment/verify` (Eximbay 재조회 + fxRateSnapshot 기준 금액 검증 + paymentStatus 멱등 전이). 보강 경로: `POST /webhooks/eximbay` (외부 IP 화이트리스트 `EXIMBAY_WEBHOOK_IPS`). 실패 보고: `POST /v1/payment/report-failure` 가 pending→failed 멱등 전이. 환불은 `payment.refundOrder` 가 Eximbay `/v1/payments/{pgTid}/cancel` 호출. PG 심사 안전망은 약관 동의 4 체크박스(Zod `literal(true)` + service 재가드), 동의 시각·IP·fxRate 저장, 이중언어 약관(`/legal/[slug]?lang=ko`) 으로 구성. 자세한 흐름은 `docs/reference/architecture.md` Payment system 섹션 참고.
- **Brand 입점 워크플로우 (구독 게이트 도입 후):** `Brand` 모델에 `status`(draft/pending/approved/rejected/withdrawal_pending/withdrawn) + `submittedById`/`submittedAt`/`approvedAt`/`approvedById`/`rejectionReason` + `pgCustomerKey`(결제 준비 게이트 플래그). `Product` 도 `status`(pending/approved/rejected) + `submittedById`/`submittedAt`/`rejectionReason`. **노출·판매는 단일 게이트 — `PURCHASABLE_PRODUCT_WHERE = PUBLIC_PRODUCT_WHERE`** (`product-selects.ts`). 가입 brand (`submittedById !== null`) 는 `BrandSubscription.status='active'` 동안만 노출/판매, 어드민이 직접 만든 brand (`submittedById === null`) 와 legacy (`brandId === null`) 제품은 구독 게이트 면제. 결제 = 자동 승인이라 어드민 검수 큐는 없다 — 대신 `/admin/brand-subscriptions/*` (구독 관찰 + 강제 해지·환불·정책 위반 reject + 제품 단위 차단). `klow_brand` 의 OnboardingGate 에서 송화인 4 + 계좌 3 필드를 저장하면 `submitForReview()` 가 `pgCustomerKey` 를 발급해 응답하고, 그 뒤 **NicePay 포스타트 빌링**(결제창 없음 — `CardEntryForm` 카드 입력 폼)으로 받은 카드정보(cardNo/expYear/expMonth/idNo/cardPw)를 `POST /v1/brand/subscription/start` 로 보내면, 서버가 secretKey 로 AES 암호화한 `encData` 로 `POST /v1/subscribe/regist`(빌키발급) + `POST /v1/subscribe/{bid}/payments`(첫 결제) + `approveApplication()` 까지 한 트랜잭션. 빌키(`bid`)는 `BillingKey.pgBillingKey`, 거래번호(`tid`)는 `SubscriptionInvoice.pgTid`, `provider='nicepay'`. 정기 청구는 KST 자정 cron (`subscription-billing.cron.ts`) 이 `POST /v1/subscribe/{bid}/payments` 로 처리하고 dunning 은 0/1/3/7 일 (4회 실패 시 `past_due` 확정). PG 어댑터는 `nicepay-billing.adapter.ts`. **카드 원문이 서버를 거치므로(PCI) 저장/로깅하지 않는다.** 자세한 흐름은 [`docs/reference/brand-subscription.md`](./docs/reference/brand-subscription.md) 참고 (2026-06 KCP→NicePay 교체 배너).

## 결정 기록

과거 결정 71건의 본문은 [`docs/decisions/`](docs/decisions/) 에 주제별로 있다. 아래는 그 색인이다.

⚠️ **어떤 코드를 건드리기 전에 그 주제의 `docs/decisions/*.md` 를 읽는다.** 본문 71건 중 55건이
`⚠️⚠️`(돈·장애 직결) 경고를 담고 있어서 색인에 등급 마커를 따로 두지 않았다 — 마커가 거의 모든
줄에 붙으면 신호가 아니라 잡음이다. **제목만 보고 넘기지 말 것.**

### 제품 · 가격 · 번역 — `products.md`

- `2026-07` [제품 가격 모델 (판매가 고정 → 정산 유동 / 물류비 분리)](docs/decisions/products.md#2026-07)
- `2026-07-30` [제품 태그 자유 텍스트 + 고정 키워드 폐지](docs/decisions/products.md#2026-07-30)
- `2026-08` [현장(박람회 부스) QR 판매 + 국가별 현장가](docs/decisions/products.md#2026-08)
- `2026-08-13` [추천 피부 타입 고정 프리셋](docs/decisions/products.md#2026-08-13)
- `2026-08-14` [카테고리 표시명 번역 + 직접 입력](docs/decisions/products.md#2026-08-14)
- `2026-08-14` [국가별 가격 배열 상한 98 → 250](docs/decisions/products.md#2026-08-14-2)
- `2026-08-18` [브랜드 리뷰 직접 등록](docs/decisions/products.md#2026-08-18)
- `2026-08-19` [제품 태그·핵심 성분 드래그 정렬](docs/decisions/products.md#2026-08-19)
- `2026-08-25` [브랜드 수동 번역 — 목업 인라인 편집](docs/decisions/products.md#2026-08-25)
- `2026-09-10` [제품 가리기(`hidden`)는 온라인 전용 — 현장은 안 가려진다](docs/decisions/products.md#2026-09-10)

### 브랜드관 · 프로모션 · 방문 통계 — `storefront.md`

- `2026-08-17` [프로모션(구 캠페인) = 인플루언서 "할인가 브랜드관 링크" 전환](docs/decisions/storefront.md#2026-08-17)
- `2026-08-18` [campaign → promotion 전면 rename](docs/decisions/storefront.md#2026-08-18)
- `2026-08-19` [브랜드관 통계에 판매 분석(국가·제품) + 현장 채널 추가](docs/decisions/storefront.md#2026-08-19)
- `2026-08-19` [브랜드관 퍼널에 결제 단계 추가](docs/decisions/storefront.md#2026-08-19-2)
- `2026-08-19` [브랜드관 방문 통계 + 장바구니 전환](docs/decisions/storefront.md#2026-08-19-3)
- `2026-08-20` [제품 상세(PDP) 직접 진입도 방문 통계에 집계](docs/decisions/storefront.md#2026-08-20)
- `2026-08-20` [브랜드관 방문자 국가 지표](docs/decisions/storefront.md#2026-08-20-2)
- `2026-08-25` [브랜드관 수동 번역 — 한 줄 소개·태그](docs/decisions/storefront.md#2026-08-25)
- `2026-08-25` [브랜드 스토리](docs/decisions/storefront.md#2026-08-25-2)
- `2026-09-18` [브랜드관 공지 팝업](docs/decisions/storefront.md#2026-09-18)
- `2026-09-22` [브랜드 자사몰(카페24) 임베드 버튼 제거](docs/decisions/storefront.md#2026-09-22)

### 배송 · 시딩 · EFS 송장 — `shipping-seeding.md`

- `2026-07-28` [결제 배송비 + 무료배송](docs/decisions/shipping-seeding.md#2026-07-28)
- `2026-07-31` [브랜드 취급 품목 = 통관 분류 정본](docs/decisions/shipping-seeding.md#2026-07-31)
- `2026-08` [시딩 다인원(선착순) 링크](docs/decisions/shipping-seeding.md#2026-08)
- `2026-08-13` [시딩 통관 신고 수량·신고가](docs/decisions/shipping-seeding.md#2026-08-13)
- `2026-08-13` [국내(한국) 시딩 — 브랜드 자체배송](docs/decisions/shipping-seeding.md#2026-08-13-2)
- `2026-08-18` [송장 발급 실패 알림(SMS) + 제한적 자동 재시도](docs/decisions/shipping-seeding.md#2026-08-18)
- `2026-08-18` [EFS 31번 세금식별코드 — 국가별 규칙 테이블화 + 멕시코(MX) RFC](docs/decisions/shipping-seeding.md#2026-08-18-2)
- `2026-08-31` [`/track` 현지 추적 링크 + 시딩 진짜 제품명](docs/decisions/shipping-seeding.md#2026-08-31)
- `2026-09-02` [시딩 "브랜드가 지정" = 브랜드 직접 입력 + 동일 주소 재발송](docs/decisions/shipping-seeding.md#2026-09-02)
- `2026-09-02` [EFS 필드 길이 + 해외 주소 자동완성](docs/decisions/shipping-seeding.md#2026-09-02-2)
- `2026-09-04` [브랜드 알림톡 — 시딩 제품명 교정 + 무가 시딩/재발송 opt-in](docs/decisions/shipping-seeding.md#2026-09-04)
- `2026-09-14` [바코드 라벨 제품명 — 일반 주문·브랜드 지정 시딩 누락](docs/decisions/shipping-seeding.md#2026-09-14)
- `2026-09-22` [3PL 풀필먼트(콜로세움) v1 — 창고 재고 + 출고신청](docs/decisions/shipping-seeding.md#2026-09-22)

### 정산 — `settlement.md`

- `2026-09` [고객 결제 배송비 → 브랜드 정산 이관](docs/decisions/settlement.md#2026-09)
- `2026-09-03` [정산 인식 시점 = 배송완료 → 결제완료](docs/decisions/settlement.md#2026-09-03)
- `2026-09-03` [어드민 정산 ↔ 브랜드 정산 화면 대조](docs/decisions/settlement.md#2026-09-03-2)
- `2026-09-04` [정산 정합성 6건 수정](docs/decisions/settlement.md#2026-09-04)
- `2026-09-09` [브랜드 정산탭 — 송장번호 식별자·전 기간 검색·달러 병기](docs/decisions/settlement.md#2026-09-09)
- `2026-09-10` [정산탭 할인 링크 유입 배지 + '시딩·제품가' → '시딩'](docs/decisions/settlement.md#2026-09-10)
- `2026-09-10` [시딩의 '고객 결제' 달러 = `Order.totalUsd`(제품가 + 배송비) (정정)](docs/decisions/settlement.md#2026-09-10-2)
- `2026-09-14` [브랜드 화면에서 원화 정산액 제거 — `고객 결제(USD)` 만 노출](docs/decisions/settlement.md#2026-09-14)
- `2026-09-14` [엑심베이 정산서 업로드 → 브랜드 정산 원화 보정](docs/decisions/settlement.md#2026-09-14-2)
- `2026-09-14` [어드민 브랜드 상세에 '정산' 탭 — 브랜드 정산탭의 읽기 전용 미러](docs/decisions/settlement.md#2026-09-14-3)

### EFS 배송비 후청구 — `efs-billing.md`

- `2026-07-29` [EFS 배송비 후청구 (efs-billing,  통합)](docs/decisions/efs-billing.md#2026-07-29)
- `2026-09-07` [브랜드 청구서 = PDF → 디자인 엑셀 + 수출신고비·관세 청구](docs/decisions/efs-billing.md#2026-09-07)

### 결제 (PG) — `payment.md`

- `2026-08-17` [결제 확정 3중 방어선](docs/decisions/payment.md#2026-08-17)
- `2026-09-04` [`trust proxy` 오설정으로 `req.ip` 가 Railway 엣지 IP 였다 — 웹훅 상시 403 · rate limit 전역 뭉침](docs/decisions/payment.md#2026-09-04)
- `2026-09-10` [⚠️⚠️ PG 실패 콜백이 결제완료로 확정된 사고 — `rescode` 게이트는 `parseAndMarkPaid` 안에](docs/decisions/payment.md#2026-09-10)

### 브랜드 계정 · 온보딩 · 스튜디오 · CRM — `brand-account.md`

- `2026-07` [Instagram 연동 (댓글→DM)](docs/decisions/brand-account.md#2026-07)
- `2026-08-10` [랜딩 상담 문의 폼](docs/decisions/brand-account.md#2026-08-10)
- `2026-08-24` [회원가입 → 브랜드 주소(slug) 순서 뒤집기](docs/decisions/brand-account.md#2026-08-24)
- `2026-08-25` [`/start` 2단계 — 업종(취급 품목) 선택](docs/decisions/brand-account.md#2026-08-25)
- `2026-08-27` [브랜드 고객 관리(CRM) + 메일 발송](docs/decisions/brand-account.md#2026-08-27)
- `2026-09-18` [스튜디오 홈 우측 패널 탭 재편 — 통계가 앞으로, 편집이 디자인 안으로](docs/decisions/brand-account.md#2026-09-18)
- `2026-09-18` [스튜디오 '재고' 탭 — 풀필먼트 창고 보관 수량 (아직 디자인 목업)](docs/decisions/brand-account.md#2026-09-18-2)
- `2026-09-18` [주문 탭 서브탭·목록 카드를 디자인 탭 톤으로 통일](docs/decisions/brand-account.md#2026-09-18-3)

### 브랜드 커스텀 도메인 — `custom-domain.md`

- `2026-08-21` [브랜드 커스텀 도메인 — P1 서버 기반](docs/decisions/custom-domain.md#2026-08-21)
- `2026-08-21` [브랜드 커스텀 도메인 — P4 브랜드 등록 UI](docs/decisions/custom-domain.md#2026-08-21-2)
- `2026-08-21` [브랜드 커스텀 도메인 — P3 서빙 개시](docs/decisions/custom-domain.md#2026-08-21-3)
- `2026-08-21` [브랜드 커스텀 도메인 — P2 핸드오프 수신부](docs/decisions/custom-domain.md#2026-08-21-4)
- `2026-08-26` [브랜드 커스텀 도메인 대행 구매 — P6](docs/decisions/custom-domain.md#2026-08-26)

### 플랫폼 · 인프라 · i18n · 제거된 기능 — `platform.md`

- `2026-08` [어드민 대시보드 개편 + 브랜드 접속 추적](docs/decisions/platform.md#2026-08)
- `2026-08-10` [크리에이터 / 릴스 영상 기능 제거](docs/decisions/platform.md#2026-08-10)
- `2026-08-11` [컨시어지(concierge) 기능 제거](docs/decisions/platform.md#2026-08-11)
- `2026-09-04` [어드민 컨택트 — 전 브랜드 시딩 수령인·바이어 조회](docs/decisions/platform.md#2026-09-04)
- `2026-09-09` [klow_web 국가 목록의 정본이 서버로 이동 + 배송 예상 기간 5–7일](docs/decisions/platform.md#2026-09-09)
- `2026-09-11` [klow_server 컨테이너 + AWS 이전 준비](docs/decisions/platform.md#2026-09-11)
- `2026-09-11` [아랍어(`ar`) 로케일 신설 — UAE 등 아랍권 13개국](docs/decisions/platform.md#2026-09-11-2)
- `2026-09-11` [현지 통화 표시 — `enabled` 게이트 제거 + 사우디 새 기호](docs/decisions/platform.md#2026-09-11-3)
- `2026-09-11` [바텀시트가 소프트 키보드에 가리던 버그](docs/decisions/platform.md#2026-09-11-4)
- `2026-09-15` [자사몰 URL 분석(`analyze-homepage`) + Playwright 제거](docs/decisions/platform.md#2026-09-15)

## Admin UI Convention — Toast Feedback (required)

어드민(`klow_admin`)의 모든 **등록 / 수정 / 삭제 / 오류**는 반드시 토스트로 사용자에게 표시한다. 조용히 리다이렉트하거나 인라인 텍스트로만 표시하지 않는다. (배경: 브랜드 미선택으로 서버가 `400 brand too_small`을 돌려줬는데 인라인 에러만 떠서 원인 파악이 늦어졌던 사례.)

- 토스트 시스템: `klow_admin/src/components/Toast.tsx` — `<ToastProvider>`가 `app/layout.tsx`에 이미 붙어있고, 컴포넌트에서는 `useToast()`로 `success / error / info`를 호출한다.
- CRUD 폼은 `klow_admin/src/hooks/useFormState.ts`가 이미 토스트를 자동으로 띄우므로 폼마다 따로 배선할 필요 없음.
- `useFormState`를 쓰지 않는 플로우(예: `reviews` 목록, `ReviewManager`)는 `useToast()`를 직접 호출해 동일한 규칙을 지킨다.
- 서버 에러 메시지는 `lib/api/client.ts`가 `Error`로 던지므로 `e.message`를 그대로 토스트에 넘기면 충분(추가 파싱 불필요). `API 400: ` 접두까지 벗기려면 같은 파일의 `extractApiError(e, fallback)`.

**목록 필터 유지**는 `sessionStorage` 로 한다 — ⚠️ URL 쿼리는 이 어드민이 **iframe 탭 셸**이라 구조적으로 안 된다(`TabsContext.normalizeHref` 가 쿼리를 떼어내고, 상세의 '목록으로'가 쿼리 없는 `<Link>` 다). settlement·shipping-rates 에 **미작동 반쪽 구현**이 남아 있으니 복사하지 말 것. 정본은 `tracking/page.tsx` + `orders/page.tsx`. ⚠️ `null` 이 유효한 선택인 값(`yearMonth` = 전체 기간)에 `??` 를 쓰면 매번 기본값으로 튕긴다. 페이지네이션은 저장하지 않는다. **목록 표**는 공용 `<TableCard>` 를 쓰고 `max-w-*` 로 좁히지 않는다(`PageShell` 기본이 전체폭). **행 클릭**은 두 관례가 갈린다 — **순수 목록**(orders·refunds·customers)만 행 전체가 상세로 가고, **체크박스·액션이 있는 작업 화면**(shipments 탭·tracking·efs-billing·settlement 상세)은 **주문번호 셀만 링크**다. ⚠️ 후자에서 행 전체를 열면 선택 상태(로컬 state)가 날아간 채 **같은 iframe 탭이 갈아끼워지고** 주문 상세의 '목록으로'가 `/orders` 라 되돌아올 길이 없다 — 정산 상세는 기본이 전체 선택이라 특히 그렇다. 바꾸려면 선택 상태를 `sessionStorage` 에 먼저 영속화할 것.

자세한 규칙은 `docs/reference/architecture.md`의 **Admin UI Conventions** 섹션 참고.

## Local Development

```bash
# Terminal 1 — backend
cd klow_server && npm run start:dev    # http://localhost:4000

# Terminal 2 — admin
cd klow_admin && npm run dev           # http://localhost:3000

# Terminal 3 — public webapp
cd klow_web && npm run dev             # http://localhost:3001

# Terminal 4 — brand onboarding
cd klow_brand && npm run dev           # http://localhost:3002
```

## Prisma Migrations

- **반드시 `npx prisma migrate dev --name <이름>`만 사용한다.** `migrate deploy`, 수동 SQL 파일 생성, `db push` 등은 사용하지 않는다.
  - 유일한 예외는 **순수 rename** 이다 — `prisma migrate dev` 가 model rename 을 감지하지 못하고 DROP + CREATE 를 생성해 데이터를 통째로 날리기 때문이다(`20260818021500_rename_campaign_to_promotion` 선례).
- 이 명령은 interactive 프롬프트가 필요하므로, non-interactive 환경에서 실패하면 사용자에게 직접 실행을 요청한다.

### ⚠️ 스키마를 바꾸는 작업은 git 브랜치 + **DB 브랜치**를 함께 판다

`staging` 과 그 DB 브랜치에서 직접 마이그레이션하지 않는다. 스키마 변경이 들어가는 작업은 시작할 때 **둘 다** 만든다.

1. **git 브랜치** — `feat/<기능>` (예: `feat/brand-gmail`)
2. **Neon DB 브랜치** — Neon 콘솔에서 staging 기준선 브랜치를 fork 하고, 그 작업 트리의 `klow_server/.env` 에서 `DATABASE_URL` 을 거기로 돌린다

즉 **git 브랜치 하나 = DB 브랜치 하나**이고, staging 기준선 DB 는 `staging` 이 실제로 가진 마이그레이션 개수와 항상 일치해야 한다.

**이유 (2026-08-31 실측).** 미병합 브랜치가 공유 dev DB 에 마이그레이션을 적용해 두면, 다른 브랜치에서 `prisma migrate dev` 를 돌릴 때 **DB 전체 리셋을 요구한다**. 그 브랜치의 모델이 이쪽 `schema.prisma` 에는 없으므로 Prisma 가 드리프트로 보고 그 테이블을 드롭하려 들기 때문이다. 실제로 `feat/domain-purchase` 의 마이그레이션이 공유 dev DB 에 남아 있어 `staging` 에서 마이그레이션을 만들 수 없었고, 풀려면 남의 브랜치 테이블(결제 기록)을 지우는 수밖에 없었다. DB 브랜치를 나눠 두면 이 상황 자체가 생기지 않는다.

**주의**

- ⚠️ **드리프트를 리셋으로 풀지 말 것.** `prisma migrate dev` 가 "We need to reset the schema" 를 띄우면 멈추고 원인을 찾는다 — 리셋은 그 DB 의 데이터를 전부 지운다.
- ⚠️ 남의 브랜치 객체를 지워야만 진행되는 상황이면, **지우기 전에 그 데이터가 다른 DB 브랜치에 살아 있는지 확인**한다. `BrandDomainRegistration`/`BrandDomainCharge` 는 환불 불가 결제 기록이다.
- ⚠️ **production DB 에는 절대 손대지 않는다.** 미병합 기능의 마이그레이션이 프로덕션에 있을 이유가 없고, 실제로 없었다(위 사례에서 프로덕션은 무변경이었다).
- ⚠️ `.env` 를 백업할 거면 파일명을 `.env` 로 시작하되 **`.gitignore` 를 먼저 확인**한다. `klow_server/.gitignore` 는 `.env` 를 **정확히** 매칭해서 `.env.bak.*` 같은 이름은 걸러지지 않고, 그대로 커밋하면 DB 비밀번호가 올라간다.

## When Working Here

- **Documentation tasks** (architecture, planning, cross-repo design notes) → write in `docs/` from this workspace root.
- **Code changes** → `cd` into the relevant subproject first. Treat each subproject as a fully isolated repo.
- **Verifying changes across repos** → run each project independently; they communicate over HTTP, not shared imports.
- **세션 경계를 넘는 작업** → [`docs/PROGRESS.md`](./docs/PROGRESS.md) 의 단계로 관리한다. 끝낼 때 진행 기록 표와 인계 메모를 갱신하지 않았으면 커밋하지 않는다.
- **작업 상태를 문서 제목이나 blockquote 에 적지 않는다** — 정본은 진행표 하나다. `⚠️` 같은 위험 마커는 상태가 아니므로 그대로 쓴다.

For the full backend architecture, see [`docs/reference/architecture.md`](./docs/reference/architecture.md).
