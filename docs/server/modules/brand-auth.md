# brand-auth — 브랜드 사용자 인증

- **모듈 경로**: `src/modules/brand-auth/`
- **주 클라이언트**: `klow_brand` (port 3002)
- **세션 쿠키**: `klow_brand_sid` (httpOnly, 7일 기본)
- **인증 방식 (메인)**: **전화번호 + SMS OTP** (Solapi)
- **인증 방식 (보조)**: Email + Password (argon2id) + 이메일 OTP, Google OAuth
- **공개 가입**: invitation 없음, TOTP 없음 (마찰 최소화)
- **계정 정책**: `BrandUser.email` / `phone` / `googleId` 모두 nullable + @unique. **같은 사람이 세 방식으로 가입하면 별개 BrandUser**.
- **가입 = brand draft 즉시 생성**: 세 가입 경로(이메일/전화/Google) 모두 랜딩에서 입력한 slug 를 받아 가입 트랜잭션 안에서 `Brand`(status `draft`) 를 만들고 `BrandUser.brandId` 를 연결한다 (`createBrandUserWithDraft`). brandId 가 null 로 남는 orphan(→ studio 빈 `klow.kr/` 주소) 을 원천 차단. slug 가용성은 토큰 소모 **전** 선검사해 충돌 시 검증 토큰을 보존한다. slug 가 안 실려온 엣지/legacy 는 studio 의 `init-draft` 안전망이 커버. 공통 draft 데이터·P2002 매핑은 `brand-applications/draft-brand.ts`.
- **OTP 정책**: 6자리 / 10분 TTL / 5회 시도 제한 / 60초 재발송 쿨다운 (phone 전용 `lastSentAt`)
- **관련 파일**: `brand-auth.service.ts`, `brand-session.ts`, `brand-google.strategy.ts`, 그리고 공용으로 `auth/phone-verification.service.ts`, `auth/sms.service.ts`

## brand-auth.controller.ts (`@Controller('v1/brand/auth')`)

### 이메일 인증

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/send-verification`      | TIGHT    | 이메일 OTP 발송 (가입용)                              |
| POST   | `/v1/brand/auth/verify-email`           | LOOSE    | OTP 검증 → 가입용 단기 토큰                           |
| POST   | `/v1/brand/auth/signup`                 | TIGHT    | 이메일/비밀번호 가입 (+slug→brand draft) + 세션 쿠키  |
| POST   | `/v1/brand/auth/login`                  | LOOSE    | 이메일/비밀번호 로그인 + 세션 쿠키                    |

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

### 세션 / 유틸 / OAuth

| Method | Path                                    | Throttle | 기능                                                  |
|--------|-----------------------------------------|----------|-------------------------------------------------------|
| POST   | `/v1/brand/auth/logout`                 | -        | 세션 무효화 + 쿠키 제거                               |
| GET    | `/v1/brand/auth/me`                     | -        | 현재 브랜드 사용자 세션 조회                          |
| POST   | `/v1/brand/auth/withdrawal-request`     | -        | 탈퇴(철회) 요청 — `Brand.status` 를 `withdrawal_pending` 으로 전환 후 세션 쿠키 제거. 실제 처리는 어드민 [brands](./brands.md) 의 brand-withdrawals 가 담당 |
| GET    | `/v1/brand/auth/slug-availability`      | LOOSE    | 브랜드 슬러그 중복 체크 (`?slug=...`)                 |
| GET    | `/v1/brand/auth/google`                 | -        | `returnTo` + `mode` + (가입 시) `slug` 쿠키 저장 후 authorize 로 |
| GET    | `/v1/brand/auth/google/authorize`       | -        | Passport — Google 로 보냄 (`BRAND_GOOGLE_STRATEGY`)   |
| GET    | `/v1/brand/auth/google/callback`        | -        | Google 콜백 → 유저 찾기/생성 (신규면 slug 쿠키로 brand draft) + `BRAND_FRONTEND_URL` 로 복귀 |

## 참고

- KR `010` 번호만 허용. 클라(`klow_brand/src/lib/phone.ts`)는 010-1234-5678 자동 포맷, 서버 `normalizePhone()` 은 digits 만 저장.
- 환경변수: `SOLAPI_API_KEY` / `SOLAPI_API_SECRET` / `SOLAPI_SENDER` (운영 전 발신번호 사전등록 필수).
- dev 에서 key 가 비어있으면 콘솔로 `[DEV sms] ...` OTP 로깅.
- `OtpCodeInput` + `useCountdown` 컴포넌트로 클라이언트 모달 공통화 (signup 페이지·LoginModal·SignupModal 3곳 재사용).
