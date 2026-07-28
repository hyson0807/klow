# 배포 런북 — 판매가에서 물류비 분리 + 무료배송 (staging → main)

판매가에 섞여 있던 **국가별 2kg 물류비의 절반(마크업)을 제거**하고, 제품/브랜드 단위 **무료배송 판매 모드**를
추가하는 릴리스의 프로덕션 배포 절차. **순서를 지키지 않으면 브랜드 정산이 조용히 깎이므로** 아래를 따른다.

관련 문서: [`pricing-model.md`](./pricing-model.md) · [이전 전환 런북](./deploy-fixed-pricing-runbook.md)

## 왜 순서가 중요한가

신 공식은 `판매가 = 정산가 ÷ 0.95 ÷ 환율` 로 물류비 항이 없다. 백필 없이 신 코드가 트래픽을 받으면
기존 제품 판매가가 `물류비/2 ÷ 0.95` 만큼 **떨어진다**. 정산가는 청구액에서 역산되므로 그 구간 주문마다
브랜드 정산이 같이 깎이는데, **고객에게 안 보이고 사후 복구도 어렵다.**

| 순서 | 그 구간 증상 | 부담 |
|---|---|---|
| **백필 → 배포** ✅ | 가격이 마크업만큼 비쌈(구 공식이 이미 오른 salePrice 에 또 더함) | 고객 — 눈에 보이고 환불 가능 |
| 배포 → 백필 ❌ | 가격이 마크업만큼 쌈 + **브랜드 마진이 조용히 깎임** | 브랜드 — 안 보이고 되돌리기 어려움 |

백필은 `salePrice += round(US 물류비/2)` 로 **정산가를 올려 판매가를 지금 수준에 고정**한다.
늘어난 정산가는 이후 실측 물류비 후청구로 다시 빠져나가므로 브랜드 순수취는 유지된다.

## 순서 (klow_server)

```bash
cd klow_server        # ⚠️ DATABASE_URL 이 prod 를 가리키는지 먼저 확인

# 1) 마이그레이션 — 컬럼 5개 추가.
#    Product.freeShipping/boxLengthCm/boxWidthCm/boxHeightCm, Brand.freeShippingAll,
#    Order.shippingFeeByBrand. 전부 default 有 additive 라 구코드가 무시한다 → 먼저 적용해도 안전.
npx prisma migrate deploy

# 2) 백필 dry-run — 아무것도 쓰지 않는다. 출력 3가지를 눈으로 확인할 것.
npm run backfill:drop-logistics-markup

# 3) 백필 반영 — ⚠️ 멱등하지 않다. 단 한 번만.
npm run backfill:drop-logistics-markup -- --apply

# 4) 신 서버 코드 배포 (2~4 는 붙여서, 트래픽 최저 시간대에)
```

그 다음 `klow_web` / `klow_admin` / `klow_brand` 배포 — 서버 배포 후라면 순서 무관.

### dry-run 에서 확인할 것

1. **`기준국 US 물류비 ₩… → salePrice 보정액 +₩…`** — prod 의 US `productLogisticsCostKrw` 절반이다.
   dev 는 ₩42,200 → +₩21,100 이었다. prod 값이 다르면 결과도 다르다.
   US 물류비가 비어 있으면 스크립트가 **거부하고 멈춘다**(조용히 0건 성공 → 전 국가 가격 하락 사고 방지).
2. **국가별 default 판매가 이동 표** — US 기준으로 보정하므로 US 보다 물류비가 싼 나라(아시아권)는
   판매가가 **오르고**, 비싼 나라는 내린다. 인상분은 브랜드 정산으로 간다. 운영/CS 가 이 숫자를 알고 있어야 한다.
3. **샘플 5건의 `US 판매가 before → after`** — 전부 `✓`(동일)여야 정상. 하나라도 `Δ` 가 뜨면 중단하고 원인 파악.

### 백필 대상/제외

- 대상 = `basePriceFxRate != null AND salePrice > 0` (브랜드 신모델 제품)
- 제외 = 어드민/legacy(`basePriceFxRate = null` — `basePriceUsd` 를 직접 쓰므로 애초에 영향 없음) ·
  `salePrice = 0` · `ProductCountryPrice.priceLocal` 핀(절대가라 물류비 성분이 없음)

## 배포 후 스모크

1. **US 판매가 보존** — 백필 전 기록해둔 제품의 `GET /v1/products/:id?country=US` `customerPriceUsd` 가
   구 판매가와 동일(±1센트).
2. **전 국가 동일가** — `?country=JP|CN|SG` 가 US 와 같은 값(핀·할인 있는 제품 제외).
3. **견적 == 청구** — `POST /v1/orders/quote` 의 `itemsTotalUsd` 가 표시가 × 수량과 일치,
   `shippingFeeUsd = 물류비/2/fx × 청구 대상 브랜드수`.
4. **무료배송** — 제품 하나를 `freeShipping=true` 로 두고 견적 → `shippingFeeUsd=0`.
   같은 브랜드에 유료 라인을 섞으면 다시 1회 청구.
5. **어드민/legacy 무변경** — `basePriceFxRate = null` 제품 가격이 백필 전후 동일.
6. **온사이트 무변경** — 부스 주문가(`basePriceUsd`)는 백필이 같은 값으로 재계산하므로 안 바뀐다.

## 사전 공지 (배포 전)

- **아시아 판매가 인상** — JP/CN/SG/TW/VN 등 제품가가 오른다(dev 기준 $8~12). 배송비는 그대로라
  고객 총액도 같은 폭으로 오른다. 마케팅·CS 사전 안내 필요.
- **브랜드 화면의 마진 점프** — `salePrice` 가 보정액만큼 오르므로 klow_brand 스튜디오의
  `deserializePriceModel`(`defaultProfit = salePrice − costKRW`)이 **마진이 하룻밤에 뛴 것처럼** 보여준다.
  판매가는 그대로다. "배송비가 판매가에서 분리되어 표시 마진에 물류비 몫이 합산됩니다 — 실제 배송비는
  사후 청구됩니다" 안내 필요.

## 롤백

백필은 되돌리는 스크립트가 없다(`salePrice -= 보정액` 을 수기로 돌려야 한다). 다만 **코드만 롤백하면**
구 공식이 오른 `salePrice` 에 물류비를 또 더해 **가격이 마크업만큼 비싸진다** — 고객에게 보이는 방향이라
즉시 발견되고 환불 가능하다. 코드 롤백 시엔 백필 되돌리기까지 같이 해야 원상복구다.

## 미구현 — 실측 물류비 후청구

어드민이 송장별 실측비를 입력해 `max(0, 실측 − 고객 선결제)` 를 브랜드에 청구하는 흐름은 **이번 릴리스에 없다.**
구 모델은 물류비 절반을 판매가 마크업으로, 절반을 배송비로 걷어 KLOW 가 실측 전액을 회수했다.
신 모델은 고객에게서 **절반만** 걷으므로, 후청구가 붙기 전까지 나머지 절반(주문당 `그 국가 물류비/2`)을
**KLOW 가 그대로 떠안는다.** US 주문 기준 건당 약 ₩21,100, JP ₩4,980.
릴리스와 가까운 시점에 붙여야 할 항목이다.
