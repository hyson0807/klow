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

`.xlsx`(5MB, `INVOICE` 시트 우선 없으면 첫 시트 — **2번째 시트 `EMS 관세` 는 같은 워크북 읽기에서
함께 파싱한다**, 위 관세 자동 반영 절 참조). **HAWB 컬럼은 결정적으로** 찾고
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

## 문서 2종 — 브랜드 발송용 PDF · 내부 대사용 엑셀

브랜드가 받는 문서와 어드민이 대사에 쓰는 문서를 **분리**했다(2026-09). 예전엔 내부 엑셀 하나를
브랜드에게 그대로 줬는데, 그 파일의 `HAWB`(EFS 내부 송장번호 — 브랜드가 조회할 곳이 없다)·
`EFS실비`·`수수료`·`배송비 정산분`이 브랜드에게는 설명이 필요한 열이었고, 특히 실비·수수료 분해는
"고객이 배송비를 냈는데 왜 또 청구하나"라는 문의를 키웠다.

### 브랜드 발송용 청구서 엑셀 (`statement-invoice.ts`)

시트 1장(`{브랜드} 청구서`). 행마다 **순번 · 송장번호(HAWB) · 날짜(픽업) · 목적지(ISO2) ·
서비스 · 청구중량 · EMS 정가 · KLOW 운송료 · 절감액**을 담고, 표 아래에 **수출신고비 ·
관세 라인 · 최종 청구금액 · 입금계좌**가 붙는다.

⚠️ **열 배치의 정본은 `statement-invoice.ts` 의 `COL` 상수 하나**다(+ 헤더 문구 `INVOICE_TABLE_HEAD`).
예전엔 `'A'`~`'H'` 가 파일 스무 곳 넘게 흩어져 있어서 열 하나를 옮기면 밴드가 표를 덮거나 합계가
엉뚱한 열에 찍히는 식으로 조용히 깨졌다. 회귀 스펙은 **헤더 배열을 문자 그대로 단언**해 배치가
말없이 바뀌는 것을 막고, 수식 단언은 `COL` 에서 파생해 열이 옮겨져도 썩지 않는다.

> **주문번호 → 송장번호·서비스 (2026-09)** — 브랜드는 청구서를 자기 스튜디오 **배송·시딩 화면**과
> 대조하는데 거기 보이는 식별자가 HAWB 다. 서비스 타입은 **EFS 회신 원문**(EMS·PREMIUM·EMSPREMIUM·
> EMSDTP·DHL·USCOS…)을 그대로 싣는다 — 우리가 이름을 지어내면 EFS 문서·추적 화면과 갈린다.
> ⚠️ `hawb`·`serviceType` 은 **원래부터 동결 스냅샷(`EfsStatementRow`)에 있던 키**라 과거 확정본을
> 다시 받아도 그대로 채워진다(백필·마이그레이션 없음). `serviceType` 만 nullable 이라 `—` 폴백.

> **왜 PDF 가 아니라 엑셀인가 (2026-09-07 전환)** — 종전 A4 PDF 는 `발송일·목적국·수취인·구분·청구액`
> 다섯 열뿐이라 **"KLOW 를 써서 얼마를 아꼈는가"에 답하지 못했다.** 그게 이 문서의 존재 이유이고,
> 그래서 서식 자체를 운영이 쓰던 참조 청구서(보라 헤드라인 + EMS 비교 3열)로 갈아탔다.
> `pdfmake`·번들 폰트 18MB(`src/assets/fonts/`)·`nest-cli.json` 의 `assets` 설정은 **전부 제거**했다 —
> 엑셀은 폰트를 임베드하지 않고 이름만 참조하기 때문이다.

**렌더러가 `exceljs` 인 이유** — 이 레포의 다른 엑셀은 전부 SheetJS(`xlsx@0.18`)로 만들지만
**커뮤니티 판은 셀 채움·폰트·테두리를 쓸 수 없다.** 브랜드 발송 문서는 그게 전부 필요하다.
반대로 아래 '내부 대사용 엑셀'은 스타일이 없어 SheetJS 그대로 둔다 — **두 라이브러리 병존은 의도된 것**이다.

