# KLOW 가격 모델 (단일 참조)

KLOW의 가격·통화·할인 모델을 한 곳에 정리한 **현재 상태 기준** 문서다. 결제 흐름은
[`payment-integration.md`](./payment-integration.md) 참고.

> **2026-07-28 전환 (판매가에서 물류비 분리 + 무료배송 판매 모드)**: 판매가에 섞여 있던
> **국가별 2kg 물류비의 절반(마크업)을 제거**했다 — `판매가 = 정산가 ÷ 0.95 ÷ 환율`, 정산 역산도
> `정산가 = 청구USD × fx × 0.95`(물류비 차감 없음). 그 결과 **미핀 국가의 default 판매가는 목적국과
> 무관한 단일 값**이 되고, 국가차는 핀(`priceLocal`)·할인에서만 생긴다.
> 고객이 결제하는 **배송비(물류비/2 × 청구 대상 브랜드수)는 그대로**이고, 그 선결제분은 브랜드 실측
> 물류비의 **선납금**이 된다 — 입고 실측과의 차액만 브랜드에 후청구(실측 ≤ 선결제면 청구 없음).
> 제품별 **무료배송**(`Product.freeShipping` / 브랜드관 전체 `Brand.freeShippingAll`)을 켜면 고객은
> 배송비를 내지 않고 실측 물류비 **전액**이 브랜드 몫이 된다. 배송비는 브랜드 단위(한 브랜드=한 송장)로
> 청구되므로 **그 브랜드 라인이 전부 무료일 때만** 면제된다.
>
> **2026-07-29 전환 (배송비 요율 단일화)**: 배송비 정본이 국가당 단일 2kg 값
> (`ShippingCountry.productLogisticsCostKrw`, 어드민 물류비용 탭)에서 **국가×무게 요율표
> `SeedingRate`(어드민 배송비용 탭) 하나**로 통합됐다 — 시딩과 일반 주문이 같은 표를 쓴다.
> 고객 결제 배송비는 그 표의 **2kg 티어 절반**(공개 응답 `logisticsCost2kgKrw`)으로 계산식은 그대로이고,
> **값만 요율표 기준으로 바뀐다**(국가별로 오르내림 — 배포 전 델타 확인 필요).
> 캐리어도 시딩과 동일한 **무게 분기**(`seedingCarrierSplitWeightG`)를 타는데, 일반 주문은
> **브랜드별 박스 청구중량**으로 갈리므로 한 주문 안에서 브랜드마다 캐리어가 다를 수 있다.
> 어드민 **물류비용** 탭은 제거됐고 캐리어 편집은 **배송비용** 탭으로 이관됐다.
> 구 컬럼 `productLogisticsCostKrw` 는 과거 백필 스크립트 참조용으로 dormant 잔존.
>
> **2026-07 전환 (판매가 고정 → 정산 유동)**: 가격 정본이 "원가+마진(KRW) → 판매가 파생"에서
> **"국가별 현지통화 판매가 고정 → 브랜드 정산가(KRW)를 주문 시점 환율로 역산"** 으로 바뀌었다.
> 환율 리스크가 **손님(가격 변동)에서 브랜드(정산액 변동)로** 이동한다 — 손님은 안정적인 현지통화 가격을 보고,
> 브랜드는 자기가 정한 판매가가 고정되는 대신 환율에 따라 정산액이 오르내린다. 정산가가 원가 밑으로 내려가도
> **구매는 막지 않고 경고만** 한다(브랜드가 재가격). 이전 모델(마진 고정)은 [`archive/`](./archive/) 참고.

## 통화 규칙 (개념별 고정)

