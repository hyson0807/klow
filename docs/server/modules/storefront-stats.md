# storefront-stats — 브랜드관 방문 통계 · 장바구니 · 결제 전환 · 판매 분석

- **모듈 경로**: `src/modules/storefront-stats/`
- **주 클라이언트**: klow_web(수집) + klow_brand `/stats`(브랜드 조회) + klow_admin 대시보드 홈 · 브랜드 상세 "브랜드관 통계" 탭(운영 조회)
- **관련 파일**: `storefront-stats.service.ts`(퍼널), `storefront-sales.service.ts`(판매 분석), `stats-window.ts`(창 규칙 공용), 컨트롤러 3개(public·brand·admin), `storefront-stats-retention.cron.ts`, `common/validation/storefront-stats.ts`
- **회귀 잠금**: `__tests__/storefront-stats.spec.ts`(퍼널) · `__tests__/storefront-sales.spec.ts`(판매 분석)

## 이 모듈이 답하는 질문

"내 브랜드관에 손님이 몇 명 들어왔고, 그 중 몇 명이 담고, 몇 명이 **샀는가**" — **유입 경로별로**.
그리고 (2026-08-19 추가) "**어느 나라에서 수요가 많고 어떤 제품이 팔리는가**" — **채널별로**.

### ⚠️ 한 화면에 모집단이 둘이다

퍼널(`storefront-stats.service.ts`)과 판매 분석(`storefront-sales.service.ts`)은 **다른 것을 센다.**
klow_brand `/stats` 가 둘을 같이 그리므로, 숫자가 안 맞는 게 정상이라는 걸 알고 있어야 한다.

| | 퍼널 | 판매 분석 |
|---|---|---|
| 출처 | `BrandDailyStat`(읽기 모델) | `Order`/`OrderItem`(원장) |
| 모집단 | **그날 브랜드관을 거친 방문자**의 결제만 | **결제 완료된 전 주문** |
| `/shop`·검색 유입 | 제외 | 포함 |
| 자사몰 임베드·브랜드 상품 링크(`?brand=`) | **포함**(2026-08-20~) | 포함 |
| 현장(부스 QR) | **제외**(수집 안 함) | 포함 |
| 환불 주문 | 차감 안 함 | **제외**(`paymentStatus='paid'`) |
| 날짜 버킷 | 원장 행의 날짜(방문일) | **`paidAt`**(결제일) |
| 소급 | 불가(집계 시작일부터) | 가능(전 기간) |
| 단위 | 명(순 인원) | 건 / 개 |
| 국가 축 | 손님이 **고른** 기준국(방문 국가 TOP) | `Order.countryCode`(국가 TOP) |

⇒ 같은 탭의 "결제 48명"과 "국가 합계 63건"은 **서로 다른 숫자이며 그게 정상**이다.

> ⚠️ **화면에는 이 설명이 없다.** 처음엔 두 섹션에 모집단을 한 줄씩 깔았는데 각주가 길어
> 걷어냈다(2026-08-19). 즉 숫자가 왜 다른지는 **이 문서와 코드 주석에만** 남아 있으니,
> "결제 수가 안 맞는다"는 문의가 오면 위 표로 답한다. 되살릴 자리는
> klow_brand `StorefrontStatsBoard.tsx` 의 요약 카드 아래와 랭킹 섹션 아래다.

이전에는 유입을 세는 곳이 `PromotionDailyStat` 하나뿐이었고 그건 **할인 링크로 들어온 트래픽만**
잡았다. 브랜드관 루트로 직접 들어온 손님(SNS 프로필 링크·QR·검색·자사몰 경유)은 어디에도
기록되지 않았다.

## 데이터 모델

| 모델 | 역할 |
|---|---|
| `BrandDailyStat(brandId, date, source)` @unique | **읽기 모델**. 브랜드 × 날(KST) × 유입경로 1행에 `visits`/`uniqueVisits`/`cartAdds`/`uniqueCartAdds`/`purchases`/`uniquePurchases`. **차트는 이것만 읽는다** |
| `BrandVisitorDay(brandId, date, visitorId)` @unique | **판정 원장**. "그날 처음인가?"를 유니크 제약으로 원자적으로 답하는 게 유일한 일. `source`(그날 첫 진입 경로) + `carted` + `purchased` 보유 |
| `Order.visitorId` (VarChar 64, nullable) | 결제 단계의 **귀속 키**. 주문 생성 시 klow_web 이 실어 보내고, 결제 확정 때 원장 조회에 쓴다 |
| `BrandVisitorCountryDay(brandId, date, source, countryCode)` @unique | **읽기 모델**. 국가별 `visitors`(순방문, 명). 아래 "방문 국가" 절 |
| `BrandVisitorDay.countryCode` (VarChar 2, nullable) | 국가 귀속 마커. `carted`/`purchased` 와 같은 역할 — null→값 전이 1회만 카운터를 올린다 |

`enum StorefrontVisitSource = direct | promotion | onsite` — ⚠️ **`onsite` 는 묘비다**(수집·보고 모두 안 함, 아래 절).

마이그레이션 `20260819025346_add_brand_storefront_stats` 는 `CREATE TYPE` + `CREATE TABLE` 2개뿐
(기존 테이블 ALTER 0) → **롤링 배포 안전 · 백필 없음**(과거 방문 기록은 존재하지 않는다).

> ⚠️ **누적 카운터를 `Brand` 에 두지 않았다.** `Brand.updatedAt` 은 `@updatedAt` 이라 방문마다
> `brand.update` 를 치면 **방문자 트래픽이 브랜드를 bump** 하고 `stats.service.ts` 의
> `brandActivity()` 가 "브랜드가 아무것도 안 했는데 활성"으로 센다 — 그 파일이
> `Promotion.updatedAt`·`Brand.updatedAt` 을 활동 소스에서 **의도적으로 제외**해 둔 원칙을
> 정면으로 깬다. 전기간 합계는 `@@unique` 위 groupBy 한 방이라 비싸지도 않다.
> 회귀 잠금이 스텁의 `brand.update`/`upsert` 미호출을 단언한다.

## 진입 경로 (`source`)

`BrandStorefront` 를 렌더하는 라우트는 **정확히 3개**, 읽는 쿼리 파라미터는 `mode=onsite` 하나뿐
(그 쿼리는 이제 "집계하지 않는다"는 신호로만 쓰인다).

| klow_web 라우트 | URL | source |
|---|---|---|
| `app/[brandSlug]/page.tsx` | `/{slug}` | `direct` |
| `app/[brandSlug]/[influencer]/page.tsx` | `/{slug}/{promotionSlug}` | `promotion` |
| `app/brand/[id]/page.tsx` | `/brand/{id}` | `direct` — 레거시. slug 가 있으면 `/{slug}` 로 replace |
| (1번 + 쿼리) | `/{slug}?mode=onsite` | **집계 안 함** — 아래 절 참고 |

`source` 는 **라우트가 prop 으로 내려준다** — 클라가 pathname 세그먼트로 넘겨짚으면 예약 슬러그
·리다이렉트가 끼는 순간 조용히 틀린다. `useAppStore.promotionCode` 도 보지 않는다(localStorage
영속이라 한 번 할인 링크로 왔던 사람이 나중에 직접 들어와도 영원히 promotion 으로 잡힌다).

### ⚠️ 현장(부스 QR)은 집계 대상이 아니다

`?mode=onsite` 진입은 방문·담기 비콘을 **아예 쏘지 않는다**(klow_web `BrandStorefront` /
`useCartStore`). 이유:

- 부스 QR 은 손님이 **이미 눈앞에 있는 POS 흐름**이지 온라인 유입이 아니다. 같은 칸에 넣으면
  "브랜드관에 얼마나 오나"의 답이 오프라인 행사 유무로 출렁인다.
- 부스 **공용 태블릿은 브라우저가 하나**라 손님 여럿이 순방문 1로 눌린다 — 합계를 통해
  일반·할인 링크 지표까지 오염시킨다.
- 부스 실적은 `Order.channel='onsite'` 로 **정산·주문 화면에 이미 잡힌다.** 빼도 잃는 게 없다.

