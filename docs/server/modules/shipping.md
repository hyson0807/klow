# shipping — 배송

- **모듈 경로**: `src/modules/shipping/`
- **데이터 모델**: `ShippingCountry`(국가 설정 + 캐리어), `SeedingRate`(국가×무게 배송비 요율표 — **시딩·일반주문 공용 정본**, `LogisticsRateService` 소유), `ShippingExclusion`(EFS 제외구역), `ShippingCarrier`. (구 `ShippingRate` 무게×캐리어 티어·미러 컬럼·추가요금은 **dormant** — [`docs/cleanup-dormant-shipping-rate.md`](../../archive/cleanup-dormant-shipping-rate.md).)
- **일반 주문 배송 산출 (2026-07-29 요율표 통합)**: 결제 시 `shipping.service.resolveProductShipping(iso2, addr, brandWeights)` 가 `(customerShippingRateKrw, 브랜드별 캐리어, 대표 캐리어)` 를 1회 반환한다.
  - **요율** = `LogisticsRateService.customerShippingRate(iso2)` = `CUSTOMER_SHIPPING_WEIGHT_G(500)` 티어(무게 올림) — `SeedingRate` 국가×무게 요율표. 운영팀이 캐리어 비교·유류할증료·마진을 미리 반영한 정본값(엑셀 `KLOW_시딩_가격표` 고객_가격표)이라 **런타임 비교·할증 가산 없음**. **고객 결제 배송비가 이 값 그대로**이고 **제품 무게와 무관**하다. 500g 이상 티어가 없으면 **구매 차단**(throw).
    - ⚠️ **2026-07-30 전환**: 구 "2kg 티어의 절반" → "500g 티어 그대로". 요율표는 고정비 비중이 커서 무게 비례가 아니다(500g 요율 ≠ 1kg 요율의 절반) — 전환으로 배송비가 **98개국 중 96개국에서 올랐다**(중앙값 +24%, 내려간 곳은 US·PH). `Order.shippingFeeByBrand` 스냅샷이 있으므로 **기존 주문은 소급 영향 없음**.
  - **캐리어** = 무게 분기(`seedingCarrierSplitWeightG`) 있으면 `무게 ≤ 분기값 ? EFS : EMS`, 없으면 국가 고정 `productCarrier`(`EFS`/`EMS`/`EMS_PREMIUM` — DHL 은 zod 에서 선택 불가). ⚠️ **분기는 EFS/EMS 로만 갈리므로 `EMS_PREMIUM` 은 분기를 해제한 국가에서만 적용된다**(고정 캐리어 전용). 표시명은 "EMS-PREMIUM" 이지만 prisma enum 값에 하이픈을 못 써 정본은 언더스코어이고, 프론트가 `carrierLabel()` 로 변환한다. 무게는 **브랜드별 박스 청구중량**(`orders/brand-weights.ts` `brandChargeableWeights` = Σ max(실무게, L×W×H/6)×수량)이라 **한 주문 안에서 브랜드마다 캐리어가 다를 수 있다**(한 브랜드 = 한 송장 = 한 박스). 둘 다 미설정이면 **구매 차단**.
  - **배송지원(`enabled`) 화이트리스트**를 강제한다(`loadEnabledCountry`) — 시딩과 다른 점.
  - EFS 로 해석된 브랜드가 하나라도 있고 주소가 EFS 제외구역(`matchExclusion`)이면 **폴백 없이 차단**. ⚠️ 전부 EMS 로 갈리면 제외구역 주소여도 통과한다(시딩에서 물려받은 성질 — 제외구역은 EFS 제약이므로 의도된 동작).