- **손님이 보는 가격 = 국가별 현지통화(고정)** — 핀한 국가는 그 나라 통화로 고정, 미핀 국가는 기본 USD 고정.
- **손님에게 받는 돈(청구) = USD** — Eximbay 는 USD 로만 청구. 현지통화가는 청구 USD 를 현지통화로 환산해 "보여주는" 값.
- **브랜드에게 주는 돈 = KRW (유동)** — 정산가는 고정 판매가에서 주문 시점 환율로 역산된다.
- **가격 정본**:
  - **미핀 default 판매가 — 두 모델**:
    - **브랜드 신모델** (`Product.basePriceFxRate` 有):
      `판매가USD = ceil(salePrice/0.95/basePriceFxRate ×100)` — **물류비 없음 → 전 국가 동일**.
      `salePrice`(정산가 = 역산 저장 기준값. 브랜드가 UI에서 친 "원가+마진" 편의 입력의 결과)와 `basePriceFxRate`(저장 시점 fx 프리즈)로
      **판매가를 한 번 파생해 고정**하고, 이후 **마진/정산가는 그 고정 판매가에서 역산**한다(판매가는 환율에 안 흔들리고 정산가만 유동). **default 정산가 ≈ 원가+마진.**
    - **어드민/legacy** (`basePriceFxRate` 無): `Product.basePriceUsd`(USD 센트, 고정) 단일 판매가를 미핀 전 국가에 적용.
    - `basePriceUsd` 는 신모델에선 **대표/정렬값**으로 남는다(US 기준 파생). 완성도 게이트는 `hasSellablePrice`.
  - `ProductCountryPrice.priceLocal` (현지통화 major, 고정) = 국가별 핀. 있으면 그 국가는 현지통화 고정
    (통화는 `ShippingCountry.currencyCode`, USD 폴백국은 USD major). 없으면 위 default 상속.
- **손님 결제가(USD 센트) 파생**:
  - 핀 국가: `customerPriceUsd = round(priceLocal / currencyUsdRate × 100)` (currencyUsdRate = 1 USD 당 현지통화, `CurrencyFxRate.usdRate`).
  - 미핀 국가: 위 default 판매가(신모델=국가별 파생, legacy=basePriceUsd).
  - 국가별/캠페인 할인은 이 위에 `× (1 − pct/100)`.
  - **⚠️ 과청구 가드(주문·견적)**: 핀(`priceLocal`)이 있는데 목적국 통화의 유효 환율(`CurrencyFxRate.usdRate>0`)이
    없으면 `currencyUsdRate`가 미해결(strict null)이라, 1로 폴백하면 현지가를 USD로 오인해 과청구(¥1500→$1500)한다.
    `OrdersService.billingRate`가 이 경우 주문/견적을 **차단**한다(핀 없는 상품은 영향 없음). 표시 경로는 1로 폴백 + 경고 로깅.
- **브랜드 정산가(KRW) 역산** = `floor(customerPriceUsd/100 × usdKrwRate × (1 − 0.05))`.
  PG 5% 만 차감한 순정산액 — **물류비는 차감하지 않는다**(배송비는 고객이 별도 결제하고 실측 차액만 사후 후청구).
  `customerPriceUsdCents` 의 역함수. **주문 시점 환율로 고정 스냅샷.**
- **원가 밑 경고**: 역산 정산가 < `Product.costKrw` 이면 `belowCost` — 브랜드/어드민 UI 가 경고, **구매·저장은 막지 않는다.**
- 환율 **단일 테이블 `CurrencyFxRate`** 로 통합: `['KRW']` 행 = **정산 정본**(USD↔KRW, 정산 역산·결제·basePriceFxRate 스냅샷.
  수동 고정 manualOverride, cron 미갱신), 그 외 코드 = USD→현지통화(핀가 청구 환산 + 표시, 매일 cron + 수동 보정).
  둘 다 어드민 **통화 환율(/currency-rates)** 페이지에서 관리. 정산 fx 는 `resolveFxRate`(`common/fx.ts`)가 KRW 행을 읽는다.
  실시간 아님 — 어드민 갱신 시 계단식. (구 `ShopSettings.usdKrwRate` 는 dormant, 후속 릴리스에서 드롭.)
