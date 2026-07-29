# efs-billing — EFS 배송비 브랜드 후청구

- **모듈 경로**: `src/modules/efs-billing/`
- **주 클라이언트**: `klow_admin` **배송비 청구** 탭(`/efs-billing`, **슈퍼관리자 전용**) +
  `klow_brand` 정산 **물류비 청구** 탭(전달받은 확정본 열람·다운로드).
- **데이터 모델**: `Shipment.{efsChargeKrw,efsChargeSource,efsChargeUpdatedAt}`(송장별 EFS 실비),
  `EfsBillingStatement`(브랜드×월 **동결** 청구서 스냅샷 + R2 xlsx), `ShippingCountry.efsBillingFeeKrw`(국가별 청구 수수료).

## 무엇을 하는 모듈인가

EFS(물류사)가 우리에게 청구한 **실제 배송비**를 송장별로 확정하고, 그 중 브랜드가 부담할 몫을
월별 청구서로 만들어 브랜드에게 전달(publish)한다. 돈의 방향이 정산(settlement)과 **반대**다 —
정산은 KLOW→브랜드(받을 돈), 이건 브랜드→KLOW(낼 돈).

## 대상 = 시딩 + 일반주문 (2026-07-29 통합)

EFS 정산표엔 **시딩과 일반주문 송장이 섞여** 온다. 이전엔 리포트가 `order.isSeeding=true` 로
하드코딩돼 있어 일반주문 HAWB 가 전부 `extraInFile` 로 잡혀 **업로드 적용이 막혔다**. 지금은 둘 다
받고 행마다 `kind`(`general`|`seeding`)로 구분한다.

### ⚠️ 청구 산식이 구분마다 다르다

| 구분 | 청구액 |
|---|---|
| 시딩 · 바이어 결제(`paymentBy='customer'`) | **청구 제외** — 바이어가 배송비를 이미 다 냈다 |
| 시딩 · 브랜드 결제 | `EFS실비 + 국가별 수수료` |
| 일반주문 | `max(0, EFS실비 + 수수료 − **고객 선결제**)` |

일반주문은 고객이 체크아웃에서 배송비(요율표 2kg 요율의 절반, 브랜드당 1회)를 **이미 선결제**했다.
빼지 않으면 이중청구가 된다. 무료배송(**배송지 국가별** — `ProductCountryPrice.freeShipping`)이면 선결제가
0 이라 자동으로 전액 청구되고, 실측이 선결제보다 싸면 0원(청구 없음)이 된다 — klow_brand 국가별 판매가
모달이 보여주는 "무료배송 vs 고객 부담" 부담액과 같은 규칙이다. **여기서 무료배송 플래그를 직접 읽지는
않는다** — 그 브랜드의 `perBrandShareUsd` 가 0 으로 스냅샷돼 있어 자동으로 전액이 된다.

- **고객 선결제액 정본**: `perBrandShareUsd`(`orders/chargeable-brands.ts`) → `Order.fxRateSnapshot` 로 KRW 환산.
  **송장 발급이 EFS 27번(배송비) 필드에 박는 값과 같은 함수**라 송장 == 청구서가 구조적으로 보장된다.
  스냅샷(`Order.shippingFeeByBrand`)이 없는 legacy 주문은 `총배송비 / 브랜드수` 균등분배로 폴백한다
  (2026-07-28 이전 주문 전부가 이 경로).
- ⚠️ `paymentBy` 는 **시딩 전용** 필드다. 일반주문은 `seedingLink` 가 없어 항상 `'brand'` 로 떨어지므로,
  바이어 결제 판정은 반드시 `kind === 'seeding'` 과 **함께** 봐야 한다.
- fx 스냅샷 결손 등으로 선결제액을 못 구하면 0 폴백(과청구) 대신 **'청구 보류'** 로 빼고 어드민에 노출한다.

## 월 버킷 = EFS 픽업 이벤트

그 달 EFS 정산표 집합과 맞추기 위해, 월 판정은 `Shipment.trackingEvents` 안의 **픽업 이벤트(코드 `03`)**
`at`(KST wall-clock 문자열) 프리픽스로 한다. 이 값은 JSON 안이라 DB 로 못 거르므로,
`submittedAt ∈ [월초 − 60일, 월말]`(픽업 ≥ 발송)로 **상위집합만 DB 에서 좁히고** 정확한 월은 JS 가 정한다.
(`Shipment.submittedAt` 인덱스는 아직 없다 — 현 볼륨에선 불필요, 증가하면 검토.)

## EFS 실비의 출처

`Shipment.efsChargeSource` 로 구분한다:
- `'excel'` — 정산표 업로드로 확정. **청구 근거**.
- `'manual'` — 어드민 수기 입력. **청구 근거**.
- `'api'` — 저장값이 없을 때 `getTrackStatus` 로 조회한 표시용 폴백. **청구 근거로 쓰지 않는다**(청구 불가로 뺀다).

## 정산표 업로드 파싱

