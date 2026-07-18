# products — 상품

- **모듈 경로**: `src/modules/products/`
- **공개 필터**: `PUBLIC_PRODUCT_WHERE`(= `PURCHASABLE_PRODUCT_WHERE`, 노출=구매 가능 시점이라 동일 조건). 게이트: `Product.status='approved'` + 완성도 `hasSellablePrice`(`image != ''` & (`basePriceUsd>0` OR (`basePriceFxRate≠null` & `salePrice>0`))) + **`Product.hidden=false`**(2026-07-03 추가, 브랜드가 스튜디오에서 직접 가린 제품 제외) + 브랜드 노출(가입 brand `submittedById != null` 는 구독 active 동안만 / 어드민 생성 brand `submittedById = null` 와 legacy `brandId = null` 은 면제).
- **`Product.hidden` 토글**: 노출/판매만 끄고 status 는 유지. **브랜드 셀프 토글은 [brand-applications](./brand-applications.md) `PATCH /v1/brand/products/:id/hidden`** 에 있다(이 모듈엔 hidden 라우트 없음). 어드민 목록은 `approvedHiddenReason`='hidden_by_brand' 뱃지로 표시.
- **공통 select**: `product-selects.ts` 의 `PRODUCT_LIST_SELECT`/`isPurchasable`/`approvedHiddenReason` 등을 모든 surface 가 공유.
- **관련 파일**: `products.service.ts`, `admin-products.controller.ts`, `public-products.controller.ts`, `product-selects.ts`

## admin-products.controller.ts (`@Controller('admin/products')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/products`          | 상품 목록 (`q`, `categoryKey`, `brandId`, `status`, `view`(pending/selling/hidden/rejected 노출칩), `hasDiscount`, `sort`, `take`/`skip`) |
| GET    | `/admin/products/:id`      | 상품 상세                                           |
| POST   | `/admin/products`          | 상품 직접 생성                                      |
| PATCH  | `/admin/products/:id`      | 상품 수정                                           |
| DELETE | `/admin/products/:id`      | 상품 삭제                                           |

## public-products.controller.ts (`@Controller('v1/products')`)

> 전체 라우트 public, `PUBLIC_PRODUCT_WHERE` 자동 적용.

| Method | Path                       | 기능                                                                                |
|--------|----------------------------|-------------------------------------------------------------------------------------|
| GET    | `/v1/products`             | 상품 목록 (`q`, `categoryKey`, `concerns[]`, `discount`, `sort`, `brandId` 필터)    |
| GET    | `/v1/products/:id`         | 상품 상세                                                                           |

## 참고

- `Product.status` ENUM: `pending` / `approved` / `rejected`. 기존 행은 마이그레이션 시 `approved` 로 백필됨.
- 어드민이 만든 상품도 `Product` 모델을 공유하지만, 어드민 페이지에서는 모든 상태가 보임.
