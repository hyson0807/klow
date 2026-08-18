# admin-auth — 어드민 인증 & 계정 관리

- **모듈 경로**: `src/modules/admin-auth/`
- **주 클라이언트**: `klow_admin` (port 3000)
- **세션 쿠키**: `klow_admin_sid` (httpOnly, 24h 절대만료 / 60분 idle — `ADMIN_SESSION_TTL_HOURS` / `ADMIN_IDLE_TIMEOUT_MINUTES` 로 조정)
- **인증 방식**: Email + Password (argon2id) + **TOTP 2FA 필수**
- **role**: `super` / `operator` (prisma `AdminRole`). `SuperAdminGuard` 는 `role === 'super'` 만 통과.
- **잠금 정책**: 로그인 실패 5회 → 15분 락 (`AdminLoginAttempt` 테이블, `ADMIN_LOGIN_LOCKOUT_THRESHOLD` / `_MINUTES`)
- **TOTP secret**: AES-256-GCM 암호화, `ADMIN_TOTP_ENCRYPTION_KEY` 환경변수 (회전 금지)
- **관련 파일**: `admin-auth.service.ts`, `totp.service.ts`, `totp-crypto.ts`, `admin-session.ts`, `admin-invitation.service.ts`, `admin-audit.interceptor.ts`

## admin-auth.controller.ts (`@Controller('admin/auth')`)

> `TIGHT` = `@Throttle({ default: { limit: 5, ttl: 60_000 } })` (5회/분 per IP).

| Method | Path                          | Guard       | Throttle | 기능                                                  |
|--------|-------------------------------|-------------|----------|-------------------------------------------------------|
| POST   | `/admin/auth/login`           | public      | TIGHT    | **Step 1**: `{email, password}` 검증 → `{stage:'totp_required', ticket}` 또는 미등록 시 `{stage:'totp_setup_required', ticket, otpauthUrl}` |
| POST   | `/admin/auth/verify-totp`     | public      | TIGHT    | **Step 2**: `{ticket, code}` 검증 → 세션 쿠키 + `{admin}` |
| POST   | `/admin/auth/accept-invite`   | public      | TIGHT    | 초대 토큰 + 비밀번호(10자↑·영문·숫자·특수문자)로 계정 생성 → `{admin, otpauthUrl, setupTicket}` (TOTP 등록 확정은 이어지는 verify-totp 성공 시점) |
| POST   | `/admin/auth/logout`          | public      | -        | 세션 무효화 + 쿠키 제거 → `{ok:true}`                 |
| GET    | `/admin/auth/me`              | public (쿠키 읽음) | - | 현재 어드민 세션 조회 → `{admin, idleTimeoutMs}` (없으면 401) |

- **ticket 은 in-process `Map`** — login step1 ↔ step2 사이의 단명 중간값. `totp` 5분 / `setup` 15분 TTL, 1회 소모. **단일 인스턴스 전용**(수평 확장 시 Redis/DB 로 이전 필요).
- `verify-totp` 성공 시 최초 1회 `totpVerifiedAt` 을 채워 enroll 을 확정하고, 락 윈도우 내 실패 기록을 지운다.

## admin-admins.controller.ts (`@Controller('admin/admins')`)

> 전체 라우트 `@UseGuards(AdminGuard, SuperAdminGuard)` — **`super` role 만 접근**. Throttle 없음.

| Method | Path                          | 기능                                                  |
|--------|-------------------------------|-------------------------------------------------------|
| GET    | `/admin/admins`               | 어드민 목록 (createdAt asc)                           |
| POST   | `/admin/admins/invite`        | `{email, role}` 로 초대 → `{invitationId}`. `ADMIN_FRONTEND_URL/accept-invite/{token}` 링크 메일 발송 |
| PATCH  | `/admin/admins/:id/role`      | role 변경 (`super` ↔ `operator`)                      |
| PATCH  | `/admin/admins/:id/profile`   | 표시 이름(`displayName`) · 프로필 이미지(`profileImage`) · **휴대폰(`phone`)** 수정 (전부 nullable optional) |
| DELETE | `/admin/admins/:id`           | 어드민 삭제 → `{ok:true}`                             |

