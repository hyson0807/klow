# 커스텀 도메인 — 원리와 흐름

이 문서는 **왜 이 설계인지**를 설명한다. 무엇을 어떻게 만드는지는
[`implementation-plan.md`](./implementation-plan.md) 가 정본이다.

⚠️ `file:line` 은 **2026-08-19 스냅샷**이다 — 심볼명으로 재확인할 것.

---

## 1. 왜 rewrite 하나로 끝나지 않는가

### 1-1. 지금 구조가 성립하는 이유

```
손님 브라우저
   │
   ├─ 화면  →  klow.kr           (Vercel · klow_web)
   └─ 데이터 →  api.klow.kr       (Railway · klow_server)
                 └─ Set-Cookie: klow_sid=…; Domain=.klow.kr
```

화면과 데이터의 **호스트가 다른데도** 세션이 유지되는 이유는 두 가지다:

1. `klow.kr` 과 `api.klow.kr` 은 **registrable domain(eTLD+1)이 `klow.kr` 로 같다** → 브라우저에게
   이 둘은 **same-site**(cross-origin 이지만 cross-site 는 아니다). 그래서 Safari ITP 의 3rd-party
   쿠키 차단 대상이 **아니다**.
2. 쿠키를 `Domain=.klow.kr` 로 구워(`klow_server/src/common/cookies.ts:25`) 두 호스트가 공유한다.

> ⚠️ **same-origin / same-site / cross-site 는 서로 다른 개념이다.** ITP·SameSite 판정은 **eTLD+1**
> 기준(site)이고 CORS 는 **scheme+host+port**(origin) 기준이다. 이 구분을 놓치면 "지금 되니까
> 커스텀 도메인도 되겠지" 라는 잘못된 결론에 도달한다.

### 1-2. `shop.brandA.com` 에서 깨지는 것 4가지

`shop.brandA.com` 은 eTLD+1 이 `brandA.com` 이라 `api.klow.kr` 과 **진짜 cross-site** 다.

| # | 무엇이 | 어떻게 깨지나 | 근거 |
|---|---|---|---|
| 1 | **세션 쿠키** | `klow_sid` 가 3rd-party 쿠키가 된다 → **Safari ITP 는 전송 자체를 차단**, Chrome 은 파티션. 로그인·서버 장바구니·게스트 주문 토큰이 **조용히** 죽는다 | `cookies.ts:19-33` |
| 2 | **Origin CSRF 가드** | 화이트리스트 밖 Origin 의 모든 `POST/PATCH/PUT/DELETE` 를 **403**. 방문 트래킹(`/v1/storefront-stats/track/visit`)부터 막힌다 | `main.ts:71-82` |
| 3 | **CORS** | `buildAllowedOrigins()` 가 `CORS_ORIGIN` env 정적 목록 + localhost 정규식뿐 | `main.ts:12-19` |
| 4 | **결제 리턴** | 확정 후 303 대상이 `FRONTEND_URL` 하드코딩 → klow.kr 로 튕기는데 거기엔 세션도, 결제 직전 브라우저 정보도 없다 | `payment.service.ts:554` |

**가장 위험한 건 1번이 "조용히" 깨진다는 점**이다. 에러가 나지 않고 그냥 로그인이 안 되거나 결제가 안
끝난다.

### 1-3. 해법 — 카페24가 하는 것과 같다

카페24·쇼피파이는 **커스텀 도메인 안에서 모든 것을 끝낸다.** 화면도 데이터도 결제도 한 호스트에서
오가므로 "남의 집" 문제가 애초에 생기지 않는다.

같은 방식을 쓴다: 커스텀 도메인 안에 **중계 창구**(`/api-proxy/*`)를 두고 브라우저는 **자기 오리진만**
호출하게 한다.

```
[ klow.kr — 변경 없음 ]                [ shop.brandA.com — 신규 ]

브라우저 → api.klow.kr                 브라우저 → shop.brandA.com/api-proxy/v1/…
        (same-site, 지금도 정상)                    ↓ (Vercel Route Handler 가 서버 사이드 전달)
                                                api.klow.kr/v1/…
                                                    ↓ Set-Cookie (Domain 없음)
                                       브라우저에 shop.brandA.com 의 1st-party 쿠키로 저장
```

