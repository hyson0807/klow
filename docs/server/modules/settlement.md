# settlement — 브랜드 매출 정산

- **모듈 경로**: `src/modules/settlement/`
- **주 클라이언트**: `klow_brand`(정산 탭 — 발송 이후 송장 원장·현장결제 라인·EFS 청구서), `klow_admin`(정산 처리 — 월별 후보 집계·월별 롤업·정산 확정).
- **데이터 모델**: 정산은 **송장(`Shipment`) 단위**로 마킹한다. 정산 상태는 `Shipment.settledAt`(정산 시각)·`Shipment.settledById`(처리한 어드민) 두 컬럼으로 표현하고, 금액은 **제품 정산가(`Shipment.items[].orderItem.settlementPriceKrw × quantity`) + 고객이 결제한 배송비의 브랜드 몫**을 합산해 산출한다(아래 배송비 이관 항목). 별도 `Settlement` 테이블 없이 송장에 직접 마킹하는 구조. 정산 단위 키는 `(orderId, brandId, shipmentId)` — 한 브랜드 = 한 송장이므로 송장 1장이 곧 정산 1건.
- **현장결제(onsite)는 Order 단위 정산**: `Order.channel='onsite'` 주문은 배송이 없어 `Shipment` 자체가 없으므로, 정산 상태를 `Order.settledAt`/`settledById`/`settledMonth`(KST `YYYY-MM` 라벨) 에 직접 마킹한다. 브랜드 귀속은 `OrderItem.productId → Product.brandId`(OrderItem 에 product 관계가 없어 별도 조회) 로 풀고, 멀티브랜드 주문이어도 자기 브랜드 라인만 합산한다. 월 버킷 기준은 `Order.paidAt` 이고, 2026-09 부터는 **송장 축도 같은 기준**이라 두 축이 통일됐다(아래 인식 시점 항목). 브랜드 정산탭이 송장 라인과 현장결제 라인을 같은 카드로 렌더하도록 서버가 `SettlementLineDTO`(`kind:'shipment'|'onsite'`, `settlementKrw`, `status`, `activityIso` 등)로 통일해 내려준다.
- **라인의 제품별 내역(`items`)**: 카드는 접힌 상태에서 `itemsLabel`(`"A 외 2건"`) 한 줄만 보이고, 2건 이상이면 펼쳐서 제품명 × 수량 × 정산액(`SettlementLineItemDTO`)을 보여준다. **배송비는 접힌 상태에서 금액 아래 `제품 ₩X · 배송 ₩Y` 보조줄로 항상 보이고, 펼친 목록에는 넣지 않는다** — 넣으면 같은 숫자를 두 번 그리고 1건짜리 라인에 토글이 생긴다. ⚠️ 배송비는 이 배열에 **넣지 않는다** — 제품별 내역이고 `itemsLabel` 이 **행 수로 "외 N건"을 세기 때문에** 한 행이 끼면 라벨이 어긋난다(브랜드 `settlementItems` / 어드민 `shipmentDisplayLines` 양쪽). 불변식은 **`Σitems == settlementKrw − shippingKrw`** 다(제품 성분은 뺄셈으로 파생한다 — 필드를 하나 더 두면 "제품 성분을 구하는 법"이 화면마다 갈린다). 송장 라인은 `GET /delivered` 응답의 `items[].orderItem`(`SHIPMENT_INCLUDE`)에 이미 전량 실려 있어 **클라가 그대로 펼친다**(서버 무변경). 현장결제만 `orderToOnsiteLine` 이 조회해 둔 필드를 라벨로 뭉개고 있어 `SettlementLineDTO.items` 로 함께 내려준다 — 항목 정산액은 `settlementPriceKrw × quantity` 라 **합이 `settlementKrw` 와 일치**한다. ⚠️ 이 배열은 조회 `where` 에서 이미 자기 브랜드 제품만 걸러진 것이라 멀티브랜드 현장 주문에서도 남의 제품이 새지 않는다.
- **정산 대상 필터 (settleable)**: **고객이 1원이라도 낸 주문**이 대상이다 — 무가 시딩(브랜드가 배송비를 내고 고객 결제액이 0)만 제외하고, 브랜드가 물품가를 청구한 시딩(`OrderItem.settlementPriceKrw > 0`)과 **물품가 없이 배송비만 받은 고객결제 시딩(`Order.shippingFeeUsd > 0`)** 은 **포함**한다. 또한 `paymentStatus=paid` + `status != 'cancelled'` 를 강제한다 — 환불은 `Order` 만 `refunded` 로 전이시켜 `Shipment` 쪽 상태가 그대로 남고, 시딩 송장 취소는 `Order.status='cancelled'` 로만 가면서 `paymentStatus` 를 `paid` 로 남기기 때문이다. 여기서 빼 브랜드 과지급을 막는다. 필터 정의는 이렇게 공유한다:
  - `SETTLEABLE_ORDER_WHERE = { paymentStatus: 'paid', status: { not: 'cancelled' }, OR: [{ isSeeding: false }, { items: { some: { settlementPriceKrw: { gt: 0 } } } }, { shippingFeeUsd: { gt: 0 } }] }` — Order 직접 필터. ⚠️⚠️ **세 번째 항을 빼면 안 된다** — 브랜드가 발급 시 "물품 가격"을 비워 둔 고객결제 시딩(전액 배송비, 프로덕션 실측 21건)이 정산 화면에서 **통째로 사라진다**. 산식만 바꾸고 이 항을 안 넣으면 "금액은 맞는데 행이 없는" 조용한 실패가 되고, 어드민 주문 목록이 `전액 배송비` 경고로 표시하던 건들이 정확히 이 케이스다. 무가 시딩은 `totalUsd`·`shippingFeeUsd` 가 둘 다 0 이라 계속 제외된다.
  - `settleableShipmentWhere(range?)` — Shipment 필터 **팩토리**. `{ status: { not: 'cancelled' }, order: { ...SETTLEABLE_ORDER_WHERE, paidAt: { gte, lt } } }` 를 만든다. ⚠️ 상수를 스프레드로 합치지 않고 팩토리로 둔 이유는 `{ ...상수, order: { paidAt } }` 가 `order` 키를 통째로 덮어 settleable 게이트를 지워 버리기 때문이다(embed 모듈이 `PUBLIC_PRODUCT_WHERE` 를 스프레드로 합쳤다가 겪은 것과 같은 사고 유형). ⚠️ 송장 조건이 `status: 'submitted'` 가 아니라 `{ not: 'cancelled' }` 인 것은, 발급 실패(`failed`)나 고아(`pending`) 송장에 묶인 매출이 조용히 사라지지 않게 하기 위해서다. `(orderId, brandId)` 당 취소 아닌 송장은 정확히 1장이라(재발급이 구 송장을 `cancelled` 로 돌린다) 이중 라인은 생기지 않는다.
  - `ONSITE_SETTLEABLE_WHERE = { channel: 'onsite', paymentStatus: 'paid', settledAt: null }` — 현장결제 전용(Shipment 가 없어 Order 로 판정).
  - **모든 read(목록·후보·월별 롤업) 와 실제 정산 write(settle) 가 같은 정의를 강제**한다. settle 의 `updateMany.where` 에도 같은 팩토리를 넣어, 시딩 송장이 후보에 안 떠도 마킹 단계에서 한 번 더 막아 ₩0 정산 누수를 차단한다.
