# reviews — 리뷰

- **모듈 경로**: `src/modules/reviews/`
- **리뷰 번역 (2026-06-30, `add_review_translation`)**: 공개 리뷰를 요청 locale 로 lazy 번역·캐시. `ReviewTranslationService` 가 `GET /v1/reviews/translations` 로 한 제품 전체 리뷰를 일괄 번역해 **`{ [reviewId]: content }` 맵**으로 반환한다. 대상 locale 은 `REVIEW_TRANSLATABLE_LOCALES`(= 제품의 `TRANSLATABLE_LOCALES` + **`en`** — 리뷰 원문이 한국어라 en 도 번역 대상). 미지원 locale(`ko` 등)·빈 본문·번역 실패는 한국어 원문으로 폴백하고, `(reviewId, locale)` 캐시가 없거나 `Review.updatedAt` 이 더 최신인 행만 모아 **1회 배치 번역** 후 upsert 한다.
- **집계 갱신**: `Product.rating` / `Product.reviewCount` 는 어드민 입력으로 받지 않고, create/bulk/update/delete 와 **같은 트랜잭션 안에서** `refreshProductAggregates` 가 재계산한다(단일 출처).
- **스크린샷/OCR 리뷰 관리 (어드민)**: 리뷰 스크린샷(R2 URL)을 비전 LLM 으로 분석해 리뷰 후보를 추출(`POST /admin/reviews/extract`, DB 미기록 — 어드민이 확인 후 `bulk` 로 적재) + 일괄 입력 그리드(`POST /admin/reviews/bulk`). `ReviewExtractionService` 담당.
- **브랜드 직접 등록 (2026-08-18)**: 브랜드가 klow_brand 스튜디오 **제품 편집 패널 > 리뷰 탭**(설정/가격 옆 3번째)에서 자기 제품 리뷰를 직접 등록/수정/삭제한다. **검수 없이 즉시 노출**이고 **자기 제품의 모든 리뷰**(어드민이 대신 넣어준 것 포함)를 손댈 수 있다 — 그래서 `Review` 에 status·출처 컬럼이 없고 **스키마 변경·마이그레이션·백필이 0건**이다. (2026-10 에 출처 컬럼 `source` 가 생겼다 — 고객 직접 작성 리뷰만은 브랜드가 손댈 수 없다, 아래 항목.) ⚠️ `helpful` 만 브랜드 입력에서 뺐다(`BrandReviewItem = ReviewInput.omit({ helpful: true })`) — 표시용 카운트를 임의로 부풀리지 못하게. ⚠️ `BrandReviewPatch` 는 **`productId` 를 뺀 base** 에 `patchOf` 를 걸어 리뷰를 남의 제품으로 옮기는 경로를 스키마 단계에서 없앤다(컨트롤러가 소유권을 봐도 옮긴 뒤 제품이 내 것이면 통과한다).
- **고객 직접 작성 (2026-10, `add_customer_reviews`)**: 구매자가 리뷰 요청 메일 링크(`klow_web /review/<orderId>?t=`)로 **로그인 없이** 자기 주문 브랜드의 제품 리뷰를 쓴다. 링크 1개 = (주문, 브랜드) 1쌍이고, 인증은 `review-link-token.ts` 의 HMAC 토큰이다(`base64url(orderId:brandId).hex(HMAC)`, **만료 없음**, 전용 시크릿 `REVIEW_LINK_SECRET` — 운영 미설정이면 `main.ts` 가 부팅 거부. ⚠️ `GUEST_ORDER_SECRET` 재사용 금지). `Review` 에 `source`(`proxy` 기본 / `customer`) · `orderId`(구매 확인 근거, `onDelete: SetNull`) · `sourceLocale`(원문 언어, null=한국어) 3컬럼이 붙었고 `@@unique([orderId, productId])` 가 **한 주문·한 제품 1건**을 강제한다(대행 입력은 orderId=null 이라 무관). 발송 큐 `ReviewRequest`(주문×브랜드 1행, `@@unique([orderId, brandId])`)는 아래 **리뷰 요청 메일** 항목이 채운다. 토큰 검증·폼 조립은 `customer-review.service.ts`, 쓰기는 `ReviewsService.createFromCustomer`(같은 트랜잭션에서 `refreshProductAggregates` + `ReviewRequest.submittedAt` 마킹). ⚠️ 번역은 `sourceLocale` 을 소스로 쓰고, 원문 언어 = 요청 locale 이면 번역도 캐시 행도 만들지 않는다.
- **리뷰 요청 메일 (2026-10)**: `review-request.cron.ts`(`review-request-dispatch`, `*/10 * * * *` KST, `running` 재진입 가드)가 `ReviewRequestService.scanDue()` → `drain()` 을 돈다. ⚠️⚠️ **기본 off — `REVIEW_REQUEST_CRON_ENABLED === 'true'` 일 때만** 동작한다(다른 cron 의 `!== 'false'` 와 의도적으로 반대). 메일 링크가 가리키는 klow_web `/review/<orderId>` 가 배포되기 전에 켜면 404 링크가 나가고 되돌릴 수 없다. **트리거는 DB 스캔이고 `shipments.service.ts` 에 훅이 없다.** 대상은 두 축: ① **송장 축** — `status=submitted` 송장이 종착(국내 `DOMESTIC` 은 `brandConfirmedShippedAt`, 그 외는 `latestStatusCode ∈ EFS_DELIVERED_CODES`(33·47·74) + `latestStatusAt`)에 닿은 (주문, 브랜드) — `isTerminalShipment()` 와 같은 분기, 브랜드 단위라 멀티 브랜드 주문은 브랜드마다 따로 생긴다 ② **현장 축** — `channel=onsite` 주문의 `paidAt`(송장 0장). 둘 다 `CONTACT_ORDER_WHERE`(paid + 미취소) + `email != ''`(엑셀 일괄 시딩은 이메일이 빈 문자열일 수 있다) + 시점이 `now − REVIEW_REQUEST_DELAY_DAYS`(기본 3) 이전 · `REVIEW_REQUEST_LOOKBACK_DAYS`(기본 14) 이내. 적재는 `createMany({ skipDuplicates })`. 발송은 `crm-email.service.ts` 와 같은 규칙(카운터 호출 前 증가, 백오프 2/10/30분, 3회 후 `failed`) + 브랜드 CRM 수신거부(`BrandCrmOptOut`) 히트는 `skipped`. 메일은 **트랜잭션 도메인**(`EmailService.sendReviewRequest`, `EMAIL_FROM`)이고 문구는 `review-request-email.ts`(en 원본 + ja/zh/vi/th/id/ru/ar, ar 은 rtl). 언어는 `Order.countryCode` → `common/country-locale.ts`(klow_web `COUNTRY_TO_LOCALE` 미러 — 현장 주문은 가격 기준국) 스냅샷을 `ReviewRequest.locale` 에 저장하고, 그 값이 `GET /v1/reviews/form` 의 `locale` 로 나간다.
- **손님 화면 (2026-10, klow_web)**: `/review/[orderId]?t=` 가 위 form/submit/upload 를 그대로 쓴다(화면 언어 = 응답 `locale`, 없으면 앱 locale · 제출 시 그 값을 `sourceLocale` 로). 사진은 `src/lib/upload.ts` 가 긴 변 1600px JPEG 로 줄여 presign URL 에 **브라우저가 직접 PUT** — ⚠️⚠️ **R2 버킷 CORS 가 klow_web 오리진을 허용해야 한다**(2026-10-01 실측: staging 버킷은 `localhost:3001`·`brand-staging.klow.kr` 만 허용, `klow.kr` 403). PDP `ReviewCard` 는 출처를 구분해 보여주지 **않는다**(2026-10-01 사용자 결정 — 배지를 만들었다가 뺐다), klow_brand 리뷰 탭은 배지 없이 수정·삭제 버튼만 숨긴다. `/review` 가 최상위 경로라 `review`·`reviews` 는 브랜드 slug 예약어다.
- **관련 파일**: `reviews.service.ts`, `review-request.service.ts`(큐 스캔·발송), `review-request.cron.ts`, `review-request-email.ts`(8 locale 문구), `customer-review.service.ts`(고객 작성 토큰 게이트), `review-link-token.ts`(HMAC), `review-extraction.service.ts`(스크린샷 OCR), `review-translation.service.ts`(번역 캐시), `admin-reviews.controller.ts`, `brand-reviews.controller.ts`, `public-reviews.controller.ts`

