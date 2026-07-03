# shipping — 배송

- **모듈 경로**: `src/modules/shipping/`
- **데이터 모델**: `ShippingCountry`(국가 설정 + 제품 물류비/캐리어), `ShippingExclusion`(EFS 제외구역), `ShippingCarrier`. (구 `ShippingRate` 무게×캐리어 티어·미러 컬럼·추가요금은 **dormant** — [`docs/cleanup-dormant-shipping-rate.md`](../../archive/cleanup-dormant-shipping-rate.md).)
- **제품 물류비/캐리어 (국가별 고정값, 비교 없음)**: 결제 시 `shipping.service.resolveFixedRate(iso2, addr)` 가 국가별 `(캐리어, 물류비)` 를 1회 반환한다. **제품 무게는 가격에 영향 없음.** 가격은 `ShippingCountry.productLogisticsCostKrw`(운영팀이 캐리어 비교·유류할증료·특별운송수수료를 미리 반영한 2kg 통합 정본값, 엑셀 `KLOW_가격표`), 캐리어는 `ShippingCountry.productCarrier`(직통 10국=EFS / 그 외=EMS) — **런타임 비교·할증 가산 없음**. `productLogisticsCostKrw`/`productCarrier` 가 null 이면(표 외 DHL-전용국 등) **구매 차단**(throw). EFS 캐리어 국가라도 주소가 EFS 제외구역(`matchExclusion`)이면 **폴백 없이 차단**.
- **고정 캐리어 산출 (송장 공용)**: `resolveCarrier(iso2, addr)` 가 `productCarrier`(+ EFS 제외구역 차단)만 반환한다 — 시딩 claim/checkout 이 송장 캐리어로 쓴다(비용은 SeedingRate, 아래 seeding 모듈). 제품/시딩 공통 EFS 제외구역 차단은 private `assertNotEfsExcluded` 단일 출처.
- **브랜드별 캐리어 스냅샷**: 한 브랜드 = 한 송장 = 한 박스. 캐리어는 국가 단위라 전 브랜드 동일하지만, 송장 발급 호환을 위해 주문 시점에 브랜드별 캐리어를 `Order.shippingCarrierByBrand`(JSON `{[brandId]:carrier}`) 에 스냅샷하고 `Order.shippingCarrier`(단일)는 같은 값을 **대표값**으로 둔다. 송장 발급(`shipments.service` `carrierForBrand`)이 `shippingCarrierByBrand[brandId] ?? shippingCarrier` 로 정한다. klow_web 은 `resolveCarrierAndRate`(`useShippingCountriesQuery.ts`) 가 동일 규칙(productLogisticsCostKrw/productCarrier + EFS 제외구역 차단)을 미러.
- **요율 절반 분할 (판매가/배송비)**: 국가별 2kg 통합 물류비를 **절반씩** 판매가 마크업과 배송비로 쓴다 — `orders.service`:
  - **판매가 마크업** = `productLogisticsCostKrw/2/fxRate` — 전 아이템 공통(제품 무게 무관).
  - **배송비** = `productLogisticsCostKrw/2/fxRate × 브랜드수` — 한 브랜드 = 한 송장.
