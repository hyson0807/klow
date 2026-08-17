# stats — 어드민 대시보드 통계

- **모듈 경로**: `src/modules/stats/`
- **주 클라이언트**: `klow_admin` 메인 대시보드
- **관련 파일**: `admin-stats.controller.ts`, `stats.service.ts`

## admin-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`.

| Method | Path                              | 기능                                                                 |
|--------|-----------------------------------|----------------------------------------------------------------------|
| GET    | `/admin/stats/kpi?from=&to=`      | **기간별 KPI 9종** — 기간 내 신규 + 전체 누적/현재 (KRW)              |
| GET    | `/admin/stats/export-trend`       | 주별 수출(배송예약 발급) 물량 — **비누적** + 4주 이동평균, 최근 26주  |
| GET    | `/admin/stats/subscription-trend` | 주별 신규 구독 브랜드 — **비누적** + 4주 이동평균, 최근 26주          |
| GET    | `/admin/stats/order-type-trend`   | 주별 결제완료 주문 — 유형별(일반·시딩·현장) 건수 + 결제금액, 최근 26주 |
| GET    | `/admin/stats/brand-activity`     | 구독중 브랜드의 마지막 활동 세그먼트 + 관리 필요 목록                 |

> **2026-08 개편**: 구 `/export-weekly`(주별 **누적** 선차트)는 제거됐다. 누적은 정의상 절대
> 내려가지 않아 실적과 무관하게 우상향으로 보인다. 함께 폐기된 것 — `avgWeeklyGrowthPct`
> (누적에서 파생돼 초기 데이터에서 수백 %가 찍힘), 시딩 이익(건당 ₩1,500 하드코딩 상수라
> 실제 EFS 정산액과 무관)과 그 파생 `totalThisMonthKrw`/`totalTotalKrw`, `brandCount`
> (`BrandUser.count()` 인데 "가입 브랜드"로 오표기됐음).

## 응답 상세

### `/kpi?from=YYYYMMDD&to=YYYYMMDD`

대표 팀원이 **매주 투자사에 제출할 수치를 엑셀에 수기 입력**하는 화면이 쓴다(어드민 대시보드
홈 상단 기간 바). 구 `/revenue`(이번 달 고정)를 흡수해 대체했다.

`from`/`to` 는 **KST 달력일 포함 구간**이고 둘 다 optional — 미지정 시 **최근 7일(당일 포함)**
로 해석하고 응답 `range` 에 에코한다. 기본 기간 정의를 서버 한 곳에만 두려는 것이라
klow_admin 은 최초 호출을 인자 없이 한다. 한쪽만 보내면 400(`from 과 to 는 함께 보내야 합니다`).

지표는 전부 `{ inRange, total }` 이다 — 타일이 `inRange` 를 크게, `total` 을 작게 병기한다.
⚠️ **`paidMembers.total` 만 예외**로 누적이 아니라 **현재 active 스냅샷**이다.

> **누적(전체 기간) 조회는 서버를 다시 부르지 않는다.** 응답이 이미 지표마다 전 기간 `total`
> 을 싣고 있으므로 어드민 기간 바의 "누적" 버튼은 큰 숫자의 출처를 `inRange` → `total` 로
> 바꾸기만 한다(왕복 0회·즉시 전환). 그래서 `all` 같은 쿼리 파라미터가 없다.
> 다만 실비 미입력 경고는 기간분(`pendingChargeCount`)과 전 기간분(`pendingChargeCountTotal`)
> 이 달라 **둘 다** 내려준다.

```
{ range: { from, to, days }, fxFallbackRate,
  brandSignups, paidMembers, subscriptionRevenueKrw,
  shippingBilledKrw, exportMarginKrw, totalRevenueKrw,
  mrrKrw,                    // 현재 스냅샷 (기간 무관)
  shipmentCount, gmvKrw, paymentFeeKrw,
  shippedProductValueKrw,    // 계산은 하되 대시보드에 없음
  pendingChargeCount, pendingChargeCountTotal,
  detail: { activeCompCount, pastDueCount, canceledInRange,
            seedingClaimedInRange, seedingClaimedTotal, seedingPendingCount } }
```

