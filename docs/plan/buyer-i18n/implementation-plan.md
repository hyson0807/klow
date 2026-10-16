# buyer-i18n — 구현 계획 (정본)

결정은 [`README.md`](./README.md) D1~D9 에 있다. 상태는 `PROGRESS.md §7` 만 갖는다.

## 0. 조사로 확인한 전제 (2026-10-16)

### klow_web

- **`[brandSlug]` 와 충돌한다.** `src/app` 최상위의 동적 세그먼트는 `[brandSlug]` 하나뿐이다.
  - 같은 레벨에 `[lang]` 을 둘 수 없다(동적 형제가 둘이 되면 빌드가 실패한다).
  - 바이어 하위 페이지가 전부 `shop/` 아래에 있는 것도 이 때문이다.
- **예약 slug 는 `kr`, `en`, `jp` 뿐이다.**
  - 위치: `klow_server/src/common/reserved-slugs.ts`. 수동 미러가 `klow_web/src/lib/reserved-slugs.ts` 이고, 둘은 현재 동일하다.
  - 서버는 **입력 시점에만** 검사한다(`BrandSlugField`, `checkSlugAvailability`).
  - 그래서 이미 그 slug 를 가진 브랜드가 있으면, 예약하는 순간 그 브랜드관이 깨진다.
    - 정적 라우트가 `[brandSlug]` 보다 우선한다.
    - 커스텀 도메인에서는 예약어로 시작하는 첫 세그먼트가 404 다(`middleware.ts:302`).
- **바이어 페이지는 모두 ISR 이다.**
  - `revalidate = 60` 이고 `cookies()`·`headers()` 를 쓰지 않는다.
  - 따라서 locale 은 반드시 경로로 받아야 한다.
  - ⚠️ `no-store` 로 바꾸면 안 된다. 2026-10-05 결정대로 Vercel 의 egress IP 가 서버 전역 throttle 에 걸린다.
- **middleware 는 primary host 에서 즉시 `next()` 한다**(`middleware.ts:269-271`).
  - 지금 이 레포에는 geo 를 쓰는 코드도, `Accept-Language` 를 읽는 코드도 없다.
  - klow.kr 은 Cloudflare 프록시를 거치지 않는다. 그래서 Vercel 이 `x-vercel-ip-country` 로 실제 국가를 준다(`decisions/platform.md` 2026-10-04).
- **기존 i18n 은 소비자 화면 전용이다.**
  - `src/i18n/config.ts` 의 `SUPPORTED_LOCALES` 8개를 쓴다.
  - `translate()` 는 순수 함수다.
  - `useT` 는 국가 store(`lib/locale.ts` `COUNTRY_TO_LOCALE` → `useAppStore.country`)로 locale 을 정한다.
- **바이어 공간은 영어 하드코딩이다.**
  - `components/buyer-space/` 68개 파일(약 9,400줄)에 문자열이 약 400~450개 있다.
  - `lib/buyer-about/*` 는 따로 노는 체계다.
    - 약 1,900줄이다.
    - `LocalizedText` 이고 `Locale = 'en'|'es'|'ru'|'ar'` 로 정의돼 있다.
    - 값은 en 뿐이다.
    - `t(text, locale='en')` 를 쓴다.
- **`<html lang="en">` 은 루트 레이아웃에 하드코딩**돼 있다(`app/layout.tsx:69`).
- **`sitemap.ts`** 는 접두 없는 영어 URL 만 싣는다.
- **hreflang 은 없다.** 2026-10-12 에 의미 없는 것을 지웠다.

### klow_server

- `/v1/buyer/{home,products,products/:id,brands/:slug}`(`modules/buyer/public-buyer.controller.ts`)는 **locale 을 받지 않는다.**
- 바이어 텍스트는 **`BuyerProduct` 의 영어 전용 컬럼**이다(`buyer.mapper.ts`).
  - 소비자용 `ProductTranslation` 캐시는 그대로 쓸 수 없다.
  - 대신 패턴을 재사용한다. 캐시 → stale 판정 → 배치 번역 → upsert → overlay(`products/product-translation.service.ts` `localize()`).
- 리뷰 번역은 `/v1/reviews/translations?lang=` 로 이미 있다. 웹이 `lang=en` 을 하드코딩하고 있을 뿐이다.

## 1. 착수 게이트 (불변식)