브라우저 입장에서 요청은 **same-origin** 이다 → 쿠키는 1st-party, CORS 는 애초에 발생하지 않고,
Origin 은 `https://shop.brandA.com` 으로 실려 서버가 검증된 도메인 목록으로 통과시킨다.

> `cookies.ts:22-24` 의 주석이 이미 이 방향을 예고해 뒀다:
> *"cross-site (vercel.app ↔ klow.kr 등) 라면 COOKIE_DOMAIN 비워두고 SameSite=None만으로는 부족하니
> 별도 proxy/rewrite 필요"*

### 1-4. 왜 klow.kr 은 프록시를 안 태우나

§1-1 대로 klow.kr↔api.klow.kr 은 same-site 라 **지금 아무 문제가 없다.** 통일성을 위해 함께 태우면
Vercel 함수 호출 비용과 1홉 지연이 전 트래픽에 얹히고, 회귀 위험만 커진다. **깨진 곳만 고친다.**

---

## 2. 요청 흐름

### 2-1. 브랜드관 진입 (커스텀 도메인)

```
GET https://shop.brandA.com/
        │
        ▼
  klow_web middleware  ──── 본 도메인인가? ──No──┐
        │ Yes                                    │
        │ (즉시 next() — 트래픽 대부분)            ▼
        │                          GET api/v1/storefront/resolve?host=shop.brandA.com
        │                                         │  (모듈 레벨 Map 캐시: 양성 60s / 음성 300s)
        │                                         ▼
        │                                  { slug: "brandA" }
        │                                         │
        │                                         ▼
        │                          rewrite("/") → "/brandA"   +   X-Robots-Tag: noindex, follow
        ▼                                         │
  [brandSlug]/page.tsx ◄─────────────────────────┘
        │  generateMetadata → getBrandBySlug (서버 fetch, 절대 URL, revalidate 300)
        ▼
  <BrandStorefront slug="brandA" source="direct" />
        │  useEffect → trackStorefrontVisit()
        ▼
  POST /api-proxy/v1/storefront-stats/track/visit   (프록시 → api.klow.kr)
```

핵심: **주소창은 `shop.brandA.com/` 그대로**다(rewrite 이므로 redirect 아님).

### 2-2. 미들웨어 경로 판정

| 요청 경로 | 처리 | 왜 |
|---|---|---|
| `/` | **rewrite** → `/{slug}` | 브랜드관이 홈이어야 한다 |
| `/{자기 slug}` | **308** → `/` | 같은 콘텐츠가 두 URL 에 뜨는 것 방지 |
| `/product/…` `/cart` `/checkout` `/login` … (예약어 최상위 세그먼트) | **pass-through** | 사이트 전체가 도메인 위에서 동작해야 한다 |
| `.` 포함 세그먼트(`/robots.txt`, `/naver….html`) | pass-through (`/sitemap.xml` 만 404) | `SLUG_REGEX` 가 `.` 을 허용하지 않아 안전한 판별자 |
| `/{seg}` (예약어 아닌 단일 세그먼트) | **rewrite** → `/{slug}/{seg}` | 프로모션 할인 링크가 커스텀 도메인에서도 동작 |
| `/{seg}/…` (2세그먼트 이상, 예약어 아님) | pass-through → 404 | |

⚠️⚠️ **`/{seg}` 규칙이 "남의 브랜드관이 안 뜬다"를 보장하는 유일한 장치다.**
pass-through 로 두면 `shop.brandA.com/brandB` 가 `[brandSlug]` 라우트에 그대로 걸려 **브랜드 B 의
브랜드관이 브랜드 A 도메인에서 렌더**된다.

⚠️ 다만 결과는 **404 가 아니다.** `[influencer]/page.tsx` 는 프로모션 code 가 null 이어도
`notFound()` 하지 않고 브랜드관을 렌더한다(의도된 graceful degradation — "Off 면 정상가로 렌더").
→ 부작용으로 **미매칭 경로가 전부 `source='promotion'` 방문으로 집계**된다(봇의 `/wp-admin` 포함).
`implementation-plan.md` **P0-5** 가 이걸 막는다.

### 2-3. 로그인 (이메일)

