# KLOW Workspace

This directory is the **workspace root** for the KLOW K-beauty platform. It contains six sibling projects, each operated as **its own independent git repository**.

## Workspace Layout

```
/Users/hyson/welkit/klow/
├── KLOW/          ← Legacy mobile webapp (Next.js 14, still uses data/mock.ts; superseded by klow_web)
├── klow_web/      ← Public mobile webapp     (Next.js 14, port 3001, reads /v1/* via TanStack Query)
├── klow_admin/    ← Admin dashboard          (Next.js 14, port 3000, internal CRUD, pure UI client)
├── klow_brand/    ← Brand self-onboarding    (Next.js 14, port 3002, posts /v1/brand/*)
├── klow_server/   ← Backend API              (NestJS 10, port 4000, owns Prisma + Neon + R2)
├── klow_search_server/ ← 인플루언서 검색 백엔드 (NestJS :4100, 자체 Neon DB + R2 bucket `search`; 프론트는 klow_admin 인플루언서 탭 — 자세히는 klow_search_server/CLAUDE.md)
├── docs/          ← Workspace docs           (architecture.md and friends)
├── CLAUDE.md      ← This file
└── .gitignore     ← Excludes the subprojects from the workspace repo
```

## Repo Independence — IMPORTANT

**Each subdirectory is its own git repository with its own history.** The workspace root may be a (separate, lightweight) git repo for docs/CLAUDE.md only.

- **NEVER** stage or commit files inside `KLOW/`, `klow_web/`, `klow_admin/`, `klow_brand/`, `klow_server/`, or `klow_search_server/` from the workspace root.
- The workspace `.gitignore` already excludes these folders.
- When working on a specific subproject, **`cd` into that subdir first**. Its own `CLAUDE.md` or `README.md` (if any) takes precedence over this one.
- When making cross-cutting changes, do them in each repo's own commit/branch — don't try to coordinate via the workspace root.

## Architecture in One Paragraph

