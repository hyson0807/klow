# 브랜드관 성과 대시보드 — 국가·제품 수요 분석 + 현장 채널 (✅ 구현 완료 · 배포 대기)

브랜드 `/stats` 를 **유입 퍼널 대시보드**에서 **브랜드관 성과 대시보드**로 확장한다.
브랜드가 한 화면에서 답을 얻어야 할 질문 셋:

1. 내 브랜드관에 들어온 사람이 담고, 사는가 (**기존**)
2. **어느 나라에서 수요가 많은가**
3. **어떤 제품이 잘 팔리고 어떤 제품이 안 팔리는가**
4. 그리고 위 셋을 **부스(현장 QR) 판매에 대해서도** — 단, 현장은 결제 결과만

- 대상 저장소: `klow_server` · `klow_brand`
- **klow_web 변경 없음 · 마이그레이션 없음 · 백필 없음 · 신규 수집 없음**
- 관련 현행 문서: [`server/modules/storefront-stats.md`](./server/modules/storefront-stats.md) ← **API·불변식의 정본은 이쪽**
- 이 문서는 계획 + 실제 구현 결과(§9)와 배포 절차(§8)를 담는다. 배포가 끝나면 `archive/` 로 옮긴다.

---

## 1. 왜 신규 수집이 필요 없나

국가·제품 데이터는 이미 주문 원장에 전부 있다.

| 필요한 값 | 이미 있는 곳 |
|---|---|
| 결제한 국가 | `Order.countryCode` — 온라인은 **배송국**, 현장은 **손님이 고른 가격 기준국** |
| 결제한 제품·수량 | `OrderItem.productId` / `quantity` |
| 브랜드 귀속 | `Product.brandId` (`OrderItem.productId` → JOIN) |
| 채널 | `Order.channel`(web/onsite) + `Order.promotionId`(할인 링크 유입 귀속) |
| 결제 시점 | `Order.paidAt` (`markPaid` 가 박는다) |

그래서 이 작업은 **조회 엔드포인트 하나 + 화면**이고, 데이터는 **과거 주문까지 즉시 소급**된다
(방문·담기 지표는 원장이 배포 후에만 쌓이므로 영원히 소급 불가 — 이 비대칭이 아래 2절의 근원이다).

---

## 2. 한 화면에 두 모집단이 산다 — 이 문서의 핵심

| | 퍼널 섹션 (방문자·장바구니·결제) | 판매 분석 섹션 (국가·제품) |
|---|---|---|
| 출처 | `BrandDailyStat` (읽기 모델) | `Order` / `OrderItem` (원장) |
| 모집단 | **그날 브랜드관을 거친 방문자**의 결제만 | **결제 완료된 전 주문** |
| `/shop`·검색·자사몰 임베드 유입 | 제외 | 포함 |
| 현장(부스 QR) | **제외**(수집 안 함) | 포함 |
| 환불 주문 | 차감 안 함 | **제외**(`paymentStatus='paid'` 만) |
| 날짜 버킷 | **원장 행의 날짜**(방문일) | **`paidAt`**(결제일) |
| 소급 | 불가(집계 시작일부터) | 가능(전 기간) |
| 단위 | **명**(순 인원) | **건 / 개**(주문·수량) |

⇒ **같은 탭의 "결제 48명"과 "국가 합계 63건"은 서로 다른 숫자이며, 그게 정상이다.**

계획 단계에선 두 섹션에 모집단 부제를 깔기로 했고 실제로 그렇게 구현했지만, **화면이 너무
장황해져 배포 전에 걷어냈다**(§9-9). 남은 설명 장치는 이 문서와 코드 주석뿐이다 — "결제 수가
안 맞는다"는 문의가 오면 위 표로 답한다.

---

## 3. 채널 탭의 정의

상단 탭 `[전체][일반][할인링크][현장]` 이 **페이지 전체**를 지배한다.

| 탭 | 퍼널(`BrandDailyStat.source`) | 랭킹(`Order`) |
|---|---|---|
| 전체 | `direct + promotion` (현장 없음) | 전 채널 (**현장 포함**) |
| 일반 | `direct` | `channel='web' AND promotionId IS NULL` |
| 할인링크 | `promotion` | `promotionId IS NOT NULL` |
| 현장 | — (수집 안 함) | `channel='onsite'` |

