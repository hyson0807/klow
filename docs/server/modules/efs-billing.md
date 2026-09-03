# efs-billing — EFS 배송비 브랜드 후청구

- **모듈 경로**: `src/modules/efs-billing/`
- **주 클라이언트**: `klow_admin` **배송비 청구** 탭(`/efs-billing`, **슈퍼관리자 전용**) +
  `klow_brand` 정산 **물류비 청구** 탭(전달받은 확정본 열람·다운로드).
- **데이터 모델**: `Shipment.{efsChargeKrw,efsChargeSource,efsChargeUpdatedAt}`(송장별 EFS 실비),
  `EfsBillingStatement`(브랜드×월 **동결** 청구서 스냅샷 + R2 xlsx), `ShippingCountry.efsBillingFeeKrw`(국가별 청구 수수료),
  **`EfsManualBillingRow`**(KLOW 밖에서 발급된 EFS 송장의 수기 청구 행 — 아래 별도 절).

## 무엇을 하는 모듈인가

EFS(물류사)가 우리에게 청구한 **실제 배송비**를 송장별로 확정하고, 그 중 브랜드가 부담할 몫을
월별 청구서로 만들어 브랜드에게 전달(publish)한다. 돈의 방향이 정산(settlement)과 **반대**다 —
정산은 KLOW→브랜드(받을 돈), 이건 브랜드→KLOW(낼 돈).

## 대상 = 시딩 + 일반주문 (2026-07-29 통합)

EFS 정산표엔 **시딩과 일반주문 송장이 섞여** 온다. 이전엔 리포트가 `order.isSeeding=true` 로
하드코딩돼 있어 일반주문 HAWB 가 전부 `extraInFile` 로 잡혀 **업로드 적용이 막혔다**. 지금은 둘 다
받고 행마다 `kind`(`general`|`seeding`)로 구분한다.

### 청구 산식은 하나다 — 실비 + 수수료 전액

| 구분 | 청구액 |
|---|---|
| 시딩 · 바이어 결제(`paymentBy='customer'`) | `EFS실비 + 국가별 수수료` |
| 시딩 · 브랜드 결제 | `EFS실비 + 국가별 수수료` |
| 일반주문 | `EFS실비 + 국가별 수수료` |

⚠️⚠️ **2026-09 전환 — 되돌리지 말 것.** 예전엔 산식이 셋이었다: 바이어 결제 시딩은 **청구 제외**,
일반주문은 **`max(0, 실비 + 수수료 − 고객 선결제)`**. 그 시절엔 고객이 낸 배송비를 KLOW 가
보유했으므로 브랜드 청구에서 빼 주는 게 맞았다. 지금은 **고객이 낸 배송비가 브랜드 정산으로 전액
지급된다**([settlement](./settlement.md)). 여기서 또 깎아 주면 KLOW 가 같은 돈을 두 번 잃는다.
요율표(고객 청구)와 EFS 실비의 차액은 이제 **브랜드 손익**이고, 적자가 이어지면 고칠 곳은 이 산식이
아니라 **배송비용 탭의 국가 요율표**다.

부수 효과: `coveredByPrepaidCount`(선결제가 실비를 덮어 0원 청구되던 행)이 사라지고, 월 청구 총액과
어드민 대시보드 **배송 청구액** KPI(`rangeChargeTotal` — 같은 `buildStatement` 를 탄다)가 계단처럼
오른다. 버그가 아니다.

- **`prepaidKrw`(= 이 건의 배송비로 **브랜드에 정산된 금액**)는 계속 계산해 행·소계·엑셀에 싣지만
  `billedKrw` 에는 넣지 않는다.** 남긴 이유는 어드민이 `Σprepaid − Σbilled` 로 "요율표가 실비를
  덮는가"(= 브랜드 손익)를 계속 볼 수 있어야 하기 때문이다.
  ⚠️⚠️ 값은 정산 지급액과 **같은 함수**(`shipments/shipment-settlement.ts` 의
  `brandShippingSettlementKrw`)로 구한다 — 여기서 `perBrandShareUsd × fx` 를 직접 하면 **PG 5% 만큼
  어긋나** 화면의 "브랜드 손익"이 늘 낙관적으로 나오고 손익분기 근처에서 부호가 뒤집힌다.
  2026-09 부터 **일반주문 전용이 아니라 전 구분 공통**이다(시딩 고객결제 건에도 값이 있다).
  ⚠️ 값을 못 구한 행(fx 스냅샷·분모 결손)은 어드민 칩 합계에 **0 으로 들어가** 손익이 실제보다
  적자로 보이므로, 옆에 `⚠ N건 미상` 을 함께 띄운다(실비 미입력을 0 으로 안 치는 것과 같은 규칙).
  ⚠️ 같은 행의 `buyerPaidKrw`(시딩 한정, 고객이 낸 **총액**)와 헷갈리지 말 것 — 어드민 표는
  `배송비 정산분`(net)과 `결제`(gross) 두 열로 나눠 보여준다.