- **캐리어 산출 (시딩 송장 전용)**: `resolveCarrier(iso2, addr, weightG)` 가 같은 무게 분기(`pickCarrierForWeight`)로 캐리어만 반환한다(비용은 `LogisticsRateService`, 아래 seeding 모듈). 시딩은 `enabled` 게이트 없음(`loadCountry`). 일반주문/시딩 공통 EFS 제외구역 차단은 private `assertNotEfsExcluded` 단일 출처.
- **브랜드별 캐리어 스냅샷**: 한 브랜드 = 한 송장 = 한 박스. **무게 분기국에서는 브랜드마다 캐리어가 갈릴 수 있으므로**(박스 청구중량이 다름) 주문 시점에 브랜드별 캐리어를 `Order.shippingCarrierByBrand`(JSON `{[brandId]:carrier}`) 에 스냅샷하고, `Order.shippingCarrier`(단일)에는 **첫 브랜드 캐리어를 대표값**으로 둔다(브랜드 없는 legacy 제품만 담긴 주문은 맵이 비므로 캐리어 근사 무게 `CARRIER_FALLBACK_WEIGHT_G`=2kg 로 산출한 값). 송장 발급(`shipments.service` `carrierForBrand`)이 `shippingCarrierByBrand[brandId] ?? shippingCarrier` 로 정한다. klow_web 은 `resolveCarrierAndRate`(`useShippingCountriesQuery.ts`) 가 같은 규칙을 **근사**로 미러한다 — 브랜드별 박스 무게를 모르므로 캐리어 표시는 근사 무게(2kg) 기준이고, 제외구역 판정만 보수적으로(무게 분기국은 근사 캐리어가 EMS 여도 차단) 건다. 정본은 서버(`/v1/orders/quote`·주문 생성).
- **500g 요율 = 고객 결제 배송비 (판매가와 무관, 2026-07-28 분리 / 2026-07-30 기준무게 전환)**: 요율표 500g 티어를 그대로 고객에게 배송비로 청구하고, **판매가에는 물류비가 들어가지 않는다**(구 "절반은 판매가 마크업" 규칙 폐기) — `orders.service`:
  - **배송비** = `요율표500g/fxRate × **청구 대상** 브랜드수` — 한 브랜드 = 한 송장. 브랜드 단위로 반올림한 뒤 곱해 `Order.shippingFeeByBrand` 스냅샷 합과 정확히 일치시킨다. 산식 단일 출처는 `common/pricing.ts perBrandShippingFeeUsdCents`.
  - **무료배송**: **국가별** `ProductCountryPrice.freeShipping`(목적국 행이 true 일 때만 — 행이 없으면 유료. 판정은 `resolveFreeShipping(row, iso2)`). 그 브랜드 라인이 **전부** 무료일 때만 그 브랜드 몫이 빠진다(`orders/chargeable-brands.ts` `chargeableBrandIds(lines, iso2)`) — 한 라인이라도 유료면 박스는 어차피 나가므로 1회 청구. 같은 주문이라도 배송지 국가가 다르면 배송비가 달라진다.
  - **입고 실측과의 차액은 브랜드 후청구 대상**(무료배송이면 실측 전액) — [efs-billing](./efs-billing.md) 참고.
  - ⚠️ 요율/캐리어 미설정국·배송지원 제외국·EFS 제외구역 차단은 **요금 게이트가 아니라 배송 가능 여부 게이트**라, 무료배송이어도 그대로 막는다.
- **편집/시드**: 어드민 **배송비용** 탭(`/seeding-cost`)에서 국가×무게 요율(`PUT /admin/seeding-rates`)과 캐리어(`PUT /admin/shipping-countries/:iso2` → `productCarrier` — 목록 select 의 `—`/`EFS`/`EMS`/`EMS-PREMIUM`, 국가 상세에서 `seedingCarrierSplitWeightG`)를 관리한다. 초기 적재 시드: `prisma/data/seeding_rates.json` → `npm run seed:seeding-rates`. (구 **물류비용** 탭 `/product-logistics-cost` + `seed:product-logistics-cost` 는 2026-07-29 제거 — 캐리어 편집은 배송비용 탭으로 이관.)
- **국가 설정**: 어드민 **국가 설정** 탭(`/shipping-countries`)에서 `enabled`(배송지원 화이트리스트)·EFS 제외구역(`ShippingExclusion`)을 관리한다. `enabled` 는 **일반 주문 전용** 게이트(`loadEnabledCountry`) — 시딩 발급국은 요율표 기준(`supportedCountries`)이라 무관하다. 캐리어는 배송비용 탭에서 관리하므로 여기서 토글하지 않는다.
- **표시용 조회**: `GET /v1/shipping-countries` 목록이 요율표에서 파생한 `customerShippingKrw`(+`productCarrier`/`seedingCarrierSplitWeightG`)를 포함하므로 프론트가 고객 배송비를 그대로 미리보기하고, 미설정 국가는 선택지/미리보기에서 제외한다. 공개 `:iso2` 응답은 `exclusions` 를 포함(클라가 EFS 제외구역 차단을 미러). **구 `productLogisticsCostKrw` 는 응답에서 제거됐다.** 어드민 목록/상세(`/admin/shipping-countries`, `:iso2`)도 같은 `customerShippingKrw` 를 싣는다(파생 단일 출처 `withCustomerShipping`).
  - ⚠️ **배포 과도기**: 구 필드명 `logisticsCost2kgKrw` 를 **같은 값으로 병기**하고 있다(`shipping.service.ts withCustomerShipping`). 프론트 3개가 신규 필드로 넘어갔으므로 다음 릴리스에서 제거한다.
- **요율표 서비스 위치**: `LogisticsRateService`(`src/modules/shipping/logistics-rate.service.ts`)가 `SeedingRate` 표의 단일 소스다 — 2026-07-29 에 seeding 모듈에서 이동(`SeedingRateService` → 개명). `SeedingModule → ShippingModule` 의존이 이미 있어 반대 방향이면 순환이 되기 때문이고, `shipping-rate.service.ts` 를 옮긴 것과 같은 선례다. 모델명 `SeedingRate` 와 어드민 라우트 `/admin/seeding-rates` 는 그대로 뒀다(rename 이득 없음).
- **관련 파일**: `shipping.service.ts`(`resolveProductShipping`/`resolveCarrier`/`pickCarrierForWeight`/`loadEnabledCountry`/`update`/exclusions CRUD/`matchExclusion`), `logistics-rate.service.ts`(요율표 — 시딩·일반주문 공용, 어드민 컨트롤러는 seeding 모듈), `shipping-rate.service.ts` + `admin-shipping-rate.controller.ts` + `xlsx-grid.ts`(시딩 EMS/DHL 비교요율 — 2026-07 seeding 모듈에서 이동, 엔드포인트 문서는 [seeding](./seeding.md)), 3 개 컨트롤러(admin country · admin shipping-rate · public country).

