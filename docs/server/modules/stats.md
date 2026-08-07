# stats — 어드민 대시보드 통계

- **모듈 경로**: `src/modules/stats/`
- **주 클라이언트**: `klow_admin` 메인 대시보드
- **관련 파일**: `admin-stats.controller.ts`, `stats.service.ts`

## admin-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`.

| Method | Path                              | 기능                                                                 |
|--------|-----------------------------------|----------------------------------------------------------------------|
| GET    | `/admin/stats`                    | 카운트 묶음 — `{ products, creators, videos }`                        |
| GET    | `/admin/stats/revenue`            | 구독 수익(KPI) 집계 — 이번 달 + 누적(KRW) + 시딩 신청 건수            |
| GET    | `/admin/stats/export-trend`       | 주별 수출(배송예약 발급) 물량 — **비누적** + 4주 이동평균, 최근 26주  |
| GET    | `/admin/stats/subscription-trend` | 주별 신규 구독 브랜드 — **비누적** + 4주 이동평균, 최근 26주          |
| GET    | `/admin/stats/brand-activity`     | 구독중 브랜드의 마지막 활동 세그먼트 + 관리 필요 목록                 |

> **2026-08 개편**: 구 `/export-weekly`(주별 **누적** 선차트)는 제거됐다. 누적은 정의상 절대
> 내려가지 않아 실적과 무관하게 우상향으로 보인다. 함께 폐기된 것 — `avgWeeklyGrowthPct`
> (누적에서 파생돼 초기 데이터에서 수백 %가 찍힘), 시딩 이익(건당 ₩1,500 하드코딩 상수라
> 실제 EFS 정산액과 무관)과 그 파생 `totalThisMonthKrw`/`totalTotalKrw`, `brandCount`
> (`BrandUser.count()` 인데 "가입 브랜드"로 오표기됐음).

## 응답 상세

### `/revenue`

모든 금액 KRW 정수, "이번 달"은 **KST 기준 당월 1일 00:00**(`kstMonthStart`) 이후.

```
{ subscription: { activeCount, pastDueCount, canceledCount, newThisMonth, canceledThisMonth,
                  mrrKrw, revenueThisMonthKrw, revenueTotalKrw },
  seeding: { claimedThisMonth, claimedTotal, pendingCount } }
```

MRR 은 active 구독을 주기별 월환산으로 합산(연 44,000 / 6개월 55,000 / legacy 월 49,500).
구독 매출은 `SubscriptionInvoice(status='paid')` 합계. 시딩은 **건수만** — 이익 추정치는 폐기됐다.
시딩 신청은 `SeedingClaim`(사람 수) 기준이고 `pendingCount` 만 링크 수다(다인원 링크 1개 = N명).

### `/export-trend` · `/subscription-trend`

둘 다 같은 shape:

```
{ weeks: 26,
  series: [{ weekStart(YYYY-MM-DD, KST 월요일), count, ma: number|null, partial: boolean }],
  windowTotalCount, allTimeTotalCount }
```

- **비누적** — `count` 는 그 주 실적 그대로다.
- **`ma`** = 4주 이동평균(소수 1자리). 창 첫 점도 정확하도록 서버가 `MA_WINDOW-1` 주를 더 읽고
  잘라낸다. 과거가 아예 없는 서비스 초기에는 확장 span 평균(`min(i+1, 4)`)이 쓰인다.
- **`partial`** — 마지막 주는 아직 진행 중이라 `partial: true` · **`ma: null`**. 미완성 주를
  평균에 넣으면 선이 인위적으로 꺾여 늘 하락으로 오독된다. 어드민은 이 막대를 연한 색으로 칠한다.
- 창 시작은 최근 26주이되 **첫 이벤트보다 앞서지 않는다**(앞쪽 0 패딩 방지).
- 데이터가 하나도 없으면 `series: []`.

`/export-trend` — `Shipment.submittedAt` 기준, **취소 송장 제외**. `allTimeTotalCount` 는 전기간
누적(KPI 타일용).

`/subscription-trend` — `BrandSubscription.createdAt` 기준.
> ⚠️ `BrandSubscription` 은 `brandId @unique` 이고 구독 시작이 `upsert` 라 `createdAt` 이
> **최초 구독 시각으로 영구 고정**된다(update 브랜치가 안 건드림). 즉 이 시리즈는 **신규 획득**
> 곡선이고 **해지 후 재가입은 다시 잡히지 않는다**. 재활성화까지 세려면 별도 이벤트 테이블이 필요하다.
>
> 무료 구독권(`planCode='brand_comp'`)·현금 결제 구독도 **필터하지 않는다** — `/brand-activity`
> 의 모집단과 같아야 대시보드 두 섹션의 숫자가 서로 어긋나지 않는다.

