# 브랜드 커스텀 도메인 연결 문서

KLOW 입점 브랜드가 자기 도메인(예: `shop.brandA.com`)을 연결하면, **그 주소에서 KLOW 쇼핑 흐름
전체**(브랜드관 → 제품 상세 → 장바구니 → 로그인 → 결제)가 동작하게 하는 기능의 설계 문서 모음.

> **현재 상태: 📄 문서 = 구현 미착수.** 5개 레포 어디에도 `customDomain` / `custom_domain` 문자열이
> **0건**이고, `klow_web` 에는 `src/middleware.ts` 자체가 없다. 완전한 신규 기능이다.
>
> 설계·통합 지점은 실측 코드와 대조해 확정했다 → 이 문서만 보고 구현에 들어갈 수 있다.
> 단 **🔴 착수 전 확인 필요 #0(Eximbay 도메인 제한)** 이 해소되지 않으면 P3(결제 경로)는 전제가 흔들린다.
>
> ⚠️ **`file:line` 은 2026-08-19 스냅샷**이다. 구현 시점엔 밀려 있을 수 있으니 **심볼명(함수/상수)으로
> 재확인**한 뒤 편집할 것.

## 목표 동작 (한 줄)

브랜드가 설정에서 도메인을 입력 → 안내된 DNS 레코드를 등록 → 몇 분 뒤 **그 도메인이 곧 브랜드의 KLOW
스토어**가 된다. 기존 `klow.kr/{slug}` 는 **그대로 살아있다**(301 하지 않는다).

## 문서 · 읽는 순서

**읽는 순서**: ① 이 README(결정 요약) → ② [`flow.md`](./flow.md)(왜 이렇게 하는지·흐름) →
③ [`implementation-plan.md`](./implementation-plan.md)(**정본 — 실제 빌드 스펙**).

| 문서 | 역할 | 정본 |
|---|---|---|
| [`flow.md`](./flow.md) | 왜 rewrite 하나로 안 되나(쿠키·CSRF·CORS·결제 리턴) · 요청 흐름 현재 vs 변경 후 · 도메인 상태 머신 · 결제 왕복 시퀀스 · 회귀 매트릭스 | **원리·흐름** |
| [`implementation-plan.md`](./implementation-plan.md) | P0~P5 로드맵 · Prisma 모델 · 모듈 구성 · Vercel API · 미들웨어/프록시 규칙표 · 쿠키 · 검증 · **§9 불변식 체크리스트** | **구현·스키마 정본** |

> **구현 시작점**: `implementation-plan.md` 의 **P0 부터 순서대로**. 각 PR 착수 전 **§9 불변식
> 체크리스트**를 반드시 먼저 읽는다 — 거기 있는 항목은 전부 **틀려도 컴파일과 테스트가 통과**한다.

## 확정된 요구사항 (2026-08-19)

| 항목 | 결정 | 비고 |
|---|---|---|
| **적용 범위** | **사이트 전체** — 브랜드관·PDP·장바구니·로그인·결제 전부 커스텀 도메인에서 동작 | "브랜드관만" 절충은 카페24·쇼피파이 어느 쪽도 하지 않는다 |
| **SSL·도메인 등록** | **Vercel Domains API 자동화** | klow_web 이 Vercel 배포. Pro 플랜은 도메인 무제한(soft 100k)·**추가 비용 없음** |
| **사용 자격** | **구독 `active` 브랜드면 어드민 승인 없이 즉시** | 슬러그 자율 변경 정책과 동일 |
| **기존 `klow.kr/{slug}`** | **유지. 301 하지 않는다** | 프로모션 링크·시딩 링크·현장 QR·카페24 임베드가 전부 무변경으로 계속 동작 |

## 다른 플랫폼은 어떻게 하나

두 곳 모두 방식이 같고, 핵심은 **"커스텀 도메인이 그 몰의 오리진 전부"** 라는 점이다.

| | 도메인 연결 | SSL | 몰 식별 | 세션·API |
|---|---|---|---|---|
| **카페24** | 브랜드가 등록기관(가비아 등)에서 **네임서버를 카페24로 변경**하거나 A레코드를 카페24 IP로 | 카페24가 무료 SSL 자동 발급 | 요청 **Host 헤더** → mall_id | 프론트·API·결제 전부 **그 도메인 한 곳**. 쿠키가 자기 도메인 쿠키라 3rd-party 이슈가 없다 |
| **쇼피파이** | 브랜드가 `CNAME → shops.myshopify.com` | Let's Encrypt 자동 | Host 헤더 → shop | 동일. 체크아웃도 같은 도메인 |
| **KLOW(이 설계)** | Vercel Domains API 자동 등록 + 안내된 A/CNAME | Vercel 자동 | Host → `BrandDomain.host` → slug | **커스텀 도메인에서만** API 를 same-origin 프록시로 서빙 |

