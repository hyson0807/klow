# embed — 브랜드 자사몰(카페24) KLOW 해외구매 버튼

브랜드가 **이미 운영 중인 국내 자사몰(카페24)** 상품 페이지에 "해외배송으로 구매" 버튼을 달아, 해외 손님을 그 상품의 KLOW 제품 상세로 보내는 임베드 표면입니다. 도착 후에는 **기존 결제 흐름을 그대로** 탑니다(신규 체크아웃 경로 없음).

- 소스: `klow_server/src/modules/embed/`
- 브랜드 UI: klow_brand 스튜디오 **브랜드관 → 링크 탭 → 자사몰** (`studio/_components/tabs/links/Cafe24Section.tsx`)
- 매핑 컬럼: `Product.externalProductCode` (`@@unique([brandId, externalProductCode])`)

## URL 표면

`/v1` 밖의 **별도 prefix `/embed/*`** 입니다. prefix 하나 = 보안 자세 하나(전부 공개 · GET 전용 · 쿠키 없음 · CORS `*`)라 감사 지점이 단일해집니다. `/r/{code}`(campaigns 단축링크)가 이미 `/v1` 밖 공개 라우트 선례입니다.

| 메서드 | 경로 | 가드 | 설명 |
|--------|------|------|------|
| GET | `/embed/v1.js` | 없음 | 브랜드가 카페24 스킨에 붙이는 스크립트 |
| GET | `/embed/v1/resolve?brand={slug}&code={externalProductCode}` | 없음 | 자사몰 상품코드 → KLOW 제품 |

### `GET /embed/v1.js`

`@SkipThrottle` · DB 접근 0 · 상수 문자열 응답.

```
Content-Type: application/javascript; charset=utf-8
Cache-Control: public, max-age=300, s-maxage=300, stale-while-revalidate=86400
X-Content-Type-Options: nosniff
Access-Control-Allow-Origin: *
```

- **`immutable` 을 쓰지 않는다.** `/embed/v1.js` 는 가변 포인터다 — 브랜드 스킨에 박힌 `<script src>` 를 우리가 고칠 수 없으므로 버그 수정이 자동 전파돼야 하고, 5분이면 긴급 롤백이 실용적 시간 안에 퍼진다.
- **경로의 `v1` 은 호환성 계약 번호**이지 콘텐츠 해시가 아니다. 깨는 변경이 필요하면 `/embed/v2.js` 를 새로 내고 **v1 은 영구 유지**한다(제거하면 그 브랜드 자사몰의 버튼이 조용히 죽는다).
- 스크립트 소스는 `embed-script.ts` 의 문자열 상수다. ⚠️ raw `.js` 파일로 두면 안 된다 — `nest-cli.json` 에 `compilerOptions.assets` 가 없어 `dist/` 에 실리지 않고 **프로덕션에서만 404** 가 난다(로컬은 통과).
- 본문이 불변이라 **gzip/brotli 압축본과 ETag 를 모듈 로드 시 1회** 만들어 둔다(`EMBED_V1_JS_ASSET`, 8.7KB → br 3.3KB). `compression` 미들웨어를 붙이지 않는 이유: 그건 응답마다 다시 압축하는데 여기는 콘텐츠가 안 바뀐다. 앞단에 압축해 줄 CDN 도 없다(Railway 직접 CNAME). ETag 는 인코딩별로 다르다 — 같은 본문이라도 바이트가 달라 캐시가 섞이면 안 된다.

### `GET /embed/v1/resolve`

```jsonc
// 200 — 매핑 있음 + 공개 게이트 통과
{ "found": true, "productId": "cku…", "name": "…", "url": "https://klow.kr/product/cku…?brand=oasis" }
// 200 — 그 외 전부
{ "found": false }
```

