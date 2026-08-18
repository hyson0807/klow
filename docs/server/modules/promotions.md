# promotions — 할인가 브랜드관 링크·유입 추적

> **이름 변경 (2026-08-18): campaign → promotion.** 기능은 그대로고 이름만 바꿨다. 이유는 **`SeedingLink.campaignName`(시딩 발급 배치 라벨)과 용어가 충돌**해서다 — 브랜드 화면에 "시딩 캠페인"과 "할인 캠페인"이 서로 다른 탭에서 같은 단어로 공존했다. ⚠️ **`campaignName` 은 지금도 시딩 것이고 rename 대상이 아니다.**
> 바뀐 것: 테이블 `Campaign`/`CampaignProductPrice`/`CampaignDailyStat` → `Promotion*`, 컬럼 `*.campaignId` → `promotionId`(`Order` 포함), enum `CampaignStatus` → `PromotionStatus`, 라우트 `/{admin,v1/brand}/campaigns`·`/v1/campaigns/track` → `promotions`, 공개 쿼리 `?campaign=` → `?promotion=`, 주문/견적 body `campaign` → `promotion`.
> 안 바뀐 것: **공개 유입 링크 `klow.kr/{brand.slug}/{promotion.slug}`**(배포된 링크가 그대로 살아있다), `Promotion.code` 값, 저장된 데이터 전부.
> 마이그레이션 `20260818021500_rename_campaign_to_promotion` 은 **`ALTER … RENAME` 만** 쓰는 순수 rename(데이터 이동·손실 0)이고, 인덱스·제약 이름까지 함께 바꾼다(안 바꾸면 Prisma 가 드리프트로 보고 rename 마이그레이션을 또 만든다). ⚠️ **이 파일은 손으로 썼다** — `prisma migrate dev` 는 model rename 을 감지하지 못하고 DROP+CREATE 를 생성해 라이브 링크와 `Order` 귀속을 통째로 날린다(CLAUDE.md 의 "수동 SQL 금지" 규칙에 대한 의도적 예외).
> ⚠️ **레거시 별칭이 살아있다** — 배포 창의 구 klow_web 이 계속 옛 이름을 보내면 **세일가가 조용히 정상가로 떨어지므로**, 서버가 공개 쿼리 `?campaign=` 과 주문/견적 body `campaign` 을 당분간 함께 읽는다(`public-products.controller.ts` 의 `legacyCampaign`, `orders.service.ts` 의 `promotionCode()`, `validation/order.ts` 의 `campaign` 필드). **klow_web 배포가 끝나면 이 셋을 함께 제거할 것.**

