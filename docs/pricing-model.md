# KLOW 가격 모델 (단일 참조)

KLOW의 가격·통화·할인 모델을 한 곳에 정리한 **현재 상태 기준** 문서다. 결제 흐름은
[`payment-integration.md`](./payment-integration.md) 참고.

> **2026-06 변경**: 브랜드 입력이 "정산가 1개"에서 **"원가 + 마진"** 으로 바뀌고, **국가별 마진·국가별 할인**이
> 도입됐다. 판매가는 **서버가 배송 국가별로 직접 계산**해 응답에 싣는다(구 "$15 기준 + 클라 국가보정" 폐기).
> PG 수수료는 `÷(1−0.05)`(=÷0.95)로 회수해 브랜드가 입력한 "남길 금액(마진)"을 수수료 후에도 정확히 net으로 남긴다.

## 통화 규칙 (개념별 고정)

- **고객에게 받는 돈 = USD** — 노출가·결제 단가·주문 총액·PG 청구 전부 USD.
- **브랜드에게 주는 돈 = KRW** — 정산가·정산 지급 전부 KRW.
- 두 통화는 주문 시점 `Order.fxRateSnapshot` 으로 연결되어 추적된다.
- **정산가(salePrice) = 원가(costKrw) + 마진(defaultMarginKrw)**. 국가별 마진 오버라이드가 있으면 그 국가의
  정산가 = `costKrw + ProductCountryPrice.marginKrw`. 브랜드/어드민이 원가·마진을 입력하고 서버가 정산가를 파생한다.
  (legacy 행은 `costKrw == null` → 기존 `salePrice` 를 그대로 정산가로 사용.)
- **판매가(USD 센트) = `ceil((정산가 + 국가별 2kg 물류비/2) / (1 − 0.05) / fxRate × 100)`**. ceil-to-cent(본전 미만 방지).
  물류비의 절반은 판매가 마크업, 절반은 배송비(브랜드당 1회). **제품 무게는 가격에 영향이 없다.**
- 가격 공식과 환율(`ShopSettings.usdKrwRate`)은 **서버 단일 소스**. 서버가 목적국별 최종 판매가/할인을 계산해
  응답(`customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`)에 싣고, 프론트는 **그 값을 그대로 표시**한다.
  편집기(klow_brand·klow_admin)는 입력 즉시 미리보기를 위해 동일 공식(`cost-pricing.ts`, ÷0.95)을 미러한다.
- **국가별 물류비**는 `ShippingCountry.productLogisticsCostKrw`에서 온다 — 운영팀이 캐리어 비교·유류할증료·특별운송수수료를
  미리 반영한 정본값(엑셀 `KLOW_가격표` 2kg 행)이라 런타임 비교·할증 가산이 없다. 어드민 **물류비용** 탭에서 국가별 수기
  편집(초기 적재 시드 `npm run seed:product-logistics-cost`).
- **캐리어는 국가당 하나로 고정**(`ShippingCountry.productCarrier`): 직통 10국=EFS, 나머지 88국=EMS. 비교하지 않는다.
- **물류비/캐리어 미설정 국가는 제품 구매 차단**(`productLogisticsCostKrw == null` → 주문 throw). EFS 캐리어 국가라도
  주소가 EFS 제외구역이면 폴백 없이 배송 차단.
- 표시 기본 국가는 `US`(klow_web `DEFAULT_COUNTRY`). 공개 read 엔드포인트는 `?country=` 쿼리로 목적국을 받는다(미지정 시 US 베스트케이스).
- **시딩 배송비**도 국가×무게 표 `SeedingRate`에서 무게 올림 조회(별도 모델, 본 문서 범위 밖 — [`server/modules/shipping.md`](./server/modules/shipping.md)).

## 한눈 표 — 무엇이 어디에 저장/계산되나

### 📦 상품 단위 (개당)