> ⚠️⚠️ **정산과 청구는 월 버킷 기준이 다르다.** 정산은 `Order.paidAt`(결제월), 청구는 EFS
> **픽업 이벤트(코드 03)** 월이다. 그래서 `배송비 정산분 − 청구액` 은 **행 단위로는 정확하지만**
> (한 송장의 두 값이라), 브랜드가 "8월 정산금의 배송비"와 "8월 청구서"를 월 합계로 대조하면
> 결제월 ≠ 픽업월인 건만큼 어긋난다. 손익은 행/기간 누적으로 읽어야 한다.
  ⚠️ 회귀 잠금이 `__tests__/build-statement.spec.ts` 의 *"prepaidKrw 는 청구액에 영향을 주지 않는다"*
  describe 다 — 차감이 되살아나면 여기서 먼저 깨진다.
- ⚠️ **`perBrandShareUsd` 는 여전히 송장 발급의 EFS 27번(배송비) 필드 정본**이므로 함수 자체는 손대지
  않는다. 바뀐 건 두 번째 소비자가 여기(청구 차감)에서 [settlement](./settlement.md)(정산 지급)로
  옮겨간 것뿐이다. **양쪽에서 동시에 읽으면 이중 반영**이다.
- legacy 분모 `orderBrandCount` 는 짝인 `perBrandShareUsd` 와 같은 파일(`pricing/chargeable-brands.ts`)로
  **이관**했다(정산도 같은 분모를 쓴다). ⚠️ 그 **분모는 주문 라인의 브랜드 수**다 — 발급된 송장 수를
  쓰면 아직 안 나온 브랜드가 빠져 분모가 작아지고, 나머지 송장이 나오면 같은 주문의 분모가 달라진다.
- ⚠️ 선결제액을 못 구해도(**fx 스냅샷 결손·분모 미상**) 더 이상 **청구를 보류하지 않는다** — 청구가
  선결제에 의존하지 않기 때문이다. `missingCharge` 는 이제 **EFS 실비 미입력** 하나만 센다.
- **손익 축이 KLOW → 브랜드로 넘어갔다** *(2026-09)*. 예전엔 바이어 결제 시딩을 청구에서 빼는 대신
  행마다 `buyerGapKrw = 바이어 결제액 − EFS 실비`(= **KLOW 손익**)를 집계했다. 지금은 그 건도 청구되고
  고객이 낸 돈은 브랜드가 받으므로 **KLOW 손익 개념 자체가 없다**. 합계 축 `buyerPaidKrw`·`buyerCostKrw`·
  `buyerGapKrw`·`buyerGapMeasuredCount`·`coveredByPrepaidCount` 는 제거하고 `prepaidKrw`(고객 결제
  배송비 합) 하나로 대체했다 — 어드민 칩 **`└ 브랜드 손익 = Σ선결제 − Σ청구액`** 이 그 자리를 대신한다.
  ⚠️ 행의 `buyerGapKrw` **키는 남긴다** — `EfsBillingStatement.rows` 는 동결 JSON 이라 과거 확정본이
  이 필드를 갖고 있다. 새 행에는 항상 `null` 이 들어간다.
  ⚠️ `buyerPaidCount` 는 **DB 컬럼**(`EfsBillingStatement.buyerPaidCount`)이자 브랜드 요약 DTO 필드라
  계속 센다. 의미만 "청구 제외 건수" → "고객이 배송비를 낸 시딩 건수"(정보성)로 바뀌었다.