- **⚠️⚠️ 고객이 낸 배송비가 브랜드 정산에 포함된다** *(2026-09 전환)*: 고객이 체크아웃·시딩 신청에서 내는 배송비는 **KLOW 요율표**(`SeedingRate` 500g 티어)가 정한 값이지 EFS 실비가 아니다. 예전엔 KLOW 가 그 선결제를 보유하고 [efs-billing](./efs-billing.md) 청구서에서 브랜드 부담을 그만큼 깎아 줬는데(`max(0, 실비 + 수수료 − 선결제)`), 지금은 **선결제 전액을 브랜드 정산으로 지급하고 EFS 실비 + 수수료를 전액 청구**한다. 요율표와 실비의 차액은 브랜드 손익이다.
  - **산식**: `settlementShippingKrw = floor(perBrandShareUsd(order, brandId, brandCount) × fxRateSnapshot × 0.95)`. 제품 정산가와 **같은 기준**(주문 시점 환율 · PG 5% 차감 · floor)이다 — 한 송장 안에서 두 성분의 수수료 기준이 다르면 브랜드가 자기 정산액을 설명할 수 없다. 단일 출처는 `shipments/shipment-settlement.ts` 의 `brandShippingSettlementKrw`.
  - ⚠️ **`perBrandShareUsd`(`pricing/chargeable-brands.ts`)의 소비처가 바뀌었다.** 그 함수는 여전히 **EFS 송장 27번 필드**에 박히는 값이므로 시그니처·동작을 건드리면 안 된다. 바뀐 건 두 번째 소비자가 "청구서의 선결제 차감"에서 "정산 지급액"으로 옮겨간 것뿐이다. **양쪽에서 동시에 읽으면 같은 배송비를 주고 + 깎아 주는 이중 반영**이 된다.
  - ⚠️ legacy 분모(`orderBrandCount`, 스냅샷 없는 주문의 균등분배)는 efs-billing 에서 `pricing/chargeable-brands.ts` 로 **이관**했다(짝인 `perBrandShareUsd` 와 같은 파일). **시딩 주문은 `shippingFeeByBrand` 스냅샷을 절대 남기지 않으므로 항상 이 폴백 경로**를 타는데, 시딩 `OrderItem` 이 `productId: null` + `brandId` 스냅샷이라 분모가 정확히 1 이 된다 — `brandId` 가지를 빠뜨린 분모 구현을 쓰면 시딩 배송비가 통째로 0 이 된다.
  - ⚠️ **`fxRateSnapshot` 이 없으면 배송비만 0 으로 두고 라인은 살린다**(`settlementShippingUnknown: true` → 어드민 amber 경고). efs-billing 의 '청구 보류'와 **정반대 방향이 맞다**: 저쪽은 모르면 안 받는 게 안전하지만, 이쪽은 모르면 안 주는 게 위험하다. 제품 정산가는 이미 동결된 KRW 라 fx 와 무관한데 라인을 빼면 멀쩡한 제품 정산금까지 화면에서 사라진다. **라이브 환율 폴백도 금지** — 지급 근거가 조회 시점마다 달라진다.
  - ⚠️⚠️ 금액은 **`(orderId, brandId)` 당 한 번만** 가산한다(`loadShippingSettlements` 의 `claimed` Set). 배송비는 박스 단위라, 같은 짝에 취소 아닌 송장이 2장 있으면 송장 단위로 더하는 순간 고객이 낸 적 없는 돈이 지급된다. 지금은 그런 짝이 없어야 정상이지만, 돈이 나가는 경로라 데이터가 어긋나도 **조용히 과지급하지 않는** 쪽으로 fail-safe 를 뒀다.
  - ⚠️ **서버가 계산해 파생 필드로 내려준다** — 송장 축은 raw Prisma 행을 반환하므로 `settlementShippingKrw`/`settlementShippingUnknown` 을 map 으로 얹는다. 클라 미러(`klow_admin/lib/api/shipments.ts`, `klow_brand/lib/api-types.ts`)에 **재료(`order.shippingFeeUsd`/`shippingFeeByBrand`)를 선언하지 말 것** — 선언하는 순간 두 프론트가 legacy 균등분배·fx 폴백 규칙을 각자 베끼고, 세 벌이 되면 반드시 갈린다. 그래서 `SHIPMENT_INCLUDE` 도 넓히지 않고 정산 전용 `SETTLEMENT_SHIPMENT_INCLUDE` 를 따로 뒀다.
  - ⚠️ **배송현황 화면도 같은 값을 본다** — `shipments.service` 의 `listPendingForBrand`/`listConfirmedForBrand` 도 같은 헬퍼를 타므로 klow_brand `baseView` 의 "정산 ₩X" 가 정산탭과 일치한다. 한쪽만 제품가로 되돌리면 같은 송장이 두 화면에서 다른 금액이 된다.
  - **현장결제(onsite)는 무변경** — `Order.shippingFeeUsd` 가 구조적으로 0 이다(부스 직접 전달).
  - ⚠️ **주문 목록의 합계와 정산액은 같은 수가 아니다.** 주문 목록은 `Order.totalUsd`(USD 센트,
    PG 청구액 그대로)이고 정산액은 그걸 주문 시점 환율로 환산하고 **PG 5% 를 뺀 KRW** 다
    (`정산 ≈ totalUsd × fx × 0.95`, 성분별 floor 라 원 단위 오차). 멀티브랜드 주문은 거기서 다시
    **그 브랜드 몫만** 잡히므로 주문 합계와 대조하면 안 된다. `SettlementLineDTO.totalUsd` 에
    `// USD 센트 (표시용 — KRW 와 합산 금지)` 주석이 붙어 있는 이유다.
  - ⚠️ 브랜드 **배송현황** 카드는 시딩을 무조건 "무료 시딩"으로 표시하면 안 된다 — 고객 결제
    시딩은 그 배송비가 정산액이 되므로 정산탭엔 금액이 뜨는데 배송 탭만 "무료"가 된다.
    판정은 `isSeeding` 이 아니라 **`freeSeeding`(= `isSeeding && 정산액 === 0`)** 이다
    (`klow_brand/src/components/shipping/shipping.model.ts` 의 `baseView`).
  - **마이그레이션·백필 없음.** 정산이 금액 스냅샷을 남기지 않아(`settle()` 은 `settledAt` 만 찍는다) 산식 변경이 **전 기간에 소급**된다 — 정산 실행 이력이 0건이라 안전하다.
  - 회귀 잠금: `settlement/__tests__/settlement-recognition.spec.ts`(배송비 가산·PG 5%·물품가 0 시딩 편입·무가 시딩 제외 유지·fx 결손 폴백·legacy 균등분배).