- 순번은 동결 `seq` 가 아니라 **표에 실제로 찍힌 순서**(배열 인덱스+1)다 — 청구 불가 행을 걸러낸 뒤
  매기므로 **마지막 번호가 곧 청구 건수**가 되어 브랜드가 세지 않고 검산한다. `seq` 를 쓰면 중간이
  빈 번호가 나온다.
- **일괄 다운로드**(`export-invoice-all`)는 그 달 청구 내역이 있는 **전 브랜드**를 zip 으로 묶는다.
  브랜드마다 개별 파일이라 그대로 각자에게 전달할 수 있다(한 파일로 합치면 다시 쪼개야 한다).
  ⚠️ **월 리포트를 브랜드마다 다시 부르지 않는다** — `exportStatementInvoice` 를 N 번 부르면
  `monthlyReport` 가 N 번 돌고 **실비 미저장 송장의 EFS API 조회가 브랜드 수만큼 반복**된다.
  리포트를 한 번 뽑아 `brandId` 로 잘라 `buildStatement({rows, brandId, buyerPaidCount})` 에 넘긴다.
  확정본·부가 항목 조회도 각각 `findMany` 한 번이다. ⚠️ zip 안 파일명에 문서번호 꼬리를 붙인다 —
  브랜드명은 자유 입력이라 동명이 가능하고, 같은 이름이면 뒤가 앞을 덮는다. 압축은 `STORE`
  (xlsx 는 이미 zip 컨테이너다).
- ⚠️ **`billedKrw == null`(EFS 실비 미입력) 행은 표에서 뺀다.** 사유를 적을 `비고` 열이 없어 금액 칸이 빈
  행이 설명 없이 남는다. 빼면 `표 행 수 == 청구 건수`, `Σ 청구액 == 운송료 합계` 가 종이 위에서 그대로
  검산된다 — 그 건수는 안내 문구에 명시한다(회귀 잠금: `__tests__/statement-invoice.spec.ts`).
- ⚠️ 렌더러는 **계산을 하지 않는다.** 금액은 동결 `rows` / `buildStatement` 결과를 그대로 옮기고,
  유일한 산술이 `savedKrw = emsListKrw − billedKrw` 와 세 합계다.
- ⚠️ **저장하지 않고 다운로드 시점에 렌더**한다. 금액이 동결 JSON 에서 오므로 무결성은 유지되고,
  publish 때 구웠다면 그 이전에 전달된 달은 영영 옛 서식으로 남았을 것이다.
- ⚠️⚠️ **어드민 다운로드도 전달된 달은 동결 스냅샷으로 렌더**한다(`exportStatementInvoice`). 라이브로만
  뽑으면 전달 후 실비를 고쳤을 때 어드민이 메일로 보낸 문서와 브랜드가 보는 문서의 총액이 갈린다 —
  청구 사고다. 전달 전 검토는 `?source=live` 다. ⚠️ **문서에는 확정/미확정 표시가 없다**(2026-09-07 결정) —
  구분은 어드민 화면(버튼 툴팁·다운로드 토스트)이 하고, 브랜드는 전달된 청구서만 조회할 수 있어
  구조적으로 미확정 문서를 받지 않는다.
- 청구서 번호는 `KLOW-INV-{YYYYMM}-{brandId 뒤 6자}`. ⚠️ **`publishedAt` 을 섞지 않는다** — 재전달마다
  번호가 바뀌면 브랜드가 이전 문서를 지목할 수 없다.
- 입금계좌 상수는 `klow-company.ts`. 2026-09 에 `국민은행 84883700007474 / 웰킷 (WELKIT)` 으로 바꿨다.
  계좌가 바뀌면 과거 청구서를 다시 받았을 때도 새 값이 찍힌다 — "지금 입금할 곳"이 맞는 값이라 의도된
  동작이다. ⚠️ 코드 밖 문서인 **견적서(KLOW SERVICE QUOTATION) 서식도 같은 계좌인지 확인할 것.**