⚠️ **조회에서도 `source: { in: ['direct','promotion'] }` 로 거른다.** 과거 행과 배포 창의 구
프론트가 `onsite` 행을 남길 수 있는데, 안 거르면 **화면 어느 칸에도 없는 값이 합계에만 섞여**
`일반 + 할인 링크 ≠ 합계` 가 된다(브랜드가 설명을 들을 방법이 없다).
⚠️ 서비스에 **2차 방어**(`reportedSource()` 로 모르는 source 는 skip)도 있다 — where 가 빠지면
`bucket[source]` 가 undefined 라 읽기 경로가 통째로 죽는다.
⚠️ prisma enum 의 `onsite` 값은 **묘비로 남긴다**(Postgres enum 값 제거는 타입 재생성이 필요하고
과거 행이 그 값을 참조한다).

### 제품 상세(PDP)도 수집 지점이다 (2026-08-20~)

브랜드 피드백 — "브랜드관으로 들어가야만 집계된다". 자사몰 카페24 임베드 버튼이 보내는
`/product/{id}?brand={slug}` 유입이 방문뿐 아니라 **담기·결제까지** 통째로 빠지고 있었다
(담기 게이트가 원장 행을 요구하고 `Order.visitorId` 도 방문 비콘이 만든 토큰에 달려 있다).

| klow_web 라우트 | URL | source |
|---|---|---|
| `app/product/[id]/page.tsx` | `/product/{id}?brand={slug}` | `direct` (귀속은 **productId**) |

- **게이트는 `?brand=` 유무 하나**다. `/shop`·검색을 둘러보다 스쳐간 조회는 안 센다 — PDP 가
  국가 선택 모달에 이미 쓰는 조건(`useGuestCountryPrompt(brandMode && …)`)과 **같은 잣대**다.
- **새 `source` 값을 만들지 않고 `direct` 에 합쳤다** — 그 덕에 prisma enum·`REPORTED_SOURCES`·
  응답 shape·klow_brand·klow_admin 이 전부 무변경이고 마이그레이션도 없다.
- ⚠️⚠️ **귀속 키는 `productId` 다. URL 의 슬러그를 쓰면 안 된다** — 주소창에서 바꿀 수 있어
  `/product/{A사 제품}?brand={B사}` 로 남의 방문수를 부풀리는 통로가 된다. 슬러그는 **클라의
  게이트로만** 쓰고, 서버가 `Product.brandId` 로 해석한다(담기 비콘과 같은 방식).
- ⚠️ 브랜드관 그리드의 상품 링크에도 `?brand=` 가 붙어 **임베드 URL 과 형태가 같다**(구별 불가).
  그래서 klow_web 이 모듈 레벨 `visitedBrands` 로 **그 탭에서 그 브랜드를 아직 안 봤을 때만**
  PDP 방문을 센다. 순방문(명)은 원장 유니크 제약이라 이 가드가 없어도 정확하고, 가드가 지키는
  건 `visits`(회)의 의미와 요청 수뿐이다 — 새 탭·새로고침 누수를 더 메우려 들지 말 것.
- ⚠️ **담기가 방문 비콘을 기다린다**(`pendingVisit`). 딥링크 PDP 는 담기 버튼이 활성화되는
  순간이 방문 POST 를 쏘는 순간과 거의 같아서, 안 기다리면 **이 기능이 살리려던 바로 그 담기가
  원장 행보다 먼저 도착해 버려진다**. **국가 비콘도 같은 이유로 같이 기다린다.**
- ⚠️⚠️ **국가 dedupe 키를 `productId` 로 되돌리지 말 것.** 그 축이면 `trackStorefrontProductVisit`
  이 "브랜드관에서 국가를 고른 뒤 제품 5개 클릭 = 헛 POST 5개"를 막으려고 게이트 **앞**에서
  키를 찍게 되고, 그 순간 **국가를 나중에 고른 딥링크 PDP 손님의 국가가 영원히 전송되지
  않는다**(2026-08-20~21 실제 버그 — 임베드 유입 국가가 100% '미상'이었다). 축은 브랜드
  문맥이어야 하고, 표시는 실제 전송과 같은 경로에서만 한다("프론트 배선" 절).

**여전히 브랜드관이 아닌 것**: `?brand=` 없는 PDP(`/shop`·검색 경유), 시딩 `/seed/{token}`.

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
⚠️ 클릭은 `source` 로 게이트하지 **않는다** — 판정 키는 `promotionCode` 하나다(이 지표는
"링크가 몇 번 눌렸나"다). 단 현장 진입은 비콘 자체를 안 쏘므로 클릭도 잡히지 않는다.
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
- ⚠️ **토큰을 새로 만드는 건 방문 비콘(`getVisitorId`)뿐이고, 담기·결제는 `peekVisitorId`
  (있으면 읽고 없으면 만들지 않음)를 쓴다.** 방문 비콘은 **두 곳**에서 나간다 — 브랜드관과
  브랜드 문맥 PDP(2026-08-20~). 그 둘 다 안 거친 손님(`/shop`·검색)의 담기·결제는 어차피
  원장이 없어 서버가 버리므로, 거기서 발급하면 통계에 잡히지도 않는 추적 식별자만 남는다.
- klow_web `lib/visitor-id.ts` 는 **저장소를 못 쓰면 null 을 돌려주고 트래킹을 통째로 건너뛴다** —
  매번 임시 id 를 만들면 순방문이 방문수까지 부풀어 오른다(조용히 틀린 숫자보다 조용히 빠진
  숫자가 낫고, `visits` 도 함께 빠지므로 두 지표의 비율은 유지된다).

**신뢰성 한계**: localStorage 삭제·시크릿 창·다른 브라우저는 새 방문자로 잡혀 **순방문 과대**,
애드블록은 방문 자체가 안 잡혀 **전체 과소**. 추세 지표로는 충분하나 **정산·투자자 감사 지표로
쓰지 말 것**. 개인정보 측면에서는 IP·UA·계정을 저장하지 않고 난수 토큰만 쓰며 cron 이 파기한다.

⚠️ 부스 공용 태블릿이 순방문을 누르는 문제는 **현장을 집계에서 통째로 뺐기 때문에** 더는
해당되지 않는다(위 절 참고).

## ⚠️ 담기 게이트 — 퍼널 정의

`recordCartAdd` 는 원장에 `(brandId, date, visitorId)` 행이 **이미 있을 때만** 집계하고, 없으면
아무것도 하지 않는다.

- 이게 "브랜드를 거친 사람이 담는가"라는 정의 그 자체다. `/shop`·검색에서 담은 건은 방문
  모집단 밖이라 빠진다.
- ⭐ **자사몰 임베드 PDP 는 2026-08-20 부터 빠지지 않는다** — PDP 방문이 원장 행을 만들면서
  그 뒤의 담기·결제가 처음으로 집계에 들어온다. **이 변경의 실질 가치가 여기다**(방문수보다).
- 덕분에 **`uniqueCartAdds ≤ uniqueVisits` 가 구조적으로 보장**돼 전환율에 `min(100, …)` 클램프가
  필요 없다(클램프는 정의가 틀렸다는 신호를 숨길 뿐이다).
- 귀속 경로는 **그 방문자의 그날 첫 진입 경로**(원장 행의 `source`)다 — 담기 시점의 URL 이 아니다.
  그래야 "할인 링크로 온 사람의 전환율"이 말이 된다.

⚠️ **순 카운터(`uniqueCartAdds`/`uniquePurchases`)의 판정은 읽은 값이 아니라 조건부 `updateMany`
가 실제로 1행을 뒤집었는지로 한다.**

```ts
const firstCartAdd = led.carted ? false : (await updateMany({
  where: { brandId, date, visitorId, carted: false },   // ← 조건이 판정 그 자체
  data:  { carted: true },
})).count === 1;
```

읽고 → 분기 → 쓰기로 하면 같은 방문자의 담기 2건(다른 제품)이 동시에 인플라이트일 때 **둘 다
`carted:false` 를 보고 순담기자를 2 올린다** — 위에서 "구조적으로 보장된다"고 한 부등식이 깨져
전환율이 100% 를 넘고, 클램프가 없으니 그대로 화면에 나간다. 왕복 수는 종전과 같다(이미 담은
사람이면 조건이 0건이라 아예 쏘지 않는다). 결제 쪽 `purchased` 와 **함의된 담기** flip 도 같은
형태이며, 함의된 담기는 flip 이 실패하면(동시에 담기 비콘이 이겼다면) 그쪽이 이미 세었으므로
카운터를 올리지 않는다. 회귀 잠금은 스펙의 `동시 담기 2건 …` / `동시 결제 2건 …` 두 케이스다
(`Promise.all` 이 두 호출을 await 지점에서 번갈아 돌려 실제 경합을 재현한다).