⚠️ **퍼널의 `source` 와 랭킹의 채널 귀속은 정의가 다르다.**
퍼널은 *그 방문자의 그날 첫 진입 경로*, 랭킹은 *주문에 프로모션 code 가 실렸는지*(`Order.promotionId`)다.
할인 링크로 들어왔지만 체크아웃까지 code 가 안 따라간 주문은 **퍼널에선 '할인', 랭킹에선 '일반'** 이 된다.
같은 사실의 두 측정이지 버그가 아니다 — 각주로 명시하고, 두 값을 억지로 맞추려 들지 말 것
(맞추려면 방문 원장과 주문을 조인해야 하는데, 그 순간 랭킹이 퍼널 모집단으로 쪼그라들어 이 작업의 목적이 사라진다).

⚠️ **국가의 의미도 채널마다 다르다** — 온라인=배송국, 현장=가격 기준국(≈국적).
전체 탭에서 섞이므로 랭킹 섹션 각주에 명시한다.

---

## 4. 화면 구성

### 4-1. 온라인 탭 (전체 / 일반 / 할인링크)

```
┌ 브랜드관 통계                          [7][30][90][전체] ┐
│ [전체][일반][할인링크][현장]                              │
├──────────────────────────────────────────────────────────┤
│  방문자 1,240      장바구니 210        결제 48            │
│                      (17%)              (3.9%)           │
├──────────────────────────────────────────────────────────┤
│  방문자 추이 ─────────╮  │  결제 추이 ──────────╮         │
├──────────────────────────────────────────────────────────┤
│  국가 TOP                │  제품 TOP                      │
│  🇺🇸 미국    ████████ 18건 (32개)                          │
│  🇯🇵 일본    ████     11건 (14개)   [세럼]  ███████ 32개   │
│  🇻🇳 베트남  ██        6건  (9개)   [크림]  ████    19개   │
│  전체 보기 ▾                        전체 보기 ▾           │
└──────────────────────────────────────────────────────────┘
```

- 퍼널 카드는 **경로별 카드 3장 → 선택된 탭 1장**으로 바뀐다(탭이 경로를 이미 고르므로 카드를 3장 둘 이유가 없다).
- 추이 차트 2종은 기존 그대로(방문자·결제, **명** 단위). 선은 탭에 해당하는 1개.

### 4-2. 현장 탭

```
│ [전체][일반][할인링크][현장◀]                             │
├──────────────────────────────────────────────────────────┤
│  결제 48건        판매 132개        판매 제품 7종          │
├──────────────────────────────────────────────────────────┤
│  결제 추이 (건) ─────────────────────────╮                │
├──────────────────────────────────────────────────────────┤
│  국가 TOP (가격 기준국)  │  제품 TOP                       │
```

- 퍼널 3칸을 `'—'` 로 비우지 않고 **칸 구성 자체를 바꾼다**(빈칸은 "고장난 화면"으로 읽힌다).
- 추이는 **주문 기준 1개(건)**. 온라인 탭의 명 단위 차트와 섞이지 않는다.
- 현장 탭에는 **전환율이 없다**(방문·담기를 수집하지 않으므로). 이건 이번 범위의 의도된 한계다 — 6절 참고.

### 4-3. 기간 토글

`[7][30][90][전체]` 하나가 퍼널·랭킹을 동시에 지배한다.

- **`전체` = 첫 데이터부터 오늘까지, 최대 365일로 클램프.**
  - 클램프하는 이유: 상한이 없으면 dense 시리즈가 무한히 길어지고, `totals ≠ Σseries` 가 되는 순간
    "합계는 100인데 그래프를 다 더하면 80"이 된다. **창을 자르면 totals 도 같은 창에서 뽑아 둘이 항상 일치**한다.
  - 365일을 넘기면 라벨을 `최근 1년`으로 바꿔 표기(거짓말을 안 하게).
- 퍼널의 `전체` 시작점 = `trackingSince`(첫 `BrandDailyStat` 행), 랭킹의 `전체` 시작점 = 첫 결제일.
  **두 섹션의 시작일이 다를 수 있다** — 각 섹션이 자기 시작일을 표기한다.

---

## 5. 서버 작업 (`klow_server`)

### 5-1. 신규 엔드포인트

`GET /v1/brand/storefront-stats/sales?days=30|all` (BrandGuard, `brand-storefront-stats.controller.ts` 에 `@Get('sales')` 추가)

**응답 = 채널별 raw 집계 행.** 클라가 탭에 맞춰 고르고, `전체` 는 클라가 채널을 합산한다.