```
POST /api-proxy/v1/auth/login          (브라우저 → shop.brandA.com, same-origin)
   Cookie: (있으면 그대로 전달)
   Origin: https://shop.brandA.com     ← 위장하지 않는다
        ▼
Route Handler → api.klow.kr/v1/auth/login
        │   + X-Klow-Client-IP, X-Klow-Proxy-Secret, X-Klow-Storefront-Host
        ▼
 main.ts Origin 가드: 화이트리스트 미스 → BrandDomain(active) 조회 → 통과
        ▼
 Set-Cookie: klow_sid=…; HttpOnly; Secure; SameSite=None      ← Domain 속성 없음(host-only)
        ▼
Route Handler 가 getSetCookie() 로 읽어 그대로 append
        ▼
브라우저: shop.brandA.com 의 1st-party 쿠키로 저장 ✅
```

⚠️ **구글 로그인은 이 그림을 못 탄다** — top-level 이동이라 프록시를 거치지 않고, 콜백이
`api.klow.kr` 에서 일어나 세션이 엉뚱한 호스트에 붙는다. P3 에서는 버튼을 숨기고 P5 에서 one-time
token 핸드오프를 붙인다.

---

## 3. 도메인 등록 상태 머신

```
        브랜드가 도메인 입력
                │
                ▼
     Vercel: POST /v10/projects/{id}/domains
                │
      ┌─────────┼──────────────┬─────────────────┐
      │         │              │                 │
   verified  verified=false  verified=false   409 domain_already_in_use
   =true     verification 없음  verification 有   (row 만들지 않음 · 400)
      │         │              │
      ▼         ▼              ▼
   [active]  [pending]      [verifying]
             A/CNAME 안내    A/CNAME + 소유권 TXT 안내
                │              │
                └──────┬───────┘
                       │  cron 5분 · 또는 브랜드의 "지금 확인"
                       ▼
              getDomainConfig → misconfigured?
                       │ No
                       ▼
              POST …/domains/{d}/verify → verified?
                       │ Yes                    │ No (7일 초과)
                       ▼                        ▼
                   [active]                  [error]
                (origin 스냅샷 즉시 갱신)      (사유 표시 + 재시도)
```

⚠️ `pending` 안에 **서로 다른 두 안내**가 있다 — ① A/CNAME 접속 레코드(항상) ② 소유권 TXT 챌린지
(`verification` 이 있을 때만 = 다른 Vercel 계정이 이미 그 도메인을 쓰는 경우). 한 덩어리로 뭉치면
브랜드가 필요 없는 TXT 를 찾아 헤매거나, 필요한 TXT 를 못 본다.

⚠️ **`active` 는 서빙 자격의 절반일 뿐**이다. `resolveHost` 는 여기에 더해 `PUBLIC_BRAND_WHERE` 와
**구독 게이트**를 함께 태운다 — 안 그러면 "구독이 끊기면 브랜드관이 사라진다"는 기존 불변식(카페24
임베드 버튼이 의존하는 그것)을 커스텀 도메인만 우회한다.

---

## 4. 결제 왕복

```
shop.brandA.com/checkout
   │  POST /api-proxy/v1/orders          → Order.storefrontHost = "shop.brandA.com"
   │        (프록시의 X-Klow-Storefront-Host 헤더로만 기록 — 바디로 받지 않는다)
   │  POST /api-proxy/v1/payment/prepare
   ▼
Eximbay JS SDK 결제창 (return_url = https://api.klow.kr/payment/return — 도메인 무관)
   │
   ▼
POST https://api.klow.kr/payment/return          (Eximbay → 우리 서버. Origin 없음 → origin-exempt)
   │  handleReturn() 이 그 요청 안에서 결제 확정
   ▼
resolveReturnRedirect(qs)
   │  order_id 로 주문 조회 → storefrontHost 확인
   │  ① 지금 이 순간 BrandDomain(active) 에 있는가?
   │  ② 그 브랜드가 이 주문의 아이템 브랜드 중 하나인가?
   ├─ 둘 다 Yes → https://shop.brandA.com/checkout/redirect?…&klow_verified=1
   └─ 아니면    → ${FRONTEND_URL}/checkout/redirect?…       (+ Sentry 경고)
   ▼ 303
/checkout/redirect  (커스텀 도메인)
   │  readCheckoutSelection()  → 결제한 상품만 카트에서 제거   ← sessionStorage(오리진별)
   │  readSeedingCheckout()    → 시딩 링크 복귀              ← sessionStorage(오리진별)
   ▼
/checkout/success
```

### 왜 "리턴 시점 재검증" 인가

