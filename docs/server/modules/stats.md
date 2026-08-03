# stats — 어드민 대시보드 통계

- **모듈 경로**: `src/modules/stats/`
- **주 클라이언트**: `klow_admin` 메인 대시보드
- **관련 파일**: `admin-stats.controller.ts`, `stats.service.ts`

## admin-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`.

| Method | Path                        | 기능                                                              |
|--------|-----------------------------|-------------------------------------------------------------------|
| GET    | `/admin/stats`              | 카운트 묶음 — `{ products, creators, videos }` (대시보드 카드용)  |
| GET    | `/admin/stats/revenue`      | 수익(KPI) 집계 — 구독 + 무료시딩 (이번 달 + 누적, KRW)            |
| GET    | `/admin/stats/export-weekly`| 주간 **누적** 수출(배송예약) 물량 — 첫 발급 주부터 이번 주까지     |

## 응답 상세

- **`/revenue`** — 모든 금액 KRW 정수, "이번 달"은 **KST 기준 당월 1일 00:00** 이후.
  `{ brandCount, subscription: { activeCount, pastDueCount, canceledCount, newThisMonth, canceledThisMonth,
  mrrKrw, revenueThisMonthKrw, revenueTotalKrw }, seeding: { claimedThisMonth, claimedTotal, pendingCount,
  profitThisMonthKrw, profitTotalKrw }, totalThisMonthKrw, totalTotalKrw }`.
  MRR 은 active 구독을 주기별 월환산으로 합산(연 44,000 / 6개월 55,000 / legacy 월 49,500),
  구독 매출은 `SubscriptionInvoice(status='paid')` 합계, 시딩 이익은 `claimed` 건수 × 1,500원 상수.
- **`/export-weekly`** — `{ series: [{ weekStart(YYYY-MM-DD, KST 주 시작), count(누적) }], avgWeeklyGrowthPct,
  totalCount }`. `Shipment.submittedAt` 기준(취소 송장 제외)이고, 발급 이력이 없으면 `series: []` ·
  `avgWeeklyGrowthPct: null` · `totalCount: 0`. `avgWeeklyGrowthPct` 는 2주차부터의 주별 성장률 산술평균(소수 1자리),
  직전 누적이 0인 구간은 제외. 상한 520주.