- **국가별 물류비**는 `SeedingRate` 국가×무게 요율표의 **기준 무게(2kg) 티어**(어드민 **배송비용** 탭,
  엑셀 `KLOW_시딩_가격표` 고객_가격표). 공개 응답엔 `logisticsCost2kgKrw` 로 실린다.
  **판매가/정산가와 무관** — 절반이 결제 배송비(청구 대상 브랜드당 1회)로 쓰일 뿐이고, 나머지 절반과
  입고 실측 차액은 브랜드 후청구 대상이다. 캐리어는 국가 고정(`productCarrier`)이되 무게 분기
  (`seedingCarrierSplitWeightG`)가 있으면 **브랜드별 박스 무게**로 갈린다(한 주문 안에서 브랜드마다 다를 수 있음).
  2kg 티어·캐리어 미설정국과 **배송지원(`enabled`) 제외국**은 구매 차단 — **무료배송이어도 마찬가지**
  (요금 게이트가 아니라 배송 가능 여부 게이트). (구 `ShippingCountry.productLogisticsCostKrw` 는 2026-07-29 요율표 통합으로 dormant.)
- 표시 기본 국가는 `US`. 공개 read 는 `?country=` 로 목적국을 받는다(미지정 US).

## 한눈 표 — 무엇이 어디에 저장/계산되나

### 📦 상품 단위 (개당)

| 개념 | 누가 정함 | 통화 | 저장/계산 | 비고 |
|---|---|---|---|---|
| **원가** | 브랜드/어드민 입력 | KRW | `Product.costKrw` **저장** (nullable) | 원가 밑 경고 기준 |
| **기본 판매가** (전국가) | 어드민 입력 · 브랜드 대표값 | USD 센트 | `Product.basePriceUsd` **저장** | legacy/어드민 단일 판매가 + 신모델 대표/정렬·게이트값 |
| **정산가 저장값** | 브랜드 "원가+마진" 편의 입력의 결과 | KRW | `Product.salePrice` **저장** | 신모델 default **판매가**를 국가별로 파생·고정하는 기준값(≈ 원가+마진). 마진 자체는 역산 |
| **저장 fx 스냅샷** | 서버(저장 시점) | KRW/USD | `Product.basePriceFxRate` **저장** | 有=국가별 파생 신모델. 판매가를 환율에 고정(정산가만 유동) |
| **국가별 핀** | 브랜드/어드민 입력 | 현지통화 major | `ProductCountryPrice.priceLocal` **저장** | 있으면 그 국가 현지통화 고정. 없으면 기본 USD 상속 |
| **국가별 할인율** | 브랜드/어드민 입력 | % | `ProductCountryPrice.discountPct` **저장** | 기간 없음. >0 항상 적용 |
| 글로벌 할인율(legacy) | 어드민 입력 | % | `Product.discount` **저장** | 마케팅 취소선 — 국가별 할인 없을 때만 폴백 |
| **손님 판매가** (취소선) | 서버 계산 | USD | 응답 `listPriceUsd`(센트) | 핀 국가 `priceLocal/rate`, 미핀 default(신모델=정산가+frozenFx 파생 / legacy `basePriceUsd`). **미핀은 전 국가 동일** |
| **실제 결제가** | 서버 계산 | USD | 응답 `customerPriceUsd`(센트) | 할인 적용가 |
| 정산가 (개당 브랜드 몫) | 서버 역산 | KRW | 응답엔 미노출(편집기만) | `= 청구USD × fx × 0.95`(물류비 차감 없음). **유동**(표시 시점 환율) |
| **무료배송** | 브랜드 입력 | — | `Product.freeShipping` **저장** + `Brand.freeShippingAll` | 실효 = 둘의 OR(`resolveFreeShipping`). 공개 응답 `freeShipping` |
| 배송 박스 규격 | 브랜드 입력 | cm/g | `Product.{weightG,boxLengthCm,boxWidthCm,boxHeightCm}` **저장** | 예상 청구 배송비(실측 후청구 미리보기)용. **가격 무관** |

> 핀도 할인도 없는 국가는 `ProductCountryPrice` 행을 만들지 않고 default(신모델=정산가+frozenFx 국가별 파생 / legacy=basePriceUsd, 할인=글로벌 discount)를 상속한다.
> 완성도 게이트(`PUBLIC_PRODUCT_WHERE`)는 `image != '' && hasSellablePrice` — 판매가(신모델=정산가+frozenFx,
> legacy=basePriceUsd) 가 정해져야 노출/판매된다. `hasSellablePrice`/`SELLABLE_PRICE_WHERE`(product-selects.ts)가 정본.

