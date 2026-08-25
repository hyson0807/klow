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
- **태그·성분 배열의 순서 = 고객 화면 순서 (2026-08-19)**: `concerns` / `recommendedFor` / `keyIngredients` 는
  **저장 순서 그대로가 노출 순서**다. klow_web PDP(`ProductAccordionCard`)가 서버 배열을 변형 없이 렌더하고,
  핵심 성분은 그 위치로 `01 / 02 / 03` 번호까지 매긴다. 브랜드가 klow_brand 스튜디오에서 **드래그로 직접 정렬**한다
  (칩은 `TagChipInput`, 성분 행은 `KeyIngredientRows` — 둘 다 `@dnd-kit`).
  ⚠️ **서버·클라 어디서도 이 배열을 정렬·중복제거하지 말 것** — 지금 zod·저장·`localize()` 어디에도 정렬이 없고,
  넣는 순간 브랜드가 정한 순서가 조용히 뭉개진다.
  ⚠️ `recommendedFor` 프리셋 overlay 는 `Product.recommendedFor[idx]` ↔ `ProductTranslation.recommendedFor[idx]` 를
  **인덱스로 짝짓는다**. 순서만 바꿔도 안전한 건 재정렬이 `prisma.product.update` 를 타 `@updatedAt` 이 올라가
  캐시가 스테일로 판정돼 재번역되기 때문이다 — **raw SQL·`updateMany` 로 순서만 바꾸면 로케일 라벨이 한 칸씩 밀린다.**
  스키마·API 계약·마이그레이션 무변경(배열 컬럼이 원래 순서를 보존한다).
- **카테고리 표시명 번역 (2026-08-14)**: `Product.category`(자유 문자열 1~60자)도 `?lang=` 에서 로케일화된다.
  종전엔 번역 대상이 아니어서 klow_web PDP 가 영문 원문을 그대로 렌더했다. **하이브리드**다 —
  고정 7종(`categoryKey != null`)은 `category-presets.ts` 큐레이션 사전, 브랜드 "직접 입력" 카테고리
  (`categoryKey == null`)는 `ProductTranslation.category` MT 캐시. 프리셋을 못박은 이유는 피부 타입과 같다:
  한 단어라 MT 가 문맥을 못 잡아 `serum` → `血清`/`Huyết thanh`(혈청), `cream`(zh) → `奶油`(유제품),
  `mask`(zh) → `面具`(가면), `mist` → 6개 중 5개 로케일이 **기상 안개**로 나왔다.
  ⚠️ 치환은 여기서도 `localize()` **overlay** 이고, 추가로 **`if (!t) continue` 앞**에 둔다 —
  프리셋은 캐시 행이 아예 없어도(신규 제품 첫 조회·번역 실패) 적용돼야 한다.
  ⚠️ `categoryLabel()` 은 **키뿐 아니라 저장된 영문 표시명까지 대조**한다. 어드민 제품 폼은 `category` 를
  `categoryKey` 와 독립된 자유 텍스트로 받으므로(`categoryKey='serum'` + `category='Vitamin C Ampoule'`),
  키만 보고 치환하면 운영자가 정한 이름을 프리셋이 뭉갠다. 어긋나면 `null` → MT 폴백.
  ⚠️ 스테일 마커가 `t.concerns === null` → **`t.category === null`** 로 이동했다. 그래서 배포 직후
  **기존 캐시 전 행 × 전 로케일이 한 번씩 재번역**된다(제품당 1회, 읽기 경로에서 점진 해소, 백필 없음).
  마이그레이션 `20260814123933_add_product_translation_category` 는 nullable ADD COLUMN 이라 **롤링 배포 안전**.
  klow_web `src/i18n/locales/*` 의 `labels.category.*`(쇼핑 카테고리 바)와 klow_brand `src/lib/i18n.ts` 의
  목업 라벨은 **의도된 크로스 레포 미러**다 — 셋 다 같은 MT 오번역을 갖고 있었고 같은 커밋에서 함께 고쳤다.
  ⚠️ **직접 입력 카테고리는 `categoryKey` 가 없어 klow_web 쇼핑 카테고리 바·추천 필터에 잡히지 않는다**
  (치과재료 선례와 동일한 트레이드오프 — 브랜드 폼 힌트가 이 점을 안내한다).