#### EMS 정가 · 절감액

`ShippingRate`(carrier=`EMS`, 어드민 **해외배송 비교요율** 탭)에서 그 **목적국 × 청구중량**으로
**올림 조회**한 공개 정가다. 조회는 `ShippingRateService.listRatesFor('EMS', keys)` 한 번(왕복 1회)이고,
`monthlyReport` 의 `attachEmsListPrices` 가 행에 붙인다.

- ⚠️⚠️ **없으면 `null` 이다 — 0 으로 폴백 금지.** 요율 미설정국(EMS 는 98/233개국)·최대 티어 초과·
  청구중량 미입력이 여기 해당한다. 0 을 넣으면 절감액이 음수로 뒤집혀 **"절감했다"는 문서가 손해를
  주장한다.** 그 행은 표에 `—` 로 남고 절감 합계·`comparedCount` 에서만 빠진다.
- ⚠️⚠️ **헤드라인 보조줄은 `emsComparedBilledKrw`(비교 가능했던 행의 운송료 합)와 비교한다.**
  전 행 합(`shippingTotalKrw`)으로 쓰면 EMS 정가가 없는 행이 한쪽에만 들어가, 실제로는 절감했는데
  `정가 336,850원 → KLOW 353,450원` 처럼 **더 비싸 보인다**. 불변식:
  `emsListKrw − emsComparedBilledKrw === savedTotalKrw`.
- ⚠️ **음수 절감(KLOW 운송료 > EMS 정가)을 0 으로 클램프하지 않는다** — 클램프하면
  `Σ절감 ≠ ΣEMS − ΣKLOW` 가 되어 표가 검산되지 않는다. 대신 3분기 숫자서식
  `"-"#,##0"원";"+"#,##0"원";"-"0"원"` 으로 `+N원`(초과)으로 표기한다. ⚠️ 참조 파일의
  `"-"#,##0"원"` 을 그대로 쓰면 **음수가 `-−12,000원` 으로 깨진다**(양수 앞에 리터럴 하이픈을 붙이는 서식).
- `comparedCount === 0` 이면 절감 헤드라인(3·4행)을 **아예 그리지 않고** 중립 제목으로 대체한다.
- ⚠️ 요율은 **이미 최종가**다 — `emsSpecialFeePerKgKrw`(dormant)를 더하지 말 것(이중 계상).
- ⚠️ `ShippingRate` 조회는 **반드시 `carrier` 를 where 에 넣는다**(`@@unique([carrier, iso2, weightG])`).
  회귀 잠금: `shipping/__tests__/shipping-rate-bulk.spec.ts`.

#### 수출신고비 (건당 300원)

정산표에 **수출신고번호가 있는 건**(`Shipment.efsExportDeclNo` / `EfsManualBillingRow.efsExportDeclNo`)
마다 `EXPORT_DECLARATION_FEE_KRW = 300` 을 청구한다. EFS 는 우리에게 **250원 + VAT** 를 청구하지만
브랜드에는 **VAT 없이 정액 300원**이다(국가별 청구 수수료와 같은 관례).

- ⚠️ 상수는 모듈 안에 둔다(env 금지 — 이 레포에 env 수치 상한이 0건이고 오타 하나가 조용히 청구를
  0원으로 만든다). klow_admin `src/lib/constants.ts` 의 `EXPORT_DECL_FEE_KRW` 는 **의도된 크로스 레포 미러**.
- ⚠️ **청구 가능한 행(`billedKrw != null`)에서만** 집계한다 — 실비 미입력이라 표에서 빠지는 행의 300원이
  총액에만 남으면 종이 위 검산이 깨진다.
- ⚠️ **`billedKrw` 에 포함하지 않는다.** 표 아래 별도 라인이고 `grandTotalKrw` 에만 더해진다
  (넣으면 `build-statement.spec.ts` 의 청구 산식 회귀 락이 깨지고 대시보드 KPI 가 조용히 부푼다).