- **편집/시드**: 어드민 **물류비용** 탭(`/product-logistics-cost`)에서 국가별 물류비/캐리어 수기 편집(`PUT /admin/shipping-countries/:iso2` → `productLogisticsCostKrw`/`productCarrier`). 초기 적재 시드: `prisma/data/product_logistics_cost.json`(엑셀 2kg 행, 직통 10국=EFS·나머지=EMS) → `npm run seed:product-logistics-cost`.
- **국가 설정**: 어드민 **국가 설정** 탭(`/shipping-countries`)에서 `enabled`(배송지원 화이트리스트)·EFS 제외구역(`ShippingExclusion`)을 관리한다. `enabled` 는 제품/시딩 공통 게이트(`loadEnabledCountry`). 캐리어는 국가 단위 고정값(`productCarrier`, 물류비용 탭)이라 여기서 토글하지 않는다.
- **표시용 조회**: `GET /v1/shipping-countries` 목록이 `productLogisticsCostKrw`/`productCarrier` 를 포함하므로 프론트가 국가별 고정 판매가를 직접 계산하고, 미설정 국가는 선택지/미리보기에서 제외한다. 공개 `:iso2` 응답은 `exclusions` 를 포함(클라가 EFS 제외구역 차단을 미러).
- **시딩 배송비는 seeding 모듈로 이관**: 크리에이터 시딩 배송비는 `SeedingRate`(국가×무게, 모든 비용 포함) + `productCarrier` 고정으로 산출한다 — `src/modules/seeding/seeding-rate.service.ts`. (구 `loadCheapestRatePlanner`/`resolveRatesForWeight`/`pickCheapestCarrier` 무게별 최저가 경로는 제거됨.)
- **관련 파일**: `shipping.service.ts`(`resolveFixedRate`/`resolveCarrier`/`loadEnabledCountry`/`update`/exclusions CRUD/`matchExclusion`), 2 개 컨트롤러(admin country · public country).

## admin-shipping.controller.ts (`@Controller('admin/shipping-countries')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                                                       | 기능                                                |
|--------|------------------------------------------------------------|-----------------------------------------------------|
| GET    | `/admin/shipping-countries`                                | 국가 목록 (+ exclusions 개수)                       |
| GET    | `/admin/shipping-countries/:iso2`                          | 특정 국가 상세                                      |
| PUT    | `/admin/shipping-countries/:iso2`                          | enabled · 제외구역 캐시 · **제품 물류비/캐리어**(물류비용 탭) |
| GET    | `/admin/shipping-countries/:iso2/exclusions`               | 해당 국가 EFS 제외 지역 목록                        |
| POST   | `/admin/shipping-countries/:iso2/exclusions`               | 제외 지역 추가                                      |
| DELETE | `/admin/shipping-countries/:iso2/exclusions/:id`           | 제외 지역 삭제 (cuid)                               |

## public-shipping.controller.ts (`@Controller('v1/shipping-countries')`)

> public.

| Method | Path                            | 기능                                                          |
|--------|---------------------------------|---------------------------------------------------------------|
| GET    | `/v1/shipping-countries`        | 배송지원(enabled) 국가 목록 (+ productLogisticsCostKrw/productCarrier) |
| GET    | `/v1/shipping-countries/:iso2`  | 특정 국가 배송 정보 (`exclusions` 포함)                       |

## 시딩 배송비 (seeding 모듈) — `admin-seeding-rate.controller.ts` (`@Controller('admin/seeding-rates')`)

> 전체 라우트 `AdminGuard`. 국가×무게 시딩 배송비 표(`SeedingRate`, 모든 추가비용/마진 포함, 무게 올림 조회). 어드민 **시딩비용** 탭(`/seeding-cost`). 캐리어는 제품 `productCarrier` 재사용.

| Method | Path                                    | 기능                                          |
|--------|-----------------------------------------|-----------------------------------------------|
| GET    | `/admin/seeding-rates`                  | 국가 목록 + 티어 커버리지 + 캐리어            |
| GET    | `/admin/seeding-rates/:iso2`            | 국가의 무게→비용 티어                         |
| PUT    | `/admin/seeding-rates`                  | `(iso2, weightG, costKrw)` 셀 upsert          |
| DELETE | `/admin/seeding-rates`                  | `(iso2, weightG)` 셀 삭제                     |
| POST   | `/admin/seeding-rates/import/preview`   | 시딩 가격표 엑셀 파싱 → 국가별 상태 diff      |
| POST   | `/admin/seeding-rates/import/apply`     | 같은 파일 재파싱 + 선택 국가 티어 통째 교체   |

초기 적재 시드: `prisma/data/seeding_rates.json`(엑셀 `KLOW_시딩_가격표` 고객_가격표) → `npm run seed:seeding-rates`.