- **국가별 가격 배열 상한 (2026-08-14)**: `countryPrices` 의 zod 상한이 `98` → `COUNTRY_PRICE_ROWS_MAX = 250`.
  ⚠️ 98은 `SeedingRate` 요율표 국가 수(= 주문 가능국 수)를 그대로 베낀 값이라 **여유가 정확히 0** 이었다.
  klow_brand 가격 탭의 "모든 국가 무료배송" 일괄 토글이 주문 가능국 전체를 한 배열로 보내므로, 요율표에
  국가가 하나만 늘거나 주문 불가국에 옛 핀이 남아 있으면 99행이 되어 **제품 저장 전체가 400** 이 됐다.
- **관련 파일**: `products.service.ts`, `admin-products.controller.ts`, `public-products.controller.ts`, `product-selects.ts`, `product-translation.service.ts`(로케일 오버레이), `product-translation-overrides.ts`(브랜드 수동 번역), `skin-type-presets.ts`(피부 타입 고정 사전), `category-presets.ts`(카테고리 고정 사전)

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
| GET    | `/v1/products`             | 상품 목록 — `q`(name/brand), `categoryKey`, **`minDiscount`**(정수, `Product.discount >= n`), `sort`=`discount_desc`\|`popular`, `take`(1~200, 기본 200), `brandId`, `lang`, `country`, `promotion`, `mode` |
| GET    | `/v1/products/:id`         | 상품 상세 — `lang`, `country`, `promotion`, `mode`. 게이트 미통과 제품은 404          |

