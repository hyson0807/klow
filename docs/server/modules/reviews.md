# reviews — 리뷰

- **모듈 경로**: `src/modules/reviews/`
- **리뷰 번역 (2026-06-30, `add_review_translation`)**: 공개 리뷰를 요청 locale 로 lazy 번역·캐시. `ReviewTranslationService` 가 `GET /v1/reviews/translations` 로 한 제품 전체 리뷰를 일괄 번역해 **`{ [reviewId]: content }` 맵**으로 반환한다. 대상 locale 은 `REVIEW_TRANSLATABLE_LOCALES`(= 제품의 `TRANSLATABLE_LOCALES` + **`en`** — 리뷰 원문이 한국어라 en 도 번역 대상). 미지원 locale(`ko` 등)·빈 본문·번역 실패는 한국어 원문으로 폴백하고, `(reviewId, locale)` 캐시가 없거나 `Review.updatedAt` 이 더 최신인 행만 모아 **1회 배치 번역** 후 upsert 한다.
- **집계 갱신**: `Product.rating` / `Product.reviewCount` 는 어드민 입력으로 받지 않고, create/bulk/update/delete 와 **같은 트랜잭션 안에서** `refreshProductAggregates` 가 재계산한다(단일 출처).
- **스크린샷/OCR 리뷰 관리 (어드민)**: 리뷰 스크린샷(R2 URL)을 비전 LLM 으로 분석해 리뷰 후보를 추출(`POST /admin/reviews/extract`, DB 미기록 — 어드민이 확인 후 `bulk` 로 적재) + 일괄 입력 그리드(`POST /admin/reviews/bulk`). `ReviewExtractionService` 담당.
- **브랜드 직접 등록 (2026-08-18)**: 브랜드가 klow_brand 스튜디오 **제품 편집 패널 > 리뷰 탭**(설정/가격 옆 3번째)에서 자기 제품 리뷰를 직접 등록/수정/삭제한다. **검수 없이 즉시 노출**이고 **자기 제품의 모든 리뷰**(어드민이 대신 넣어준 것 포함)를 손댈 수 있다 — 그래서 `Review` 에 status·출처 컬럼이 없고 **스키마 변경·마이그레이션·백필이 0건**이다. ⚠️ `helpful` 만 브랜드 입력에서 뺐다(`BrandReviewItem = ReviewInput.omit({ helpful: true })`) — 표시용 카운트를 임의로 부풀리지 못하게. ⚠️ `BrandReviewPatch` 는 **`productId` 를 뺀 base** 에 `patchOf` 를 걸어 리뷰를 남의 제품으로 옮기는 경로를 스키마 단계에서 없앤다(컨트롤러가 소유권을 봐도 옮긴 뒤 제품이 내 것이면 통과한다).
- **관련 파일**: `reviews.service.ts`, `review-extraction.service.ts`(스크린샷 OCR), `review-translation.service.ts`(번역 캐시), `admin-reviews.controller.ts`, `brand-reviews.controller.ts`, `public-reviews.controller.ts`

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

## brand-reviews.controller.ts (`@Controller('v1/brand/reviews')`)

> 전체 라우트 `BrandGuard` + `requireBrandId(user)`.
> ⚠️ `Review` 에는 `brandId` 가 없다 — 소유권은 전부 **`Review.productId → Product.brandId` 조인**으로 판정하고, 실패는 `Forbidden` 이 아니라 **`NotFound`** 다(id 를 넣어보며 남의 제품 존재를 열거하지 못하게).
> ⚠️ `bulk`·`extract` 는 리터럴 라우트라 `:id` 보다 **먼저** 선언한다.

| Method | Path                          | 기능                                                        |
|--------|-------------------------------|-------------------------------------------------------------|
| GET    | `/v1/brand/reviews?productId=` | 내 제품 1건의 리뷰 목록. `productId` 필수(브랜드 화면이 늘 제품 하나로 좁혀져 있다). ⚠️ 어드민 `findAll` 을 쓰지 않고 **제품 조회에 리뷰를 매달아 1쿼리**로 끝낸다 — 그쪽은 행마다 `product`(id·name·brand·image)를 조인해 싣는데 이 화면은 전부 버린다(200행 상한이면 수십 KB). `null`=남의 제품(404) / `[]`=내 제품인데 리뷰 없음(200) |
| POST   | `/v1/brand/reviews/bulk`      | 여러 건 한 번에 등록 (`items` 1~200 — 어드민 2000 과 다름). **단건 POST 는 없다** — 카드 1장이어도 여기로 보낸다 |
| POST   | `/v1/brand/reviews/extract`   | 리뷰 스크린샷(R2 URL) 비전 LLM 분석 → 후보 반환(DB 미기록). ⚠️ `@Throttle` 5회/분 — 어드민엔 없지만 브랜드는 계정 수가 많고 이 경로가 `gpt-4o`+`detail:'high'` 를 태운다 |
| PATCH  | `/v1/brand/reviews/:id`       | 리뷰 수정 (`BrandReviewPatch` — `productId` 불가)             |
| DELETE | `/v1/brand/reviews/:id`       | 리뷰 삭제                                                    |

⚠️ 브랜드 메서드(`listForBrand`/`createManyForBrand`/`updateForBrand`/`removeForBrand`)는 **전부 기존 어드민 경로와 같은 트랜잭션·`refreshProductAggregates`** 를 거친다. 집계를 우회하는 지름길을 새로 파면 `Product.rating` 이 어긋난 채 klow_web 에 노출된다. `update`/`remove` 는 소유 검증(`assertReviewOwned`)만 따로 걸고 **본체를 어드민 메서드에 위임**한다 — `orNotFound` 까지 함께 타므로 동시 삭제가 raw P2025(500)이 아니라 404 로 나온다(`manual-seeding.service.ts` 의 `assertOwned`→mutate 관용구와 같은 형태이며, 같은 TOCTOU 창을 같은 이유로 받아들인다).
