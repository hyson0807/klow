# brand-scraper — AI 기반 제품/소개서 이미지 분석

- **모듈 경로**: `src/modules/brand-scraper/`
- **목적**: 브랜드가 **상품 상세/소개서 이미지**를 넣으면 AI 가 브랜드 정보·상품 정보를 자동 추출 → 신청/제품 폼 자동 채우기
- ⚠️ **서버는 아무 URL 도 fetch 하지 않는다.** 입력은 언제나 **클라가 올린 이미지 배열(`imageUrls`)** 이고 그대로 OpenAI Vision 에 태운다(서버가 그 이미지를 fetch 하지도 않는다 — URL 은 OpenAI 가 읽는다).
- **LLM**: OpenAI chat completions (`OPENAI_API_KEY` 필수, 모델은 `OPENAI_MODEL` ?? `gpt-4o-mini`), `response_format: json_object` + zod 검증. 응답이 비었거나 JSON/스키마 검증에 실패하면 **502(BadGateway)**.
- **관련 파일**: `brand-scraper.service.ts`, `brand-scraper.controller.ts`, `scraper.prompts.ts`

## ⚠️ 자사몰 URL 분석(`analyze-homepage`)은 제거됐다 (2026-09-15)

브랜드가 자사몰 홈페이지 URL 을 넣으면 서버가 그 페이지를 긁어(HTTP fetch → SPA 면 Playwright chromium 폴백) 브랜드 메타 정보를 추출하던 라우트가 있었다. 지금은 **없다.**

- **왜**: klow_brand 가 2026-08-19(`7e0e3de` "데드코드·중복 정의 제거")에 `api.scraper.analyzeHomepage` 호출을 지웠다. 그 뒤로 **세 프론트 어디에도 호출자가 0건**이었고, 소개서·상세 이미지 Vision 분석이 그 자리를 대신하고 있다.
- **어차피 운영에서 반쯤 죽어 있었다**: 레포 어디에도 chromium 설치 단계가 없어(`Dockerfile`·entrypoint·CI 전부) SPA 폴백은 항상 503 이었다.
- **함께 제거된 것**: `ssrf-guard.ts`(유일한 소비자가 이 fetch 경로였다) · `scraper.prompts.ts` 의 `SCRAPER_SYSTEM_PROMPT`/`buildUserPrompt` · `BrandDraft` 타입 · `scripts/scrape-test.ts` · npm 의존성 **`playwright`·`cheerio`** · `BrandScraperService` 의 `OnApplicationShutdown`(브라우저 정리).
- ⚠️ **되살릴 거라면 `ssrf-guard` 를 함께 되살려야 한다.** 사용자 입력 URL 을 서버가 fetch 하는 순간 SSRF 표면이 생긴다(사내망·클라우드 메타데이터 169.254.169.254). 이전 구현은 `assertPublicUrl` 로 목적지가 공인 IP 로 리졸브되는지 검사하고, HTTP 는 `redirect:'manual'` 로 홉마다 재검증했으며(follow 는 사후 호스트검사를 우회한다), Playwright 도 브라우저가 만드는 모든 http(s) 요청에 같은 가드를 걸었다. `common/client-ip.ts` 의 `normalizeIp` 로 대신하면 안 된다(hex 형 `::ffff:aabb:ccdd` 를 디코드하지 않는다). 원본은 klow_server 레포에서 되찾을 수 있다 — 삭제 커밋을 `git log --diff-filter=D --oneline -- src/modules/brand-scraper/ssrf-guard.ts` 로 찾아 `git show <그 커밋>^:src/modules/brand-scraper/ssrf-guard.ts`.

## brand-scraper.controller.ts (`@Controller('v1/brand/scraper')`)

> 전체 라우트 `BrandGuard`.

| Method | Path                                       | Throttle           | Body                                              | 기능                                                            |
|--------|--------------------------------------------|--------------------|---------------------------------------------------|-----------------------------------------------------------------|
| POST   | `/v1/brand/scraper/analyze-product`        | 6회 / 분           | `{imageUrls[1..12], brandName?}`                  | 상품 상세 페이지 이미지(위→아래 분할 조각) → **한 제품**으로 종합 추출 |
| POST   | `/v1/brand/scraper/analyze-deck`           | 3회 / 분           | `{imageUrls[1..20], brandName?}`                  | 소개서 페이지 이미지 → 브랜드 정보 + **여러 제품** 한 번에 추출 |

`imageUrls` 의 각 항목은 **http(s) public URL(R2 등)** 또는 **`data:image/(png|jpeg|webp|gif);base64,...`**(klow_brand 가 PDF→PNG 변환 / 긴 상세페이지 분할한 결과) 만 허용한다(항목당 문자열 길이 15,000,000자 상한).

## 응답 형태

- `analyze-product` → `{ name, categoryKey, categoryLabel, recommendedFor[], concerns[], keyIngredients[{name,effect}], tagline }`.
- `analyze-deck` → `{ brand: { name, oneLiner, tags[≤5] }, products: ProductAnalysis[≤30] }`. **브랜드 컬러는 deck 에서 추출하지 않는다**(제거됨). 가격도 추출하지 않는다 — 브랜드가 직접 입력.

## 참고

- LLM 호출 비용이 비싸므로 throttle 이 다른 엔드포인트보다 매우 타이트하게 설정됨.
- 프롬프트는 `scraper.prompts.ts` 에 격리되어 있어 페이지 패턴별 튜닝 가능.
- **제품명·핵심성분은 영문 강제**(해외 고객에게 그대로 노출) — 프롬프트가 회사명만 빼고 라인·시리즈·컨셉 단어는 모두 포함하도록 지시한다.
- **`recommendedFor`/`concerns` 는 고정 enum 이 아닌 영문 자유 텍스트 명사구**(예: "Dry skin", "Pore care"). 서버는 여기서 걸러내지 않고, 저장 시점의 zod(`EnglishTagList`/초안 `DraftTagList`)가 non-ASCII·초과분을 처리한다. 반면 `categoryKey` 는 `PRODUCT_CATEGORY_KEYS` 화이트리스트로 필터링해 벗어난 값은 `''` 로 비운다(단건·deck 공용 `normalizeCategoryKey`).
- 추출 결과는 서버 로그(`[deck] …`)로도 남겨 운영 중 품질을 바로 확인한다.
