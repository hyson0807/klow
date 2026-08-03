# brand-auth — 브랜드 사용자 인증

- **모듈 경로**: `src/modules/brand-auth/`
- **주 클라이언트**: `klow_brand` (port 3002)
- **세션 쿠키**: `klow_brand_sid` (httpOnly, 7일 기본)
- **인증 방식 (메인)**: **전화번호 + SMS OTP** (Solapi)
- **인증 방식 (보조)**: Email + Password (argon2id) + 이메일 OTP, Google OAuth
- **공개 가입**: invitation 없음, TOTP 없음 (마찰 최소화)
- **계정 정책**: `BrandUser.email` / `phone` / `googleId` 모두 nullable + @unique. **같은 사람이 세 방식으로 가입하면 별개 BrandUser** (가입 시점 기준). 단 가입 후에는 설정 페이지에서 **로그인 수단을 서로 붙일 수 있다** — 전화번호는 계정당 N개(아래 `BrandUserPhone`), 이메일+비밀번호는 계정당 1개(아래 `email/link`). 그래서 한 계정이 전화·이메일·구글을 동시에 갖고 어느 쪽으로든 로그인할 수 있다.
- **로그인 전화번호는 계정당 N개 (최대 5, 2026-07)**: `BrandUserPhone(brandUserId, phone @unique, isPrimary, verifiedAt)` 이 **"이 번호를 누가 쓰는가"의 단일 진실** — 가입 중복검사·로그인 조회가 모두 이 테이블을 본다(A 계정의 보조번호로 B 계정 신규 가입 차단). `BrandUser.phone` 은 `isPrimary` 행의 **비정규화 미러**로 남아 알림톡 수신번호 폴백(`payment.service`)·NicePay `buyerTel`(`subscription.service`)·`senderPhone` prefill·어드민 `submittedBy.select` 가 그대로 읽는다. 추가/삭제/대표지정은 설정 페이지에서만(`/v1/brand/auth/phones/*`). 이메일·구글 가입 계정이 첫 번호를 붙이면 그 즉시 전화 로그인이 열린다. 마이그레이션 `20260728050713_add_brand_user_phones` + 백필 `npm run backfill:brand-user-phones` (**배포 순서: migrate → 백필 → 코드 → 백필 재실행** — 마지막 재실행이 배포 창에서 구 코드로 가입해 미러만 가진 계정을 주워 담는다).
- **가입 = brand draft 즉시 생성**: 세 가입 경로(이메일/전화/Google) 모두 랜딩에서 입력한 slug 를 받아 가입 트랜잭션 안에서 `Brand`(status `draft`) 를 만들고 `BrandUser.brandId` 를 연결한다 (`createBrandUserWithDraft`). brandId 가 null 로 남는 orphan(→ studio 빈 `klow.kr/` 주소) 을 원천 차단. slug 가용성은 토큰 소모 **전** 선검사해 충돌 시 검증 토큰을 보존한다. slug 가 안 실려온 엣지/legacy 는 studio 의 `init-draft` 안전망이 커버. 공통 draft 데이터·P2002 매핑은 `brand-applications/draft-brand.ts`.
- **OTP 정책**: 6자리 / 10분 TTL / 5회 시도 제한 / 60초 재발송 쿨다운 (phone 전용 `lastSentAt`)
- **관련 파일**: `brand-auth.service.ts`, `brand-session.ts`, `brand-google.strategy.ts`, 그리고 공용으로 `auth/phone-verification.service.ts`, `auth/sms.service.ts`

## brand-auth.controller.ts (`@Controller('v1/brand/auth')`)

> `TIGHT` = 5회/분, `LOOSE` = 10회/분 (per IP). 비밀번호는 8자↑ + 영문 + 숫자(`BrandPasswordField`), 전화번호는 `010`+8자리로 정규화 후 검증.