#### 관세 대납 (`EfsBillingExtraCharge`)

송장 단위로 귀속되지 않는 브랜드×월 금액. **정산표 업로드가 자동 반영**하고(아래 절), 남는 건만 어드민
**관세·기타 청구** 모달에서 직접 넣는다(한 브랜드에 여러 건). 청구서에는 `관세 대납 · {메모}` 한 줄씩
찍히고 `grandTotalKrw` 에 합산된다.

- ⚠️ **송장 축과 별개 테이블이다** — 여기에 HAWB 를 두면 `mergeBillingRows` 의 dedupe 가 이 행까지
  집어삼켜 관세가 조용히 사라진다.
- ⚠️⚠️ **`paidBy`(선지급 주체: `efs` | `klow`)는 우리 장부용 축이고 청구서에 나가지 않는다.**
  `efs` = EFS 가 대납해 정산표 `EMS 관세` 시트로 우리에게 청구된 것 / `klow` = KLOW 가 직접 낸 것.
  브랜드 청구액은 주체와 **무관하게 같다**. 메모 문자열이 아니라 컬럼인 이유는, 문자열이면 오분류가
  어디서도 안 드러나는데 그 차이가 곧 "EFS 에 갚아야 할 돈"과 "이미 나간 우리 돈"의 구분이기 때문이다.
  구조적 차단: `InvoiceExtra` 타입에 `paidBy` 자리가 **아예 없다**(회귀 잠금: `__tests__/extra-charge.spec.ts`).
- ⚠️ 어드민 모달의 주체 셀렉트는 **기본값이 없다** — 주면 급히 입력할 때 전부 그 값으로 쌓여 축이
  무의미해진다.
- ⚠️ **수기로 넣은 행은 여전히 자동 매칭되지 않는다.** 자동 반영분은 `sourceRef` 로 멱등하지만
  (아래 절), 사람이 넣은 행은 그 키가 없어 같은 관세를 두 번 넣으면 두 번 청구된다. 방어선은
  ① 미리보기의 **수기 중복 의심** 배지(메모에 등기번호가 들어 있을 때만 잡히는 휴리스틱)
  ② 모달의 주체별 소계를 시트 합계와 눈으로 대조 ③ 메모에 등기번호 기재.
- ⚠️ **publish 는 `extras` 를 동결한다** — 전달 후 항목을 추가·수정해도 **재전달 전까지** 브랜드가 받는
  문서는 안 바뀐다. 어드민 모달이 그 경고를 띄운다.

#### 정산표 `EMS 관세` 시트 자동 반영 (2026-09)

정산표 업로드가 **2번째 시트까지** 읽어 관세를 브랜드별로 꽂는다. 종전엔 어드민이 금액과 등기번호를
손으로 옮겨 적었다.

- 시트 헤더 실측: `접수일자 | 등기번호 | 총관세결제금액 | 우편물 | 도착국 | 업체명`.
- ⚠️⚠️ **`업체명` 열은 브랜드가 아니다** — 전부 `welkit`(EFS 계정 명의 = 우리)이라 귀속 근거가 될 수
  없어 파서가 **읽지도 않는다**(읽는 코드가 있으면 언젠가 폴백으로 쓰인다). 귀속의 유일한 근거는
  **등기번호 = 현지 송장번호**다. 회귀 스펙이 "`업체명` 값이 결과 어디에도 없다"를 단언한다.
- **귀속 사다리** (`resolveCustomsPreview`):
  ① 파일 내 조인 `등기번호 → INVOICE 시트 Remarks(REF #) → HAWB → 그 달 리포트 행 → brandId`
  ② DB 폴백 `Shipment.localTrackingNumber` 일치
  ③ 실패 → `matchedBy:'none'`. **절대 자동 반영하지 않고** 어드민에게 금액과 함께 경고로 보여준다
  (브랜드를 추측하면 엉뚱한 브랜드에 관세가 청구되고, 그 사고는 "금액만 조금 다름"으로만 드러난다).
  ⚠️ ①이 먼저인 이유는 **같은 문서 안의 사실**이라 DB 상태와 무관하게 성립하기 때문이다(2026-08 실측 7/7).
  ⚠️ ②의 `localTrackingNumber` 는 **unique 가 아니다** — 2건 이상 걸리면 하나를 고르지 않고 미매칭이다.
  ⚠️ ①의 `등기번호 → HAWB` 맵도 충돌하면 엔트리를 **지운다**(추측 금지).
