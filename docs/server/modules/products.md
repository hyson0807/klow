# products — 상품

- **모듈 경로**: `src/modules/products/`
- **공개 필터**: `PUBLIC_PRODUCT_WHERE`(= `PURCHASABLE_PRODUCT_WHERE`, 노출=구매 가능 시점이라 동일 조건). 게이트: `Product.status='approved'` + 대표사진(`image != ''`) + 가격 완성도 `hasSellablePrice`(`basePriceUsd>0` OR (`basePriceFxRate≠null` & `salePrice>0`), Prisma 짝은 `SELLABLE_PRICE_WHERE`) + **`Product.hidden=false`**(2026-07-03 추가, 브랜드가 스튜디오에서 직접 가린 제품 제외) + 브랜드 노출(가입 brand `submittedById != null` 는 `Brand.status='approved'` & 구독 active 동안만 / 어드민 생성 brand `submittedById = null` 은 `Brand.status='approved'` 만 / legacy `brandId = null` 은 면제).
- **`Product.hidden` 토글**: 노출/판매만 끄고 status 는 유지. **브랜드 셀프 토글은 [brand-applications](./brand-applications.md) `PATCH /v1/brand/products/:id/hidden`** 에 있다(이 모듈엔 hidden 라우트 없음). 어드민 목록 응답은 `approvedHiddenReason()` 결과를 **`hiddenReason` 필드**로 실어 뱃지에 쓴다 — `hidden_by_brand` / `incomplete` / `brand_unapproved` / `subscription_inactive`, 정상 노출이면 `null`. `status='approved'` 인 행에만 계산하고 pending/rejected 는 항상 `null`.
- **공통 select**: `product-selects.ts` 의 `PRODUCT_LIST_SELECT`/`isPurchasable`/`approvedHiddenReason` 등을 모든 surface 가 공유.
- **무료배송 노출**: 무료배송은 **국가별**(`ProductCountryPrice.freeShipping`)이라 `PRODUCT_COUNTRY_PRICE_SELECT`
  가 이미 실어 오고, `attachCustomerPricing` 이 `resolveFreeShipping(row, ctx.iso2)` 로 **목적국 값**을 파생해
  공개 응답 `freeShipping` 에 싣는다(`?country=` 미지정이면 US). 행이 없는 국가는 유료 — fail-closed.
  ⚠️ 응답의 `freeShipping` 은 **그 한 나라에 대한 값**이라 카트/스토어에 스냅샷하면 배송지를 바꿀 때 어긋난다(배지 표시 전용).
  ⚠️ 브랜드 스튜디오용 `mapBrandProduct` 는 대신 **국가 목록** `freeShippingCountries: string[]` 을 돌려준다 —
  스튜디오는 국가별 원본이 필요한데 파생값은 한 나라 기준이라(국가 미지정 → US) 폼 재구성에 쓸 수 없다.
- **공개 응답의 가격 필드 (2026-07-28~30 가격 모델)**: 모든 공개 read 는 `?country=`(미지정 US)를 받아
  `attachCustomerPricing` 으로 **목적국 기준 파생값** `customerPriceUsd` / `listPriceUsd` /
  `customerDiscountPercent` / `freeShipping` 을 싣는다(앞의 두 금액은 **USD 센트**). 사업 기밀인 내부 가격
  (`costKrw` / `salePrice` / `basePriceUsd` / `basePriceFxRate` / `countryPrices` / `brandId`)과
  게이트 판정용 `brandRef` 는 **기본값이 strip**(fail-closed)이고, 어드민 목록/단건처럼 원가가
  정당하게 필요한 내부 surface 만 `{ includeInternalPricing: true }` 로 유지한다(`brandRef` 는 내부에서도 항상 strip).
- **자유 텍스트 태그 (2026-07-30)**: `concerns`(8개) / `recommendedFor`(6개)는 고정 enum 이 아니라 **영문 자유 텍스트 태그**다.
  `concerns` 는 `PRODUCT_LIST_SELECT` 에도 포함돼 카드에서 상세 fetch 없이 노출되고, `?lang=` 이 오면
  `ProductTranslationService.localize()` 가 `ProductTranslation` MT 캐시로 로케일 문자열을 덮어쓴다.
- **피부 타입 프리셋 예외 (2026-08-13)**: `recommendedFor` 만 고정 선택지 5종(지성·건성·민감성·복합성·수부지 →
  `Oily skin`/`Dry skin`/`Sensitive skin`/`Combination skin`/`Dehydrated oily skin`)이 **MT 대신 큐레이션 번역**을 탄다.
  한 단어짜리 태그라 문맥이 없어 Google 이 "지성"을 `Intellect` 로 옮겼기 때문. 사전은 `skin-type-presets.ts`,
  치환은 `localize()` **overlay** 에서 한다 — ⚠️ `translateAndCache()` 에서 하면 스테일 판정에 걸린 행만 고쳐져
  이미 캐시된 로케일 행이 오번역을 계속 서빙한다(overlay 라 캐시 무효화·백필 없이 소급된다).
  저장 정본·컬럼·검증(`EnglishTagList(6)`)은 그대로이고 `concerns` 는 순수 자유 텍스트로 남는다.
- **관련 파일**: `products.service.ts`, `admin-products.controller.ts`, `public-products.controller.ts`, `product-selects.ts`, `product-translation.service.ts`(로케일 오버레이), `skin-type-presets.ts`(피부 타입 고정 사전)

