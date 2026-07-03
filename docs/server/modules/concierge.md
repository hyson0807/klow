# concierge — 컨시어지 문의

- **모듈 경로**: `src/modules/concierge/`
- **목적**: 공개 페이지에서 "원하는 상품 찾아주기" 같은 문의 폼을 받아 어드민이 처리.
- **데이터 모델**: `ConciergeRequest`
- **관련 파일**: `concierge.service.ts`, `admin-concierge.controller.ts`, `public-concierge.controller.ts`

## admin-concierge.controller.ts (`@Controller('admin/concierge-requests')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                                       | 기능                                                |
|--------|--------------------------------------------|-----------------------------------------------------|
| GET    | `/admin/concierge-requests`                | 요청 목록 (`status` 필터)                           |
| GET    | `/admin/concierge-requests/:id`            | 요청 상세                                           |
| PATCH  | `/admin/concierge-requests/:id`            | 상태/메모 업데이트                                  |
| DELETE | `/admin/concierge-requests/:id`            | 요청 삭제                                           |

## public-concierge.controller.ts (`@Controller('v1/concierge-requests')`)

| Method | Path                              | Guard      | 기능                                                |
|--------|-----------------------------------|------------|-----------------------------------------------------|
| POST   | `/v1/concierge-requests`          | public     | 공개 문의 폼 제출 (이메일·요청 내용)                |