- **⚠️ 인식 시점 = 결제완료(`Order.paidAt`)** *(2026-09 전환)*: 예전에는 `Shipment.latestStatusCode === '33'`(EFS 배송완료)인 송장만 정산 후보가 됐고 월 버킷도 `latestStatusAt` 이었다. 그래서 **EFS 픽업 전(`'01'` 배송 예약)에 멈춘 송장에 묶인 매출이 어드민·브랜드 어느 화면에도 뜨지 않았다** — 실측으로 한 브랜드에서 ₩1,510,506 이 10~16일간 그렇게 숨어 있었다(고객이 결제를 마친 유료 시딩 3건). 지금은 결제만 완료되면 후보에 뜨고, 월 버킷·정렬도 `order.paidAt` 이다. 현장결제(onsite)가 원래 `paidAt` 기준이라 이 전환으로 두 축이 통일됐다.
  - **배송 상태는 게이트가 아니라 표시**다. 어드민 브랜드 상세는 `배송` 열(`latestStatusCode` → `lib/tracking-status.ts`)에서, 브랜드 정산탭은 `정산 예정 · 배송 중` 배지로 구분만 하고 **금액은 양쪽 다 받을 금액에 합산**한다. 지급 시점 판단은 어드민이 그 열을 보고 한다.
  - ⚠️ **배송완료 코드 조건이 취소 주문/송장을 막던 유일한 암묵적 방어막이었다.** 그 자리를 `Order.status != 'cancelled'` 와 `Shipment.status != 'cancelled'` 두 축이 명시적으로 대신한다 — 둘 중 하나라도 빼면 취소된 건이 정산 후보에 새고, 증상은 "금액만 틀린" 조용한 형태다.
  - 곁들여 해소된 잠재 버그: 시스템 전체는 `EFS_DELIVERED_CODES = ['33','47','74']`(efs.client.ts)를 쓰는데 정산만 `'33'` 단독이라 **47(수취인 수거)·74(종료 처리)로 끝난 송장이 영원히 정산되지 않았다.** 게이트에서 코드를 없애면서 함께 사라졌다(표시용 코드 집합은 klow_brand 가 3개 전부 미러한다).
  - 회귀 잠금: `settlement/__tests__/settlement-recognition.spec.ts`(배송 미완료 포함·무가 시딩 제외·취소 2축·결제월 버킷·정렬 기준·settle write).