| 지표 | 대시보드 라벨 | 술어 |
|---|---|---|
| `brandSignups` | 회원가입 파트너사 | `Brand` where `submittedById != null AND status <> 'draft' AND submittedAt != null`, `submittedAt` 기준 (어드민이 직접 만든 브랜드 제외 — 신청 큐와 같은 술어) |
| `paidMembers` | 유료회원수 | inRange = `BrandSubscription.createdAt ∈ 기간` / total = `status='active'` **현재 수** |
| `subscriptionRevenueKrw` | 구독 매출 | `Σ SubscriptionInvoice.amountKrw` where `status='paid' AND paidAt ∈ 기간` |
| `shippingBilledKrw` | **수출 매출액** | efs-billing `rangeChargeTotal` — 아래 별도 항목 |
| `exportMarginKrw` | 수출 마진 | `shippingBilledKrw × 10%` (`EXPORT_MARGIN_RATE`) |
| `totalRevenueKrw` | 총 매출 | 구독 매출 + 수출 매출액 (= **우리 매출**) |
| `mrrKrw` | MRR | active 구독 주기별 월환산 합. ⚠️ `planCode='brand_comp'`(무료 구독권) **제외** |
| `shipmentCount` | 수출량 | `Shipment` where `submittedAt != null AND status <> 'cancelled'` |
| `gmvKrw` | 거래액 | `Σ Order.totalUsd/100 × fx` where `paymentStatus='paid' AND paidAt ∈ 기간`. 시딩·현장 **포함**(= "전체 결제") |
| `paymentFeeKrw` | 결제 수수료 | `gmvKrw × 5%` (`PAYMENT_FEE_RATE`) |
| `shippedProductValueKrw` | *(없음)* | 아래 SQL |

> ⚠️⚠️ **`shippingBilledKrw` 가 화면의 "수출 매출액"이다.** 발급 송장 상품가
> (`shippedProductValueKrw`)와 헷갈리지 말 것 — 완전히 다른 값이고 후자는 대시보드에 없다.
> 그래서 후자의 서버 필드·메서드 이름에서 `exportRevenue` 를 일부러 뺐다(예전 이름이었다).
> 계산과 회귀 스펙은 살려 뒀다 — 실제 수출 상품가는 언제든 다시 필요해진다.

> ⚠️ **파생 두 개(`exportMarginKrw`·`paymentFeeKrw`)는 표시 전용**이고 `totalRevenueKrw` 에
> 더하지 않는다 — 마진은 수출 매출액의 일부이고 수수료는 거래액의 일부라, 더하면 이중계상이다.
> 비율은 `stats.service.ts` 상단 상수 두 개가 정본이고 `scaled()` 가 inRange·total 양쪽에
> 같은 규칙으로 적용한다(누적 조회가 어긋나지 않게).

> ⚠️ **"수출 마진"은 회계상 매출총이익이 아니다.** 밑단인 배송 청구액에는 EFS 실비
> pass-through 가 섞여 있다(우리가 실제로 남기는 건 국가별 청구수수료뿐). 운영이 합의한
> 관리 지표로 이해할 것.

**발급 송장 상품가 SQL** — Shipment→ShipmentItem→OrderItem→Order 조인, `Σ unitPriceUsd × quantity / 100 × fx`:

```sql
WHERE s."submittedAt" IS NOT NULL
  AND s."status"       <> 'cancelled'   -- 취소 후 재발급이 두 번 잡힌다
  AND s."carrier"      <> 'DOMESTIC'    -- 국내 자체배송(시딩 전용)은 수출이 아니다
  AND o."isSeeding"     = false         -- 시딩 unitPriceUsd 는 EFS 통관 신고가라 실결제액과 무관
  AND o."paymentStatus" = 'paid'        -- 환불 소급 차감(확정 정책)
```

⚠️ **필터 4개가 전부 필수다.** 하나라도 빠지면 에러 없이 **매출이 조용히 부풀어 오른다**.
회귀 잠금은 `modules/stats/__tests__/kpi.spec.ts` 가 SQL 문자열을 직접 검사한다.
현장(onsite) 주문은 Shipment 자체가 없어 조인에서 자동으로 빠진다.
`ShipmentItem.orderItemId @unique` 라 조인 fan-out 중복 합산은 구조적으로 불가능하다.
배송비를 빼는 이유는 EFS 실비로 그대로 나가는 pass-through 라 수출액이 아니기 때문이다.