- **모듈 경로**: `src/modules/promotions/`
- **모델 요약**: **프로모션 1개 = 할인가 브랜드관 링크 1개.** ⚠️ **받는 사람은 인플루언서로 한정되지 않는다** — 브랜드가 원하는 누구에게나(단골·VIP·뉴스레터 구독자·제휴처) 주는 링크이고, klow_brand/klow_admin UI 문구가 그 전제로 쓰여 있다(2026-08-18). "인플루언서 전용"으로 좁히지 말 것. 브랜드가 발급 마법사에서 이름 하나를 넣으면 곧 프로모션 1건이 생성된다(구 "프로모션 컨테이너 + 그 안에 링크 N개" 2단계 구조 폐기).
- **주 클라이언트**: `klow_brand`(자기 할인 링크 CRUD·발급·세일가 편집·유입 차트, `/v1/brand/promotions/*`) + `klow_admin`(전 브랜드 관찰·강제 On/Off·삭제, `/admin/promotions/*`) + 공개 트래픽(klow_web `klow.kr/{brand}/{influencer}` pretty 링크 클릭).
- **데이터 모델**: `Promotion`(brand 소유, `name`(링크 표시명 — 브랜드가 "누구에게 주는 링크인지" 알아보려고 짓는 이름)/`slug`(브랜드 내 유니크, name 에서 자동 생성)/`code`(@unique 6자 영숫자, 유입 식별 키)/`clickCount`(누적)/`enabled`/`status`), **`PromotionProductPrice`**(`promotionId`×`productId`×`iso2` @unique, `priceLocal` Float non-null — 이 링크의 제품×국가 세일가), `PromotionDailyStat`(프로모션×날(KST) 1행, `date`(YYYY-MM-DD)/`clicks` — "기간별 유입 추이" 차트용). 삭제는 `onDelete: Cascade` 로 세일가·일별통계 함께 제거.
- **구매·매출 귀속 (2026-07)**: 체크아웃에 프로모션 code 가 실려 오면 주문 생성 시 **`Order.promotionId`** 로 귀속한다(`orders.service.create` → `resolvePromotionForOrder(code, iso2).id`, **세일가·enabled 무관** — 링크로 유입해 산 사실만 기준, `onDelete: SetNull`). 프로모션별 **구매수·매출**은 `promotions.service` 가 `order.groupBy(by:['promotionId'], where:{ paymentStatus:paid, isSeeding:false })` 로 집계 — **매출은 주문 전체 결제액(`Order.totalUsd`, USD 센트) 합**, pending/refunded/취소/시딩은 제외, 전 기간 누적. `listForBrand` 는 각 item `purchaseCount`(+ KPI `totalPurchases`/`totalRevenueUsd` 합계), `detailForBrand` 는 `purchaseCount`/`revenueUsd` 추가(per-promotion 은 bare 이름, `total*` 은 KPI 합계 전용).
- **유입 세일가 실적용 (2026-08 — 단일 할인율 모델 폐기)**: pretty 링크로 들어온 방문자는 브랜드가 그 링크에 정해둔 **제품×국가 판매가**를 실제 표시가·견적가·결제 청구가로 받는다.
  - ① **범위는 제품 단위**다 — 세일가 행이 있는 제품만 그 가격, **없는 제품은 정상가**(브랜드관은 전 제품을 계속 노출한다). 브랜드 매칭 조건이 따로 없는 이유: `productId` 가 이미 정확한 키이고 소유권은 저장 시점(`assertProductsOwned`)에 강제된다.
  - ② **병합: 프로모션 세일가가 국가 핀(`ProductCountryPrice.priceLocal`)·국가 할인(`discountPct`)을 outright 이긴다 — `max` 병합이 아니다.** 구 모델은 `max(국가할인%, 프로모션할인%)`(고객 유리)였지만, 이제 브랜드가 이 링크·이 나라·이 제품에 대해 **금액을 명시적으로 지정**하므로 그 값이 정본이다. 취소선(`listPriceUsd`)은 프로모션 전 정상 판매가를 그대로 쓰고 표시 할인율은 `round((1 − 청구가/정상가) × 100)` 로 파생한다. ⚠️ 세일가가 정상가보다 **비싸면** 파생 할인율이 음수가 되므로 **0 클램프**(취소선 없이 세일가로 판매). 회귀 잠금: `pricing/__tests__/promotion-pricing.spec.ts`.
  - ③ **유지**: 프로모션이 `enabled && status==='active'` 이고 그 나라 세일가가 하나라도 있는 동안 — **서버가 매 가격요청마다 재검증**하므로 브랜드가 링크를 Off/중지하면 즉시 정상가로 소멸.
  - ④ **정산**: 정산가는 실청구가에서 역산(`settlementKrwFromCustomerUsd`)되므로 **깎은 만큼 브랜드 정산이 줄어든다**(할인분 브랜드 부담). `belowCost` 경고도 세일가 기준으로 뜬다.
  - ⑤ **현장(onsite)은 무관** — `onsitePriceLine` 이 세일가를 인자로 받지도 않고, `resolvePricingCtx` 는 `onsite:true` 면 프로모션 쿼리 자체를 쏘지 않는다.
  - 경로: `trackBySlug` 가 유입 시 `{ code }` 반환 → klow_web `PromotionCapture` 가 `useAppStore.promotionCode`(localStorage)에 저장 → 제품 read(`?promotion=`)·견적/주문(body `promotion`)에 동봉 → 서버 `resolvePromotionPricing(code, iso2)`(그 **목적국 행만** 조회) + `promotionPriceFor(promotion, productId)` 로 `priceLine(..., promotionPriceLocal)` 단일 정본에서 적용(표시가==청구가). 무효/위조 code 는 조용히 무시(정상가).
  - ⚠️ **`billingRate` 가드에 세일가가 반드시 들어가야 한다** — 세일가도 현지통화 값이라, FX 미해결국에서 폴백 `rate=1` 로 환산되면 `¥3,000` 이 `$3,000` 으로 청구된다(국가 핀과 같은 사고). `modules/orders/billing-rate.ts` + `__tests__/billing-rate.spec.ts`.
  - ⚠️ **알려진 갭**: `cart.service.list` 는 프로모션 code 없이 `resolvePricingCtx` 를 호출해 **로그인 서버 카트가 정상가를 보여준다**(quote/create 는 세일가로 청구). 구 `discountPct` 시절에도 있던 구멍이고 가격 정본은 `POST /v1/orders/quote` 다 — 고치려면 `GET /v1/cart` 에 `?promotion=` 을 추가하면 된다.
  - 코드: `pricing/promotion.ts`+`pricing/price-line.ts`, `products.service.ts`(findAll/findOne `promotion`), `orders.service.ts`(quote/create).