- **KST(UTC+9) 기준 시간 처리**: 월 경계는 `src/common/kst-time.ts` 의 `parseKstYearMonth`/`previousKstYearMonth` 로 KST 기준 산출한다. 어드민 조회 `yearMonth` 는 `YYYY-MM` 형식이고 형식이 어긋나면 400(`yearMonth는 YYYY-MM 형식이어야 합니다`), 미지정 시 `previousKstYearMonth()` = 직전월 — 매월 15일 어드민이 직전월 결제분을 일괄 정산하는 운영 흐름. 모듈 로컬 `KST_OFFSET_MS = 9h` 는 `settle` 이 현장결제 주문에 찍는 `settledMonth`(KST `YYYY-MM`) 산출에 쓴다.
- **정산 확정(settle) 액션**: 한 트랜잭션에서 **송장(`shipmentIds`)과 현장결제 주문(`orderIds`)을 함께** `settledAt=now`·`settledById=adminId` 마킹한다(둘 다 비면 400 `정산할 대상을 선택하세요`). 송장 `where` 에는 `brandId` + `settledAt=null` + settleable(`settleableShipmentWhere()`) 을, 현장결제 `where` 에는 `channel='onsite'` + `paymentStatus=paid` + `settledAt=null` 을 강제하고, 각각 `updateMany.count` 가 요청 개수와 다르면 400 으로 롤백 — 부분 마킹을 방지한다("일부 송장이 정산 대상이 아닙니다" / "일부 현장결제 주문이 정산 대상이 아닙니다"). ⚠️ **배송완료를 요구하지 않는다** — 결제완료가 인식 시점이고, 배송 전 지급 여부는 운영 판단이라 화면의 배송 열로 넘긴다. 현장결제 주문에는 `settledMonth`(KST `YYYY-MM`)도 함께 찍는다. 응답은 `{ settledCount, onsiteSettledCount, settledAt }`. (참고: 정산 *사유/reason* 은 `SettleBody`(`brandId`/`shipmentIds`/`orderIds`) 에 없으며, 기록 필드는 `adminId`·`settledAt` 이다.)
- **브랜드 정산탭 조회**: 요약(summary) 엔드포인트는 없다 — 브랜드 화면이 원장 3종을 직접 받아 집계한다. `listDeliveredForBrand`(`GET /delivered`)는 **결제완료 주문의 그 브랜드 송장 전부**(settleable · 취소 제외)를 발송대기·배송중·배송완료·정산완료 구분 없이 200건까지 내려주고(클라가 `settledAt`/`latestStatusCode` 로 분류), ⚠️ 예전에 있던 `brandConfirmedShippedAt != null`(브랜드 패킹 확인) 게이트는 **되살리면 안 된다** — 매출은 결제로 확정되는데 그 플래그는 브랜드가 버튼을 눌러야 켜져서, 안 누른 채 몇 주가 지나면 브랜드가 자기 정산금을 어느 화면에서도 못 본다(위 ₩1,510,506 이 정확히 이 경우였다). `listOnsiteForBrand`(`GET /onsite`)가 현장결제 라인을, [efs-billing](./efs-billing.md) 청구서 3종 라우트가 "낼 돈"을 같은 탭에 채운다.
- **어드민 월별 롤업(monthly)**: `listAdminMonthly(yearMonth)` 는 candidates(미정산만)와 달리 **이미 정산된 브랜드도 포함**해 브랜드별 `receivableKrw`/`settledKrw`/`lineCount`/`unsettledCount` + 계좌정보를 낸다. 정산 실행(`settledAt`) = 입금 완료라 `unsettledCount === 0` 이면 그 달 정산·입금 마감으로 읽는다. 송장과 현장결제 **모두 그 달 `Order.paidAt`** 기준으로 롤업한다.
- **⚠️ 어드민·브랜드 두 화면이 같은 숫자를 보게 하는 규칙** *(2026-09 정리)*: 정산은 서로 다른 3개 쿼리(`listAdminMonthly` / `listAdminBrandCandidates` / 브랜드의 `listDeliveredForBrand`+`listOnsiteForBrand`)가 각자 다른 모집단·상한으로 도는 구조라, 값이 조용히 갈리기 쉽다. 아래는 실제로 갈렸다가 맞춘 것들이다.
  - **현장결제 건수는 주문 단위로 센다.** `listAdminMonthly` 만 `OrderItem` 마다 `lineCount`/`unsettledCount` 를 올려서, 한 주문에 그 브랜드 제품이 여럿이면 건수가 부풀었다 — 실측으로 어드민 목록이 `56건` 인데 상세 표는 `39행`, 브랜드 화면도 `39장` 이었다(금액은 정확했다). 상세와 브랜드 조회가 모두 주문 1건 = 1행이므로 롤업을 거기 맞췄다(`orderId` 를 select 에 추가하고 `Set` 으로 센다). ⚠️ 아이템 단위로 되돌리면 같은 불일치가 돌아온다.
  - ⚠️⚠️ **브랜드 상세(`listAdminBrandCandidates`)는 정산완료 라인도 함께 내려준다.** 예전엔 `settledAt: null` 로 좁혀서 **정산을 실행하는 순간 그 화면이 0건**("정산할 송장이 없습니다")이 됐다 — 어드민이 "무엇을 얼마에 지급했는지" 확인할 화면이 어디에도 남지 않아, 브랜드가 "몇 건 누락됐다"고 할 때 대조할 수단이 DB 직접 조회뿐이었다(브랜드는 자기 정산 탭에서 그 라인을 계속 본다). 미정산/정산완료 분리는 **클라가 `settledAt`(송장)·`status==='settled'`(현장)로** 하고, 실제 마킹은 `settle()` 이 `settledAt: null` 을 다시 강제해 이중 지급을 막는다. 현장결제 축은 `ONSITE_ORDER_WHERE`(원장, settledAt 조건 없음)와 `ONSITE_SETTLEABLE_WHERE`(미정산만)로 나뉜다 — 후자는 **브랜드별 후보 집계와 settle 전용**이다("정산할 브랜드"를 고르는 큐라 미정산만 보는 게 맞다).
  - **어드민 상세 헤더 건수(`shipments.length + onsiteOrders.length`)** 도 같은 축이다 — 예전엔 현장결제를 빼고 세서 아래 표에 나오는 건이 헤더에 없었다.
  - **어드민 미러 타입 `klow_admin/src/lib/api/settlement.ts` 의 `SettlementLineDTO` 는 서버 타입의 미러다.** 필드를 빠뜨리면 그 값이 어드민 화면에서 영영 안 보인다 — `items`(제품별 내역)·`activityIso` 가 실제로 누락돼 있어, 서버는 내려주는데 **어드민만 현장결제 제품 내역을 못 봤다**(브랜드는 카드를 펼쳐 봤다).
  - **어드민 상세 표 3개(미정산 송장 · 현장결제 · 정산 완료)는 주문 목록과 같은 열(`유형`·`이메일`)을 쓴다** *(2026-09-03)*. 배지 정본은 `klow_admin/src/lib/order-status.ts` 의 `ORDER_TYPE_BADGE`/`ORDER_TYPE_HINT` 하나라 두 화면이 같은 어휘로 대사된다(라벨을 다시 적으면 갈린다).
    - 서버는 `SettlementLineDTO.email` 을 추가로 싣는다 — ⚠️ `buyer` 는 `fullName || email` **폴백**이라 이름이 있으면 이메일이 화면에서 사라져 대사 키로 쓸 수 없다. 조회 select 는 원래 `email` 을 읽고 있어 **쿼리·마이그레이션 변경이 없다**. klow_brand 미러는 이 필드를 선언하지 않아 무시하므로 그쪽은 무변경이다.
    - 송장 라인의 유형은 `settlement-cells.ts` 의 `shipmentOrderType()` 이 낸다. ⚠️ `orderTypeOf`(주문 목록)의 **channel 분기를 쓰지 않는 이유**는 취향이 아니라, 현장결제는 배송이 없어 `Shipment` 자체가 없으므로 이 축에 **구조적으로** 올 수 없기 때문이다(현장 표는 상수 `'onsite'` 를 넘긴다). 결제주체가 없는 레거시 시딩(claim 없음)은 주문 목록과 같은 규칙으로 무가(`seedingBrand`)로 본다.
    - ⚠️ 이때 **`ShipmentDTO`(`klow_admin/src/lib/api/shipments.ts`) 미러에도 같은 병이 있었다** — `SHIPMENT_INCLUDE` 는 원래 `order.isSeeding` 과 `seedingClaim.link.paymentBy` 를 내려주는데 손으로 쓴 미러가 그 둘을 선언하지 않아 어드민이 유형을 계산할 수 없었다(위 `items`·`activityIso` 와 같은 사례). **송장을 쓰는 화면에 값이 안 보이면 서버가 아니라 이 두 미러를 먼저 볼 것.**
    - 배포 순서는 **klow_server → klow_admin**. 반대면 이메일 열만 빈칸이고 400 은 나지 않는다(추가 전용 필드).
