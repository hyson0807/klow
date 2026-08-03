# translation — Google 번역 래퍼 (런타임 콘텐츠 번역)

- **모듈 경로**: `src/modules/translation/`
- **컨트롤러 없음 (내부 서비스)**: 이 모듈 자체는 라우트를 노출하지 않는다. `TranslationModule` 이 `TranslationService` 를 `exports` 만 하고, 다른 모듈이 주입해서 쓴다. (번역을 HTTP 로 노출하는 유일한 라우트는 brand-applications 모듈이 소유한 `POST /v1/brand/translate` — 아래 **사용처** 참고.)
- **Google Cloud Translation v2 API 래퍼**: REST + API-key 인증의 얇은 래퍼. 엔드포인트 `https://translation.googleapis.com/language/translate/v2`, `POST` body `{ q, target, format: 'text' }` (+ `source` 는 값이 있을 때만 포함), key 는 쿼리스트링(`?key=`)으로 전달. 응답 `data.translations[].translatedText` 순서는 요청 `q` 순서와 동일(누락 시 원문 fallback).
- **원본 언어는 en 기본 + auto-detect 가능**: `translateBatch(texts, target, source)` 의 `source` 기본값은 `'en'` 이지만 타입이 `string | null` 이라 **`null` 을 넘기면 `source` 키를 아예 빼서 Google 자동 감지**에 맡긴다. 제품/브랜드/리뷰 캐시 경로는 원문 언어가 정해져 있어 명시값을 쓰고, 브랜드 스튜디오의 입력 영문화·목업 라이브 번역(`POST /v1/brand/translate`)은 한글/영어 혼용 입력 때문에 `null`(자동 감지)로 호출한다.
- **위치 보존 + 빈 문자열 스킵**: 입력 배열에서 비어있지 않은(`t.trim()`) 문자열만 API 로 전송하고, 빈 문자열은 인덱스만 보존해 그대로 돌려준다. 반환 배열은 **입력과 같은 길이/순서**.
- **청킹**: Google v2 가 요청당 최대 128 segment 라 그 아래인 **`CHUNK = 100`** 으로 잘라 순차 호출한다.
- **dev fallback**: `GOOGLE_TRANSLATE_API_KEY` 가 비어있으면(`enabled === false`) API 를 호출하지 않고 원문을 그대로 echo + `[DEV translate] no GOOGLE_TRANSLATE_API_KEY — echoing N segment(s) en->xx` 로 경고 로깅(`sms.service.ts` 의 dev 로깅 패턴과 동일).
- **klow_web UI i18n 과는 별개**: 이 모듈은 **런타임 콘텐츠 번역**(DB 의 제품/브랜드 텍스트를 요청 시점 locale 로 번역)이다. 앱 UI 라벨 번역(`klow_web/src/i18n/` + `npm run i18n:fill`, en 단일 원본 → ja/zh/vi/th/id/ru 빌드타임 생성)과는 무관하다.
- **관련 파일**: `translation.service.ts`, `translation.module.ts`.

## TranslationService

### `get enabled(): boolean`

`process.env.GOOGLE_TRANSLATE_API_KEY` 가 설정되어 있으면(길이 > 0) `true`. dev fallback 분기에 쓰인다.

### `async translateBatch(texts: string[], target: string, source: string | null = 'en'): Promise<string[]>`

- `texts` 와 **동일 길이/순서**의 번역 배열을 반환.
- `texts.length === 0` → `[]` 즉시 반환.
- `enabled === false` → 입력 복사본(`[...texts]`) echo + dev 경고 로깅.
- 빈/공백 문자열은 API 미전송 + 위치 보존(원문 그대로). 보낼 게 하나도 없으면(`q.length === 0`) API 호출 없이 입력 복사본 반환.
- `source` 가 falsy(`null`/빈 문자열)면 요청 body 에서 `source` 를 생략 → Google 자동 감지.
- 보낼 문자열을 `CHUNK(100)` 단위로 잘라 `requestChunk` 로 순차 호출, 각 결과를 원래 인덱스에 되꽂는다.
- API 응답이 `res.ok` 가 아니면 `Error('Google Translate <status>: <body>')` throw.

(`requestChunk` 는 private — 단일 chunk 를 `fetch` 로 전송하고 `translatedText[]` 를 반환한다.)

## 사용처 (주입하는 소비자)

`TranslationModule` 을 import 하는 모듈은 **products / brands / reviews / brand-applications** 네 곳이다. 앞의 셋은 도메인 전용 래퍼를 한 단계 더 두고, 마지막 하나만 `TranslationService` 를 컨트롤러에서 직접 주입한다.

- **`products/product-translation.service.ts` (`ProductTranslationService`)** — 제품 텍스트 segment 들을 모아 `translation.translateBatch(segments, locale)` 호출 — 제품명·상세설명·핵심성분·공감카드·**자유 텍스트 태그(concerns/recommendedFor)** + 고시 필드(서술형 5 + 식별 4). 전성분 INCI 는 국제 표준 영문이라 번역 대상이 아니다. 가변 길이 항목(성분·카드·태그)은 고정 필드 뒤에 정해진 순서로 평탄화하고 같은 순서로 재조립한다. 대상 locale 은 `TRANSLATABLE_LOCALES = ['ja','zh','vi','th','id','ru']` (원문이 영어라 en 제외). `products.service.ts` 가 소비. `products.module.ts` 가 `ProductTranslationService` 를 export.
- **`brands/brand-translation.service.ts` (`BrandTranslationService`)** — 브랜드 텍스트 segment 들을 모아 `translation.translateBatch(segments, locale)` 호출. `brands.service.ts` 가 소비, `brands.module.ts` 에 등록.
- **`reviews/review-translation.service.ts` (`ReviewTranslationService`)** — 한 제품의 리뷰 본문(최대 200건)을 locale 로 번역해 `{ [reviewId]: content }` 맵 반환. `ReviewTranslation` 캐시를 우선 쓰고 미스/stale 만 모아 **1회 배치 번역** 후 upsert. **원문이 한국어**라 대상 locale 이 `REVIEW_TRANSLATABLE_LOCALES = ['en', ...TRANSLATABLE_LOCALES]` 로 **en 을 포함**한다(제품과 다른 지점). `public-reviews.controller.ts` 가 소비.
- **`brand-applications/public-brand-applications.controller.ts`** — 유일하게 번역을 **HTTP 로 노출**하는 곳: `POST /v1/brand/translate` (`BrandGuard`, `@Throttle` **20회/분/IP**, `HttpCode 200`). Body `BrandTranslateInput` = `{ texts: string[](1~20개, 각 ≤2000자), target: en|ja|zh|vi|th|id|ru, source?: 위 7개+ko }`, 응답 `{ translated: string[] }`. `source` 미지정 시 `null` 로 넘겨 자동 감지. 스튜디오 폼 입력 영문화(`target:'en'`)와 목업 라이브 번역(`target:<locale>`) 공용이며, 표시/입력 보조라 브랜드 소유권 체크 없이 로그인만 요구한다. ⚠️ **요청당 20개 상한**이라 클라(`TagChipInput` 등)는 20개씩 청크해 호출한다.

> 즉 호출 그래프는 `products/brands/reviews` → `Product/Brand/ReviewTranslationService` → `TranslationService` → Google v2, 그리고 `POST /v1/brand/translate` → `TranslationService` 직행이다. `TranslationService` 자체는 도메인 무관한 순수 배치 번역기다.