- **`sort`**: `discount_desc`(=`discount` desc) / `popular`(=`rating` desc → `reviewCount` desc — 삭제된 discover 모듈의 bestsellers 정렬을 승계한 "추천/인기" 단일 출처). 미지정 시 `brandId` 필터가 있으면 어드민 수동 정렬(`order` asc → `createdAt` desc), 그 외 `updatedAt` desc.
- **`country`**: ISO2 목적국. 위 "공개 응답의 가격 필드" 참고(미지정 US).
- **`promotion`**: 인플루언서 프로모션 링크 유입 시의 프로모션 code. 서버가 재검증해 **그 링크에 세일가가 정해진 제품만** 그 가격으로 내려준다(안 정한 제품은 정상가). 세일가는 국가 핀·국가 할인을 outright 이긴다(max 병합 아님) — [promotions](./promotions.md).
- **`mode=onsite`**: 현장(박람회 부스) QR 모드. **`brandId` 와 함께일 때만 유효** — 목록에서 `onsiteExcluded=true` 제품을 숨기고, 표시가를 `onsitePriceLine()` 이 산출한 단일가로 덮는다. 현장주문 생성(`orders.createOnsite`)이 **같은 함수**로 청구액을 산출하므로 표시가==청구가. raw `onsitePriceUsd`/`onsiteExcluded` 필드는 응답에서 제거된다. (상세 라우트는 `brandId` 없이 `mode=onsite` 만으로 표시가를 덮는다.)
  - **가격 우선순위**: `?country=` 목적국의 `ProductOnsiteCountryPrice.priceLocal`(현지통화 → `customerUsdCentsFromLocal` 로 USD 센트 환산) > `Product.onsitePriceUsd`(브랜드가 정한 기준 현장가) > `defaultListUsd(row)`(일반 default 판매가 = 신모델은 `salePrice`+`basePriceFxRate` 파생, legacy 는 `basePriceUsd`).
  - ⚠️ 마지막 폴백이 **`basePriceUsd ?? 0` 이 아니라 `defaultListUsd`** 인 게 중요하다 — 이전 구현은 `basePriceUsd` 가 null 인 브랜드 신모델 제품을 현장모드에서 **$0 으로 표시·청구**했다(공짜 판매). 회귀 가드는 `__tests__/onsite-pricing.spec.ts`.
  - 국가별 **할인·프로모션·무료배송은 현장에 적용하지 않는다**(현장은 배송이 없다). 현장 응답의 `freeShipping` 은 항상 `false` 다 — 소매 국가 행의 값을 흘리면 부스 화면에 엉뚱한 "무료배송" 배지가 뜬다.
  - **표시용 할인율 `Product.onsiteDiscountPct`** (2026-08-13): 브랜드가 현장 탭에서 세팅한 가격(기준가 파생 + 국가 핀)이 **이미 할인이 적용된 최종 판매가**라는 전제로, 그 위에 취소선만 역산해 보여준다 — `listPriceUsd = listPriceUsdCents(청구가, pct)`(소매 글로벌 `Product.discount` 취소선과 같은 헬퍼), `customerDiscountPercent = pct`. **`customerPriceUsd` 와 정산가는 pct 와 무관하게 불변**이고, `onsitePriceLine()` 은 이 값을 **인자로 받지도 않으며** 청구 경로(`orders.createOnsite`)의 select 에도 **없다** — "할인이 청구가를 못 건드린다"가 리뷰가 아니라 쿼리로 강제된다. 핀이 있는 국가는 취소선도 **핀 통화에서 직접** 파생해(`listPriceLocal = 핀 × 100 / (100 − pct)`) 내려보낸다 — USD 센트로 왕복하면 판매가는 정확한데 취소선만 최소단위 1 어긋난다(A$30 핀 20% → A$37.50 대신 A$37.51). ⚠️ 통화 소수자리 반올림은 서버가 하지 않는다(`PricingCtx` 에 통화코드가 없다) — klow_web 의 Intl 이 처리한다. pct 0·100↑·음수는 취소선을 만들지 않는다. 회귀 잠금은 `__tests__/onsite-pricing.spec.ts` 의 `onsiteDiscountPct` 블록.
  - **분기 위치**: 현장/일반은 `PricingCtx.onsite` 로 갈리고 판정은 `attachCustomerPricing()` **안**에서 끝난다. 호출부가 DTO 를 사후에 덮어쓰지 않는다 — 예전엔 목록·단건이 각자 `delete bag.onsitePriceUsd` 로 원본을 지웠고, 그 손으로 관리하던 목록에 새 컬럼(`onsiteSettleKrw`)이 누락돼 공개 응답으로 샜다. 지금은 현장 원본 5종(`onsitePriceUsd`/`onsiteSettleKrw`/`onsiteExcluded`/`onsiteDiscountPct`/`onsiteCountryPrices`)이 전부 선언적 `StrippedPricingKeys` 로 벗겨진다. ⚠️ 목록 select 는 명시적이라 `onsiteDiscountPct: true` 를 빠뜨리면 취소선이 PDP(include 경로)에만 뜨고 브랜드관 그리드에는 안 뜬다.

## 브랜드 수동 번역 오버라이드 (2026-08-25)

기계번역이 부정확한 **자유 텍스트**를 브랜드가 직접 고칠 수 있게 한 통로. 스튜디오 목업에서 국가를 고르면 이미 그 나라 언어로 보이므로, 거기서 **텍스트를 눌러 올바른 번역을 타이핑**하면 그 값이 고객 화면에 그대로 나간다. 프리셋(피부 타입·카테고리)이 값이 유한한 필드만 구제할 수 있었던 것에 대한 일반해다.

