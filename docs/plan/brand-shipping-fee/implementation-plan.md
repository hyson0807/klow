# brand-shipping-fee — 구현 계획 (빌드 스펙 정본)

결정과 그 근거는 [`README.md`](./README.md) 에 있다. 여기엔 **무엇을 어떻게 만드나**만 둔다.
상태는 [`../../PROGRESS.md`](../../PROGRESS.md) 가 갖는다.

---

## §1 착수 게이트 — 코드를 쓰기 전에 알아야 할 것

### G1 ⚠️⚠️ `shippingFeeByBrand` 의 루프는 **"첫 라인 승"** 이다 — 2패스로 바꿔야 한다

`src/pricing/chargeable-brands.ts:52-57`:

```ts
for (const line of lines) {
  if (!line.brandId || byBrand[line.brandId] !== undefined) continue;  // ← 브랜드의 첫 라인만 본다
  const cents = chargeable.has(line.brandId) ? perBrandCents : 0;      // ← 금액이 상수라 정당했다
```

금액이 상수인 동안은 *"브랜드의 첫 라인만 보고 끝내기"* 가 맞다. **라인마다 값이 달라지는 순간
이 루프는 max 가 아니라 "배열 순서상 첫 제품의 배송비"가 된다.** 같은 장바구니를 담는 순서만
바꿔도 청구액이 달라지고, `quote()` 와 `create()` 가 `products` 배열을 각자 만들기 때문에
(`findMany` 의 `where id in` 은 순서를 보장하지 않는다) **견적가 ≠ 청구가**가 될 수 있다.

지금 그 불변식을 *"같은 헬퍼를 쓴다"* 로 지키고 있는데, 순서 의존이 들어오면 같은 헬퍼로도
안 지켜진다.

→ **① KRW 도메인에서 브랜드별 max 집계 → ② 브랜드별로 센트 변환 1회.**
`chargeableBrandIds` 는 `maxKrw > 0` 으로 자연히 파생되므로 **별도 함수로 남기지 않는다**
(남기면 판정이 두 벌로 갈린다).

⚠️ **반올림은 정확히 1회.** `max(round(a), round(b)) ≠ round(max(a, b))` 다.
라인별로 센트로 바꾼 뒤 max 를 취하면 안 된다. **KRW 에서 max → 그다음 센트.**

### G2 ⚠️⚠️ `writeProductCountryPrices` 는 **replace-all** 이라 두 방향으로 데이터를 죽인다

`src/pricing/country-price.ts:99-122` 는 `deleteMany` → `createMany` 다.

**(a) 저장 필터.** 104-110행의 *"기본값만인 행은 스킵"* 필터에 새 컬럼을 넣지 않으면
**"배송비만 설정한 국가"의 행이 저장 시점에 사라진다.** 실패가 에러가 아니라 *"요율표 기본값으로
되돌아감"* 이라 아무도 모른다.

**(b) 구 클라이언트의 파괴적 저장.** 쓰기 경로 4개가 전부 replace-all 이고
(`products.service.ts` 어드민 2곳 · `brand-applications.service.ts` 브랜드 2곳), 프론트는 배열을
**처음부터 다시 만든다**(klow_admin `ProductForm.tsx` 의 `buildCountryPrices`,
klow_brand `ProductForm.tsx` 의 payload 조립). 즉 **구버전 프론트가 제품을 한 번 저장하면 그
제품의 배송비 설정이 전부 날아간다.**

→ 대응 둘을 **함께** 쓴다.

1. **배포 순서 `klow_server → klow_admin → klow_brand`** — 브랜드가 금액을 설정하기 시작하는
   시점엔 어드민이 이미 그 값을 표현할 수 있다. `CLAUDE.md §4` 기본 순서 그대로다
2. **보존 shim** — payload 배열의 **어느 행에도 새 키가 없으면**(= 구 클라) `deleteMany` 전에
   기존 행을 `iso2 → 금액` 으로 읽어 캐리오버한다. 행 하나라도 키를 보내면 신 클라로 보고
   payload 가 정본. 열어 둔 낡은 탭까지 막는다. **프론트 배포 완료 후 제거**

