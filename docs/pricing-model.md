# KLOW 가격 모델 (단일 참조)

KLOW의 가격·통화·할인 모델을 한 곳에 정리한 **현재 상태 기준** 문서다. 마이그레이션 절차/단계는
[`pricing-usd-migration.md`](./pricing-usd-migration.md), 결제 흐름은 [`payment-integration.md`](./payment-integration.md) 참고.

## 통화 규칙 (개념별 고정)

- **고객에게 받는 돈 = USD** — 노출가·결제 단가·주문 총액·PG 청구 전부 USD.
- **브랜드에게 주는 돈 = KRW** — 정산가·정산 지급 전부 KRW.
- 두 통화는 주문 시점 `Order.fxRateSnapshot` 으로 연결되어 추적된다.
- 가격 공식(마크업 + 결제수수료 5%)과 환율(`ShopSettings.usdKrwRate`)은 **서버 단일 소스**.
  프론트는 서버 공식을 미러하되 요율 데이터도 서버에서 받아 쓴다(체크아웃은 서버 청구액과 cent-exact).
- **마크업·배송비는 배송 국가별 "2kg 고정 요율"의 절반씩**이다. **제품 무게는 가격에 영향이 없다.**
  요율은 `ShippingCountry.{efs,ems,dhl}RateKrw`(= ShippingRate 2kg 티어 올림 동기화한 대표값)에서 온다.
  $15(`GLOBAL_SALE_MARKUP_USD`)는 목적지를 모르는 둘러보기 카드의 **기준 표시값**일 뿐, 실제가는 국가에 따라 달라진다.
- **요율의 캐리어는 2kg 기준 최저가**: EFS·EMS 둘 다 가능하면 더 싼 쪽(동점 → EFS, EFS 제외구역이면
  EMS), 둘 다 불가면 DHL. EFS 가 가능해도 EMS 가 더 싸면 EMS 요율을 쓴다.
  요율·캐리어 선택 구조는 [`klow_server/docs/modules/shipping.md`](../klow_server/docs/modules/shipping.md) 참고.
  (무게 티어 테이블 `ShippingRate`·엑셀 업로드·어드민 매트릭스는 유지 — 대표값 도출 + 크리에이터 시딩 박스 비용 산정용.)
- **kg당 추가요금**: EFS 유류할증료(`ShippingCountry.efsFuelSurchargePerKgKrw`)·EMS 특별운송수수료
  (`emsSpecialFeePerKgKrw`)가 캐리어 기본 요율에 `perKg × 올림(무게/1kg)` 만큼 가산된다(DHL 0).
  **2kg 고정 경로(판매가/배송비)는 ×2**, 시딩은 실측/부피 무게(max) 기준. 가산된 총액이 다시 판매가·배송비에
  절반씩 분할된다(예: 기본 15,000 + 2kg 추가요금을 7,500:7,500 식으로). 최저가 캐리어 비교도 추가요금 포함
  총액 기준. 어드민이 국가 상세페이지에서 편집(시드 `npm run seed:shipping-surcharges`). 구조는
  [`klow_server/docs/modules/shipping.md`](../klow_server/docs/modules/shipping.md) 참고.

## 한눈 표 — 무엇이 어디에 저장/계산되나

### 📦 상품 단위 (개당)

| 개념 | 누가 정함 | 통화 | 저장/계산 | 비고 |
|---|---|---|---|---|
| **브랜드 정산금액** (개당 받는 돈) | 브랜드 입력 | KRW | `Product.salePrice` **저장** | 브랜드가 입력하는 유일한 가격 |
| **제품 무게** | (브랜드 입력 안 함) | g | `Product.weightG` **저장** | 가격과 무관(legacy 호환용, 1kg 기본). EFS 송장도 입고 시 재측정 |
| 할인율 | 어드민 입력 (브랜드는 0) | % | `Product.discount` **저장** | 고객가에 직접 적용되는 마케팅 할인 |
| **판매가** (쇼핑몰 노출 실제가) | 서버 계산 | USD | **저장 안 함** → 응답 `customerPriceUsd`(센트, 기준 $15) | `(salePrice/fx + markup)/(1−0.05)`. markup = `요율(국가 2kg)/2/fx`. 응답값은 $15 기준이고 프론트가 국가로 보정 |
| 취소선 원가 (할인 연출) | 서버 계산 | USD | 저장 안 함 → 응답 `listPriceUsd`(센트) | `customerPriceUsd ÷ (1 − discount/100)` |
| 화면 할인율 뱃지 | 서버 전달 | % | 응답 `customerDiscountPercent` | `= discount` (고객가 기준이라 그대로) |

### 🧾 주문 단위 (결제 시 고정 스냅샷)

| 개념 | 통화 | 저장 위치 | 비고 |
|---|---|---|---|
| 주문 시점 고객 단가 | USD | `OrderItem.unitPriceUsd`(센트) | `(salePrice/fx + 요율(국가 2kg)/2/fx)/(1−0.05)` 단일 반올림 (전 아이템 공통) |
| 주문 시점 정산 단가 | KRW | `OrderItem.settlementPriceKrw` | `= 주문 시점 salePrice` |
| 배송비 | USD | `Order.shippingFeeUsd`(센트) | `요율(국가 2kg)/2/fx × 브랜드수` (한 브랜드 = 한 송장) |
| **고객 결제 총액** (배송비 포함 실제 결제액) | USD | `Order.totalUsd`(센트) | `Σ unitPriceUsd×수량 + shippingFeeUsd` |
| 환율 고정 스냅샷 | — | `Order.fxRateSnapshot` | 결제·환불·정산 환산 기준 |

### 💳 결제 / 정산