- **상태 enum**: `PromotionStatus` = `active` | `ended`. (구 `PromotionPlatform` enum 은 2026-08 에 제거.)
- **프로모션이란**: 브랜드가 **이름 + 제품별·국가별 판매가**를 입력해 발급하면, 서버가 `slug`·`code` 를 발급하고 공개 링크 `klow.kr/{brand.slug}/{promotion.slug}` 를 만든다. 받는 사람(인플루언서·단골·제휴처 등)이 그 링크를 공유 → 방문자 클릭 시 klow_web 이 유입 1 을 집계하고 **그 가격이 적용된 브랜드관**을 렌더한다(방문자는 pretty URL 에 머문다). 세일가는 비워도 발급되고(먼저 링크만 뽑는 흐름) 그때는 정상가 브랜드관으로 동작한다. **발급 후에도 상세 화면에서 언제든 고칠 수 있다.**
- **slug 생성**: `name` → `slugify`(브랜드 slug 와 동일한 정본 규칙, klow_brand `src/lib/slug.ts` `sanitizeSlug` 미러 — lowercase·NFKD·비허용문자→`-`·collapse). 브랜드 내 충돌 시 `-2`/`-3` 접미사(`uniqueSlug`: `startsWith` findMany + in-memory 스캔). `@@unique([brandId, slug])` + `code @unique` 충돌(P2002)이면 최대 5회 재시도(매 시도 slug 재계산). ⚠️ **이름을 바꿔도 slug 를 재발급하지 않는다** — 이미 배포된 링크가 죽는다.
- **세일가 저장은 replace-all**: `POST` 는 `prices` 배열 전체, `PATCH` 는 `prices` 를 **보냈을 때만** 그 프로모션 행을 통째로 갈아끼운다(`deleteMany` → `createMany`, 클라 중복 `(productId,iso2)` 는 마지막 값으로 dedupe). ⚠️ 그래서 클라는 **항상 전체 배열**을 보내야 한다. ⚠️ zod 는 PATCH `prices` 를 **`.optional()`** 로 받는다 — `.default([])` 를 주면 배포 창의 구 klow_brand 탭이 `{status}` 만 보내도 서버가 `prices:[]` 를 주입해 **세일가 전체를 조용히 지운다**(`onsiteDiscountPct`·`externalProductCode` 와 같은 함정). 상한은 `PROMOTION_PRICE_ROWS_MAX = 3000`(제품 × 국가라 곱셈 — 제품 하나짜리 `COUNTRY_PRICE_ROWS_MAX=250` 과 축이 다르므로 재사용하지 않는다). `iso2` 는 주문 가능국 목록과 **대조하지 않는다**(운영팀이 국가를 내리면 스테일 행 하나가 이후 저장 전체를 400 으로 막기 때문 — `BrandProductCountryPriceInput` 과 같은 방침).
- **pretty 링크**: 응답 `url` = `{FRONTEND_URL}/{brand.slug}/{promotion.slug}`(복사·표시 정본, `toDto` 단일 출처). ⚠️ **구 단축링크 `/r/{code}` 는 2026-08 에 제거**했다 — 302 가 code 를 버리고 브랜드관 루트로 보내서 할인이 애초에 걸리지 않았고, 브랜드 UI 에 노출된 적도 없다.
- **클릭 집계 규칙**: 미존재(만료/오타) → 미집계. `enabled=false` 또는 `status!=='active'` → 미집계. 정상이면 `clickCount +1`(단일 update) + 오늘(KST) 일별 버킷 `clicks +1`(fire-and-forget upsert, 동시 첫클릭 P2002 은 update 폴백 후 실패 무시).
- **env**: pretty 링크 베이스는 시딩과 공용 `FRONTEND_URL`(기본 `http://localhost:3001`, 운영 `https://klow.kr`).
- **스코핑**: 브랜드 라우트는 전부 `BrandGuard` + `requireBrandId`(본인 브랜드 스코핑). ⚠️ `updateForBrand` 는 세일가만 보낼 때 스칼라 update 가 비어 `updateMany.count` 로 스코핑을 판정할 수 없으므로 **소유 검증을 `findFirst` 로 먼저** 끝낸다. 어드민 라우트는 `AdminGuard`(brandId 스코핑 없음), mutation 은 글로벌 `AdminAuditInterceptor` 자동 기록. track 라우트는 가드 없음(공개 트래픽).
- **관련 파일**: `promotions.service.ts`(브랜드 CRUD·slug 생성·세일가 replace-all·유입 집계·일별 통계), 컨트롤러 3개(brand·admin·public), `promotions.module.ts`(`BrandAuthModule` import). klow_web `src/app/[brandSlug]/[influencer]/page.tsx`(pretty 랜딩) + `src/lib/brand-server.ts` `trackPromotionVisit`. klow_brand `src/app/(authed)/promotions/`(`PromotionPriceEditor`/`PromotionPriceModal` + `_hooks/usePromotionProducts.ts`) + `src/lib/promotion-prices.ts`(맵↔배열 변환 단일 출처).
- **교차링크**: [brands](./brands.md)(brand.slug 랜딩 대상), [products](./products.md)(`?promotion=` 가격 컨텍스트), [orders](./orders.md)(귀속·청구), [seeding](./seeding.md)(FRONTEND_URL 공용).