- 매핑 없음 / 미승인 / 구독 만료 / 가격 미설정을 **구분하지 않는다.** 제3자 페이지에 브랜드의 승인·구독 상태를 흘리지 않기 위해서다.
- 404 가 아니라 200 인 이유: 스크립트 분기가 단순해지고, 브랜드 콘솔에 빨간 404 가 안 찍혀 "우리 쇼핑몰에 에러가 난다"는 오해를 사지 않는다.
- **가격을 싣지 않는다.** 방문자 국가를 모르면 정확할 수 없고, 자사몰 ₩가와 나란히 보이면 오해를 부른다. 필요해지면 v2 에서 `?country=` + 필드를 **더하기만** 하면 되므로 하위호환이 유지된다.
- 캐시: `found:true` → `max-age=60, s-maxage=300` / `found:false` → `max-age=30`(방금 상품코드를 입력한 브랜드가 새로고침 두 번 안에 확인할 수 있게).
- Throttle: **120/분** (전역 60/분보다 완화). 부작용 없는 인덱스 단건 읽기 2회 + 브라우저 60초 캐시가 앞단 감쇄기이고, CGNAT 뒤 다수 방문자가 한 IP 로 뭉치면 60 은 쉽게 넘는다. 여기서 429 는 결제 중인 브랜드 자사몰의 구매 버튼 소실이라 손실이 크고 공격 가치는 낮다.

## ⚠️ preflight 금지 (하드룰)

`main.ts` 의 전역 `enableCors({ origin: allowedOrigins })` 가 OPTIONS 를 가로채는데, **비화이트리스트 origin(= 모든 브랜드 자사몰 도메인)에는 ACAO 를 붙이지 않는다.** 즉 preflight 가 한 번이라도 발생하면 컨트롤러에 **도달조차 못 하고** 조용히 실패한다.

→ resolve 는 영구히 CORS **simple request** 여야 한다:

- GET 만 · 커스텀 요청 헤더 금지 · `Content-Type` 지정 금지 · `credentials` 금지 · 요청 바디 금지

여기에 헤더 하나만 추가해도 **전 브랜드 자사몰의 버튼이 동시에 죽는다.**

CORS 자체는 `main.ts` 를 건드리지 않고 해결한다:
1. CSRF Origin 미들웨어는 `POST/PATCH/PUT/DELETE` 만 검사 → GET 전용인 embed 는 그대로 통과.
2. `<script src>` 클래식 로드는 애초에 CORS 대상이 아님.
3. 남는 resolve XHR 하나는 컨트롤러의 `setPublicSurfaceCors(res)` 가 ACAO `*` 를 세우고 전역 cors 가 붙인 `Access-Control-Allow-Credentials` 를 걷어낸다(`ACAO: *` 와 함께 쓸 수 없는 조합).
   ⚠️ **`res.append` 금지** — 화이트리스트 origin 이 왔을 때 전역 cors 가 붙인 값과 합쳐져 ACAO 가 2개가 되고, 브라우저는 그런 응답을 전부 거부한다. 이 표면은 쿠키를 절대 쓰지 않으므로 `*` 가 안전하다.
   ⚠️ **두 라우트가 반드시 같은 헬퍼를 타야 한다.** 라우트마다 손으로 헤더를 세우면 누락이 dev 에서 안 잡힌다 — `localhost:*` 가 화이트리스트라 전역 cors 가 대신 ACAO 를 붙여주고, 빠뜨렸다는 사실은 **실제 브랜드 도메인에서만** 드러난다(실제로 한 라우트만 ACAC 를 걷어낸 상태로 갈렸던 적이 있다).

## 노출 게이트 — 구독이 끊기면 버튼이 자동으로 사라진다

`embed.service.ts` 의 제품 조회는 `PUBLIC_PRODUCT_WHERE`(`modules/products/product-selects.ts`)를 그대로 탄다.

```ts
where: { AND: [PUBLIC_PRODUCT_WHERE, { brandId: brand.id, externalProductCode: code }] }
```