## 확정된 핵심 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| **API 접근 방식** | 커스텀 도메인에서 **same-origin 프록시**(`/api-proxy/*`) | 진짜 cross-site 가 되면 Safari ITP 가 세션 쿠키를 차단하고 CSRF 가드가 모든 POST 를 403 한다. `flow.md` §1 |
| **프록시 적용 범위** | **커스텀 도메인만.** klow.kr 은 경로 불변 | klow.kr↔api.klow.kr 은 same-site(eTLD+1 동일)라 지금도 정상이다. 굳이 태우면 함수 비용과 회귀 위험만 생긴다 |
| **프록시 구현** | **Route Handler** (`next.config` rewrites 아님) | rewrites 는 요청 헤더를 추가할 수 없어 **실 클라이언트 IP 를 전달할 방법이 없다** → `Order.agreementIp`(PG 분쟁 증거) 오염. `implementation-plan.md` P3-2 |
| **데이터 모델** | `Brand` 컬럼이 아니라 **별도 `BrandDomain` 테이블** | apex 와 `www` 는 Vercel 에 각각 등록해야 하는 별개 도메인이고(레코드 타입도 A vs CNAME), 검증 상태 머신과 Vercel 챌린지 원문을 담을 곳이 필요하다 |
| **apex 판정** | **우리가 하지 않고 Vercel `apexName` 에 위임** | `brandA.co.kr` 은 레이블 3개지만 apex 다(Public Suffix List 문제). 한국 브랜드가 주 대상이라 자체 판정하면 **첫 고객부터 잘못된 레코드를 안내**한다 |
| **DNS 안내 값** | **하드코딩 금지** — Vercel 응답의 권장값을 저장해 그대로 표시 | `76.76.21.21` / `cname.vercel-dns.com` 은 현재값일 뿐이고 Vercel 이 리전별 타겟으로 옮겨가는 중이다 |
| **세션 쿠키** | klow_web 쿠키만 **host-only** 로 전환. admin/brand 쿠키는 `Domain=.klow.kr` 유지 | `klow_brand/src/middleware.ts` 가 도메인 공유에 의존한다 |
| **SEO(초기값)** | 커스텀 도메인 전량 **`noindex, follow`**, canonical 은 klow.kr 유지 | 중복 콘텐츠 위험 0. `siteConfig.url` 을 host 인식으로 바꾸면 5개 파일이 request-time dynamic 이 되어 ISR 이점을 잃는다. 브랜드 요구 시 P5 에서 브랜드별로 개방 |
| **구글 로그인** | P3 에서는 커스텀 도메인에서 **버튼을 숨긴다** | 3중으로 깨져 별도 핸드오프 설계가 필요하다(P5). 이메일 로그인은 정상 동작 |

## 착수 전 확인 필요

| # | 항목 | 막는 것 |
|---|---|---|
| **0** 🔴 | **Eximbay 가맹점에 허용 도메인(referrer) 제한이 있는가** — 아래 별도 절 | P3 결제 경로 (전제가 흔들릴 수 있음) |
| 1 | `GET /v6/domains/{d}/config` 응답에 권장 A/CNAME 값이 실려 오는지 | 없으면 DNS 안내 값 출처를 재설계 |
| 2 | `domain_already_in_use` 의 정확한 HTTP status + `error.code` 문자열 | 에러 매핑 |
| 3 | **Vercel 플랜** — Hobby 는 프로젝트당 50개 상한. Pro 여야 무제한 | 확장성 |
| 4 | Railway 엣지가 `X-Forwarded-For` 를 append 하는지 replace 하는지 + express `req.ips` semantics | 프록시 IP 신뢰 설계 확정 |
| 5 | **스테이징 klow_web 이 별도 Vercel 프로젝트인지** — 같은 도메인을 두 프로젝트에 붙일 수 없어 실도메인 테스트가 불가능하다 | 테스트 전용 도메인 필요 |
| 6 | 기존 브랜드 중 `customer-center`/`track`/`seed` 슬러그 보유자 유무 | P0 선행 |
| 7 | 커스텀 도메인 브랜드관의 법적 표기(통신판매 주체는 KLOW) — 푸터가 그대로 따라가므로 별도 조치는 불필요해 보이나 확인 권장 | 컴플라이언스 |