## brand-promotions.controller.ts (`@Controller('v1/brand/promotions')`)

> 전체 라우트 `BrandGuard` + `requireBrandId`(본인 브랜드 스코핑). body/query 는 `ZodValidationPipe` 검증.

| Method | Path                              | 기능                                                                                       |
|--------|-----------------------------------|--------------------------------------------------------------------------------------------|
| GET    | `/v1/brand/promotions`             | 내 할인 링크 목록(각 item `id/name/status/clickCount/purchaseCount` — **per-item 매출·세일가는 안 실림**) + KPI(activePromotions/totalClicks/totalPurchases/totalRevenueUsd) |
| POST   | `/v1/brand/promotions`             | 프로모션(=할인 링크) 생성(`name` + `prices[]{productId,iso2,priceLocal}`, prices 는 생략 가능) — slug·code·url 발급 |
| GET    | `/v1/brand/promotions/:id`         | 상세(플랫 DTO: slug·code·url·**prices**(`{productId:{iso2:priceLocal}}` 중첩 맵)·clickCount·purchaseCount·revenueUsd 등) |
| PATCH  | `/v1/brand/promotions/:id`         | 이름(`name?`) + 중지/재개(`status?`) + 링크 On/Off(`enabled?`) + 세일가(`prices?`, **replace-all**) (최소 1필드) |
| DELETE | `/v1/brand/promotions/:id`         | 삭제(세일가·일별통계 cascade)                                                               |
| GET    | `/v1/brand/promotions/:id/stats`   | 일자별 유입 시계열(`days=1~90`, 기본 30, dense 제로필)                                       |

## admin-promotions.controller.ts (`@Controller('admin/promotions')`)

> 전체 라우트 `AdminGuard`(brandId 스코핑 없음 — 전 브랜드 관찰·강제개입). mutation 은 `AdminAuditInterceptor` 자동 기록.
> ⚠️ 세일가는 어드민 DTO 에 싣지 않는다 — 혜택은 브랜드가 klow_brand 에서 관리하고 어드민은 관찰·강제 중지/삭제만 한다.

| Method | Path                   | 기능                                                                     |
|--------|------------------------|--------------------------------------------------------------------------|
| GET    | `/admin/promotions`     | 전체 목록(`q`=링크 이름/브랜드명 검색, `status`, `take`/`skip`)         |
| GET    | `/admin/promotions/:id` | 상세(브랜드 정보 + 프로모션 플랫 필드 + clickCount)                         |
| PATCH  | `/admin/promotions/:id` | On/Off 강제 토글(`status`=active\|ended, 필수)                           |
| DELETE | `/admin/promotions/:id` | 삭제(cascade)                                                            |

## public-promotions.controller.ts (`@Controller('v1/promotions')`)

> 가드 없음 — 공개 트래픽.

| Method | Path                                          | 기능                                                                            |
|--------|-----------------------------------------------|---------------------------------------------------------------------------------|
| GET    | `/v1/promotions/track/:brandSlug/:influencerSlug` | pretty 링크 유입 집계 — klow_web 진입 시 호출. `{ ok, code }` 반환(무효/Off 는 `{ok:false, code:null}`). `code` 는 klow_web 이 localStorage 에 저장해 이후 가격/견적/주문에 동봉하는 **세일가 적용 키** |