- **G1 — 예약어를 넣기 전에 운영 DB 를 실측한다.** 아래 둘이 `ja zh vi th id ru ar kbl` 과 겹치는지 SELECT 한다.
  - `Brand.slug`
  - 커스텀 도메인 브랜드의 프로모션 코드
  - 1건이라도 겹치면 **멈추고 사용자에게 묻는다.** dev 브랜치로 판단하지 않는다(메모리 "운영 DB 로 판단한다").
- **G2 — 스키마를 바꾸므로 git 브랜치와 Neon DB 브랜치를 같이 판다.**
  - git 은 `feat/buyer-i18n`(staging 에서), DB 는 staging fork 다(CLAUDE.md).
  - 없으면 `§3` 대로 멈춘다.
- **G3 — 리다이렉트는 `/` 하나에만 건다.**
  - `/{lc}/*` 와 `/shop/*` 는 어떤 경우에도 자동 리다이렉트하지 않는다(D3).
  - 봇 UA 는 언제나 통과시킨다.
- **G4 — middleware 의 새 로직은 순수 문자열 판정만 한다.**
  - fetch 를 하지 않는다.
  - 전체를 try 로 감싸고, 예외가 나면 `next()` 로 빠진다.
  - 여기서 throw 하면 전 호스트·전 경로가 500 이 된다(`middleware.ts:19`).
  - 커스텀 도메인 분기는 건드리지 않는다.
- **G5 — 번역 실패는 영어 폴백이다.**
  - LLM 키가 없거나 호출·파싱이 실패하면 원문을 반환한다.
  - 이때 **캐시를 쓰지 않는다**(다음 요청에서 재시도하게).
  - 바이어 페이지는 번역 때문에 500 이 나면 안 된다.
- **G6 — 고유명사·숫자를 보존한다.**
  - 브랜드명, 제품명(`displayName`), INCI, 숫자, 단위, 가격은 번역 대상 필드에 넣지 않는다.
  - LLM 출력을 받으면, 원문에 있던 숫자 토큰이 번역문에도 그대로 있는지 검사한다. 없으면 그 필드는 원문을 쓴다.
- **G7 — B 만 운영에 나가면 안 된다.**
  - B 단계 동안 비영어 URL 은 **noindex** 다. UI 가 아직 영어라 중복 콘텐츠가 되기 때문이다.
  - C 가 noindex 를 풀고 hreflang 과 sitemap 을 켠다.
  - 운영 배포는 **B+C 함께** 한다.

## 2. 설계

### 2-1. 라우팅 (klow_web)

- **폴더 이동**
  - `src/app/(buyer)/**` → `src/app/kbl/[lang]/**`. 하위 `shop/...` 구조는 그대로다.
  - `kbl/[lang]/layout.tsx` 는 다음을 한다.
    - `generateStaticParams` 로 8개 언어를 만든다.
    - `dynamicParams = false` 로 그 밖의 언어는 404 를 낸다.
    - `KbLocaleProvider` 로 감싼다.
    - `.kb` 래퍼에 `lang={lang}` 를 단다.
  - `kbl` 은 **내부 경로**다. 사용자에게 보이지 않는다.
- **middleware(primary host)**

  | 요청 경로 | 처리 |
  |---|---|
  | `/`, `/shop`, `/shop/*` | rewrite → `/kbl/en/...` |
  | `/{lc}`, `/{lc}/shop/*` (lc ∈ 비영어 7개) | rewrite → `/kbl/{lc}/...` |
  | `/{lc}/그 밖` | 통과. `[brandSlug]` 가 받고 예약어라 404 |
  | `/en`, `/en/*` | 308 → 접두를 뗀 경로 |
  | `/kbl/*` 직접 접근 | 404 rewrite |

- **`next.config.js`**
  - 기존 `/shop` → `/` 리다이렉트들은 middleware 보다 먼저 돈다.
  - 언어판도 같은 규칙을 넣는다: `/{lc}/shop` → `/{lc}`, `/{lc}/shop/search/*` 등.
- **쿠키 이름 `kb_lang`**
  - 1년, `SameSite=Lax`, httpOnly 아님.
  - 클라이언트 언어 메뉴가 쓰기 때문이다.
