# buyer-auth — 구현 계획 (빌드 스펙 정본)

결정 요약은 [`README.md`](./README.md). 상태는 [`../../PROGRESS.md`](../../PROGRESS.md) `§7` 27·28·29행.

## §1 착수 게이트 (불변식)

어기면 소비자 로그인이 깨지거나 사업자 서류가 새거나 세션이 섞인다.

| # | 불변식 |
|---|---|
| G1 | **소비자 인증 무접촉** — `User`·`Session`·`klow_sid`·`/v1/auth/*`·`web-auth.service`·클라 `qk.session`·`useSession` 을 바이어 코드가 **읽지도 쓰지도 않는다.** 재사용은 `EmailVerificationService`·`EmailService`·`common/password`·`common/cookies` 의 **배관**까지만 |
| G2 | **서류 공개 URL 금지** — R2 버킷 `klow`/`klow-staging` 은 공개 버킷이다. 서류 키는 추측 불가(`buyer-docs/<cuid>/<randomBytes>.<ext>`)로 만들고, `publicUrl` 을 **응답·DB·로그 어디에도** 싣지 않는다. 어드민은 `R2Service.getBytes` 서버 프록시로만 받는다 |
| G3 | **가입 토큰 게이트** — 서류 presign 과 `signup` 은 `verify-code` 가 준 15분 토큰 없이 불가. `signup` 이 토큰을 **1회 소비**한다. presign 은 토큰을 소비하지 않고 검증만 한다(파일이 2개) |
| G4 | **바이어 세션은 클라이언트에서만** — `buyer-space-server.ts` 의 ISR fetch(무자격 · `revalidate 60`)에 섞지 않는다. 섞으면 한 바이어의 응답이 캐시로 모두에게 간다 |
| G5 | **새 DB 브랜치 기준선 확인** — fork 직후 `_prisma_migrations` 에 `20261004140057_add_buyer_platform`·`20261005062641_add_ems_dtp_carrier` 가 있는지 SELECT. 없으면 기준선이 틀린 것이다(멈추고 묻는다) |
| G6 | **이메일 정규화 하나** — 저장·조회·OTP 모두 `trim().toLowerCase()`. 소비자·브랜드와 같은 규칙 |
| G7 | **OTP 메일은 영어** — `issueOtp` 는 purpose 접두로 템플릿을 고르고 모르는 접두는 **한국어 소비자 가입 메일**로 떨어진다. `buyer-` 분기를 **먼저** 넣고 나서 purpose 를 쓴다 (구현: 접두 분기 대신 `issueOtp(…, send)` 로 템플릿을 명시 — 2026-10-08 점검) |

## §2 데이터 모델 (A단계)

```prisma
enum BuyerUserStatus { pending verified rejected }
enum BuyerDocumentKind { business_license store_photo }

model BuyerUser {
  id               String          @id @default(cuid())
  email            String          @unique          // G6 정규화
  passwordHash     String
  emailVerifiedAt  DateTime
  name             String
  dial             String                           // "+1"
  phone            String
  country          String                           // iso2
  company          String
  businessType     String                           // 디자인 STEPS[0] 값 — zod enum 으로 막고 DB 는 문자열
  currency         String          @default("USD")
  channels         String[]                         // offline · online 하위 · etc
  website          String?
  interestedBrands String[]                         // Brand.slug — FK 아님(브랜드가 사라져도 가입 기록은 남는다)
  referral         String?
  status           BuyerUserStatus @default(pending)
  statusNote       String?                          // 어드민 메모(바이어에게 안 보임)
  statusChangedAt  DateTime?
  statusChangedById String?                         // Admin.id
  lastSeenAt       DateTime?
  createdAt / updatedAt
  sessions  BuyerSession[]
  documents BuyerUserDocument[]
}

model BuyerSession {        // BrandSession 과 같은 모양 — token @unique, expiresAt, userAgent, ip, lastSeenAt
  ... buyerUserId → BuyerUser onDelete: Cascade, @@index([buyerUserId]) @@index([expiresAt])
}

model BuyerUserDocument {
  id, buyerUserId(Cascade), kind BuyerDocumentKind, r2Key String @unique, fileName, contentType, size Int, createdAt
}
```