```ts
type SalesChannel = 'direct' | 'promotion' | 'onsite';

type StorefrontSalesDTO = {
  range: { from: string; to: string };   // 창의 실제 경계(KST 'YYYY-MM-DD')
  // ⬇ 구현하며 추가됐다(§9-1) — 화면이 제품 행을 더해 건수를 만드는 함정을 구조로 없앤다.
  summary:   Record<SalesChannel | 'all', { orders: number; quantity: number; productCount: number }>;
  countries: { channel: SalesChannel; iso2: string | null; nameKo: string | null;
               orders: number; quantity: number }[];
  products:  { channel: SalesChannel; productId: string; name: string; image: string;
               orders: number; quantity: number }[];
  onsiteDaily: { date: string; orders: number }[];   // 현장만, 창 전체 dense 제로필(§9-10)
};
```

⚠️ **탭 전환에 재요청이 없다** — 한 번 받은 행을 클라가 채널로 필터/합산한다. 재요청 설계면 탭을 옮길 때마다
숫자가 잠깐 비고, `전체` 를 서버가 따로 계산하면 부분합과 전체가 갈릴 여지가 생긴다.

⚠️ **채널 합산이 정확한 이유**: 한 주문은 정확히 하나의 `(channel)` 과 하나의 `(countryCode)` 에 속한다.
그래서 `Σ채널` 과 `Σ국가` 는 중복 없이 실제 주문 수와 같다.
**단 `Σ제품` 은 아니다** — 한 주문에 그 브랜드 제품이 2종이면 제품 행 2개에 나타난다.
→ **요약 카드의 `결제 건수` 는 반드시 `countries`(또는 `daily`) 에서 뽑는다. `products` 에서 뽑으면 부풀려진다.**
(`판매 제품 종수` 만 `products` 에서 distinct 로 센다.)

### 5-2. 신규 서비스 `storefront-sales.service.ts`

같은 모듈(`src/modules/storefront-stats/`)의 두 번째 서비스로 둔다 — 같은 화면이 소비하고,
기존 `storefront-stats.service.ts`(576줄, 기록 경로 포함)에 조회 로직을 더 얹으면 파일 성격이 흐려진다.
모듈 규칙(3레벨·평면·접미사 분류)에 그대로 맞는다.

**집계는 `$queryRaw` GROUP BY 3개.** 결과 크기가 구조적으로 유계라 `take` 절단(=조용한 왜곡)이 필요 없다:
`국가 ≤ 234×3` · `제품 ≤ 브랜드 제품수×3` · `일자 ≤ 365×3`.

공통 WHERE:

```sql
JOIN "Product" p ON p."id" = oi."productId" AND p."brandId" = ${brandId}
WHERE o."paymentStatus" = 'paid'::"PaymentStatus"
  AND o."isSeeding"     = false
  AND o."paidAt" IS NOT NULL
  AND o."paidAt" >= ${start}        -- 'all' 이면 이 줄 없음
```

채널 키:

```sql
CASE WHEN o."channel" = 'onsite' THEN 'onsite'
     WHEN o."promotionId" IS NOT NULL THEN 'promotion'
     ELSE 'direct' END
```

일자 버킷은 **KST** — `kst-time.ts` 의 `kstWeekBucketSql` 과 같은 함정이 있다:

```sql
to_char(o."paidAt" AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD')
```

⚠️ **`AT TIME ZONE` 을 한 번만 걸면 안 된다.** Prisma `DateTime` 은 `timestamp without time zone` 이라
한 번만 걸면 Postgres 가 값을 KST 로 오해해 −9h 시프트하고, **00:00~09:00 KST 결제가 전날 버킷으로 밀린다.**
(2026-08 추이 차트 3종이 전부 이 버그였다.)

국가명은 `ShippingCountry.nameKo` 를 함께 낸다(구현은 JOIN 이 아니라 **상관 서브쿼리** — 바깥 참조가
`GROUP BY` 컬럼뿐이라 집계와 공존하고, JOIN 을 쓰면 `GROUP BY` 에 컬럼이 하나 더 붙는다) —
클라의 `useOrderableCountries` 는 `enabled=true` 만 담아서 **비활성국 주문의 이름이 비어버린다**.
`countryCode` 가 null 인 legacy 주문은 `iso2:null` 로 내려보내고 화면에서 `미상` 으로 표기한다.

제품명·이미지는 **현재 `Product` 값**을 쓴다(`OrderItem.productName` 스냅샷 아님) — 브랜드는 지금 카탈로그의
이름으로 인식하고, 이름을 바꿔도 `productId` 로 한 행에 모인다.

⚠️ **알려진 한계: 하드 삭제된 제품의 과거 판매는 랭킹에서 사라진다**(`products.remove` 가 hard delete,
`OrderItem.productId` 에 FK·relation 이 없어 JOIN 이 그 라인을 떨군다). 브랜드 귀속 자체가 `Product.brandId`
경유라 국가 집계에서도 같이 빠진다. 기존 `resolveItemBrands` 도 동일하게 동작하므로 **퍼널 결제 집계와는 일관**된다.

