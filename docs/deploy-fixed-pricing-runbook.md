# 배포 런북 — 판매가 고정 가격 모델 (staging → main)

가격 모델을 "브랜드 마진 고정 → 고객 USD 변동"에서 **"판매가 고정 + 브랜드 정산 유동"**으로 전환하는
릴리스의 프로덕션 배포 절차. **순서를 지키지 않으면 전 제품이 노출/구매 불가가 되거나 과청구가 발생**하므로
아래 순서를 반드시 따른다.

## 왜 순서가 중요한가

- **노출/구매 게이트가 `basePriceUsd > 0` 로 이관됨** (`product-selects.ts` `PURCHASABLE_PRODUCT_WHERE`).
  마이그레이션은 `basePriceUsd` 를 `null` 로 추가하므로, **백필 전에 신 서버가 트래픽을 받으면
  기존 전 제품이 `basePriceUsd=null` → 전부 사라진다.**
- **현지통화 핀(`priceLocal`)의 청구 USD 는 `CurrencyFxRate` 환율로 산출된다.** 백필이 핀을 현지통화로
  환산할 때 이 환율 행이 있어야 하고, 런타임에도 non-USD 통화의 유효 환율 행이 없으면 주문이 차단된다
  (과청구 방지 가드). 따라서 **환율 행이 실제로 채워진 뒤** 백필/트래픽을 진행해야 한다.

## 순서 (klow_server)

```bash
cd klow_server

# 1) 마이그레이션 — 컬럼 추가 (basePriceUsd/costKrw/priceLocal/currencyCode/CurrencyFxRate 등)
npx prisma migrate deploy   # 운영 배포 시. 로컬 검증은 migrate dev.

# 2) 국가→통화 매핑 + 환율 부트스트랩. ⚠️ 환율 API 실패 시 currencyCode 만 채우고
#    CurrencyFxRate 부트스트랩을 건너뛴다 — 반드시 rows 가 채워졌는지 확인할 것.
npm run seed:country-currency

#    검증: USD 외 통화 환율 행이 실제로 있는지 (0건이면 백필 금지 — cron/재실행으로 채운 뒤 진행)
#    예) psql "$DATABASE_URL" -c "select count(*) from \"CurrencyFxRate\" where code<>'USD' and \"usdRate\">0;"

# 3) 백필 — 전환 순간의 현재 US 판매가를 basePriceUsd 로, 구 marginKrw 오버라이드 국가를 priceLocal 핀으로.
npm run backfill:fixed-pricing

#    검증: basePriceUsd 미설정(=null) 제품이 없어야 함 (있으면 노출 누락)
#    예) psql "$DATABASE_URL" -c "select count(*) from \"Product\" where \"basePriceUsd\" is null;"

# 4) 신 서버 코드 배포(트래픽 오픈) — 위 3단계가 끝난 뒤에만.
```

배포 후 스모크: 핀 국가(예: JP) 제품 상세에서 `customerPriceUsd` 표시가 뜨는지, `/v1/orders/quote` 의
`unitPriceUsd` 와 일치하는지, 환율 행을 일시 제거/0 으로 만들면 그 국가 핀 상품 주문이 400 으로 차단되는지.

## 프론트 배포 (klow_web / klow_admin / klow_brand)

세 프론트는 서버가 실어 보내는 `customerPriceUsd`/`listPriceUsd` 를 직접 렌더한다(클라 재계산 없음).
서버 배포 후 순서 무관하게 배포 가능하나, 어드민/브랜드 입력 폼의 정산·마진 미리보기가 서버 정산가(floor)
와 일치하려면 이 릴리스의 `cost-pricing.ts` 수정본이 함께 나가야 한다.

## 롤백 주의

`basePriceUsd`/`priceLocal` 백필과 신 게이트는 짝이다. 신 서버를 구 서버로 롤백하면 구 게이트
(`salePrice>0`)로 돌아가므로 노출은 복구되지만, 그 사이 신 모델로 편집된 가격(basePriceUsd 기준)은
구 모델 표시와 어긋날 수 있다. 롤백은 가격 편집 트래픽이 적은 시간대에.
