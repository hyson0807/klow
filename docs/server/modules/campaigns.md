# campaigns — 인플루언서 어필리에이트 링크·유입 추적

- **모듈 경로**: `src/modules/campaigns/`
- **모델 요약**: **인플루언서 1명 = 캠페인 1개 = 브랜드관 링크 1개.** 브랜드가 발급 마법사에서 인플루언서 하나를 넣으면 곧 캠페인 1건이 생성된다(구 "캠페인 컨테이너 + 그 안에 링크 N개" 2단계 구조 폐기).
- **주 클라이언트**: `klow_brand`(자기 인플루언서 CRUD·발급·유입 차트, `/v1/brand/campaigns/*`) + `klow_admin`(전 브랜드 관찰·강제 On/Off·삭제, `/admin/campaigns/*`) + 공개 트래픽(klow_web `klow.kr/{brand}/{influencer}` pretty 링크 클릭, 하위호환 `/r/{code}`).
- **데이터 모델**: `Campaign`(brand 소유, `name`(인플루언서 SNS 이름)/`slug`(브랜드 내 유니크, name 에서 자동 생성)/`snsUrl`/`platforms`(복수 `CampaignPlatform[]`)/`countries`(대상국 iso2 `String[]`, 빈 배열=전국가)/`discountPct`(0-90, **실결제 할인 — 아래 유입 할인 참고**)/`memo`/`code`(@unique 6자 영숫자, `/r` 폴백)/`clickCount`(누적)/`enabled`/`status`), `CampaignDailyStat`(캠페인×날(KST) 1행, `date`(YYYY-MM-DD)/`clicks` — "기간별 유입 추이" 차트용). 삭제는 `onDelete: Cascade` 로 일별통계 함께 제거.
- **구매·매출 귀속 (2026-07)**: 체크아웃에 캠페인 code 가 실려 오면 주문 생성 시 **`Order.campaignId`** 로 귀속한다(`orders.service.create` → `resolveCampaignIdByCode(code)`, **할인·enabled 무관** — 링크로 유입해 산 사실만 기준, `onDelete: SetNull`). 캠페인별 **구매수·매출**은 `campaigns.service` 가 `order.groupBy(by:['campaignId'], where:{ paymentStatus:paid, isSeeding:false })` 로 집계 — **매출은 주문 전체 결제액(`Order.totalUsd`, USD 센트) 합**, pending/refunded/취소/시딩은 제외, 전 기간 누적. `listForBrand` 는 각 item `purchaseCount`(+ KPI `totalPurchases`/`totalRevenueUsd` 합계), `detailForBrand` 는 `purchaseCount`/`revenueUsd` 추가(per-campaign 은 bare 이름, `total*` 은 KPI 합계 전용). klow_brand campaigns 페이지 KPI·카드·상세에 표시(전환율·일자별 구매차트는 미도입).
- **유입 할인 실적용 (2026-07)**: pretty 링크로 들어온 방문자는 그 캠페인의 `discountPct` 를 **실제 표시가·견적가·결제 청구가**에 받는다. ① 범위: **그 캠페인 브랜드 제품만** + 방문자 국가가 `countries` 에 포함(빈 배열=전국가)일 때. ② 병합: 국가별 `ProductCountryPrice.discountPct` 와 **더 큰 값(max, 스택 없음)**. ③ 유지: 캠페인이 `enabled && status==='active' && discountPct>0` 인 동안 계속 — **서버가 매 가격요청마다 재검증**하므로 브랜드가 링크를 Off/중지하면 즉시 소멸. 경로: `trackBySlug` 가 유입 시 `{ code }` 반환 → klow_web `CampaignCapture` 가 `useAppStore.campaignCode`(localStorage)에 저장 → 제품 read(`?campaign=`)·견적/주문(body `campaign`)에 동봉 → 서버 `resolveCampaignPricing(code)` + `campaignPctFor(campaign, brandId, iso2)` 로 `priceLine(...campaignPct)` 단일 정본에서 적용(표시가==청구가). 무효/위조 code 는 조용히 무시(정상가). 코드: `product-selects.ts`, `products.service.ts`(findAll/findOne `campaign`), `orders.service.ts`(quote/create).
- **상태 enum**: `CampaignStatus` = `active` | `ended`. `CampaignPlatform` = `IG` | `YT` | `TT`.
- **캠페인이란**: 브랜드가 인플루언서 정보(이름·복수 플랫폼·SNS 주소·메모) + 어필리에이트 혜택(대상 국가·할인율)을 입력해 발급하면, 서버가 `slug`·`code` 를 발급하고 공개 링크 `klow.kr/{brand.slug}/{campaign.slug}` 를 만든다. 인플루언서가 그 링크를 SNS 에 게시 → 유저 클릭 시 klow_web 이 유입 1 을 집계하고 브랜드관을 렌더한다(방문자는 pretty URL 에 머문다). 브랜드는 누적 클릭·일자별 유입 시계열을 대시보드에서 본다.
- **slug 생성**: `name` → `slugify`(브랜드 slug 와 동일한 정본 규칙, klow_brand `src/lib/slug.ts` `sanitizeSlug` 미러 — lowercase·NFKD·비허용문자→`-`·collapse). 브랜드 내 충돌 시 `-2`/`-3` 접미사(`uniqueSlug`: `startsWith` findMany + in-memory 스캔). `@@unique([brandId, slug])` + `code @unique` 충돌(P2002)이면 최대 5회 재시도(매 시도 slug 재계산).
- **pretty 링크 / 폴백**: 응답 `url` = `{FRONTEND_URL}/{brand.slug}/{campaign.slug}`(복사·표시 정본, `toDto` 단일 출처). 구 `/r/{code}` 단축링크도 하위호환으로 유지(`resolveAndCount` → 브랜드관 302). 두 경로 모두 아래 집계 규칙 공유.
- **클릭 집계 규칙**: 미존재(만료/오타) → 미집계·웹 홈 폴백. `enabled=false` 또는 `status!=='active'` → 미집계. 정상이면 `clickCount +1`(단일 update) + 오늘(KST) 일별 버킷 `clicks +1`(fire-and-forget upsert, 동시 첫클릭 P2002 은 update 폴백 후 실패 무시). pretty 경로(`trackBySlug`)는 klow_web 이 이미 brandSlug 를 알므로 집계만 하고 `{ ok }` 반환; `/r/{code}`(`resolveAndCount`)는 리다이렉트 대상 URL 을 반환.
- **env**: 리다이렉트 대상 + pretty 링크 베이스는 시딩과 공용 `FRONTEND_URL`(기본 `http://localhost:3001`, 운영 `https://klow.kr`).
- **스코핑**: 브랜드 라우트는 전부 `BrandGuard` + `requireBrandId`(본인 브랜드 스코핑, mutation 은 `where { id, brandId }` `updateMany`/`deleteMany`). 어드민 라우트는 `AdminGuard`(brandId 스코핑 없음), mutation 은 글로벌 `AdminAuditInterceptor` 자동 기록. track 라우트는 가드 없음(공개 트래픽).
- **관련 파일**: `campaigns.service.ts`(브랜드 CRUD·slug 생성·pretty/short 집계·일별 통계), 컨트롤러 3개(brand·admin·public — public 은 `/r/{code}` 리다이렉트 + `/v1/campaigns/track/*` 집계 두 컨트롤러), `campaigns.module.ts`(`BrandAuthModule` import). klow_web `src/app/[brandSlug]/[influencer]/page.tsx`(pretty 랜딩) + `src/lib/brand-server.ts` `trackInfluencerVisit`.
- **교차링크**: [brands](./brands.md)(brand.slug 랜딩 대상), [seeding](./seeding.md)(FRONTEND_URL 공용).