- **파싱은 결정적**이다 — `settlementSideColumns` 와 같은 이유로 **OpenAI 를 쓰지 않는다**
  (`customsSheetColumns` 헤더 정규식). 시트 선택은 시트명(`/관세|customs/`)이고 `INVOICE` 는
  **명시적으로 제외**한다 — 그 시트 푸터에 `EMS 관세 | 7 | 건` 이라는 **라벨 행**이 있다.
- ⚠️⚠️ **합계 행을 행 번호로 자르지 않는다.** 채택 조건이 *모양*(등기번호가 `^[A-Z0-9]{8,}$` 통과 +
  금액 > 0)이라, 실측 9행 `['','',107760,'','','']` 은 구조적으로 걸러져 `sheetTotalKrw`(검산값)로만
  들어간다. 이게 새면 시트 합계가 통째로 한 번 더 청구된다. 어드민 모달이 `읽은 합계 vs 시트 합계`
  를 나란히 띄우는 게 2차 방어선이다.
- ⚠️ 같은 등기번호가 여러 줄이면 **금액을 합산**한다 — last-wins 는 돈을 조용히 잃고, 별개 행은
  `sourceRef` unique 를 위반한다.
- ⚠️ 등기번호 형식을 `EG…KR` 로 못박지 않는다 — 실측 Remarks 열에 `UP900986735KR`,
  `GFUS01070348013060`, `363213610690` 이 함께 온다. 40자를 넘는 값은 **자르지 않고 버린다**
  (자르면 멱등 키가 깨진다).
- **멱등성**: `EfsBillingExtraCharge.sourceRef`(등기번호, `@unique`, nullable)를 키로 **upsert** 한다.
  같은 정산표를 다시 올려도 행이 늘지 않고, EFS 가 금액을 정정하면 따라간다(미리보기가
  `금액 정정 ₩old → ₩new` 로 먼저 보여준 뒤에만).
  ⚠️ **수기 행은 `sourceRef = null`** 이라 Postgres unique 가 무시한다 — 손으로 넣는 흐름은 무제약이다.
  ⚠️ 복합 unique(`[brandId, yearMonth, sourceRef]`)가 **아니다** — 그러면 같은 등기번호가 다른 달에
  한 번 더 들어가 이중청구가 된다.
  ⚠️ `ExtraChargeInput`·컨트롤러 `ExtraChargeBody`(수기 입력)에는 이 필드가 **없다** — 수기 행이 자동
  반영 키를 선점하면 그 달 자동 반영이 조용히 사라진다(회귀 잠금: `extra-charge.spec.ts`).
- `paidBy` 는 서버가 **`'efs'` 로 하드코딩**한다(이 시트에 실려 온 것이 곧 EFS 대납이다). 클라가 보낼
  자리가 없고, upsert 의 `update` 에서도 갱신하지 않는다(사람이 고쳐 둔 분류를 덮지 않는다).
- 메모(`관세 대납 · EG050851717KR · DE · 08-04`)는 서버 `customsMemo()` 가 만든다 — 클라가 조립하면
  재업로드 때 문자열이 갈려 수기 중복 탐지가 어긋나고, 브랜드 문서 문구를 클라가 정하게 된다.
- 귀속 월은 **어드민이 고른 달**이지 접수일자 파생이 아니다 — 그래야 관세가 그 운송료 행들과 **같은
  청구서**에 실린다. 접수일자가 다른 달이면 배지로만 알리고 **거르지 않는다**(거르면 돈이 사라진다).