⚠️ **brandId 는 서버가 `productId` 로 해석한다** — 공개 제품 응답에는 `brandId` 가 없다
(`pricing/price-line.ts` 의 `StrippedPricingKeys` 가 의도적으로 벗긴다). 그 strip 목록은 건드리지
않았고, `CartLine` 에 필드를 더하는 대안도 기각했다(`persist`+`migrate` 를 가진 **영속 스키마**라
분석 부수효과 하나 때문에 결제 경로를 건드릴 이유가 없다).


## 결제 단계 (2026-08-19 추가)

퍼널이 `방문자 → 장바구니 → **결제**` 로 늘었다. 정의는 담기와 같은 모집단이다 — **그날(±1일)
그 브랜드관을 거친 방문자의 결제 완료 주문만** 센다.

### ⚠️ 집계 지점이 클라가 아니라 서버(`markPaid`)인 이유

방문·담기는 klow_web 클라이언트가 비콘으로 보내지만 **결제는 서버가 센다.** 결제 성공 화면
(`/checkout/redirect`)에서 비콘을 쏘는 방식은 이 코드베이스가 이미 크게 데인 패턴이다 —
결제 확정 자체가 거기의 fire-and-forget 클라 호출이었다가 QR·인앱 브라우저 왕복에서 유실돼
**카드는 승인됐는데 주문이 `pending` 에 남는** 사고를 냈다([payment](./payment.md) "3중 방어선").

`payment.service.markPaid` 의 `count === 1` 분기는 `updateMany` 로 `pending → paid` 를 DB 레벨에서
한 번만 성립시키는 자리이고, **클라 verify · 웹훅 · `payment-reconcile` 크론 세 경로가 모두 여기로
모인다.** 그래서 `recordPurchase` 는 그 블록의 **맨 앞**에 있다 — 뒤(송장 발급 EFS 왕복·알림톡)에
두면 그쪽이 느려지거나 죽었을 때 결제 집계만 조용히 사라진다.

`markPaid` 가 유일한 전이 지점인 것도 확인했다. `paymentStatus='paid'` 를 쓰는 다른 곳은 전부
`where` 절이거나, 시딩 주문을 처음부터 paid 로 만드는 `seeding.service`(→ `isSeeding` 으로 제외)다.
어드민 "수동 결제완료 처리" 엔드포인트는 **일부러 없다**(`orders.service` 주석).

### ⚠️ 원장 조회는 주문일과 그 전날, **2일**을 본다

같은 날만 보면 두 부류가 통째로 빠진다:

- **KST 자정(= 11:00 ET)이 미국 손님의 쇼핑 시간 한복판**이라 방문과 결제가 날짜를 넘긴다.
- 카트가 localStorage 영속이라 **어제 담아둔 손님은 오늘 `/{slug}` 를 다시 거치지 않는다.**

버킷은 **주문일이 아니라 원장 행의 날짜**로 잡는다 — 그래야 "그날 방문한 사람 중 몇 명이 샀나"
라는 코호트 의미가 유지되고 `uniquePurchases <= uniqueVisits` 가 안 깨진다(주문일로 잡으면 방문이
0 인 날에 결제가 찍혀 클램프가 필요해진다). 조회는 기존 유니크 인덱스 위 point read 2회라
**새 인덱스가 필요 없다**. 한계: **직전 방문이 이틀 이상 지난 결제는 집계되지 않는다.**

### ⚠️ 결제는 담기를 **함의한다**

`carted=false` 인 방문자가 결제하면 담기 카운터(`cartAdds`/`uniqueCartAdds`)도 함께 올린다.

klow_web 은 카트가 비면 체크아웃을 못 하고 모든 담기 경로가 `useCartStore.addToCart` 하나를
지나므로, **`carted=false` 인 결제자는 "안 담은 사람"이 아니라 담기 비콘이 유실됐거나(애드블록·
저장소 차단) 전날 담은 사람**이다. 이 캐리포워드 덕에 클램프 없이 성립한다:

`uniquePurchases <= uniqueCartAdds <= uniqueVisits` 그리고 `uniqueCartAdds <= cartAdds`

⚠️ 반대로 `led.carted` 를 결제의 **조건**으로 걸면 안 된다 — 서버가 아는 사실(실제 결제)을
클라 비콘의 도달 여부에 종속시키는 것이라, **실제로 산 사람이 화면에서 사라진다.**
⚠️ `cartAdds`(회)도 같이 올린다. `uniqueCartAdds` 만 올리면 어드민이 나란히 보여주는
`uniqueCartAdds <= cartAdds` 가 깨진다.

### 안 세는 것

| 대상 | 이유 |
|---|---|
| 현장(`channel='onsite'`) | 방문·담기와 같은 원칙(부스는 POS 흐름). klow_web 이 `/checkout/onsite` 에서 `visitorId` 를 아예 안 보내고, 서버도 채널로 한 번 더 막는다 |
| 시딩(`isSeeding`) | 무가 주문 |
| `visitorId` 없는 주문 | `/shop`·검색 유입, 저장소 차단 브라우저, 배포 창의 구 klow_web |
| **환불·취소** | **차감하지 않는다.** `uniquePurchases` 는 불리언 플래그라 "그날 다른 결제가 또 있었나"를 답할 수 없어 정확한 차감이 불가능하고, 차감하면 과거 버킷이 사후에 움직여 브랜드가 어제 본 숫자와 오늘 본 숫자가 달라진다. 매출 정본은 정산 화면이다 |

⚠️ **부스에서 만난 손님은 사라질 수 있다** — 그날 첫 진입이 `?mode=onsite` 였으면 원장 행의
`source` 가 `onsite` 라, 나중에 온라인 결제해도 `REPORTED_SOURCES` 필터에 걸려 어느 칸에도 안 뜬다.
방문·담기가 이미 그렇게 동작하므로 일관되지만, 알고는 있어야 한다.

⚠️ **자사몰(카페24) 임베드는 2026-08-20 부터 PDP 진입 시점에 이미 잡힌다**(그전엔 "바로구매"로
`/{slug}` 에 push 됐을 때만 잡혔다).

⚠️ **임베드 PDP 를 먼저 본 사람은 그날 귀속이 `direct` 로 고정된다.** 오전에 임베드 PDP 로 들어와
원장 행이 `direct` 로 생기면, 오후에 할인 링크로 브랜드관에 와서 결제해도 그 결제는 `promotion`
이 아니라 `direct` 에 잡힌다(원장 유니크 키에 source 가 없고 "그날 최초 진입 경로"가 기준이다).
그 결과 **"할인 링크 추이: 클릭 1" 인데 "할인링크 탭: 방문자 0"** 으로 두 화면이 어긋나 보일 수
있다. 위 부스 사례와 같은 성질이고, 고치려면 마지막-쓰기-승이 필요한데 그건 읽기 모델에 감산을
요구해 음수 카운터를 만든다(이 모듈이 기각한 방향). 회귀 스펙이 이 동작을 **의도된 손실로
명문화**해 두었다.

### ⚠️ `Order.visitorId` 도 원장과 함께 파기한다

`pruneVisitorDays()` 가 원장 100일 경과분을 지울 때 **같은 커트라인의 `Order.visitorId` 도 null 로
지운다.** 주문 행은 영구 보존인데다 이름·이메일·주소를 들고 있어서, 그대로 두면 익명 토큰이
**영구적으로 실명과 연결**된다 — "IP·UA·계정과 연결하지 않고 cron 이 파기한다"는 이 모듈의 약속을
조용히 뒤집는 셈이다. 원장이 사라지면 조인 대상도 없어 분석 가치가 0 이고, `recordPurchase` 는
늘 이 시점보다 한참 전에 끝난다.

### 신뢰성 한계 (브랜드 안내용)

**이 숫자는 브랜드의 실제 주문 건수보다 적다.** `/shop`·검색 직행으로 산 주문은 방문 모집단
밖이고, 이틀 이상 지난 방문의 결제도 빠진다(자사몰 임베드 PDP 는 2026-08-20 부터 포함). **정산·주문 화면의 숫자와 다른 게 정상**
이며, 그쪽이 매출의 정본이다.

## 방문 국가 (2026-08-20)

"결제하지 않은 방문자는 **어느 나라에서 오는가**". 종전엔 국가 지표가 판매 분석의
`Order.countryCode` 하나뿐이라 **산 사람의 나라만** 보였다.

### 국가의 출처 = 손님이 **고른** 값

`useAppStore.country` — klow_web 국가 선택 모달에서 손님이 직접 고른 배송/가격 기준국이다.
브랜드관 진입 시 비로그인 + `country == null` 이면 모달이 자동으로 뜬다(`useGuestCountryPrompt`).