### 이메일 인증

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/send-verification`      | TIGHT    | 이메일 OTP 발송 (가입용)                              |
| POST   | `/v1/brand/auth/verify-email`           | LOOSE    | OTP 검증 → 가입용 단기 토큰                           |
| POST   | `/v1/brand/auth/signup`                 | TIGHT    | 이메일/비밀번호 가입 (+slug→brand draft) + 세션 쿠키  |
| POST   | `/v1/brand/auth/login`                  | LOOSE    | 이메일/비밀번호 로그인 + 세션 쿠키                    |

- `login` 은 **미가입 이메일 또는 비밀번호 없는 계정(구글/전화 가입)** 이면 404 `user_not_found` — LoginModal 이 이 코드를 받아 랜딩의 회원가입 안내로 보낸다. 비밀번호만 틀리면 401.
- 이메일 중복은 409 (`assertEmailAvailable` — 가입·연결 두 경로의 단일 출처), slug 충돌은 409 / 형식·예약어는 400.

### 비밀번호 변경 / 찾기 (2026-07)

`passwordHash` 있는 계정(이메일+비밀번호 가입)만 대상 — 구글/전화 가입 계정은 400 `password_not_set`, 미가입 이메일은 404 `user_not_found` (login 의 명시 에러 관례를 따름, enumeration 은 THROTTLE 로 완화).

| Method | Path                                        | Throttle | 기능                                                  |
|--------|---------------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/change-password`            | TIGHT    | 현재 비밀번호 확인 후 교체 (세션 쿠키 필요). 현재 세션 **제외** 전 세션 무효화 |
| POST   | `/v1/brand/auth/password-reset/send-otp`    | TIGHT    | 재설정용 이메일 OTP 발송 (전용 메일 템플릿)           |
| POST   | `/v1/brand/auth/password-reset/verify-otp`  | LOOSE    | OTP 검증 → reset 단기 토큰 (15분)                     |
| POST   | `/v1/brand/auth/password-reset/confirm`     | LOOSE    | 새 비밀번호 확정 → **전 세션 무효화 후 새 세션 쿠키 발급(자동 로그인)**. 토큰 1회용 |

- purpose: `brand-password-reset-otp` / `brand-password-reset-token` — 가입과 동일한 `EmailVerificationService` 인프라 재사용 (10분 OTP·5회 시도·15분 토큰).
- `me`/로그인 응답의 user 에 `hasPassword: boolean` 포함 — klow_brand 설정 페이지가 비밀번호 변경 섹션 노출 분기에 사용.
- 클라: LoginModal 이메일 폼 하단 "비밀번호를 잊으셨나요?" → 모달 내 `ForgotPasswordFlow` 3스텝(이메일→OTP→새 비밀번호), 설정 페이지 `PasswordSection` 카드.

