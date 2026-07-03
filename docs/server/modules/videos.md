# videos — 비디오

- **모듈 경로**: `src/modules/videos/`
- **공개 필터**: 연관 상품에 `PUBLIC_PRODUCT_WHERE` 적용 (미승인 상품은 include 에서 제외)
- **관련 파일**: `videos.service.ts`, `admin-videos.controller.ts`, `public-videos.controller.ts`

## admin-videos.controller.ts (`@Controller('admin/videos')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/videos`            | 비디오 목록                                         |
| GET    | `/admin/videos/:id`        | 비디오 상세                                         |
| POST   | `/admin/videos`            | 비디오 생성                                         |
| PATCH  | `/admin/videos/:id`        | 비디오 수정                                         |
| DELETE | `/admin/videos/:id`        | 비디오 삭제                                         |

## public-videos.controller.ts (`@Controller('v1/videos')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                              |
|--------|----------------------------|-------------------------------------------------------------------|
| GET    | `/v1/videos`               | 비디오 목록 (`creatorId`, `productId` 필터)                       |
| GET    | `/v1/videos/:id`           | 비디오 상세 (연관 products include, 공개 상품만)                  |
