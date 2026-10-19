# buyer-seo — klow.kr 바이어 공간 검색 노출 보강

목표: "wholesale k-beauty skincare" 류를 각 언어(en·ja·zh·vi·th·id·ru·ar)로 검색했을 때 klow.kr 이 걸리게 한다.

## 이미 끝난 것 (트랙 밖, 2026-10-19 · klow_web `35191f3` · 운영 배포됨)

기술 SEO 기본 — 결정 [storefront 2026-10-19](../../decisions/storefront.md#2026-10-19).
언어별 URL·canonical·hreflang·sitemap(2026-10-16) 위에, 제목·H1·설명의 현지 검색어(용어집 [`buyer-i18n/glossary.md §2-1`](../buyer-i18n/glossary.md)),
봇에게 첫 방문 모달 끄기, 소비자 `/product/*` noindex, twitter 상속 정리, 언어판 Breadcrumb URL, 푸터 언어판 `<a hreflang>`, sitemap lastmod 제거.

## 남은 것 — 왜 더 필요한가

기본 신호는 정리됐지만 키워드 페이지가 **카테고리 3개(skincare·sun-care·makeup)뿐이고 그마저 제품 그리드라 본문이 얇다.**
경쟁 검색어(Faire·Alibaba·국내 도매몰)에서는 그 검색어에 답하는 페이지와 텍스트 양이 순위를 가른다.
순위의 다른 큰 축(백링크·도메인 신뢰·시간)은 코드 밖이라 이 트랙에 넣지 않는다.

| 행 | 단계 | 레포 |
|---|---|---|
| 40 | **A. 품목 랜딩 페이지 + 본문** | klow_web (서버 변경 여부는 착수 시 결정 — 아래) |
| 41 | **B. 브랜드 페이지 본문** | klow_server → klow_web |
| 42 | **C. `<html lang>` 언어별 + 자잘한 것** | klow_web |

### A. 품목 랜딩 페이지 + 본문 (효과 가장 큼)

- ⚠️ **착수 전제: Search Console 실적 1~2주치**(2026-10-19 배포 기준). 어느 품목·언어 검색어로 노출이 생기는지 보고 품목을 고른다 — 추측으로 페이지를 늘리면 얇은 페이지만 는다.
- 품목 후보: toner · serum/ampoule · cream · sheet mask · sunscreen · cleanser.
- ⚠️ **정책 공백 — 착수 시 사용자에게 묻는다**: 품목을 무엇으로 묶나 — (a) 서버 카테고리를 세분화(klow_server + 어드민, 기존 `shop/categories/[slug]` 그대로 동작) / (b) 웹 전용 랜딩 + 제품 태그·이름 필터(서버 무변경이지만 태그가 자유 텍스트라 결정 [products 2026-07-30](../../decisions/products.md#2026-07-30) — 매칭이 흔들린다).
- 랜딩마다 본문 2~4문단 + FAQ 3~5개(MOQ·샘플 1개부터·5개 무료배송·수출서류). ⚠️ **확인된 사실만**(결정 [storefront 2026-10-15](../../decisions/storefront.md#2026-10-15)) — 배송일수·관세율 같은 근거 없는 수치 금지. 문구는 `src/i18n/kb` 직접 번역 + `npm run kb:check`.
- 카테고리 3개에도 같은 본문 블록을 붙인다(지금 가장 강한 키워드 페이지).
- 국가 랜딩("K-beauty wholesale UAE")은 이 단계 밖 — A 의 실적을 보고 판단.

### B. 브랜드 페이지 본문

확정분(2026-10-19): 소스 = `Brand.description` 그대로(`intro`) · 스토리 본문은 1곳이 한국어라 보류 · 한글 잔존 시 비움. 결정 storefront 2026-10-19 후속 단락.


브랜드 페이지(`app/kbl/[lang]/shop/brands/[slug]`)가 이름+사실+그리드뿐. 브랜드 소개 텍스트를 바이어 브랜드 응답(`/v1/buyer/brands/:slug`)에 싣고 `BuyerTranslation` 캐시로 번역, klow_web `KbBrandProfile` 에 렌더. 소스 필드(기존 브랜드관 소개 재사용 vs 바이어 전용 입력)는 착수 시 조사. 배포 순서 server → web(웹은 필드 없으면 숨김).

### C. `<html lang>` 언어별 + 자잘한 것

확정분(2026-10-19): 루트 `app/(consumer)/layout.tsx` · `app/(kb)/kbl/[lang]/layout.tsx` · About `availableLanguage` 는 영어 유지(확인 안 된 사실) · `sameAs` 보류(SNS 주소 없음) · 인증 토큰은 env.


- 루트 `app/layout.tsx` 의 `lang="en"` 고정 → route group 으로 루트 레이아웃 분리(`(kb)` 가 `<html lang={lang}>`). 파일 이동 규모가 커서 마지막. 아랍어는 LTR 유지(결정 2026-10-16 D8).
- 홈 JSON-LD `inLanguage`·`sameAs`(공식 SNS URL — 사용자 제공), About `availableLanguage` 8개, `alt=""` 이미지(갤러리 썸네일·브랜드 목록)에 이름, Bing·Yandex·Baidu 인증 메타(토큰 사용자 발급).

## 검증 (공통)

`npm run kb:check` · `npx tsc --noEmit` · 바꾼 파일 `npx eslint` → Googlebot UA curl 로 title·description·H1·canonical·hreflang·본문 텍스트·sitemap 포함 확인 → 배포 뒤 Search Console URL 검사, 1~2주 뒤 실적(검색어·국가).
