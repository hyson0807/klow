# reviews — 리뷰

- **모듈 경로**: `src/modules/reviews/`
- **리뷰 번역 (2026-06-30, `add_review_translation`)**: 공개 리뷰를 요청 locale 로 lazy 번역·캐시. `ReviewTranslationService` 가 `GET /v1/reviews/translations` 로 한 제품 전체 리뷰를 일괄 번역해 **`{ [reviewId]: content }` 맵**으로 반환한다. 대상 locale 은 `REVIEW_TRANSLATABLE_LOCALES`(= 제품의 `TRANSLATABLE_LOCALES` + **`en`** — 리뷰 원문이 한국어라 en 도 번역 대상). 미지원 locale(`ko` 등)·빈 본문·번역 실패는 한국어 원문으로 폴백하고, `(reviewId, locale)` 캐시가 없거나 `Review.updatedAt` 이 더 최신인 행만 모아 **1회 배치 번역** 후 upsert 한다.
- **집계 갱신**: `Product.rating` / `Product.reviewCount` 는 어드민 입력으로 받지 않고, create/bulk/update/delete 와 **같은 트랜잭션 안에서** `refreshProductAggregates` 가 재계산한다(단일 출처).
- **스크린샷/OCR 리뷰 관리 (어드민)**: 리뷰 스크린샷(R2 URL)을 비전 LLM 으로 분석해 리뷰 후보를 추출(`POST /admin/reviews/extract`, DB 미기록 — 어드민이 확인 후 `bulk` 로 적재) + 일괄 입력 그리드(`POST /admin/reviews/bulk`). `ReviewExtractionService` 담당.
- **관련 파일**: `reviews.service.ts`, `review-extraction.service.ts`(스크린샷 OCR), `review-translation.service.ts`(번역 캐시), `admin-reviews.controller.ts`, `public-reviews.controller.ts`

## admin-reviews.controller.ts (`@Controller('admin/reviews')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/reviews`           | 리뷰 목록 (`productId`, `minRating`, `q`(userName/content) 필터). `createdAt` desc, 최대 200건, `product` 요약 포함 |
| GET    | `/admin/reviews/:id`       | 리뷰 상세                                           |
| POST   | `/admin/reviews`           | 리뷰 생성 — `createdAt` 을 넘기면 원본 작성일 보존(생략 시 `now()`) |
| POST   | `/admin/reviews/bulk`      | 리뷰 일괄 생성 (일괄 입력 그리드, `items` 1~2000) → `{ count }` |
| POST   | `/admin/reviews/extract`   | 리뷰 스크린샷(R2 URL, `imageUrls` 1~20) 비전 LLM 분석 → `{ reviews }` 후보 반환(DB 미기록) |
| PATCH  | `/admin/reviews/:id`       | 리뷰 수정                                           |
| DELETE | `/admin/reviews/:id`       | 리뷰 삭제                                           |

## public-reviews.controller.ts (`@Controller('v1/reviews')`)

> 전체 라우트 public (현재는 읽기 전용 노출). ⚠️ 리뷰에는 `PUBLIC_PRODUCT_WHERE` 게이트가 걸려 있지 않다 — 어드민 목록과 같은 `ReviewsService.findAll` 을 그대로 쓰므로 `productId` 를 지정하지 않으면 비노출 제품의 리뷰도 섞여 나온다. 클라이언트는 항상 `productId` 로 좁혀 호출한다.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/reviews`              | 리뷰 목록 (`productId`, `minRating`, `q` 필터) — 어드민 목록과 동일 서비스(`createdAt` desc, 최대 200건) |
| GET    | `/v1/reviews/translations` | 한 제품 전체 리뷰를 요청 locale 로 일괄 번역(`productId`, `lang`, lazy 캐시) → `{ [reviewId]: content }`. 리터럴 라우트라 `:id` 보다 먼저 선언 |
| GET    | `/v1/reviews/:id`          | 리뷰 상세                                           |