### #0 — Eximbay 문의 (잠재 블로커)

**확인된 사실**: `return_url`/`status_url` 은 `EXIMBAY_RETURN_BASE_SERVER`(= `api.klow.kr`) 고정이라
브랜드 도메인과 무관하고(`payment.service.ts:334-335`), 결제 payload
(`fgkey`/`payment`/`merchant`/`buyer`/`url`/`settings`/`product`)에도 **도메인 파라미터가 없다.**

→ 제한이 있다면 **가맹점 계정 설정** 쪽이고, 코드로는 확인이 불가능하다. Eximbay 에 직접 문의해야 한다.

문의 항목:
1. 허용 도메인 화이트리스트가 존재하는가? 존재한다면 **검사 기준**이 무엇인가 — ①결제창을 호출한 페이지의
   도메인(Referer) ②`return_url`·`status_url` ③둘 다?
2. 미등록 도메인에서 결제창을 호출하면 **거래가 거절되는가?**
3. 등록이 필요하다면 절차·소요기간·**등록 개수 상한**·**API/콘솔을 통한 가맹점 자체 등록 자동화 가능 여부**
4. **단일 MID 로 복수 도메인에서 결제창을 호출**하는 구성이 계약·심사 기준상 허용되는가?
5. 3-DS 인증·카드사 심사 관련 유의사항

⚠️ **3번의 "자동화 가능 여부"가 실제 판단 기준**이다. "가능하다"만 받고 건별 수기 등록이면, 브랜드가 늘
때마다 운영이 막혀 기능 자체가 성립하지 않는다.

ℹ️ 이 확인은 **P0~P2 와 무관**하므로 병행 가능하다. P3 착수 전까지만 답이 오면 일정에 영향이 없다.

<details>
<summary><b>메일 초안 (보내기 전 MID 만 채우면 됨)</b></summary>

> **받는 곳**: 담당 영업 매니저 + 기술지원(`tech@eximbay.com` 참조)
> **제목**: [가맹점 MID: ○○○○] 결제창 호출 도메인(Referer) 제한 여부 문의

안녕하세요, KLOW 운영사 ○○○입니다.

당사는 현재 Eximbay JavaScript SDK v2(`request_pay`)로 해외 결제를 연동하여 운영 중입니다.
서비스 확장에 따른 구성 변경을 앞두고 있어, 진행 가능 여부를 사전에 확인드리고자 문의드립니다.

**■ 현재 연동 구성**
- 가맹점 MID: `○○○○○○○○○○`
- 연동 방식: JavaScript SDK v2 (`request_pay`)
- 결제창 호출 페이지 도메인: `https://klow.kr`
- `return_url`: `https://api.klow.kr/payment/return`
- `status_url`: `https://api.klow.kr/webhooks/eximbay`

**■ 변경하려는 구성**
당사 플랫폼에 입점한 브랜드가 자사 도메인(예: `https://shop.brandA.com`)을 연결하면, 그 도메인에서도
동일한 상품을 판매할 수 있도록 하려고 합니다. 이때 **결제창을 호출하는 페이지의 도메인만 브랜드별로
달라지고**, 나머지는 모두 현재와 동일합니다.
- 가맹점 MID: **동일** (단일 MID 유지)
- `return_url` / `status_url`: **동일** (`api.klow.kr` 고정, 변경 없음)
- 실제 판매·정산 주체: **당사 단일** (브랜드는 상품 공급자이며 결제 당사자가 아닙니다)

**■ 문의 사항**
1. 가맹점(MID) 설정에 **허용 도메인 / URL 화이트리스트**가 존재합니까? 존재한다면 검사 기준이
   무엇입니까 — ①결제창을 호출한 페이지의 도메인(Referer), ②`return_url`·`status_url`, 또는 ③둘 다입니까?
2. 등록되지 않은 도메인에서 결제창을 호출할 경우 **거래가 거절되거나 결제창이 열리지 않습니까?**
3. 도메인 등록이 필요하다면 — 신청 절차와 소요 기간 / **등록 가능한 도메인 개수 상한** /
   **API 또는 관리자 콘솔을 통한 가맹점 자체 등록·자동화가 가능한지**
   (브랜드 입점에 따라 수시로 추가되므로 건별 요청 방식은 운영이 어렵습니다)