### 🧾 주문 단위 (결제 시 고정 스냅샷)

| 개념 | 통화 | 저장 위치 | 비고 |
|---|---|---|---|
| 주문 시점 고객 단가 | USD | `OrderItem.unitPriceUsd`(센트) | 고정 판매가 + 할인 (표시가와 동일 `priceLine`) |
| 주문 시점 정산 단가 | KRW | `OrderItem.settlementPriceKrw` | **청구USD 에서 주문 시점 환율로 역산** — 이 시점에 확정, 이후 환율 변동 무관 |
| 주문 시점 원가 | KRW | `OrderItem.costKrw` | 원가 밑 정산 경고/리포트 기준(제품 원가가 나중에 바뀌어도 불변) |
| 배송비 | USD | `Order.shippingFeeUsd`(센트) | `요율표 2kg 티어/2/fx × **청구 대상** 브랜드수` (한 브랜드 = 한 송장) |
| 브랜드별 배송비 스냅샷 | USD | `Order.shippingFeeByBrand`(JSON `{brandId: 센트}`) | 무료배송 브랜드는 0. Σ == `shippingFeeUsd`. 송장 발급이 EFS 27번을 이걸로 안분(legacy null → 균등분배) |
| **고객 결제 총액** | USD | `Order.totalUsd`(센트) | `Σ unitPriceUsd×수량 + shippingFeeUsd` |
| 환율 고정 스냅샷 | — | `Order.fxRateSnapshot` | 결제·환불·정산 역산 기준(usdKrwRate) |

> 주문 하나 안에서는 정산가도 이미 고정(주문 시점 역산 스냅샷). "유동"은 **환율 갱신 사이의 신규 주문들** 간 차이일 뿐이다.
> 정산 모듈은 `settlementPriceKrw` 스냅샷을 합산만 한다(재계산 없음). 원가 밑 라인은 어드민 정산 후보에 플래그(`belowCostItemCount`).

## 할인의 의미

- **국가별 할인(`discountPct`)은 고정 판매가를 낮춘다.** 취소선 = 고정가(핀/기본), 결제가 = `× (1−pct/100)`.
  할인가에서 정산가를 역산하므로 **할인할수록 브랜드 정산도 줄어든다**(브랜드가 할인 부담). 마이너스면 편집기가 경고.
- **글로벌 `Product.discount`(legacy)** 는 마케팅 앵커 — 국가별 할인 없을 때만 폴백으로 취소선을 부풀린다(결제가 불변).
- 국가별 할인 우선, 없으면 글로벌. 스택 안 함. 캠페인 할인은 `max(국가별, 캠페인)`.

## 마진 / 환율 리스크

```
주문당 브랜드 정산(KRW) = Σ OrderItem.settlementPriceKrw × 수량   (주문 시점 환율로 고정)
개당 마진(KRW) = settlementPriceKrw − OrderItem.costKrw            (음수면 원가 밑 = 손해)
```
판매가는 고정이고 정산가는 주문 시점 `fxRateSnapshot`(usdKrwRate)과 `CurrencyFxRate`(핀 국가)로 역산된다.
원화가 강세면 정산액이 줄어(원가 밑 가능), 약세면 늘어난다 — **브랜드가 환율 리스크를 진다.**

## 핵심 함수 (서버, 단일 소스)

- `customerPriceUsdCents(settlementKrw, fxRate)` / `customerUsdCentsFromLocal(priceLocal, currencyUsdRate)` /
  `settlementKrwFromCustomerUsd(customerUsdCents, fxRate)` / `applyDiscountUsdCents(cents, pct)` /
  `shippingFeeUsdCents(rateKrw, fxRate, brandCount)`(브랜드 단위 반올림 × n) — `klow_server/src/common/pricing.ts`
- `priceLine(row, cp, fxRate, currencyUsdRate, campaignPct)` — `product-selects.ts`. **고정 판매가 → USD 청구 → 정산가 역산 + belowCost**
  의 1라인 단일 출처. 표시(`attachCustomerPricing`)·주문 생성·견적(`quote`)이 모두 이 함수를 거쳐 "표시가 == 청구가"를 보장한다.
