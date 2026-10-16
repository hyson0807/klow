# buyer-i18n — 바이어 공간 다국어 URL + 첫 방문 자동 언어

바이어 공간(`klow.kr/`)은 지금 영어로 하드코딩돼 있다. 이 트랙은 두 가지를 한다.

- **SEO:** `klow.kr/ja`, `/zh` 처럼 **언어별로 색인되는 URL** 을 만든다.
- **자동 언어:** 해외 바이어가 처음 들어오면 그 사람의 언어로 보여 준다.

상태는 [`../../PROGRESS.md`](../../PROGRESS.md) 만 갖는다. 이 폴더에는 적지 않는다.

## 결정 (2026-10-16 계획 세션, 사용자)

| # | 결정 |
|---|---|
| D1 | 언어는 기존 i18n 8개(`en ja zh vi th id ru ar`)다. 중국어는 `ch` 가 아니라 **`zh`**(ISO 639-1, hreflang 표준) |
| D2 | **영어는 접두 없이 `/` · `/shop/*`** 에 둔다(이미 색인된 URL 유지). 그 밖의 언어는 `/{lc}` · `/{lc}/shop/*` 이고, `/en/*` 은 308 으로 접두 없는 경로로 보낸다 |
| D3 | 자동 언어는 **첫 방문 `/` 에서만** 리다이렉트한다(307). 판정은 쿠키 `kb_lang` → `Accept-Language` 1순위 → `x-vercel-ip-country`(Vercel 이 붙이는 IP 국가 헤더) 순서다. **언어가 박힌 URL 은 절대 리다이렉트하지 않는다.** 구글봇은 미국 IP 이고 언어 헤더도 없다. 강제로 리다이렉트하면 영어 말고는 색인되지 않는다 |
| D4 | 번역 범위: UI 문구, About 그룹 문구, **상품·브랜드·홈 구성 데이터** |
| D5 | **하드코딩 문구는 Claude 가 직접 번역**한다. 기계번역(`i18n:fill`)은 쓰지 않는다. 먼저 용어집을 만들고, 문맥을 보며 번역하고, 역번역으로 점검한다 |
| D6 | **DB 데이터는 서버 LLM 번역(OpenAI) + DB 캐시**다. 소비자 화면의 Google MT 와 다르게 한다. 바이어 데이터는 어드민이 큐레이션해 양이 적고, 용어집을 프롬프트에 넣어 UI 와 용어를 맞출 수 있다 |
| D7 | 번역하지 않는 것: **브랜드명, 제품명, 성분(INCI), 숫자·단위.** 국가명은 웹에서 `Intl.DisplayNames` 로 처리한다 |
| D8 | `ar` 은 소비자 화면처럼 **LTR 그대로**, 번역만 한다. RTL 레이아웃은 범위 밖이다 |
| D9 | 어드민 수동 번역(override)은 v1 범위 밖이다 |

## 읽는 순서

1. 이 문서 — 결정
2. [`implementation-plan.md`](./implementation-plan.md) — **정본: 빌드 스펙.** §1 게이트, §2 설계, §3 단계 A·B·C
3. 착수 시점에 같이 읽을 것
   - [`decisions/storefront.md` 2026-10-05](../../decisions/storefront.md#2026-10-05)
   - [`decisions/storefront.md` 2026-10-12](../../decisions/storefront.md#2026-10-12) — SEO. 이 트랙이 hreflang 부분을 대체한다
   - [`decisions/storefront.md` 2026-10-15](../../decisions/storefront.md#2026-10-15) — About 은 확인된 사실만

`glossary.md`(용어집)는 C 단계 첫머리에서 만든다. 서버 LLM 프롬프트(A)는 그 전까지 implementation-plan §2-4 의 임시 용어 목록을 쓰고, C 에서 용어집과 맞춘다.