| 개념 | 값 | 통화 |
|---|---|---|
| **PG(Eximbay) 청구액** | `Order.totalUsd ÷ 100` → `"$X.XX"` | USD |
| **브랜드 실제 정산 지급** | Σ `OrderItem.settlementPriceKrw` | KRW |
| 운영 환율 (어드민 설정) | `ShopSettings.usdKrwRate` → `/v1/shop/fx-rate` | — |

> **USD 금액은 모두 정수 센트** (예: `2630` = `$26.30`). 표시·PG 경계에서만 `cents/100 → "26.30"`.

## 흐름

```
[브랜드 입력]  정산가(KRW) ──저장──▶ Product.salePrice
[어드민 입력]  할인율(%)   ──저장──▶ Product.discount   (브랜드 제품은 0)
                                          │
[고객 노출]  salePrice ─×fx+마크업+5%→ customerPriceUsd (실제가)
             마크업 = 요율(국가 2kg)/2/fx  (국가별 고정 요율, 제품 무게 무관, 카드는 기준 $15)
             discount  ─역적용→        listPriceUsd = customerPriceUsd/(1−discount%) (취소선)
                                          │
[주문 확정]  고객측 → OrderItem.unitPriceUsd ─Σ→ Order.totalUsd
             배송비   → 요율(국가 2kg)/2/fx × 브랜드수 → Order.shippingFeeUsd
             브랜드측 → OrderItem.settlementPriceKrw (= salePrice)
             + Order.fxRateSnapshot 고정
                                          │
[결제]  Order.totalUsd ÷100 → "$X.XX" ──▶ Eximbay (USD)
[정산]  Σ settlementPriceKrw ──▶ 브랜드 원화 입금 (KRW)
```

## 할인의 의미 (중요)

할인은 **마케팅 앵커**다 — 브랜드 정산을 깎지 않는다.
- 브랜드는 할인과 무관하게 항상 `salePrice` 를 정산받는다.
- `discount` 는 고객 결제가(`customerPriceUsd`)에 **직접** 적용된다 → 취소선 원가를 부풀려
  "N% off" 로 보여줄 뿐, 고객이 실제 내는 돈은 `customerPriceUsd` 그대로.
- 따라서 **뱃지에 표시되는 할인율 = 화면의 (취소선−실제가)/취소선** 이 정확히 일치한다.
  (구 모델은 정산가 기준 % 라 고정 마크업+수수료에 비율이 압축돼 화면과 어긋났음 — 폐기.)

## 마진

```
주문당 마진(USD) = Order.totalUsd − (Σ OrderItem.settlementPriceKrw ÷ Order.fxRateSnapshot)
```
환위험은 주문 시점 `fxRateSnapshot` 으로 고정·추적된다.

## 핵심 함수 (서버, 단일 소스)

- `calculateCustomerPriceUsdCents(salePrice, fxRate, markupUsd?)` — `klow_server/src/common/pricing.ts`
  (markupUsd 주입형 — 주문은 `요율(국가 2kg)/2/fx`, 상품 응답 기본값은 $15)
- `attachCustomerPricing(row, fxRate)` / `listPriceUsdCents(customerPriceUsd, discount)` —
  `klow_server/src/modules/products/product-selects.ts` (모든 상품 응답에 가격 3종 부착, 기준 $15)
- 요율·캐리어: `resolveFixedRate(iso2, address?)`(주문 가격 정본 — 국가별 2kg 미러 컬럼 최저가) /
  `pickCheapestCarrier`(EFS·EMS 최저가) / `loadCheapestRatePlanner`·`resolveRatesForWeight`(시딩 박스 무게별) —
  `klow_server/src/modules/shipping/shipping.service.ts`. 미러 2kg 동기화는 `rate-import/rate-writer.syncCountryColumn`.
- `resolveFxRate(prisma)` — `klow_server/src/common/fx.ts`
- 미리보기: 정산가→고객가 `GET /v1/shop/price-preview?settlementKrw=`, 국가별 2kg 요율 `GET /v1/shipping-countries`(미러 컬럼).
  (`GET /v1/shipping-countries/rates/by-weight?weightG=` 는 이제 시딩 박스 비용 전용.)

## 프론트 미러 (요율 데이터는 서버에서 수신)

- **klow_web**: `lib/pricing.ts` (`markupDeviationCents`, `customerPriceUsdCents`),
  `useCountryPricing`(둘러보기 카드 — 선택 국가 2kg 요율로 base+편차 보정), `checkout`(결제가는
  `customerPriceUsdCents` 절대식으로 서버와 cent-exact, 배송비는 `요율(국가 2kg)/2 × 브랜드수`).
- **klow_brand**: 제품 등록에 무게 입력 없음 + `useShippingCountries`(2kg 미러) 로 국가별 판매가 미리보기.
- **klow_admin**: 국가 상세의 무게×캐리어 요율 매트릭스(셀 편집) + 엑셀 재업로드(대표값 2kg).

## Deprecated / 제거 완료

아래 컬럼들은 모두 **DROP 완료**. 고객측 금액 정본은 USD 컬럼(`totalUsd`/`unitPriceUsd`/`shippingFeeUsd`),
정산측 정본은 KRW(`settlementPriceKrw`)다.

- ~~`Product.price` (정가, KRW)~~ — discount 가 고객가 기준 직접 입력값이라 정가 컬럼 불필요. 단독 DROP.
- ~~`Order.subtotal` · `OrderItem.unitPrice` · `Order.shippingFeeKrw` · `Order.shippingFeeUsdSnapshot`~~
  (KRW dual-write 컬럼) — [`pricing-usd-migration.md`](./pricing-usd-migration.md) **단계 5(a)** 에서 DROP.