- `attachCustomerPricing(row, fxRate, ctx)` / `resolvePricingCtx(prisma, country)`(→ **currencyUsdRate** + campaign. 물류비는 없다) /
  `writeProductCountryPrices(tx, productId, rows)` — `product-selects.ts`. 공개 응답은 `costKrw`/`countryPrices`/`basePriceUsd`/`basePriceFxRate`/`salePrice`/`brandRef` strip(`StrippedPricingKeys`).
- 물류비·캐리어: `resolveProductShipping(iso2, address, brandWeights)` — `shipping.service.ts`(배송비 산출 전용, 가격 무관).
  요율표 조회는 `LogisticsRateService`(`shipping/logistics-rate.service.ts`), 브랜드별 박스 무게는 `orders/brand-weights.ts` `brandChargeableWeights`.
  환율: `resolveFxRate(prisma)` — `common/fx.ts`.
- 무료배송: `resolveFreeShipping(row)` — `product-selects.ts`(실효 = `brandRef.freeShippingAll || freeShipping`).
  `chargeableBrandIds(lines)` — `orders/chargeable-brands.ts`. **주문 생성·견적이 공유하는 브랜드 단위 청구 규칙**
  (그 브랜드 라인이 전부 무료일 때만 면제).

## 프론트

- **klow_web**: 서버가 준 `customerPriceUsd`/`listPriceUsd`/`customerDiscountPercent`를 **그대로 렌더**하고, 현지통화 표시는
  `useLocalPrice`(`customerPriceUsd × CurrencyFxRate`)로 포맷만. 체크아웃은 `/v1/orders/quote`로 정확한 결제 총액을 받는다.
- **입력 방식은 두 앱이 다르지만 저장 정본은 동일**(basePriceUsd + 국가별 priceLocal 핀). `src/lib/cost-pricing.ts`가
  서버 공식(`serializePriceModel`/`deserializePriceModel` 역함수 쌍)을 미러해 입력 즉시 정산가·마진·원가 밑 경고를 미리보기.
  - **klow_admin**: **원가(KRW) + 기본 판매가(USD) 직접 입력** + 국가별 현지통화 핀. basePriceUsd 를 직접 다룬다.
  - **klow_brand**: 기본가는 **원가(KRW) + 마진(KRW) 입력** — 단 이는 앱이 즉시 **고정 판매가로 변환**하는 편의 입력이다(정산가 salePrice=원가+마진 저장 +
    저장 시점 fx 를 서버가 `basePriceFxRate` 로 스냅샷). 미핀 국가의 default 판매가는 **물류비가 빠져 전 국가 동일**하고 default 정산가 ≈ 원가+마진.
    국가별은 판매가 모달에서 **그 나라 현지통화 판매가를 직접 입력**해 `priceLocal` 핀으로 저장(그 국가만 판매가 고정·마진 역산). 카드의 국가별
    마진/정산가는 **읽기전용 역산 표시**(klow_brand `PriceStep`·`ProductDetailPreview` 가 `sellingPriceUSD` 로 동일 파생). 환율 소스 `/v1/shop/fx-rate`.

## 스키마

