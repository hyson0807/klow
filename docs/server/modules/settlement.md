# settlement — 브랜드 매출 정산

- **모듈 경로**: `src/modules/settlement/`
- **주 클라이언트**: `klow_brand`(정산 탭 — 요약·배송완료 목록), `klow_admin`(정산 처리 — 월별 후보 집계·정산 확정).
- **데이터 모델**: 정산은 **송장(`Shipment`) 단위**로 마킹한다. 정산 상태는 `Shipment.settledAt`(정산 시각)·`Shipment.settledById`(처리한 어드민) 두 컬럼으로 표현하고, 금액은 `Shipment.items[].orderItem.settlementPriceKrw × quantity` 를 합산해 산출한다. 별도 `Settlement` 테이블 없이 송장에 직접 마킹하는 구조. 정산 단위 키는 `(orderId, brandId, shipmentId)` — 한 브랜드 = 한 송장이므로 송장 1장이 곧 정산 1건.
- **정산 대상 필터 (settleable)**: 무가 시딩 주문(`Order.isSeeding=true`, 매출 ₩0)은 정산에서 **제외**한다. 정산 가능한 송장은 결제 완료(`paymentStatus=paid`) + 발송 시작(`status=submitted` / `brandConfirmedShippedAt != null`)분만이다. 필터 정의는 두 형태로 공유한다:
  - `SETTLEABLE_ORDER_WHERE = { isSeeding: false }` — Order 직접 필터(오늘 매출 집계 등).
  - `SETTLEABLE_SHIPMENT_WHERE = { order: { isSeeding: false } }` — Shipment→order 관계 필터.
  - **모든 read(요약·목록·후보) 와 실제 정산 write(settle) 가 같은 정의를 강제**한다. settle 의 `updateMany.where` 에도 `SETTLEABLE_SHIPMENT_WHERE` 를 넣어, 시딩 송장이 후보에 안 떠도 마킹 단계에서 한 번 더 막아 ₩0 정산 누수를 차단한다.
- **EFS 추적 상태코드 '33' = 배송완료**: `EFS_STATUS_DELIVERED = '33'`(소비자 인도 완료). `Shipment.latestStatusCode === '33'` 인 송장만 정산 후보가 된다. 후보 월 필터는 `Shipment.latestStatusAt`(배송완료 시각) 기준.
- **KST(UTC+9) 기준 시간 처리**: 모든 일/월/연 경계는 `src/common/kst-time.ts`(`kstDayStart/kstDayEnd/kstMonthStart/kstMonthEnd/parseKstYearMonth/previousKstYearMonth`) 로 KST 기준 산출한다. 어드민 후보 조회 `yearMonth` 는 `YYYY-MM` 형식(미지정 시 `previousKstYearMonth()` = 직전월) — 매월 15일 어드민이 직전월 배송완료분을 일괄 정산하는 운영 흐름. 브랜드 요약의 "오늘 매출"은 단일 `now` 기준으로 `kstDayStart/End` 를 계산해 자정 통과 시 데이터 부조화를 막는다. `KST_OFFSET_MS = 9h` 는 직전 정산 회차의 KST 월 추출에 사용.
- **정산 확정(settle) 액션**: 선택 송장을 트랜잭션으로 `settledAt=now`·`settledById=adminId` 마킹한다. `where` 에 `brandId` + `latestStatusCode='33'`(배송완료) + `settledAt=null`(미정산) + settleable 을 모두 강제하고, `updateMany.count !== shipmentIds.length` 면 "일부 송장이 정산 대상이 아닙니다"로 롤백 — 부분 마킹을 방지한다. (참고: 정산 *사유/reason* 은 현재 컨트롤러 `SettleBody`(`brandId`/`shipmentIds`) 에 포함되지 않으며, 기록 필드는 `adminId`·`settledAt` 이다.)
- **브랜드 요약(summary) 집계**: `getBrandSummary(brandId)` 가 한 번에 4지표를 반환 — `todayOrderCount`(오늘 KST 결제 건수), `todaySalesKrw`(오늘 매출), `pendingSettlementKrw`(배송완료 + 미정산 송장 합 = 정산 예정), `lastSettledKrw`/`lastSettledMonth`(직전 정산 회차가 속한 KST 월의 settled 송장 합과 월). 오늘 매출은 `OrderItem ↔ Product` 관계가 schema 에 없어 브랜드 제품 `productId[]` 를 사전 조회한 뒤 `IN` 으로 집계.
- **관련 파일**: `settlement.service.ts`(settleable 필터 정의·`getBrandSummary`·`listDeliveredForBrand`·`listAdminCandidates`·`listAdminBrandCandidates`·`settle`), 2 개 컨트롤러(brand · admin). 송장 include 형태는 [shipments](./shipments.md) 의 `SHIPMENT_INCLUDE`/`SHIPMENT_LIST_OMIT` 재사용. 주문 매출/시딩 구분은 [orders](./orders.md), 브랜드 구독 게이트는 [subscription](./subscription.md) 참고.

## brand-settlement.controller.ts (`@Controller('v1/brand/settlement')`)

> 전체 라우트 `BrandGuard`. 호출 브랜드(`requireBrandId`) 범위로 스코프.

| Method | Path                          | 기능                                                                       |
|--------|-------------------------------|----------------------------------------------------------------------------|
| GET    | `/v1/brand/settlement/summary`   | 정산 요약 4지표(오늘 건수/매출, 정산 예정, 직전 정산 금액·월)             |
| GET    | `/v1/brand/settlement/delivered` | 발송 시작 이후 모든 송장(배송중 + 배송완료 + 정산완료, settleable 만)     |

## admin-settlement.controller.ts (`@Controller('admin/settlement')`)

> 전체 라우트 `AdminGuard` + `SuperAdminGuard` (슈퍼관리자 전용 — 자금 지급 처리).

| Method | Path                                   | 기능                                                              |
|--------|----------------------------------------|------------------------------------------------------------------|
| GET    | `/admin/settlement/candidates`         | 지정 월(`?yearMonth=YYYY-MM`, 기본 직전월) 배송완료+미정산 송장을 브랜드별 합계(+계좌정보) |
| GET    | `/admin/settlement/candidates/:brandId`| 특정 브랜드의 해당 월 정산 대상 송장 상세                         |
| POST   | `/admin/settlement/settle`             | 선택 송장(`{brandId, shipmentIds[1..500]}`) settled 마킹(트랜잭션, adminId 기록) |