- ⚠️ `paymentBy` 는 **시딩 전용** 필드다. 일반주문은 `seedingLink` 가 없어 항상 `'brand'` 로 떨어지므로,
  바이어 결제 판정은 반드시 `kind === 'seeding'` 과 **함께** 봐야 한다(지금은 비고 문구에만 쓴다).

## 월 버킷 = EFS 픽업 이벤트

그 달 EFS 정산표 집합과 맞추기 위해, 월 판정은 `Shipment.trackingEvents` 안의 **픽업 이벤트(코드 `03`)**
`at`(KST wall-clock 문자열) 프리픽스로 한다. 이 값은 JSON 안이라 DB 로 못 거르므로,
`submittedAt ∈ [월초 − 60일, 월말]`(픽업 ≥ 발송)로 **상위집합만 DB 에서 좁히고** 정확한 월은 JS 가 정한다.
(`Shipment.submittedAt` 인덱스는 아직 없다 — 현 볼륨에선 불필요, 증가하면 검토.)

### 예외 — 대시보드 KPI 는 발급일로 자른다 (`rangeChargeTotal`, 2026-08-17)

어드민 대시보드의 **배송 청구액** 타일은 임의 기간(주 단위)을 조회해야 하는데 픽업월 귀속으론
그게 표현되지 않는다. 그래서 `rangeChargeTotal(start, endExclusive)` 는 **`Shipment.submittedAt`**
기준으로 자르고(`status <> cancelled`, `carrier <> DOMESTIC`), 수출량·수출매출 KPI 와 같은
모집단을 쓴다. `endExclusive: null` 이면 전 기간(누적).

⚠️ **따라서 KPI 합계와 발행된 월별 청구서 합계는 일치하지 않는다** — 기준일이 다르고 청구서는
publish 시점에 동결된다. 자릿수·부호가 맞는지만 대조할 것.

⚠️ 청구 공식 자체는 **`buildStatement` 를 그대로 태운다**(KPI 전용 산식을 새로 쓰면 대시보드
숫자와 실제 청구서가 갈라진다). 두 경로가 같은 `BILLING_SHIPMENT_SELECT` + `buildBillingRows` 를
공유하므로 한쪽만 필드를 늘리면 그쪽 금액만 조용히 달라진다는 점에 주의.

⚠️ **EFS live 조회를 하지 않는다**(빈 맵을 넘긴다). `buildStatement` 가 저장값만 청구 근거로 쓰므로
금액에 영향이 없고, 대시보드가 외부 API 를 때리면 EFS 장애가 대시보드 장애가 된다. 대신
**정산표 업로드 전 송장은 금액에서 빠지므로** `pendingChargeCount`(= `build.missingCharge`)를 함께
돌려주고 어드민 타일이 `⚠ 실비 미입력 N건 — 과소집계` 로 표시한다. 실측(2026-08-17 dev): 청구 대상
102건 중 **101건이 실비 미입력**이었다 — 이 경고가 없으면 팀이 미확정 숫자를 확정으로 제출한다.

## EFS 실비의 출처

`Shipment.efsChargeSource` 로 구분한다:
- `'excel'` — 정산표 업로드로 확정. **청구 근거**.
- `'manual'` — 어드민 수기 입력. **청구 근거**.
- `'api'` — 저장값이 없을 때 `getTrackStatus` 로 조회한 표시용 폴백. **청구 근거로 쓰지 않는다**(청구 불가로 뺀다).

## 정산표 업로드 파싱

`.xlsx`(5MB, `INVOICE` 시트 우선 없으면 첫 시트). **HAWB 컬럼은 결정적으로** 찾고
(`/^EFS\d+/i` 셀이 가장 많은 컬럼), **총배송비 컬럼만 OpenAI 가 추론**한 뒤 헤더 정규식
(`shipping charge|total|합계|…`)으로 덮어쓴다 — 포맷이 바뀌어도 견디되 오판은 결정적으로 보정.
매칭 키는 **HAWB**(`Shipment.efsTrackingNumber`)이고 refNo 는 쓰지 않는다. 모델은 `OPENAI_MODEL`(기본 `gpt-4o-mini`)이고, OpenAI 호출이 실패해도 던지지 않고 헤더 정규식 가드로 폴백한다 — 그마저 못 찾으면 400(`총 배송비 컬럼을 찾지 못했습니다`).