⚠️ **반드시 `AND: [...]` 로 감쌀 것.** `PUBLIC_PRODUCT_WHERE` 는 최상위에 `OR` 과 `AND` 키를 이미 갖고 있어, 스프레드로 합치면 나중 키가 조용히 덮어써 **노출 게이트가 통째로 사라진다**(`ProductsService.findAll` 이 같은 이유로 같은 형태를 쓴다).

부수 효과이자 기능: 이 게이트가 브랜드 `status=approved` + 가입 브랜드의 `subscription.status=active` 를 요구하므로 **구독이 끊기면 그 브랜드 자사몰의 버튼이 전부 자동으로 사라진다.** 별도 킬스위치가 필요 없다.

> 🛟 **CS 필독**: "갑자기 버튼이 안 보여요" 의 원인 순서 — ① 구독 상태(active 아님) ② 제품을 스튜디오에서 가림(`hidden`) ③ 제품이 검수중/반려 ④ 상품코드 오입력 ⑤ 모바일 스킨에 스크립트 미설치. ①~③ 은 klow_brand 자사몰 탭의 상태 배지가 알려준다.

브랜드 조회와 제품 조회를 **2단으로** 나눈 것은 `@@unique([brandId, externalProductCode])` 인덱스를 그대로 타기 위해서다 — relation filter(`brandRef: { is: { slug } }`) 한 방으로 쓰면 Prisma 가 서브쿼리를 만들어 이 인덱스를 못 탄다.

## 스크립트 동작 (`embed-script.ts`)

### 상품코드 해결 사다리 (먼저 맞는 것 채택)

1. `<script>` 태그의 `data-code`
2. 마운트 엘리먼트(`#klow-buy` 등)의 `data-code`
3. **`location.search` 의 `product_no`** ← 주력. 브랜드가 스킨 템플릿을 전혀 안 고쳐도 동작한다
4. `location.pathname` 정규식 (카페24 SEO 재작성 URL `/product/{name}/{no}/`)
5. `window.iProductNo` (비공식 전역, `typeof` 가드)
6. 실패 → **아무것도 렌더하지 않는다**

폴백이 "버튼 미노출"이지 "브랜드관 링크"가 아닌 이유: 상품 A 페이지에서 브랜드관으로 보내면 손님이 A 를 다시 찾아야 하고, 최악은 엉뚱한 상품으로 보내는 것이다. 확신이 없으면 침묵한다.

### 삽입 자리

1. `<script data-mount="{셀렉터}">`
2. `<div id="klow-buy"></div>` ← 문서화된 정상 경로
3. 카페24 구매 버튼 후보 셀렉터 첫 매치 뒤(`.btnBuy`, `#btnBuy`, `.btn_buy`, `a[href*="order_form"]`, `a[href*="basket"]` …)
4. 못 찾으면 렌더하지 않는다 — **`document.body` 폴백 금지**(페이지 아무 데나 떠 있는 고아 버튼은 없는 것보다 나쁘다)

`data-position="after|before"` 로 위치를 뒤집을 수 있다.

### 스타일 / 문구

- **Shadow DOM(closed) 격리.** 카페24 스킨의 `!important` 를 인라인 스타일로는 이길 수 없고, `:hover`/`@media` 도 인라인으로 표현할 수 없다(호스트 `<head>` 에 `<style>` 을 넣으면 이번엔 우리가 호스트를 오염시킨다). `attachShadow` 미지원 시 인라인 스타일 `<a>` 로 degrade.
- 문구는 `navigator.language` 기준 `en/ja/zh/vi/th/id/ru` (기본 `en`). **한국어 문구는 넣지 않는다** — 한국어를 읽는 방문자는 그 자사몰에서 사면 된다. `data-label` / `data-lang` 으로 오버라이드 가능.
- "더 싸다"가 아니라 **해외배송 프레이밍**으로 쓴다(자사몰 ₩가 vs 국제가 차이가 "속았다"로 읽히면 안 된다).
- 진짜 `<a href>` + `target="_blank" rel="noopener"`. `found:true` 를 받은 뒤에만 렌더하므로 레이아웃 시프트가 0이다.
- 실패는 전 구간 무음(재시도 없음 — 재시도가 곧 증폭 공격). **Sentry 등 계측 금지** — 제3자 페이지 데이터를 수집하게 된다.