⚠️ **GeoIP 를 쓰지 않는다.** 이 서버엔 `cf-ipcountry` 류를 읽는 코드가 아예 없고(IP·UA 를
저장하지 않는다는 이 모듈의 약속), VPN·통신사 라우팅에서 틀린다. 무엇보다 **고른 값은 이미
가격·언어·배송비를 좌우하는 정본**이라, 두 번째 추정 국가를 두면 같은 화면 안에서 국가가 두
벌이 되고 판매 분석의 국가 랭킹과 비교가 불가능해진다.
⚠️ **`navigator.language` 추정도 안 쓴다.** `OnboardingModal` 이 초기 하이라이트에만 쓰고
저장하지 않는 값이며, en-US 기본 브라우저를 쓰는 베트남 손님이 미국으로 잡힌다.
⚠️ **klow_web 에서 `?? DEFAULT_COUNTRY('US')` 폴백을 걸면 안 된다.** 가격 조회가 미선택을 US 로
폴백하는 건 조회 편의지만, 지표에서 그 폴백은 **"모른다"를 "미국이다"로 바꾸는 조작**이다 —
브랜드가 있지도 않은 미국 수요를 보고 마케팅비를 쓴다. 안 보내고 '미상'으로 남긴다.

### 저장 2축 — 원장 마커 + 읽기 모델

| | 역할 |
|---|---|
| `BrandVisitorDay.countryCode` | **판정**. null→값 전이가 곧 "이 방문자를 셌다" |
| `BrandVisitorCountryDay` | **읽기 모델**. 차트/랭킹은 이것만 읽는다 |

⚠️ **원장을 groupBy 해서 쓰지 않는 이유**: 원장은 `pruneVisitorDays()` 가 **100일**에 파기하는데
조회 창은 `days='all'` 에서 **365일**까지 간다. 원장 집계로 만들면 `전체` 가 조용히 최근 100일만
가리킨다 — "지금은 되고 100일 뒤에 조용히 틀려지는" 실패다. `BrandDailyStat`(안 지움) ↔
`BrandVisitorDay`(지움)로 이미 갈라 둔 구조 그대로다.
⚠️ **그래서 prune 에 이 테이블을 추가하면 안 된다.**
⚠️ `BrandDailyStat` 에 국가를 안 붙인 이유: 유니크 키에 국가가 들어가면 기존 퍼널 카운터 6개가
전부 국가별로 쪼개져 마이그레이션이 파괴적이 된다.
⚠️ `countryCode` 에 **`ShippingCountry` FK 를 걸지 않는다** — 온보딩 국가 목록(115개)과
`ShippingCountry`(234행)가 갈릴 수 있고, FK 면 그 순간 기록 경로가 throw 한다.

### ⚠️ 첫-쓰기-승 — 감산이 없는 설계

```ts
if (led.countryCode) return;                    // 이미 귀속됨 → 끝(왕복도 아낀다)
const flipped = await updateMany({
  where: { brandId, date, visitorId, countryCode: null },   // ← 조건이 판정 그 자체
  data: { countryCode },
});
if (flipped.count !== 1) return;                // 경합에서 졌다 → 저쪽이 이미 셌다
await this.bumpCountry(brandId, date, led.source, countryCode);
```

**마지막-쓰기-승으로 바꾸지 말 것.** 국가를 바꾸면 옛 국가 −1 이 필요한데, 읽기 모델은
트랜잭션 없는 increment upsert 라 lost update 에서 **음수 카운터**가 나오고 이 모듈엔 클램프가
없다. 질문 자체도 "그날 이 방문자는 어느 나라 손님인가"라 첫 값 고정이 의미상 맞다
(`source` 가 "그날 첫 진입 경로"인 것과 같은 규칙).
⇒ **한계: 같은 날 국가를 바꾸면 그날 지표엔 반영되지 않는다**(다음 KST 날짜부터).

판정을 읽은 값이 아니라 **조건부 `updateMany` 의 `count === 1`** 로 하는 이유는 담기·결제와
같다 — 읽고→분기→쓰기면 같은 방문자의 국가 이벤트 2건(탭 2개·모달 재선택)이 동시에
인플라이트일 때 둘 다 `null` 을 보고 `visitors` 를 2 올려 **Σ국가 > uniqueVisits** 가 된다.

⚠️ **국가 이벤트는 `visits`/`uniqueVisits` 를 절대 건드리지 않는다**(`bumpDaily` 미호출).
올리면 국가를 고른 손님만 방문이 2로 세어진다.
⚠️ **방문 비콘을 재발사하는 방식이 아니다** — 그러면 `visits` 가 +1 된다. "이번엔 안 올려도
된다"는 플래그를 주는 대안은 공개 비콘이 *얼마나 올릴지*를 클라가 주장하게 만드는 것이라,
`unique` 필드를 API 에서 아예 뺀 이 모듈의 원칙과 어긋난다.

### '미상' 은 서버가 뺄셈으로 파생한다

`iso2: null` 행의 값 = `max(0, totals[source].uniqueVisits − Σ그 source 의 국가 visitors)`.

- 클라가 빼게 두면 요약 카드의 방문자 수와 랭킹 합계가 화면에서 어긋나 보이는데 원인을 화면만
  보고는 알 수 없다. 서버가 **같은 창·같은 `source` 필터**에서 파생하면
  `랭킹 합계 == 요약 카드 방문자` 가 구조적으로 성립한다.
- **0 이면 행을 만들지 않는다**(유령 "미상 0명" 금지).
- source 별로 각각 낸다 — 그래야 탭별 합이 그 탭의 `uniqueVisits` 와 정확히 맞는다.

⚠️ **초기에는 미상이 1위일 것이다.** 원인 3가지: ① 집계 시작 전 방문은 영원히 미상(백필 불가)
② 모달을 닫은 게스트 ③ klow_web 배포 이후에야 채워지기 시작. "국가별로 안 나온다"는 문의가
오면 이 셋이 답이다.

### 일자별 시리즈 · 직전 기간 비교

`points` 는 **`series` 와 같은 길이·순서**의 dense 배열이고, `prevVisitors` 는 **직전 동일 길이
기간**의 합이다(`previousWindow()` — 창 바로 앞, 닫힌 구간).

- 화면이 이 둘로 **누적 영역 차트 + 순위표**를 한 카드에 그린다. 색 점이 차트 조각을 가리키므로
  차트와 표는 반드시 **같은 출처**여야 한다.
- ⚠️ 미상은 **일자별로도** 같은 뺄셈을 한다(`그날 uniqueVisits − 그날 국가 합`). 기간 합계만
  맞추고 일자를 안 맞추면 누적 영역의 그날 높이가 그날 방문자 수와 어긋난다.
- ⚠️ 직전 기간에만 있던 국가는 **행으로 나오지 않는다**(랭킹은 현재 기간 기준). "사라진 국가"는
  화면에서 볼 수 없다 — 의도된 한계다.
- ⚠️ 집계 시작 직후엔 직전 기간에 기록이 없어 전부 `신규` 로 보인다. 0 이 아니라 데이터 없음이다.

### ⚠️ 한 화면에 국가 랭킹이 둘이다

| | 방문 국가 TOP | 국가 TOP |
|---|---|---|
| 출처 | `BrandVisitorCountryDay` | `Order`/`OrderItem` |
| 모집단 | 브랜드관을 거친 **방문자** | 결제 완료된 **전 주문** |
| 단위 | **명** | **건** |
| 국가의 의미 | 손님이 **고른** 기준국 | 온라인=배송국 / 현장=가격 기준국 |

제목·단위가 갈라져 있어 구분은 되지만 **이 변경의 최대 혼동 위험**이다. 위 표는 이 문서
§"한 화면에 모집단이 둘이다" 의 국가 축 버전이다.

## 라우트

### public-storefront-stats.controller.ts (`@Controller('v1/storefront-stats')`)

> 가드 없음 — 공개 트래픽. `@HttpCode(200)`, 응답은 항상 `{ ok: true }`
> (**서비스가 모든 예외를 삼키므로 이 경로는 5xx 를 내지 않는다** — 집계 실패가 손님 화면을
> 흔들면 안 된다). 없는 브랜드/제품도 조용히 200 이다.

> ⚠️ **기록 메서드 3종은 각자 바깥 try/catch 를 가진다** — callee 들이 알아서 삼키는 데 기대지
> 않는다. 그 계약이 구현 세부에 걸려 있으면 나중에 한 줄만 추가돼도 공개 비콘이 500 을 낸다.