### 전화 인증 (메인 플로우)

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/phone/send-signup-otp`  | TIGHT    | 가입용 SMS OTP 발송 (Solapi)                          |
| POST   | `/v1/brand/auth/phone/send-login-otp`   | TIGHT    | 로그인용 SMS OTP 발송 (Solapi)                        |
| POST   | `/v1/brand/auth/phone/verify-signup`    | LOOSE    | 가입 OTP 검증 → 가입용 토큰                           |
| POST   | `/v1/brand/auth/phone/verify-login`     | LOOSE    | 로그인 OTP 검증 → 로그인용 토큰                       |
| POST   | `/v1/brand/auth/phone/signup`           | TIGHT    | 전화 가입 완료 (브랜드 이름/슬러그 포함) + 세션 쿠키  |
| POST   | `/v1/brand/auth/phone/login`            | LOOSE    | 전화 로그인 완료 + 세션 쿠키                          |

- `phone/send-login-otp` 는 **`BrandUserPhone` 에 없는 번호면 SMS 를 보내지 않고 404 `user_not_found`** (이메일 login 과 같은 관례 — 클라가 회원가입 안내로 분기). 반대로 `phone/send-signup-otp` 는 이미 쓰이는 번호면 409.
- `phone/signup` 은 `contactName` 없이 빈 문자열로 생성하고, 가입 트랜잭션이 `BrandUserPhone` 대표 행까지 함께 만든다.

### 로그인 전화번호 관리 (설정 페이지, 전부 BrandGuard)

계정당 최대 5개. 추가하려는 **새 번호로 직접 OTP** 를 보내 소유를 확인한다 (세션이 이미 인증된 상태라 대표번호 재인증은 요구하지 않음 — 이메일 추가와 동일한 강도). mutation 은 갱신된 목록(`{ phones }`)을 그대로 반환해 클라 refetch 왕복을 없앤다.

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| GET    | `/v1/brand/auth/phones`                 | -        | 등록된 로그인 번호 목록 (대표 우선, 등록순)           |
| POST   | `/v1/brand/auth/phones/send-otp`        | TIGHT    | 추가할 번호로 SMS OTP 발송 (상한·중복 선검사)         |
| POST   | `/v1/brand/auth/phones/verify-otp`      | LOOSE    | OTP 검증 → 추가용 단기 토큰                           |
| POST   | `/v1/brand/auth/phones`                 | TIGHT    | 번호 추가 확정 → `{ phones }`                         |
| POST   | `/v1/brand/auth/phones/:id/primary`     | LOOSE    | 대표번호 지정 (+`BrandUser.phone` 미러 동기화)        |
| DELETE | `/v1/brand/auth/phones/:id`             | LOOSE    | 번호 삭제 (대표면 최고참 번호가 자동 승계)            |

- purpose: `brand-add-phone-otp` / `brand-add-phone-token` — `PhoneVerificationService` 무수정 재사용(10분 OTP·5회 시도·60초 쿨다운·15분 토큰).
- 토큰 소모 **전에** 상한·중복을 먼저 본다 (충돌 시 인증 토큰 보존 — 가입의 slug 선검사와 같은 이유).
- **마지막 로그인 수단 가드**: 남는 번호가 0개인데 `email`+`passwordHash` 쌍도 `googleId` 도 없으면 400 `last_login_method` — 계정 영구 잠김 방지.
- **번호 변경 3경로는 계정 행을 잠근 트랜잭션에서 돈다** (`lockBrandUser` → `SELECT ... FOR UPDATE`). read committed 에서는 읽기-검사-쓰기를 한 트랜잭션에 넣어도 동시 요청이 같은 스냅샷을 보므로, 잠그지 않으면 마지막 두 번호를 동시에 지울 때 둘 다 가드를 통과해 계정이 잠긴다(대표번호가 2개 생기는 창도 같은 잠금으로 닫힌다).
- **중복 검사는 `BrandUserPhone` + `BrandUser.phone` 둘 다 본다** — 배포 창에서 구 코드가 만든 "미러만 있고 서브테이블 행이 없는" 계정의 번호를 남이 가져가는 것을 막는다.
- 클라: 설정 페이지 `PhoneSection` (11자리 입력 시 자동 발송 + `OtpCodeInput`/`useCountdown` 재사용, LoginModal 전화 스텝과 동일 관례).

### 이메일 로그인 연결 (설정 페이지, 전부 BrandGuard)

전화로 가입한 계정은 `email`/`passwordHash` 가 비어 있어 이메일 로그인·비밀번호 찾기가 막혀 있다. 설정 페이지에서 **이메일 OTP + 비밀번호를 한 흐름으로** 붙이면 기존 `login()` · `ForgotPasswordFlow` · `changePassword` 가 **추가 코드 없이 그대로 살아난다**. 이메일은 계정당 1개(`BrandUser.email @unique`) — 스키마 변경 없음.

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/email/send-otp`         | TIGHT    | 연결할 이메일로 OTP (계정 상태·중복 선검사)           |
| POST   | `/v1/brand/auth/email/verify-otp`       | LOOSE    | OTP 검증 → 연결용 단기 토큰                           |
| POST   | `/v1/brand/auth/email/link`             | TIGHT    | 이메일+비밀번호 확정 → `{ user }`                     |
| POST   | `/v1/brand/auth/set-password`           | TIGHT    | 구글 계정(이메일 有·비번 無) 비밀번호 설정 → `{ user }` |

- purpose: `brand-link-email-otp` / `brand-link-email-token` — `EmailVerificationService` 무수정 재사용. 단 `issueOtp` 의 템플릿 분기에 `brand-link-email` 을 추가해 **전용 메일**(`sendEmailLinkCode`, `[KLOW] 이메일 연결 인증 코드`)이 나가게 한다 — 기본 템플릿은 "회원가입 화면에 입력" 문구라 맥락이 안 맞는다.
- 토큰 소모 **전에** 계정 상태·중복을 먼저 본다 (충돌 시 인증 토큰 보존 — 가입의 slug 선검사와 동일).
- 에러 코드: 이미 이메일 있는 계정 400 `email_already_linked` / 남이 쓰는 이메일 409 / `set-password` 는 이메일 없으면 400 `email_required`, 비번 이미 있으면 400 `password_already_set`(변경은 `change-password`).
- **세션은 유지한다** — 자격 증명 *추가*이지 회전이 아니라 `changePassword`/`resetPassword` 와 달리 다른 세션을 죽이지 않는다.
- ⚠️ `PhoneVerification` 과 달리 `EmailVerification` 에는 재발송 쿨다운 컬럼이 없어 `THROTTLE_TIGHT` 가 유일한 방어다(클라는 UI 로 60초 카운트다운).
- 부수효과: 비밀번호가 생기면 `removePhone` 의 `last_login_method` 가드가 완화돼 마지막 전화번호도 삭제 가능해진다. 어드민 담당자 표기도 `contactName || email || phone` 순서라 전화번호 → 이메일로 바뀐다.
- 클라: 설정 페이지 `EmailSection` (전화 계정 3스텝 / 구글 계정 비밀번호만 / 연결됨 표시 3갈래).