⚠️ 같은 클래스의 사고 선례가 둘 있다 — `onsiteDiscountPct` 에 `.default(0)` 을 줬다가 구 탭
저장이 할인율을 지운 건([`decisions/products.md` 2026-08](../../decisions/products.md#2026-08)),
그리고 `ProductOnsiteCountryPrice` 를 **같은 테이블에 합치지 않고 나눈 이유**가 정확히 이
replace-all 쓰기 격리였다는 것.

### G3 ⚠️ `chargeableBrands` 카운트가 **센트 기준**이라 0원 함정이 있다

`src/modules/orders/orders.service.ts:884`:

```ts
chargeableBrands: Object.values(byBrand).filter((cents) => cents > 0).length,
```

klow_web 이 이 값으로 "무료" 라벨을 켠다(`checkout/page.tsx`). 브랜드가 **5원**을 입력하면
`round(5 / 1380 × 100) = 0센트` → 손님 화면에 **"무료배송"**, 정산도 0원, EFS 27번도 0원.
브랜드는 유료로 설정했는데 전 구간이 무료가 된다.

→ 판정을 **KRW 기준**(`maxKrw > 0`)으로 옮긴다. 커널에 *"krw > 0 이면 최소 1센트"* 바닥은
**두지 않는다** — 청구 커널에 특수 케이스를 넣는 것보다 입력 단계에서 막는 게 이 레포 관례다
(fail-closed 는 판정에, 보정은 UI 에). 브랜드 UI 가 "너무 작은 금액" 경고를 낸다.

### G4 ⚠️ 읽기 쪽은 **건드리지 않는다**

`Order.shippingFeeByBrand` 는 **이미 브랜드별 금액 맵**이다. 그래서 `perBrandShareUsd` 와
`orderBrandCount`, 그리고 그 소비처 — 송장 EFS 27번 안분 · 브랜드 정산 지급액
(`brandShippingSettlementKrw`) · efs-billing 선결제 참고값 · 어드민/브랜드 정산 화면 — 은
**전부 무수정으로 따라온다**. 생성 쪽만 바꾼다.

⚠️ **`perBrandShareUsd` 를 "고치려" 들지 말 것.** 그 함수는 EFS 27번 필드의 정본이기도 하다
([`decisions/settlement.md` 2026-09](../../decisions/settlement.md#2026-09)).

### G5 불변식

| 불변식 | 어떻게 지키나 |
|---|---|
| `Σ byBrand === shippingFeeUsd` | `total` 을 맵에서 **누적**해 만든다(정의상 성립). ⚠️ `total = round(rate × n / fx)` 로 따로 계산하려는 유혹을 막을 것 — 브랜드마다 값이 다르면 `× n` 자체가 성립하지 않는다 |
| 견적가 == 청구가 | `create()`/`quote()` 가 계속 같은 헬퍼를 공유 + **G1 의 순서 무관성** |
| `byBrand[b]` 는 `maxKrw[b]` 에서 **정확히 1회** 반올림 | G1 의 2패스 (KRW max → 센트) |
| 배송 가능 여부 게이트는 요금과 무관 | 요율 미설정국 · 캐리어 미설정 · EFS 제외구역은 **0원이어도 그대로 막는다**(현행 유지) |

---

## §2 스키마

```prisma
model ProductCountryPrice {
  ...
  freeShipping        Boolean @default(false)  // [dormant] 파생 미러 — 쓰기만 하고 읽지 않는다
  shippingKrwOverride Int?                     // NULL=500g 요율 추종 / 0=무료 / >0=브랜드 지정
}
```

`ADD COLUMN` nullable → **롤링 안전**. 백필은 **같은 마이그레이션 SQL 안에** 넣는다:

```sql
UPDATE "ProductCountryPrice" SET "shippingKrwOverride" = 0
 WHERE "freeShipping" = true AND "shippingKrwOverride" IS NULL;
```

⚠️ **별도 백필 스크립트로 빼지 않는다.** 이 레포는 데이터 백필을 마이그레이션 SQL 안에 넣는 것이
관례고(`20260617213856_backfill_shipping_country_enabled` · `20260618032438_seeding_fee_krw_backfill`
등 10건 이상), 그래야 `ADD COLUMN` 과 원자적이며 *"컬럼은 있는데 백필 전"* 창이 없다.
멱등성은 `IS NULL` 이 확보한다.

⚠️ `freeShipping` 은 **드롭하지 않는다**(`DROP COLUMN` 은 롤링 비안전). 대신
`freeShipping = (shippingKrwOverride === 0)` 으로 **dual-write** 한다. **정본은 새 컬럼 하나**이고
구 컬럼은 읽지 않는다 — `BrandUser.phone` 이 `BrandUserPhone` 의 비정규화 미러인 것과 같은 구조다.
드롭은 `§5` 에서 **예약**만 한다.

### zod (어드민·브랜드 공용 — `src/common/validation/product.ts`)

```ts
shippingKrwOverride: z.coerce.number().int().min(0).max(1_000_000).nullish()
```

⚠️⚠️ **`.default()` 를 쓰지 않는다.** `undefined`(미전송) / `null`(요율표 추종) / `0`(무료)이
**셋 다 다른 뜻**이어야 G2 의 보존 shim 이 작동한다. `.max(1_000_000)` 은 정책이 아니라
**자릿수 오타 방어**다(`priceLocal` 의 `1억` 을 베끼지 말 것 — 그건 VND/IDR major 를 담기 때문이다).

---

## §3 단계

### 1. 스키마 · 마이그레이션 · 쓰기 경로

- **읽을 것**: `§1` G2 · `§2` 전체, `server/modules/products.md` 와
  `server/modules/brand-applications.md` 의 제품 저장 엔드포인트 절,
  [`decisions/products.md` 2026-08](../../decisions/products.md#2026-08) 의 `onsiteDiscountPct` 문단
- **건드리는 레포 · 배포 순서**: klow_server — **이 단계 자체는 배포 없음**(2단계 끝에 함께 나간다)
- **스키마·데이터 위험**: 마이그레이션 `add_product_country_shipping_override` ·
  `ADD COLUMN` nullable → **롤링 안전** · **백필이 같은 SQL 안에** 있고 멱등 ·
  ⚠️ **git 브랜치 + Neon DB 브랜치를 함께 판다**(기준선 `staging`)
- **할 일**
  - `schema.prisma` 컬럼 추가 + 주석(세 상태의 뜻) + `npx prisma migrate dev --name add_product_country_shipping_override`
  - 생성된 SQL 에 백필 `UPDATE` 한 줄 추가
  - `src/pricing/country-price.ts` — `PRODUCT_COUNTRY_PRICE_SELECT` · `PricingCountryPrice` 타입 ·
    `CountryPriceInput` 에 새 필드. `writeProductCountryPrices` 에 **① 저장 필터 확장
    ② 보존 shim ③ dual-write** 셋
  - `src/common/validation/product.ts` — 위 zod (`.nullish()`)
  - **이행 어댑터** — 구 프론트의 `freeShipping: true` → `shippingKrwOverride: 0` 번역
  - `brand-applications.service.ts` `mapBrandProduct` — `freeShippingCountries` 를 **새 컬럼에서
    파생**하고(구 스튜디오 호환 유지) 새 맵 필드를 함께 싣는다
- **완료 기준**
  - 운영 SELECT 로 `freeShipping = true` 행 수·제품 수·브랜드 수를 **실측해 기록**한다
    (⚠️ dev 브랜치 수치로 판단하지 않는다)
  - DB 브랜치에서 백필 후 `shippingKrwOverride = 0` 행 수가 위 실측치와 일치
  - 스펙 2개: **"배송비만 설정한 행이 저장에서 살아남는다"**,
    **"새 키 없는 payload 는 기존 금액을 보존한다"**
  - ⚠️ `mapBrandProduct` 왕복 — 무료배송을 켠 제품을 구 스튜디오 형식으로 읽으면
    `freeShippingCountries` 에 그 국가가 그대로 들어온다

### 2. 청구 커널

- **읽을 것**: `§1` G1·G3·G4·G5, `server/modules/orders.md` 의 `quote`/`create` 절,
  [`reference/pricing-model.md`](../../reference/pricing-model.md) 의 배송비 절,
  [`decisions/settlement.md` 2026-09](../../decisions/settlement.md#2026-09)
- **건드리는 레포 · 배포 순서**: **klow_server**(단독 선배포. 프론트가 아직 구버전이어도
  이행 어댑터가 받는다)
- **스키마·데이터 위험**: **없음**
- **할 일**
  - `country-price.ts` — `resolveShippingKrw(row, iso2, defaultRateKrw): number`
    (행 없음·`NULL` → `defaultRateKrw`). `resolveFreeShipping` 은 여기서 **파생**시키거나 제거
  - `chargeable-brands.ts` — **2패스 재작성**(G1). `chargeableBrandIds` 흡수.
    `shippingFeeByBrand` 의 `rateKrw` 인자는 이름을 **`defaultRateKrw`** 로 바꿔 의미를 못박는다
  - `orders.service.ts:884` — `chargeableBrands` 를 **KRW 기준**으로(G3)
  - `price-line.ts:305` — `freeShipping: cp?.shippingKrwOverride === 0`
    (⚠️ onsite 경로의 고정 `false` 는 그대로 — `onsite-pricing.spec.ts` 가 잠그고 있다)
  - 어드민 주문 상세 응답에 `Order.shippingFeeByBrand` 를 싣는다(3단계가 그릴 표의 재료)
  - `server/modules/orders.md`·`products.md` 갱신
- **완료 기준** — 기존 스펙 3개(`chargeable-brands` · `onsite-pricing` · `promotion-pricing`)를
  의미 보존한 채 번역하고, **새 회귀 잠금 5개**를 넣는다.
  ⚠️ `test/app.e2e-spec.ts` 는 DB 없는 부팅 스모크라 이 변경을 **잡아 주지 않는다** — 잠금은
  전부 유닛 스펙이다
  1. 혼합 라인(0원 + 5,000원) → 브랜드 금액 **5,000원** (max)
  2. **라인 순서를 뒤집어도 `byBrand` 동일** (G1 직격)
  3. `NULL` / 행 없음 → 기본 요율 (fail-closed 유지)
  4. 다른 국가 행만 있으면 목적국은 기본 요율
  5. **브랜드마다 금액이 다를 때도 `Σ byBrand === total`**

### 3~5 (제목과 순서만 — 착수 세션에서 명세한다)

앞 단계가 끝나야 전제가 확정되므로 지금 정밀하게 쓰지 않는다 — **틀린 명세는 없는 명세보다 나쁘다.**

| # | 단계 | 한 줄 | 레포 |
|---|---|---|---|
| 3 | **klow_admin** | 제품 폼 국가별 토글 → 숫자 입력(기본값 표시 포함) · 주문 상세에 브랜드별 배송비 표 | klow_admin |
| 4 | **klow_brand** | `PriceModal` 스위치 → 금액 입력+슬라이더 · `PriceStep` 일괄/카드 · `ProductForm` state · `cost-pricing` 왕복 · **`prepaidKrw` 산식(R8)** · **max 경고 문구(R7)** | klow_brand |
| 5 | **klow_web + 마무리** | 견적 전 추정 제거(R4) · 주석/문서 전수 정정(R9) · `freeShipping` 드롭 예약 · **운영 배포** | klow_web |

---

## §4 위험 대장

`§1` 이 착수 전에 반드시 읽어야 할 넷(G1·G2·G3·G4)을 갖고, 여기엔 나머지를 둔다.

### R7 — PDP 무료배송 배지 ↔ max 집계 괴리가 **훨씬 흔해진다**

`price-line.ts` 의 `freeShipping` 은 **제품 단위** 파생인데 청구는 **브랜드 max** 다. 오늘도 있는
괴리지만, 불린 시절엔 브랜드가 "전 제품 무료" 또는 "전 제품 유료"로 쏠려서 잘 안 터졌다. 숫자가
되면 제품별로 값을 다르게 줄 유인이 커지고(신제품만 무료배송 프로모션 등), *"배지 보고 담았는데
체크아웃에서 3,000원"* 이 일상이 된다.

→ 정책은 유지한다(결정 1). 대신 **브랜드 모달에 고정 문구**를 둔다:
*"같은 브랜드의 다른 제품과 함께 주문되면 그중 가장 비싼 배송비가 청구됩니다."*
이건 문구 문제가 아니라 **브랜드가 프로모션 설계를 오판하는 문제**다.

### R8 — 브랜드 손익 비교표가 틀린 값을 보여주게 된다

`klow_brand .../product-form/PriceStep.tsx:495` 가 `prepaidKrw={openRow.shipKrw}` 로 **그 나라 500g
요율**을 넘기고, `PriceModal.tsx:451` 의 `BurdenRow` 가
`shipCostKrw - prepaidKrw * (1 - PG_FEE_RATE)` 로 브랜드 부담액을 계산한다.

브랜드가 금액을 직접 정하면 이 식의 `prepaidKrw` 는 **브랜드가 설정한 값**이어야 한다. 안 고치면
브랜드가 *"배송비를 올렸는데 손익 표시가 안 움직인다"* 를 보거나, 더 나쁘게 **잘못된 손익을 보고
가격을 결정**한다. **4단계 필수 항목.**

### R4 — klow_web 낙관적 추정의 "상한 보장"이 깨진다

`klow_web/src/lib/cart.ts` 가 `cartBrandCount` 를 **"무료배송을 반영하지 않는 상한 추정치"** 로
계약하고, `checkout/page.tsx` 가 **"과대 추정만 하고 과소는 안 한다"** 고 못 박은 뒤
`perBrandShippingCents × cartBrands` 를 쓴다.

브랜드가 요율표보다 **비싸게** 매기는 순간 계약이 뒤집혀, 결제 직전에 총액이 **올라가는** 점프가
생긴다(내려가는 점프와 심리적 무게가 다르다). 상한 없는 입력을 허용한 이상 구조적으로 피할 수 없다.

→ **견적 도착 전에는 금액 대신 "계산 중"** 을 보여준다(총액도 소계만). 가장 정직하고 코드도 작다.
⚠️ **카트 라인에 금액을 스냅샷하지 말 것** — 무료배송 불린을 카트에서 뺀 이유
(`useCartStore` v2 마이그레이션)와 정확히 같은 이유로 배송지 변경 시 어긋난다.

### R9 — 주석·문서 드리프트 (5단계에서 전수 정정)

`freeShipping` 또는 *"브랜드당 같은 금액"* 을 단언하는 곳:
`prisma/schema.prisma`(`ProductCountryPrice` · `Order` 주석) · `src/pricing/` 4파일
(`chargeable-brands` 상단 블록 · `formulas` · `country-price` · `price-line`) ·
`src/modules/cart/cart.service.ts` · `orders.service.ts` · `shipping/shipping.service.ts` ·
[`decisions/shipping-seeding.md` 2026-07-28](../../decisions/shipping-seeding.md#2026-07-28) ·
[`reference/pricing-model.md`](../../reference/pricing-model.md).

⚠️⚠️ **특히 `efs-billing.service.ts` 의 이 문장이 거짓이 된다**:

> 적자가 이어질 때 고칠 곳은 여전히 **배송비용 탭의 국가 요율표**다.

이 트랙 이후로는 적자의 원인이 **브랜드 자의의 설정**일 수 있다. 이 레포는 주석이 계약이라,
남겨 두면 다음 사람이 옛 규칙으로 최적화한다.

조사 중 **이미 틀려 있던 것** 둘도 같이 고친다(이 트랙이 만든 드리프트가 아니다):

- `schema.prisma` 가 `resolveFreeShipping` 을 `product-selects.ts` 에 있다고 하는데 실제로는
  `src/pricing/country-price.ts` 다
- `schema.prisma`(`ShippingCountry.productLogisticsCostKrw`) 와 `country-price.ts` 가
  *"국가 **2kg** 요율의 **절반**"* 이라고 하는데 실제는 **500g 요율 전액**이다
  (`CUSTOMER_SHIPPING_WEIGHT_G = 500`)

### R10 — 어드민 손익 감시는 이번에 안 한다 (의도된 부채)

efs-billing 의 `요율표 대비` 컬럼을 **뺐다**(결정 7). 브랜드가 배송비를 낮췄을 때 어떤 패턴이
나올지 아직 모르기 때문이고, **실제로 적자 행이 보이기 시작하면 그때 더한다.**
그때 필요한 재료는 이미 다 있다 — 행의 `prepaidKrw` 와 그 국가 500g 요율.

---

## §5 이 트랙이 끝나면

- **`freeShipping` 드롭을 예약한다.** 세 프론트 배포가 끝나고 관측 기간을 지난 뒤 별도
  마이그레이션으로 뗀다. ⚠️ **`DROP COLUMN` 은 롤링 비안전**이라 단일 레플리카 컷오버 또는
  2단계 배포가 필요하다
- **보존 shim 을 걷어낸다**(G2) — klow_admin·klow_brand 배포가 끝나면 그 시점부터 죽은 코드다
- **퇴출 판정**(`PROGRESS.md §2`)은 **`archive/`** 다 — `server/modules/products.md` 와
  `reference/pricing-model.md` 가 현행 사양의 설명을 이미 갖는다. 결정과 함정은
  `decisions/shipping-seeding.md` 에 항목으로 올리고 색인 2곳(`decisions/README.md` ·
  `CLAUDE.md`)에 한 줄씩 넣는다