> ⚠️ **삼킨 예외의 로그 레벨은 경로마다 다르다.** 방문·담기는 `debug`(고 QPS 라 시끄러워진다),
> **결제는 `warn` + `Sentry.captureException`** 이다 — 건수가 적어 로그가 넘칠 일이 없고, 유실이
> 곧 "브랜드 매출이 없는 것처럼 보임"이라 조용히 실패하면 아무도 눈치채지 못한다
> ([payment](./payment.md) 3중 방어선에서 조용한 분기를 전부 Sentry 로 배선한 것과 같은 이유).

| Method | Path | body | throttle |
|---|---|---|---|
| POST | `/v1/storefront-stats/track/visit` | `{ brandId ⊕ productId, visitorId, source }` | 120회/분 |
| POST | `/v1/storefront-stats/track/cart-add` | `{ productId, visitorId }` | 60회/분 |
| POST | `/v1/storefront-stats/track/country` | `{ brandId ⊕ productId, visitorId, countryCode }` | 120회/분 |

> ⚠️ `brandId` 와 `productId` 는 **정확히 하나만** 온다(zod `superRefine`). 브랜드관은 전자,
> 제품 상세는 후자다 — PDP 는 brandId 를 알 수 없다(`StrippedPricingKeys`).
> `z.union` 이 아니라 `superRefine` 인 이유: union 은 400 바디에 중첩 `unionErrors` 를 통째로
> 실어 보내지만 이건 issue 1개다.

> `track/visit` 은 `countryCode?` 를 **함께** 받는다(마운트 시점에 이미 고른 손님 — 흔한 경로에
> 요청을 더 만들지 않는다). `track/country` 는 **방문 뒤에 고른 경우** 전용이다.

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
| GET | `/v1/brand/storefront-stats?days=1~90\|all(기본 30)` | 유입 퍼널 — 일자별 시계열 + 창 합계 |
| GET | `/v1/brand/storefront-stats/sales?days=1~90\|all(기본 30)` | 판매 분석 — 채널×국가/제품/일자 집계 |

```
{ days, trackingSince,                        // 집계 시작일(최초 행). null = 아직 데이터 없음
  totals: { direct, promotion, all },        // 각각 {visits, uniqueVisits, cartAdds, uniqueCartAdds, cartConversionPct,
                                             //        purchases, uniquePurchases, purchaseConversionPct}
  series: [{ date, direct:{…}, promotion:{…}, all:{…} }],  // dense 제로필 (onsite 키는 없다)
  countries: [{ source, iso2, nameKo, visitors, prevVisitors, points }] }  // 방문 국가 — 아래 절
```

- **dense 제로필** — 데이터 없는 날이 배열에서 빠지면 차트가 그 구간을 이어 그려 추이를 왜곡한다
  (2026-08 추이 3종에서 실제로 났던 버그 클래스).
- 데이터가 없어도 경로 4칸을 **항상** 채운다(빈 경로가 빠지면 프론트가 옵셔널 체이닝 범벅이 된다).
- ⚠️ **`trackingSince` 는 화면에 반드시 노출한다.** 차트는 집계 시작 전 구간도 0 으로 평평하게
  그리므로, 안내가 없으면 브랜드가 "그때는 아무도 안 왔구나"로 읽는다(백필 불가라 0 이 아니라
  **기록이 없는 기간**이다). klow_brand `StorefrontStatsBoard` 는 `trackingSince` 가 조회 창
  안쪽일 때만 각주를 띄운다 — 창의 시작일은 dense 시리즈의 첫 날(`series[0].date`)이라 클라에
  KST 날짜 계산을 복제하지 않는다.
- `cartConversionPct` 는 `uniqueVisits === 0` 이면 0 이다(0 나눗셈 NaN 이 응답에 실리면 차트가 죽는다).
- `purchaseConversionPct` 의 분모도 **`uniqueVisits`** 다(`uniqueCartAdds` 아님) — 두 전환율이 분모를
  공유해야 "들어온 사람 중 몇 %"로 나란히 읽힌다.

#### `days=all` 과 창 규칙 (`stats-window.ts`)

`'all'` = **첫 데이터부터 오늘까지, 365일 클램프**(`STATS_ALL_MAX_DAYS`). 두 조회가 같은 헬퍼
(`resolveStatsWindow`)를 쓴다 — 창 규칙이 갈리면 토글은 하나인데 두 섹션이 다른 기간을 가리킨다.

> ⚠️ **클램프의 이유는 성능이 아니라 정합성이다.** 창이 무한히 길어지면 dense 시리즈도 같이
> 길어지는데, `totals` 를 창과 다른 범위에서 뽑는 순간 "합계는 100인데 그래프를 다 더하면 80"이
> 된다. 창을 자르고 **`totals` 도 같은 창에서** 뽑으면 `totals == Σseries` 가 늘 성립한다.

> ⚠️ **집계 하한(`statsWindowStart`)도 같은 상한만큼 거슬러 간다.** 하한 없이 전부 뽑고 창만
> 나중에 자르면 국가·제품 합계에는 창 밖 주문이 섞여 일별 합과 갈라진다. 두 함수는 **같은
> `now`** 를 받아야 한다 — 요청이 KST 자정을 걸치면 집계 경계와 창 경계가 하루 어긋난다.

> ⚠️ 퍼널 조회는 `'all'` 일 때만 두 쿼리를 직렬화한다(그때만 창이 `earliest` 에 달려 있다).
> 숫자 창은 종전대로 `Promise.all` 이다 — 늘 직렬로 두면 기본 경로가 옵션 하나 때문에
> Neon(싱가포르) 왕복을 한 번 더 문다.

> ⚠️ 어드민 라우트는 **`'all'` 을 일부러 안 받는다**(`StorefrontAdminStatsQuery` 별도).
> `trafficForAdmin` 이 전 브랜드를 훑는 쿼리라 창 확장을 검토한 적이 없고, 브랜드 스키마를
> 그대로 쓰면 `'all'` 이 문법상 통과하면서 **조용히 오늘 하루만** 집계된다.

#### `GET /sales` — 판매 분석 (2026-08-19 추가)

```
{ range: { from, to },                                // 창의 실제 경계('all' 은 서버가 정한다)
  dates: ['YYYY-MM-DD', …],                           // 창 전체 dense — countries[].points 의 x 축
  summary:   { direct, promotion, onsite, all },      // 각각 {orders, quantity, productCount}
  countries: [{ channel, iso2, nameKo, orders, quantity, prevOrders, points }],
  products:  [{ channel, productId, name, image, orders, quantity, prevQuantity }] }
```

> **2026-08-20**: `countries` 에 일자별 `points` 와 `prevOrders` 가 붙고 `onsiteDaily` 는 **제거**됐다.
> 화면이 결제도 방문 국가와 같은 모양(누적 영역 + 순위표)으로 그리게 되면서 현장 전용 시리즈가
> 필요 없어졌다 — 현장 탭도 국가별 조각으로 그린다.
> ⚠️ **국가 집계에 일자를 넣어 한 번에 뽑고 합계는 서버가 접는다.** 합계용 쿼리를 따로 두면 같은
> 조인을 한 번 더 훑는데다 두 값이 갈릴 여지가 생긴다(한 주문은 하루·한 국가에만 속하므로 접기가
> 정확하다).
> ⚠️ **`days='all'` 은 직전 기간을 조회하지 않는다** — 첫 결제일부터가 창이라 "그 앞"이 존재하지
> 않고, `paidAt` 인덱스가 없어 헛스캔이 비싸다. 그 탭에선 증감이 전부 `신규` 다.
> ⚠️ 직전 기간 쿼리는 **경계가 둘**이다(`>= prevStart AND < start`). 하한만 걸면 현재 기간까지
> 함께 세어 증감률이 늘 "그대로"로 나온다.

- **채널 = 주문의 성질**: `onsite`(현장) > `promotionId≠null`(할인링크) > `direct`(그 외).
  ⚠️ 퍼널의 `source`(그 방문자의 **그날 첫 진입 경로**)와 **정의가 다르다** — 할인 링크로 들어왔지만
  체크아웃까지 code 가 안 따라간 주문은 퍼널에선 `promotion`, 여기선 `direct` 다. 같은 사실의 두
  측정이지 버그가 아니다(화면이 각주로 명시). 억지로 맞추려면 방문 원장과 주문을 조인해야 하는데,
  그 순간 랭킹이 퍼널 모집단으로 쪼그라들어 이 기능의 목적(전 주문 수요 파악)이 사라진다.