- **링크**
  - `kbHref(lang, path)` 를 만든다. en 이면 접두 없이, 그 외는 `/{lc}` + path 다.
  - Kb 컴포넌트의 내부 링크를 전부 이것으로 바꾼다.
  - 소비자 쪽으로 나가는 링크(`consumerReturnHref`)는 언어와 무관하다.

### 2-2. 자동 언어 (middleware, `/` 에만)

```
봇 UA → 통과
쿠키 kb_lang 있음 → en 이면 통과, 아니면 307 /{lc}
없음 → Accept-Language 1순위가 지원 언어면 그것
     → 아니면 x-vercel-ip-country → COUNTRY_TO_LOCALE
     → 비영어로 판정되면 307 /{lc} + 쿠키 심기 / en 이면 통과
```

- **`COUNTRY_TO_LOCALE` 이동**
  - edge 에서 import 할 수 있도록 `src/i18n/country-locale.ts` 로 떼어 낸다(React·zustand 의존 없이).
  - `lib/locale.ts` 는 거기서 re-export 한다.
- **언어 메뉴(`KbHeader`)**
  - 같은 경로의 다른 언어판으로 이동하고 `kb_lang` 을 쓴다.
  - en 을 고른 사람도 쿠키가 생기므로 이후 `/` 리다이렉트가 멈춘다.

### 2-3. 웹의 locale 소비

- **서버 컴포넌트**
  - `params.lang` 을 받아 `translate(lang, 'kb', key)` 를 부른다.
  - 데이터는 `lib/buyer-space-server.ts` 의 모든 fetch 에 `?lang=` 를 붙여 가져온다.
  - 리뷰 번역의 `lang=en` 하드코딩도 lang 으로 바꾼다.
- **클라이언트**
  - `useKbT()` 가 Context 를 읽는다.
  - 소비자 `useT`/`useLocale` 은 건드리지 않는다.
- **루트 `<html lang="en">`** 은 params 가 닿지 않는 알려진 한계다.
  - `.kb` 래퍼의 `lang` 과 hreflang 으로 보완한다.
  - 루트 레이아웃을 쪼개는 건 범위 밖이다.

### 2-4. 서버 번역 (klow_server)

- **테이블**

  ```
  BuyerTranslation(entityType, entityId, locale, fields Json, sourceHash)
  @@unique([entityType, entityId, locale])
  ```

  - entityType 은 `product`(상세 문구), `productCard`(카드 문구), `category`, `shelf`, `shelfItem`, `band`, `heroSlide`, `video` 다.
    - A 착수 시 확정: 제품을 카드/상세로 나눴다 — 홈·목록이 상세 문구(`about` 최대 4000자)까지 번역하면 첫 방문 비용이 커진다.
    - 스테일 판정은 `sourceUpdatedAt` 대신 **원문 필드 해시**다 — `band`·`shelfItem`·`video` 에는 `updatedAt` 이 없다.
  - `entityId` 는 각 오버레이 행의 id 다.

- **번역 필드**

  | 대상 | 필드 |
  |---|---|
  | 제품 상세(`product`) | `about`, `forText`, `keyActives[]` |
  | 제품 카드(`productCard`) | `badge`, `size` |
  | 카테고리 | `name` — 바이어 slug(`skincare`…)가 `category-presets.ts` 키와 달라 프리셋은 못 쓴다(LLM 캐시) |
  | 선반 | `title`, `lede` |
  | 선반 아이템 | `tag` |
  | 칩 | `label`, `note` |
  | 히어로 | `caption` |
  | 영상 | `title` |

  - 착수 시 `buyer.mapper.ts` 를 다시 보고 표를 확정한다.
  - 번역하지 않는 것(D7): `displayName`, 브랜드명, `ingredients`, `madeIn`, `spf`, 수치.
  - 국가 배열은 웹이 `Intl.DisplayNames` 로 표시한다.
- **서비스 `modules/buyer/buyer-translation.service.ts`**
  - `localize(entities, lang)` 의 흐름: 캐시 조회 → stale 판정(`sourceUpdatedAt < 원본 updatedAt`, 또는 필드 집합 변경) → LLM 배치 → upsert → overlay.
  - `lang` 이 `en` 이거나 지원 외 값이면 no-op 이다.