| 개념 | 누가 정함 | 통화 | 저장/계산 | 비고 |
|---|---|---|---|---|
| **원가** | 브랜드/어드민 입력 | KRW | `Product.costKrw` **저장** (nullable) | 신 모델의 입력값. null = legacy |
| **기본 마진** (전국가 공통) | 브랜드/어드민 입력 | KRW | 저장 안 함 → `salePrice − costKrw` 로 파생 | "남길 금액" |
| **정산가** (개당 받는 돈) | 서버 파생 | KRW | `Product.salePrice` **저장** | `= costKrw + 기본마진` (전국가 기본) |
| **국가별 마진 오버라이드** | 브랜드/어드민 입력 | KRW | `ProductCountryPrice.marginKrw` **저장** | 그 국가 정산가 = `costKrw + marginKrw`. 없으면 기본 상속 |
| **국가별 할인율** | 브랜드/어드민 입력 | % | `ProductCountryPrice.discountPct` **저장** | 기간 없음. >0 이면 항상 적용 |
| 글로벌 할인율(legacy) | 어드민 입력 | % | `Product.discount` **저장** | 마케팅 취소선 — 국가별 할인 없을 때만 폴백 |
| **제품 무게** | (입력 안 함) | g | `Product.weightG` **저장** | 가격과 무관(legacy 호환, 1kg 기본) |
| **판매가** (취소선 원가) | 서버 계산 | USD | 응답 `listPriceUsd`(센트) | `ceil((정산가+물류비/2)/0.95/fx×100)`. 목적국별 |
| **실제 결제가** | 서버 계산 | USD | 응답 `customerPriceUsd`(센트) | 국가별 할인 적용가 = `round(listPriceUsd×(1−pct/100))` |
| 화면 할인율 뱃지 | 서버 전달 | % | 응답 `customerDiscountPercent` | 적용된 할인율(국가별 우선, 없으면 글로벌) |

> 마진 오버라이드도 할인도 없는 국가는 `ProductCountryPrice` 행을 만들지 않고 전국가 기본(정산가=salePrice, 할인=글로벌 discount)을 상속한다.

### 🧾 주문 단위 (결제 시 고정 스냅샷)

| 개념 | 통화 | 저장 위치 | 비고 |
|---|---|---|---|
| 주문 시점 고객 단가 | USD | `OrderItem.unitPriceUsd`(센트) | 목적국 기준 판매가 + 국가별 할인 (표시가와 동일 `priceLine`) |
| 주문 시점 정산 단가 | KRW | `OrderItem.settlementPriceKrw` | `= 목적국 정산가` (원가 + 국가별 마진) |
| 배송비 | USD | `Order.shippingFeeUsd`(센트) | `물류비/2/fx × 브랜드수` (한 브랜드 = 한 송장) |
| **고객 결제 총액** | USD | `Order.totalUsd`(센트) | `Σ unitPriceUsd×수량 + shippingFeeUsd` |
| 환율 고정 스냅샷 | — | `Order.fxRateSnapshot` | 결제·환불·정산 환산 기준 |

> 주문은 `resolveFixedRate`(EFS 제외구역/EMS 반영)의 요율을 쓰고, 표시는 베스트케이스 `productLogisticsCostKrw`를 쓴다.
> 제외구역이 없으면 둘이 같아 표시가 == 청구가. 체크아웃은 `POST /v1/orders/quote`로 주문 생성과 동일 공식의 견적을 받아 표시한다(cent-exact).

## 할인의 의미 (중요 — 변경됨)

- **국가별 할인(`ProductCountryPrice.discountPct`)은 실제 판매가를 낮춘다.** 판매가(`listPriceUsd`, 취소선)에서
  `× (1−pct/100)` 한 값이 고객이 실제 내는 `customerPriceUsd`이고, 주문 청구가도 같다. 할인할수록 브랜드가 남기는
  마진이 줄어든다(본전 미만이면 손해 — 편집기가 `maxDiscountPct`/`breakEvenDiscountPct`로 경고·상한).