- **채널별 raw 행을 한 번에 내려보낸다** — 화면의 채널 탭 전환에 **재요청이 없고**, `전체` 탭은
  클라가 채널을 합산한다(서버가 `전체` 를 따로 계산하면 부분합과 전체가 갈릴 여지가 생긴다).
  합산이 정확한 이유: 한 주문은 정확히 **하나의 (채널, 국가)** 에 속한다.
- ⚠️⚠️ **`summary` 를 서버가 내는 건 편의가 아니라 오집계 방지다.** 한 주문에 그 브랜드 제품이
  2종이면 `products` 행에 2번 나타나므로, 화면이 제품 행을 더해 "결제 건수"를 만들면 부풀려진다.
  건수는 `countries`(또는 `daily`)에서만 나올 수 있고, 그 규칙을 주석이 아니라 **응답 모양으로
  강제**한다 — 화면엔 더할 것이 남아 있지 않다. `all.productCount` 도 채널별 종수의 합이 아니라
  distinct 집합이다(온라인·현장 양쪽에서 팔린 제품이 두 번 세어진다).
- **국가명은 서버가 붙인다**(`ShippingCountry.nameKo` 상관 서브쿼리). 클라의 국가 목록
  (`useOrderableCountries`)은 `enabled=true` 만 담아서 **배송지원을 끈 국가**(현장 판매국 상당수)의
  이름이 빈칸이 된다. `countryCode` 가 null 인 legacy 주문은 `iso2:null` 로 내려가고 화면이 `미상` 표기.
- ⚠️ 일자 버킷 SQL 은 **`AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul'` 이중 캐스트**다. 한 번만 걸면
  Postgres 가 값을 KST 로 오해해 −9h 시프트하고 **00:00~09:00 KST 결제가 전날 버킷으로 밀린다**
  (`kstWeekBucketSql` 과 같은 함정 — 2026-08 추이 3종이 전부 이 버그였다).
- **국가의 의미가 채널마다 다르다** — 온라인은 배송국, 현장은 손님이 고른 **가격 기준국**(≈국적).
  전체 탭에서 섞이므로 화면이 각주로 명시한다.
- 브랜드 귀속은 `OrderItem.productId → Product.brandId` JOIN 하나(`resolveItemBrands` 와 같은 규칙).
  ⚠️ **하드 삭제된 제품의 과거 판매는 랭킹에서 사라진다** — `OrderItem` 에 Product relation 이 없어
  dangling productId 는 어느 브랜드 것인지 알 방법이 없다(퍼널 결제 집계도 똑같이 동작한다).
- 세 쿼리 모두 `GROUP BY` 결과라 행 수가 **구조적으로 유계**다(국가 ≤ 234×3 · 제품 ≤ 제품수×3 ·
  일자 ≤ 365×3). `take` 로 자르지 않는다 — 절단은 조용한 왜곡이다.
- ⚠️ **알려진 확장 한계 2가지**(지금 규모에선 문제가 아니지만 커지면 여기부터 본다):
  ① 같은 조인을 세 번 훑는다 → `GROUPING SETS` 한 방으로 합칠 수 있다(그때 `iso2=NULL` 은
  실제 값이므로 롤업 구분에 `GROUPING()` 을 쓸 것). ② **`Order` 에 `paidAt` 인덱스가 없어**
  기간이 좁아도 비용이 줄지 않는다(브랜드 제품의 전 기간 `OrderItem` 을 훑고 `paidAt` 은 사후
  필터). 필요해지면 `@@index([paymentStatus, paidAt])` 를 추가한다 — 이 기능은 마이그레이션
  없이 배포하려고 일부러 미뤘다.
- 시딩(`isSeeding`)·미결제·환불 주문은 제외.

### admin-storefront-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`. **URL 은 기존 어드민 통계 surface 에 붙이되 코드는 이 모듈이 소유한다** — Nest 는
> 같은 prefix 컨트롤러 둘을 문제없이 매핑하고 klow_admin 클라(`lib/api/stats.ts`)는 엔드포인트를
> 한 군데서만 알면 된다. 반대로 `stats` 모듈에 넣으면 그쪽의 "어드민 KPI" 정체성이 깨진다.

| Method | Path | 기능 |
|---|---|---|
| GET | `/admin/stats/storefront-visits?days=1~90(기본 30)` | 전 브랜드 집계(방문 내림차순) + 전체 합계 |
| GET | `/admin/stats/storefront/:brandId?days=1~90\|all` | 브랜드 하나의 유입 퍼널 — 브랜드 라우트와 **같은 응답** |
| GET | `/admin/stats/storefront/:brandId/sales?days=1~90\|all` | 브랜드 하나의 판매 분석 — 브랜드 라우트와 **같은 응답** |

> 아래 둘은 `seriesForBrand`/`salesForBrand` 를 **그대로** 부른다(그 메서드들은 원래 brandId 를
> 인자로 받고, 브랜드 전용이라는 제약은 brand 컨트롤러의 `requireBrandId(user)` 에만 있었다).
> 집계를 두 벌로 구현하지 않았으므로 klow_admin 브랜드 상세 탭과 klow_brand `/stats` 는
> **구조적으로 같은 숫자**를 낸다 — "우리 화면엔 47명인데 운영팀은 52명" 이 날 수 없다.

> ⚠️⚠️ **`days=all` 이 여기선 되고 위 전체 목록에선 안 된다.** 스키마가 다르다 —
> 브랜드 상세 2개는 **브랜드용 `StorefrontStatsQuery`/`StorefrontSalesQuery` 를 재사용**하고,
> 전체 목록만 `StorefrontRollupQuery`(숫자 전용)를 쓴다. 갈리는 축은 **호출자가 아니라 쿼리
> 비용**이다 — `trafficForAdmin` 은 **전 브랜드를 스캔**하고 `kstDateWindow('all')` 이 깨지지만,
> 단일 브랜드 조회는 코드경로가 브랜드 라우트와 완전히 같다(그래서 스키마 이름도 "Admin" 이
> 아니라 "Rollup" 이다). **반대로 `trafficForAdmin` 쪽에 `'all'` 을 열지 말 것.**

> ⚠️ **브랜드 상세 2개는 `storefront-visits` 가 아니라 `storefront` 밑에 있다.** 롤업은 실제로
> 방문만 담지만 이 둘은 퍼널 + **주문 원장**이라, `storefront-visits/:brandId/sales` 로 두면
> 경로가 "visits 안의 sales" 라는 거짓말을 한다(브랜드 쪽 짝인 `v1/brand/storefront-stats`
> + `/sales` 도 이미 상위를 `storefront-stats` 로 부른다).

> ⚠️ **브랜드 존재 검증을 하지 않는다** — 없는 brandId 는 0 으로 채워진 정상 응답이 되고
> (거짓말이 아니라 '데이터 없음'), 게이트는 이미 klow_admin `brands/[id]/page.tsx` 의
> `api.brands.get()` → `notFound()` 다. 검증을 넣으면 흔한 경로마다 Neon 왕복이 하나 더 붙는다.

## cron

`storefront-visitor-day-prune` — 매일 KST 04:30. 원장(`BrandVisitorDay`)의 100일 경과분 파기
(최대 조회 창 90일보다 넉넉히). **읽기 모델은 지우지 않으므로 과거 차트는 그대로**다.
보존기간·조건은 서비스가 소유하고 cron 파일은 스케줄만 갖는다.

⚠️ 이 cron 이 늘어 `test/app.e2e-spec.ts` 의 기대 목록이 **8개**가 됐다.

## 화면 구성 (klow_brand `/stats`, 2026-08-20 개편)

```
요약 카드   방문자 · 장바구니 · 결제        ← 퍼널(명)
[방문 국가]  누적 영역(국가별 명) + 순위표   ← BrandVisitorCountryDay
[결제]       누적 영역(국가별 건) + 국가·제품 순위표  ← Order/OrderItem
```

- **방문자 추이 차트를 따로 두지 않는다** — 방문 국가 누적 영역의 높이가 곧 그날 방문자 수라
  같은 그림을 두 번 그리는 셈이 된다.