4. **단일 MID로 복수 도메인에서 결제창을 호출하는 구성**이 계약·심사 기준상 허용됩니까?
   별도 심사나 서류 제출이 필요하다면 안내 부탁드립니다.
5. 그 밖에 도메인 확장 시 3-DS 인증·카드사 심사 등에서 유의해야 할 사항이 있다면 알려주시기 바랍니다.

회신 주시면 일정 수립에 반영하겠습니다. 감사합니다.

⚠️ 보내기 전: `○○○○` 를 **운영 MID** 로 교체(`.env.example` 의 `1849705C64` 는 테스트 MID).
국내 결제도 쓰면 `EXIMBAY_DOMESTIC_MID` 도 함께 기재.

</details>

## 검토했으나 채택하지 않은 안

재논의를 막기 위해 기록해 둔다. 되돌리려면 **여기 적힌 근거가 먼저 무너져야 한다.**

| 안 | 왜 안 골랐나 |
|---|---|
| **브랜드관 한 페이지만 커스텀 도메인** (제품 클릭 시 klow.kr 로 이동) | 구현은 가장 싸지만 **사용자가 요구한 범위가 아니다**(사이트 전체). 카페24·쇼피파이 어느 쪽도 이 절충을 하지 않는다 |
| **`next.config.js` rewrites 로 프록시** | 요청 헤더를 추가할 수 없어 **실 클라이언트 IP 를 전달할 방법이 없다** → `Order.agreementIp`(PG 분쟁 증거) 오염. `trust proxy` 를 2로 올려 우회하면 직접 호출 경로에서 XFF 위조가 열린다. `implementation-plan.md` §4-2 |
| **Cloudflare for SaaS (Custom Hostnames)** | klow.kr DNS 가 이미 Cloudflare 라 후보였다. 그러나 **오리진이 Vercel** 이라 Vercel 도 그 호스트를 알아야 하고(Host 기반 라우팅), Host 를 바꿔 넘기는 Worker 가 추가로 필요해 체인이 한 단 더 길어진다. 도메인 수가 **수백 개 규모**가 되면 재검토 가치가 있다 |
| **운영팀이 Vercel 대시보드에서 수동 등록** | 1단계로는 가장 안전하지만 브랜드가 늘 때마다 사람이 개입해야 한다. Vercel Domains API 로 자동화가 되므로 처음부터 자동으로 간다 |
| **`klow.kr/{slug}` → 커스텀 도메인 301** (쇼피파이 primary domain 방식) | 브랜드 SEO 에는 유리하지만 프로모션 링크·시딩 링크·현장 QR·카페24 임베드가 **전부 한 번씩 튀고**, `/shop` 에서 브랜드관에 들어가도 도메인이 바뀐다. **사용자가 "둘 다 살려두기"를 선택**했다 |
| **klow.kr 도 프록시를 태워 경로 통일** | 디버깅 일관성이라는 장점은 있으나 klow.kr↔api.klow.kr 은 same-site 라 **지금 아무 문제가 없다**. 전 트래픽에 Vercel 함수 비용과 1홉 지연이 얹히고 회귀 위험만 커진다 |
| **`Brand.customDomain` 단일 컬럼** | apex 와 `www` 는 Vercel 에 각각 등록해야 하는 별개 도메인이고 레코드 타입도 다르다. 검증 상태 머신과 Vercel 챌린지 원문을 담을 곳도 없다 |
| **커스텀 도메인 self-canonical + index (초기부터)** | `siteConfig.url` 을 host 인식으로 바꾸려면 5개 파일이 request-time dynamic 이 되어 ISR 이점을 통째로 잃는다. 브랜드가 소수인 초기엔 손해다. 브랜드 요구 시 P5 에서 **브랜드별 플래그**로 개방 |

## 관련 문서

- [`../architecture.md`](../architecture.md) — 전체 구조·URL surface·요청 흐름
- [`../payment-integration.md`](../payment-integration.md) — Eximbay 결제 흐름(이 기능이 건드리는 리턴 경로)
- [`../server/modules/storefront-stats.md`](../server/modules/storefront-stats.md) — 브랜드관 방문 통계(회귀 대상)
- [`../server/modules/embed.md`](../server/modules/embed.md) — 카페24 임베드(무관하지만 CORS 규칙이 인접)