- **LLM**
  - 기존 OpenAI 호출부(`shipping/rate-sheet-ai.service.ts` 등)의 클라이언트와 키 관례를 재사용한다.
  - 프롬프트
    - 용어집을 넣는다(C 의 `glossary.md` 가 나오기 전에는 아래 임시 목록).
    - JSON in/out 으로 필드 키를 보존한다.
    - B2B 존댓말 톤을 지시한다.
  - G6 숫자 보존 검사를 한다.
  - 임시 용어 목록: KLOW · K-beauty · MOQ · sample box · wholesale · verified buyer · SPF/PA 는 원문 유지. 카테고리 7종은 `category-presets.ts` 의 기존 번역을 우선한다.
- **엔드포인트:** `public-buyer.controller.ts` 4개 라우트에 `@Query('lang')` 를 추가한다.
  - zod 로 `SUPPORTED_LOCALES` 를 검증하고, 지원 외 값은 en 으로 취급한다.
  - 소비자 `?lang=` 패턴과 같다.
- **예약 slug:** `ja zh vi th id ru ar kbl` 을 추가한다(G1 이후).
  - `common/reserved-slugs.ts` 한 곳만 고치면 모든 입력 경로가 함께 막힌다(2026-10-16 확인).
    - `BrandSlugField`(`common/validation/shared.ts`)를 쓰는 곳: 어드민 브랜드 생성·수정 `BrandInput`, 입점 신청 `BrandApplicationInput`·`BrandApplicationInitInput`, 가입 `brand-auth.ts`
    - klow_brand 실시간 중복 확인 `checkSlugAvailability`
  - 기존 행은 검사하지 않는다. 그래서 G1 실측이 필요하다.

### 2-5. SEO (C)

- **공용 헬퍼 `kbMetadata(lang, path, {title, description, noindex?})`**
  - 다음을 채운다.
    - `alternates.canonical` = 자기 언어 URL
    - `alternates.languages` = 8개 + `x-default` → 접두 없는 URL
    - `openGraph` = `type`, `locale`, `url`, `siteName` 을 다시 명시한다. 자식이 객체 전체를 덮어쓰기 때문이다(2026-10-12)
  - `lib/buyer-about/metadata.ts` 를 이 헬퍼로 흡수한다.
- **`sitemap.ts`:** 공개 URL 마다 `alternates.languages` 를 붙인다. 목업과 사적 화면은 그대로 noindex 이고 sitemap 에서 뺀다.
- **결정 기록:** `decisions/storefront.md` 에 새 항목을 쓴다. 2026-10-12 의 "hreflang 제거" 부분을 대체한다. CLAUDE.md 색인과 decisions/README 표에도 한 줄씩 넣는다.

### 2-6. 문구 번역 (C) — Claude 직접

- **`docs/plan/buyer-i18n/glossary.md`**: 8개 언어 용어 대응표와 번역 금지어를 담는다. 서버 프롬프트(2-4)의 임시 목록을 이걸로 교체한다.
- **UI 문구**
  - `src/i18n/locales/en/kb.ts` 를 만든다. `MESSAGES` 등록 방식은 기존 네임스페이스를 따른다.
  - 7개 언어 `kb` 값은 Claude 가 직접 쓴다.
    - `{placeholder}` 를 보존한다.
    - 레이아웃이 깨지지 않을 길이로 쓴다.
    - 역번역으로 점검한다.
  - ⚠️ `i18n:fill` 은 "en 과 같은 값" 도 다시 채운다. 원문 유지 키가 덮이므로 `kb` 를 제외하는 옵션을 넣는다.
- **buyer-about**
  - `Locale` 을 `SUPPORTED_LOCALES` 로 통일한다(`es` 제거).
  - 7개 언어 값을 Claude 가 직접 채운다.
  - ⚠️ 사업자 정보와 배송·결제 조건(2026-10-15 "확인된 사실만")은 숫자, 기간, 회사명을 원문과 대조한다. 원어민 1회 검수를 권고한다.
- `KbCheckout.tsx:35` 의 "영어 전용" 주석을 지운다.

## 3. 단계

### A. klow_server — 바이어 데이터 번역 API + 예약어