### 5-3. dense 제로필 + 창 계산 공용화

`resolveStatsWindow(days: number | 'all', earliest: string | null): string[]` 헬퍼를 만들어
**퍼널·판매 두 조회가 같은 창 규칙**을 쓰게 한다.

- 숫자면 `kstDateWindow(days)`.
- `'all'` 이면 `earliest .. 오늘`, **365일 클램프**.
- `earliest` 는 각자 자기 데이터에서: 퍼널은 기존 `findFirst`, 판매은 `daily` 집계 행의 최소 날짜(추가 쿼리 없음).

`daily` 는 **서버가 채널×날짜로 dense 제로필**한다(빠진 날을 차트가 이어 그려 추이를 왜곡하는 걸 막는 기존 규칙).

### 5-4. 기존 퍼널 조회에 `'all'` 추가

- `common/validation/storefront-stats.ts`
  `days: z.union([z.literal('all'), z.coerce.number().int().min(1).max(90)]).default(30)`
  ⚠️ **`literal('all')` 을 먼저** 둔다 — `z.coerce.number()` 가 `'all'` 을 NaN 으로 만들어 먼저 실패하면 유니온 에러 메시지가 엉킨다.
- `seriesForBrand(brandId, days)` 가 `'all'` 을 받아 `resolveStatsWindow` 로 창을 잡는다.
  **totals 도 같은 창에서 합산**한다(현행과 동일) → `totals == Σseries` 불변식 유지.
- 판매 쿼리 스키마 `StorefrontSalesQuery` 는 같은 `days` 유니온을 재사용한다(창 규칙이 갈리면 두 섹션이 다른 기간을 가리킨다).

### 5-5. 테스트 (회귀 잠금)

신규 `src/modules/storefront-stats/__tests__/storefront-sales.spec.ts` — `$queryRaw` 를 스텁하고
**행 → DTO 로 빚는 순수 함수**를 잠근다:

1. 채널 키 분류 3종(onsite 우선 → promotionId → direct).
2. `전체` = 채널 합산이 실제 주문 수와 같다(국가·일자 기준).
3. **제품 행 합산으로 요약 건수를 만들지 않는다** — 2제품 주문 1건이 `결제 2건` 으로 새지 않는지.
4. dense 제로필: 결제 없는 날이 `0` 으로 채워지고 창 밖 날짜가 안 샌다.
5. `'all'` 클램프: 400일치 데이터 → 창 365일, `range.from` 이 클램프 값.
6. 빈 브랜드(행 0) → 모든 배열이 `[]`, `range` 는 유효.

기존 `storefront-stats.spec.ts` 에는 `'all'` 창 케이스만 추가한다.

### 5-6. 서버 체크리스트

- [ ] `src/modules/storefront-stats/storefront-sales.service.ts` (신규)
- [ ] `src/modules/storefront-stats/storefront-stats.module.ts` — provider 추가
- [ ] `src/modules/storefront-stats/brand-storefront-stats.controller.ts` — `@Get('sales')`
- [ ] `src/modules/storefront-stats/storefront-stats.service.ts` — `'all'` 창
- [ ] `src/common/validation/storefront-stats.ts` — `days` 유니온 + `StorefrontSalesQuery`
- [ ] `src/common/kst-time.ts` — `resolveStatsWindow`(또는 storefront-stats 안에 두고 공유)
- [ ] `__tests__/storefront-sales.spec.ts`
- [ ] `docs/server/modules/storefront-stats.md` 갱신 (**컨트롤러 변경 시 필수 규칙**)
- [ ] 워크스페이스 `CLAUDE.md` Key Facts 에 항목 추가

검증 3층: `npm run typecheck` → `npm run test:e2e`(**cron 8개 불변**) → `npm run start`(라우트 288 → **289**).

---

## 6. 이번 범위에서 **안 하는 것**

