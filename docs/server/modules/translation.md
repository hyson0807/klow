# translation — Google 번역 래퍼 (런타임 콘텐츠 번역)

- **모듈 경로**: `src/modules/translation/`
- **컨트롤러 없음 (내부 서비스)**: 라우트를 노출하지 않는다. `TranslationModule` 이 `TranslationService` 를 `exports` 만 하고, 다른 모듈이 주입해서 쓴다.
- **Google Cloud Translation v2 API 래퍼**: REST + API-key 인증의 얇은 래퍼. 엔드포인트 `https://translation.googleapis.com/language/translate/v2`, `POST` body `{ q, source, target, format: 'text' }`, key 는 쿼리스트링(`?key=`)으로 전달. 응답 `data.translations[].translatedText` 순서는 요청 `q` 순서와 동일(누락 시 원문 fallback).
- **원본 언어 en 고정**: `translateBatch` 의 `source` 기본값이 `'en'`. 제품/브랜드 콘텐츠가 영어로 작성된다는 전제(번역은 en → target 단방향).
- **위치 보존 + 빈 문자열 스킵**: 입력 배열에서 비어있지 않은(`t.trim()`) 문자열만 API 로 전송하고, 빈 문자열은 인덱스만 보존해 그대로 돌려준다. 반환 배열은 **입력과 같은 길이/순서**.
- **청킹**: Google v2 가 요청당 최대 128 segment 라 그 아래인 **`CHUNK = 100`** 으로 잘라 순차 호출한다.
- **dev fallback**: `GOOGLE_TRANSLATE_API_KEY` 가 비어있으면(`enabled === false`) API 를 호출하지 않고 원문을 그대로 echo + `[DEV translate] no GOOGLE_TRANSLATE_API_KEY — echoing N segment(s) en->xx` 로 경고 로깅(`sms.service.ts` 의 dev 로깅 패턴과 동일).
- **klow_web UI i18n 과는 별개**: 이 모듈은 **런타임 콘텐츠 번역**(DB 의 제품/브랜드 텍스트를 요청 시점 locale 로 번역)이다. 앱 UI 라벨 번역(`klow_web/src/i18n/` + `npm run i18n:fill`, en 단일 원본 → ja/zh/vi/th/id/ru 빌드타임 생성)과는 무관하다.
- **관련 파일**: `translation.service.ts`, `translation.module.ts`.

## TranslationService

### `get enabled(): boolean`

`process.env.GOOGLE_TRANSLATE_API_KEY` 가 설정되어 있으면(길이 > 0) `true`. dev fallback 분기에 쓰인다.

### `async translateBatch(texts: string[], target: string, source = 'en'): Promise<string[]>`

- `texts` 와 **동일 길이/순서**의 번역 배열을 반환.
- `texts.length === 0` → `[]` 즉시 반환.
- `enabled === false` → 입력 복사본(`[...texts]`) echo + dev 경고 로깅.
- 빈/공백 문자열은 API 미전송 + 위치 보존(원문 그대로).
- 보낼 문자열을 `CHUNK(100)` 단위로 잘라 `requestChunk` 로 순차 호출, 각 결과를 원래 인덱스에 되꽂는다.
- API 응답이 `res.ok` 가 아니면 `Error('Google Translate <status>: <body>')` throw.

(`requestChunk` 는 private — 단일 chunk 를 `fetch` 로 전송하고 `translatedText[]` 를 반환한다.)

## 사용처 (주입하는 소비자)

`TranslationService` 를 직접 주입하는 모듈은 **products / brands** 두 곳이며, 각각 도메인 전용 래퍼를 한 단계 더 둔다.

- **`products/product-translation.service.ts` (`ProductTranslationService`)** — 제품 텍스트 segment 들을 모아 `translation.translateBatch(segments, locale)` 호출. `products.service.ts` 와 `discover/discover.service.ts`(`ProductTranslationService` 주입)가 소비. `products.module.ts` 가 `ProductTranslationService` 를 export.
- **`brands/brand-translation.service.ts` (`BrandTranslationService`)** — 브랜드 텍스트 segment 들을 모아 `translation.translateBatch(segments, locale)` 호출. `brands.service.ts` 가 소비, `brands.module.ts` 에 등록.

> 즉 호출 그래프는 `products/brands(+discover)` → `Product/BrandTranslationService` → `TranslationService` → Google v2 다. `TranslationService` 자체는 도메인 무관한 순수 배치 번역기다.
