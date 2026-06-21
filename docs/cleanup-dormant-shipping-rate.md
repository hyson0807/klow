# Follow-up: dormant 배송 요율 DB 드롭

제품 가격을 `ShippingCountry.productLogisticsCostKrw`/`productCarrier`로, 시딩 배송비를 `SeedingRate`(국가×무게)로
옮기면서 **구 무게×캐리어 요율 인프라의 코드는 전부 제거**했지만, 데이터 유실 위험을 피하려고 **DB 객체는 남겨뒀다**(dormant).
아래 객체들은 현재 어떤 코드에서도 읽지/쓰지 않는다.

## 운영 배포 완료 후 드롭 대상

- 테이블 **`ShippingRate`** (`carrier, iso2, weightG, rateKrw`)
- `ShippingCountry` 컬럼:
  - `efsRateKrw`, `emsRateKrw`, `dhlRateKrw` (구 2kg 미러 대표값)
  - `efsFuelSurchargePerKgKrw`, `emsSpecialFeePerKgKrw` (kg당 추가요금)

> `ShippingCountry.enabled` / `efsPartialExclusions` 와 `ShippingExclusion` 테이블은 **유지**
> (국가 설정 탭·제품/시딩 EFS 제외구역 차단에서 계속 사용).
> (구 `ShippingCountry.carriers` 컬럼은 별도 마이그레이션 `drop_shipping_country_carriers` 로 이미 제거됨.)

## 절차 (모든 환경 — dev/staging/prod — 배포가 끝난 뒤)

1. 위 객체를 읽는 코드가 없는지 재확인:
   `grep -rn "ShippingRate\|efsRateKrw\|emsRateKrw\|dhlRateKrw\|FuelSurcharge\|SpecialFee" klow_server/src klow_admin/src klow_web/src klow_brand/src`
2. `klow_server/prisma/schema.prisma`에서 `model ShippingRate` 블록과 위 컬럼 5개를 삭제.
3. `cd klow_server && npx prisma migrate dev --name drop_dormant_shipping_rate` (CLAUDE.md 규칙 — 사용자 직접 실행).
4. 운영은 `prisma migrate deploy`로 적용.

## 참고 — 이번 변경에서 함께 제거된 코드 (이미 완료)

- `klow_server/src/modules/shipping/rate-import/**` (엑셀 파서·writer·컨트롤러)
- `shipping.service.ts`의 `resolveRatesForWeight`/`loadCheapestRatePlanner`/`pickCheapestCarrier`/`pickTierRate`/`ratesByCarrier`/`upsertRate`/`deleteRate`
- `AdminShippingRatesController`, 공개 `rates/by-weight`/`:iso2.rates`
- 시드/생성 스크립트: `generate-shipping-rates`, `seed-shipping-rates(.ems/.dhl)`, `seed-shipping-surcharges` + `prisma/data/{efs,ems,dhl}_rates.json`·`*_surcharge*_by_iso2.json`
- 어드민 국가/캐리어 탭의 요율 매트릭스·추가요금·엑셀 업로드 (→ '국가 설정' 탭으로 축소)