`importApply` 만 DB 에 쓴다(preview 는 저장하지 않음).

### 집합 불일치는 차단하지 않는다 (2026-08)

`importPreview` 는 **매칭된 송장이 1건이라도 있으면** `ok:true` 다(`matchedCount > 0`). 예전엔
**파일 HAWB 집합 == 그 달 송장 집합**을 요구했는데, 그러면 **우리 시스템 밖에서 수기 발급한 EFS 송장**이
정산표에 섞여 오는 순간(실제로 있다) 업로드 전체가 막혔다. 두 목록은 성격이 다르고 **둘 다 오염 위험이 없다**:

| 목록 | 뜻 | 처리 |
|---|---|---|
| `extraInFile` | 파일엔 있고 DB 엔 없음 — 수기 발급분 | **회색 정보 배너.** `importApply` 는 DB 행의 `shipmentId` 로만 쓰므로 아무 데도 안 닿는다. **수기 청구 행으로 등록하면 이 목록에서 빠진다**(아래 절) |
| `missingInFile` | DB 엔 있고 파일엔 없음 — 월 경계·미청구분 | **노란 경고 배너.** 그 송장만 값이 안 채워질 뿐 |

⚠️ `missingInFile`·`rows`·`monthCount` 는 **실제 송장 행만** 센다(`shipmentId != null`). 수기 행은
`importApply` 대상이 아니라 넣으면 "월 N건 vs 파일 M건"이 영원히 안 맞는다. 반대로 `monthHawbs`
(= `extraInFile` 판정 기준)에는 **수기 행도 포함**한다 — 그래야 등록한 HAWB 가 경고에서 사라진다.

## 수기 청구 행 (`EfsManualBillingRow`, 2026-08-17)

**KLOW 시스템 밖에서 발급된 EFS 송장**을 월별 청구서에 태운다. 위 `extraInFile` 로 경고만 뜨고
버려지던 건들이 대상이고, 어드민 **배송비 청구** 탭의 `수기 추가` 버튼 → 모달에서 입력한다
(브랜드·HAWB·픽업일자·구분·목적국·EFS 실비·수수료·메모).

**가짜 `Shipment` 를 만들지 않는 이유**: Shipment 는 `orderId`/`brandId` FK·`carrier`·
`efsServiceType`·`requestPayload` 가 전부 필수이고, 청구 파이프라인이 `efsTrackingNumber` + 픽업
이벤트(코드 `03`)에 의존해 **가짜 주문과 가짜 tracking 이벤트까지** 지어내야 한다.

**합류 지점은 두 곳뿐**이고 둘 다 `mergeBillingRows` → `buildStatement` 를 탄다. 청구가 단일
출처를 유지하므로 **엑셀·publish 동결본·대시보드 KPI 가 자동으로 따라온다**:
- `monthlyReport` — `chargedAt` 이 그 KST 월인 행 (정렬·`perBrand`·합계가 전부 병합 뒤에 있어
  수기 행만 있는 브랜드도 셀렉트·필터·엑셀·publish 에 그대로 잡힌다)
- `rangeChargeTotal` — `chargedAt ∈ [start, endExclusive)`

> **⚠️ `manualToBillingRow` 의 `efsChargeSource: 'manual'` 이 금액을 조용히 바꾼다.**
> 이 값이 아니면 `buildStatement` 가 청구 근거로 안 쓰고 금액이 0 이 된다.
> (같이 박히는 `prepaidKrw: 0` 은 2026-09 전에는 "선결제 미상 → 청구 보류" 분기를 피하려고
> **필수**였다. 지금은 선결제가 청구액에 영향을 주지 않아 그 값이 무의미하다 — 수기 행은
> KLOW 주문이 없어 고객 선결제 개념 자체가 없으므로 0 을 유지한다.)
> 회귀 잠금: `__tests__/build-statement.spec.ts`.

