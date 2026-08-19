# storefront-stats — 브랜드관 방문 통계 · 장바구니 전환

- **모듈 경로**: `src/modules/storefront-stats/`
- **주 클라이언트**: klow_web(수집) + klow_brand 스튜디오 홈 '통계' 탭(브랜드 조회) + klow_admin 대시보드 홈(운영 조회)
- **관련 파일**: `storefront-stats.service.ts`, 컨트롤러 3개(public·brand·admin), `storefront-stats-retention.cron.ts`, `common/validation/storefront-stats.ts`
- **회귀 잠금**: `src/modules/storefront-stats/__tests__/storefront-stats.spec.ts`

## 이 모듈이 답하는 질문

"내 브랜드관에 손님이 몇 명 들어왔고, 그 중 몇 명이 장바구니에 담았는가" — **유입 경로별로**.

이전에는 유입을 세는 곳이 `PromotionDailyStat` 하나뿐이었고 그건 **할인 링크로 들어온 트래픽만**
잡았다. 브랜드관 루트로 직접 들어온 손님(SNS 프로필 링크·QR·검색·자사몰 경유)은 어디에도
기록되지 않았다.

## 데이터 모델

| 모델 | 역할 |
|---|---|
| `BrandDailyStat(brandId, date, source)` @unique | **읽기 모델**. 브랜드 × 날(KST) × 유입경로 1행에 `visits`/`uniqueVisits`/`cartAdds`/`uniqueCartAdds`. **차트는 이것만 읽는다** |
| `BrandVisitorDay(brandId, date, visitorId)` @unique | **판정 원장**. "그날 처음인가?"를 유니크 제약으로 원자적으로 답하는 게 유일한 일. `source`(그날 첫 진입 경로) + `carted` 보유 |

`enum StorefrontVisitSource = direct | promotion | onsite`.

마이그레이션 `20260819025346_add_brand_storefront_stats` 는 `CREATE TYPE` + `CREATE TABLE` 2개뿐
(기존 테이블 ALTER 0) → **롤링 배포 안전 · 백필 없음**(과거 방문 기록은 존재하지 않는다).

> ⚠️ **누적 카운터를 `Brand` 에 두지 않았다.** `Brand.updatedAt` 은 `@updatedAt` 이라 방문마다
> `brand.update` 를 치면 **방문자 트래픽이 브랜드를 bump** 하고 `stats.service.ts` 의
> `brandActivity()` 가 "브랜드가 아무것도 안 했는데 활성"으로 센다 — 그 파일이
> `Promotion.updatedAt`·`Brand.updatedAt` 을 활동 소스에서 **의도적으로 제외**해 둔 원칙을
> 정면으로 깬다. 전기간 합계는 `@@unique` 위 groupBy 한 방이라 비싸지도 않다.
> 회귀 잠금이 스텁의 `brand.update`/`upsert` 미호출을 단언한다.

## 진입 경로 (`source`)

`BrandStorefront` 를 렌더하는 라우트는 **정확히 3개**, 읽는 쿼리 파라미터는 `mode=onsite` 하나뿐.

| klow_web 라우트 | URL | source |
|---|---|---|
| `app/[brandSlug]/page.tsx` | `/{slug}` | `direct` |
| `app/[brandSlug]/[influencer]/page.tsx` | `/{slug}/{promotionSlug}` | `promotion` |
| `app/brand/[id]/page.tsx` | `/brand/{id}` | `direct` — 레거시. slug 가 있으면 `/{slug}` 로 replace |
| (1번 + 쿼리) | `/{slug}?mode=onsite` | `onsite` — 부스 QR(`klow_brand onsiteStoreUrl()`) |

`source` 는 **라우트가 prop 으로 내려준다** — 클라가 pathname 세그먼트로 넘겨짚으면 예약 슬러그
·리다이렉트가 끼는 순간 조용히 틀린다. `useAppStore.promotionCode` 도 보지 않는다(localStorage
영속이라 한 번 할인 링크로 왔던 사람이 나중에 직접 들어와도 영원히 promotion 으로 잡힌다).