### `Admin.phone` — 운영 알림 수신번호 (2026-08-18)

- **용도는 하나다**: EFS **송장 자동발급 실패 SMS** 의 수신번호(→ [shipments](./shipments.md) 발급 실패 알림). 로그인·인증에는 일절 쓰이지 않는다(어드민 인증은 여전히 비밀번호 + TOTP).
- 검증은 `common/validation/shared.ts` 의 **`KrPhone`**(digits 추출 → `^010\d{8}$`) — 원래 `brand-auth.ts` 의 비공개 const 였던 것을 shared 로 올려 브랜드 전화 OTP 와 **공유**한다. 두 도메인이 각자 복사본을 가지면 한쪽만 규칙이 바뀌어 "가입은 되는데 알림은 안 가는" 형태로 어긋난다. 저장 정본은 **digits-only**.
- ⚠️ zod 에 **`.default()` 를 붙이지 않는다** — PATCH 마다 주입되어 이 필드를 안 보낸 저장이 남의 번호를 지운다(`onsiteDiscountPct`·promotion `prices` 선례).
- ⚠️ `updateProfile()` 의 **명시적 허용목록**에 넣어야 실제로 저장된다 — 빠뜨리면 zod 를 통과한 PATCH 가 **조용히 무시**되고 typecheck 도 통과한다(`ShippingService.update()` 와 같은 함정).
- ⚠️ 이 라우트는 `SuperAdminGuard` 라 **operator 는 자기 번호를 스스로 못 넣는다** — 슈퍼관리자가 대신 채운다. 반면 "누가 알림을 받을지" 토글은 출고관리 탭(`AdminGuard`)이라 operator 도 할 수 있다. 번호 등록과 수신 지정의 권한을 일부러 다르게 뒀다.
- 마이그레이션 `20260818093419_add_admin_phone_and_shipment_retry` 는 nullable ADD COLUMN + DEFAULT 있는 boolean ADD COLUMN 이라 **롤링 배포 안전 · 백필 없음**. 같은 행의 `shipmentAlertEnabled`(수신 대상 플래그)는 shipments 모듈이 소유한다.
- 초대(`AdminInvitation`) 흐름은 **손대지 않았다** — 초대 시점엔 번호를 받지 않고, 계정이 생긴 뒤 프로필 수정에서 채운다.

### 가드 규칙 (service 예외)

- 자기 자신은 **role 변경·삭제 불가**.
- `isProtected` 계정은 role 변경·삭제 불가.
- **마지막 `super`** 는 강등도 삭제도 불가.
- 이미 같은 이메일의 어드민이 있으면 `accept-invite` 는 409.

## 부가 모듈 — AdminAuditInterceptor

- `app.module.ts` 에 `APP_INTERCEPTOR` 로 **글로벌 등록**.
- 대상: `POST/PATCH/PUT/DELETE` × (`/admin/*` 또는 `/upload*`). **`/admin/auth/*` 는 제외**(로그인/로그아웃은 감사 대상 아님 + `req.admin` 이 없음), `req.admin` 이 없으면(가드 거부 등) 기록하지 않는다.
- 저장 필드: `adminId`, `action`(= HTTP method), `resource`(경로 첫 세그먼트 — `/admin/products/x` → `products`, `/upload*` → `upload`), `resourceId`(경로 두 번째 세그먼트 → 없으면 응답 body `id` → 요청 body `id`), `payload`(요청 body), `ip`, `userAgent`. **응답 status 는 저장하지 않는다.**
- redact 대상(정확히 이 키 목록, 대소문자 무시): `password`, `passwordHash`, `currentPassword`, `newPassword`, `code`, `totpCode`, `totp`, `totpSecret`, `token`, `tokenHash`, `sessionToken`, `emailVerificationToken`.
- payload 가 10KB 를 넘으면 `{_truncated:true, preview}` 로 잘라 저장. 로그 쓰기 실패는 요청을 막지 않는다(에러 로깅 후 무시).
