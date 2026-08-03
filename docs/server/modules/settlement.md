# settlement — 브랜드 매출 정산

- **모듈 경로**: `src/modules/settlement/`
- **주 클라이언트**: `klow_brand`(정산 탭 — 발송 이후 송장 원장·현장결제 라인·EFS 청구서), `klow_admin`(정산 처리 — 월별 후보 집계·월별 롤업·정산 확정).
- **데이터 모델**: 정산은 **송장(`Shipment`) 단위**로 마킹한다. 정산 상태는 `Shipment.settledAt`(정산 시각)·`Shipment.settledById`(처리한 어드민) 두 컬럼으로 표현하고, 금액은 `Shipment.items[].orderItem.settlementPriceKrw × quantity` 를 합산해 산출한다. 별도 `Settlement` 테이블 없이 송장에 직접 마킹하는 구조. 정산 단위 키는 `(orderId, brandId, shipmentId)` — 한 브랜드 = 한 송장이므로 송장 1장이 곧 정산 1건.
- **현장결제(onsite)는 Order 단위 정산**: `Order.channel='onsite'` 주문은 배송이 없어 `Shipment` 자체가 없으므로, 정산 상태를 `Order.settledAt`/`settledById`/`settledMonth`(KST `YYYY-MM` 라벨) 에 직접 마킹한다. 브랜드 귀속은 `OrderItem.productId → Product.brandId`(OrderItem 에 product 관계가 없어 별도 조회) 로 풀고, 멀티브랜드 주문이어도 자기 브랜드 라인만 합산한다. 월 버킷 기준도 송장(`latestStatusAt`)이 아니라 `Order.paidAt` 이다. 브랜드 정산탭이 송장 라인과 현장결제 라인을 같은 카드로 렌더하도록 서버가 `SettlementLineDTO`(`kind:'shipment'|'onsite'`, `settlementKrw`, `status`, `activityIso` 등)로 통일해 내려준다.
- **정산 대상 필터 (settleable)**: 무가(배송비만) 시딩 주문은 정산에서 **제외**하되, 브랜드가 물품가를 청구한 시딩 주문(`OrderItem.settlementPriceKrw > 0` = 브랜드 매출)은 **포함**한다. 또한 `paymentStatus=paid` 를 강제한다 — 배송완료(EFS `33`) 뒤 환불된 주문은 환불이 `Order` 만 `refunded` 로 전이시켜 `Shipment.status`/`latestStatusCode` 가 그대로 남아 후보에 계속 잡히므로, 여기서 빼 브랜드 과지급을 막는다. 필터 정의는 두 형태로 공유한다:
  - `SETTLEABLE_ORDER_WHERE = { paymentStatus: 'paid', OR: [{ isSeeding: false }, { items: { some: { settlementPriceKrw: { gt: 0 } } } }] }` — Order 직접 필터.
  - `SETTLEABLE_SHIPMENT_WHERE = { order: SETTLEABLE_ORDER_WHERE }` — Shipment→order 관계 필터.
  - `ONSITE_SETTLEABLE_WHERE = { channel: 'onsite', paymentStatus: 'paid', settledAt: null }` — 현장결제 전용(Shipment 가 없어 Order 로 판정).
  - **모든 read(목록·후보·월별 롤업) 와 실제 정산 write(settle) 가 같은 정의를 강제**한다. settle 의 `updateMany.where` 에도 `SETTLEABLE_SHIPMENT_WHERE` 를 넣어, 시딩 송장이 후보에 안 떠도 마킹 단계에서 한 번 더 막아 ₩0 정산 누수를 차단한다.