- `importApply` 는 운송료 업데이트와 관세 upsert 를 **하나의 `$transaction`** 으로 처리하고, 브랜드
  존재는 **트랜잭션 밖에서** 먼저 검증한다(안에서 FK 가 터지면 운송료까지 롤백되고 원인 없는 500 이 된다).
- ⚠️ `ImportApplyBody.items` 의 `.min(1)` 이 빠지고 `refine`("둘 중 하나 이상")으로 옮겨갔다 —
  **관세만 반영하는 업로드가 정상 경로**다(실비가 이미 다 일치하는 재업로드).
- ⚠️ 어드민 모달의 관세 섹션은 **`preview.ok` 와 무관하게 렌더**한다. `ok` 는 "운송료 행이
  매칭됐는가"라서, 거기에 묶으면 실비가 다 맞는 재업로드에서 관세 반영이 **도달 불가**가 된다
  (적용 버튼을 `diffRows.length > 0` 으로 가렸다가 청구중량 백필이 막혔던 것과 같은 사고).
- 회귀 잠금: `__tests__/customs-sheet-parse.spec.ts`(파싱·합계행·중복·정규화),
  `__tests__/customs-import-apply.spec.ts`(멱등 upsert·귀속 사다리·트랜잭션).

#### 합계는 수식이다 — 받은 파일에서 금액을 고치면 따라 움직인다 (2026-09)

브랜드 청구서 xlsx 의 합계·최종 청구금액·행 절감액·절감 헤드라인이 **엑셀 수식**이다. 운영이
받은 파일에서 특정 건의 운송료를 고치면 아래가 전부 자동으로 다시 계산된다.

| 자리 | 수식 |
|---|---|
| 행 절감액 (H) | `IF(ISNUMBER(F13),F13-G13,"—")` |
| 합계 F·G·H | `SUM(F13:F{n})` 등 |
| 최종 청구금액 | `G{합계행}+SUM(G{부가라인 범위})` |
| 헤드라인 (3행) | `"{브랜드}님, … 총 "&TEXT(H{합계행},"#,##0")&"원을 절감하셨습니다"` |
| 보조줄 (4행) | `"EMS 공개 정가 "&TEXT(F{합계행},…)&"원  →  KLOW 청구 "&TEXT(SUMIF(F…,">0",G…),…)&"원"` |

- ⚠️⚠️ **수식은 표시 계층일 뿐이다.** 우리가 청구한 금액의 정본은 `buildStatement` 와
  `EfsBillingStatement` 동결 스냅샷이고, **다운로드한 파일을 고쳐도 청구액·정산·KPI 는 바뀌지
  않는다.** 고친 파일을 브랜드에 보내면 우리 장부와 갈린다 — 금액을 실제로 바꿔야 하면
  어드민 표에서 EFS 실비를 고치고 **재전달(publish)** 해야 한다.
- 모든 수식은 `result`(서버 계산값)를 함께 들고 나간다 — **편집 전에는 지금까지와 글자 하나까지
  같은 숫자**가 보이고, 고쳤을 때만 엑셀이 다시 계산한다. 회귀 스펙이 `result === 서버값` 을 잠근다.
- ⚠️ `wb.calcProperties.fullCalcOnLoad = true` 가 필요하다 — 없으면 뷰어에 따라 캐시된 값만 보이고
  편집해도 합계가 안 움직인다. ⚠️ exceljs **리더는 이 플래그를 되읽지 않으므로** 라운드트립으로
  검증하면 아무것도 못 잡는다(스펙이 zip 안 `workbook.xml` 을 직접 본다).
- ⚠️⚠️ **EMS 정가가 없는 행에 `F−G` 를 그냥 걸면 안 된다** — 절감액이 운송료만큼 **음수로 뒤집혀
  문서가 손해를 주장한다**. 그래서 `ISNUMBER` 가드가 수식 안에 있고, 표시값도 `—` 그대로다.
  (나중에 그 행의 정가를 손으로 채우면 그때부터 계산된다.)