- 마이그레이션 `add_buyer_auth` — **신규 테이블 3 + enum 2 뿐이라 롤링 안전.** 백필 없음
- 비밀번호 규칙: 8자 이상(디자인 그대로), 상한 128

## §3 API (A단계)

모두 `/v1/buyer/auth/*` — 기존 `v1/buyer/{home,products,brands,inquiries}` 와 안 겹친다. 쿠키 `klow_buyer_sid`(`BUYER_SESSION_COOKIE_NAME`), TTL `BUYER_SESSION_TTL_DAYS`(기본 30).

| 메서드 · 경로 | 가드 · 스로틀 | 동작 |
|---|---|---|
| `POST send-code` `{email}` | TIGHT | 이미 `BuyerUser` 면 409 `email_taken`. `issueOtp(email,'buyer-signup-otp')` |
| `POST verify-code` `{email, code}` | LOOSE | `verifyOtpAndIssueSignupToken(…,'buyer-signup-otp','buyer-signup-token')` → `{token}` |
| `POST documents/presign` `{token, email, kind, fileName, contentType, size}` | TIGHT | 토큰 **검증만**(G3). pdf/jpeg/png/webp · ≤10MB. → `{uploadUrl, key}` (publicUrl 없음 — G2) |
| `POST signup` `{token, email, password, 프로필…, documents:[{kind,key,fileName,contentType,size}], keepSignedIn}` | TIGHT | 토큰 소비 → 이메일 재중복검사 → 키가 `buyer-docs/` 이고 presign 이 만든 형식인지 확인 → 트랜잭션(계정 + 서류 행) → 세션 + 쿠키 → `me` 모양 |
| `POST login` `{email, password, keepSignedIn}` | LOOSE | 실패는 **401 하나**(`invalid_credentials` — 존재 여부를 드러내지 않는다) |
| `POST logout` | — | 세션 행 삭제 + 쿠키 지움 |
| `GET me` | 쿠키 직접 읽음(가드 없음 · 없으면 401) | 프로필 + `status` + 서류 목록(**파일명·종류만**) |
| `PATCH me` | `BuyerGuard` | 이름·전화·회사·업종·통화·채널·웹사이트·관심 브랜드. 이메일·상태 불가 |
| `POST password-reset/send-otp` `{email}` | TIGHT | 없는 이메일도 **200**(존재 여부 비공개 — 브랜드와 다르게) · 있으면 `issueOtp(…,'buyer-password-reset-otp')` |
| `POST password-reset/verify-otp` | LOOSE | → `{token}` (`buyer-password-reset-token`) |
| `POST password-reset/confirm` `{email, token, password}` | LOOSE | 트랜잭션(해시 갱신 + 그 계정 **전 세션 삭제**) → 새 세션 + 쿠키 |

어드민 `/admin/buyer/accounts/*`(`AdminGuard` · 감사 인터셉터가 자동 기록):

| 메서드 · 경로 | 동작 |
|---|---|
| `GET /admin/buyer/accounts?q=&status=&page=` | 이메일·이름·회사 검색, 상태 필터, 최신순, 서류 개수 |
| `GET /admin/buyer/accounts/:id` | 가입 정보 전부 + 관심 브랜드(slug → 이름 조인) + 서류 메타 + 상태 이력 칸 |
| `PATCH /admin/buyer/accounts/:id/status` `{status, note?}` | `statusChangedAt`·`statusChangedById` 기록 |
| `GET /admin/buyer/accounts/:id/documents/:docId` | `getBytes` → `Content-Type` 원본 · `Content-Disposition: inline; filename*=` — 어드민 오리진에서 미리보기·다운로드 |

### 세션 규칙

