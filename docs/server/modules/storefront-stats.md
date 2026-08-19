# storefront-stats — 브랜드관 방문 통계 · 장바구니 · 결제 전환

- **모듈 경로**: `src/modules/storefront-stats/`
- **주 클라이언트**: klow_web(수집) + klow_brand 스튜디오 홈 '통계' 탭(브랜드 조회) + klow_admin 대시보드 홈(운영 조회)
- **관련 파일**: `storefront-stats.service.ts`, 컨트롤러 3개(public·brand·admin), `storefront-stats-retention.cron.ts`, `common/validation/storefront-stats.ts`
- **회귀 잠금**: `src/modules/storefront-stats/__tests__/storefront-stats.spec.ts`

## 이 모듈이 답하는 질문

"내 브랜드관에 손님이 몇 명 들어왔고, 그 중 몇 명이 담고, 몇 명이 **샀는가**" — **유입 경로별로**.

이전에는 유입을 세는 곳이 `PromotionDailyStat` 하나뿐이었고 그건 **할인 링크로 들어온 트래픽만**
잡았다. 브랜드관 루트로 직접 들어온 손님(SNS 프로필 링크·QR·검색·자사몰 경유)은 어디에도
기록되지 않았다.

## 데이터 모델

| 모델 | 역할 |
|---|---|
| `BrandDailyStat(brandId, date, source)` @unique | **읽기 모델**. 브랜드 × 날(KST) × 유입경로 1행에 `visits`/`uniqueVisits`/`cartAdds`/`uniqueCartAdds`/`purchases`/`uniquePurchases`. **차트는 이것만 읽는다** |
| `BrandVisitorDay(brandId, date, visitorId)` @unique | **판정 원장**. "그날 처음인가?"를 유니크 제약으로 원자적으로 답하는 게 유일한 일. `source`(그날 첫 진입 경로) + `carted` + `purchased` 보유 |
| `Order.visitorId` (VarChar 64, nullable) | 결제 단계의 **귀속 키**. 주문 생성 시 klow_web 이 실어 보내고, 결제 확정 때 원장 조회에 쓴다 |

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
- ⚠️ **토큰을 새로 만드는 건 방문 비콘(`getVisitorId`) 하나뿐이고, 담기·결제는 `peekVisitorId`
  (있으면 읽고 없으면 만들지 않음)를 쓴다.** 브랜드관을 안 거친 손님(`/shop`·검색·임베드 PDP)의
  담기·결제는 어차피 원장이 없어 서버가 버리므로, 거기서 발급하면 통계에 잡히지도 않는 추적
  식별자만 남는다.
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

- 이게 "브랜드관에 들어온 사람이 담는가"라는 정의 그 자체다. `/shop`·검색·임베드 PDP 에서 담은
  건은 방문 모집단 밖이라 빠진다.
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

⚠️ **자사몰(카페24) 임베드는 완전히 밖은 아니다** — 임베드 PDP 에서 "바로구매"를 누르면
`/{slug}` 로 push 돼 그때 `direct` 방문이 찍히므로, 그 경로의 구매는 `direct` 로 잡힌다.

### ⚠️ `Order.visitorId` 도 원장과 함께 파기한다

`pruneVisitorDays()` 가 원장 100일 경과분을 지울 때 **같은 커트라인의 `Order.visitorId` 도 null 로
지운다.** 주문 행은 영구 보존인데다 이름·이메일·주소를 들고 있어서, 그대로 두면 익명 토큰이
**영구적으로 실명과 연결**된다 — "IP·UA·계정과 연결하지 않고 cron 이 파기한다"는 이 모듈의 약속을
조용히 뒤집는 셈이다. 원장이 사라지면 조인 대상도 없어 분석 가치가 0 이고, `recordPurchase` 는
늘 이 시점보다 한참 전에 끝난다.

### 신뢰성 한계 (브랜드 안내용)

**이 숫자는 브랜드의 실제 주문 건수보다 적다.** `/shop`·검색·자사몰 임베드 PDP 직행으로 산 주문은
방문 모집단 밖이고, 이틀 이상 지난 방문의 결제도 빠진다. **정산·주문 화면의 숫자와 다른 게 정상**
이며, 그쪽이 매출의 정본이다.

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
  totals: { direct, promotion, all },        // 각각 {visits, uniqueVisits, cartAdds, uniqueCartAdds, cartConversionPct,
                                             //        purchases, uniquePurchases, purchaseConversionPct}
  series: [{ date, direct:{…}, promotion:{…}, all:{…} }] }   // dense 제로필 (onsite 키는 없다)
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

## 교차링크

[brands](./brands.md) · [promotions](./promotions.md)(클릭 카운터 소유권) · [stats](./stats.md)(brandActivity 오염 금지 원칙) · [products](./products.md)(`StrippedPricingKeys`)
