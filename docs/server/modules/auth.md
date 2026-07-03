# auth — 일반 유저 인증

- **모듈 경로**: `src/modules/auth/`
- **주 클라이언트**: `klow_web` (port 3001)
- **세션 쿠키**: `klow_sid` (httpOnly, DB `Session` 테이블 기반)
- **인증 방식**: 이메일 + 비밀번호 (이메일 OTP 6자리/10분 TTL) + Google OAuth
- **관련 파일**: `auth.service.ts`, `password.ts`, `session.ts`, `email-verification.service.ts`, `email.service.ts`, `sms.service.ts`, `google.strategy.ts`

## public-auth.controller.ts (`@Controller('v1/auth')`)

| Method | Path                          | Guard               | Throttle | 기능                                                              |
|--------|-------------------------------|---------------------|----------|-------------------------------------------------------------------|
| POST   | `/v1/auth/send-verification`  | public              | TIGHT    | 가입용 이메일 OTP 코드 발송 (10분 TTL, 60초 재발송 쿨다운)        |
| POST   | `/v1/auth/verify-email`       | public              | LOOSE    | OTP 코드 검증 → 가입 진행용 단기 토큰 발급                        |
| POST   | `/v1/auth/signup`             | public              | TIGHT    | 토큰+비밀번호로 가입 + 세션 쿠키 설정                              |
| POST   | `/v1/auth/login`              | public              | LOOSE    | 이메일/비밀번호 로그인 + 세션 쿠키 설정                            |
| POST   | `/v1/auth/logout`             | public              | -        | 세션 무효화 + 쿠키 제거                                           |
| GET    | `/v1/auth/me`                 | public (쿠키 읽음)  | -        | 현재 로그인 유저 (없으면 401)                                     |
| PATCH  | `/v1/auth/me`                 | `UserGuard`         | -        | 프로필 편집 (닉네임/국가/피부타입/concerns 등)                    |
| GET    | `/v1/auth/google`             | public              | -        | `returnTo` 쿠키 저장 후 `/v1/auth/google/authorize` 로 리다이렉트 |
| GET    | `/v1/auth/google/authorize`   | `AuthGuard('google')`| -       | Passport — Google 로 보냄                                         |
| GET    | `/v1/auth/google/callback`    | `AuthGuard('google')`| -       | Google 콜백 → 유저 찾기/생성 + 세션 쿠키 + `FRONTEND_URL` 로 복귀  |

## 참고 사항

- `klow_web` 측에서는 `useSession` / `useAuthGate` 훅으로 게이트 처리.
- 비로그인 상태로 쌓아둔 cart/profile 은 로그인 직후 `SessionSyncMount` 가 `PATCH /v1/auth/me` + `PUT /v1/cart/merge` 로 서버에 승격.
- Google OAuth callback URL 은 `GOOGLE_CALLBACK_URL` 환경변수 (브랜드는 `GOOGLE_BRAND_CALLBACK_URL` 로 분리).