| 안 하는 것 | 이유 |
|---|---|
| 현장 방문·장바구니 수집 | 부스는 손님이 눈앞에 있는 POS 흐름이고, 공용 태블릿이면 순방문이 1로 눌린다. **현장 탭엔 전환율이 없다** — 의도된 한계 |
| 매출 금액(₩/$) 표시 | 이번 지표는 `결제 건수 / 판매 수량`. 금액은 정산 화면이 정본 |
| 세계지도(choropleth) | 라이브러리+GeoJSON 수백KB, 주문이 몇 건이면 지도가 비어 보인다. 가로 막대가 모바일에서 더 잘 읽힌다 |
| 국가×제품 교차표 | 모바일 폭에서 못 읽고 데이터가 성기다 |
| 어드민 대시보드 반영 | 이번엔 klow_brand 만. 어드민은 기존 '브랜드관 방문' 섹션 유지 |
| 장바구니 담기의 국가·제품 분해 | 담기 이벤트에 국가가 없고 제품 단위 집계도 저장하지 않는다(신규 수집 설계 필요) |
| ~~방문자(비결제)의 국가~~ | **2026-08-20 에 별도 작업으로 구현했다** — `BrandVisitorCountryDay` + `track/country` 비콘. 국가는 손님이 국가 선택 모달에서 **고른 값**이고 단위는 **명**이다. 그래서 `/stats` 에 국가 랭킹이 **둘**(방문=명 / 판매=건)이 됐다 — 모집단 비교는 [server/modules/storefront-stats.md](./server/modules/storefront-stats.md) "방문 국가" 절 |
| 마이그레이션·백필 | 스키마 변경 0 |

---

## 7. klow_brand 작업

### 7-1. 컴포넌트 트리

```
app/(authed)/stats/
├ page.tsx                          (변경 없음)
├ _hooks/useStorefrontStats.ts      days: number|'all' 로 시그니처 확장
├ _hooks/useStorefrontSales.ts      (신규)
└ _components/
   ├ StorefrontStatsBoard.tsx       컨테이너 — 탭·기간 상태, 훅 2개, 섹션 조립
   ├ ChannelTabs.tsx                (신규) 전체/일반/할인링크/현장
   ├ FunnelSummaryCard.tsx          (기존 SourceCard 를 단일 카드로 재구성)
   ├ OnsiteSummaryCard.tsx          (신규) 결제 건수·판매 수량·제품 종수
   └ RankingList.tsx                (신규) 가로 막대 TOP 5 + '전체 보기'
```

- `RankingList` 는 국가·제품 **양쪽이 쓰는 하나의 컴포넌트**다(props: `rows[{key, label, leading, value, secondary}]`).
  ⚠️ 국가용/제품용으로 쪼개지 말 것 — `TrendChart` 가 mini 변형으로 갈렸다가 죽은 선례가 있다.
- 막대 길이는 그 목록의 **최댓값 대비 비율**(합계 대비가 아니다 — 1위가 60%면 나머지가 전부 실오라기가 된다).
- 기본 5행 + `전체 보기` 토글로 펼침(최대 높이 + 내부 스크롤).
- `flagFromIso2`(`src/lib/format.ts`) 재사용 — 새 국기 헬퍼를 만들지 말 것.

### 7-2. 상태·캐시

```ts
const [channel, setChannel] = useState<'all'|'direct'|'promotion'|'onsite'>('all');
const [days, setDays] = useState<number|'all'>(30);
const funnel = useStorefrontStats(days);   // 탭과 무관 — 경로별 값을 이미 다 갖고 있다
const sales  = useStorefrontSales(days);   // 탭과 무관 — 채널별 행을 다 갖고 있다
```

- **탭 전환에 네트워크 요청이 없다.** 기간 변경만 재요청.
- `qk.storefrontSales(days)` 추가(`src/lib/query-keys.ts`), `api.storefrontStats.sales(days)` 추가(`src/lib/api.ts`).
- `staleTime` 60초(기존 퍼널 훅과 동일).

### 7-3. 공용 크롬 변경

`components/charts/ChartChrome.tsx` 의 `RangeToggle` 이 `(number|'all')[]` 을 받도록 확장하고 `'all'` 라벨은 `전체`.
⚠️ 이 컴포넌트는 할인 링크 상세(`PromotionStatsPanel`)와 공용이다 — **기본 `ranges` 를 바꾸지 말고**
`/stats` 호출부에서만 `[7,30,90,'all']` 을 넘긴다(안 그러면 프로모션 추이에도 전체 버튼이 딸려 들어간다).

### 7-4. 빈 상태

| 상황 | 표기 |
|---|---|
| 랭킹 0행 | `아직 결제 데이터가 없어요` (차트 오버레이와 같은 톤) |
| 현장 탭 0건 | `현장(부스 QR) 결제 기록이 없어요` |
| 퍼널 `trackingSince` 가 창 안쪽 | 기존 안내문 유지 — `전체` 기간에서도 그대로 뜬다 |

### 7-5. 브랜드 체크리스트