### `/brand-activity`

구독중(`status in ('active','past_due')`)인 브랜드가 실제로 플랫폼을 쓰고 있는지.

```
{ totalBrands,
  segments: [{ key: 'active'|'low'|'dormant', count, pct }],
  rows: [{ brandId, brandName, subscriptionStatus, lastActivityAt, lastActivitySource,
           daysSinceActivity, lastLoginAt, daysSinceLogin, segment }],
  loginTrackedCount, loginActive7dCount, loginTrackingSince }
```

`rows` 는 **구독 브랜드 전체**를 오래된 활동 순(기록 없음이 맨 앞)으로 내려준다 — 세그먼트 도넛과
관리필요 테이블이 같은 배열에서 파생돼야 두 숫자가 어긋나지 않는다. 자르는 건 어드민 몫.
한국어 라벨은 서버가 아니라 `klow_admin/src/lib/brand-activity.ts` 가 소유한다.

**세그먼트 임계** — `daysSinceActivity = floor((now − lastActivityAt) / 86400000)`
| key | 조건 |
|---|---|
| `active` | 0 ≤ d ≤ 7 |
| `low` | 8 ≤ d ≤ 30 |
| `dormant` | d > 30 **또는 활동 기록 자체가 없음(null)** |

#### 실사용 축 — 활동 소스 8종 (브랜드만 만들 수 있는 신호)

| 소스 | 필드 |
|---|---|
| `seeding_link` / `seeding_link_closed` | `SeedingLink._max(createdAt)` / `_max(closedAt)` |
| `product_submit` | `Product._max(submittedAt)` where `submittedById not null` |
| `shipment_confirm` | `Shipment._max(brandConfirmedShippedAt)` |
| `instagram_reply` | `InstagramReply._max(createdAt)` |
| `instagram_template` | `InstagramTemplate._max(updatedAt)` |
| `manual_seeding` | `ManualSeedingRecord._max(updatedAt)` |
| `campaign` | `Campaign._max(createdAt)` |

**의도적으로 제외한 것 — 넣으면 브랜드가 아무것도 안 했는데 "활성"으로 뒤집힌다:**

| 제외 | 이유 |
|---|---|
| `Campaign.updatedAt` | 공개 어필리에이트 링크의 **방문자 클릭**이 `clickCount` 를 올리며 `@updatedAt` 을 bump 한다 (`campaigns.service.ts` `trackByCode`/`trackBySlug`) |
| `Product.updatedAt` | 어드민 제품 편집이 bump. 게다가 `backfill:product-tags-english` 가 **전 제품의 updatedAt 을 의도적으로 올린** 전례가 있어, 백필 한 번에 전 브랜드가 활성이 되고 관리필요 목록이 통째로 비어버린다 |
| `Brand.updatedAt` | 어드민 승인/편집이 bump |
| `SeedingClaim.*` | 브랜드가 아니라 **바이어** 행동. 브랜드 행동은 `SeedingLink.createdAt` 이 이미 잡는다 |

소스마다 `where` 가 달라서 raw SQL UNION 대신 **병렬 `groupBy` + JS 머지**를 쓴다(대상이 수십 개
브랜드 규모이고 관련 테이블에 `brandId` 인덱스가 이미 있어 왕복 수는 무의미하다).

#### 접속 축

`BrandUser.lastSeenAt`(브랜드에 계정이 여러 개면 최신값)에서 파생한다.
**`BrandSession.lastSeenAt` 이 아니다** — 세션은 만료 시 하드 삭제되고 TTL 이 7일이라, 20일 전
접속한 브랜드는 행 자체가 없어 "휴면 60일"과 구분이 안 된다. 갱신은 `brand-auth.service.ts`
`getSession()` 이 5분 스로틀로 두 컬럼에 함께 찍는다(`docs/server/modules/brand-auth.md`).

⚠️ **백필 불가** — 과거 접속 기록은 삭제된 세션 안에만 있었다. `add_brand_last_seen` 마이그레이션
배포일(`loginTrackingSince`) 이후로만 **전진 채움**되며, `lastLoginAt: null` 은 "미접속"이 아니라
"데이터 없음"이다. 어드민이 `loginTrackedCount === 0` 이면 집계 시작일을 대신 표시한다.
