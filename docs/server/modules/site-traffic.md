# site-traffic — klow_web 사이트 트래픽 (Vercel 엣지 요청 × 접속 국가)

- **모듈 경로**: `src/modules/site-traffic/`
- **목적**: 어드민 대시보드 "사이트 트래픽 · 국가별 요청"(영업용). klow_web 이 어느 나라에서 얼마나 불리는지를
  Cloudflare "Requests by country" 와 같은 모양으로 보여 준다.
- **원천**: Vercel Observability 쿼리 API `POST https://api.vercel.com/metrics/v1?teamId=` (**공개 문서 없음** —
  `vercel metrics` CLI v62 가 쓰는 엔드포인트를 2026-10-04 실측. 봉투는 `vercel-metrics.client.ts` 헤더 주석)
- **데이터 모델**: `SiteTrafficDay(date, scope, countryCode, requests, bytesOut, fetchedAt)` — `@@unique([date, scope, countryCode])`
- **관련 파일**: `vercel-metrics.client.ts`, `site-traffic.service.ts`, `site-traffic-window.ts`(순수 날짜 규칙),
  `site-traffic-collect.cron.ts`, `admin-site-traffic.controller.ts`, 검증 `common/validation/site-traffic.ts`
- **env**: `VERCEL_TOKEN` · `VERCEL_PROJECT_ID` · `VERCEL_TEAM_ID`(brand-domains 와 공용) + `SITE_TRAFFIC_CRON_ENABLED`.
  하나라도 비면 수집만 건너뛰고 조회는 `configured:false` 로 응답한다(**fail-soft** — 돈·장애와 무관한 지표).

## 무엇을 세나

| scope   | Vercel 필터 | 의미 |
|---------|-------------|------|
| `all`   | `environment:production` | 엣지가 받은 **모든 요청**(JS·이미지·RSC prefetch·봇 포함). 대시보드 "Requests" 와 같은 축 |
| `pages` | `… AND contentType:text/html* AND botCategory:""` | **사람이 연 HTML 페이지**. 페이지뷰에 가깝다 |

- 국가는 **접속 IP**(`clientIpCountry`). 미상은 `'XX'`. ⚠️ 브랜드관 방문 통계의 국가(손님이 **고른** 배송국,
  [결정 2026-08-20-2](../../decisions/storefront.md#2026-08-20-2))와 **다른 축**이라 두 숫자는 맞지 않는다.
- ⚠️ **사람 수가 아니다.** 2026-10-02 운영 실측: 하루 `all` 23,617 / `pages` 668. 방문 1회에 `all` 이 수십 건 생긴다.
- ⚠️ `botCategory:unknown` 도 사람이 아니다(실측 상위: bnf.fr_bot · wp-admin 스캐너 · IDC ASN) — 그래서 `pages` 는
  "분류 없음(`""`)"만 센다. `NOT botCategory:*` 는 0건을 돌려주므로 쓰지 말 것.

## 수집 (cron `site-traffic-collect`, 매일 KST 03:00)

- 대상일 = **수집 가능 90일 중 아직 없는 날 ∪ 최근 3일**(늦게 도착하는 집계 보정). 첫 실행이 곧 **90일 백필**이다.
  Vercel 은 조회 시작점이 **92일 전**까지만 허용한다(400 `timeRange cannot begin more than 92 days ago`).
- 날짜마다 두 scope 를 **다 받은 뒤** 한 트랜잭션에서 `deleteMany(date) + createMany` 로 통째 교체 → 멱등.
  "수집됨" 판정은 `all` 행의 존재다.
- 순차 호출 · 429 면 남은 날짜를 다음 실행으로 미룬다 · 서비스는 throw 하지 않는다 · 인스턴스 내 중복 실행 가드(`running`).
- KST 하루 경계: `summary` 가 timeRange 전체 합계이고 원천이 1시간 집계라 KST 자정 경계가 정확하다
  (`bucketSeconds` 는 series 용 UTC 정렬 — 쓰지 않는다. CLI 의 `--bucket-timezone` 은 새 API 가 거부한다).
- ⚠️ `VERCEL_PROJECT_ID` 는 환경마다 다르다 — **스테이징 서버는 klow-web-staging 트래픽을 모은다**(의도).
- ⚠️ 보존 정리(prune) 없음 — Vercel 에서 사라진 과거는 이 테이블에만 남는다.

## admin-site-traffic.controller.ts (`@Controller('admin/stats/site-traffic')`, AdminGuard)

| Method | Path | 기능 |
|--------|------|------|
| GET  | `/admin/stats/site-traffic?days=7\|30\|90&scope=pages\|all` | 기본 `days=30`, `scope=pages`. 창 = **어제까지** `days` 일(오늘은 미완성이라 제외) |
| POST | `/admin/stats/site-traffic/collect` | cron 을 기다리지 않고 지금 수집 시작. **기다리지 않는다**(백필은 수 분~수십 분) → `{started:true, dates}` / `{started:false, reason:'not_configured'\|'already_running'}` |

**GET 응답**
```ts
{
  configured, scope, days,
  range: { from, to },                       // KST 'YYYY-MM-DD'
  coverage: { collectedDays, expectedDays }, // 창 안에서 수집된 날 수
  lastCollectedAt,                           // ISO | null
  totals: { requests, bytes, prevRequests, prevBytes, requestsChangePct, bytesChangePct }, // 직전 창이 다 수집 안 됐으면 pct=null
  countries: [{ iso2, nameKo, requests, bytes, prevRequests }], // 요청 많은 순, nameKo 는 ShippingCountry 조인(없으면 null)
  series: [{ date, requests, bytes }],       // 창의 일별 합계(수집 안 된 날 0)
}
```

## 프론트

klow_admin 대시보드 `src/app/(authed)/_components/SiteTrafficSection.tsx` — KPI 3칸(요청·전송량·접속 국가) +
지도(`CountryTrafficMap`, d3-geo + world-atlas 110m, lazy) + 국가 순위. 110m 에 모양이 없는 작은 나라(SG·HK·MO 등)는
`src/lib/world-countries.ts` 의 중심점으로 원 마커를 그린다. 초기 fetch 는 `.catch(() => null)` 로 대시보드 critical path 밖이다.