- ⚠️⚠️ **두 패널의 단위가 다르다**(명 vs 건). 차트와 표가 **같은 출처**여야 색 점이 조각을
  가리키므로, 결제 패널을 퍼널(명)로는 그릴 수 없다. 그래서 요약 카드의 "결제 N명"과 결제
  패널의 "N건"은 서로 다른 숫자다 — 각 패널의 `note` 한 줄이 그걸 적는다(**지우지 말 것**.
  이 화면에서 유일하게 남은 모집단 설명이다).
- 색은 **항목(국가)에 붙지 순위에 붙지 않는다.** 배정은 탭과 무관한 **전체 순위**로 하고 채널
  탭을 옮겨도 재배정하지 않는다 — 필터 하나 바꿨을 뿐인데 살아남은 국가 색이 뒤바뀌면 안 된다.
  검증된 5색(`SERIES_PALETTE`) + 잔여 무채색(`SERIES_OTHER_COLOR`)이고, 6번째 국가부터는
  '기타' 한 조각으로 접는다. 미상은 정체성이 아니라 잔여라 무채색을 쓴다.
- ⚠️ 팔레트 3색이 흰 배경 대비 3:1 미만이라 **표가 반드시 차트와 함께 있어야 한다**(색만으로
  정체성을 나르지 않게 하는 relief 조건).
- ⚠️ **펼침 버튼은 패널이 소유한다.** 표마다 두면 결제 패널(국가·제품)에서 카드 아래 같은
  버튼이 두 개 생긴다.
- 현장 탭은 방문을 수집하지 않으므로 **방문 국가 패널이 없고** 요약 카드도 결제 요약으로 바뀐다.

**klow_admin 브랜드 상세 3번째 탭이 같은 구성을 재현한다**(2026-08-21). 로직(접기·색 배정·
탭 분기)은 그대로 옮기고 마크업만 어드민 토큰/프리미티브(`Card`·`StatCard`·`Table`·
`SegmentedToggle`)로 바꿨다. ⚠️ **두 화면은 서로의 거울이라 한쪽만 고치면 갈린다** — 접기 규칙·
색 배정·`note` 문구를 바꿀 때는 반드시 양쪽을 함께 볼 것. 다른 점 셋:
- 팔레트가 `klow_admin/src/lib/chart-theme.ts` 에 산다(그 파일이 **recharts 를 import 하지
  않는다**는 계약을 갖고 있어, 색 점·색 배정 모듈이 recharts 를 끌어오지 않는다).
  ⚠️ klow_brand `LazyTrendChart.tsx` 는 `export { SERIES_PALETTE } from './TrendChart'` 로
  **값을 정적 재export** 해서 lazy 경계가 사실상 뚫려 있다 — 어드민에 그 패턴을 옮기지 말 것
  (Lazy 파일은 `dynamic()` + `export type` 만).
- 운영팀이 CS 문의를 **받는** 쪽이라 패널 아래에 모집단 차이 각주를 한 줄 남겼다
  (klow_brand 는 각주가 길어 걷어낸 자리다 — 그쪽 결정은 그대로 둔다).
- klow_brand `TrendChart` 의 `variant: 'line' | 'stacked-area'` 분기 중 **누적 영역만** 옮겼다
  (선 차트를 쓰던 할인 링크 추이 화면이 어드민엔 없다). 선 차트가 필요해지면 파일을 새로
  만들지 말고 그 파일에 variant 를 되살릴 것.

## 화면 표기 규칙 — 퍼널은 "명", 횟수는 보조줄

`visits`/`cartAdds`(회)와 `uniqueVisits`/`uniqueCartAdds`(명)를 **같은 크기로 나란히 두지 않는다.**
전환율이 이미 `uniqueCartAdds ÷ uniqueVisits` 라 퍼널의 축은 사람 수인데, "회" 지표가 동등하게
놓이면 어느 게 본선인지 안 보이고 "방문은 뭐고 순방문은 뭐지"가 된다(실제로 나온 피드백).

| 화면 라벨 | 필드 | 위치 |
|---|---|---|
| 방문자 | `uniqueVisits` | 큰 숫자 |
| 장바구니 | `uniqueCartAdds` | 큰 숫자 |
| 결제 | `uniquePurchases` | 큰 숫자 |
| (장바구니 아래) N% | `cartConversionPct` | 보조줄 |
| (결제 아래) N% | `purchaseConversionPct` | 보조줄 |

⚠️ 라벨은 **"담은 사람"이 아니라 "장바구니"** 다(2026-08-19 통일 — klow_brand·klow_admin 양쪽).
⚠️ 보조줄에 들어가는 건 **전환율(%)** 이지 `visits`/`cartAdds`(회)가 아니다 — 회 지표를 큰 숫자
옆에 두면 단위가 섞여 "방문은 뭐고 순방문은 뭐지"가 되돌아온다(그래서 한 번 지웠던 자리다).
어드민 합계 카드만 방문자 아래에 `총 N회 방문` 을 남긴다.

⚠️ **"순방문" 이라는 말을 UI 에 쓰지 않는다** — 업계 용어라 브랜드가 바로 못 읽는다. 단위를
드러낸 "방문자(명) / 방문 횟수(회)" 가 설명 없이 읽힌다.
⚠️ **차트도 같은 단위(명)로 그린다.** 요약 칸은 명인데 차트가 회면 한 화면에서 단위가 갈려,
정리해 없앤 혼란이 그대로 돌아온다.
⚠️ 어드민 브랜드별 표의 **정렬 키도 `uniqueVisits`** 다(동률은 `visits`) — 앞세운 열과 정렬
기준이 다르면 "방문자 많은 순"인데 첫 열이 뒤죽박죽으로 보인다.

## 프론트 배선

| 앱 | 파일 |
|---|---|
| klow_web | `lib/visitor-id.ts`(난수 토큰) · `lib/storefront-track.ts`(발사 + 중복 가드 **Set 3개** — `sentVisits`/`visitedBrands`/`sentCountries`, + **담기·국가**가 기다리는 `pendingVisit`) · `app/product/[id]/page.tsx`(PDP 방문·국가 effect) · `components/brand/BrandStorefront.tsx`(방문 effect, `source`/`promotionCode` prop) · `store/useCartStore.ts`(담기 1줄) · `lib/brand-server.ts` `resolvePromotionCode`(집계 아님, code 해석만) |
| klow_brand | `app/(authed)/stats/page.tsx` + `_components/StorefrontStatsBoard.tsx` · `_hooks/useStorefrontStats.ts` · `components/charts/{TrendChart,ChartChrome}.tsx`(할인 링크 추이 탭과 공유) |
| klow_admin | `app/(authed)/_components/StorefrontVisitSection.tsx`(대시보드 표 — 브랜드명이 `?tab=stats` 로 링크) · `app/(authed)/brands/_components/BrandDetailTabs.tsx`(3번째 탭) · `app/(authed)/brands/_components/stats/{BrandStorefrontStatsPanel,BreakdownPanel,ChannelTabs,breakdown-series}` · `components/charts/{TrendChart,LazyTrendChart,ChartChrome}.tsx`(klow_brand 트리 의도적 미러) · `components/ui/segmented-toggle.tsx` · `lib/chart-theme.ts`(SERIES_PALETTE) · `lib/api/stats.ts` |

- ⚠️ 방문 중복 가드는 **모듈 레벨 `Set`** 이다 — 컴포넌트 `useRef` 로는 StrictMode dev 이중 effect 는
  막아도 `?mode=onsite` 토글·view 전환 **remount** 에서 뚫린다. 키에 `source` 를 넣어 같은 탭에서
  경로를 바꿔 재진입한 것은 각각 잡히게 한다(그게 실제로 다른 유입이다).
- ⚠️ **`sentCountries` 의 축은 "브랜드 문맥 × 국가"다 — 제품이 아니다.** 원장 키가
  `(brandId, date, visitorId)` 이고 국가가 첫-쓰기-승이라, 국가 비콘이 의미를 갖는 단위는
  **탭 × 브랜드 하나**다. 그래서 키가 두 별칭(`id:{brandId}:{cc}` / `slug:{slug}:{cc}`)이고
  브랜드관 비콘이 둘 다 찍는다 — 이어지는 제품 클릭(slug 만 아는 PDP)이 헛 POST 를 안 쏘게.
  ⚠️⚠️ **표시는 반드시 실제 전송과 같은 경로에서만 한다**(`markCountrySent`). 2026-08-20~21
  사이 `trackStorefrontProductVisit` 이 `visitedBrands` 게이트 **앞**에서 키를 찍는 바람에,
  국가를 나중에 고른 딥링크 PDP 손님(= 자사몰 임베드 유입 = 이 기능의 주 대상)의 국가가
  **한 번도 서버에 도달하지 못하고** 전부 '미상'으로 남았다. 그 최적화를 되살리려고 시드를
  게이트 위로 올리지 말 것 — 지금은 slug 별칭이 같은 일을 한다.