## admin-shipping.controller.ts (`@Controller('admin/shipping-countries')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                                                       | 기능                                                |
|--------|------------------------------------------------------------|-----------------------------------------------------|
| GET    | `/admin/shipping-countries`                                | 국가 목록 (enabled 무관 전체 + exclusions 개수 + `customerShippingKrw`) |
| GET    | `/admin/shipping-countries/:iso2`                          | 특정 국가 상세 (+ exclusions 개수 + `customerShippingKrw`, 없으면 404) |
| PUT    | `/admin/shipping-countries/:iso2`                          | enabled · 제외구역 캐시 · **캐리어**(고정값·무게분기, 배송비용 탭) · efsBillingFeeKrw · currencyCode |
| GET    | `/admin/shipping-countries/:iso2/exclusions`               | 해당 국가 EFS 제외 지역 목록                        |
| POST   | `/admin/shipping-countries/:iso2/exclusions`               | 제외 지역 추가                                      |
| DELETE | `/admin/shipping-countries/:iso2/exclusions/:id`           | 제외 지역 삭제 (cuid)                               |

에러: 없는 국가는 404 `shipping country not found`(상세·PUT·제외구역 추가), 없는 제외구역 삭제는 404 `exclusion not found`. 제외구역 추가/삭제는 `ShippingCountry.efsPartialExclusions`(있냐 없냐 캐시)를 0→N / N→0 전이에서만 자동 동기화한다. `ShippingExclusionInput` 은 `kind` 별 필수 필드를 강제한다(zip→`zipFrom`, city→`city`, state→`state`) — ⚠️ `state` 종류는 저장은 되지만 `Order` 에 state 매칭 근거가 없어 **차단 판정에 쓰이지 않는다**(`matchExclusion` 이 zip/city 만 본다).

## public-shipping.controller.ts (`@Controller('v1/shipping-countries')`)

> public.

| Method | Path                            | 기능                                                          |
|--------|---------------------------------|---------------------------------------------------------------|
| GET    | `/v1/shipping-countries`        | 배송지원(enabled) 국가 목록 (+ 요율표 파생 `customerShippingKrw`/캐리어 설정) |
| GET    | `/v1/shipping-countries/:iso2`  | 특정 국가 배송 정보 (`exclusions` 포함)                       |

## 배송비 요율표 (컨트롤러는 seeding 모듈) — `admin-seeding-rate.controller.ts` (`@Controller('admin/seeding-rates')`)

> 전체 라우트 `AdminGuard`. 국가×무게 배송비 요율표(`SeedingRate`, 모든 추가비용/마진 포함, 무게 올림 조회) — **시딩·일반주문 공용**. 어드민 **배송비용** 탭(`/seeding-cost`). 캐리어는 `productCarrier` + 무게 분기.

| Method | Path                                    | 기능                                          |
|--------|-----------------------------------------|-----------------------------------------------|
| GET    | `/admin/seeding-rates`                  | 국가 목록 + 티어 커버리지 + 캐리어            |
| GET    | `/admin/seeding-rates/:iso2`            | 국가의 무게→비용 티어                         |
| PUT    | `/admin/seeding-rates`                  | `(iso2, weightG, costKrw)` 셀 upsert          |
| DELETE | `/admin/seeding-rates`                  | `(iso2, weightG)` 셀 삭제                     |
| POST   | `/admin/seeding-rates/import/preview`   | 시딩 가격표 엑셀 파싱 → 국가별 상태 diff      |
| POST   | `/admin/seeding-rates/import/apply`     | 같은 파일 재파싱 + 선택 국가 티어 통째 교체   |
| POST   | `/admin/seeding-rates/:iso2/import/ai-preview` | 임의 포맷 요율표 → AI 추출 + diff (적용 안 함) |
| PUT    | `/admin/seeding-rates/:iso2/tiers`      | 한 국가 티어 일괄 저장(`replace`/`merge`)     |

초기 적재 시드: `prisma/data/seeding_rates.json`(엑셀 `KLOW_시딩_가격표` 고객_가격표) → `npm run seed:seeding-rates`.

국가 상세의 AI 추출(`rate-sheet-ai.service.ts`)은 **AI 에게 레이아웃만 묻고 금액은 서버가 원본 셀에서 직접 읽는** 2단계 구조다 — 자세히는 [seeding](./seeding.md#admin-seeding-ratecontrollerts-controlleradminseeding-rates).
서비스는 `shipping/logistics-rate.service.ts` `LogisticsRateService`(컨트롤러만 seeding 모듈에 남음).