- **브랜드 정산 탭의 기본 선택 월** = **내역이 있는 가장 최근 달**(`dataMonths[0]`). ⚠️ `months[0]` 로 되돌리지 말 것 — 그 배열은 이번 달을 항상 포함시켜 최신순 정렬한 결과라 **언제나 이번 달**이고, 정산은 회고적이라 이번 달은 대개 비어 있다. 실측으로 8월에 ₩1,510,506 을 받을 브랜드가 9월에 탭을 열면 "정산 내역이 없어요" 빈 화면을 먼저 봤다(어드민이 `previousKstYearMonth()` 로 여는 것과 같은 이유). 월 **목록**에는 이번 달을 계속 넣는다(내역이 없어도 열어볼 수 있게).
- **브랜드 화면의 실패 표시** — '받을 금액'은 세 원장의 합이라 **하나만 실패해도 값이 거짓**이다. 예전엔 실패해도 `loading` 이 풀리며 **₩0 이 정상값처럼** 렌더됐고(부분 실패는 더 조용해서 현장결제만 실패하면 그만큼 적은 금액이 확정 표시됐다), 시딩 탭은 `error={null}` 하드코딩이라 **통신 실패가 "정산 내역이 없어요"로 위장**됐다. 지금은 합계가 `—` 로 빠지고 탭마다 `ErrorBlock` + 재시도가 뜬다. ⚠️ EFS 청구서(낼 돈)는 합계와 무관해 실패 판정에서 제외한다.
- **반대 방향(낼 돈)**: 브랜드가 KLOW 에 내는 EFS 배송비 후청구는 [efs-billing](./efs-billing.md) 모듈이다 — 이 모듈(받을 돈)과 돈의 방향이 반대이고, 브랜드 정산탭에서 나란히 보인다.
- **관련 파일**: `settlement.service.ts`(settleable 필터 정의·`settleableShipmentWhere` 팩토리·`listDeliveredForBrand`·`listOnsiteForBrand`·`listAdminCandidates`·`listAdminBrandCandidates`·`listAdminMonthly`·`settle`), 2 개 컨트롤러(brand · admin — 브랜드 컨트롤러는 `EfsBillingService` 도 주입해 청구서 열람 라우트를 함께 노출). 송장 include 형태는 [shipments](./shipments.md) 의 `SHIPMENT_INCLUDE`/`SHIPMENT_LIST_OMIT` 재사용. 주문 매출/시딩 구분은 [orders](./orders.md), 브랜드 구독 게이트는 [subscription](./subscription.md) 참고.