- **글로벌 `Product.discount`(legacy)** 는 마케팅 앵커다 — 국가별 할인이 없을 때만 폴백으로, 취소선 원가를
  `customerPriceUsd ÷ (1−discount/100)` 로 부풀려 "N% off"만 연출하고 실제 결제가는 그대로다.
- 즉 **국가별 할인 우선, 없으면 글로벌 할인**. 둘은 스택하지 않는다.

## 마진

```
주문당 마진(USD) = Order.totalUsd − (Σ OrderItem.settlementPriceKrw ÷ Order.fxRateSnapshot)
```
환위험은 주문 시점 `fxRateSnapshot` 으로 고정·추적된다.

## 핵심 함수 (서버, 단일 소스)

- `customerPriceUsdCents(settlementKrw, logisticsKrw, fxRate)` / `applyDiscountUsdCents(cents, pct)` /
  `shippingFeeUsdCents(rateKrw, fxRate, brandCount)` — `klow_server/src/common/pricing.ts` (÷0.95, ceil-to-cent)
- `priceLine(row, cp, rateKrw, fxRate)` — `product-selects.ts`. **정산가→판매가→국가별 할인** 1라인 계산의 단일 출처.
  표시(`attachCustomerPricing`)·주문 생성·견적(`quote`)이 모두 이 함수를 거쳐 "표시가 == 청구가"를 보장한다.
- `attachCustomerPricing(row, fxRate, ctx)` / `resolvePricingCtx(prisma, country)` /
  `writeProductCountryPrices(tx, productId, rows)` / `deriveCreated|UpdatedSalePriceKrw(...)` — `product-selects.ts`
- 물류비·캐리어: `resolveFixedRate(iso2, address?)` — `shipping.service.ts`. 환율: `resolveFxRate(prisma)` — `common/fx.ts`.
- 엔드포인트: 공개 read 는 `?country=` 지원(`/v1/products`, `/v1/products/:id`, `/v1/shop/today`, `/v1/discover`,
  `/v1/videos/:id`, `/v1/creators/:id/products`). 견적 `POST /v1/orders/quote`. fx `GET /v1/shop/fx-rate`,
  국가표 `GET /v1/shipping-countries`(productLogisticsCostKrw/productCarrier).

## 프론트

- **klow_web**: 서버가 준 `customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`를 **그대로 렌더**(구 `useCountryPricing`·
  `markupDeviationCents` 클라 보정 폐기). 뷰어 국가는 `useAppStore.country`(기본 US)를 쿼리키·요청에 전파. 체크아웃은
  `/v1/orders/quote`로 정확한 결제 총액을 받는다.
- **klow_brand · klow_admin**: 제품 편집에서 **원가 + 마진** 입력 + **국가별 마진/할인** 편집. `src/lib/cost-pricing.ts`(÷0.95,
  서버 공식 미러, 무게 입력 없음)와 국가별 2kg 물류비(`shipping-countries`)로 입력 즉시 국가별 판매가/마진/손익을 미리보기.

## 스키마

```prisma
model Product {
  salePrice  Int      // 정산가 = costKrw + 기본 마진
  costKrw    Int?     // 원가 (null = legacy)
  discount   Int      // 글로벌 마케팅 할인%(legacy 폴백)
  countryPrices ProductCountryPrice[]
}
model ProductCountryPrice {
  productId   String
  iso2        String   @db.VarChar(2)
  marginKrw   Int?     // 국가별 "남길 금액" 오버라이드(null = 기본 상속)
  discountPct Int      @default(0)  // 국가별 할인%(기간 없음, >0 항상 적용)
  @@unique([productId, iso2])
}
```
마이그레이션: `20260627124039_add_product_cost_and_country_pricing`.

## 이력 (보관 문서)

- 고객측 금액 USD 정본화(KRW 장부 컬럼 드롭): [`archive/pricing-usd-migration.md`](./archive/pricing-usd-migration.md)
- dormant 배송 요율 컬럼 드롭(2026-06-23): [`archive/cleanup-dormant-shipping-rate.md`](./archive/cleanup-dormant-shipping-rate.md)
