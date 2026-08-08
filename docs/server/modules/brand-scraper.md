# brand-scraper — AI 기반 자사몰 자동 분석

- **모듈 경로**: `src/modules/brand-scraper/`
- **목적**: 브랜드가 **자사몰 홈페이지 URL**(텍스트 스크레이핑) 또는 **상품 상세/소개서 이미지**(Vision 분석)를 넣으면 AI 가 브랜드 정보·상품 정보를 자동 추출 → 신청/제품 폼 자동 채우기
- **입력이 두 종류다**: `analyze-homepage` 만 **서버가 URL 을 직접 fetch** 하고, `analyze-product`/`analyze-deck` 은 **클라가 올린 이미지 배열(`imageUrls`)** 을 그대로 OpenAI Vision 에 태운다(서버가 그 이미지를 fetch 하지 않는다).
- **LLM**: OpenAI chat completions (`OPENAI_API_KEY` 필수, 모델은 `OPENAI_MODEL` ?? `gpt-4o-mini`), `response_format: json_object` + zod 검증. 응답이 비었거나 JSON/스키마 검증에 실패하면 **502(BadGateway)**.
- **홈페이지 fetch 전략**: HTTP fetch(5s 타임아웃) → 본문이 2KB 미만이거나 `__next`/`root` 빈 컨테이너면 SPA 로 보고 **Playwright(chromium, 15s)** 폴백. 본문이 비면 502. chromium 미설치 등 브라우저 기동 실패는 503.
- **SSRF 방어**: 사용자가 넣은 홈페이지 URL 을 그대로 fetch 하므로, `brand-scraper/ssrf-guard.ts` 의 `assertPublicUrl` 로 **목적지 호스트가 공인 IP 로 리졸브되는지 먼저 검사**해 사내망·클라우드 메타데이터(169.254.169.254 등) 대역을 차단한다(`BlockedHostError` → 400 "접근할 수 없는 주소입니다"). HTTP fetch 는 `redirect:'manual'` 로 최대 5홉을 돌며 홉마다 재검증하고(follow 가 사후 호스트검사를 우회하므로), Playwright fetch 도 브라우저가 만드는 모든 http(s) 요청(네비게이션·리다이렉트·서브리소스)에 동일 가드를 건다.
- **관련 파일**: `brand-scraper.service.ts`, `brand-scraper.controller.ts`, `scraper.prompts.ts`, `brand-scraper/ssrf-guard.ts`

## brand-scraper.controller.ts (`@Controller('v1/brand/scraper')`)

> 전체 라우트 `BrandGuard`.

| Method | Path                                       | Throttle           | Body                                              | 기능                                                            |
|--------|--------------------------------------------|--------------------|---------------------------------------------------|-----------------------------------------------------------------|
| POST   | `/v1/brand/scraper/analyze-homepage`       | 3회 / 분           | `{url}` (1~2048자)                                | 자사몰 홈페이지 fetch → 텍스트/메타 → 브랜드 메타 정보 추출     |
| POST   | `/v1/brand/scraper/analyze-product`        | 6회 / 분           | `{imageUrls[1..12], brandName?}`                  | 상품 상세 페이지 이미지(위→아래 분할 조각) → **한 제품**으로 종합 추출 |
| POST   | `/v1/brand/scraper/analyze-deck`           | 3회 / 분           | `{imageUrls[1..20], brandName?}`                  | 소개서 페이지 이미지 → 브랜드 정보 + **여러 제품** 한 번에 추출 |

`imageUrls` 의 각 항목은 **http(s) public URL(R2 등)** 또는 **`data:image/(png|jpeg|webp|gif);base64,...`**(klow_brand 가 PDF→PNG 변환 / 긴 상세페이지 분할한 결과) 만 허용한다(항목당 문자열 길이 15,000,000자 상한).

## 응답 형태

- `analyze-homepage` → `{ name, tagline, description, logoCandidates[≤4], bannerCandidates[≤3], suggestedAccentColor, sourceFetchMode: 'http'|'playwright', warnings[] }` (로고/배너 후보는 LLM 이 아니라 HTML 파싱 결과).
- `analyze-product` → `{ name, categoryKey, categoryLabel, recommendedFor[], concerns[], keyIngredients[{name,effect}], tagline }`.
- `analyze-deck` → `{ brand: { name, oneLiner, tags[≤5] }, products: ProductAnalysis[≤30] }`. **브랜드 컬러는 deck 에서 추출하지 않는다**(제거됨). 가격도 추출하지 않는다 — 브랜드가 직접 입력.

## 참고

- LLM 호출 비용이 비싸므로 throttle 이 다른 엔드포인트보다 매우 타이트하게 설정됨.
- 프롬프트는 `scraper.prompts.ts` 에 격리되어 있어 페이지 패턴별 튜닝 가능.
- **제품명·핵심성분은 영문 강제**(해외 고객에게 그대로 노출) — 프롬프트가 회사명만 빼고 라인·시리즈·컨셉 단어는 모두 포함하도록 지시한다.
- **`recommendedFor`/`concerns` 는 고정 enum 이 아닌 영문 자유 텍스트 명사구**(예: "Dry skin", "Pore care"). 서버는 여기서 걸러내지 않고, 저장 시점의 zod(`EnglishTagList`/초안 `DraftTagList`)가 non-ASCII·초과분을 처리한다. 반면 `categoryKey` 는 `PRODUCT_CATEGORY_KEYS` 화이트리스트로 필터링해 벗어난 값은 `''` 로 비운다(단건·deck 공용 `normalizeCategoryKey`).
- 추출 결과는 서버 로그(`[deck] …`)로도 남겨 운영 중 품질을 바로 확인한다.
