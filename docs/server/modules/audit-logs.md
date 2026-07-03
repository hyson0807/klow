# audit-logs — 어드민 감사 로그 조회

- **모듈 경로**: `src/modules/audit-logs/`
- **주 클라이언트**: `klow_admin` (port 3000)
- **권한**: `AdminGuard + SuperAdminGuard` — **SUPER role 만**.
- **데이터 소스**: `AdminAuditLog` 테이블 (`AdminAuditInterceptor` 가 자동 기록).
- **관련 파일**: `audit-logs.controller.ts`, `audit-logs.service.ts`

## audit-logs.controller.ts (`@Controller('admin/audit-logs')`)

| Method | Path                  | 기능                                                                |
|--------|-----------------------|---------------------------------------------------------------------|
| GET    | `/admin/audit-logs`   | 감사 로그 목록 조회 (필터: actorId/method/path/from/to, 페이지네이션) |

## 기록되는 정보

- actor admin id, IP, UA
- 요청 method + path
- 요청 body (password/code/token/secret/otp 류 redact)
- 응답 status
- 타임스탬프

## 활용

- 어드민 활동 추적 (누가 언제 무엇을 수정/삭제했는지).
- 보안 이벤트 (로그인 실패 → 락 등) 사후 조사.