> ⚠️ **`onsite` 가 `promotion` 을 이긴다.** `/{slug}/{promo}?mode=onsite` 는 정상 발급 경로가
> 만들지 않지만 손으로는 만들 수 있고, 그때 promotion 으로 세면 거짓이다 — 현장 모드에서는
> 서버가 **프로모션 세일가를 아예 적용하지 않는다**(`resolvePricingCtx` 가 `onsite:true` 면
> 프로모션 쿼리를 쏘지도 않는다). 가격이 안 걸린 유입을 할인 링크 성과로 셀 수 없다.

**브랜드관이 아닌 것**: 자사몰 카페24 임베드 버튼은 `/product/{id}?brand={slug}` = **PDP** 로 간다
(브랜드관 방문 아님. 단 거기서 "바로구매"를 누르면 `/{slug}` 로 push 되어 그때 `direct` 로 잡힌다).
시딩 `/seed/{token}` 도 별도 페이지다.

## 할인 링크 클릭도 이 파이프라인으로 통일했다 (2026-08-19)

원래 `PromotionDailyStat.clicks` 는 klow_web **서버 컴포넌트**가 셌다. 그래서 두 측정이 갈렸다:

| | 구 `PromotionDailyStat.clicks` | 이 모듈의 방문수 |
|---|---|---|
| 집계 위치 | 서버 컴포넌트 | 클라이언트 effect |
| 봇/OG 크롤러 | **포함됨** | 대부분 제외 |
| 새로고침 | 매번 +1 | 탭당 1회 |

⚠️ **봇 포함 집계는 중립적으로 틀리지 않는다 — 할인 링크 성과를 실제보다 부풀린다.** 브랜드가
"이 링크에 할인을 계속 줄까"를 판단하는 숫자가 과대계상돼 있었다. 그래서 클릭 집계를 방문
비콘과 **같은 요청**으로 옮겼다:

- klow_web 이 방문 비콘에 `promotionCode` 를 실어 보낸다(할인 링크 진입일 때만).
- `StorefrontStatsService.recordVisit` 이 `PromotionsService.recordClickByCode()` 를 부른다.
  **카운터 소유권은 promotions 모듈에 남긴다** — Off/중지 게이트가 그 도메인 규칙이라
  두 벌이 되면 갈린다.
- 구 경로 `GET /v1/promotions/track/:brandSlug/:influencerSlug` 는 **세일가 code 해석 전용**이
  됐다(`resolveBySlug`). 렌더 전에 code 가 필요해 서버 호출 자체는 남는다. **경로 이름의
  `track` 은 klow_web 과의 계약이라 남긴 legacy 다.**

⚠️ **전환 시 기존 클릭 시계열이 한 번 계단처럼 내려간다**(봇 + 새로고침이 빠진다). 버그가 아니다.
⚠️ **애드블록·JS 차단 방문자는 이제 아예 안 잡힌다**(전엔 서버에서 세어 잡혔다) — 정확도를 얻고
커버리지를 잃는 교환이다.

⚠️ `promotionCode` 는 **라우트가 이번 진입분만** 내려줘야 한다. klow_web `useAppStore.promotionCode`
는 **localStorage 영속**이라 그 값을 쓰면 예전에 링크로 왔던 사람의 클릭이 그 링크에 영원히 붙는다.
⚠️ 클릭은 `source` 로 게이트하지 **않는다** — `/{slug}/{promo}?mode=onsite` 는 source 가 `onsite`
지만 링크는 실제로 눌린 것이다(이 지표는 "링크가 몇 번 눌렸나"다).
⚠️ 클라 dedupe 키에 code 가 들어간다 — 같은 탭에서 링크 A → B 로 들어오면 둘 다 실제 클릭이라
B 가 묻히면 안 된다.

## 집계 지점이 klow_web **클라이언트**인 이유

1. **봇/크롤러 오염** — `klow.kr/{slug}` 는 SNS 로 뿌려지는 링크라 언펄러가 링크 하나당 여러 번
   HTML 을 긁는다. 서버에서 세면 전부 방문이 된다(브랜드에게 보여줄 숫자라 오염이 곧 신뢰 상실).
2. **순방문 판정 불가** — `visitorId` 는 브라우저 저장소에 있고 서버 컴포넌트는 못 읽는다.
3. **TTFB** — `[brandSlug]/page.tsx` 는 non-async 서버 컴포넌트다. 집계를 위해 async 로 바꾸면
   최다 트래픽 페이지 첫 바이트에 API 왕복이 얹힌다.