> **환율**: USD 금액은 **`Order.fxRateSnapshot`(주문 시점 환율)** 으로 환산한다. 라이브 환율을
> 쓰면 지난주 제출한 숫자가 이번주 재조회 때 달라져 투자사 자료로 못 쓴다. 스냅샷이 없는
> legacy 주문만 `resolveFxRate()` 라이브값으로 폴백하고 그 값을 `fxFallbackRate` 로 함께 내린다.

> **⚠️ `::float8` 로 캐스트할 것.** `::bigint` 로 바꾸면 Prisma 가 JS `BigInt` 를 돌려주고
> `JSON.stringify` 가 `TypeError: Do not know how to serialize a BigInt` 로 죽는다. KRW 합계는
> 2^53 근처도 못 가므로 float8 이 안전하다. `COALESCE(…::numeric, …)` 의 `::numeric` 캐스트도
> 필수 — `fxRateSnapshot` 이 `Float`(double)이라 없으면 `ROUND(v)` 단일인자 오버로드가 없어 에러난다.

> **⚠️ 기간 필터에는 `AT TIME ZONE` 이중 캐스트가 필요 없다.** 아래 `kstWeekBucketSql` 이
> 이중 캐스트를 하는 건 SQL *안에서 버킷 키를 만들기* 때문이고, 기간 필터는 JS(`kstYmdRange`)가
> 이미 계산한 UTC 인스턴트를 파라미터로 넘길 뿐이라 캐스트가 낄 자리가 없다. 모든 기간 비교는
> **반열림** `>= start AND < endExclusive` 다 — `lte 23:59:59` 로 쓰면 그날 마지막 1초가 잘린다.

> **⚠️ MRR 단가 정정 (2026-08-17)**: 그전까지 stats 는 반기 330,000 / 연 528,000(월환산
> 55,000 / 44,000)이라는 **가격 인상 전 구 가격표**를 들고 있었다. 실제 청구는 396,000 / 660,000
> (월환산 66,000 / 55,000)이고 env(`SUBSCRIPTION_*_PRICE_KRW`) 오버라이드도 무시했다. 즉
> **2026-08 이전 리포트의 MRR 은 약 20% 과소집계**였다 — 투자사에 이미 낸 수치보다 커진다.
> 재발 방지로 단가 정본을 `src/pricing/subscription-price.ts` 하나로 뽑았고(청구 경로와 공유),
> 회귀 잠금은 `pricing/__tests__/subscription-price.spec.ts`.

> **⚠️ 배송 청구액은 확정 금액이 아니다.** `buildStatement` 가 `efsChargeSource ∈ ('excel','manual')`
> 인 송장만 청구 근거로 삼으므로(API 폴백값은 안 씀) **EFS 정산표 업로드 전 송장은 금액에서 빠진다**.
> 그만큼 과소집계이고, 정산표를 나중에 올리면 과거 기간 수치가 올라간다. `pendingChargeCount` 를
> 함께 내리는 이유이고 어드민 타일이 `⚠ 실비 미입력 N건 — 과소집계` 로 표시한다.
> 또한 KPI 는 **송장 발급일(`submittedAt`)** 기준인데 실제 청구서는 **EFS 픽업 이벤트(코드 03) 월**
> 기준이라 **KPI 합계와 발행된 월별 청구서 합계는 일치하지 않는다**(대시보드가 임의 기간을
> 조회해야 하는데 픽업월 귀속으론 표현이 안 된다). 대신 수출량·수출매출과 **같은 모집단**이라
> 세 타일이 서로 설명된다.

> **⚠️ 기준일이 지표마다 다르다.** 수출매출·수출량·배송청구액은 **발급일**, 거래액·구독매출은
> **결제일**이다. 그래서 같은 창에서 대소가 역전될 수 있다(발급은 결제보다 늦다).