## 설치 방식 2가지

**(A) 스크립트 한 줄** — 카페24 관리자 → 디자인 → 스마트디자인 편집 → **상품 상세** → `</body>` 직전
```html
<script src="https://api.klow.kr/embed/v1.js" data-brand="{brandSlug}" defer></script>
```
⚠️ 카페24는 **PC 스킨과 모바일 스킨이 별도 템플릿**이다. 해외 트래픽은 대부분 모바일이므로 **양쪽 모두**에 붙여야 한다.

**(B) 제품별 수동 링크** — 스튜디오가 최종 URL(`https://klow.kr/product/{id}?brand={slug}`)과 인라인 스타일 `<a>` 스니펫을 복사시켜 준다.
302 리다이렉트 라우트를 두지 않은 이유: 통계가 범위 밖이라 `/r/{code}` 가 302 인 유일한 명분(`resolveAndCount`)이 없고, 고객 구매 동선 위에 서버 홉을 놓으면 **우리 API 가 죽을 때 브랜드 자사몰의 구매 링크가 같이 죽는** 새 실패 모드가 생긴다. 대가로 제품을 삭제 후 재등록하면 cuid 가 바뀌어 링크가 죽는다(복사 UI 에 경고).

## `?brand=` 도착 시 국가 선택

임베드 링크는 `/product/{id}?brand={slug}` 로 도착한다. klow_web PDP 는 이 파라미터가 있을 때 게스트에게 국가 선택 모달을 띄운다(`klow_web/src/app/product/[id]/page.tsx`) — 안 그러면 `country` 가 null 인 채 서버 기본값 **US/en 이 조용히 굳는다**(온보딩 자동 노출이 `/shop` 과 브랜드관에만 걸려 있어 이 경로는 물어볼 기회가 없었다). 게이트는 `onboardedAt` 이 아니라 **`country` 유무**라 채워지면 다시 뜨지 않는다(`BrandStorefront` 와 동일 조건).

`?guest=1` 은 임베드 링크에 **절대 싣지 않는다** — 게스트 결제 발급처는 `/login` 의 `GuestCheckoutButton` 하나여야 한다.

## 로컬 테스트

정적 더미 몰(`/product/detail.html?product_no=12345` + 가짜 카페24 DOM + 공격적 전역 CSS)에 스크립트 한 줄을 붙여 확인한다.

⚠️ **결정적 함정: 하네스를 `http://localhost:PORT` 에서 띄우면 안 된다.** `main.ts` 의 `/^http:\/\/localhost:\d+$/` 가 이미 CORS 화이트리스트라, ACAO 구현이 완전히 빠져 있어도 테스트가 통과하고 **프로덕션에서만 죽는다.** → **`http://127.0.0.1:PORT`** 에서 띄울 것(정규식이 `localhost` 문자열만 매치). `file://`(Origin: `null`)로도 확인하면 최악 케이스까지 커버된다.

resolve 게이트 매트릭스(전부 `found:false` 여야 함): 매핑 없음 / 다른 브랜드 slug + 맞는 code / 없는 slug / `status≠approved` / `hidden=true` / `image=''` / 판매가 미설정 / 브랜드 미승인 / 구독 `past_due·canceled`.

## 범위 밖 (백로그)

클릭·전환 통계, 카페24 정식 앱(OAuth + 상품 자동 동기화), `/embed/v1/go/` 영구 링크 302, 자동 이름 매칭, 응답 가격 표시, 퀵뷰/AJAX 상품 모달 스킨 지원(`MutationObserver`), 한 브랜드가 자사몰을 2개 운영하는 경우.