## brand-campaigns.controller.ts (`@Controller('v1/brand/campaigns')`)

> 전체 라우트 `BrandGuard` + `requireBrandId`(본인 브랜드 스코핑). body/query 는 `ZodValidationPipe` 검증.

| Method | Path                              | 기능                                                                                       |
|--------|-----------------------------------|--------------------------------------------------------------------------------------------|
| GET    | `/v1/brand/campaigns`             | 내 인플루언서 목록(각 item clickCount/purchaseCount/revenueUsd) + KPI(activeCampaigns/totalClicks/totalPurchases/totalRevenueUsd) |
| POST   | `/v1/brand/campaigns`             | 인플루언서(=캠페인) 생성(`name`/`snsUrl`/`platforms[]`/`countries[]`/`discountPct`/`memo?`) — slug·code·url 발급 |
| GET    | `/v1/brand/campaigns/:id`         | 상세(플랫 DTO: slug·url·platforms·countries·discountPct·clickCount·purchaseCount·revenueUsd 등) |
| PATCH  | `/v1/brand/campaigns/:id`         | 중지/재개(`status?`) + 링크 On/Off(`enabled?`, 최소 1필드)                                  |
| DELETE | `/v1/brand/campaigns/:id`         | 삭제(일별통계 cascade)                                                                      |
| GET    | `/v1/brand/campaigns/:id/stats`   | 일자별 유입 시계열(`days=1~90`, 기본 30, dense 제로필)                                       |

## admin-campaigns.controller.ts (`@Controller('admin/campaigns')`)

> 전체 라우트 `AdminGuard`(brandId 스코핑 없음 — 전 브랜드 관찰·강제개입). mutation 은 `AdminAuditInterceptor` 자동 기록.

| Method | Path                   | 기능                                                                     |
|--------|------------------------|--------------------------------------------------------------------------|
| GET    | `/admin/campaigns`     | 전체 목록(`q`=인플루언서명/브랜드명 검색, `status`, `take`/`skip`)         |
| GET    | `/admin/campaigns/:id` | 상세(브랜드 정보 + 인플루언서 플랫 필드 + clickCount)                     |
| PATCH  | `/admin/campaigns/:id` | On/Off 강제 토글(`status`=active\|ended, 필수)                           |
| DELETE | `/admin/campaigns/:id` | 삭제(cascade)                                                            |

## public-campaigns.controller.ts

> 가드 없음 — 공개 트래픽. 두 컨트롤러(`@Controller('r')` + `@Controller('v1/campaigns')`).

| Method | Path                                          | 기능                                                                            |
|--------|-----------------------------------------------|---------------------------------------------------------------------------------|
| GET    | `/r/:code`                                    | (하위호환) 클릭 1 기록 후 브랜드관 302. 무효/Off 는 미집계·홈 폴백               |
| GET    | `/v1/campaigns/track/:brandSlug/:influencerSlug` | pretty 링크 유입 집계 — klow_web 진입 시 호출. `{ ok }` 반환(무효/Off 는 `ok:false`) |