- **읽을 것**: 이 문서 §0·§1·§2-4 · `server/modules/buyer.md`(있으면 — 없으면 `buyer` 관련 모듈 문서) · `products/product-translation.service.ts`(패턴만)
- **건드리는 레포 · 배포 순서**: klow_server 하나다. 배포는 B·C 보다 먼저 한다. 기존 웹은 `lang` 을 보내지 않으므로 무해하다
- **스키마·데이터 위험**:
  - 마이그레이션 `add_buyer_translation` 은 신규 테이블 1개다. 롤링 안전이고 백필은 없다.
  - ⚠️ G2 브랜치가 필수다.
  - ⚠️ 예약어 추가는 G1 실측이 먼저다.
- **할 일** — 세션 안 순서이자 정지점
  1. G1 운영 실측
  2. 마이그레이션
  3. `buyer-translation.service.ts` + 컨트롤러 `?lang=` + mapper overlay
  4. 예약어
  5. 모듈 문서
- **완료 기준**:
  - `npm run typecheck` · `npm run test:e2e` 가 통과한다.
  - 단위 스펙이 다음을 확인한다.
    - stale 판정
    - 번역 금지 필드 보존
    - 숫자 보존 실패 시 원문
    - LLM 실패 시 원문 + 캐시 미기록
  - 로컬에서 `curl '/v1/buyer/home?lang=ja'` 와 `/v1/buyer/products/:id?lang=ja` 를 2회씩 호출한다. 2회차는 LLM 호출이 0회여야 한다(로그로 확인).
  - `?lang=xx` 와 `?lang=en` 은 응답이 지금과 같아야 한다.
- **불변식**: G1 · G2 · G5 · G6

### B. klow_web — 라우팅 · 자동 언어 · 언어 메뉴 · `?lang=` 조회

- **읽을 것**: §0·§1·§2-1~2-3 · `src/middleware.ts` 전체 · `decisions/storefront.md` 2026-10-05
- **건드리는 레포 · 배포 순서**: klow_web 하나다. A 이후에 배포하고, **운영은 C 와 함께** 한다(G7)
- **스키마·데이터 위험**: 없음. 예약어 미러는 A 와 같은 값으로 맞춘다
- **할 일**:
  - 정지점 ① 라우팅 이동
    - `kbl/[lang]`
    - middleware rewrite
    - `next.config.js`
    - 예약어 미러
    - 비영어 noindex
  - 정지점 ② 자동 언어 + `kb_lang`
    - `country-locale.ts` 분리
    - 언어 메뉴
  - 정지점 ③ `KbLocaleProvider`, `useKbT`, `kbHref` + 링크 일괄 치환 + `?lang=` fetch
- **완료 기준**:
  - `npm run build` 가 통과한다(`kbl/[lang]` 정적 파라미터 생성, `[brandSlug]`·`/cart` 정상).
  - `curl -I` 결과:
    - `/` + `Accept-Language: ja` → 307 `/ja`
    - 쿠키 `kb_lang=en` → 200
    - `x-vercel-ip-country: JP` 만 있어도 → 307
    - Googlebot UA → 200
    - `/ja/shop/products` → 200
    - `/en/shop/brands` → 308
    - `/kbl/en` → 404
    - `/ja/cart` → 404
    - 기존 브랜드관 `/{slug}` → 200
  - 커스텀 도메인 Host 회귀 1건.
- **불변식**: G3 · G4 · G7

### C. klow_web — 용어집 · 문구 직접 번역 · SEO 켜기 · 마무리

- 제목과 순서만 적는다. 명세는 B 가 끝난 뒤 정밀화한다.
- 세션 안 순서(= 정지점):
  1. 용어집 + 서버 프롬프트 교체(server 커밋 1개)
  2. `kb` 추출 + 7개 언어
  3. buyer-about 7개 언어
  4. `kbMetadata`, hreflang, sitemap, noindex 해제
  5. 결정 기록·색인
- 분량상 2 세션이 될 수 있다. 넘치면 `진행 중(부분 완료)` 로 기록한다.
- **완료 기준(예정)**:
  - Playwright 로 `/ja`, `/zh/shop/brands/<slug>`, `/ru/shop/about` 을 열어 화면을 확인한다.
  - 하드코딩 영어 잔존을 grep 한다.
  - 페이지 소스에 hreflang 8개 + x-default 와 canonical 이 있는지, `sitemap.xml` 에 alternates 가 있는지 본다.
  - 운영 배포 뒤 할 일:
    - 서치 콘솔에 sitemap 을 재제출한다.
    - 해외 VPN 이나 헤더로 첫 방문 리다이렉트를 실측한다.
