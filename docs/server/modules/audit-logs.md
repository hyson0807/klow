# audit-logs — 어드민 감사 로그 조회

- **모듈 경로**: `src/modules/audit-logs/`
- **주 클라이언트**: `klow_admin` (port 3000)
- **권한**: `AdminGuard + SuperAdminGuard` — **`super` role 만**.
- **데이터 소스**: `AdminAuditLog` 테이블 (`AdminAuditInterceptor` 가 자동 기록).
- **관련 파일**: `audit-logs.controller.ts`, `audit-logs.service.ts`

## audit-logs.controller.ts (`@Controller('admin/audit-logs')`)

| Method | Path                  | 기능                                                                |
|--------|-----------------------|---------------------------------------------------------------------|
| GET    | `/admin/audit-logs`   | 감사 로그 목록 조회 (`createdAt desc`) → `{ data, total }`           |

### 쿼리 파라미터 (`AuditLogQueryInput`)

| 필드         | 타입                                    | 비고                          |
|--------------|-----------------------------------------|-------------------------------|
| `adminId`    | string (1~64)                           | 행위자 어드민 id              |
| `resource`   | string (1~64)                           | 경로 첫 세그먼트 (`products` 등) |
| `action`     | `POST` \| `PATCH` \| `PUT` \| `DELETE`  | HTTP method                   |
| `resourceId` | string (1~128)                          | 대상 레코드 id                |
| `since` / `until` | date (coerce)                      | `createdAt` 범위              |
| `take`       | int 1~200, default **50**               | 페이지 크기                   |
| `skip`       | int ≥0, default **0**                   | offset                        |

`data[].admin` 에 `{ id, email, role }` 이 join 되어 함께 내려온다. `total` 은 표시용이라 동시 insert 로 1건 어긋날 수 있다(두 쿼리를 트랜잭션으로 묶지 않음).

## 기록되는 정보

`AdminAuditInterceptor`(글로벌, `admin-auth` 모듈 소유)가 남기는 컬럼:

- `adminId`(행위자), `ip`, `userAgent`
- `action`(HTTP method) + `resource`(경로 첫 세그먼트) + `resourceId` — **전체 path 를 그대로 저장하지는 않는다**
- `payload` = 요청 body (`password`/`code`/`token`/`totp` 류 키 redact, 10KB 초과 시 truncate)
- `createdAt` 타임스탬프

⚠️ **응답 status 는 저장하지 않는다.** 또한 `/admin/auth/*` (로그인·로그아웃·초대 수락) 는 감사 대상에서 제외된다.

## 활용

- 어드민 활동 추적 (누가 언제 무엇을 수정/삭제했는지).
- 로그인 실패·락 이력은 여기가 아니라 **`AdminLoginAttempt`** 테이블에 쌓인다(조회 엔드포인트 없음 — DB 직접 확인).