## brand-settlement.controller.ts (`@Controller('v1/brand/settlement')`)

> 전체 라우트 `BrandGuard`. 호출 브랜드(`requireBrandId`) 범위로 스코프.

| Method | Path                          | 기능                                                                       |
|--------|-------------------------------|----------------------------------------------------------------------------|
| GET    | `/v1/brand/settlement/delivered` | 결제완료 주문의 송장 전부(발송대기 + 배송중 + 배송완료 + 정산완료, settleable 만, 200건) |
| GET    | `/v1/brand/settlement/onsite`    | 현장결제(onsite) 정산 라인(`SettlementLineDTO[]`, 200건)                  |
| GET    | `/v1/brand/settlement/efs-statements` | 전달받은 EFS 배송비 청구서 목록 — [efs-billing](./efs-billing.md)   |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth` | 청구서 상세(동결 rows 스냅샷)                 |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth/excel` | 동결 xlsx 재스트리밍(R2)                 |

## admin-settlement.controller.ts (`@Controller('admin/settlement')`)

> 전체 라우트 `AdminGuard` + `SuperAdminGuard` (슈퍼관리자 전용 — 자금 지급 처리).

| Method | Path                                   | 기능                                                              |
|--------|----------------------------------------|------------------------------------------------------------------|
| GET    | `/admin/settlement/candidates`         | 지정 월(`?yearMonth=YYYY-MM`, 기본 직전월) 결제완료+미정산 송장 **+ 현장결제 미정산분**을 브랜드별 합계(+계좌정보·`belowCostItemCount`) |
| GET    | `/admin/settlement/monthly`            | 같은 월의 브랜드별 받을 금액 롤업(정산 완료분 포함 — `receivableKrw`/`settledKrw`/`unsettledCount`) |
| GET    | `/admin/settlement/candidates/:brandId`| 특정 브랜드의 해당 월 정산 대상 송장 상세 + 현장결제 주문(`onsiteOrders`) |
| POST   | `/admin/settlement/settle`             | 선택 송장·현장결제 주문(`{brandId, shipmentIds[≤500], orderIds[≤500]}` — 둘 중 하나 이상) settled 마킹(트랜잭션, adminId 기록, `@HttpCode(200)`) |