- [ ] `src/lib/api.ts` — `storefrontStats.sales` + `StorefrontSalesDTO` 타입
- [ ] `src/lib/query-keys.ts` — `storefrontSales(days)`
- [ ] `_hooks/useStorefrontSales.ts` (신규) / `useStorefrontStats.ts` 시그니처
- [ ] `_components/` 4개 파일(신규 3 + 기존 1 재구성)
- [ ] `components/charts/ChartChrome.tsx` — `RangeToggle` 타입 확장
- [ ] 모바일(≈380px)·데스크탑 양쪽에서 랭킹 2단 → 1단 스택 확인

---

## 8. 배포

**순서: `klow_server` → `klow_brand`.** 마이그레이션·백필·klow_web 변경 없음, cron 개수 불변.

- 서버 먼저면: 신규 엔드포인트가 아무도 안 부르는 상태로 떠 있다(무해).
- **반대로 하면**: klow_brand `/stats` 의 랭킹 섹션이 404 로 에러 상태에 빠진다(퍼널은 살아 있음).
- 롤백은 klow_brand 만 되돌리면 된다(서버는 순수 추가).

### 스모크

1. 브랜드 계정으로 `/stats` → 탭 4개 전환에 **네트워크 요청이 안 나가는지**(DevTools).
2. 기간 `전체` → 퍼널 합계 == 차트 합, 랭킹 시작일 표기 확인.
3. 현장 결제가 있는 브랜드로 현장 탭 → 결제 건수가 정산 탭 '현장결제' 라인 수와 일치.
4. 다브랜드 주문 1건 → 각 브랜드 화면에서 **자기 라인만** 잡히는지.
5. 2제품 주문 1건 → 요약 `결제 1건` / 제품 랭킹 2행(합산 2건이 아님).
6. 환불 처리한 주문이 랭킹에서 빠지고 퍼널 결제엔 남아 있는지(2절 표대로).

---

## 9. 구현 결과 — 계획과 달라진 점

계획대로 간 것은 다시 적지 않는다. **설계가 바뀐 지점만** 남긴다.

### 9-1. `summary` 를 서버가 내려준다 (계획: 클라가 `countries` 에서 뽑는다)

계획 5-1 은 "요약 건수는 반드시 `countries` 에서 뽑을 것"을 **주석 규칙**으로 뒀다. 그런데
klow_brand 에는 테스트 인프라가 없어 그 규칙을 잠글 방법이 없었다 — 나중에 누가 `products` 를
더하면 조용히 부풀려진 건수가 브랜드 화면에 나간다. 그래서 응답에 `summary`(채널별 + `all`)를
실어 **화면에 더할 것을 남기지 않았다.** 규칙이 주석에서 응답 모양으로 승급했고, 서버 스펙이
"2제품 주문 1건이 2건으로 새지 않는다"를 잠근다.

`all.productCount` 도 채널별 종수의 합이 아니라 distinct 집합이다(온라인·현장 양쪽에서 팔린
제품이 두 번 세어진다).

### 9-2. `RangeToggle` 을 제네릭으로 (계획: 타입만 확장)

값 타입을 `number | 'all'` 로 **고정**하면, `'all'` 을 지원하지 않는 할인 링크 추이
(`PromotionStatsPanel`, 핸들러가 `(n: number) => void`)가 컴파일에서 막히고 통과시키려면
캐스트를 뿌리게 된다. `RangeToggle<T extends RangeValue = number>` 로 두면 호출부가 숫자만 쓸 때
`onChange` 도 숫자로 좁혀진다. `'all'` 은 기본 `ranges` 에 넣지 않고 `/stats` 가 `STATS_RANGES` 를
명시적으로 넘긴다.

### 9-3. 어드민 쿼리 스키마를 분리 (계획에 없던 항목)

퍼널 `days` 에 `'all'` 을 추가하자 **같은 스키마를 쓰던 어드민 라우트**(`/admin/stats/storefront-visits`)가
`'all'` 을 문법상 받아들이게 됐다. `trafficForAdmin` 은 창 확장을 검토한 적이 없어 그대로 두면
**조용히 오늘 하루만** 집계된다. `StorefrontAdminStatsQuery`(숫자 전용)로 갈랐다.

### 9-4. 창 계산은 모듈 파일 `stats-window.ts` 로

`common/` 입주 조건(서로 다른 모듈 2개 이상 + 도메인 로직 없음)을 만족하지 않는다 — 소비자가
둘 다 storefront-stats 모듈 안이고 `'all'` 의 의미도 이 화면의 규칙이다. 모듈 규칙(3레벨 · 평면 ·
접미사 없는 명사 = 순수 헬퍼)에 그대로 맞는다.