저장 시점에만 검증하면 도메인을 해제한 뒤 들어오는 옛 결제 리턴이 **더 이상 우리 것이 아닌 호스트**로
303 된다. 스킴은 항상 서버가 `https://` 로 구성하고 host 는 DB 값만 쓴다 — **오픈 리다이렉트 방지**.

### ⚠️ 폴백은 보안장치이지 우아한 폴백이 아니다

`/checkout/redirect` 가 하는 일은 전부 **브라우저에만 있는 정보**(sessionStorage)로 결정된다. klow.kr
로 떨어지면 그 정보가 없어 `clearCart()` 폴백이 **엉뚱한 klow.kr 카트**를 비우고, 실제 결제한 상품은
브랜드 도메인 카트에 그대로 남는다. 시딩 복귀도 실패한다. → **폴백이 발동하면 Sentry 경고**를 남긴다.

### ✅ 손댈 필요 없는 것 (확인 완료)

- `checkout/success` 는 **API 를 부르지 않는다**(주문번호·이메일 쿼리만) → 세션 불필요
- 주문 확인 이메일의 배송조회 링크는 쿠키가 아니라 **URL 서명 토큰**
  (`order-confirmation-email.ts:86` — `/track/{id}?t=signGuestOrderToken(...)`) → klow.kr 로 열려도 정상
- `return_url`/`status_url` 이 api 도메인 고정이라 **PG 쪽 등록 작업 없음** (단 README #0 확인 필요)

---

## 5. 회귀 매트릭스

| 기능 | 커스텀 도메인에서 | 조치 |
|---|---|---|
| 방문 트래킹 `POST /v1/storefront-stats/track/visit` | 프록시 경유, Origin = 커스텀 도메인 | **Origin 술어가 없으면 전량 403.** P1 필수 |
| 방문→담기 퍼널 | `visitorId`(localStorage)가 같은 오리진 안에서 일관 → **퍼널 성립** | 변경 없음 ✅ |
| **순방문 수** | `visitorId` 가 오리진별이라 같은 사람이 klow.kr 과 자기 도메인을 다 보면 **순방문 2로 중복 계상** | 감수(방문수는 원래 재방문 포함이라 무관). 문서 명시 |
| **유입 경로 `source`** | 커스텀 도메인 루트가 전부 `direct` 로 뭉쳐 "내 도메인 유입"을 구분 못 한다 | **P1 에서 `custom_domain` enum 값 추가 권장** — 나중에 넣으면 그 기간 데이터가 영영 복구 불가 |
| klow_brand `/stats` 페이지 | `brand.klow.kr` 에서 돌고 쿠키도 `.klow.kr` 유지 | 무영향 ✅ |
| 프로모션 유입 | `/summer` → rewrite → `[brandSlug]/[influencer]` → `source="promotion"` | 변경 없음 ✅ |
| 카페24 임베드 `/embed/*` | 스크립트 src 가 API 호스트라 **완전 무관** | 손대지 말 것 ✅ |
| 임베드 딥링크·프로모션 pretty 링크·현장 QR·인스타 답글 링크 | klow.kr 로 생성 | **알려진 갭**. P5 에서 primary 도메인 반영 검토 |
| 시딩 링크 `/seed/{token}` | klow.kr | **그대로 둔다** — 크리에이터 운영 링크지 브랜드 마케팅 표면이 아니다 |
| Eximbay 웹훅 / payment-reconcile cron | api 도메인 직결 | 무관 ✅ |
| **장바구니** | 오리진별로 별개(zustand persist = localStorage) | 쇼피파이와 동일한 의도된 동작. 로그인 사용자만 서버 카트로 합쳐진다 |
| **로그인 세션** | 쿠키가 오리진별이라 klow.kr 에서 로그인한 사람이 커스텀 도메인에 가면 **비로그인** | 의도된 동작. ⚠️ **릴리즈 노트·CS 가이드에 명시** — 모르면 "로그인이 자꾸 풀려요" 문의로 돌아온다 |
| **어드민·웹훅 IP 기록** | 프록시를 안 타므로 `req.ip` 해석 불변 | 무관 ✅ |
| **응답 지연** | 커스텀 도메인만 브라우저 → Vercel 함수 → Railway 로 **1홉 증가** | Vercel 함수 리전 고정(`preferredRegion`) 검토. klow.kr 은 홉 수 불변 |