- **슬라이딩**: 세션 검증 시 `expiresAt - now < TTL/2` 이면 `expiresAt = now + TTL` 로 갱신하고 **영속 쿠키였던 경우만** 쿠키 재발급. `lastSeenAt` 은 5분 스로틀(브랜드와 동일). 갱신은 fire-and-forget
- **Keep me signed in 해제** = 서버 TTL 은 같고 쿠키에 `maxAge` 가 없다. 세션 행에 `persistent Boolean` 을 두어 슬라이딩 재발급이 세션 쿠키를 영속 쿠키로 바꾸지 않게 한다(§2 `BuyerSession` 에 컬럼 1개 추가)
- `makeCookieHelpers` 는 늘 `maxAge` 를 붙인다 → `set(res, value, { persistent })` 옵션 인자를 **하위호환으로** 추가(기본 true — 기존 5개 소비자 무변경)
- 만료 세션은 조회 시 하드 삭제(소비자와 동일)

## §4 단계

### A. klow_server (27행)

- **읽을 것**: 이 문서 §1~§3 · `server/modules/brand-auth.md` 의 비밀번호 찾기 절 · `klow_server/src/modules/brand-auth/brand-auth.service.ts` 의 `findUserForPasswordReset`~`resetPassword` · `web-auth/email-verification.service.ts` 전체(짧다) · `common/cookies.ts`
- **건드리는 레포 · 배포 순서**: klow_server 단독(이 단계는 배포하지 않는다 — B·C 와 함께 staging 병합)
- **스키마·데이터 위험**: `add_buyer_auth` — 신규 테이블 3 + enum 2, 롤링 안전, 백필 없음. ⚠️ **git `feat/buyer-auth`(staging 에서) + Neon DB 브랜치 필수**(staging 기준선 `ep-icy-flower` 에서 fork → 이 작업 트리 `.env` `DATABASE_URL` 교체). G5 먼저
- **할 일** — 세션 안 순서 = 정지점
  1. 스키마 + `npx prisma migrate dev --name add_buyer_auth`
  2. `src/modules/buyer-auth/`: `buyer-session.ts`(쿠키 인스턴스 + `common/cookies.ts` 헤더 목록에 한 줄) · `buyer-auth.service.ts` · `public-buyer-auth.controller.ts` · `buyer.guard.ts` · `current-buyer.decorator.ts` · `buyer-auth.module.ts`(imports `WebAuthModule`·`UploadModule`, exports guard·service) · `app.module.ts` 등록. zod 는 `common/validation/buyer-auth.ts` + 배럴 re-export
  3. `email-verification.service.issueOtp` 에 `buyer-` 분기(G7) + `EmailService.sendBuyerSignupCode`/`sendBuyerPasswordResetCode` 영어 템플릿
  4. `admin-buyer-accounts.controller.ts`(같은 모듈) — 어드민 4개
  5. `server/modules/buyer-auth.md` 신설 + `server/README.md` 모듈 색인 · `.env.example` 에 `BUYER_SESSION_COOKIE_NAME=klow_buyer_sid` · `BUYER_SESSION_TTL_DAYS=30`
  - 스펙: 서비스 단위(슬라이딩 경계 · 토큰 1회 소비 · 서류 키 형식 검증 · 비번 찾기 후 전 세션 삭제 · 없는 이메일 reset 200)
- **완료 기준**
  - 검증 3층: `npm run typecheck` · `npm run test:e2e`(cron 무변경) · `npm run start` 라우트 수 증가분 = 15
  - curl 왕복(`Origin: http://localhost:3000` 필수 · `RESEND_API_KEY=` 비워 OTP 를 콘솔로): send-code → verify-code → presign → R2 PUT → signup(`Set-Cookie: klow_buyer_sid` · Max-Age 2592000) → me → logout → login(`keepSignedIn:false` 면 Max-Age 없음) → DB 에서 `expiresAt` 을 10일 뒤로 당긴 뒤 me → 30일로 복구됨 → 비번 찾기 → 구 쿠키 401 → 어드민 목록·상세·상태 변경·서류 다운로드 바이트 일치
  - **분리 확인**: 소비자 `klow_sid` 만으로 `/v1/buyer/auth/me` 401 · 바이어 쿠키만으로 `/v1/auth/me` 401 · 같은 이메일로 소비자 계정이 있어도 바이어 send-code 통과
  - 응답 어디에도 `r2.dev`·`cdn.klow.kr` 서류 URL 이 없다(G2 — `grep`)