### 세션 / 유틸 / OAuth

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/logout`                 | -        | 세션 무효화 + 쿠키 제거                               |
| GET    | `/v1/brand/auth/me`                     | -        | 현재 브랜드 사용자 세션 조회                          |
| POST   | `/v1/brand/auth/withdrawal-request`     | -        | 탈퇴(철회) 요청 — `Brand.status` 를 `withdrawal_pending` 으로 전환 후 세션 쿠키 제거. 실제 처리는 어드민 [brands](./brands.md) 의 brand-withdrawals 가 담당 |
| GET    | `/v1/brand/auth/slug-availability`      | LOOSE    | 브랜드 슬러그 중복 체크 (`?slug=...`) → `{slug, available, reason}` (`invalid`/`reserved`/`taken`/`null`) |
| GET    | `/v1/brand/auth/google`                 | -        | `returnTo` + `mode` + (가입 시) `slug` + CSRF `state` 쿠키 저장 후 `authorize?state=...` 로 |
| GET    | `/v1/brand/auth/google/authorize`       | -        | Passport — Google 로 보냄 (`BRAND_GOOGLE_STRATEGY`, `state` 통과)   |
| GET    | `/v1/brand/auth/google/callback`        | -        | `state` 대조(불일치 401) → mode 분기 → 세션 쿠키 + `BRAND_FRONTEND_URL` 로 복귀 |

- **탈퇴 요청은 세션 쿠키만 지우는 게 아니다** — 같은 트랜잭션에서 (1) `Brand.status = withdrawal_pending` + 요청자 스냅샷(`withdrawalRequested*`) 기록, (2) `canceled` 가 아닌 **모든 `BrandSubscription` 즉시 해지**(안 끊으면 cron 이 `brand.status` 를 안 봐서 탈퇴 브랜드 카드가 계속 결제된다), (3) **그 브랜드에 속한 모든 BrandUser 의 세션 삭제**. 이미 `withdrawn` 이거나 브랜드가 없으면 400.
- **탈퇴 신청/완료 브랜드는 인증 자체가 막힌다** — 세션 발급은 403(`assertCanAuthenticate`), 기존 세션은 `me`/`getSession` 이 조회 시점에 삭제하고 null 을 돌려준다.
- **Google `mode` 분기**: `mode=login`(LoginModal 발) 은 **신규 계정을 만들지 않고**, 미가입이면 `BRAND_FRONTEND_URL/?signup=guide` 로 보내 랜딩에서 슬러그부터 입력하게 한다. 그 외(기본 `signup`)는 `slug` 쿠키로 brand draft 까지 만든다. 두 경로 모두 `googleId` 미매칭이어도 **이메일이 같은 기존 계정이 있으면 그 계정에 `googleId` 를 링크**한다(신규 생성 아님).

## 참고

- KR `010` 번호만 허용. 클라(`klow_brand/src/lib/phone.ts`)는 010-1234-5678 자동 포맷, 서버 `normalizePhone()` 은 digits 만 저장.
- 환경변수: `SOLAPI_API_KEY` / `SOLAPI_API_SECRET` / `SOLAPI_SENDER` (운영 전 발신번호 사전등록 필수).
- dev 에서 key 가 비어있으면 콘솔로 `[DEV sms] ...` OTP 로깅.
- `OtpCodeInput` + `useCountdown` 컴포넌트로 클라이언트 모달 공통화 (signup 페이지·LoginModal·SignupModal 3곳 재사용).
