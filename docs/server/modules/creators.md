# creators — 크리에이터

- **모듈 경로**: `src/modules/creators/`
- **관련 파일**: `creators.service.ts`, `admin-creators.controller.ts`, `public-creators.controller.ts`
- **⚠️ 이 모듈의 `Creator` 는 klow_web 노출용 크리에이터**다. 어드민 인플루언서 탭이 다루는 큐레이션 인플루언서(`CuratedInfluencer`)는 별도 모듈 [curated-influencers](./curated-influencers.md) 이고, 브랜드용 `/v1/brand/creators` 도 그쪽이다.
- **[2026-07-30 제거]** 고정 고민/피부타입 키워드 폐지로 `Creator.skinType` / `Creator.concerns` 컬럼이 drop 됐다 — 입력·필터·응답 어디에도 없다.

## admin-creators.controller.ts (`@Controller('admin/creators')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/creators`          | 크리에이터 목록 → `{ data, total }`. `q`(name/handle), `country`, `isReal`, `sort`(`updatedAt_desc`(기본)\|`createdAt_desc`), `take`(1~200, 기본 50)/`skip`. `_count.videos` 포함 |
| GET    | `/admin/creators/:id`      | 크리에이터 상세                                     |
| POST   | `/admin/creators`          | 크리에이터 생성 (`CreatorInput`)                    |
| PATCH  | `/admin/creators/:id`      | 크리에이터 수정 — ⚠️ 부분 patch 가 아니라 **`CreatorInput` 전체**를 검증한다(`patchOf` 미사용, 필수 필드 누락 시 400) |
| DELETE | `/admin/creators/:id`      | 크리에이터 삭제                                     |

## public-creators.controller.ts (`@Controller('v1/creators')`)

> 전체 라우트 public.

| Method | Path                              | 기능                                                              |
|--------|-----------------------------------|-------------------------------------------------------------------|
| GET    | `/v1/creators`                    | 크리에이터 목록 — 쿼리 파라미터 없음. `updatedAt` desc, 최대 200건, `_count.videos` 포함 |
| GET    | `/v1/creators/:id/products`       | 이 크리에이터의 영상에 붙은 상품 목록 (`VideoProduct` 조인, `productId` distinct, 최대 200). `PUBLIC_PRODUCT_WHERE` 적용 + **`?country=`** 로 목적국 소비자가(`customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`/`freeShipping`) 부착 — 미지정 US. 정렬은 영상 `updatedAt` desc → `VideoProduct.order` asc |
| GET    | `/v1/creators/:id`                | 크리에이터 상세 — 없으면 404 (공개/비공개 구분 없이 전 행 조회)   |
