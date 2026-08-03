# videos — 비디오

- **모듈 경로**: `src/modules/videos/`
- **공개 필터**: **단건(`GET /v1/videos/:id`)의 연관 상품에만** `PUBLIC_PRODUCT_WHERE` 를 적용한다(미승인/미완성/비노출 상품은 include 에서 제외). ⚠️ 목록(`GET /v1/videos`)은 상품을 include 하지 않고 `_count.products`(게이트 미적용 원시 카운트)만 내려주므로, 목록의 상품 수와 상세의 상품 수가 다를 수 있다.
- **가격 부착**: 단건은 임베드된 상품마다 `attachCustomerPricing` 으로 `customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`/`freeShipping` 을 붙인다(`?country=` 목적국, 미지정 US — [products](./products.md) 참고).
- **관련 파일**: `videos.service.ts`, `admin-videos.controller.ts`, `public-videos.controller.ts`
- **[2026-07-30 제거]** 고정 고민/피부타입 키워드 폐지로 `Video.concerns` / `Video.forSkinTypes` 컬럼이 drop 됐다 — `VideoInput` 에도 없다.

## admin-videos.controller.ts (`@Controller('admin/videos')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/videos`            | 비디오 목록 → `{ data, total }`. `q`(title), `creatorId`, `sort`(`updatedAt_desc`(기본)\|`views_desc`), `take`(1~200, 기본 50)/`skip`. `creator` 요약 + `_count.products` 포함 |
| GET    | `/admin/videos/:id`        | 비디오 상세 — 게이트 없이 **전 상품** include(`publicOnly` 미지정) |
| POST   | `/admin/videos`            | 비디오 생성 — `productIds` 배열 순서가 `VideoProduct.order` 가 된다 |
| PATCH  | `/admin/videos/:id`        | 비디오 수정 — ⚠️ 부분 patch 가 아니라 **`VideoInput` 전체**를 검증하고, `VideoProduct` 는 delete → recreate 로 **전량 교체**한다 |
| DELETE | `/admin/videos/:id`        | 비디오 삭제                                         |

## public-videos.controller.ts (`@Controller('v1/videos')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                              |
|--------|----------------------------|-------------------------------------------------------------------|
| GET    | `/v1/videos`               | 비디오 목록 — `creatorId`, `productId` 필터. `updatedAt` desc, 최대 200건. `creator` 요약 + `_count.products` (상품 자체는 미포함) |
| GET    | `/v1/videos/:id`           | 비디오 상세 — 연관 products include(공개 상품만) + `?country=` 기준 소비자가 부착. 없으면 404 |