`klow_server` (NestJS, port 4000) is the single source of truth for the database (Neon Postgres via Prisma) and file storage (Cloudflare R2). It exposes three URL surfaces: `/admin/*` for full CRUD by `klow_admin`, `/v1/*` for read-only access by `klow_web` (and later, mobile/native apps), and `/v1/brand/*` for self-service write access by `klow_brand` (BrandGuard-protected, scoped to the caller's own brand). All three frontends are pure UI clients — none have Prisma installed. The legacy `KLOW/` project is still wired to `data/mock.ts` and is being phased out in favor of `klow_web`. See `docs/architecture.md` for the full picture, including module conventions, data model, and request flow examples.

## Where Things Live

| What                          | Where                                                                                                   |
|-------------------------------|---------------------------------------------------------------------------------------------------------|
| Database schema               | `klow_server/prisma/schema.prisma`                                                                      |
| Migrations                    | `klow_server/prisma/migrations/`                                                                        |
| Server modules                | `klow_server/src/modules/` (products, brands, creators, videos, reviews, shop, discover, stats, upload, concierge, orders, payment, auth, admin-auth, brand-auth, brand-applications, cart) |
| Server validation (zod)       | `klow_server/src/common/validation.ts`                                                                  |
| Shared product field selects  | `klow_server/src/modules/products/product-selects.ts`                                                   |
| Admin pages (보호)            | `klow_admin/src/app/(authed)/` (products, brands, brand-applications, creators, videos, reviews, orders, concierge-requests, shop-settings, admins) |
| Admin pages (공개)            | `klow_admin/src/app/login/`, `klow_admin/src/app/accept-invite/[token]/`                                |
| Admin API client              | `klow_admin/src/lib/api.ts` (credentials:'include' + 401 자동 /login 리다이렉트)                         |
| Admin upload helper           | `klow_admin/src/lib/upload.ts`                                                                          |
| Admin 인증 클라이언트         | `klow_admin/src/lib/admin-auth.ts`, `klow_admin/src/hooks/useCurrentAdmin.ts`, `klow_admin/src/hooks/useIdleLogout.ts` |
| Admin 인증 모듈               | `klow_server/src/modules/admin-auth/` (service, controller, admins controller, totp, invitation, audit interceptor) |
| AdminGuard + CurrentAdmin     | `klow_server/src/common/guards/admin.guard.ts`, `klow_server/src/common/guards/super-admin.guard.ts`, `klow_server/src/common/decorators/current-admin.decorator.ts` |
| Admin 시드 스크립트           | `klow_server/prisma/seed-admin.ts` (`npm run seed:admin`, env `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`) |
| klow_web pages                | `klow_web/src/app/` (feed, videos, product, creator, shop, discover, concierge, cart, checkout, my)     |
| klow_web UI i18n (앱 전역)    | `klow_web/src/i18n/` (en 단일 원본 → `npm run i18n:fill` 로 ja/zh/vi/th/id/ru 생성) + `useT`/`useLabels` 훅. 가이드: [`klow_web/docs/i18n.md`](./klow_web/docs/i18n.md) |
| klow_brand pages              | `klow_brand/src/app/` (랜딩 `/`, signup, onboarding/{brand,products}, dashboard/products/{new,[id]/edit}) |
| klow_brand API client         | `klow_brand/src/lib/api.ts` + `klow_brand/src/lib/upload.ts`                                            |
| klow_brand 인증 훅            | `klow_brand/src/hooks/useBrandSession.ts`, `klow_brand/src/hooks/useRequireBrandAuth.ts`                |
| klow_brand 로그인/가입 UI     | `klow_brand/src/app/signup/` + `klow_brand/src/components/{LoginModal,SignupModal,Modal,OtpCodeInput}.tsx` + `klow_brand/src/hooks/useCountdown.ts` + `klow_brand/src/lib/phone.ts` (/login 페이지 없음 — 헤더/CTA에서 모달로 처리) |
| Brand 인증 모듈               | `klow_server/src/modules/brand-auth/` (service, controller, brand-session 쿠키 헬퍼)                    |
| Brand 신청 / 제품 모듈        | `klow_server/src/modules/brand-applications/` (public + admin 컨트롤러, 승인/거부 트랜잭션)              |
| BrandGuard + CurrentBrandUser | `klow_server/src/common/guards/brand.guard.ts`, `klow_server/src/common/decorators/current-brand.decorator.ts` |
| klow_web API client           | `klow_web/src/lib/api.ts`                                                                               |
| klow_web TanStack Query hooks | `klow_web/src/hooks/`                                                                                   |
| klow_web 인증 훅              | `klow_web/src/hooks/useSession.ts`, `klow_web/src/hooks/useAuthGate.ts`                                 |
| klow_web 세션 동기화          | `klow_web/src/hooks/useSessionSync.ts` (+ `components/common/SessionSyncMount.tsx` 레이아웃 마운트)      |
| klow_web 장바구니 스토어      | `klow_web/src/store/useCartStore.ts` (`syncedUserId` 기반 자동 서버 replication)                        |
| klow_web 로그인/가입 화면     | `klow_web/src/app/login/`, `klow_web/src/app/signup/`, `klow_web/src/components/auth/`                  |
| 서버 인증 모듈                | `klow_server/src/modules/auth/` (service, controller, password/session, email/phone OTP, Solapi SMS, google strategy) |
| UserGuard + CurrentUser       | `klow_server/src/common/guards/user.guard.ts`, `klow_server/src/common/decorators/current-user.decorator.ts` |
| Admin toast feedback          | `klow_admin/src/components/Toast.tsx` (`useToast()`) + wired into `klow_admin/src/hooks/useFormState.ts` |
| Legacy KLOW mock data         | `KLOW/data/mock.ts`                                                                                     |
| Legacy KLOW pages             | `KLOW/app/`                                                                                             |

## Key Facts

- **Server port:** `4000` (NestJS)
- **Admin port:** `3000` (Next.js dev)
- **klow_web port:** `3001` (Next.js dev, chosen to avoid the admin)
- **klow_brand port:** `3002` (Next.js dev, chosen to avoid web/admin)
- **DB:** Neon Postgres dev branch (Singapore region) — credentials in `klow_server/.env`
- **Object storage:** Cloudflare R2 bucket `klow`, public base `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk:** AWS SDK v3.729+ adds CRC32 checksums that R2 cannot validate. `r2.service.ts` sets `requestChecksumCalculation: 'WHEN_REQUIRED'` to disable this. If presigned uploads break, check this first.
- **CORS:** `klow_server/src/main.ts` already whitelists `http://localhost:*` via regex, so both admin (3000) and klow_web (3001) work out of the box. Swap to an explicit origin list before deploy.
- **Auth (user):** 이메일+비밀번호(OTP 이메일 인증) + Google OAuth. DB `Session` + httpOnly 쿠키(`klow_sid`). `UserGuard`는 실제 세션 검증(klow_server `src/modules/auth/`). klow_web은 `useSession` / `useAuthGate` 훅으로 게이트한다. 자세한 규칙은 `docs/architecture.md`의 **User Authentication** 섹션 참고.
- **User profile & cart 영속화:** `User`에 `country/skinType/concerns` + `CartItem` 테이블. 비로그인 상태에서 입력된 온보딩/카트는 클라이언트 `localStorage`에만 있다가, 로그인 직후 `SessionSyncMount` 훅이 `PATCH /v1/auth/me` + `PUT /v1/cart/merge`(수량 max-merge)로 서버에 승격하고 이후에는 카트 스토어 mutation이 자동으로 `/v1/cart/*`에 replicate된다. Me 탭은 닉네임·국가·피부타입·고민 편집을 `PATCH /v1/auth/me`로 처리한다.
- **Auth (admin):** Email + Password (argon2id) + TOTP 2FA. `Admin` / `AdminSession` / `AdminInvitation` / `AdminLoginAttempt` / `AdminAuditLog` 테이블 + httpOnly 쿠키(`klow_admin_sid`, 24h, 30분 idle). `AdminGuard`가 실제 세션 검증(klow_server `src/modules/admin-auth/`). 슈퍼관리자 초대 기반 프로비저닝 (공개 가입 없음, 시드로 첫 super → `/admins`에서 초대). 로그인 실패 5회 → 15분 락. 모든 admin mutation은 `AdminAuditInterceptor`가 `AdminAuditLog`에 자동 기록(GET 제외, password/code/token 류 redact). TOTP secret은 AES-256-GCM 암호화(`ADMIN_TOTP_ENCRYPTION_KEY` 환경변수, 회전 금지).
- **Auth (brand):** **전화번호 + SMS OTP (Solapi) 가 메인 인증**이고, Email + Password (argon2id) + 이메일 OTP, Google OAuth 는 보조 옵션이다. `BrandUser` / `BrandSession` 테이블 + httpOnly 쿠키(`klow_brand_sid`, 7일 기본). `BrandGuard`가 세션 검증(klow_server `src/modules/brand-auth/`). 공개 자체 가입(invitation 없음, TOTP 없음 — 마찰 최소화). klow_brand 가 `/v1/brand/auth/*` 호출. **`BrandUser.email` / `phone` / `googleId` 모두 nullable + @unique** — 같은 사람이 세 방식으로 따로 가입하면 별개 BrandUser 가 생긴다(완전 독립 정책). 비밀번호는 phone-only 가입자에겐 없음(`passwordHash` nullable). OTP 인증은 `EmailVerification`(이메일) + 신규 `PhoneVerification`(전화) 두 테이블 분리 — `purpose` 로 분기(`brand-signup-otp` / `brand-signup-token` / `brand-signup-phone-otp` / `brand-signup-phone-token` / `brand-login-phone-otp` / `brand-login-phone-token`). 코드는 6자리 / 10분 TTL / 5회 시도제한 / 60초 재발송 쿨다운(phone 전용, `PhoneVerification.lastSentAt`). KR `010` only — 클라(`klow_brand/src/lib/phone.ts`)는 010-1234-5678 자동 포맷, 서버(`brand-auth.service.ts` `normalizePhone`)는 digits 만 저장. SMS 발송은 `klow_server/src/modules/auth/sms.service.ts` 가 `solapi` SDK 의 `send()` 호출 — `SOLAPI_API_KEY` / `SOLAPI_API_SECRET` / `SOLAPI_SENDER` 환경변수(운영 전 솔라피 콘솔에서 발신번호 사전등록 필수). dev 에서 key 가 비어있으면 콘솔로 OTP 로깅(`[DEV sms] ...`). SMS 발송 엔드포인트는 `THROTTLE_TIGHT` (5회/분 per IP) — 솔라피 비용 폭주 + enumeration 동시 차단. 클라 모달은 6자리 입력 컴포넌트 `OtpCodeInput` + 카운트다운 훅 `useCountdown` 으로 공통 추출 (signup 페이지·LoginModal·SignupModal 3곳 재사용). Google OAuth 는 `klow_web` 과 동일한 `GOOGLE_CLIENT_ID/SECRET` 을 공용으로 쓰고 callback URL 만 `GOOGLE_BRAND_CALLBACK_URL` 로 분리 (`/v1/brand/auth/google` → `/google/authorize` → `/google/callback`). 콜백 후 `BRAND_FRONTEND_URL` 로 redirect.
- **제품 가격 모델 (원가+마진+국가별, 2026-06):** 브랜드/어드민이 **원가(`Product.costKrw`) + 마진**을 입력 → **정산가(`Product.salePrice`) = 원가 + 마진**(서버 파생, legacy 행은 `costKrw=null` → salePrice 그대로). **판매가(USD 센트) = `ceil((정산가 + 국가별 2kg 물류비/2) / (1−0.05) / fx × 100)`** — PG 5% 수수료는 `÷0.95`(브랜드 마진을 수수료 후에도 정확히 net으로 회수). **제품 무게는 가격에 영향 없음**(`weightG` legacy, EFS 송장은 입고 시 재측정). **국가별 차등**: `ProductCountryPrice(productId, iso2, marginKrw?, discountPct)` — 국가별 마진 오버라이드(그 국가 정산가=`costKrw+marginKrw`) + 국가별 할인(%, **기간 없음**, >0 항상 적용). 행 없으면 전국가 기본 상속. **국가별 할인 우선, 없으면 글로벌 `Product.discount`(legacy 마케팅 취소선) 폴백**(스택 안 함). **서버가 목적국별 최종가를 계산해 응답에 싣는다** — 공개 read 는 `?country=`(미지정 US 베스트케이스), 응답 `customerPriceUsd`(할인 적용 결제가)/`listPriceUsd`(취소선)/`customerDiscountPercent`. 1라인 계산 단일 출처는 `product-selects.ts priceLine(row, cp, rateKrw, fx)` — 표시(`attachCustomerPricing`)·주문(`orders.create`)·견적(`POST /v1/orders/quote`)이 모두 거쳐 **표시가 == 청구가** 보장. 물류비 정본 `ShippingCountry.productLogisticsCostKrw`(엑셀 `KLOW_가격표`, 어드민 **물류비용** 탭·`seed:product-logistics-cost`), 캐리어 `productCarrier`(직통 10국=EFS/나머지 88국=EMS, 런타임 비교 없음). 주문은 `resolveFixedRate(iso2, addr)`(EFS 제외구역/EMS 반영), 표시는 베스트케이스 — 제외구역 없으면 동일. 미설정국·EFS 제외구역은 **구매 차단**, 캐리어는 `Order.shippingCarrierByBrand`(JSON) 스냅샷. **결제 배송비 = `물류비/2/fx × 브랜드수`**(한 브랜드=한 송장). 프론트: **klow_web 은 서버값 직접 렌더**(구 `useCountryPricing`/`markupDeviationCents` 클라보정 폐기, 체크아웃은 `/v1/orders/quote`로 cent-exact), **klow_brand·klow_admin** 은 `src/lib/cost-pricing.ts`(÷0.95 미러)로 입력 즉시 국가별 판매가/마진/손익 미리보기. 마이그레이션 `20260627124039_add_product_cost_and_country_pricing`. (구 미러 컬럼 `{efs,ems,dhl}RateKrw`·`efsFuelSurchargePerKgKrw` 는 2026-06-23 드롭. 무게 티어 `ShippingRate` 는 시딩 EMS/DHL 비교가로 유지하되 **2026-07 부터 `rateKrw`=업로드 요율표의 통합 최종가 그대로가 표시가** — 구 `emsSpecialFeePerKgKrw`·`dhlFuelSurchargeRate` 재조합은 폐기, 두 컬럼은 dormant.) 자세히는 [`docs/pricing-model.md`](./docs/pricing-model.md) + `klow_server/docs/modules/shipping.md`.
- **시딩 배송비 (국가×무게 고정 표):** 크리에이터 시딩 배송비도 제품처럼 단순화 — 신규 `SeedingRate(iso2, weightG, costKrw)` 표(운영팀이 원가·캐리어·할증·마진을 미리 반영한 `KLOW_시딩_가격표` 고객_가격표, 98개국×71무게티어 0.1~30kg)에서 **무게 올림 조회한 값을 그대로 배송비로 쓴다** — 캐리어 비교·할증 가산·구 ₩1000 정액수수료 전부 제거. 캐리어는 제품 `productCarrier` 재사용(국가별 고정). 경로: `seeding-rate.service` `resolveCost`/`quoteByWeight`(브랜드 발급·견적) + `shipping.service.resolveCarrier`(claim/checkout 송장 캐리어, EFS 제외구역이면 차단). 어드민 **시딩비용** 탭(`klow_admin /seeding-cost`)에서 국가별 무게×비용 수기 편집 + 엑셀 업로드, 초기 적재 시드 `npm run seed:seeding-rates`(`prisma/data/seeding_rates.json`). 구 국가/캐리어 탭은 **'국가 설정'**(enabled·EFS 제외구역만; 캐리어는 국가 고정값 productCarrier — 물류비용 탭에서 관리)으로 축소.
- **Shipping & EFS 송장:** 한 브랜드 = 한 EFS 송장. 한 주문이 N 개 브랜드 제품을 담으면 결제 배송비도 브랜드별 무게 요율의 합(위 무게별 요율 참고), EFS 송장도 N 장(`Shipment` 1개 + `ShipmentItem` N개 라인). 각 브랜드가 자기 송장만 EFS 창고로 발송하기 위함. payload-builder 가 24번 itemCapsule 을 `{...},{...}` multi-item 으로 묶고, 27번 배송비는 송장별 균등 안분(총 / brandCount). 어드민 발급은 `(orderId, brandId)` 그룹 단위(`/admin/shipments/order/:orderId/brand/:brandId`). 자세히는 `docs/architecture.md` Shipment 섹션 참고.
- **Payment (Eximbay):** 결제 통화는 USD. 흐름은 `POST /v1/orders` (동의 3종 + IP + 시점 fxRate snapshot 저장) → `POST /v1/payment/prepare` (동의·ownership 재검증, fgkey echo) → klow_web 에서 Eximbay JS SDK → `return_url` 303 → `/checkout/redirect` → `POST /v1/payment/verify` (Eximbay 재조회 + fxRateSnapshot 기준 금액 검증 + paymentStatus 멱등 전이). 보강 경로: `POST /webhooks/eximbay` (외부 IP 화이트리스트 `EXIMBAY_WEBHOOK_IPS`). 실패 보고: `POST /v1/payment/report-failure` 가 pending→failed 멱등 전이. 환불은 `payment.refundOrder` 가 Eximbay `/v1/payments/{pgTid}/cancel` 호출. PG 심사 안전망은 약관 동의 4 체크박스(Zod `literal(true)` + service 재가드), 동의 시각·IP·fxRate 저장, 이중언어 약관(`/legal/[slug]?lang=ko`) 으로 구성. 자세한 흐름은 `docs/architecture.md` Payment system 섹션 참고.
- **Brand 입점 워크플로우 (구독 게이트 도입 후):** `Brand` 모델에 `status`(draft/pending/approved/rejected/withdrawal_pending/withdrawn) + `submittedById`/`submittedAt`/`approvedAt`/`approvedById`/`rejectionReason` + `pgCustomerKey`(결제 준비 게이트 플래그). `Product` 도 `status`(pending/approved/rejected) + `submittedById`/`submittedAt`/`rejectionReason`. **노출·판매는 단일 게이트 — `PURCHASABLE_PRODUCT_WHERE = PUBLIC_PRODUCT_WHERE`** (`product-selects.ts`). 가입 brand (`submittedById !== null`) 는 `BrandSubscription.status='active'` 동안만 노출/판매, 어드민이 직접 만든 brand (`submittedById === null`) 와 legacy (`brandId === null`) 제품은 구독 게이트 면제. 결제 = 자동 승인이라 어드민 검수 큐는 없다 — 대신 `/admin/brand-subscriptions/*` (구독 관찰 + 강제 해지·환불·정책 위반 reject + 제품 단위 차단). `klow_brand` 의 OnboardingGate 에서 송화인 4 + 계좌 3 필드를 저장하면 `submitForReview()` 가 `pgCustomerKey` 를 발급해 응답하고, 그 뒤 **NicePay 포스타트 빌링**(결제창 없음 — `CardEntryForm` 카드 입력 폼)으로 받은 카드정보(cardNo/expYear/expMonth/idNo/cardPw)를 `POST /v1/brand/subscription/start` 로 보내면, 서버가 secretKey 로 AES 암호화한 `encData` 로 `POST /v1/subscribe/regist`(빌키발급) + `POST /v1/subscribe/{bid}/payments`(첫 결제) + `approveApplication()` 까지 한 트랜잭션. 빌키(`bid`)는 `BillingKey.pgBillingKey`, 거래번호(`tid`)는 `SubscriptionInvoice.pgTid`, `provider='nicepay'`. 정기 청구는 KST 자정 cron (`subscription-billing.cron.ts`) 이 `POST /v1/subscribe/{bid}/payments` 로 처리하고 dunning 은 0/1/3/7 일 (4회 실패 시 `past_due` 확정). PG 어댑터는 `nicepay-billing.adapter.ts`. **카드 원문이 서버를 거치므로(PCI) 저장/로깅하지 않는다.** 자세한 흐름은 [`docs/brand-subscription.md`](./docs/brand-subscription.md) 참고 (2026-06 KCP→NicePay 교체 배너).

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

# Terminal 4 — brand onboarding
cd klow_brand && npm run dev           # http://localhost:3002
```

## Prisma Migrations

- **반드시 `npx prisma migrate dev --name <이름>`만 사용한다.** `migrate deploy`, 수동 SQL 파일 생성, `db push` 등은 사용하지 않는다.
- 이 명령은 interactive 프롬프트가 필요하므로, non-interactive 환경에서 실패하면 사용자에게 직접 실행을 요청한다.

## When Working Here

- **Documentation tasks** (architecture, planning, cross-repo design notes) → write in `docs/` from this workspace root.
- **Code changes** → `cd` into the relevant subproject first. Treat each subproject as a fully isolated repo.
- **Verifying changes across repos** → run each project independently; they communicate over HTTP, not shared imports.

For the full backend architecture, see [`docs/architecture.md`](./docs/architecture.md).
