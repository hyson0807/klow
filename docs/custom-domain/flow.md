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

### 1-3. 해법 — 깨지는 흐름을 그 도메인에서 하지 않는다

> ⚠️ **2026-08-20 변경.** 원래는 커스텀 도메인 안에 중계 창구(`/api-proxy/*`)를 두어 **결제까지 그
> 도메인에서 끝내는** same-origin 프록시였다. 지금은 **경계를 긋는 쪽**으로 바꿨다. 프록시 설계는
> 폐기하지 않고 [implementation-plan §6-1](./implementation-plan.md#6-1-풀-프록시-승격--로그인결제까지-커스텀-도메인)
> 에 승격 경로로 보존한다.

**커스텀 도메인은 "둘러보고 담는 곳"이고, 로그인·결제는 `klow.kr` 에서 한다.**

```
[ shop.brandA.com — 신규 ]                       [ klow.kr — 오늘과 동일 ]

브랜드관 · PDP · 장바구니                          로그인 · 결제 · 주문조회 · 내 정보
브라우저 → api.klow.kr (공개 GET + 비콘 2개)        브라우저 → api.klow.kr (same-site, 지금도 정상)
쿠키 없음 (credentials:'omit')                     쿠키 그대로 (Domain=.klow.kr, 무변경)
        │
        │  "결제하기"
        ▼
  location.assign("https://klow.kr/handoff?h=<payload>")   ← top-level 이동
        payload = { 카트(id·수량), 국가, promotionCode, visitorId }
```

§1-2 의 4가지가 이렇게 정리된다:

| # | 깨지던 것 | 이 방식에서 |
|---|---|---|
| 1 | 세션 쿠키 3rd-party (ITP) | **소멸** — 그 도메인에서 세션을 쓰지 않는다 |
| 2 | Origin CSRF 가드 | **남는다** — 트래킹 비콘 2개가 여전히 POST 다 → **Origin 술어(P1)로 해결** |
| 3 | CORS | **남는다** — 진짜 cross-origin 이 된다 → 같은 술어 |
| 4 | 결제 리턴 | **소멸** — 결제가 klow.kr 에서 시작하므로 리턴도 klow.kr 이 정답 |

즉 **프록시 없이도 2·3 만 열면 된다**(그건 원래 P1 작업이다).

### 1-4. 왜 이 경계인가 — 이미 같은 이음매가 있다

- **카페24 임베드 버튼**이 브랜드 자사몰에서 `klow.kr/product/{id}?brand={slug}` 로 **더 이른 지점에서**
  손님을 넘긴다. 이미 운영 중인 패턴이고, 결제 직전 전환은 그보다 관대하다.
- `useCheckoutGate`(`useAuthGate.ts:104`)가 **결제 진입마다 로그인/비회원을 다시 묻는다.** 도메인이
  바뀌는 지점과 로그인 화면이 원래 겹쳐 있어, 손님 눈에 가장 덜 튀는 자리다.
- Eximbay 결제창을 호출하는 페이지가 **오늘과 동일한 `klow.kr`** 이라 PG 쪽 전제가 **하나도 안 바뀐다**
  ([README #0](./README.md#0--eximbay-도메인-제한-2026-08-20-조사--남은-질문-1개)).

**대가**(감수하기로 한 것):

- 결제 직전에 **주소창이 바뀐다.**
- 커스텀 도메인은 **항상 비로그인 화면**이다. 로그인·내 정보·주문조회 진입점은 klow.kr 링크로 나간다.
- 브라우징·담기의 **API 호출은 여전히 `api.klow.kr` 직행**이라 홉 수가 늘지 않는다(프록시 방식은 늘었다).

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
  POST https://api.klow.kr/v1/storefront-stats/track/visit
        (cross-origin · credentials 없음 · Origin: https://shop.brandA.com → P1 술어가 통과시킨다)
```

핵심: **주소창은 `shop.brandA.com/` 그대로**다(rewrite 이므로 redirect 아님).

### 2-2. 미들웨어 경로 판정

| 요청 경로 | 처리 | 왜 |
|---|---|---|
| `/` | **rewrite** → `/{slug}` | 브랜드관이 홈이어야 한다 |
| `/{자기 slug}` | **307** → `/` | 같은 콘텐츠가 두 URL 에 뜨는 것 방지. ⚠️ **308 이 아니다**(2026-08-21 정정) — 슬러그·도메인은 가변 DB 상태인데 308·301 은 브라우저가 영구 캐시해 되돌릴 수 없다. 서버가 같은 데이터에 `max-age=60` 을 거는 것과 일관되게 임시 리다이렉트를 쓴다 |
| `/product/…` `/cart` `/track` `/legal` `/faq` `/customer-center` | **pass-through** | 둘러보기·담기는 이 도메인에서 끝난다. ⚠️ **명시 허용목록**(`STOREFRONT_SEGMENTS`)이다 — 예전엔 "예약어면 전부 통과"였는데 `RESERVED_BRAND_SLUGS` 는 klow_server 미러이자 **"브랜드 슬러그로 못 쓰는 단어"라는 다른 질문의 답**이라 실재하지 않는 라우트까지 들어 있고, 무엇보다 기본값이 위험한 방향이었다(내일 `/wishlist` 를 추가하면 아무도 이 파일을 안 고쳐도 **모든 브랜드 도메인에서 세션 없이 열린다**). 이제 모르는 최상위 경로는 **404** 이므로, 새 라우트를 만들면 여기나 klow.kr 전용 목록에 **등록해야 한다** |
| **쿠키가 필요한 경로** — `/login` `/signup` `/my` `/orders` **`/seed/*`** `/checkout/onsite`, 그리고 `/shop` | **미들웨어가 307 → klow.kr 같은 경로** | ⚠️ **2026-08-21 정정 — 예전엔 "화면이 처리한다"고 적혀 있었다.** 그 근거("미들웨어에서 리다이렉트하면 카트·국가·프로모션이 안 실려 넘어간다")는 **`/checkout` 에만** 해당하고 나머지는 카트를 들고 갈 필요가 없다. 미들웨어에서 하면 KLOW UI 가 한 번 그려지는 깜빡임이 없고, 대상 페이지 자체 effect(`/my` 의 `api.auth.me` 등)와 경합하지 않으며(`location.replace` 는 React 를 멈추지 않는다) JS 가 꺼져 있어도 동작한다. ⚠️ **경로를 외우지 말고 "쿠키가 필요한가"로 판정할 것** — `/seed/*` 는 `klow_order` 게스트 쿠키에 의존하는 데다 **자기 도메인에서 결제창을 열어** 특히 놓치기 쉽다. ℹ️ `/shop` 만은 쿠키와 무관한 예외로, **KLOW 마켓플레이스(경쟁 브랜드 목록)** 를 브랜드 자기 도메인에서 링크하지 않기 위해 함께 넣었다 |
| **`/checkout`** | pass-through 되지만 **화면이 핸드오프**(`klow.kr/handoff?h=…`)로 넘긴다 | 여기만은 **카트를 읽어야** 해서 미들웨어가 할 수 없다. 두 결제 버튼이 이미 핸드오프를 타므로 이 경로에 도달하는 건 주소를 직접 친 경우뿐인 **안전망**이다 |
| `/track/{id}?t=` | **pass-through, 그대로 동작** | 쿠키가 아니라 **URL 서명 토큰**으로 여는 화면이라 cross-site 여도 무관하다(위 규칙의 유일한 예외 — 근거가 있어서 예외다) |
| `/handoff` | **미들웨어가 404** (화면의 `/cart` 폴백은 2중 방어로 그대로 남는다) | 여기서 복원하면 손님이 **브랜드 도메인에 남은 채 결제까지** 간다 — 이 설계의 전제가 깨진다(plan F16). 클라의 `isCustomDomain()` bail 보다 미들웨어가 싸고 JS 없이도 동작한다 |
| `?mode=onsite` | **미들웨어가 파라미터를 떼어 내고 307** | 현장 QR 은 klow_brand 가 **klow.kr 로 생성**하고 방문 집계도 onsite 를 제외한다. ⚠️ rewrite 가 쿼리를 보존하므로 이 파라미터는 **실제로 도달한다** — 떼어 내지 않으면 `onsiteMode` 가 켜져 결제가 `/checkout/onsite`(게스트 쿠키 필요)로 분기한다 |
| `.` 포함 세그먼트(`/robots.txt`, `/naver….html`) | pass-through (`/sitemap.xml` 만 404) | `SLUG_REGEX` 가 `.` 을 허용하지 않아 안전한 판별자 |
| `/{seg}` (예약어 아닌 단일 세그먼트) | **rewrite** → `/{slug}/{seg}` | 프로모션 할인 링크가 커스텀 도메인에서도 동작 |
| `/{자기 slug}/{seg}` | **307** → `/{seg}` | 위와 같은 이유(정본 URL 은 `/{seg}`) |
| `/{seg}/…` (2세그먼트 이상, 예약어 아님) | **404** | ⚠️⚠️ **2026-08-21 정정 — 예전엔 여기 "pass-through → 404" 라고 적혀 있었는데 404 가 아니다.** `[brandSlug]/[influencer]/page.tsx` 는 `isBrandSlugAllowed` 만 보고 통과시키므로 `shop.brandA.com/brandB/nana` 가 **브랜드 B 의 브랜드관을, 브랜드 B 의 프로모션 세일가까지 적용해** 브랜드 A 도메인에 렌더하고, `source='promotion'` 방문 비콘이 나가 **브랜드 B 의 할인 링크 클릭 통계까지 오염**시킨다. 같은 문서 §2-2 아래 경고(그리고 plan 부록 V15)가 "code 가 null 이어도 notFound 하지 않는다" 고 이미 적어 둔 것과 표가 모순이었다. 1세그먼트와 **동일하게** 취급해야 F11 이 성립한다 |

⚠️⚠️ **`/{seg}` 규칙이 "남의 브랜드관이 안 뜬다"를 보장하는 유일한 장치다.**
pass-through 로 두면 `shop.brandA.com/brandB` 가 `[brandSlug]` 라우트에 그대로 걸려 **브랜드 B 의
브랜드관이 브랜드 A 도메인에서 렌더**된다.

⚠️ 다만 결과는 **404 가 아니다.** `[influencer]/page.tsx` 는 프로모션 code 가 null 이어도
`notFound()` 하지 않고 브랜드관을 렌더한다(의도된 graceful degradation — "Off 면 정상가로 렌더").
→ 부작용으로 **미매칭 경로가 전부 `source='promotion'` 방문으로 집계**된다(봇의 `/wp-admin` 포함).
`implementation-plan.md` **P0-5** 가 이걸 막는다.

### 2-3. 결제로 넘어가기 (핸드오프)

```
shop.brandA.com/cart  — "결제하기"
        │
        │  peekVisitorId()  ⚠️ getVisitorId() 아님 (없으면 만들지 않는다)
        │  encodeHandoff({ v:1, c:국가, p:promotionCode, vid, o:location.host,
        │                   l:[[productId, 수량], …] })
        ▼
location.assign("https://klow.kr/handoff?h=…")     ⚠️ 새 탭 금지 (인앱 브라우저에서 컨텍스트 유실)
        ▼
klow.kr/handoff
        │ 1. decode 실패 → /cart (조용히 실패해도 손님은 자기 카트를 본다)
        │ 2. 국가 먼저 setCountry — ⚠️ 기존 klow.kr 국가와 다르면 기존 카트 폐기
        │ 3. setPromotion
        │ 4. visitorId 이관 — 없으면 심고, 있으면 덮지 말고 이번 주문에만
        │ 4-b. o 를 /v1/storefront/resolve 로 재검증 → setBrandReturn("https://"+o+"/")
        │      ⚠️ 검증 실패면 저장하지 않는다 (성공 화면의 "계속 쇼핑" 이 임의 사이트로 가면 안 된다)
        │ 5. 카트 재구성 — productId 를 그 국가·프로모션으로 재조회(toCartItem)
        │    ⚠️ addToCart 로 담지 않는다 → 담기 비콘이 재발사돼 이중 집계
        ▼ router.replace  (⚠️ ?h 를 히스토리에서 제거 — 뒤로가기 재복원 방지)
klow.kr/checkout        ← 여기서부터 오늘과 100% 동일 (로그인/게스트 게이트 · 결제 · 리턴)
```

**왜 서명하지 않는가**: payload 의 4개 값은 **전부 이미 손님이 소유·조작 가능한 값**이고(카트는
localStorage, 국가·프로모션은 URL·모달, `visitorId` 는 클라 난수), **청구 금액의 정본은 서버 견적·주문
생성**이다. 서명은 지키는 게 없고 비밀키·만료·재생방지만 늘린다.
⚠️ **가격을 실으면 그 순간 서명이 필요해진다** → 싣지 않는다.

**왜 `visitorId` 까지 옮기는가**: 퍼널 원장이 `(brandId, date, visitorId)` 인데 그 행은 **커스텀
도메인에서** 만들어졌다. 주문이 다른 vid 로 들어가면 `recordPurchase` 가 행을 못 찾고 **조용히 버린다**
→ 그 브랜드의 **결제 단계가 영구 0**. 2일 룩백으로도 못 구한다.

---

## 3. 도메인 등록 상태 머신

```
        브랜드가 도메인 입력
                │
                ▼
     Vercel: POST /v10/projects/{id}/domains
                │
      ┌────────────────────────┬─────────────────┐
      │                        │                 │
  verification 없음      verification 有    409 domain_already_in_use
  (충돌 없음 — 대부분)    (다른 Vercel 계정)  (row 만들지 않음)
      │                        │
      ▼                        ▼
   [pending]              [verifying]
   A/CNAME 안내           A/CNAME + 소유권 TXT 안내
      │                        │
      └───────────┬────────────┘
                  │  cron 5분 · 또는 브랜드의 "지금 확인"
                  ▼
        getDomainConfig(host).misconfigured === false
                  │  AND
        getProjectDomain(host).verified === true
                  │ 둘 다 Yes            │ 7일 초과
                  ▼                      ▼
              [active]                [error]
        (origin 스냅샷 즉시 갱신)      (사유 표시 + 재시도)
```

⚠️⚠️ **추가 직후에는 `active` 로 보내지 않는다.** Vercel 의 `verified` 는 "접속이 되는가"가 아니라
**"소유권이 다투지 않는가"** 다 — 우리가 소유하지도 않은 도메인이 추가 즉시 `verified: true` 로 오고
(2026-08-21 실측), 같은 시점 `getDomainConfig` 는 `misconfigured: true` 였다. `verified` 만 보고 올리면
**DNS 를 한 줄도 안 건 도메인이 "연결 완료"** 로 표시된다([plan F29](./implementation-plan.md#9-불변식-체크리스트-착수-전-필독)).
그래서 위 그림의 `active` 조건이 **두 API 의 AND** 다.

⚠️ `pending` 안에 **서로 다른 두 안내**가 있다 — ① A/CNAME 접속 레코드(항상) ② 소유권 TXT 챌린지
(`verification` 이 있을 때만 = 다른 Vercel 계정이 이미 그 도메인을 쓰는 경우). 한 덩어리로 뭉치면
브랜드가 필요 없는 TXT 를 찾아 헤매거나, 필요한 TXT 를 못 본다.

⚠️ **해지·삭제 반영에는 최대 2분이 걸린다** — resolve 응답 캐시 60초 + 미들웨어 양성 캐시 60초.
엣지에 흩어진 미들웨어 캐시를 밖에서 무효화할 수 없어 **설계상 수용**한 지연이다(두 값을 짧게 유지하는
것이 그 대가다).

⚠️ **`active` 는 서빙 자격의 절반일 뿐**이다. `resolveHost` 는 여기에 더해 `PUBLIC_BRAND_WHERE` 와
**구독 게이트**를 함께 태운다 — 안 그러면 "구독이 끊기면 브랜드관이 사라진다"는 기존 불변식(카페24
임베드 버튼이 의존하는 그것)을 커스텀 도메인만 우회한다.

---

## 4. 결제 왕복

### 4-1. 지금 설계 — **손댈 것이 없다**

```
shop.brandA.com/cart ──핸드오프(§2-3)──► klow.kr/handoff ──► klow.kr/checkout
                                                                  │
        ┌─────────────────────────────────────────────────────────┘
        │  POST /v1/orders → POST /v1/payment/prepare      (오늘과 동일 · 오리진 klow.kr)
        ▼
Eximbay JS SDK 결제창  (호출 페이지 = klow.kr — **PG 가 보는 것이 하나도 안 바뀐다**)
        ▼
POST https://api.klow.kr/payment/return   (Eximbay → 우리 서버, Origin 없음 → origin-exempt)
        │  handleReturn() 이 그 요청 안에서 확정
        ▼ 303 ${FRONTEND_URL}/checkout/redirect?…&klow_verified=1     ← 하드코딩 그대로 정답
klow.kr/checkout/redirect
        │  readCheckoutSelection() → 결제한 상품만 카트에서 제거   ← sessionStorage (같은 오리진 ✅)
        │  readSeedingCheckout()   → 시딩 링크 복귀              ← sessionStorage (같은 오리진 ✅)
        │  setBrandReturn(복귀URL + "?purchased=…")  → 브랜드 도메인 카트 정리용 (§plan 3-4)
        ▼
klow.kr/checkout/success
```

- `Order.storefrontHost` 컬럼 **없음** · 마이그레이션 **없음**
- 리턴 host 재검증 **없음** — **오픈 리다이렉트 표면이 애초에 생기지 않는다**
- `payment.service.ts` 를 이 기능이 **건드리지 않는다**

⚠️ 프록시 방식에서 가장 위험했던 지점이 여기였다: `/checkout/redirect` 의 판단 재료가 전부
**오리진별 `sessionStorage`** 라, 리턴이 klow.kr 로 떨어지면 `clearCart()` 폴백이 **엉뚱한 카트**를
비우고 실제 결제한 상품은 브랜드 도메인 카트에 남았다. 지금은 결제 시작과 리턴이 같은 오리진이라
**그 시나리오 자체가 존재하지 않는다.**

### 4-2. 승격 시 결제 왕복 (P5)

[implementation-plan §6-1](./implementation-plan.md#6-1-풀-프록시-승격--로그인결제까지-커스텀-도메인)
로 결제까지 커스텀 도메인에서 하게 되면, 리턴 303 대상이 다시 문제가 된다. 그때 필요한 규칙:

- `Order.storefrontHost` 를 **프록시 헤더로만** 기록(바디 금지 — 클라이언트가 임의 값을 넣으면 오픈 리다이렉트)
- 리턴 **시점에 재검증**: ① 지금 `BrandDomain(active)` 인가 ② 그 브랜드가 이 주문의 아이템 브랜드인가.
  저장 시점에만 검증하면 도메인을 해제한 뒤 들어오는 옛 리턴이 **남의 호스트**로 303 된다
- 스킴은 항상 서버가 `https://` 로 구성하고 host 는 **DB 값만** 쓴다
- ⚠️ **폴백(`FRONTEND_URL`)은 우아한 폴백이 아니라 보안장치**다. 발동하면 위 sessionStorage 문제가
  그대로 재현되므로 **Sentry 경고**를 남긴다

### 4-3. ✅ 손댈 필요 없는 것 (확인 완료)

- `checkout/success` 는 **API 를 부르지 않는다**(주문번호·이메일 쿼리만) → 세션 불필요
- 주문 확인 이메일의 배송조회 링크는 쿠키가 아니라 **URL 서명 토큰**
  (`order-confirmation-email.ts:86` — `/track/{id}?t=signGuestOrderToken(...)`) → klow.kr 로 열려도 정상
- `return_url`/`status_url` 이 api 도메인 고정이고 **결제창 호출 도메인도 klow.kr 그대로** → PG 쪽 작업 0

---

## 5. 회귀 매트릭스

| 기능 | 커스텀 도메인에서 | 조치 |
|---|---|---|
| 방문 트래킹 `POST /v1/storefront-stats/track/visit` | **진짜 cross-origin** POST (Origin = 커스텀 도메인, 쿠키 없음) | **Origin 술어 + CORS 가 없으면 전량 403.** P1 필수 |
| 방문→담기 퍼널 | `visitorId`(localStorage)가 같은 오리진 안에서 일관 → **성립** | 변경 없음 ✅ |
| **담기→결제 퍼널** | 결제가 **다른 오리진**에서 일어난다 → `visitorId` 를 핸드오프로 옮겨야 성립 | **§2-3 이관 규칙 필수.** 빠뜨리면 결제 단계만 영구 0 |
| **순방문 수** | `visitorId` 가 오리진별이라 같은 사람이 klow.kr 과 자기 도메인을 다 보면 **순방문 2로 중복 계상** | 감수(방문수는 원래 재방문 포함이라 무관). 문서 명시 |
| **유입 경로 `source`** | 커스텀 도메인 루트가 전부 `direct` 로 뭉쳐 "내 도메인 유입"을 구분 못 한다 | **감수한다.** ⚠️ `StorefrontVisitSource` 에 `custom_domain` 을 **넣지 않는다** — `source` 는 유입 경로 축이고 호스트는 다른 축이라, 넣으면 커스텀 도메인의 **할인 링크 유입이 promotion 으로 안 잡힌다**([plan §2-9](./implementation-plan.md#2-9-유입-경로-enum--custom_domain-을-추가하지-않는다)) |
| **판매 분석(국가·제품)** | `Order` 기반이라 **오리진과 무관** | 무영향 ✅ |
| klow_brand `/stats` 페이지 | `brand.klow.kr` 에서 돌고 쿠키도 `.klow.kr` 유지 | 무영향 ✅ |
| 프로모션 유입 | `/summer` → rewrite → `[brandSlug]/[influencer]` → `source="promotion"` | 변경 없음 ✅ |
| **프로모션 세일가** | 브랜드관·PDP 는 정상. **결제는 klow.kr** 이라 `promotionCode` 를 안 넘기면 정상가가 된다 | **핸드오프 필수 필드**(§2-3) |
| 카페24 임베드 `/embed/*` | 스크립트 src 가 API 호스트라 **완전 무관** | 손대지 말 것 ✅ |
| 임베드 딥링크·프로모션 pretty 링크·현장 QR·인스타 답글 링크 | klow.kr 로 생성 | **알려진 갭**. P5 에서 primary 도메인 반영 검토 |
| 시딩 링크 `/seed/{token}` | klow.kr | **그대로 둔다** — 크리에이터 운영 링크지 브랜드 마케팅 표면이 아니다. ⚠️ 커스텀 도메인으로 열리면 **klow.kr 로 보낸다**(§2-2) — `klow_order` 게스트 쿠키가 필요해 cross-site 에서 조용히 깨진다 |
| Eximbay 웹훅 / payment-reconcile cron | api 도메인 직결 | 무관 ✅ |
| **결제 흐름 전체** | klow.kr 에서 오늘과 동일하게 일어난다 | **무변경** ✅ (§4-1) |
| **장바구니** | 오리진별로 별개(zustand persist). 결제 시 핸드오프로 넘어간다 | 결제 완주 후 성공 화면의 **"계속 쇼핑" 링크에 `?purchased=`** 를 실어 브랜드 도메인 카트도 정리한다(`removeProducts` 재사용 — [plan §3-4](./implementation-plan.md#3-4-결제-후-브랜드-도메인-카트-정리)). ⚠️ **best-effort** — 손님이 그 버튼을 안 누르거나 탭을 닫으면 그 도메인 카트에 산 상품이 남는다(**재구매 가능일 뿐 오청구는 아니다**) |
| **로그인 세션** | **항상 비로그인.** 헤더의 로그인·내정보 진입점은 **아예 숨긴다**(klow.kr 링크로 두면 편도 이탈 — plan F26) | 의도된 동작. 로그인은 **결제 진입에서** 묻고(`useCheckoutGate`), 주문조회는 확인 메일의 **서명 링크**로 연다. ⚠️ **릴리즈 노트·CS 가이드에 명시** |
| 구글 로그인 | 커스텀 도메인에 **버튼 자체가 없다**(로그인 화면이 klow.kr) | 별도 작업 없음 ✅ (프록시 방식에서는 P3 숨김 + P5 핸드오프가 필요했다) |
| **어드민·웹훅 IP 기록** | 프록시가 없어 `req.ip` 해석 불변 | 무관 ✅ |
| **rate limit** | 손님 IP 가 서버에 그대로 도달 | 무관 ✅ (프록시 방식에서는 전체가 한 버킷이 되는 함정이 있었다) |
| **응답 지연** | API 직행이라 **홉 수 불변** | 무관 ✅ |