⚠️ 계획에 없던 함수 `statsWindowStart(days, now)` 가 생겼다. **집계 하한도 창과 같은 상한(365일)만큼
거슬러 가야 한다** — 하한 없이 전부 뽑고 창만 나중에 자르면 국가·제품 합계에 창 밖 주문이 섞여
일별 합과 갈라진다. 두 함수는 **같은 `now`** 를 받는다(요청이 KST 자정을 걸치면 집계 경계와 창
경계가 하루 어긋난다). 계획에 있던 `clamped` 플래그는 §9-10 에서 제거했다 — 하한이 이미
클램프라 판매 쪽에선 항상 false 였고, "최근 1년" 라벨을 화면이 쓰지 않았다.

### 9-5. 퍼널 응답의 `range` 는 넣었다가 뺐다

`'all'` 의 실제 경계를 싣느라 추가했는데, 각주를 걷어내면서 읽는 곳이 사라졌다(§9-10).
되살릴 때 창 시작일은 dense 시리즈의 `series[0].date` 로 충분하다 — 원래 구현이 그랬다.
계획 5-4 의 "totals 도 같은 창에서" 는 그대로다.

### 9-6. 요약 카드는 컴포넌트 1개

`FunnelSummaryCard` / `OnsiteSummaryCard` 두 파일 대신 `SummaryCard(cells, note)` 하나를 보드
파일 안에 뒀다 — 차이가 셀 3개의 내용과 `note` 문구뿐이라 파일을 가르면 같은 마크업이 두 벌 된다.
`note`(모집단 설명)는 **필수 prop** 이라 설명 없는 요약 카드를 만들 수 없다.

### 9-7. 실제 파일 목록

| 저장소 | 신규 | 수정 |
|---|---|---|
| klow_server | `storefront-sales.service.ts` · `stats-window.ts` · `__tests__/storefront-sales.spec.ts` | `storefront-stats.service.ts`(`'all'`+`range`) · `brand-storefront-stats.controller.ts` · `admin-storefront-stats.controller.ts` · `storefront-stats.module.ts` · `common/validation/storefront-stats.ts` · `__tests__/storefront-stats.spec.ts` |
| klow_brand | `_components/ChannelTabs.tsx` · `_components/RankingList.tsx` · `_hooks/useStorefrontSales.ts` | `_components/StorefrontStatsBoard.tsx`(전면 개편) · `_hooks/useStorefrontStats.ts` · `components/charts/ChartChrome.tsx` · `lib/api.ts` · `lib/api-types.ts` · `lib/query-keys.ts` |

### 9-8. 검증 결과

- klow_server: `npm run typecheck` ✅ · `npx jest src/modules/storefront-stats` ✅ (42 + 9) ·
  `npm run test:e2e` ✅ (cron 8개 불변) · 부팅 시 `/v1/brand/storefront-stats/sales` 매핑 확인 ✅
- **raw SQL 3종을 dev DB 에 실제 실행해 확인** ✅ — 채널 CASE · `nameKo` 상관 서브쿼리 · KST 이중
  캐스트 버킷이 모두 기대한 행을 낸다(빈 브랜드와 결제 있는 브랜드 양쪽).
- klow_brand: `npm run type-check` ✅ · `npx eslint` ✅ · `npm run build` ✅
- **남은 것: 브랜드 계정으로 로그인한 실제 화면 확인**(§8 스모크). 세션이 필요해 자동 검증에서 제외했다.

### 9-9. 화면 각주를 전부 걷어냈다 (배포 전 결정)

요약 카드 부제 2종 · `trackingSince` 안내 · 랭킹 모집단 각주를 **화면에서 제거**했다. 데이터가
막 쌓이기 시작한 화면에 설명문이 지표보다 길어 보였다.

⚠️ **잃은 것을 알고 있어야 한다**: 브랜드는 이제 화면만 보고는 (a) 퍼널 결제와 랭킹 건수가 왜
다른지 (b) 차트의 앞 구간 0 이 "아무도 안 왔다"가 아니라 "기록이 없다"인지 알 수 없다. 둘 다
실제로 문의가 나올 수 있는 지점이고, 답은 §2 표에 있다. 되살릴 위치는 `SummaryCard` 아래와
랭킹 섹션 아래이며, 서버는 `trackingSince`/`range` 를 **계속 내려주고 있어** 화면만 붙이면 된다.

같은 결정으로 채널 탭의 색 점 아이콘도 제거하고 기간 토글과 **같은 모양**으로 통일했다
(한 줄에 나란히 서는 두 컨트롤이라 모양이 갈리면 무엇이 무엇을 거는 스위치인지 안 읽힌다).
`TAB_META.color` 는 남는다 — 그 탭에서 그리는 **추이선 색**이다.