```prisma
model Product {
  basePriceUsd    Int?    // legacy/어드민 단일 판매가(USD 센트) + 신모델 대표/정렬·게이트값
  basePriceFxRate Float?  // 저장 시점 fx 스냅샷. 有=정산가 파생 신모델(판매가 환율 고정)
  salePrice       Int     // 정산가 저장값(≈원가+마진). 신모델 default 판매가 파생·프리즈 기준(마진은 역산)
  costKrw         Int?    // 원가(KRW) — 원가 밑 경고 기준
  freeShipping    Boolean // 무료배송 개별 토글. 실효 = brandRef.freeShippingAll || freeShipping
  boxLengthCm     Float?  // 박스 규격(cm) — 예상 청구 배송비의 부피무게용. 가격 무관
  boxWidthCm      Float?
  boxHeightCm     Float?
  discount        Int     // 글로벌 마케팅 할인%(legacy 폴백)
  countryPrices   ProductCountryPrice[]
}
model ProductCountryPrice {
  productId   String
  iso2        String   @db.VarChar(2)
  priceLocal  Float?   // 국가별 고정 현지통화 판매가(major). null = 기본 USD 상속
  marginKrw   Int?     // [dormant] 구 모델 마진. priceLocal 백필 소스만 — prod 백필 후 드롭 가능
  discountPct Int      @default(0)
  @@unique([productId, iso2])
}
model Brand {
  freeShippingAll Boolean // 브랜드관 전체 무료배송. 켜진 동안 개별 freeShipping 을 덮어씀(개별값은 보존)
}
model Order {
  shippingFeeUsd     Int   // = 물류비/2/fx × 청구 대상 브랜드수
  shippingFeeByBrand Json? // { brandId: 센트 }. 무료배송 브랜드는 0, Σ == shippingFeeUsd.
                           // legacy 주문은 null → 송장 발급이 균등분배로 폴백
}
model OrderItem {
  unitPriceUsd       Int   // 고객 결제 단가(USD 센트) 스냅샷
  settlementPriceKrw Int?  // 브랜드 정산 단가(KRW) — 주문 시점 환율로 역산 스냅샷
  costKrw            Int?  // 주문 시점 원가 스냅샷(원가 밑 판정)
}
```

### 명명·dormant 주의 (감사 메모)

- **`Product.salePrice` 는 이름과 달리 판매가가 아니라 정산가(≈원가+마진, KRW)** 를 담는다 — 역사적 명명이고, 컬럼명 리네임 대신
  주석/문서로 정정만 했다(정확한 이름은 `settlementKrw`). 신모델에선 default **판매가를 파생·프리즈**하는 저장 기준값이다(판매가가 정본, 마진/정산가는 역산 — legacy 아님).
- **dormant(저장만·로직 미사용) 컬럼** — 드롭 보류: `ProductCountryPrice.marginKrw`(유일 소비처 = `backfill-fixed-pricing.ts`,
  prod 백필 실행 후 드롭 가능), `Product.isLoss`.
  (`Product.weightG` 는 **더 이상 dormant 가 아니다** — 박스 규격과 함께 예상 청구 배송비의 청구중량 산출에 쓰인다. 가격엔 여전히 무관.)
  그 외:
  `ShippingCountry.emsSpecialFeePerKgKrw`·`ShopSettings.dhlFuelSurchargeRate`(구 요율 재조합 폐기).
- `ShippingRate` 모델은 시딩 EMS/DHL **비교 표 전용** — 주문/제품 가격(정산·판매가) 계산엔 쓰이지 않는다.
마이그레이션: `add_country_currency_and_fx`(통화) + 판매가 고정 전환 + `pricing_free_shipping`(무료배송·박스규격·브랜드별 배송비 스냅샷).
백필: `npm run backfill:fixed-pricing`(구 전환) · `npm run backfill:drop-logistics-markup`(물류비 분리 전환).

> **`backfill:drop-logistics-markup` 주의**: 판매가에서 물류비를 뺀 만큼 `salePrice` 를 올려 **현 판매가를 보존**한다
> (`salePrice += round(US 물류비/2)`). **멱등하지 않다** — 기본은 dry-run 이고 `-- --apply` 로만 쓴다.
> 기준국이 US 하나뿐이라 **다른 국가의 default 판매가는 `(US물류비 − 그국가물류비)/2/0.95/fx` 만큼 이동**한다
> (물류비가 US 보다 싼 아시아권은 인상, 비싼 국가는 인하). dry-run 이 국가별 델타 표를 출력하니 반드시 확인하고 진행할 것.
> **백필 → 코드 배포 순서**를 지킨다 — 뒤집으면 그 구간 주문마다 브랜드 정산이 조용히 깎인다.

## 이력 (보관 문서)

- 고객측 금액 USD 정본화: [`archive/pricing-usd-migration.md`](./archive/pricing-usd-migration.md)
- dormant 배송 요율 컬럼 드롭: [`archive/cleanup-dormant-shipping-rate.md`](./archive/cleanup-dormant-shipping-rate.md)