4. **전송 경로 단일화** — 담기 이벤트는 어차피 클라에서만 알 수 있다. 방문/담기가 같은
   `visitorId` 를 쓰면 퍼널 두 축이 어긋나지 않는다.

한계(막지 않음): 브랜드 본인·운영팀이 미리보기로 열어도 방문으로 잡힌다.

## 순방문 판정 — 서버 원장

클라는 불투명 `visitorId`(localStorage 난수)만 보내고, **"처음인가"는 주장하지 않는다** —
`brandVisitorDay.create` 가 성공했는지로 서버가 판정한다. API 에 `unique` 필드가 아예 없다.

- 클라가 계산해 보내는 방식을 기각한 이유: 클라가 진실을 주장하게 되고, 더 중요하게는
  **"방문한 그 사람이 담았는가"를 서버가 알 수 없어 퍼널 자체가 성립하지 않는다**.
- 서버 쿠키를 기각한 이유: 호스트가 갈리면 SameSite 처리가 필요하고 프리뷰 환경에서 조용히
  무력화된다. 고 QPS 경로마다 `Set-Cookie` 비용도 붙는다.
- klow_web `lib/visitor-id.ts` 는 **저장소를 못 쓰면 null 을 돌려주고 트래킹을 통째로 건너뛴다** —
  매번 임시 id 를 만들면 순방문이 방문수까지 부풀어 오른다(조용히 틀린 숫자보다 조용히 빠진
  숫자가 낫고, `visits` 도 함께 빠지므로 두 지표의 비율은 유지된다).

**신뢰성 한계**: localStorage 삭제·시크릿 창·다른 브라우저는 새 방문자로 잡혀 **순방문 과대**,
애드블록은 방문 자체가 안 잡혀 **전체 과소**. 추세 지표로는 충분하나 **정산·투자자 감사 지표로
쓰지 말 것**. 개인정보 측면에서는 IP·UA·계정을 저장하지 않고 난수 토큰만 쓰며 cron 이 파기한다.

⚠️ 현장 부스 공용 태블릿은 브라우저가 하나라 손님 여럿이 순방문 1로 눌린다 — `onsite` 로
격리돼 **일반/할인링크 순방문을 오염시키지 않는다**(경로를 나눈 실질적 이득이 여기 있다).

## ⚠️ 담기 게이트 — 퍼널 정의

`recordCartAdd` 는 원장에 `(brandId, date, visitorId)` 행이 **이미 있을 때만** 집계하고, 없으면
아무것도 하지 않는다.

- 이게 "브랜드관에 들어온 사람이 담는가"라는 정의 그 자체다. `/shop`·검색·임베드 PDP 에서 담은
  건은 방문 모집단 밖이라 빠진다.
- 덕분에 **`uniqueCartAdds ≤ uniqueVisits` 가 구조적으로 보장**돼 전환율에 `min(100, …)` 클램프가
  필요 없다(클램프는 정의가 틀렸다는 신호를 숨길 뿐이다).
- 귀속 경로는 **그 방문자의 그날 첫 진입 경로**(원장 행의 `source`)다 — 담기 시점의 URL 이 아니다.
  그래야 "할인 링크로 온 사람의 전환율"이 말이 된다.

⚠️ `recordCartAdd` 는 `led.carted` 를 **update 前에 값으로 붙잡는다**. 뒤에 읽으면 "이미 담았음"이
되어 순담기자가 영원히 0 이 된다.

⚠️ **brandId 는 서버가 `productId` 로 해석한다** — 공개 제품 응답에는 `brandId` 가 없다
(`pricing/price-line.ts` 의 `StrippedPricingKeys` 가 의도적으로 벗긴다). 그 strip 목록은 건드리지
않았고, `CartLine` 에 필드를 더하는 대안도 기각했다(`persist`+`migrate` 를 가진 **영속 스키마**라
분석 부수효과 하나 때문에 결제 경로를 건드릴 이유가 없다).

## 라우트

### public-storefront-stats.controller.ts (`@Controller('v1/storefront-stats')`)

> 가드 없음 — 공개 트래픽. `@HttpCode(200)`, 응답은 항상 `{ ok: true }`
> (**서비스가 모든 예외를 삼키므로 이 경로는 5xx 를 내지 않는다** — 집계 실패가 손님 화면을
> 흔들면 안 된다). 없는 브랜드/제품도 조용히 200 이다.

