# customers — 고객(유저) 어드민 관리

- **모듈 경로**: `src/modules/customers/`
- **데이터 모델**: `User` (auth 모듈 소유)
- **주 클라이언트**: `klow_admin`
- **관련 파일**: `customers.service.ts`, `admin-customers.controller.ts`

## admin-customers.controller.ts (`@Controller('admin/customers')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                                  |
|--------|----------------------------|-----------------------------------------------------------------------|
| GET    | `/admin/customers`         | 고객 목록 (`q`, `status` 등 필터, 페이지네이션)                       |
| GET    | `/admin/customers/:id`     | 고객 상세 (주문 이력 등 include)                                      |
| PATCH  | `/admin/customers/:id`     | 고객 프로필 수정 (어드민 권한; CS 응대용)                             |