## admin-products.controller.ts (`@Controller('admin/products')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/products`          | 상품 목록 → `{ data, total }`. `q`(name/brand), `categoryKey`, `brandId`, `status`, `view`(pending/selling/hidden/rejected 노출칩 — 지정 시 `status` 보다 우선), `hasDiscount`, `sort`(`updatedAt_desc`(기본)\|`price_asc`\|`price_desc`\|`discount_desc`), `take`(1~200, 기본 50)/`skip`. 각 행에 내부 가격 + `hiddenReason` 포함 |
| GET    | `/admin/products/:id`      | 상품 상세                                           |
| POST   | `/admin/products`          | 상품 직접 생성                                      |
| PATCH  | `/admin/products/:id`      | 상품 수정                                           |
| DELETE | `/admin/products/:id`      | 상품 삭제                                           |

## public-products.controller.ts (`@Controller('v1/products')`)

> 전체 라우트 public, `PUBLIC_PRODUCT_WHERE` 자동 적용.

| Method | Path                       | 기능                                                                                |
|--------|----------------------------|-------------------------------------------------------------------------------------|
| GET    | `/v1/products`             | 상품 목록 — `q`(name/brand), `categoryKey`, **`minDiscount`**(정수, `Product.discount >= n`), `sort`=`discount_desc`\|`popular`, `take`(1~200, 기본 200), `brandId`, `lang`, `country`, `campaign`, `mode` |
| GET    | `/v1/products/:id`         | 상품 상세 — `lang`, `country`, `campaign`, `mode`. 게이트 미통과 제품은 404          |

- **`sort`**: `discount_desc`(=`discount` desc) / `popular`(=`rating` desc → `reviewCount` desc — 삭제된 discover 모듈의 bestsellers 정렬을 승계한 "추천/인기" 단일 출처). 미지정 시 `brandId` 필터가 있으면 어드민 수동 정렬(`order` asc → `createdAt` desc), 그 외 `updatedAt` desc.
- **`country`**: ISO2 목적국. 위 "공개 응답의 가격 필드" 참고(미지정 US).
- **`campaign`**: 인플루언서 캠페인 링크 유입 시의 캠페인 code. 서버가 재검증해 대상 브랜드·국가일 때만 할인을 적용한다([campaigns](./campaigns.md)).
- **`mode=onsite`**: 현장(박람회 부스) QR 모드. **`brandId` 와 함께일 때만 유효** — 목록에서 `onsiteExcluded=true` 제품을 숨기고, 표시가를 `onsitePriceLine()` 이 산출한 단일가로 덮는다(할인/취소선 없음, `customerDiscountPercent=0`). 현장주문 생성(`orders.createOnsite`)이 **같은 함수**로 청구액을 산출하므로 표시가==청구가. raw `onsitePriceUsd`/`onsiteExcluded` 필드는 응답에서 제거된다. (상세 라우트는 `brandId` 없이 `mode=onsite` 만으로 표시가를 덮는다.)
  - **가격 우선순위**: `?country=` 목적국의 `ProductOnsiteCountryPrice.priceLocal`(현지통화 → `customerUsdCentsFromLocal` 로 USD 센트 환산) > `Product.onsitePriceUsd`(브랜드가 정한 기준 현장가) > `defaultListUsd(row)`(일반 default 판매가 = 신모델은 `salePrice`+`basePriceFxRate` 파생, legacy 는 `basePriceUsd`).
  - ⚠️ 마지막 폴백이 **`basePriceUsd ?? 0` 이 아니라 `defaultListUsd`** 인 게 중요하다 — 이전 구현은 `basePriceUsd` 가 null 인 브랜드 신모델 제품을 현장모드에서 **$0 으로 표시·청구**했다(공짜 판매). 회귀 가드는 `__tests__/onsite-pricing.spec.ts`.
  - 국가별 **할인·캠페인·무료배송은 현장에 적용하지 않는다**(현장은 배송이 없고 할인 개념도 없다). 현장 응답의 `freeShipping` 은 항상 `false` 다 — 소매 국가 행의 값을 흘리면 부스 화면에 엉뚱한 "무료배송" 배지가 뜬다.
  - **분기 위치**: 현장/일반은 `PricingCtx.onsite` 로 갈리고 판정은 `attachCustomerPricing()` **안**에서 끝난다. 호출부가 DTO 를 사후에 덮어쓰지 않는다 — 예전엔 목록·단건이 각자 `delete bag.onsitePriceUsd` 로 원본을 지웠고, 그 손으로 관리하던 목록에 새 컬럼(`onsiteSettleKrw`)이 누락돼 공개 응답으로 샜다. 지금은 현장 원본 4종(`onsitePriceUsd`/`onsiteSettleKrw`/`onsiteExcluded`/`onsiteCountryPrices`)이 전부 선언적 `StrippedPricingKeys` 로 벗겨진다.

## 참고

- `Product.status` ENUM: `pending` / `approved` / `rejected`. 기존 행은 마이그레이션 시 `approved` 로 백필됨.
- 어드민이 만든 상품도 `Product` 모델을 공유하지만, 어드민 페이지에서는 모든 상태가 보임.
- 어드민 create/update 는 `brandId` 가 오면 연결된 `Brand.name` 으로 비정규화 컬럼 `Product.brand` 를 덮어쓴다(`syncBrandName`, 없는 brandId 면 404). `countryPrices` 는 `writeProductCountryPrices` 로 **replace-all** 저장되고, PATCH 에서 키 자체가 없으면 국가별 핀은 미변경.
- **[2026-07-30 제거]** `discover` 모듈(`/v1/discover*`) 전체가 삭제되고 `GET /v1/products?sort=popular` 로 대체됐다. 고정 고민/피부타입 키워드 enum 도 함께 폐지 — 위 "자유 텍스트 태그" 참고.
