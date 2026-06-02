# KLOW 가격 모델 (단일 참조)

KLOW의 가격·통화·할인 모델을 한 곳에 정리한 **현재 상태 기준** 문서다. 마이그레이션 절차/단계는
[`pricing-usd-migration.md`](./pricing-usd-migration.md), 결제 흐름은 [`payment-integration.md`](./payment-integration.md) 참고.

## 통화 규칙 (개념별 고정)

- **고객에게 받는 돈 = USD** — 노출가·결제 단가·주문 총액·PG 청구 전부 USD.
- **브랜드에게 주는 돈 = KRW** — 정산가·정산 지급 전부 KRW.
- 두 통화는 주문 시점 `Order.fxRateSnapshot` 으로 연결되어 추적된다.
- 가격 공식(마크업 $15 + 결제수수료 5%)과 환율(`ShopSettings.usdKrwRate`)은 **서버 단일 소스**.
  프론트는 서버가 내려준 값을 표시만 한다(복제 계산 금지).

## 한눈 표 — 무엇이 어디에 저장/계산되나

### 📦 상품 단위 (개당)

| 개념 | 누가 정함 | 통화 | 저장/계산 | 비고 |
|---|---|---|---|---|
| **브랜드 정산금액** (개당 받는 돈) | 브랜드 입력 | KRW | `Product.salePrice` **저장** | 브랜드가 입력하는 유일한 가격 |
| 할인율 | 어드민 입력 (브랜드는 0) | % | `Product.discount` **저장** | 고객가에 직접 적용되는 마케팅 할인 |
| **판매가** (쇼핑몰 노출 실제가) | 서버 계산 | USD | **저장 안 함** → 응답 `customerPriceUsd`(센트) | `(salePrice/fx + $15)/(1−0.05)` |
| 취소선 원가 (할인 연출) | 서버 계산 | USD | 저장 안 함 → 응답 `listPriceUsd`(센트) | `customerPriceUsd ÷ (1 − discount/100)` |
| 화면 할인율 뱃지 | 서버 전달 | % | 응답 `customerDiscountPercent` | `= discount` (고객가 기준이라 그대로) |

### 🧾 주문 단위 (결제 시 고정 스냅샷)

| 개념 | 통화 | 저장 위치 | 비고 |
|---|---|---|---|
| 주문 시점 고객 단가 | USD | `OrderItem.unitPriceUsd`(센트) | 주문 순간 customerPriceUsd 박음 |
| 주문 시점 정산 단가 | KRW | `OrderItem.settlementPriceKrw` | `= 주문 시점 salePrice` |
| 배송비 | USD | `Order.shippingFeeUsd`(센트) | `캐리어 feeUsd × distinct brandId 수` |
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
[고객 노출]  salePrice ─×fx+$15+5%→ customerPriceUsd (실제가)
             discount  ─역적용→        listPriceUsd = customerPriceUsd/(1−discount%) (취소선)
                                          │
[주문 확정]  고객측 → OrderItem.unitPriceUsd ─Σ→ Order.totalUsd  (+ shippingFeeUsd)
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

- `calculateCustomerPriceUsdCents(salePrice, fxRate)` — `klow_server/src/common/pricing.ts`
- `attachCustomerPricing(row, fxRate)` / `listPriceUsdCents(customerPriceUsd, discount)` —
  `klow_server/src/modules/products/product-selects.ts` (모든 상품 응답에 가격 3종 부착)
- `resolveFxRate(prisma)` — `klow_server/src/common/fx.ts`
- 미리보기(미저장 정산가 → 고객가): `GET /v1/shop/price-preview?settlementKrw=`

## Deprecated / 제거 예정

- `Product.price` (정가, KRW) — 더 이상 사용 안 함(nullable). 컬럼 DROP 은
  [`pricing-usd-migration.md`](./pricing-usd-migration.md) **단계 5(b)** 에서 일괄 수행.
- `Order.subtotal` · `OrderItem.unitPrice` · `Order.shippingFeeKrw` · `Order.shippingFeeUsdSnapshot`
  (KRW dual-write 컬럼) — 단계 5(a) 에서 DROP. **정본은 USD 컬럼**이므로 참조 금지.