- **저장은 신규 테이블 `ProductTranslationOverride`**(`@@unique([productId, locale])`, `entries Json`). ⚠️ `ProductTranslation` 에 컬럼을 붙이지 **않았다** — 그쪽은 스테일마다 upsert 로 덮이는 소모품이라 누가 재번역을 강제하려고 테이블을 비우면 사람이 쓴 원고가 사라진다. 결정적으로, **캐시 행이 없는 로케일**에 오버라이드를 넣으려면 가짜 캐시 행(`sourceUpdatedAt` 조작 + MT 컬럼 전부 null)을 지어내야 하고 그 행은 곧바로 `t.category === null` 스테일 마커에 걸린다.
- **모양**: `{ v: 1, fields: { <필드키>: { <영문 원문>: <번역문> } } }`. ⚠️⚠️ **안쪽 키가 영문 원문 문자열인 것이 설계의 핵심**이다 — ① 태그·성분을 재정렬하거나 중간을 지워도 짝이 안 밀린다(`recommendedFor` 프리셋 overlay 가 인덱스로 짝지어 생긴 취약점을 구조적으로 회피) ② **원문을 고치면 키가 빗나가 자동으로 MT 로 폴백**한다. 즉 "원문이 바뀌면 수동 번역 서빙을 멈춘다"가 **비교 코드 0줄**로 성립하고, 스테일한 번역이 고객에게 나가는 경로가 아예 없다(fail-safe) ③ 지웠던 값을 같은 문구로 다시 넣으면 오버라이드가 저절로 되살아난다.
- **필드 15종**은 `common/validation/product.ts` 의 `OVERRIDE_FIELDS` 가 정본이고, 이름은 klow_brand `product-form/product-fields.ts` 의 `PRODUCT_TEXT_LIMITS` 키와 **일부러 같다**(라벨 `productFieldLabel` 재사용). `keyIngredients` 는 한 행에 문자열이 2개라 `keyIngredientName`/`keyIngredientEffect` **두 키로 나눈다**(네임스페이스가 갈려야 같은 영문이 성분명이자 효과일 때 안 섞인다). ⚠️ `ingredients`(전성분 INCI)는 국제 표준 영문이라 **영구 제외**. `detailDescription`/`empathyCards` 는 목업이 렌더하지 않아 지금은 빠져 있다.
- **우선순위 = 오버라이드 > 프리셋(피부타입·카테고리) > MT 캐시 > 영문 원문.** `localize()` overlay **맨 마지막**에 대입해 이 순서가 필드별 가드 없이 성립한다.
- ⚠️⚠️ **MT overlay 가 덮기 전에 영문 원문을 붙잡아야 한다**(`captureSource`, 행 루프의 첫 문장). 그 시점의 `r.name`·`r.concerns`·`r.usage` 는 아직 영문이고 몇 줄 뒤 사라지는데, 그게 오버라이드 조회 키다. 오버라이드가 없는 제품은 스냅샷을 만들지 않아 비용이 0이다.
- ⚠️ 예전의 `if (!t) continue;` 가 **`if (t) { … }`** 로 바뀌었다 — 오버라이드는 캐시 행이 아예 없어도(신규 제품 첫 조회·번역 실패) 적용돼야 한다. 카테고리 프리셋이 이미 같은 이유로 그 위에 나와 있다.
- ⚠️ **치환을 `translateAndCache()` 에 두지 말 것** — 프리셋 2건이 못박은 규칙과 같다. 스테일에 걸린 행만 고쳐져 **이미 캐시된 로케일이 영원히 MT 를 서빙**한다.
- ⚠️ 배열 필드는 **영문 스냅샷의 길이가 정본**이고, 이미 화면에 놓인 값(MT·프리셋)은 **길이가 정확히 같을 때만** 인덱스로 재사용한다(legacy/torn 캐시 행을 억지로 짝지으면 라벨이 한 칸 밀린다). ⚠️ `captureSource` 의 성분 배열은 **빈 값을 걸러내지 않는다** — 효과가 빈 행이 하나만 있어도 `filter(Boolean)` 을 태우면 뒤 행이 전부 밀린다.
- ⚠️ 읽기 경로는 캐시와 오버라이드를 **`Promise.all` 로 병렬 조회**한다(목록·PDP 핫 경로라 직렬로 이으면 왕복이 더해진다). 이 쿼리를 없애겠다고 **`Product` 에 마커 컬럼을 두면 안 된다** — `@updatedAt` 이 어떤 write 에도 반응해 6개 로케일 캐시가 전부 무효화되고 재번역 폭풍이 난다. **오버라이드 읽기·쓰기 어느 쪽도 `Product` 를 쓰지 않는다**(스펙이 단언).
- ⚠️⚠️ **고아 엔트리를 전부 물어보지 않는다.** `driftOf` 는 **스칼라 필드 + 후보가 정확히 1개**인 경우만 보고하고, 나머지는 `pruneUnreportable` 이 조용히 지운다(`updateProduct` 가 태그·성분 편집 직후 호출). 이유는 필드 성격이 다르기 때문이다 — 스칼라(제품명·사용방법) 고아는 "그 필드의 텍스트가 수정됨"이라 브랜드가 쓴 번역이 새 원문에도 대체로 맞으니 물을 가치가 있지만, **배열(태그·성분) 고아는 "그 항목이 삭제됨"** 이라 같은 배열의 다른 항목은 개명된 버전이 아니라 별개 개념이다. 예전엔 태그를 지우면 "원문이 바뀐 번역 1건이 꺼져 있어요" 배너가 뜨고 모달이 **`うるおいチャージ`(Hydration 의 번역)를 `Skin texture` 에 붙이라고 제안**했다 — 소음이자 오답 유도였다. 부수 효과로 **보고되는 드리프트의 `candidates` 는 언제나 정확히 1개**가 되어 모달에서 선택기와 빈 상태 UI 가 통째로 사라졌다. ⚠️ `pruneUnreportable` 은 규칙을 따로 쓰지 않고 **`driftOf` 결과를 빼는 식**으로 정의한다 — "물어보지 않는 고아는 지운다"가 한 문장으로 성립하고 두 규칙이 갈라질 수 없다. ⚠️ 스냅샷에 없는 필드(원문을 모르는 list select 등)는 양쪽 다 **건드리지 않는다**.
- **브랜드 라우트 4개**는 brand-applications 모듈이 호스팅한다 — [`brand-applications.md`](./brand-applications.md) 참고.
- **마이그레이션 `20260825010947_add_product_translation_override`** 는 `CREATE TABLE` + 인덱스 2개 + FK 뿐이라 **롤링 배포 안전 · 백필 없음**. 무엇보다 **스테일 마커가 이동하지 않아 재번역·Google 과금이 0**이다(`20260814123933_add_product_translation_category` 는 배포 직후 전 캐시 행 × 전 로케일을 재번역시켰다). 구 인스턴스는 새 테이블을 안 읽고, 신 인스턴스는 빈 테이블에서 overlay 가 no-op 이라 양방향 안전.
- **알려진 갭**(이 작업이 만든 게 아님): `cart.service.ts` 는 `localize()` 를 아예 타지 않아 `product.name` 을 **영문 그대로** 내려준다. 브랜드가 일본어 제품명을 넣어도 로그인 사용자의 서버 카트에는 영문이 뜬다. 기존 MT 에서도 같았다.
- **관련 파일**: `product-translation-overrides.ts`(순수 로직 — 파싱·병합·드리프트), `product-translation.service.ts`(overlay + 쓰기 메서드), `common/validation/product.ts`(필드·로케일·길이 정본). 회귀 잠금은 `__tests__/translation-override.spec.ts`(overlay 14케이스) + `__tests__/translation-override-shape.spec.ts`(순수 헬퍼).
- ⚠️ `category-overlay.spec.ts`·`skin-type-overlay.spec.ts` 의 Prisma 스텁에 **`productTranslationOverride: { findMany }` 가 있어야 한다** — `localize()` 가 병렬로 읽으므로 없으면 그 스펙 전체가 TypeError 로 죽는다.

## 참고

- `Product.status` ENUM: `pending` / `approved` / `rejected`. 기존 행은 마이그레이션 시 `approved` 로 백필됨.
- 어드민이 만든 상품도 `Product` 모델을 공유하지만, 어드민 페이지에서는 모든 상태가 보임.
- 어드민 create/update 는 `brandId` 가 오면 연결된 `Brand.name` 으로 비정규화 컬럼 `Product.brand` 를 덮어쓴다(`syncBrandName`, 없는 brandId 면 404). `countryPrices` 는 `writeProductCountryPrices` 로 **replace-all** 저장되고, PATCH 에서 키 자체가 없으면 국가별 핀은 미변경.
- **[2026-07-30 제거]** `discover` 모듈(`/v1/discover*`) 전체가 삭제되고 `GET /v1/products?sort=popular` 로 대체됐다. 고정 고민/피부타입 키워드 enum 도 함께 폐지 — 위 "자유 텍스트 태그" 참고.
