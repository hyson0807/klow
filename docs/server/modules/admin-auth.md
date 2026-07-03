# admin-auth — 어드민 인증 & 계정 관리

- **모듈 경로**: `src/modules/admin-auth/`
- **주 클라이언트**: `klow_admin` (port 3000)
- **세션 쿠키**: `klow_admin_sid` (httpOnly, 24h 절대만료 / 60분 idle)
- **인증 방식**: Email + Password (argon2id) + **TOTP 2FA 필수**
- **잠금 정책**: 로그인 실패 5회 → 15분 락 (`AdminLoginAttempt` 테이블)
- **TOTP secret**: AES-256-GCM 암호화, `ADMIN_TOTP_ENCRYPTION_KEY` 환경변수 (회전 금지)
- **관련 파일**: `admin-auth.service.ts`, `totp.service.ts`, `totp-crypto.ts`, `admin-session.ts`, `admin-invitation.service.ts`, `admin-audit.interceptor.ts`

## admin-auth.controller.ts (`@Controller('admin/auth')`)

| Method | Path                          | Guard       | Throttle | 기능                                                  |
|--------|-------------------------------|-------------|----------|-------------------------------------------------------|
| POST   | `/admin/auth/login`           | public      | TIGHT    | **Step 1**: 이메일/비밀번호 검증 → TOTP ticket 반환   |
| POST   | `/admin/auth/verify-totp`     | public      | TIGHT    | **Step 2**: TOTP 코드 검증 → 세션 쿠키 발급           |
| POST   | `/admin/auth/accept-invite`   | public      | TIGHT    | 초대 토큰으로 어드민 계정 활성화 (비밀번호+TOTP 설정) |
| POST   | `/admin/auth/logout`          | public      | -        | 세션 무효화 + 쿠키 제거                               |
| GET    | `/admin/auth/me`              | public      | -        | 현재 어드민 세션 조회 (없으면 401)                    |

## admins.controller.ts (`@Controller('admin/admins')`)

> 전체 라우트 `@UseGuards(AdminGuard, SuperAdminGuard)` — **SUPER role 만 접근**.

| Method | Path                          | 기능                                                  |
|--------|-------------------------------|-------------------------------------------------------|
| GET    | `/admin/admins`               | 어드민 목록                                           |
| POST   | `/admin/admins/invite`        | 새 어드민 초대 (이메일로 활성화 링크 발송)            |
| PATCH  | `/admin/admins/:id/role`      | role 변경 (`SUPER` ↔ `STAFF`)                         |
| PATCH  | `/admin/admins/:id/profile`   | 표시 이름(`displayName`) · 프로필 이미지(`profileImage`) 수정 |
| DELETE | `/admin/admins/:id`           | 어드민 삭제                                           |

## 부가 모듈 — AdminAuditInterceptor

- `/admin/*` 의 모든 **non-GET** 응답을 `AdminAuditLog` 에 자동 기록.
- redact 대상: `password`, `code`, `token`, `secret`, `otp` 등.
- IP, UA, actor admin id, 응답 status 함께 저장.