- ⚠️ **국가 비콘도 `pendingVisit` 을 기다린다**(담기와 같은 `afterVisit`). 국가 POST 가 방문
  POST 를 앞지르면 서버가 원장 행을 못 찾아 버리는데 클라는 이미 dedupe 에 찍어 **재시도가
  없다**. 로그인 손님에서 실제로 난다 — `useSessionSync` 가 `/v1/auth/me` 직후 `syncCountry`
  를 호출해 마운트 직후에 `country` 가 채워진다.
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

## 배포 순서

⚠️ **klow_web → klow_server(마이그레이션 포함) → klow_brand / klow_admin.**
**할인 링크 클릭 통일 때문에 klow_web 이 먼저다** — 흔한 "서버 먼저"의 반대다.

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| **klow_web 먼저** ✅ | 신규 트래킹 POST 가 404 로 조용히 버려진다(아직 아무도 안 보는 신규 지표). 할인 링크 클릭은 **구 서버가 종전대로 계속 센다** — 유실 없음. 새 `promotionCode` 필드는 구 서버 zod 가 unknown key 로 흘려보낸다(strip). |
| klow_server 먼저 ❌ | `resolveBySlug` 가 집계를 멈췄는데 구 klow_web 은 `promotionCode` 를 아직 안 보낸다 → **이미 운영 중인 할인 링크 클릭이 통째로 유실**된다. |

- 데이터는 klow_web 배포부터 쌓인다. **백필 불가**이므로 `trackingSince` 이전은 0 이 아니라 데이터 없음이다.
- 브랜드/어드민 화면은 마지막 — 먼저 내보내면 텅 빈 차트를 보고 "통계가 안 나와요" 문의가 온다.

### 결제 단계 배포 (2026-08-19) — 이번엔 **서버가 먼저**

**klow_server(마이그레이션 포함) → klow_web → klow_brand / klow_admin.** 위 최초 배포에서
klow_web 이 먼저였던 건 할인 링크 클릭 유실 때문이고 여기엔 해당 사항이 없다.

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| klow_server 먼저 ✅ | 컬럼과 훅이 준비된다. 아직 아무도 `visitorId` 를 안 보내므로 `recordPurchase` 가 첫 줄에서 return — 쓰기 0, 위험 0. 구 klow_web 은 그대로 동작한다(필드 optional). |
| klow_web 다음 | 여기부터 결제가 쌓인다. **이전 주문은 복구 불가**(`Order.visitorId` 가 영원히 null, 백필 없음). |
| 프론트 2개 마지막 ⚠️ | **klow_server 보다 먼저 내보내면 안 된다** — `formatNumberKo`/`formatCountKo` 가 `undefined.toLocaleString()` 로 **throw** 한다. klow_brand 는 `/stats` 가 죽고, klow_admin `StorefrontVisitSection` 은 **서버 컴포넌트**라 대시보드 홈 전체가 죽는다(NaN 이 아니라 하드 크래시). |

⚠️ **klow_web 배포 후 최소 2일(KST) 지나서 프론트를 내보낼 것.** 첫날엔 방문자·장바구니가 몇 주치
이력을 보여주는데 결제만 0 이라, 브랜드의 첫인상이 "이 숫자 틀렸다"가 된다. 같은 이유로 **결제
추이 차트는 `trackingSince` 이전 구간 전체를 0 으로 그린다**(`trackingSince` 는 방문 최초 행에서
파생되므로 결제 추적 시작보다 몇 주 앞선다) — 신경 쓰이면 별도 `purchaseTrackingSince` 를 내려
선을 거기서 시작시키면 된다.

### 방문 국가 배포 (2026-08-20) — **klow_server → klow_web → klow_brand**

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| klow_server 먼저 ✅ | 새 라우트·컬럼이 준비된다. 아직 아무도 국가를 안 보내므로 쓰기 0. |
| klow_web 다음 | 여기부터 국가가 쌓인다. **이전 방문은 복구 불가**(백필 없음). |
| klow_brand 마지막 ⚠️ | `/stats` 가 `funnel.countries` 를 읽는다. 서버보다 먼저 내면 `undefined` 인데, 보드가 `?? []` 로 방어하므로 크래시 대신 **빈 랭킹**이 뜬다(결제 단계 배포의 하드 크래시와 다르다). 그래도 마지막이 낫다 — 첫날 화면이 100% 미상이라 "고장"으로 읽힌다. |

⚠️ **klow_server 를 먼저 내는 게 중요한 이유**: `StorefrontVisitInput` 은 non-strict 라 구
서버에 `countryCode` 를 보내면 **400 이 아니라 조용히 버려진다**. 반대 순서면 그 창의 국가가
흔적 없이 사라진다.
마이그레이션은 **nullable ADD COLUMN + CREATE TABLE = 추가 전용 → 롤링 안전 · 백필 없음**,
**cron 개수 불변(8)**, 라우트 +1(294).

### PDP 집계 배포 (2026-08-20) — **klow_server → klow_web**

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| klow_server 먼저 ✅ | XOR 스키마·`resolveBrandId` 가 준비된다. 구 klow_web 은 `{brandId,…}` 만 보내고 그건 XOR 을 통과하므로 **동작 100% 동일, 쓰기 변화 0** |
| klow_web 다음 | 여기부터 PDP 방문·담기·결제가 쌓인다. 소급 불가 |
| klow_brand / klow_admin | **배포 없음** — 응답 shape·enum·프론트 타입 전부 무변경(`direct` 에 합친 결정의 배당금) |

⚠️ **klow_web 을 먼저 내면 그 창의 PDP 방문이 통째로 유실된다.** 국가 수집 배포 때는 필드
*추가*라 구 서버가 unknown key 를 조용히 strip 했지만, 여기는 **필수 필드(`brandId`) 제거**라
구 서버 zod 가 **400** 을 내고 `api.ts` 의 `.catch(devWarn)` 이 프로덕션에서 삼킨다.
마이그레이션 없음 · cron 8개 불변 · **라우트 수 불변**(새 라우트 없음).

⚠️ **배포 첫날 `uniqueVisits(direct)` 와 `purchases` 가 계단처럼 올라간다**(임베드 유입이 새로
들어온다). 할인 링크 클릭이 봇 제외로 계단처럼 내려갔던 것과 같은 성질이니 운영팀에 미리 알릴 것.

### 어드민 브랜드관 통계 탭 배포 (2026-08-21) — **klow_server → klow_admin**

| 순서 | 그 창에서 벌어지는 일 |
|---|---|
| klow_server 먼저 ✅ | 새 라우트 2개가 준비된다. 아직 호출자가 없어 **동작 변화 0 · 쓰기 0**. 기존 `/admin/stats/storefront-visits` 는 같은 컨트롤러에 `@Get` 이 둘 붙었을 뿐 완전 무변경이고(`?days=all` 은 계속 400), **서비스는 한 글자도 안 바뀌어** klow_brand `/stats` 도 무영향이다. |
| klow_admin 다음 ⚠️ | 반대로 하면 브랜드 이름 링크가 `?tab=stats` 로 들어가는데 두 요청이 **404** → 토스트 + 인라인 에러. 단 **대시보드 홈은 죽지 않는다**(링크 href 만 바뀌었고 탭이 lazy 라 클릭 전엔 요청 0) — 2026-08-19 결제 단계 배포의 하드 크래시와는 다르다. |

**마이그레이션 없음 · 백필 없음 · cron 8개 불변 · 라우트 +2(296 → 298).**
klow_web · klow_brand 는 배포 대상이 아니다. 롤백은 각 저장소 독립이며, klow_admin 만
되돌려도 서버의 새 라우트는 호출자 0 으로 무해하게 남는다.

⚠️ **운영팀 공지**: 새 탭의 "결제 N명"(요약 = 퍼널 모집단)과 결제 패널의 "N건"(주문 원장)은
**서로 다른 숫자이며 정상**이다. 배포 직후 가장 먼저 올 문의이고, 근거는 이 문서 맨 위
"한 화면에 모집단이 둘이다" 표다.

## 교차링크

[brands](./brands.md) · [promotions](./promotions.md)(클릭 카운터 소유권) · [stats](./stats.md)(brandActivity 오염 금지 원칙) · [products](./products.md)(`StrippedPricingKeys`)
