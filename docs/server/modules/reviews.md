# reviews — 리뷰

- **모듈 경로**: `src/modules/reviews/`
- **리뷰 번역 (2026-06-30, `add_review_translation`)**: 공개 리뷰를 요청 locale 로 lazy 번역·캐시. `ReviewTranslationService` 가 `GET /v1/reviews/translations` 로 한 제품 전체 리뷰를 일괄 번역해 반환한다.
- **스크린샷/OCR 리뷰 관리 (어드민)**: 리뷰 스크린샷(R2 URL)을 비전 LLM 으로 분석해 리뷰 후보를 추출(`POST /admin/reviews/extract`, DB 미기록 — 어드민이 확인 후 `bulk` 로 적재) + 일괄 입력 그리드(`POST /admin/reviews/bulk`). `ReviewExtractionService` 담당.
- **관련 파일**: `reviews.service.ts`, `review-extraction.service.ts`(스크린샷 OCR), `review-translation.service.ts`(번역 캐시), `admin-reviews.controller.ts`, `public-reviews.controller.ts`

## admin-reviews.controller.ts (`@Controller('admin/reviews')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/reviews`           | 리뷰 목록 (`productId`, `minRating`, `q` 필터)      |
| GET    | `/admin/reviews/:id`       | 리뷰 상세                                           |
| POST   | `/admin/reviews`           | 리뷰 생성                                           |
| POST   | `/admin/reviews/bulk`      | 리뷰 일괄 생성 (일괄 입력 그리드)                   |
| POST   | `/admin/reviews/extract`   | 리뷰 스크린샷(R2 URL) 비전 LLM 분석 → 후보 추출(DB 미기록) |
| PATCH  | `/admin/reviews/:id`       | 리뷰 수정                                           |
| DELETE | `/admin/reviews/:id`       | 리뷰 삭제                                           |

## public-reviews.controller.ts (`@Controller('v1/reviews')`)

> 전체 라우트 public (현재는 읽기 전용 노출).

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/reviews`              | 리뷰 목록 (`productId`, `minRating`, `q` 필터)      |
| GET    | `/v1/reviews/translations` | 한 제품 전체 리뷰를 요청 locale 로 일괄 번역(`productId`, `lang`, lazy 캐시) |
| GET    | `/v1/reviews/:id`          | 리뷰 상세                                           |