| Method | Path | body | throttle |
|---|---|---|---|
| POST | `/v1/storefront-stats/track/visit` | `{ brandId, visitorId, source }` | 120회/분 |
| POST | `/v1/storefront-stats/track/cart-add` | `{ productId, visitorId }` | 60회/분 |

> ⚠️ **전역 60회/분보다 조인 게 아니라 푼다.** 이건 폼 제출이 아니라 페이지 진입 신호라,
> 박람회 부스 와이파이·사무실·통신사 **NAT 뒤에서 한 IP가 장소 전체를 대표**한다. 60 이면 정상
> 방문자끼리 서로를 429 로 막고 그 결과가 "조용한 과소집계"라 아무도 눈치채지 못한다
> (`public-seeding.controller` 가 같은 이유로 5→20 완화한 선례). `@SkipThrottle()` 은 쓰지 않는다 —
> 인증 없는 쓰기라 상한이 아예 없으면 남용 통로가 된다.

> ⚠️ **brandId 존재 검증 쿼리를 따로 하지 않는다** — FK 가 검증이다. 없는 브랜드면 P2003 이 나고
> 서비스가 삼킨다(쿼리 1회 절약 + 제약으로 강제).

> ⚠️ 이 두 라우트는 `main.ts` 의 **Origin CSRF 가드 대상**이다(면제 목록에 없다). 브라우저는
> 상태 변경 POST 에 항상 Origin 을 보내므로 정상 동작하고, Origin 없는 호출(curl·서버간)은 403 이다.

### brand-storefront-stats.controller.ts (`@Controller('v1/brand/storefront-stats')`)

> `BrandGuard` + `requireBrandId`. brandId 가 세션에서 나오므로 별도 소유 검증이 필요 없다.

| Method | Path | 기능 |
|---|---|---|
| GET | `/v1/brand/storefront-stats?days=1~90(기본 30)` | 일자별 시계열 + 전기간 합계 |

```
{ days, trackingSince,                        // 집계 시작일(최초 행). null = 아직 데이터 없음
  totals: { direct, promotion, onsite, all }, // 각각 {visits, uniqueVisits, cartAdds, uniqueCartAdds, cartConversionPct}
  series: [{ date, direct:{…}, promotion:{…}, onsite:{…}, all:{…} }] }   // dense 제로필
```

- **dense 제로필** — 데이터 없는 날이 배열에서 빠지면 차트가 그 구간을 이어 그려 추이를 왜곡한다
  (2026-08 추이 3종에서 실제로 났던 버그 클래스).
- 데이터가 없어도 경로 4칸을 **항상** 채운다(빈 경로가 빠지면 프론트가 옵셔널 체이닝 범벅이 된다).
- `cartConversionPct` 는 `uniqueVisits === 0` 이면 0 이다(0 나눗셈 NaN 이 응답에 실리면 차트가 죽는다).

### admin-storefront-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`. **URL 은 기존 어드민 통계 surface 에 붙이되 코드는 이 모듈이 소유한다** — Nest 는
> 같은 prefix 컨트롤러 둘을 문제없이 매핑하고 klow_admin 클라(`lib/api/stats.ts`)는 엔드포인트를
> 한 군데서만 알면 된다. 반대로 `stats` 모듈에 넣으면 그쪽의 "어드민 KPI" 정체성이 깨진다.

| Method | Path | 기능 |
|---|---|---|
| GET | `/admin/stats/storefront-visits?days=` | 브랜드별 집계(방문 내림차순) + 전체 합계 |

## cron

`storefront-visitor-day-prune` — 매일 KST 04:30. 원장(`BrandVisitorDay`)의 100일 경과분 파기
(최대 조회 창 90일보다 넉넉히). **읽기 모델은 지우지 않으므로 과거 차트는 그대로**다.
보존기간·조건은 서비스가 소유하고 cron 파일은 스케줄만 갖는다.

⚠️ 이 cron 이 늘어 `test/app.e2e-spec.ts` 의 기대 목록이 **8개**가 됐다.

## 프론트 배선