> **교차검증**: `shipmentCount.total` 은 `/export-trend` 의 `allTimeTotalCount` 와 **항상 같아야
> 한다**(술어가 글자 그대로 같다). 대시보드 한 화면에 둘 다 뜨므로 어긋나면 즉시 보인다.
> `totalRevenueKrw = subscriptionRevenueKrw + shippingBilledKrw` 도 응답 자체로 검산된다.
> 누적에 `paidAt IS NOT NULL` 을 거는 것도 같은 이유 — 누적이 기간 합계의 상한이어야 성립한다.

> **인덱스**: `Shipment.submittedAt`·`Order.paidAt`·`SubscriptionInvoice.paidAt`·`Brand.submittedAt`
> ·`BrandSubscription.createdAt` 에 인덱스가 없다. 기존 추이 3종이 이미 같은 컬럼을 풀스캔 중이고
> 현 규모(브랜드 수십, 송장 수천)에서 seq scan 이 수 ms 라 **이번엔 추가하지 않았다**. 재검토 임계는
> Shipment 10만 행 또는 p95 500ms. ⚠️ 그때 `CREATE INDEX CONCURRENTLY` 를 쓰려면 Prisma Migrate 가
> 마이그레이션을 트랜잭션으로 감싸므로 **수동 적용 후 `migrate resolve --applied`** 여야 한다.

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

### `/order-type-trend`

```
{ weeks: 26,
  series: [{ weekStart, general, seeding, onsite, count, amountUsd, partial }],
  windowTotals: { count, amountUsd } }
```

- 모집단은 **`paymentStatus='paid'` 뿐**이다. 환불건은 `refunded` 로 바뀌므로 **자동으로 빠진다**
  — 즉 과거 주의 매출이 환불 시점에 **소급 감소**한다. "환불 제외"의 의미가 그것이다.
- 버킷 기준일은 **`paidAt`(결제일)** — 돈이 들어온 주에 잡힌다. 주문일(`createdAt`)이 아니다.
- 유형 판정 순서는 어드민 목록 필터·`orderTypeOf` 와 같다 — **`isSeeding` 을 먼저** 본다.
  시딩 주문도 `channel` 기본값이 `web` 이라 channel 을 먼저 보면 '일반'에 섞인다.
- **`amountUsd`** 는 USD 센트. `ma` 가 **없다** — 선이 파생 지표가 아니라 그 주의 실제 결제금액이라서다.
  대신 `partial` 은 그대로 내려가고, 어드민이 막대를 반투명하게·선 꼬리를 점선으로 그린다.
- ⚠️ 어드민 차트가 **금액이 아니라 건수를 쌓는다.** 시딩 대부분이 브랜드 결제(무가) 링크라
  금액이 0 이어서, 금액을 쌓으면 시딩 물량이 막대에서 사라진다(고객 결제 시딩만 금액이 붙는다).

### ⚠️ 주별 버킷의 타임존 — `AT TIME ZONE` 을 두 번 쓴다

추이 3종이 공유하는 `common/kst-time.ts` 의 `kstWeekBucketSql()` 이야기다 — JS 짝인
`kstWeekStart` 바로 옆에 둔다(둘이 같은 "KST 월요일"을 가리켜야 집계가 성립한다).
Prisma 의 `DateTime` 은 Postgres
`timestamp without time zone` 으로 매핑돼 값이 **UTC 벽시계**로 저장된다. 여기에
`col AT TIME ZONE 'Asia/Seoul'` 을 **한 번만** 걸면 Postgres 가 그 값을 KST 로 **오해**해
−9시간 시프트하고, **월요일 00:00~09:00 KST 이벤트가 전주 버킷으로 밀린다**.

이게 조용한 데이터 손실인 이유: 창 경계는 JS `kstWeekStart`(진짜 KST 월요일)가 잡는데 버킷만
한 주 앞으로 밀리면 그 버킷이 dense 배열에 없어 **시리즈에서 통째로 빠진다**. 2026-08 에
`/order-type-trend` 를 붙이면서 실측으로 발견했고(최초 결제 1건이 창 밖 버킷으로 새어 합계가
모자랐다), `/export-trend`·`/subscription-trend` 도 같은 버그였어서 함께 고쳤다.
올바른 형태는 **먼저 UTC 로 태그한 뒤 KST 로 변환**하는 것이다:

```sql
date_trunc('week', "col" AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul')
```

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