## admin-reviews.controller.ts (`@Controller('admin/reviews')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/reviews`           | 리뷰 목록 (`productId`, `minRating`, `q`(userName/content), `source`(`proxy`\|`customer`, 그 밖의 값은 무시) 필터). `createdAt` desc, 최대 200건, `product` 요약 포함. 응답 행에 `source` 가 실려 어드민이 고객 리뷰의 수정 버튼을 숨긴다(출처 배지는 없다 — 필터로만 가른다) |
| GET    | `/admin/reviews/:id`       | 리뷰 상세                                           |
| POST   | `/admin/reviews`           | 리뷰 생성 — `createdAt` 을 넘기면 원본 작성일 보존(생략 시 `now()`) |
| POST   | `/admin/reviews/bulk`      | 리뷰 일괄 생성 (일괄 입력 그리드, `items` 1~2000) → `{ count }` |
| POST   | `/admin/reviews/extract`   | 리뷰 스크린샷(R2 URL, `imageUrls` 1~20) 비전 LLM 분석 → `{ reviews }` 후보 반환(DB 미기록) |
| PATCH  | `/admin/reviews/:id`       | 리뷰 수정                                           |
| DELETE | `/admin/reviews/:id`       | 리뷰 삭제                                           |

## public-reviews.controller.ts (`@Controller('v1/reviews')`)