- **EFS 추적 상태코드 '33' = 배송완료**: `EFS_STATUS_DELIVERED = '33'`(소비자 인도 완료). `Shipment.latestStatusCode === '33'` 인 송장만 정산 후보가 된다. 후보 월 필터는 `Shipment.latestStatusAt`(배송완료 시각) 기준.
- **KST(UTC+9) 기준 시간 처리**: 월 경계는 `src/common/kst-time.ts` 의 `parseKstYearMonth`/`previousKstYearMonth` 로 KST 기준 산출한다. 어드민 조회 `yearMonth` 는 `YYYY-MM` 형식이고 형식이 어긋나면 400(`yearMonth는 YYYY-MM 형식이어야 합니다`), 미지정 시 `previousKstYearMonth()` = 직전월 — 매월 15일 어드민이 직전월 배송완료분을 일괄 정산하는 운영 흐름. 모듈 로컬 `KST_OFFSET_MS = 9h` 는 `settle` 이 현장결제 주문에 찍는 `settledMonth`(KST `YYYY-MM`) 산출에 쓴다.
- **정산 확정(settle) 액션**: 한 트랜잭션에서 **송장(`shipmentIds`)과 현장결제 주문(`orderIds`)을 함께** `settledAt=now`·`settledById=adminId` 마킹한다(둘 다 비면 400 `정산할 대상을 선택하세요`). 송장 `where` 에는 `brandId` + `latestStatusCode='33'`(배송완료) + `settledAt=null` + settleable 을, 현장결제 `where` 에는 `channel='onsite'` + `paymentStatus=paid` + `settledAt=null` 을 강제하고, 각각 `updateMany.count` 가 요청 개수와 다르면 400 으로 롤백 — 부분 마킹을 방지한다("일부 송장이 정산 대상이 아닙니다" / "일부 현장결제 주문이 정산 대상이 아닙니다"). 현장결제 주문에는 `settledMonth`(KST `YYYY-MM`)도 함께 찍는다. 응답은 `{ settledCount, onsiteSettledCount, settledAt }`. (참고: 정산 *사유/reason* 은 `SettleBody`(`brandId`/`shipmentIds`/`orderIds`) 에 없으며, 기록 필드는 `adminId`·`settledAt` 이다.)
- **브랜드 정산탭 조회**: 요약(summary) 엔드포인트는 없다 — 브랜드 화면이 원장 3종을 직접 받아 집계한다. `listDeliveredForBrand`(`GET /delivered`)는 **브랜드가 발송 시작한 이후 모든 송장**(`status=submitted` + `brandConfirmedShippedAt != null` + settleable)을 배송중·배송완료·정산완료 구분 없이 200건까지 내려주고(클라가 `settledAt`/`latestStatusCode` 로 분류), `listOnsiteForBrand`(`GET /onsite`)가 현장결제 라인을, [efs-billing](./efs-billing.md) 청구서 3종 라우트가 "낼 돈"을 같은 탭에 채운다.
- **어드민 월별 롤업(monthly)**: `listAdminMonthly(yearMonth)` 는 candidates(미정산만)와 달리 **이미 정산된 브랜드도 포함**해 브랜드별 `receivableKrw`/`settledKrw`/`lineCount`/`unsettledCount` + 계좌정보를 낸다. 정산 실행(`settledAt`) = 입금 완료라 `unsettledCount === 0` 이면 그 달 정산·입금 마감으로 읽는다. 송장(배송완료 `33` + 그 달 `latestStatusAt`)과 현장결제(그 달 `paidAt`)를 함께 롤업한다.
- **반대 방향(낼 돈)**: 브랜드가 KLOW 에 내는 EFS 배송비 후청구는 [efs-billing](./efs-billing.md) 모듈이다 — 이 모듈(받을 돈)과 돈의 방향이 반대이고, 브랜드 정산탭에서 나란히 보인다.
- **관련 파일**: `settlement.service.ts`(settleable 필터 정의·`listDeliveredForBrand`·`listOnsiteForBrand`·`listAdminCandidates`·`listAdminBrandCandidates`·`listAdminMonthly`·`settle`), 2 개 컨트롤러(brand · admin — 브랜드 컨트롤러는 `EfsBillingService` 도 주입해 청구서 열람 라우트를 함께 노출). 송장 include 형태는 [shipments](./shipments.md) 의 `SHIPMENT_INCLUDE`/`SHIPMENT_LIST_OMIT` 재사용. 주문 매출/시딩 구분은 [orders](./orders.md), 브랜드 구독 게이트는 [subscription](./subscription.md) 참고.

## brand-settlement.controller.ts (`@Controller('v1/brand/settlement')`)

> 전체 라우트 `BrandGuard`. 호출 브랜드(`requireBrandId`) 범위로 스코프.

| Method | Path                          | 기능                                                                       |
|--------|-------------------------------|----------------------------------------------------------------------------|
| GET    | `/v1/brand/settlement/delivered` | 발송 시작 이후 모든 송장(배송중 + 배송완료 + 정산완료, settleable 만, 200건) |
| GET    | `/v1/brand/settlement/onsite`    | 현장결제(onsite) 정산 라인(`SettlementLineDTO[]`, 200건)                  |
| GET    | `/v1/brand/settlement/efs-statements` | 전달받은 EFS 배송비 청구서 목록 — [efs-billing](./efs-billing.md)   |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth` | 청구서 상세(동결 rows 스냅샷)                 |
| GET    | `/v1/brand/settlement/efs-statements/:yearMonth/excel` | 동결 xlsx 재스트리밍(R2)                 |

## admin-settlement.controller.ts (`@Controller('admin/settlement')`)

> 전체 라우트 `AdminGuard` + `SuperAdminGuard` (슈퍼관리자 전용 — 자금 지급 처리).

| Method | Path                                   | 기능                                                              |
|--------|----------------------------------------|------------------------------------------------------------------|
| GET    | `/admin/settlement/candidates`         | 지정 월(`?yearMonth=YYYY-MM`, 기본 직전월) 배송완료+미정산 송장 **+ 현장결제 미정산분**을 브랜드별 합계(+계좌정보·`belowCostItemCount`) |
| GET    | `/admin/settlement/monthly`            | 같은 월의 브랜드별 받을 금액 롤업(정산 완료분 포함 — `receivableKrw`/`settledKrw`/`unsettledCount`) |
| GET    | `/admin/settlement/candidates/:brandId`| 특정 브랜드의 해당 월 정산 대상 송장 상세 + 현장결제 주문(`onsiteOrders`) |
| POST   | `/admin/settlement/settle`             | 선택 송장·현장결제 주문(`{brandId, shipmentIds[≤500], orderIds[≤500]}` — 둘 중 하나 이상) settled 마킹(트랜잭션, adminId 기록, `@HttpCode(200)`) |
