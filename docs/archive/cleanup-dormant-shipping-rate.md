# Follow-up: dormant 배송 요율 DB 드롭

> **📦 보관 문서 (2026-06-23 완료):** 드롭 마이그레이션(`20260623032631_drop_dormant_shipping_rate`)까지
> 실행 완료된 일회성 정리 노트. 현행 배송/가격 모델은 [`../pricing-model.md`](../pricing-model.md) 와
> [`../server/modules/shipping.md`](../server/modules/shipping.md) 참고.

제품 가격을 `ShippingCountry.productLogisticsCostKrw`/`productCarrier`로, 시딩 배송비를 `SeedingRate`(국가×무게)로
옮기면서 **구 무게×캐리어 요율 인프라의 제품 경로 코드는 전부 제거**했지만, 데이터 유실 위험을 피하려고 **일부 DB 객체는 남겨뒀다**(dormant).
아래 객체들은 현재 어떤 코드에서도 읽지/쓰지 않는다.

> **정정 (2026-06):** `ShippingRate` 테이블과 `ShippingCountry.emsSpecialFeePerKgKrw` 는 **더 이상 dormant 가 아니다** —
> 시딩 EMS/DHL **비교가** 산정에 재사용 중이다 (`klow_server/src/modules/seeding/shipping-rate.service.ts`,
> `admin-shipping-rate.controller.ts`, `brand-seeding.controller.ts`, `common/validation.ts`). 드롭 대상에서 제외한다.

## 드롭 완료 (2026-06-23)

- `ShippingCountry` 컬럼 4개 드롭됨 — 마이그레이션 `20260623032631_drop_dormant_shipping_rate`:
  - `efsRateKrw`, `emsRateKrw`, `dhlRateKrw` (구 2kg 미러 대표값)
  - `efsFuelSurchargePerKgKrw` (구 EFS 유류할증료, kg당)
- dev 적용 완료. **운영은 배포 시 `prisma migrate deploy` 로 자동 적용된다.**

> **유지** 대상 (드롭 안 함):
> - 테이블 `ShippingRate` + 컬럼 `emsSpecialFeePerKgKrw` — 시딩 비교가에서 사용 중 (위 정정 참고).
> - `ShippingCountry.enabled` / `efsPartialExclusions` 와 `ShippingExclusion` 테이블 — 국가 설정 탭·제품/시딩 EFS 제외구역 차단에서 계속 사용.
> - (구 `ShippingCountry.carriers` 컬럼은 별도 마이그레이션 `drop_shipping_country_carriers` 로 이미 제거됨.)

## 참고 — 이번 변경에서 함께 제거된 코드 (이미 완료)

- `klow_server/src/modules/shipping/rate-import/**` (엑셀 파서·writer·컨트롤러)
- `shipping.service.ts`의 `resolveRatesForWeight`/`loadCheapestRatePlanner`/`pickCheapestCarrier`/`pickTierRate`/`ratesByCarrier`/`upsertRate`/`deleteRate`
- `AdminShippingRatesController`, 공개 `rates/by-weight`/`:iso2.rates`
- 시드/생성 스크립트: `generate-shipping-rates`, `seed-shipping-rates(.ems/.dhl)`, `seed-shipping-surcharges` + `prisma/data/{efs,ems,dhl}_rates.json`·`*_surcharge*_by_iso2.json`
- 어드민 국가/캐리어 탭의 요율 매트릭스·추가요금·엑셀 업로드 (→ '국가 설정' 탭으로 축소)
- (2026-06) dormant 미러 컬럼 전용 시드 데이터 `prisma/data/{efs,ems,dhl}_rate_by_iso2.json` 삭제 (어느 seed 스크립트도 미참조)
- (2026-06) 데드 함수 `klow_server/src/common/reserved-slugs.ts` `isReservedBrandSlug()` 삭제 (호출처 0, 사용처는 `RESERVED_BRAND_SLUGS.has(...)` 직접 호출), 미사용 npm 패키지 `qrcode`/`@types/qrcode` 제거