> 전체 라우트 public (Nest 가드 없음). 고객 작성 3 라우트(`form`·`submit`·`upload`)는 링크 토큰(`t`)이 인증이고 **위조 토큰·없는 주문·취소/미결제 주문은 전부 같은 404** 다(열거 방지 — 주문 모집단은 `CONTACT_ORDER_WHERE`). ⚠️ 목록·상세 응답에서 `orderId` 는 벗긴다(`stripOrderId`) — 손님 배지는 `source` 로 충분하다. ⚠️ 리뷰에는 `PUBLIC_PRODUCT_WHERE` 게이트가 걸려 있지 않다 — 어드민 목록과 같은 `ReviewsService.findAll` 을 그대로 쓰므로 `productId` 를 지정하지 않으면 비노출 제품의 리뷰도 섞여 나온다. 클라이언트는 항상 `productId` 로 좁혀 호출한다.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/reviews`              | 리뷰 목록 (`productId`, `minRating`, `q` 필터) — 어드민 목록과 동일 서비스(`createdAt` desc, 최대 200건) |
| GET    | `/v1/reviews/translations` | 한 제품 전체 리뷰를 요청 locale 로 일괄 번역(`productId`, `lang`, lazy 캐시) → `{ [reviewId]: content }`. 리터럴 라우트라 `:id` 보다 먼저 선언 |
| GET    | `/v1/reviews/form?t=`      | 고객 작성 폼 → `{ brand{name,slug,logo}, locale, receivedProducts[], otherProducts[], written[], defaultUserName, submittedAt }`. 받은 제품은 일반·현장은 `resolveItemBrands`, 시딩은 `seedingItemNames` → `resolveProductsByLabel` 로 파생. **노출 게이트(`PUBLIC_PRODUCT_WHERE`) 미통과 제품은 양쪽 목록에서 빠진다**(리뷰를 받아도 보일 PDP 가 없다). `otherProducts` 상한 60. `locale`·`submittedAt` 은 `ReviewRequest` 행에서(없으면 null). `defaultUserName` 은 `fullName` 첫 단어. `@Throttle` 20/분 |
| POST   | `/v1/reviews/submit`       | 고객 리뷰 1~20건(`CustomerReviewSubmitInput` — 본문 1~2000자, 사진 ≤5, 요청 내 중복 productId 400). 전 제품이 그 브랜드 소유 + 노출 게이트 통과가 아니면 **400**(브랜드 표면의 404 와 다름 — 자기 주문 범위 입력 오류라 숨길 것이 없다). 사진 URL 은 **이 주문의 업로드 prefix(`R2Service.publicUrlPrefix('reviews/<orderId>')`) 아래만** 허용(400). `sourceLocale` 은 리뷰 번역 locale 만 저장(그 외 null). 이미 쓴 제품 → **409**. `@Throttle` 5/분 |
| POST   | `/v1/reviews/upload`       | 리뷰 사진 presign — `{ t, filename, contentType, kind:'image' }`. 키는 `brands/reviews/<orderId>/images/…`. `@Throttle` 20/분 |
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
| PATCH  | `/v1/brand/reviews/:id`       | 리뷰 수정 (`BrandReviewPatch` — `productId` 불가). 고객 작성(`source='customer'`)이면 **403** |
| DELETE | `/v1/brand/reviews/:id`       | 리뷰 삭제. 고객 작성이면 **403**                               |

⚠️ **고객 작성 리뷰 403 은 이 표면의 404 관례의 의도된 예외다** — 소유 검증을 통과해 브랜드가 그 제품을 실제로 가졌으므로 숨길 것이 없고, 403 이어야 화면이 "왜 안 되는지" 말할 수 있다(`assertReviewOwned`). 어드민은 종전대로 전부 수정·삭제 가능(스팸·욕설 대응). 목록 응답(`BRAND_REVIEW_SELECT`)에 `source` 가 실린다.

⚠️ 브랜드 메서드(`listForBrand`/`createManyForBrand`/`updateForBrand`/`removeForBrand`)는 **전부 기존 어드민 경로와 같은 트랜잭션·`refreshProductAggregates`** 를 거친다. 집계를 우회하는 지름길을 새로 파면 `Product.rating` 이 어긋난 채 klow_web 에 노출된다. `update`/`remove` 는 소유 검증(`assertReviewOwned`)만 따로 걸고 **본체를 어드민 메서드에 위임**한다 — `orNotFound` 까지 함께 타므로 동시 삭제가 raw P2025(500)이 아니라 404 로 나온다(`manual-seeding.service.ts` 의 `assertOwned`→mutate 관용구와 같은 형태이며, 같은 TOCTOU 창을 같은 이유로 받아들인다).