### 9-10. `/simplify` 정리 (구현 후)

4개 리뷰 에이전트(재사용·간소화·효율·고도)를 돌려 나온 지적을 반영했다. 되돌리기 쉬운
"작은 정리"가 아니라 **설계 결정을 바꾼 것들**만 적는다.

| 지적 | 반영 |
|---|---|
| `ChannelTabs` 가 `RangeToggle` 의 클래스 문자열을 통째로 복사 — `ChartChrome` 이 없애려고 만들어진 병이 재발 | `SegmentedToggle` 을 `ChartChrome` 에 추출하고 **둘 다 그것을 감싼다** |
| `PAID_DATE_EXPR` 이 `kstWeekBucketSql` 의 이중 캐스트 트랩을 통째로 복제 | `common/kst-time.ts` 에 **`kstDayBucketSql(column, table?)`** 을 주간 짝 옆에 추가 |
| `TAB_META.funnel: boolean` 이 타입을 좁히지 못해 `as 'direct'\|'promotion'` 캐스트 2개 필요 | **`FunnelTab` 타입 + `funnelKeyOf(tab)`** — 값 하나가 분기와 인덱싱을 동시에 좁힌다. `{key:'onsite', funnel:true}` 같은 설정 실수가 이제 컴파일 에러다 |
| `countryRows`/`productRows` 가 같은 함수 두 벌 — 실제로 라벨 규칙이 갈려 있었다(한쪽은 첫 행, 한쪽은 마지막 행) | **`mergeByTab(rows, tab, keyOf)` + `byValue`** 공용화 |
| `daily` 가 3채널 × 365일을 제로필하는데 화면은 현장만 읽는다(730행·`quantity` 전부 사장) | **`onsiteDaily: {date, orders}[]`** 로 축소 |
| 퍼널 조회가 `'all'` 하나 때문에 **항상** 2쿼리를 직렬화(기본 경로가 Neon 왕복을 한 번 더) | `'all'` 일 때만 직렬, 숫자 창은 `Promise.all` 복원 |
| `statsWindowStart` 가 365개 문자열 배열을 만들어 `[0]` 만 쓰고 다시 파싱(+ 도달 불가 폴백) | `kstDayStart(now) - (span-1)*DAY_MS` 한 줄 |
| 두 창 함수가 각자 `new Date()` — KST 자정을 걸치면 집계·창 경계가 하루 어긋남 | 호출부가 `now` 하나를 만들어 둘 다에 넘긴다 |
| 어드민 스키마를 포크하며 숫자 경계(`min(1).max(90)`)까지 복붙 | `StatsDaysNumber` 잎 하나를 두 스키마가 공유 |
| `clamped`·`range.days`·퍼널 `range` 가 아무도 안 읽는 응답 필드 | 전부 제거 (`trackingSince` 만 남긴다 — §9-5) |
| 채널 목록이 `summarize()` 안에서 세 번 반복 | `SALES_CHANNELS` 에서 `Object.fromEntries` 로 생성 |
| 제품 쿼리 `GROUP BY 1,2,3,4` 가 이미지 URL 을 그룹 키에 넣음 / `paidAt IS NOT NULL` 중복 술어 | `GROUP BY 1, p."id"` · 술어 제거 |

**넘긴 지적과 이유**
- **3쿼리 → `GROUPING SETS` 한 방**: 실익은 인정하지만 `iso2=NULL`(실제 값)과 롤업 행을
  `GROUPING()` 으로 갈라야 해 정리 범위를 넘는 재작성이다. 코드와 모듈 문서에 다음 수로 적어 뒀다.
- **`Order(paymentStatus, paidAt)` 인덱스 추가**: 진짜 확장 병목이 맞다(기간을 좁혀도 비용이
  안 준다). 다만 **마이그레이션이 생겨 "무중단·마이그레이션 없음"이라는 이 릴리스의 성격이
  바뀐다.** 별도 작업으로 분리하고 모듈 문서에 근거를 남겼다.
- **`summary` 를 현장 전용으로 축소**: 지금 화면이 현장 탭에서만 읽는 건 맞지만, 축소하면
  §9-1 이 세운 "제품 행을 더해 건수를 만들 수 없다"는 구조적 방어가 사라진다. 객체 4개 값이다.
- **랭킹 썸네일 CDN 리사이즈(`?width=48`)·`'all'` 퍼널 페이로드 다운샘플링**: 둘 다 이 화면만의
  문제가 아니라 앱 전반의 규칙이라 여기서 단독으로 도입하지 않는다.

정리 후 `/stats` 클라 번들이 6.27 kB → **3.2 kB**.