> **⚠️ 수수료는 행별 override 가 국가 기본값을 이긴다.** `buildStatement` 는
> `r.feeOverrideKrw ?? feeOf(r.country)` 를 쓴다 — **`??` 이지 `||` 가 아니다**(수수료 0원 지정이
> 국가 기본값 ₩1,000 으로 튄다). 기존 `EfsBillingRow.feeKrw` 는 `SeedingLink.feeKrw`(참고용)라
> **청구에 쓰이지 않는다** — 거기에 override 를 실으면 기존 시딩 청구액이 전부 바뀐다.

> **⚠️ HAWB 중복 = 이중청구. 3중 방어다.**
> ① `normalizeHawb`(trim+upper) — `efs1005…` 와 `EFS1005… ` 는 Postgres `@unique` 를 그대로
> 통과한다. 저장·조회·병합이 **모두** 이걸 지난다. ② `EfsManualBillingRow.hawb @unique`(수기 vs
> 수기) + `assertHawbFree` 의 `Shipment.efsTrackingNumber` 조회(수기 vs 실제 송장 — DB 제약이
> 테이블을 가로질러 못 건다). ③ **`mergeBillingRows` dedupe(같은 HAWB 는 송장 행이 이긴다)** —
> ②는 TOCTOU 라 이게 유일한 구조적 보장이다. 수기로 넣은 뒤 그 송장이 뒤늦게 KLOW 로 들어와도
> 청구서에 두 번 실리지 않는다.

> **⚠️ 기준일이 두 종류로 섞인다.** 월별 청구서에서 실제 송장은 **EFS 픽업 이벤트 월**,
> 수기 행은 **입력받은 `chargedAt`** 이다. 대시보드 KPI(`rangeChargeTotal`)에서는 실제 송장이
> `submittedAt`(발급일), 수기 행이 `chargedAt`(픽업일)이라 기간 경계에서 소폭 어긋난다.
> 수기 행에 발급일을 따로 받는 건 입력 부담만 늘고 정확도 이득이 없어 이대로 둔다.

> `chargedAt` 은 그 KST 달력일 00:00 의 UTC 인스턴트다. DTO 로 내릴 땐 반드시 `kstDateStr` 를
> 쓸 것 — `toISOString().slice(0,10)` 은 **하루 전 날짜**를 준다(KST 00:00 = UTC 전날 15:00).

엑셀은 코드 변경 없이 포함된다 — `EfsStatementRow` 를 그대로 렌더하므로 `비고` 열에
`수기 입력 · <메모>` 가 찍히고 요약 시트 소계·총계에 자동 합산된다. `수취인` 은 빈칸이다.

**알려진 갭**: 정산표 업로드로 **수기 행의 실비를 갱신하지는 않는다**(`importApply` 가
`Shipment.id` 로만 저장). 수기 행 금액이 정산표와 달라도 자동 대사되지 않으니 모달에서 고친다.
publish 이후 수기 행을 고쳐도 **동결본은 안 바뀐다**(기존 동작과 동일 — 재전달로만 갱신).

값이 **HAWB 키**로 들어가므로 다른 달 파일을 올려도 매칭된 송장에 채워지는 금액은 그 송장의 실비다.
그래서 남은 유일한 차단 사유는 "이 파일에 그 달 송장이 하나도 없다"(= 명백한 오파일)뿐이다.
⚠️ 집합 일치 검사로 되돌리지 말 것 — 수기 발급분이 있는 한 영구히 막힌다.

## 청구서 엑셀 (요약 + 구분별 시트)

`renderXlsx` 가 **요약 / 일반주문 / 시딩** 3시트를 만든다(해당 구분 행이 0건이면 그 시트는 생략, 요약은 항상).
- **요약**: 구분별 건수·EFS실비 합·수수료 합·**배송비 정산분(참고)**·청구액 합 + 총계 +
  청구 불가 사유별 건수. 고객이 배송비를 낸 시딩이 있으면 "그 금액은 브랜드 정산으로 지급되고
  물류 실비는 이 청구서로 별도 정산한다"는 안내 한 줄이 붙는다 — 없으면 브랜드가 "고객이 냈는데
  왜 또 청구하나"로 읽는다.
- **구분별 시트**: `배송비 정산분(참고)` 열은 **두 시트 공통**이다(2026-09 전에는 일반주문
  전용이었고 값도 음수였다 — 차감액이 아니므로 이제 양수). `시딩` 시트만 `인스타그램` 열이 있다.