- ⚠️ **비교 대상이 0건이면 F·H 합계와 헤드라인에 수식을 넣지 않는다** — `SUM` 이 0 을 돌려주면
  "0원을 절감하셨습니다"가 찍히는데, 그건 이 문서가 처음부터 피하려고 만든 표기다. 운송료
  합계(G)만 늘 수식이다.
- ⚠️ 헤드라인 보조줄은 **`SUMIF(F>0, G)`**(비교 가능한 행의 운송료 합)이지 G 합계가 아니다 —
  `F합계 − 이 값 = H합계` 라는 검산이 문서 안에서 성립해야 하기 때문이다(전 행 합을 쓰면
  실제로는 절감했는데 더 비싸 보인다 — 이 문서가 이미 한 번 밟은 함정이다).
- ⚠️ 브랜드명은 자유 입력이라 헤드라인 수식에 넣을 때 `"` 를 **두 번 써서 escape** 한다.
- 회귀 잠금: `__tests__/statement-invoice.spec.ts` 의 *'합계 자동 계산'* describe.
- 내부 대사용 엑셀(`renderXlsx`, SheetJS)은 **무변경**이다 — 그쪽은 대사용 원장이라 수식이 필요 없다.

### 내부 대사용 엑셀 (요약 + 구분별 시트)

⚠️ **브랜드에게 보내는 문서가 아니다.** 어드민 전용 보조 버튼이고, EFS 정산표와 대사할 때 실비·수수료·
배송비 정산분이 필요해서 남겼다. `publish` 도 이 파일을 R2 에 동결해 기록으로 남긴다(`excelKey`).

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
| GET    | `/admin/efs-billing/extra`              | 부가 청구 항목(관세 대납) 목록 — `yearMonth`+`brandId`     |
| POST   | `/admin/efs-billing/extra`              | 부가 청구 항목 등록 (`paidBy` 는 기본값 없는 필수값)        |
| PATCH  | `/admin/efs-billing/extra`              | 부가 청구 항목 수정                                        |
| DELETE | `/admin/efs-billing/extra`              | 부가 청구 항목 삭제 — ⚠️ **body 로 `id`**(수기 행과 같은 이유) |
| POST   | `/admin/efs-billing/import/preview`     | 정산표 .xlsx 파싱 → 현재값 대비 diff (저장 안 함)          |
| POST   | `/admin/efs-billing/import/apply`       | 선택 행 저장(`efsChargeSource='excel'`, 최대 2000건)       |
| POST   | `/admin/efs-billing/publish`            | 브랜드×월 청구서 동결(스냅샷 + R2 xlsx) → 브랜드 전달      |
| GET    | `/admin/efs-billing/published`          | 선택 브랜드×월 전달/납부 상태(배지·버튼용)                 |
| POST   | `/admin/efs-billing/mark-paid`          | 브랜드 납부 수령 확인 토글                                 |
| GET    | `/admin/efs-billing/export-invoice`     | **브랜드 발송용 청구서 엑셀**(전달된 달은 동결본, `source=live` 면 라이브) |
| GET    | `/admin/efs-billing/export-invoice-all` | 그 달 내역 있는 **전 브랜드** 청구서 엑셀을 zip 으로(브랜드 선택 불필요)   |
| GET    | `/admin/efs-billing/export`             | 내부 대사용 엑셀(요약/일반주문/시딩 시트) — 브랜드 발송용 아님 |

## 브랜드 열람 (settlement 모듈 컨트롤러)

| Method | Path                                              | 기능                          |
|--------|---------------------------------------------------|-------------------------------|
| GET    | `/v1/brand/settlement/efs-statements`             | 전달받은 청구서 목록(최신월 순) |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth`  | 청구서 상세(동결 rows)         |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth/invoice` | **청구서 엑셀**(동결 rows 에서 렌더) |

## 교차링크

[shipments](./shipments.md)(송장 발급·추적·EFS 27번 배송비 share) ·
[settlement](./settlement.md)(반대 방향 = 받을 돈) ·
[shipping](./shipping.md)(국가별 수수료 `efsBillingFeeKrw`·요율표) ·
[seeding](./seeding.md)(시딩 링크 `paymentBy`).