`.xlsx`(5MB, `INVOICE` 시트 우선 없으면 첫 시트). **HAWB 컬럼은 결정적으로** 찾고
(`/^EFS\d+/i` 셀이 가장 많은 컬럼), **총배송비 컬럼만 OpenAI 가 추론**한 뒤 헤더 정규식
(`shipping charge|total|합계|…`)으로 덮어쓴다 — 포맷이 바뀌어도 견디되 오판은 결정적으로 보정.
매칭 키는 **HAWB**(`Shipment.efsTrackingNumber`)이고 refNo 는 쓰지 않는다.

`importPreview` 는 **파일 HAWB 집합 == 그 달 송장 집합**일 때만 `ok:true` 를 준다(개수·집합 불일치 시 적용 차단).
`importApply` 만 DB 에 쓴다(preview 는 저장하지 않음).

## 청구서 엑셀 (요약 + 구분별 시트)

`renderXlsx` 가 **요약 / 일반주문 / 시딩** 3시트를 만든다(해당 구분 행이 0건이면 그 시트는 생략, 요약은 항상).
- **요약**: 구분별 건수·EFS실비 합·수수료 합·선결제 차감·청구액 합 + 총계 + 청구 제외 사유별 건수.
- **일반주문**: `고객선결제` 열이 추가된다(음수로 표기 — 차감액임을 분명히).
- **시딩**: 기존 11열 유지(`인스타그램` 포함).

`buildStatement`(모듈 스코프 순수 함수)가 **청구가 단일 출처**라 export·publish 가 같은 값을 낸다.

## publish = 동결 스냅샷

"전달"하면 그 시점의 rows·합계·xlsx 를 `EfsBillingStatement` 에 동결하고(R2 업로드 + `@@unique([brandId,yearMonth])` upsert),
브랜드는 **이 확정본만** 본다. 이후 어드민이 `efsChargeKrw`/`efsBillingFeeKrw` 를 고쳐도 스냅샷은 불변 —
갱신은 **재전달**로만.

> **하위호환**: `rows` 는 동결 JSON 이라 2026-07-29 이전 발행분엔 `kind`·`prepaidKrw` 키가 **없다**.
> 읽는 쪽(브랜드 UI)은 `kind ?? 'seeding'` 으로 해석한다 — 그때는 전부 시딩이었으므로 정확하다.

## 관련 파일

`efs-billing.service.ts`(`monthlyReport`·`saveCharge`·`extractFromSettlement`·`importPreview/Apply`·
`feeResolver`·**`buildStatement`**·`renderXlsx`+시트 빌더·`exportExcel`·`publish`·`markPaid`·브랜드 열람),
`admin-efs-billing.controller.ts`. 선결제 share 는 `orders/chargeable-brands.ts` `perBrandShareUsd`,
EFS 조회는 `shipments/efs.client.ts`, 브랜드 열람 라우트는 `settlement/brand-settlement.controller.ts`.

## admin-efs-billing.controller.ts (`@Controller('admin/efs-billing')`)

> 전체 라우트 `AdminGuard` + **`SuperAdminGuard`**.

| Method | Path                                    | 기능                                                      |
|--------|-----------------------------------------|-----------------------------------------------------------|
| GET    | `/admin/efs-billing/report`             | `yearMonth`(+`brandId?`) 월별 리포트 — 시딩·일반 모두      |
| PATCH  | `/admin/efs-billing/charge`             | 송장 1건 EFS 실비 수기 저장/초기화(`null`=초기화)          |
| POST   | `/admin/efs-billing/import/preview`     | 정산표 .xlsx 파싱 → 현재값 대비 diff (저장 안 함)          |
| POST   | `/admin/efs-billing/import/apply`       | 선택 행 저장(`efsChargeSource='excel'`, 최대 2000건)       |
| POST   | `/admin/efs-billing/publish`            | 브랜드×월 청구서 동결(스냅샷 + R2 xlsx) → 브랜드 전달      |
| GET    | `/admin/efs-billing/published`          | 선택 브랜드×월 전달/납부 상태(배지·버튼용)                 |
| POST   | `/admin/efs-billing/mark-paid`          | 브랜드 납부 수령 확인 토글                                 |
| GET    | `/admin/efs-billing/export`             | 청구서 엑셀 스트리밍(요약/일반주문/시딩 시트)              |

## 브랜드 열람 (settlement 모듈 컨트롤러)

| Method | Path                                              | 기능                          |
|--------|---------------------------------------------------|-------------------------------|
| GET    | `/v1/brand/settlement/efs-statements`             | 전달받은 청구서 목록(최신월 순) |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth`  | 청구서 상세(동결 rows)         |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth/excel` | 동결 xlsx 재스트리밍(R2)  |

## 교차링크

[shipments](./shipments.md)(송장 발급·추적·EFS 27번 배송비 share) ·
[settlement](./settlement.md)(반대 방향 = 받을 돈) ·
[shipping](./shipping.md)(국가별 수수료 `efsBillingFeeKrw`·요율표) ·
[seeding](./seeding.md)(시딩 링크 `paymentBy`).