`buildStatement`(모듈 스코프 순수 함수)가 **청구가 단일 출처**라 export·publish 가 같은 값을 낸다.

## publish = 동결 스냅샷

"전달"하면 그 시점의 rows·합계·xlsx 를 `EfsBillingStatement` 에 동결하고(R2 업로드 + `@@unique([brandId,yearMonth])` upsert),
브랜드는 **이 확정본만** 본다. 이후 어드민이 `efsChargeKrw`/`efsBillingFeeKrw` 를 고쳐도 스냅샷은 불변 —
갱신은 **재전달**로만. 동결되는 `count` 는 실제로 돈이 청구되는 행 수(`billableCount`)다.
오류는 모두 **400** — 그 달 청구 내역이 0건이면 `전달할 청구 내역이 없습니다.`, 아직 전달 안 된 브랜드×월에
`mark-paid`/브랜드 상세·엑셀을 부르면 `전달된 청구서가 없습니다.` (`published` 조회만 예외적으로
`{published:false, paidAt:null}` 로 응답).

> **하위호환**: `rows` 는 동결 JSON 이라 2026-07-29 이전 발행분엔 `kind`·`prepaidKrw` 키가 **없다**.
> 읽는 쪽(브랜드 UI)은 `kind ?? 'seeding'` 으로 해석한다 — 그때는 전부 시딩이었으므로 정확하다.
>
> ⚠️ **2026-09 이전 발행분은 옛 산식(선결제 차감 · 바이어 결제 제외)으로 동결돼 있다.** 그 달들은
> 정산이 새 산식으로 소급되므로 **KLOW 가 배송비를 이중 부담**한 상태로 남는다. 배포 전 발행
> 이력을 확인하고, 필요하면 재발행(`publish` 는 upsert 라 덮어쓴다)할 것. 브랜드가 이미 납부
> (`paidAt != null`)했다면 차액은 운영이 수동 처리한다.

## 관련 파일

`efs-billing.service.ts`(`monthlyReport`·**`rangeChargeTotal`**(대시보드 KPI)·`buildBillingRows`·`saveCharge`·**수기 행 CRUD**(`createManualRow`/`updateManualRow`/`deleteManualRow`/`assertHawbFree`)·**순수 헬퍼**(`normalizeHawb`/`kstPickupLabel`/`manualToBillingRow`/`mergeBillingRows`)·`extractFromSettlement`·`importPreview/Apply`·
`feeResolver`·**`buildStatement`**·`renderXlsx`+시트 빌더·`exportExcel`·`publish`·`markPaid`·브랜드 열람),
`admin-efs-billing.controller.ts`. 고객 결제 배송비(참고값) share 는 `pricing/chargeable-brands.ts`
`perBrandShareUsd` + `orderBrandCount` — ⚠️ 그 함수는 **송장 EFS 27번**과 **브랜드 정산 지급액**
([settlement](./settlement.md))의 정본이기도 하다. 청구에서 다시 차감하면 이중 반영이다.
EFS 조회는 `shipments/efs.client.ts`, 브랜드 열람 라우트는 `settlement/brand-settlement.controller.ts`.

## admin-efs-billing.controller.ts (`@Controller('admin/efs-billing')`)

> 전체 라우트 `AdminGuard` + **`SuperAdminGuard`**.

| Method | Path                                    | 기능                                                      |
|--------|-----------------------------------------|-----------------------------------------------------------|
| GET    | `/admin/efs-billing/report`             | `yearMonth`(+`brandId?`) 월별 리포트 — 시딩·일반 모두      |
| PATCH  | `/admin/efs-billing/charge`             | 송장 1건 EFS 실비 수기 저장/초기화(`null`=초기화)          |
| POST   | `/admin/efs-billing/manual`             | **수기 청구 행 등록**(KLOW 밖 발급 송장)                   |
| PATCH  | `/admin/efs-billing/manual`             | 수기 청구 행 수정                                          |
| DELETE | `/admin/efs-billing/manual`             | 수기 청구 행 삭제 — ⚠️ **body 로 `id`**(감사 로그가 `req.body` 만 남긴다) |
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