| 앱 | 파일 |
|---|---|
| klow_web | `lib/visitor-id.ts`(난수 토큰) · `lib/storefront-track.ts`(발사 + 중복 가드) · `components/brand/BrandStorefront.tsx`(방문 effect, `source`/`promotionCode` prop) · `store/useCartStore.ts`(담기 1줄) · `lib/brand-server.ts` `resolvePromotionCode`(집계 아님, code 해석만) |
| klow_brand | `app/(authed)/stats/page.tsx` + `_components/StorefrontStatsBoard.tsx` · `_hooks/useStorefrontStats.ts` · `components/charts/{TrendChart,ChartChrome}.tsx`(할인 링크 추이 탭과 공유) |
| klow_admin | `app/(authed)/_components/StorefrontVisitSection.tsx` · `lib/api/stats.ts` |

- ⚠️ 방문 중복 가드는 **모듈 레벨 `Set`** 이다 — 컴포넌트 `useRef` 로는 StrictMode dev 이중 effect 는
  막아도 `?mode=onsite` 토글·view 전환 **remount** 에서 뚫린다. 키에 `source` 를 넣어 같은 탭에서
  경로를 바꿔 재진입한 것은 각각 잡히게 한다(그게 실제로 다른 유입이다).
- ⚠️ 담기 초크포인트는 `useCartStore.addToCart` 의 `addQty <= 0` early return **바로 다음**이다.
  그 가드가 "눌렀지만 브랜드당 5개 상한에 막혀 아무 일도 안 일어난 경우"를 자동으로 제외해 준다.
  `updateQuantity`(카트 `+`)·`replaceCart`(로그인 머지)는 이 함수를 타지 않아 유령 이벤트가 없다.
- klow_brand `TrendChart` 는 `promotions/_components/` 에서 `components/charts/` 로 옮기며
  `lines` prop 으로 일반화했다(할인 링크 1선 / 통계 3선 공용). **복사본을 만들지 말 것** — 예전에
  mini 변형으로 갈라졌다가 죽은 이력이 있다.
- klow_brand 통계는 **헤더 필의 독립 페이지 `/stats`** 다(`StudioShell active="stats"`). 스튜디오
  탭 스트립에 넣지 않은 이유: 그쪽은 브랜드관을 *편집*하는 자리라 자동저장 상태 표시와 섞이고,
  탭을 하나 늘릴 때마다 `StudioTab` union·`TABS`·렌더 분기·`?tab=` 화이트리스트 4곳을 함께
  고쳐야 한다. ⚠️ **새 최상위 보호 라우트는 `src/middleware.ts` matcher 에 반드시 넣을 것** —
  빠뜨리면 미인증 접근이 랜딩으로 튕기지 않고 빈 화면을 한 번 그린 뒤 클라 가드가 뒤늦게
  처리한다(`/onsite`·`/settlement`·`/promotions` 가 지금도 그 상태다).
- 통계 화면은 **현장 데이터가 0 이면 그 칸·선을 숨긴다**(부스를 안 하는 브랜드가 대부분).

## 배포 순서

⚠️ **klow_web → klow_server(마이그레이션 포함) → klow_brand / klow_admin.**
**할인 링크 클릭 통일 때문에 klow_web 이 먼저다** — 흔한 "서버 먼저"의 반대다.

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| **klow_web 먼저** ✅ | 신규 트래킹 POST 가 404 로 조용히 버려진다(아직 아무도 안 보는 신규 지표). 할인 링크 클릭은 **구 서버가 종전대로 계속 센다** — 유실 없음. 새 `promotionCode` 필드는 구 서버 zod 가 unknown key 로 흘려보낸다(strip). |
| klow_server 먼저 ❌ | `resolveBySlug` 가 집계를 멈췄는데 구 klow_web 은 `promotionCode` 를 아직 안 보낸다 → **이미 운영 중인 할인 링크 클릭이 통째로 유실**된다. |

- 데이터는 klow_web 배포부터 쌓인다. **백필 불가**이므로 `trackingSince` 이전은 0 이 아니라 데이터 없음이다.
- 브랜드/어드민 화면은 마지막 — 먼저 내보내면 텅 빈 차트를 보고 "통계가 안 나와요" 문의가 온다.

## 교차링크

[brands](./brands.md) · [promotions](./promotions.md)(클릭 카운터 소유권) · [stats](./stats.md)(brandActivity 오염 금지 원칙) · [products](./products.md)(`StrippedPricingKeys`)
