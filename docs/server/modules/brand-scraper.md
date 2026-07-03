# brand-scraper — AI 기반 자사몰 자동 분석

- **모듈 경로**: `src/modules/brand-scraper/`
- **목적**: 브랜드가 자사몰 URL/상품 페이지 URL/소개서를 넣으면 AI 가 페이지를 분석해 브랜드 정보·상품 정보를 자동 추출 → 신청 폼 자동 채우기
- **SSRF 방어**: 사용자가 넣은 URL 을 그대로 fetch 하므로, `common/ssrf-guard.ts` 의 `assertPublicUrl` 로 **목적지 호스트가 공인 IP 로 리졸브되는지 먼저 검사**해 사내망·클라우드 메타데이터(169.254.169.254 등) 대역을 차단한다(`BlockedHostError` → 400). HTTP fetch 는 `redirect:'manual'`(follow 가 사후 호스트검사를 우회하므로), Playwright fetch 도 브라우저가 만드는 모든 http(s) 요청(네비게이션·리다이렉트·서브리소스)에 동일 가드를 건다.
- **관련 파일**: `brand-scraper.service.ts`, `brand-scraper.controller.ts`, `scraper.prompts.ts`, `common/ssrf-guard.ts`

## brand-scraper.controller.ts (`@Controller('v1/brand/scraper')`)

> 전체 라우트 `BrandGuard`.

| Method | Path                                       | Throttle           | 기능                                                            |
|--------|--------------------------------------------|--------------------|-----------------------------------------------------------------|
| POST   | `/v1/brand/scraper/analyze-homepage`       | 3회 / 분           | 자사몰 홈페이지 URL → 브랜드 메타 정보 추출 (LLM 호출 비용 큼)  |
| POST   | `/v1/brand/scraper/analyze-product`        | 6회 / 분           | 상품 상세 URL → 이미지 + 텍스트 → AI 로 상품 필드 추출          |
| POST   | `/v1/brand/scraper/analyze-deck`           | 3회 / 분           | 소개서(deck) 일괄 분석 → 멀티 제품 + 브랜드 정보 한 번에 추출   |

## 참고

- LLM 호출 비용이 비싸므로 throttle 이 다른 엔드포인트보다 매우 타이트하게 설정됨.
- 프롬프트는 `scraper.prompts.ts` 에 격리되어 있어 페이지 패턴별 튜닝 가능.