### B. klow_web (28행)

- **읽을 것**: 이 문서 §1·§3 · `server/modules/buyer-auth.md` · `plan/buyer-platform/mock-parity.md` · klow_web `components/buyer-space/{KbBuyer,KbSignup,KbAccount}.tsx` · `hooks/useSessionSync.ts`
- **건드리는 레포 · 배포 순서**: klow_web(같은 `feat/buyer-auth`). 배포는 **klow_server 먼저**(뒤집으면 로그인·가입이 404 — 목업보다 못하다)
- **스키마·데이터 위험**: 없음
- **할 일**
  - `lib/api.ts` 에 `api.buyerAuth.*` · 훅 `useBuyerSession`(쿼리키 `['buyer-session']`, 401 → null)
  - `KbBuyerProvider`: `buyer` 를 서버 세션으로 교체 — `ready`·`buyer`·`signOut`·`updateBuyer` 는 서버, `orders`·`placeOrder` 는 목업 그대로(24행). `kb.buyer`·`kb.buyer.last` 는 첫 마운트에 지운다(옛 목업 프로필이 남아 로그인처럼 보이지 않게). 컨텍스트 모양을 유지해 `KbHeader`·`KbPricing`·`KbCheckout`·`KbPayment`·`KbComplete`·`KbAskProduct` 는 무수정이 목표
  - `KbSignup`: 로그인 실연결(에러 문구 · Keep me signed in · **Forgot password 3스텝 화면**) · 가입 Step 2 끝 = send-code(409 면 Step 1 로 되돌려 이메일 칸에 안내) · Step 3 = verify-code → 파일 2개 presign·PUT → signup · 재발송 60초 · "any 6 digits" 문구 삭제 · 완료 화면 = **검수 대기 문구**(pending)
  - `KbAccount`: 상태 배지(verified "Verified buyer" · pending "Under review" · rejected 안내) · 프로필 저장 = `PATCH me` · 서류는 파일명만 · 탈퇴 버튼 → Request 드로어
  - `useSessionSync`: 바이어 경로(`/`, `/shop/*`)에서 정지(G1 — 소비자 국가 PATCH·카트 merge 가 바이어 화면에서 돌지 않게)
  - `mock-parity.md` 의 해당 행을 "실구현됨" 으로 · "디자인과 의도적으로 다른 곳" 에 가입 완료 문구 추가
- **완료 기준**: Playwright(로컬 서버 = A 의 DB 브랜치) — 가입(콘솔 OTP) → "Under review" → PDP MOQ 구간가 블러 해제 → 새로고침·새 탭 유지 → 로그아웃 → 로그인 실패 문구 → 로그인 → 비번 찾기 → 새 비번 로그인 · **소비자 `/login` 로그인 상태와 동시에 있어도 소비자 카트·국가 무변경, 두 쿠키 공존** · 400px 넘침 0 · `npm run build`(`NEXT_PUBLIC_API_URL` 지정)

### C. klow_admin + 마무리 (29행)

순서만 적는다(전제는 A 가 끝나야 확정).
1. 사이드바 "바이어 공간" 그룹에 `바이어 계정`(`/buyer/accounts`) — 목록 `<TableCard>` · 상태 필터 sessionStorage 유지(정본 `tracking/page.tsx`) · 행 전체 → 상세(순수 목록)
2. 상세 — 가입 정보 전부 · 관심 브랜드 · 서류 미리보기(이미지 인라인 / PDF 새 탭)·다운로드 · 상태 변경 + 메모(토스트)
3. 결정 기록 `decisions/storefront.md` 1건 + `decisions/README.md` 표 + `CLAUDE.md` `## 결정 기록` 색인 + Where Things Live 한 줄 · staging 병합 메모(**server → admin·web**, staging DB 에 `add_buyer_auth` 먼저) · env 2줄은 Railway staging/운영에
