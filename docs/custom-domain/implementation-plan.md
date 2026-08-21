# 커스텀 도메인 — 구현 정본

배경·원리는 [`flow.md`](./flow.md), 결정 요약은 [`README.md`](./README.md).
이 문서는 **무엇을 어떤 순서로 만드는가**의 정본이다.

⚠️ `file:line` 은 **2026-08-19 스냅샷**이다. 구현 시점엔 밀려 있을 수 있으니 **심볼명으로 재확인**한 뒤
편집할 것.

⚠️ **각 PR 착수 전 [§9 불변식 체크리스트](#9-불변식-체크리스트-착수-전-필독)를 먼저 읽는다.** 거기 있는
항목은 전부 **틀려도 컴파일과 테스트가 통과**한다.

---

## PR 구성

| PR | 내용 | 레포 | 이 단계에서 사용자에게 보이는 것 |
|---|---|---|---|
| **P0** ✅ | 정지 작업(예약 슬러그·하드코딩·집계 버그) — **2026-08-21 완료** | web, server, brand | 없음 (독립 배포 가능) |
| **P1** ✅ | 서버 기반: `BrandDomain` 모델 + Vercel 연동 + resolve + Origin 술어 — **2026-08-21 완료 · ⚠️ 미배포** | server | 없음 (아직 서빙 안 함) |
| **P2** ✅ | **핸드오프 수신부**(klow.kr `/handoff`) — **2026-08-21 완료 · ⚠️ 미배포** | web ⚠️ **P1 의 `/v1/storefront/resolve` 에 런타임 의존** | 없음 (klow.kr 에서 불가시·무해) |
| **P3** ✅ | klow_web 미들웨어 + 커스텀 도메인 서빙 + **핸드오프 송신부** — **2026-08-21 완료 · ⚠️ 미배포** | web | **커스텀 도메인이 실제로 동작** |
| **P4** ✅ | klow_brand 설정 UI — **2026-08-21 완료 · ⚠️ 미배포** | brand | 브랜드가 직접 등록 가능 |
| **P5** (선택) | **풀 프록시 승격**(로그인·결제까지 커스텀 도메인) · 링크 도메인화 · SEO index 개방 | 전부 | |

> ⚠️ **P2·P3·P5 는 2026-08-20 에 전면 재작성됐다.** 원래 계획은 커스텀 도메인 안에서 결제까지
> 끝내는 **same-origin 프록시**였으나, **결제·로그인만 `klow.kr` 로 넘기는 핸드오프**로 바꿨다.
> 근거는 [§4-0](#4-0-왜-프록시가-아니라-핸드오프인가). 프록시 설계 자체는 버리지 않고 **[§6-1 승격
> 경로](#6-1-풀-프록시-승격--로그인결제까지-커스텀-도메인)** 에 그대로 보존한다 — 브랜드가 실제로
> 요구하면 그때 올린다.

**순서: P0 → P1 → P2 → P3 → P4.**
⚠️ **P4 를 P3 보다 먼저 내면 브랜드가 도메인을 연결했는데 사이트가 안 뜬다.**

**롤백 지점**: P4 를 되돌리면 신규 등록만 막히고 기존 도메인은 계속 동작한다. P3 를 되돌리면 커스텀
도메인이 전부 죽지만 klow.kr 은 무사하다.

---

## 1. P0 — 정지 작업 ✅ **코드 완료 (2026-08-21) · ⚠️ 미배포**

독립 배포 가능하고 되돌릴 일이 없다. 코드는 3개 레포 `develop/custom-domain` 에 커밋돼 있고,
**배포는 P1 과 묶어서** 한다(운영 결정). 아래 §7 배포 순서를 그때 함께 볼 것.

| # | 내용 | 파일 | 상태 |
|---|---|---|---|
| 1 | 예약 슬러그에 `customer-center`·`track`·`seed`·`handoff` 추가 (F10) | `klow_web/src/lib/reserved-slugs.ts` · `klow_server/src/common/reserved-slugs.ts` (미러 2개, 41개) | ✅ |
| 2 | 도메인 정본을 **apex(`klow.kr`)** 로 통일 | `klow_web/src/lib/seo.ts` · `.env.example` + Vercel/Railway 설정 | ✅ |
| 3 | `klow.kr/${slug}` 하드코딩 → `storefrontLabel(slug)` | `klow_brand/src/components/auth/SlugCheck.tsx` | ✅ |
| 4 | 워크스페이스 `CLAUDE.md` cron 개수 6 → **8** | `CLAUDE.md` | ✅ |
| 5 | code 가 null 이면 `source='direct'` (F12) | `klow_web/src/app/[brandSlug]/[influencer]/page.tsx` | ✅ |

⚠️ **1번은 운영(production) DB 에서 충돌 0건을 확인하고 넣었다.** 로컬 `klow_server/.env` 는 **Neon dev
브랜치**라 그쪽 조회는 근거가 못 된다(브랜드 목록이 `test`·`test123` 류다). 앞으로 "기존 데이터가 있는가"를
묻는 모든 확인은 운영 브랜치에서 할 것.

⚠️ **1번의 두 파일은 반드시 같은 배포 창에** 나가야 한다 — 미러가 갈리면 서버는 가입을 허용하는데
klow_web 이 못 열거나 그 반대가 된다.

### 2번은 문서의 전제가 반대였다 — 기록해 둔다

착수 전 이 문서는 *"canonical(www)이 브랜드 공유 링크(apex)와 어긋난다"* 고 적었는데, 실측하니
**운영 Vercel primary 가 `www.klow.kr` 이고 apex 가 307 로 www 에 넘어가고 있었다.** 그리고 링크 계열이
**둘로 갈라져** 있었다:

| 링크 | 만드는 곳 | 전환 전 |
|---|---|---|
| 카페24 임베드 딥링크 · 프로모션 pretty 링크 · 시딩 링크 · 인스타 답글 · 주문확인/배송 메일 · **결제 리턴 303** | 서버, 전부 `FRONTEND_URL` 파생 | **www** |
| 현장 QR · 브랜드 공유 링크 | klow_brand `lib/storefront.ts`(API 호스트에서 파생) | **apex** |

전환 내용(전부 반영 완료):
- Vercel `klow-web`: `klow.kr` = **Production**, `www.klow.kr` = **308 → klow.kr**
- Railway `FRONTEND_URL` = `https://klow.kr` (`COOKIE_DOMAIN` = `.klow.kr` 유지)
- `seo.ts` 기본값 = `https://klow.kr`
  ⚠️ **운영 Vercel 에 `NEXT_PUBLIC_SITE_URL` 이 없다 — 그래서 이 기본값이 곧 운영값이다.**
  변수를 새로 만들지 말 것(코드가 단일 출처여야 값이 갈리지 않는다).
- Cloudflare DNS 는 **무변경** — apex `A 216.198.79.1`(이미 Vercel 현재 대역) · `cdn.klow.kr` 은 R2 라
  Proxied 유지. Vercel 의 `DNS Change Recommended` 는 에러가 아니라 새 CNAME 타겟 권장이다.

⚠️⚠️ **오리진이 www → apex 로 옮겨가 `localStorage` 가 한 번 초기화된다.** 손님들은 그동안 실제로는
`www.klow.kr` 오리진에 있었고, 저장소는 오리진 단위라 이관이 **원리적으로 불가능**하다(커스텀 도메인
문서가 iframe 카트 정리를 기각한 것과 같은 뿌리 — [§3-4](#3-4-결제-후-브랜드-도메인-카트-정리)).

- `klow-web-cart` → **비로그인 게스트 카트가 비어 보인다**(로그인 사용자는 서버 카트에서 복원)
- `klow-web-store` → 국가 선택 초기화 · **`promotionCode` 소실**(링크를 다시 타면 복구)
- `klow-vid` → 새 토큰 → 며칠간 **순방문이 부풀고** 진행 중이던 담기→결제 퍼널이 한 번 끊긴다
- 세션 쿠키는 `Domain=.klow.kr` 이라 **유지된다**

### P3 로 넘기는 메모

- `lib/host.ts` 의 본 도메인 Set 에 **`klow.kr` 과 `www.klow.kr` 둘 다** 넣는다(www 는 308 로 빠지지만
  미들웨어가 그 요청을 커스텀 도메인으로 오인하면 안 된다).
- ⚠️ Vercel 에 커스텀 도메인을 추가할 때 **"Redirect to primary domain" 이 붙으면 기능이 통째로 죽는다**
  (브랜드 도메인이 전부 klow.kr 로 튕긴다). P1 `vercel.client.ts` 가 도메인 추가 시 리다이렉트 설정을
  넣지 않는지 확인할 것.
- ⚠️ `VERCEL_PROJECT_ID` 는 **환경별로 다른 값**이다(`klow-web` / `klow-web-staging`).

### 배포 후 확인 (아직 남음)

- `curl -s https://klow.kr/shop | grep canonical` 이 apex 인지 (배포 전엔 www 였다)
- **결제 1건 완주** — 리턴 303 목적지와 주문확인 메일의 배송조회 링크가 apex 인지
  (`FRONTEND_URL` 은 dev DB 로는 관측이 불가능해 코드 리뷰로만 확인했다)
- 릴리즈 노트: ① 할인 링크 방문이 한 번 계단처럼 내려간다(봇·미매칭 제외 — 5번의 효과)
  ② 위 `localStorage` 초기화

---

## 2. P1 — 서버 기반 ✅ **코드 완료 (2026-08-21) · ⚠️ 미배포**

코드는 `klow_server` `develop/custom-domain` 에 있고 **배포는 P0 과 같은 창에서** 한다(§7).
아래 절들은 착수 시점의 설계 그대로이고, **어긋난 전제만 이 절에 기록한다.**

### 착수 중 어긋난 전제 (다음 PR 이 믿어야 할 것)

| # | 계획이 가정한 것 | 실제 | 결과 |
|---|---|---|---|
| 1 | §2-4 가 "`PUBLIC_BRAND_WHERE` 와 구독 게이트를 함께 태운다"고 적었다 | ⚠️⚠️ **`PUBLIC_BRAND_WHERE` 에는 구독 게이트가 아예 없다** — status `notIn [rejected, withdrawal_pending, withdrawn]` 뿐이라 `pending`·`draft` 도 통과한다. 구독 게이트는 **제품 쪽에만** 있었다(`product-selects.ts` `isPurchasable()`) | 브랜드 루트 짝 **`canServeStorefront()`** 을 `brands/brand-selects.ts` 에 신설. resolve 와 오리진 스냅샷이 둘 다 이걸 탄다 |
| 2 | §2-4 가 resolve 에 `/embed/*` 식 공개 표면 규칙을 암시 | **CORS 대상이 아니다** — 부르는 쪽이 브라우저가 아니라 klow_web 미들웨어(서버 사이드)다 | `ACAO:*` 수동 배선을 **복사하지 않았다**. `Cache-Control` 만 세팅 |
| 3 | §2-3 이 `@vercel/sdk` 를 쓴다고 적었다 | 실제로 필요한 값(`rank` 배열 권장값 · 409 의 `error.domain.projectId`)이 전부 raw 응답이고 SDK 를 써도 에러를 다시 벗겨야 한다 | **native fetch**(`instagram.client.ts` 관례). 새 의존성 0 |
| 4 | §2-5 가 "`credentials:true` 설정 자체는 유지"라고 적었다 | F8(커스텀 도메인은 `credentials:'omit'`)이 klow_web 규율에만 걸려 있는데 klow_web 엔 테스트 인프라가 없다(V10) | `enableCors` 를 **delegate** 로 바꿔 **오리진별로 credentials 를 가른다** — 커스텀 도메인은 `false` 라 F8 이 서버쪽에서 fail-closed 다 |
| 5 | `Brand.slug` 이 항상 있다고 암묵 가정 | **nullable** 이다 — 도메인은 붙었는데 슬러그가 없는 브랜드가 성립한다 | `slug === null` 이면 resolve 가 미해석으로 내린다(스펙이 잠금) |
| 6 | §2-3 이 API 버전을 add v10 / config v6 만 실측 | **5개 전부 실측 확정**(2026-08-21, 스테이징 프로젝트) | add `v10` / get·verify·remove `v9` / config `v6`. 409·400·404 본문 모양도 재확인 |

### 이 PR 이 실제로 남긴 것

- 마이그레이션 `20260821052240_add_brand_domains` — `CREATE TYPE ×2 + CREATE TABLE` (롤링 안전 · 백필 없음)
- 모듈 `src/modules/brand-domains/` 7파일 + `__tests__/` 5스펙 + `harness.ts`
- `common/validation/brand-domain.ts`(+배럴) · `brands/brand-selects.ts` 의 `canServeStorefront`/`STOREFRONT_BRAND_SELECT`
- `main.ts` Origin 술어 + CORS delegate · `app.module.ts` 등록 · `.env.example` 4개 · `test/app.e2e-spec.ts` cron 9
- `common/origin-policy.ts`(+스펙) · `brands/brand-selects.ts` 가 브랜드 축 게이트의 단일 소유자
- 문서: `docs/server/modules/brand-domains.md` + 색인 · 워크스페이스 `CLAUDE.md` Key Facts + cron 9

⚠️ 착수 후 `/simplify` 리뷰에서 **실제 결함 3개**가 더 나와 함께 고쳤다:
① `cleanupOrphans` 의 후보 조건이 서빙 게이트의 부정이 아니어서 `pending`·`rejected`·
`withdrawal_pending` 브랜드가 정리 대상에서 통째로 빠져 있었다(서빙은 막혔는데 Vercel 등록만
영원히 남는다) → 브랜드 축 규칙을 `brands/brand-selects.ts` 한 곳이 소유하게 하고 Prisma 짝
(`BRAND_SERVICEABLE_WHERE` / `BRAND_NOT_SERVICEABLE_WHERE`)을 신설, `product-selects.ts` 도
그걸 호출하게 바꿔 **네 벌이던 규칙을 한 벌로** 줄였다.
② `resolveHost` 가 정규화를 손으로 다시 써 **IDNA 변환이 빠져 있었다**(한글 도메인이 저장은
punycode, 조회는 U-label) → `canonicalHost()` 를 쓰기·읽기가 공유한다.
③ 재확인 실패 문구가 www 전용 카피를 재사용해 `shop.brand.com` 같은 호스트에도 "www 주소가…"
가 붙었다 → `pairErrorMessage` / `reconnectErrorMessage` 로 분리.

그 밖에 오리진 분류·정책을 **`common/origin-policy.ts`** 로 빼서 스펙으로 잠갔고
(`origin-exempt.ts` 선례 — 익명 콜백 안에서는 테스트가 닿지 않는다), 7일 폴링 포기 규칙도
순수 함수 `shouldGiveUpPending()` 으로 빼 스펙을 붙였다.

**검증 3층 결과**: typecheck(2 tsconfig) 통과 · `test:e2e` 2/2(cron 9) · 전체 unit **659/659** · **라우트 298 → 303**.
실측 확인: resolve 200(primary→slug / www→apex host / Host 헤더 형태 흡수) · 브랜드 도메인 오리진에
`ACAO` 는 붙고 **`ACAC` 는 안 붙음** · redirect 롤 호스트는 오리진 불허 · 비콘 POST 가 브랜드 도메인에서
200, 임의 오리진에서 403 · `/embed/v1.js` 는 여전히 `ACAO:*` · `origin-exempt.spec.ts` 무변경 통과.

### P2 이후로 넘기는 메모

- ⚠️ 로컬 `klow_server/.env` 의 `VERCEL_PROJECT_ID` 는 **스테이징(`klow-web-staging`)** 을 가리킨다(확인 완료).
  운영 Railway 에는 **운영 프로젝트 id** 를 따로 넣어야 한다.
- ⚠️ `redirectTo` 는 **호스트만** 담는다 — P3 미들웨어가 `https://{host}{pathname}{search}` 로 조립할 것.
- ⚠️ 미들웨어 양성 캐시는 **60초를 넘기지 말 것**. resolve 응답 캐시 60초와 합쳐 §2-4 가 수용한
  "반영 지연 최대 2분"이 그 합이다.
- 실도메인 E2E(§8-2 A-1·1-1)는 **아직 안 했다** — 스테이징 Vercel 프로젝트에 테스트 도메인을
  붙여서 P3 와 함께 한다. ⚠️ 그때 Vercel 대시보드에서 그 도메인에 **"Redirect to primary domain" 이
  붙지 않았는지** 확인할 것(붙으면 기능이 통째로 죽는다).


### 2-1. Prisma 모델

`Brand.customDomain` 단일 컬럼이 아니라 **별도 테이블**을 만든다. 근거는 [README 결정표](./README.md#확정된-핵심-결정).

```prisma
enum BrandDomainStatus { pending  verifying  active  error }
enum BrandDomainRole   { primary  redirect }

model BrandDomain {
  id            String            @id @default(cuid())
  brandId       String
  /// 소문자 punycode 호스트. 스킴·포트·trailing dot 없음. 라우팅 조회의 유일한 키.
  host          String            @unique @db.VarChar(253)
  role          BrandDomainRole   @default(primary)
  status        BrandDomainStatus @default(pending)
  /// 'A' | 'CNAME'. Vercel 응답에서 파생 — 우리가 판정하지 않는다(§2-3 apex 주의).
  recordType    String            @db.VarChar(8)
  /// 안내할 레코드 값. Vercel 이 준 값을 그대로 저장한다(하드코딩 금지).
  recordValue   String            @db.VarChar(253)
  /// 소유권 TXT 챌린지 원문(다른 Vercel 계정이 이미 그 도메인을 쓸 때만).
  verification  Json?
  lastCheckedAt DateTime?
  verifiedAt    DateTime?
  /// 사람이 읽을 실패 사유(브랜드 UI 에 그대로 노출). 민감정보 금지.
  lastError     String?           @db.VarChar(300)
  createdAt     DateTime          @default(now())
  updatedAt     DateTime          @updatedAt
  brand         Brand             @relation(fields: [brandId], references: [id], onDelete: Cascade)

  @@index([brandId])
  @@index([status, lastCheckedAt])
}
```

`Brand` 에 `domains BrandDomain[]` 역참조 1줄 추가. 브랜드당 상한은 **앱 레벨 3개**.
⚠️ 2개(apex + www)로 잡으면 **`shop.brandA.com` 를 쓰는 브랜드가 apex·www 리다이렉트를 함께 걸 수
없다** — 서브도메인 운영이 오히려 흔한 형태다. 상한은 Vercel 쿼터가 아니라 **운영 부담**을 막으려는
값이므로 숫자를 상수 하나로 두고 주석에 이유를 남긴다.

⚠️ **"primary 는 브랜드당 1개"를 DB 유니크로 못 박지 않는다** — Prisma 는 partial unique index
(`WHERE role='primary'`)를 지원하지 않고, `@@unique([brandId, role])` 로 하면 `redirect` 도 1개로
묶여 버린다. 서비스 트랜잭션에서 강제하고 스펙으로 잠근다. **이 선택의 이유를 코드 주석에 남길 것.**

**마이그레이션**: `CREATE TYPE`×2 + `CREATE TABLE` 뿐 → **롤링 배포 안전 · 백필 없음**.
`npx prisma migrate dev --name add_brand_domains`
(CLAUDE.md 규칙 — `migrate deploy`·수동 SQL·`db push` 금지. non-interactive 실패 시 사용자에게 직접 실행 요청)

### 2-2. 모듈 구성

CLAUDE.md 의 3레벨·평면·접미사 규칙 준수:

```
klow_server/src/modules/brand-domains/
├── brand-domains.module.ts
├── brand-domains.service.ts        # CRUD + 상태머신 + verified-origin 스냅샷
├── brand-domains.controller.ts     # surface: /v1/brand/domains   (BrandGuard)
├── public-domains.controller.ts    # surface: /v1/storefront/resolve (공개 GET)
├── brand-domains.cron.ts           # @Cron name: 'brand-domain-verify'
├── vercel.client.ts                # 외부 API 어댑터
├── domain-host.ts                  # 순수 헬퍼(정규화·거부 규칙) — 접미사 없는 명사
└── __tests__/
```

- `common/validation/brand-domain.ts` 신설 + `common/validation/index.ts` 배럴 re-export (규칙 7)
- `domain-host.ts` 는 소비자가 이 모듈뿐이라 `common/` 에 올리지 않는다 (규칙 3 휴리스틱)
- `vercel.client.ts` — stem 이 모듈명과 다른 이유(벤더명이 더 정확)를 주석에 남길 것

### 2-3. Vercel 클라이언트

`@vercel/sdk` 공식 패키지를 쓴다(수기 REST 보다 응답 타입이 안전).
`payment.service` 의 `eximbayFetch` 패턴(native fetch + `AbortController` 15s + `BadGatewayException`)을 따른다.

| 동작 | SDK 함수 / REST |
|---|---|
| 추가 | `projectsAddProjectDomain({ idOrName, teamId, requestBody:{ name } })` — `POST /v10/projects/{id}/domains` |
| 상태 조회 | `projectsGetProjectDomain(...)` |
| 검증 트리거 | `projectsVerifyProjectDomain(...)` |
| DNS 설정 확인 | `domains.getDomainConfig({ domain })` → `misconfigured` |
| 제거 | `projectsRemoveProjectDomain(...)` (+ 필요 시 `domainsDeleteDomain`) |

⚠️⚠️ **`verified` 는 "접속이 되는가"가 아니다 — "소유권이 다투지 않는가"다** (2026-08-21 실측).
우리가 소유하지도 않은 `dtest.co.kr` 을 추가하니 **그 자리에서 `verified: true`** 였고
(`POST …/verify` 도 그대로 `true`), 같은 시점 `getDomainConfig` 는 **`misconfigured: true`** 였다.
DNS 를 한 줄도 걸지 않은 상태다.

**그래서 `active` 전이 조건은 `verified === true` 만으로는 안 된다** — 그렇게 짜면 브랜드가 도메인을
입력한 **그 순간 "연결 완료"** 로 뜨고, 정작 주소를 열면 아무 데도 닿지 않는다. 조건은 반드시:

```
active  ⟺  domain.verified === true  &&  config.misconfigured === false
```

즉 **두 API 를 모두 봐야 한다**(`projectsGetProjectDomain` + `domains.getDomainConfig`). `verified` 가
false 인 경우는 **다른 Vercel 계정이 그 도메인을 이미 쓰는 때**뿐이고, 그때만 응답에 `verification`
챌린지가 실린다(충돌이 없던 실측에서는 **필드 자체가 없었다**).

⚠️⚠️ **apex 판정을 우리가 하지 않는다.** `brandA.co.kr` 은 레이블 3개지만 apex 다 — 이중 TLD 는 Public
Suffix List 문제이고, 한국 브랜드가 주 대상이라 자체 판정하면 **첫 고객부터 잘못된 레코드를 안내**한다.
도메인 추가 응답의 **`apexName` 을 정본**으로 쓴다(`apexName === name` 이면 apex → A 레코드).
`domain-host.ts` 는 **정규화·거부만** 담당한다.

⚠️ **DNS 값을 하드코딩하지 않는다.** apex `A 76.76.21.21` / 서브도메인 `CNAME cname.vercel-dns.com` 은
현재값일 뿐이고 Vercel 이 리전별 타겟으로 옮겨가는 중이다. `getDomainConfig` 응답의 권장값을
`recordValue` 에 저장해 화면에 **그대로** 띄운다. 하드코딩하면 Vercel 이 값을 바꾼 날 신규 연결이 전부
실패한다. (폴백 상수는 응답에 권장값이 없을 때만)

**실측 응답** (2026-08-21, `GET /v6/domains/{d}/config?teamId=`):

```json
{ "misconfigured": true,
  "recommendedIPv4":  [{"rank":1,"value":["216.150.1.1","216.150.16.1"]},
                       {"rank":2,"value":["76.76.21.21"]}],
  "recommendedCNAME": [{"rank":1,"value":"49f87b35b8122d1a.vercel-dns-017.com."},
                       {"rank":2,"value":"cname.vercel-dns.com."}],
  "nameservers": ["…"], "conflicts": [], "acceptedChallenges": [], "aValues": [], "cnames": [] }
```

⚠️ 모양이 단순 문자열이 아니다 — **`rank` 가 붙은 배열**이고 **IPv4 는 `value` 가 배열**(현재 2개)이다.
`rank:1` 을 쓰되 **CNAME 값의 후행 점(`.`)을 제거**해야 브랜드가 그대로 복사해 넣을 수 있다.
`rank:2` 는 legacy 폴백이므로 **화면에 같이 띄우지 않는다**(둘 중 뭘 넣어야 하냐는 문의가 생긴다).

ℹ️ 이 엔드포인트는 **도메인을 프로젝트에 추가하지 않아도 200 을 준다.** 등록 전에 "이 도메인은 이런
레코드가 필요합니다" 를 미리 보여줄 수 있다(P4 선택 사항).

**에러 매핑** (Vercel 공식 코드):

| Vercel | 우리 처리 | 브랜드에게 |
|---|---|---|
| `domain_already_in_use` (**HTTP 409**) | **row 를 만들지 않고 409** | 아래 ⚠️ — 점유자가 우리 팀인지에 따라 문구가 갈린다 |
| `invalid_domain` | 400 | 형식 오류 |
| `forbidden` | 502 + Sentry | "일시적 오류" (서버 설정 문제) |
| `rate_limit_exceeded` | 지수 백오프 재시도 | — |

⚠️ **`domain_already_in_use` 는 400 이 아니라 409 이고, "다른 Vercel 계정" 전용이 아니다** (2026-08-21 실측).
**같은 팀의 다른 프로젝트**와 충돌해도 같은 코드가 온다:

```json
{"error":{"code":"domain_already_in_use",
          "projectId":"prj_…",                       // 우리가 요청한 프로젝트
          "domain":{"name":"…","apexName":"…","projectId":"prj_…"},  // 실제 점유자
          "message":"Cannot add … since it's already in use by one of your projects."}}
```

→ **`error.domain.projectId` 로 갈라서 안내한다.** 그 값이 우리 팀 프로젝트면 내부 충돌(운영/스테이징을
잘못 지정했거나 이미 등록된 도메인)이고, 아니면 다른 계정이라 **소유권 TXT** 안내가 필요하다.
⚠️ 같은 KLOW 브랜드끼리의 중복은 `BrandDomain.host @unique` 로 **Vercel 을 부르기 전에** 잡아
`domain_taken` 으로 내린다 — 이 에러까지 오면 그건 우리 DB 밖의 충돌이다.

**호스트 검증** (`domain-host.ts` + zod `BrandDomainHostField`): 소문자·punycode 정규화, 스킴/경로/포트/
trailing dot 제거, 253자·라벨 63자 상한, **`klow.kr`·`*.klow.kr`·`*.vercel.app`·IP 리터럴·localhost
거부**(자기 도메인 탈취 방지).

### 2-4. resolve 엔드포인트

`GET /v1/storefront/resolve?host=` → `200 { slug: string|null, redirectTo: string|null }`

- **404 가 아니라 200 + `slug:null`** — 미들웨어에서 상태코드 분기를 줄인다
  (`/embed/v1/resolve` 가 `{found:false}` 로 뭉갠 것과 같은 이유)
- `status='active'` 인 것만 해석하고, ⚠️ **`PUBLIC_BRAND_WHERE`(`modules/brands/brand-selects.ts`)와
  구독 게이트를 반드시 함께 태운다.** 안 태우면 구독이 끊긴 브랜드의 도메인만 계속 살아
  "구독이 끊기면 브랜드관이 사라진다"는 기존 불변식을 우회한다
- `role='redirect'` 면 `redirectTo` 로 apex 를 돌려줘 미들웨어가 308 한다
- 응답에 `Cache-Control: public, max-age=60, s-maxage=60` (계약 명시)
- ⚠️⚠️ **`@SkipThrottle()` 을 이 라우트 하나에만 건다.** 부르는 쪽이 손님 브라우저가 아니라 **klow_web
  미들웨어(서버 사이드)** 라, klow_server 가 보는 IP 는 **Vercel 것 하나로 뭉친다.** 전역 스로틀은
  `ttl 60s / limit 60` **per IP**(`app.module.ts:45`)이므로 도메인이 몇 개만 붙어도 천장에 닿고,
  429 가 나면 미들웨어가 fail-open 해서 **전 브랜드 도메인이 동시에 KLOW 홈**(그리고 `/{seg}` 는 503)이
  된다. `payment/return`·`webhooks/eximbay` 가 같은 이유로 이미 `@SkipThrottle()` 이다.
  남용 방어는 ① 응답이 공개 정보(호스트→슬러그)뿐이고 ② `Cache-Control` 을 엣지가 흡수하며
  ③ 미들웨어 캐시가 앞단에 있다는 것으로 갈음한다. ⚠️ **모듈 전체가 아니라 이 라우트에만** — 브랜드
  CRUD·`check` 는 스로틀을 그대로 받아야 한다
- ⚠️ **반영 지연이 최대 2분이다** — 응답 캐시 60초 + 미들웨어 양성 캐시 60초. 즉 **구독 해지·도메인
  삭제 후에도 최대 2분간 계속 서빙**된다. 엣지에 분산된 미들웨어 캐시를 밖에서 무효화할 방법이 없어
  **이 지연은 설계상 수용**한다(두 값을 60초로 짧게 유지하는 것이 그 대가다). ⚠️ §2-6 의 "서빙이 즉시
  멈춘다"를 이 창만큼 완화해 읽을 것

**브랜드 CRUD API 계약** (P4 가 다른 레포·다른 PR 이라 **여기서 못 박는다**)

| 메서드 | 경로 | 가드 | 요청 | 응답 |
|---|---|---|---|---|
| GET | `/v1/brand/domains` | BrandGuard | — | `{ domains: BrandDomainDTO[] }` |
| POST | `/v1/brand/domains` | BrandGuard | `{ host: string }` | `201 { domain, pair? }` |
| POST | `/v1/brand/domains/:id/check` | BrandGuard · Throttle 6/분 | — | `{ domain: BrandDomainDTO }` |
| DELETE | `/v1/brand/domains/:id` | BrandGuard | — | `204` |
| GET | `/v1/storefront/resolve?host=` | 공개 · SkipThrottle | — | `{ slug, redirectTo }` |

```ts
type BrandDomainDTO = {
  id: string;
  host: string;                                   // punycode 정규화된 정본
  role: 'primary' | 'redirect';
  status: 'pending' | 'verifying' | 'active' | 'error';
  recordType: 'A' | 'CNAME';
  recordValue: string;                            // Vercel 이 준 값 그대로
  verification: unknown[] | null;                 // Vercel 챌린지 원문 배열 그대로
  lastError: string | null;                       // 사람이 읽는 사유(그대로 표시)
  verifiedAt: string | null;
};
```

⚠️ `brandId`·`lastCheckedAt` 은 **싣지 않는다**(브랜드가 쓸 일이 없다).
⚠️ `verification` 은 **재가공하지 않는다** — 우리가 모양을 바꾸면 Vercel 이 값을 바꾼 날 조용히 깨진다
(F3 와 같은 이유).

**에러 코드** — 브랜드 UI 가 분기할 수 있게 `{ code, message }` 로 내린다. **표시 문구는 서버 `message`
를 그대로** 쓴다(P4 규칙과 일치).

| code | HTTP | 언제 |
|---|---|---|
| `domain_invalid` | 400 | 정규화·거부 규칙 위반(`klow.kr`/`*.vercel.app`/IP/localhost/길이) |
| `domain_taken` | 409 | **다른 KLOW 브랜드**가 이미 연결 |
| `domain_already_in_use` | **409** | Vercel 쪽 충돌 — **다른 Vercel 계정**(소유권 TXT 필요) 또는 **우리 팀의 다른 프로젝트**. 둘은 `error.domain.projectId` 로 갈린다(§2-3) |
| `domain_limit` | 400 | 브랜드당 3개 초과 |
| `subscription_required` | 403 | 구독 `active` 아님 |
| `domain_service_unavailable` | 503 | `VERCEL_*` 미설정(§2-8) |

### 2-5. Origin 술어 (CSRF 가드 + CORS)

⚠️⚠️ **이 술어가 없으면 비콘이 아니라 브랜드관 화면이 통째로 빈다.** 두 가지가 걸린다:

| 걸리는 것 | 무엇이 | 없으면 |
|---|---|---|
| **CORS** (더 크다) | 브랜드관·PDP 의 **모든 데이터 GET**. `BrandStorefront` 는 `'use client'` 라 `useBrandBySlugQuery`·`useProductsByBrandQuery` 가 **브라우저에서** `api.klow.kr` 를 친다 | 제품·브랜드가 하나도 안 뜬다 |
| **Origin CSRF 가드** | 방문·담기 트래킹 비콘 2개 (`/v1/storefront-stats/track/{visit,cart-add}`) | 403 (집계만 유실) |

프록시가 없으므로 이건 **진짜 cross-origin** 이고 브라우저가 `Origin: https://shop.brandA.com` 을 싣는다
→ 지금 코드면 GET 은 CORS 로, POST 는 403 으로 막힌다.

`main.ts` 의 `buildAllowedOrigins()` 정적 배열을 **술어**로 바꾸고 화이트리스트 미스 시 폴백:

```ts
const domains = app.get(BrandDomainsService);   // NestFactory.create() 후 컨테이너에서 직접
const originAllowed = (o: string) =>
  originMatches(o, allowedOrigins) || domains.isVerifiedOrigin(o);
```

- `isVerifiedOrigin` 은 **동기**여야 한다(express 미들웨어가 sync). 서비스가 `Set<string>` 스냅샷을 들고
  TTL 60초로 **백그라운드 갱신**하되 현재값을 즉시 반환한다.
  ⚠️ **도메인 삭제·비활성 전이는 그 자리에서 스냅샷 갱신**(지연되면 안 된다)
- `app.enableCors({ origin: (o, cb) => cb(null, !o || originAllowed(o)) })` 로 **함께** 교체 —
  두 판정이 갈리면 반드시 사고가 난다
- 비콘 POST 가 `Content-Type: application/json` 이라 **방문마다 preflight** 가 붙는다 →
  `enableCors({ maxAge })` 를 함께 준다(없으면 요청 수가 2배)
- ⚠️ **자격증명은 이 오리진에서 오가지 않는다** — 커스텀 도메인 클라는 `credentials:'omit'` 로 고정한다(§4-2 · F8).
  `credentials:true` 설정 자체는 유지하되(klow.kr 용), **커스텀 도메인 요청에 쿠키가 실리면 설계가 어긋난 것**이다
- `common/origin-exempt.ts` 는 **손대지 않는다** — 새 예외 경로가 없다.
  `common/__tests__/origin-exempt.spec.ts` 가 **그대로 통과해야 하고, 통과하지 않으면 설계가 틀어진 것**이다
- ⚠️ `/embed/*` 의 수동 CORS(`res.setHeader`, `res.append` 금지, 영구 simple request)를 깨뜨리지 않는지 확인

### 2-5b. apex ↔ www 페어 — **브랜드는 호스트를 하나만 입력한다**

`role: primary | redirect` 를 **누가 언제 만드는지**의 규칙이다. 정하지 않으면 P1 서비스와 P4 UI 가
서로 다른 가정으로 만들어진다.

1. 브랜드가 입력한 호스트 = **`role='primary'`**. 화면도 이것 하나를 기준으로 그린다.
2. **그 호스트가 apex 이면** `www.{host}` 를 **`role='redirect'` 로 자동 함께 등록**한다
   (Vercel 에도 추가). 서브도메인(`shop.brandA.com`)이면 **페어를 만들지 않는다.**
   ⚠️⚠️ **거꾸로(서브도메인 입력 → apex 자동 등록)는 절대 하지 않는다** — apex 는 브랜드의 기존
   홈페이지일 가능성이 높고, 그걸 우리가 가져가면 **브랜드 사이트를 죽인다.**
3. ⚠️ **apex 판정은 primary 를 Vercel 에 추가한 뒤** 응답의 `apexName === name` 으로 한다(F2).
   우리가 미리 레이블 수를 세면 `brandA.co.kr` 에서 틀린다 — 즉 **페어 생성은 1번 성공 이후**다.
4. **페어 실패는 primary 를 막지 않는다.** `www` 가 이미 다른 곳에 물려 있어
   `domain_already_in_use` 가 나거나 DNS 미설정으로 `pending` 에 머무는 건 **정상 상황**이다.
   redirect row 의 `lastError` 에 사유를 남기고 브랜드가 재시도한다.
5. **삭제는 페어 단위** — primary 를 지우면 그 도메인의 redirect 도 함께 지운다(Vercel·DB 양쪽).
6. 브랜드당 상한 3개(§2-1)는 **primary + redirect 를 합쳐** 센다.

P4 화면은 **primary 의 상태**를 크게 그리고, redirect 는 그 아래 한 줄로 붙인다
(`www 도 연결됨` / `www 연결 실패 — 재시도`). ⚠️ 두 상태를 대등하게 그리면 브랜드가 "왜 두 개죠?"를
매번 묻는다 — 입력은 하나였기 때문이다.

### 2-6. 생명주기 — 등록 실패 롤백 · 해지 시 정리

- ⚠️ **Vercel 추가 성공 → DB insert 실패면 Vercel 에만 남는 orphan** 이 된다. 순서를
  `Vercel 추가 → DB insert` 로 두되 insert 실패 시 **보상으로 Vercel 에서 제거**하고, 그마저 실패하면
  Sentry 로 올린다(정리 cron 이 최종 안전망).
- ⚠️ **구독 해지·브랜드 탈퇴 시 Vercel 도메인을 제거하는 경로가 필요하다.** `resolveHost` 가 막아 서빙은
  즉시 멈추지만 **Vercel 프로젝트에는 도메인이 영구히 남아** 쿼터와 관리 부담이 누적된다.
  `brand-domains.cron.ts` 가 같은 배치에서 **orphan 정리**를 겸한다: 브랜드가 `withdrawn` 이거나 구독이
  오래 끊긴 도메인 → Vercel 제거 + row 삭제.
  ⚠️ **즉시 제거하지 않고 유예를 둔다** — 결제 실패로 잠깐 `past_due` 가 된 브랜드의 도메인을 날리면
  재결제 후 DNS 재설정을 다시 시켜야 한다(브랜드 입장에서 회복 불가에 가깝다).

### 2-7. 폴링 cron

`brand-domains.cron.ts` — 5분마다 `status IN (pending, verifying)` 중 `lastCheckedAt` 오래된 것
`take: 20`(rate limit 보호). `createdAt` 7일 초과 pending 은 `error` 로 내려 무한 폴링을 막는다.

전이 판정 (⚠️ **두 API 를 모두 본다** — 위 §2-3 의 `verified` 함정):

```
getDomainConfig(host)            → misconfigured?
getProjectDomain(host)           → verified? / verification?
  ├ verified && !misconfigured   → active   (+ origin 스냅샷 **즉시** 갱신)
  ├ !verified && verification 有 → verifying  (소유권 TXT 안내) → POST …/verify 재시도
  └ 그 외                        → pending   (A/CNAME 안내 유지)
```

⚠️ `verified` 만 보고 `active` 로 올리면 **DNS 를 안 걸어도 "연결 완료"** 가 된다(F29).

브랜드의 "지금 확인" 버튼은 같은 로직 1건: `POST /v1/brand/domains/:id/check` (Throttle 6/분).

⚠️ 새 cron 이라 **`test/app.e2e-spec.ts` 의 cron 기대 목록이 8개 → 9개**. 안 늘리면 `@Cron` 미등록이
**완전 무음**이다(typecheck 통과·로그 없음).

### 2-8. env

```
VERCEL_TOKEN=          # 프로젝트 도메인 관리 권한
VERCEL_PROJECT_ID=     # klow_web 프로젝트 (prj_xxx) — ⚠️ 환경별로 다른 값
VERCEL_TEAM_ID=        # 팀 소속이면 필수 (team_xxx)
```

⚠️⚠️ **`VERCEL_PROJECT_ID` 는 운영·스테이징이 서로 다른 프로젝트다**(`klow-web` / `klow-web-staging`,
2026-08-21 확인). 스테이징 klow_server 가 운영 프로젝트 id 를 들고 있으면 **테스트로 붙인 브랜드
도메인이 운영 사이트에 꽂힌다.** 플랜은 **Pro** 라 도메인 수 상한은 걱정하지 않아도 된다.

ℹ️ 프록시 공유 비밀(`KLOW_PROXY_SECRET`)은 **없다.** 핸드오프 방식에는 프록시가 없다(§4-0).
승격 시에만 필요하다 → §6-1.

⚠️ **부팅 fail-closed 가드를 붙이지 않는다.** 기존 fail-closed 3종(Eximbay·`GUEST_ORDER_SECRET`·OTP)은
"조용히 깨지고 돈이 사라지는" 경로다. 도메인은 미설정 시 브랜드가 즉시 에러를 보므로 부팅을 막을 성질이
아니다. 대신 서비스가 `503 도메인 기능이 아직 활성화되지 않았습니다` 로 명시 거부.

### 2-9. 유입 경로 enum — **`custom_domain` 을 추가하지 않는다**

커스텀 도메인 루트 방문은 전부 `direct` 로 잡힌다. "내 도메인 유입"을 구분하고 싶어지는데,
⚠️ **`StorefrontVisitSource` 에 `custom_domain` 을 넣으면 안 된다 — 축이 다르다.**

`source` 는 **유입 경로**(`direct` | `promotion`)이고 `custom_domain` 은 **호스트**다. 원장 키가
`(brandId, date, source)` 라 값은 **하나만** 저장된다. 커스텀 도메인으로 들어온 할인 링크 방문은
promotion 이거나 custom_domain 이거나 둘 중 하나가 되고, **어느 쪽을 골라도 한 축이 통째로 사라진다.**
promotion 을 잃으면 브랜드가 "이 링크에 할인을 계속 줄지"를 판단하는 그 숫자가 무너진다 — 커스텀
도메인을 붙인 브랜드에서만, 조용히.

**지금 결정: 커스텀 도메인 방문도 `direct` / `promotion` 그대로 기록한다.**

나중에 정말 호스트 축이 필요하면 그건 **enum 값이 아니라 별도 차원**이어야 하고(원장·읽기모델의 유니크
키가 바뀌는 별건 작업이다), 그때 과거 데이터가 없는 건 감수한다. ⚠️ **"나중에 넣으면 복구 불가라서 지금
넣자"는 유혹을 여기서 명시적으로 기각한다** — 복구 불가한 건 맞지만, 그 대가로 **이미 운영 중인 지표를
망가뜨린다.** 없는 데이터보다 틀린 데이터가 나쁘다.

---

## 3. P2 — 핸드오프 수신부 (klow.kr) ✅ **코드 완료 (2026-08-21) · ⚠️ 미배포**

코드는 `klow_web` `develop/custom-domain` 에 있다. 아래 절들은 착수 시점의 설계 그대로이고,
**어긋난 전제만 이 절에 기록한다.**

### 착수 중 어긋난 전제 (P3 이후가 믿어야 할 것)

| # | 계획이 가정한 것 | 실제 | 결과 |
|---|---|---|---|
| 1 | §3-3 이 "페이지 안에서 ①→②③④ 순서를 지키면" 복원이 안전하다 | ⚠️⚠️ **안 된다.** `SessionSyncMount` 은 `layout.tsx:77` 에서 **`{children}` 앞 형제**라 **effect 가 페이지보다 먼저** 돈다 — `syncServerProfileToStore(user)` 가 동기적으로 `syncCountry(프로필 국가)` 를 때리고(그래서 2단계가 비교하는 "기존 국가"부터 오염된다), 옛 카트로 `merge` 를 동시에 쏘며, `clearRemovedIds()` 가 핸드오프가 쓸 묘비를 지운다 | `useSessionSync` 안에 **`usePathname() !== '/handoff'` 스위치**. `/handoff` 가 같은 일(프로필 국가 업로드 → merge → replaceCart)을 직접 한다. ⚠️ "이미 동기화됨" 플래그는 **일부러 안 뒀다** — `/checkout` 에서 훅이 한 번 도는 게 no-op(`sameCart` early-return)이면서 핸드오프 merge 실패 시 **자가치유**가 된다 |
| 2 | "수량 **max-merge**" | ⚠️ `cart.service.ts:221` 이 `quantity: { set }` — **클라 승**이다. `Math.max`(:212)는 payload 내부 중복 제거용일 뿐 | 핸드오프 payload 가 그 id 들의 수량을 확정한다. 대신 3번이 필요해진다 |
| 3 | (언급 없음) | ⚠️ **`PUT /v1/cart/merge` 는 브랜드당 5개 상한을 검사하지 않는다**(상한은 `cart.upsert`:126 과 **주문 생성** `orders.service.ts:414` 에만 있다) | 합친 뒤 `brandRemainingCapacity` 로 **클램프**. 안 하면 손님이 결제 버튼에서 raw 400 을 본다 |
| 4 | §3-3 2단계 "버릴 id 들을 `removedIds` 로" | ⚠️ 스토어에 **이미 쌓여 있던 묘비**를 언급하지 않는다 | `기존 removedIds ∪ 폐기분` **합집합**. 살아남은 라인은 목록에서 뺀다(카트에 있는 상품의 묘비는 모순) |
| 5 | 비로그인 = `replaceCart(merged, null)` | ⚠️ 같은 §3-3 트랩의 "`syncedUserId` 보존"과 **자기모순**이다(쿠키 만료 직후에 실제로 갈린다) | **기존 값 보존**(`prevSyncedUserId`) |
| 6 | V2 "`repriceCartForCountry` 재사용" | ⚠️ 그 함수는 **이미 있는 라인을 다시 매기는** 것이라 `[productId,qty]` 로 라인을 못 만든다(`repriceCart` 가 기존 cart 를 map 한다) | per-line 조회를 **인덱스 보존** `fetchCartLines()` 로 추출해 둘이 공유 |
| 7 | §3-5 i18n | ✅ `GOOGLE_TRANSLATE_API_KEY` 가 `klow_server/.env` 에 실재 → `npm run i18n:fill` 로 6개 로케일 생성 | ⚠️⚠️ **fill 은 값이 en 과 같은 로케일 문자열을 "누락"으로 보고 다시 기계번역한다** — `labels.category` 의 큐레이션 값 3개(`id.mist`=Mist / `vi.toner`=Toner / `vi.serum`=Serum)가 `Kabut`·`Mực toner`·`Huyết thanh`(혈청)로 **되돌아갔다.** 손으로 복구했다. **다음에 fill 을 돌리면 그 3개를 반드시 다시 확인할 것** |
| 8 | 토스트 문구가 `useT` 로 충분하다 | ⚠️ 토스트는 effect 안에서 **한 번만** 만들어지는데 그 클로저의 `t` 는 **첫 렌더**의 것이라 persist rehydration 전 locale(en)로 굳는다 — 일본어 화면에 영어 토스트가 떴다(실측) | 토스트만 `translate(localeForCountry(getState().country), path)` 로 **부르는 시점에** 번역 |

### 이 PR 이 실제로 남긴 것

- 신규: `lib/handoff.ts`(`encode/decodeHandoff` + 오리진을 건너는 상수 `HANDOFF_PATH`·
  `HANDOFF_PARAM`·`PURCHASED_PARAM`) · `lib/host.ts`(`isCustomDomain`·`isExternalHref`) ·
  `lib/cart-sync.ts`(`mergeCartToServer`) · `app/handoff/page.tsx` · `i18n/locales/en/handoff.ts`
- 수정: `hooks/useSessionSync.ts`(경로 스위치 + 전송부를 `cart-sync` 로 위임) ·
  `store/useCartStore.ts`(`addRemovedIds`) · `lib/cart-reprice.ts`(`fetchCartLines` 추출) ·
  `lib/visitor-id.ts`(`VISITOR_ID_RE`·`adoptVisitorId`·`visitorIdForOrder`) ·
  `lib/locale.ts`(`currentLocale`) · `lib/api.ts`(`storefront.resolve`) ·
  `lib/brandReturn.ts`(`appendPurchasedToBrandReturn`) ·
  `checkout/{page,redirect/page,_components/SuccessView,preview/page}.tsx`
- **서버·brand·admin 무변경. 마이그레이션 없음.**

⚠️ **한 벌만 두기로 한 것 3가지** — 나중에 두 번째 사본을 만들지 말 것:
① **서버 카트 머지 절차**(`lib/cart-sync.ts`) — "묘비는 서버가 삭제를 확인했을 때만 비운다"가
`useSessionSync` 와 `/handoff` 두 곳에 흩어지면 한쪽만 고쳐진다.
② **"남의 오리진인가"**(`lib/host.ts isExternalHref`) — `?purchased=` 를 붙일지와 성공 화면을
`<Link>` 로 그릴지가 같은 값을 두 규칙(`startsWith('https://')` vs host 비교)으로 보고 있었다.
③ **주문이 쓸 방문자 토큰**(`visitor-id.ts visitorIdForOrder`) — `handoffVisitorId` 를 export 하지
않아 담기 비콘 같은 데 끼워 넣는 두 번째 호출부가 **구조적으로** 불가능하다.

**검증 결과**: `type-check`(i18n 파리티 포함) · `eslint`(신규 경고 0) · `build` 통과.
순수 함수 24케이스 수동 검증(라운드트립·8KB/100라인 상한·`o` 의 `//evil.com`·`javascript:`·
`host:port`·`host/path` 거부·dedupe). 실측 E2E(로컬 dev+prod, 실 DB): 게스트 국가변경 폐기 ·
브랜드 상한 클램프(4+3 → 5) · 로그인 경로(`PATCH /v1/auth/me` 1회 + `merge` 1회, `/checkout`
재진입에도 **국가가 안 되돌아감**) · **담기 비콘 0건** · `o=example.com` → `brandReturn` 미기록 ·
`?purchased=` 가 절대 URL 에만 붙고 상대경로엔 안 붙음 · 게스트→로그인 머지 무회귀.

⚠️ **dev 에서 `/checkout/success` 의 "계속 쇼핑" 버튼이 안 보이는 건 이 PR 과 무관한 기존
StrictMode 아티팩트다** — 그 페이지 effect 가 두 번 돌면서 두 번째에 이미 비운
`readBrandReturn()` 을 읽어 state 를 `null` 로 덮는다. 프로덕션 빌드에서는 정상이다(실측).

### P3 로 넘기는 메모

- ⚠️ 송신부는 `encodeHandoff` 를 그대로 쓴다. **`o` 는 `location.host`(소문자 host 만)** 여야 한다 —
  디코더가 대문자·포트·경로를 전부 거부한다(fail-closed).
- ⚠️ `?purchased=` 값은 `URLSearchParams` 가 콤마를 `%2C` 로 인코딩한다. 받는 쪽은
  `searchParams.get(PURCHASED_PARAM)` 로 읽으면 자동 디코드되므로 `.split(',')` 이면 된다.
  **파라미터 이름은 `lib/handoff.ts` 의 `PURCHASED_PARAM` 을 import 할 것** — 오리진을 건너는
  계약이라 문자열을 양쪽에 흩어 두면 갈린다.
- ⚠️ `isCustomDomain()` 은 **부정형**이다(본 도메인이 아니면 전부 커스텀). 본 도메인 판정은
  **존 접미사 규칙**(`host === apex || host.endsWith('.'+apex)`)이라 `www.`·`staging.klow.kr` 같은
  건 자동으로 덮인다 — 서버 `domain-host.ts` 가 `klow.kr`·`*.klow.kr` 을 커스텀 도메인으로
  **거부**하는 것과 정확히 맞물린다. 그 밖의 호스트(`*.vercel.app`·localhost)만 목록이다.
  ⚠️ P3 미들웨어는 어차피 호스트를 분류하므로, 그 판정을 아래로 내려보내고 이 함수를 그 값을
  읽는 쪽으로 줄이는 편이 낫다(지금은 두 번째 분류기가 될 수 있다).
- 커스텀 도메인 쪽 `?purchased=` **수신**부(§4-5)는 아직 없다.

---

커스텀 도메인은 **브라우징 + 담기까지**만 맡고, **로그인·결제·주문조회는 `klow.kr`** 이 맡는다.
그 경계를 건너는 순간 **오리진이 바뀌어 `localStorage` 가 따라오지 않는다.** 이 PR 은 klow.kr 쪽
**받는 쪽**만 먼저 만든다 — 아무도 아직 링크하지 않으므로 **klow.kr 사용자에게 보이지 않는다.**

### 3-1. 넘겨야 하는 것 — 상태 4개 + 복귀 주소 1개

| 값 | 어디에 사는가 | 안 넘기면 |
|---|---|---|
| 카트 라인 `{productId, quantity}` | `klow-web-cart` (zustand persist) | 결제 화면에 **빈 카트** |
| 가격 기준국 `country` | `klow-web-store` | 기준국이 **US 로 리셋** → 브랜드관에서 본 가격과 청구가가 갈린다 |
| `promotionCode` | `klow-web-store` (localStorage 영속) | **세일가가 정상가로 조용히 되돌아간다** |
| `visitorId` | `klow-vid` (localStorage) | **결제 단계 퍼널이 영구 0** (§4-3) |
| **복귀 host** | `location.host` (상태가 아니라 **주소**) | 결제 후 브랜드 도메인 카트가 **정리되지 않는다** (§3-4) |

⚠️ **상태는 이 4개가 전부다.** 다른 걸 더 싣고 싶어지면 먼저 "그 값의 정본이 서버에 있지 않은가"를
의심할 것. 5번째 `o` 는 상태가 아니라 **돌아갈 주소**이고, 그래서 **다른 4개와 취급이 다르다** —
쓰기 전에 **반드시 서버로 재검증**한다(§3-3).

### 3-2. `src/lib/handoff.ts` — 송신(P3)·수신(P2) 공유 순수 함수

```ts
export type HandoffPayload = {
  v: 1;
  c: string;                 // 가격 기준국 ISO2
  p?: string;                // promotionCode
  vid?: string;              // visitorId
  o?: string;                // 복귀 host (검증 전 raw — §3-3 에서 재검증)
  l: [string, number][];     // [productId, quantity]
};
export function encodeHandoff(p: HandoffPayload): string;        // base64url(JSON), 패딩 없음
export function decodeHandoff(raw: string): HandoffPayload | null; // 어긋나면 throw 대신 null
```

⚠️⚠️ **서명하지 않는다.** 담기는 값은 **전부 이미 클라이언트가 소유·조작 가능한 값**이고(카트는
localStorage, `country`·`promotionCode` 는 URL·모달, `visitorId` 는 클라 난수), **청구 금액의 정본은
서버 견적/주문 생성**이다. 서명을 붙이면 엔드포인트·비밀키·만료·재생방지가 따라오는데 **지키는 것이 0** 이다.
⚠️ **단 `o` 는 예외다** — 그건 나중에 **링크의 href 로 렌더**되므로 조작되면 결제 성공 화면이 임의
사이트로 보내는 링크가 된다. 서명 대신 **서버 재검증**으로 막는다(§3-3 · F21).
⚠️ 뒤집어 말하면 **가격을 payload 에 실으면 그 순간 서명이 필요해진다** → 싣지 않는다(F4).

크기는 제품 30개 기준 base64 약 1.2KB 로 URL 길이 문제가 없다. `decodeHandoff` 는 **raw 8KB · 라인
100개**를 넘으면 `null` 로 떨군다(정상 카트는 브랜드당 5개 상한이라 근처도 못 간다 — 이 숫자는 기능
제약이 아니라 **손으로 만든 URL 방어선**이다).

### 3-3. `klow_web/src/app/handoff/page.tsx` (신규, `'use client'`)

**복원 순서가 곧 정확성이다:**

1. `decodeHandoff` 실패 → **아무것도 복원하지 않고** `/cart` 로. (조용히 실패해도 손님은 자기 klow.kr 카트를 본다)
2. **국가 먼저** — `setCountry(c)`. ⚠️ 기존 klow.kr `country` 와 **다르면 기존 카트를 버린다.**
   `OnboardingModal.select()` 의 기존 규칙과 **같은 이유**다(라인이 담을 때 `customerPriceUsd` 를
   스냅샷하므로 두 국가가 섞이면 표시가 ≠ 청구가). 같으면 수량 max-merge.
   ⚠️ **로그인 사용자면 버릴 id 들을 `removedIds` 로 모아 5단계 merge 에 함께 보낸다** — 로컬만
   지우면 다음 동기화가 **서버 카트에서 되살린다**(그게 묘비 메커니즘이 있는 이유다).
   ⚠️ 여기서 `clearCart()` 로 때우지 말 것 — 그건 **로그인 상태에서 서버 DELETE 까지 친다**
   (`OnboardingModal.tsx:72` 주석). 별도 왕복이 생기고, 그 사이 복원이 실패하면 손님 카트만 날아간다.
   `removedIds` 는 merge **한 번**에 폐기와 추가가 같이 들어간다.
3. `setPromotion(p)`
4. `visitorId` 이관 — §4-3 규칙
5. **카트** — `l` 의 각 `productId` 를 **그 국가·프로모션 기준으로 다시 조회**해 `toCartItem()` 으로 라인을
   만든다. `lib/cart-reprice.ts` 의 `repriceCartForCountry` 가 쓰는 **같은 `qk.productDetail` 캐시·같은
   헬퍼**를 재사용한다(사본을 만들면 두 경로가 각자 캐시 없이 같은 자원을 읽는다).
   조회 실패한 라인은 **버리고 나머지를 살린다** — 그쪽과 같은 판단이다(정본은 `/v1/orders/quote`).

   ⚠️⚠️ **쓰는 방법이 로그인 여부로 갈린다. 취향이 아니라 `useSessionSync` 와의 경합 때문이다.**
   **`useSession().ready` 를 기다린 뒤** 시작한다.

   | 상태 | 반영 방법 |
   |---|---|
   | 비로그인 | `replaceCart(merged, null)` 하나로 끝 |
   | 로그인 | **① `api.auth.updateProfile({ country })` → ② `api.cart.merge(lines, removedIds)` → ③ `replaceCart(res, user.id)` → ④ `repriceCartForCountry(country, qc)`** |

   **왜 그냥 `replaceCart` 로 끝내면 안 되나** — 그건 **서버에 복제하지 않는다**(스토어의 `set()` 하나다).
   그런데 `SessionSyncMount` 는 **fresh mount 마다** 로컬 카트를 읽어 `api.cart.merge()` 한 뒤 그 결과로
   다시 `replaceCart` 하고, 핸드오프는 **cross-origin 이동이라 klow.kr 레이아웃이 언제나 fresh mount** 다.
   순서에 따라 **복원한 카트가 서버 카트로 덮이거나**(sync 가 나중), **복원분이 서버에 영영 안
   올라간다**(sync 가 먼저 읽고 `syncedUserIdRef` 로 재실행을 막는다).

   **왜 ①이 먼저인가** — `useSessionSync` 의 `syncServerProfileToStore` 는 **프로필 국가로 앱 스토어를
   덮는다**(`user.country !== store.country` 면 `syncCountry(user.country)`). 프로필이 US 인 손님이
   브랜드 도메인에서 JP 로 골라 넘어오면 **핸드오프 국가가 프로필 국가로 되돌아간다** — F7 이 지키려던
   것이 그대로 깨진다. ⚠️ 그쪽의 자동 업로드는 `!user.country` **일 때만** 돌아서 이 경우를 못 메운다.

   **왜 ④가 필요한가** — `merge` 응답은 서버 카트(`cart.service.list`)이고 그건 **`User.country` 로
   가격을 매기며 프로모션 code 를 아예 받지 않는다**(CLAUDE.md 가 이미 적어 둔 알려진 갭). 응답을 그대로
   화면에 넣으면 **할인 링크로 들어온 손님의 카트가 결제 직전에 정상가로 보인다** — F6 이 막으려던 그
   실패가 이 경로로 되돌아온다. `repriceCartForCountry` 는 `useAppStore.promotionCode`(3단계에서 세팅)를
   읽어 **국가·프로모션을 함께** 반영하고, 서버에만 있던 라인(다른 기기에서 담은 것)까지 같이 고친다.
   ℹ️ `merge` 는 `items` 에 있는 id 를 `removed` 에서 **알아서 뺀다**(보존 우선) — 국가 폐기 목록과 새
   라인에 같은 상품이 겹쳐도 안전하다.
6. **복귀 주소 검증** — `o` 가 있으면 **`GET /v1/storefront/resolve?host={o}`**(P1 에 이미 있는
   엔드포인트, 새로 만들지 않는다)로 확인해 `slug` 가 non-null 일 때만
   `setBrandReturn("https://" + o + "/")`. ⚠️ **스킴은 클라가 `https://` 로 직접 조립**하고 `o` 는
   host 만 쓴다(`//evil.com`·`javascript:` 차단). 검증 실패면 **아무것도 저장하지 않는다** →
   성공 화면이 기존 폴백(마지막 방문 브랜드관 / 버튼 숨김)으로 떨어진다.
   ⚠️ **검증은 여기서 한 번만** 한다 — raw 값을 sessionStorage 에 **절대 넣지 않기 위해서**다.
   저장되는 것은 언제나 검증을 통과한 URL 뿐이다.
7. **5·6 이 끝난 뒤에** `router.replace('/checkout')` — **`?h` 를 히스토리에서 지운다.** 뒤로가기로
   재복원되면 2번의 "국가가 다르면 카트 폐기"가 다시 돌아 손님 카트를 두 번 날린다.
   ⚠️⚠️ **먼저 보내면 안 된다.** 복원은 제품 재조회·merge 로 **비동기**인데 `/checkout` 은
   `cart.length === 0` 이면 **`/cart` 로 튕긴다**(`checkout/page.tsx:295`). 카트가 채워지기 전에
   보내면 손님이 결제가 아니라 장바구니 화면에 떨어진다 — 그동안 이 페이지는 **로딩 상태**를 보여준다.

**⚠️ 트랩**

- ⚠️⚠️ **`addToCart` 로 복원하지 말 것.** 그 함수는 `trackStorefrontCartAdd` 비콘을 쏜다
  (`useCartStore.ts:7`). 복원은 **커스텀 도메인에서 이미 센 담기를 klow.kr 에서 한 번 더 세는 것**이라
  `cartAdds` 가 두 배가 된다(순담기자는 flip-once 라 안 늘어 **비율만 조용히 망가진다**).
  → 위 5단계 표의 경로(비로그인 `replaceCart` / 로그인 merge)로만 쓴다.
- ⚠️ 로그인 사용자면 `syncedUserId` 가 이미 붙어 있다 → **그 값을 보존**해 넘긴다. `null` 로 덮으면
  서버 카트와 끊긴 채로 결제에 들어간다.
- ⚠️ `/handoff` 는 **예약 슬러그**여야 한다(P0-1). 빠뜨리면 `handoff` 슬러그를 가진 브랜드가 브랜드관을 잃는다.
- 커스텀 도메인에서 이 경로가 열리면(예약어라 pass-through 된다) 아무것도 하지 않고 `/cart` 로 보낸다.
  **여기서 복원하면 손님이 브랜드 도메인에 남아 결제까지 가버린다.**

### 3-4. 결제 후 브랜드 도메인 카트 정리

결제는 klow.kr 에서 끝나므로 `/checkout/redirect` 는 **klow.kr 카트만** 정리한다. 손님이 브랜드
도메인에 두고 온 카트는 **다른 오리진**이라 손도 못 댄다 — 나중에 그 도메인에 다시 오면 **이미 산
상품이 담겨 보인다.**

**해법은 새 부품이 아니라 기존 3개를 잇는 것이다** (전부 이미 존재한다):

| 기존 부품 | 지금 하는 일 | 여기서 |
|---|---|---|
| `lib/brandReturn.ts` (`setBrandReturn`) | 성공 화면의 "계속 쇼핑" 버튼 목적지(마지막 브랜드관) | **커스텀 도메인 URL** 을 넣는다 |
| `lib/checkoutSelection.ts` (`readCheckoutSelection`) | 결제한 productId 목록 | 그대로 재사용 |
| `useCartStore.removeProducts(ids)` | klow.kr 카트에서 결제분 제거 | **브랜드 도메인에서도** 같은 함수 |

```
/handoff        setBrandReturn("https://shop.brandA.com/")        ← 검증된 값만 (§3-3 6단계)
/checkout/redirect
      const purchased = readCheckoutSelection();
      removeProducts(purchased)                                    ← klow.kr 카트 (오늘 그대로)
      setBrandReturn(그 URL + "?purchased=" + ids.join(","))       ← ⚠️ 추가되는 유일한 줄
/checkout/success  "계속 쇼핑" → https://shop.brandA.com/?purchased=…
shop.brandA.com    ?purchased= 읽고 removeProducts(ids) → router.replace 로 파라미터 제거 (§4-5)
```

⚠️ `setBrandReturn` 갱신은 **`removeProducts` 와 같은 블록**에 둔다. 그 블록이 "결제가 성공했고 이
상품들이 팔렸다"를 아는 **유일한 지점**이고, 둘이 갈라지면 한쪽만 도는 조합이 생긴다.
⚠️ 저장된 값이 커스텀 도메인이 아니면(=평소 klow.kr 브랜드관) `?purchased=` 를 붙일 필요가 없다 —
그쪽 카트는 이미 같은 오리진에서 정리됐다. **붙여도 무해**하지만(§4-5 가 멱등) 붙이지 않는 게 맞다.
⚠️ 판정은 **`new URL(저장값).host !== location.host`** 로 한다. `isCustomDomain()` 은 **자기
`location.host`** 를 보는 함수라 여기서는 쓸 수 없다(그 시점 호스트는 언제나 klow.kr 이다).

**⚠️ 이건 best-effort 다 — 명시적으로 감수한다**

- 손님이 **"계속 쇼핑"을 안 누르면** 브랜드 도메인 카트는 남는다. 결과는 "이미 산 상품이 담겨 보인다"
  이고 **재구매가 가능할 뿐 오청구가 아니다**(가격·재고·결제는 전부 서버 정본).
- `setBrandReturn` 은 **마지막 writer 가 이긴다.** 핸드오프 후 손님이 klow.kr 에서 **다른 브랜드관**을
  들렀다가 결제하면 복귀 링크가 그쪽으로 바뀌고 브랜드 도메인 카트는 정리되지 않는다. 그게 맞는
  동작이다 — 그 손님이 마지막에 있던 곳이 거기다.
- `brandReturn`·`checkoutSelection` 이 **sessionStorage** 라 **탭을 닫으면 사라진다.** 결제 후 바로
  탭을 닫는 손님(현장 QR 선례)은 정리 기회가 없다. 이건 두 헬퍼가 **이미 가진 성질**이고 같은 한계를
  공유하는 것이지 새로 만드는 결함이 아니다.

**기각한 대안** (재논의 방지 — 되돌리려면 아래 근거가 먼저 무너져야 한다)

| 안 | 왜 안 되는가 |
|---|---|
| **hidden iframe + postMessage 로 브랜드 도메인 localStorage 정리** | ❌ **동작하지 않는다.** 3rd-party storage partitioning 때문에 klow.kr 안의 `shop.brandA.com` iframe 이 보는 localStorage 는 **파티션된 별개 저장소**다(Safari·Chrome 둘 다). 1st-party 카트에 애초에 닿지 못한다 — 이 기능이 프록시를 버린 것과 **같은 뿌리** |
| **`GET /v1/storefront/purchased?visitorId=` 로 다음 방문 때 서버에 묻기** | 새 공개 엔드포인트가 **분석용 토큰 하나로 구매 이력을 조회**하게 만든다(`visitorId` 는 비밀이 아니다). 브랜드관 방문마다 쿼리도 는다. 얻는 건 "버튼을 안 누른 손님의 카트 정리" 하나 |
| **결제 성공 후 브랜드 도메인으로 자동 리다이렉트** | 성공 화면(주문번호·이메일)과 시딩 복귀 로직이 거기 있고, **결제 직후 추가 이동은 이 코드베이스가 이미 크게 데인 지점**이다(인앱 브라우저 컨텍스트 유실 → CLAUDE.md 「결제 확정 3중 방어선」) |
| **핸드오프 시 커스텀 도메인 카트를 비운다** | **결제는 대부분 이탈한다.** 이탈 손님이 뒤로 갔을 때 카트가 비어 있으면 **정상 흐름에서 손해**가 나고, 정리하려던 건 예외 상황이다. 비용/편익이 뒤집혀 있다 |

### 3-5. 손님에게 보이는 문구는 i18n 을 탄다

klow_web 은 **`src/i18n/locales/en/` 이 단일 원본**이고 `npm run i18n:fill` 로 ja/zh/vi/th/id/ru 를
생성한다([`klow_web/docs/i18n.md`](../../klow_web/docs/i18n.md)). ⚠️ **이 기능이 만드는 새 문구도 전부
그 규칙을 탄다 — 하드코딩 금지.** 커스텀 도메인 손님은 정의상 해외 손님이라 더 그렇다.

| 화면 | 키 | 비고 |
|---|---|---|
| `/handoff` 로딩 | `handoff.loading` | 복원 중(§3-3 7단계의 로딩 상태) |
| `/handoff` decode 실패 | `handoff.expired` | `/cart` 로 보내며 토스트 |
| 국가 상이로 카트 폐기 | **기존 `onboarding.cartCleared` 재사용** | `OnboardingModal` 이 이미 쓰는 키(`en/onboarding.ts:15`)다 — 같은 사건이므로 새 키를 만들지 말 것 |

⚠️ klow_brand(P4)는 한국어 단일이라 해당 없음.

**P2 를 단독으로 먼저 내보내도 안전한 이유**: `/handoff` 를 가리키는 링크가 아직 없고, `?h` 없이 열면
`/cart` 로 보낸다. klow.kr 의 기존 흐름은 **한 줄도 지나가지 않는다.**

---

## 4. P3 — 커스텀 도메인 서빙 (핵심) ✅ **코드 완료 (2026-08-21) · ⚠️ 미배포**

코드는 `klow_web` `develop/custom-domain` 에 있다. 아래 절들은 착수 시점의 설계 그대로이고,
**어긋난 전제만 이 절에 기록한다.**

### 착수 중 어긋난 전제 (다음 사람이 믿어야 할 것)

| # | 계획이 가정한 것 | 실제 | 결과 |
|---|---|---|---|
| 1 | `credentials:'omit'`(F8)은 "브라우저마다 로그인 상태가 갈리는 것"을 막는 **위생** 조치다 | ⚠️⚠️ **아니다 — 화면이 뜨는 조건이다.** `origin-policy.ts:31` 이 브랜드 오리진에 `credentials:false` 를 주므로 응답에 `Access-Control-Allow-Credentials` 가 안 붙고, 그러면 `'include'` 요청은 쿠키만 빠지는 게 아니라 **브라우저가 CORS 실패로 응답 자체를 막는다**(= 브랜드관 전체가 빈 화면). 서버가 이걸 fail-closed 로 의도했다 | 이 PR 의 **1순위 변경**. 그리고 `isCustomDomain` 을 **`'use client'` 인 `host.ts` 가 아니라 지시자 없는 `host-classify.ts`** 에 둬야 한다 — `api.ts` 는 지시자가 없어 서버 그래프에 들어갈 수 있고, `'use client'` 모듈을 import 하면 client reference 가 되어 터진다(지금 안 터지는 건 `brand-server.ts` 가 raw fetch 를 쓰는 우연이다) |
| 2 | rewrite 는 `new URL('/'+slug, req.url)` | ⚠️ 그건 **쿼리스트링을 버린다.** P2 가 만든 복귀 경로가 죽는다 — `/handoff` 가 저장하는 값이 `https://{o}/`(루트)라 **`?purchased=` 는 언제나 `/` 로 도착**하고 `/` 가 바로 rewrite 대상이다. UTM·`?_rsc=` 프리페치도 같이 날아간다 | **`req.nextUrl.clone()`** 로 바꿔 `search` 를 보존한다(실측 확인) |
| 3 | §2-2·flow.md: `/{seg}/…`(2세그먼트, 예약어 아님)는 "pass-through → 404" | ⚠️⚠️ **404 가 아니다.** `[brandSlug]/[influencer]` 는 `isBrandSlugAllowed` 만 보고 통과시켜 `shop.brandA.com/brandB/nana` 가 **브랜드 B 의 브랜드관을 브랜드 B 의 세일가까지 적용해** 렌더하고, `source='promotion'` 비콘이 나가 **브랜드 B 의 할인 링크 통계까지 오염**시킨다. (부록 V15 가 이미 "code 가 null 이어도 notFound 하지 않는다"고 적어 둔 것과 표가 모순이었다) | **F11 구멍이었다.** 1세그먼트와 동일 처리(`seg1===slug` 면 307, 아니면 404). `flow.md` 표도 함께 고쳤다 |
| 4 | 리다이렉트는 **308** | ⚠️ 308·301 은 브라우저가 **영구 캐시**해 되돌릴 수 없는데, 두 리다이렉트 모두 **가변 DB 상태**에서 파생된다(`redirectTo` · 슬러그). 서버 자신이 같은 데이터에 `max-age=60` 을 건다 | **307** 로 바꿨다(`NextResponse.redirect` 기본값도 307이라 어차피 명시가 필요하다). flow.md 도 정정 |
| 5 | 쿠키 경로 차단(F24)은 **화면**이 한다("미들웨어에서 리다이렉트하면 카트·국가·프로모션이 안 실려 넘어간다") | ⚠️ 그 근거는 **`/checkout` 에만** 해당한다. `/login`·`/my`·`/seed` 는 카트를 들고 갈 필요가 없다 | 그 다섯은 **미들웨어에서 307**(깜빡임 없음 · 대상 페이지 effect 와 경합 없음 · JS 꺼져도 동작). `/checkout` 만 화면이 핸드오프한다 |
| 6 | (언급 없음) | ⚠️ 수신부 `/handoff` 가 `setCountry(c)` 를 부르는데 그건 `syncCountry` 와 달리 **`onboardedAt` 까지 찍는다** | 국가 미선택 손님을 `?? 'US'` 로 넘기면 klow.kr 에서 **국가 모달이 영구 억제된 채 US 가격으로 결제**한다 → 송신부가 미선택이면 **넘기지 않고 국가 모달을 연다** |
| 7 | §5-4: PDP 바로구매의 담기 비콘 유실은 "감수한다" | ⚠️ `storefront-track.ts:317` 에 **"언로드 유실 걱정은 없다 — 담기 후 이동이 전부 `router.push`"** 라는 전제가 주석으로 박혀 있었다. `location.assign` 이 그걸 깬다. 게다가 같은 창에서 `peekVisitorId()` 도 아직 `null` 일 수 있다(→ **결제 단계 퍼널 영구 0**) | 감수하지 않고 고쳤다 — `flushPendingVisit(300ms)` 를 노출해 송신부가 기다린 뒤 이동한다. **그 주석도 함께 고쳤다** |
| 8 | `?mode=onsite` 는 "커스텀 도메인 대상 아님"이라 신경 쓸 것 없다 | ⚠️ 2번을 고쳐 쿼리를 보존하는 순간 **실제로 도달한다** → `onsiteMode` 가 켜져 결제가 `/checkout/onsite`(게스트 쿠키 필요)로 분기 | 미들웨어가 그 파라미터를 **떼어 내고 307** |
| 9 | 음성 캐시 TTL 300초 | ⚠️ 서버 응답 자체가 `max-age=60` 이다. 300초면 도메인 검증 직후 **아이솔레이트마다 404 와 정상이 뒤섞여** 브랜드가 "됐다 안 됐다"를 겪는다 | **60초**로 낮추고, **실패는 아예 캐시하지 않는다**(stale 읽기만). `Host` 는 공격자 통제 값이라 Map 에 **상한 256 + 축출**, fetch 전 **문법 검사** |
| 10 | (언급 없음) | ⚠️ 루트 레이아웃 컴포넌트에서 `useSearchParams()` 를 쓰면 **전 페이지가 CSR 로 deopt** 된다 | `CustomDomainMount` 는 `window.location.search` 를 마운트 effect 에서 읽는다(`useCheckoutGate` 선례). 빌드 결과 정적 페이지가 전부 `○` 로 유지됨을 확인 |

### 이 PR 이 실제로 남긴 것

- 신규: `src/middleware.ts` · `lib/host-classify.ts`(순수 호스트 분류 + `isHostShaped` — edge·서버
  그래프·클라 공용) · `lib/handoff-send.ts`(**`useGoCheckout()` = 결제 진입점 하나**) ·
  `components/common/CustomDomainMount.tsx` · `scripts/check-handoff.ts` ·
  값 없는 공유 상수 3종 `lib/api-base.ts` · `lib/api-types.ts` · `lib/onsite-entry.ts`
- 수정: `lib/host.ts`(분류를 위임 + `useIsCustomDomain` 훅) · `lib/handoff.ts`(`sanitizeHandoffPayload`) ·
  `lib/api.ts`(credentials) · `lib/storefront-track.ts`(`flushPendingVisit` + 주석 정정) ·
  `hooks/useSession.ts` · `hooks/useSessionSync.ts` · `components/layout/BottomTabBar.tsx` ·
  `app/layout.tsx` · `app/cart/page.tsx` · `app/product/[id]/page.tsx` · `package.json`
- **서버·brand·admin 무변경. 마이그레이션 없음. 신규 i18n 키 없음**(`i18n:fill` 을 돌리지 않았다).

⚠️ **`encodeHandoff` 가 자기 정화(self-sanitizing)가 됐다** — "encode 가 만든 것은 decode 가 반드시
받는다"가 이제 불변식이다. `decodeHandoff` 는 fail-closed 라 **선택 필드 하나만 어긋나도 payload
전체를 버리는데**, 송신부가 싣는 값 중 셋이 우리 통제 밖이다: `o = location.host`(**로컬·스테이징에서
포트가 붙어 실제로 전량 폐기됐다**) · `p = promotionCode`(localStorage) · `l`(persist 스키마).
어긋났을 때 증상이 "프로모션만 빠짐"이 아니라 **손님이 klow.kr `/cart` 로 떨어져 장바구니가 사라진
것처럼 보이는** 것이라 조용하다. 규약을 아는 `handoff.ts` 가 직접 떨어낸다 — 술어를 export 해서
송신부가 검사하게 하면 **검사를 잊는 두 번째 호출부**가 생긴다.

**검증 결과**: `type-check` · `next lint`(신규 경고 0) · `build` 통과(정적 페이지가 전부 정적으로
유지됨 = 루트 레이아웃 deopt 없음, `ƒ Middleware 77.4 kB` 등록 확인).
**신규 `npm run check:handoff`** — 순수 함수 9케이스(정상 왕복 · 포트 붙은 `o` · 망가진 promotionCode ·
형식 틀린 vid · 수량 클램프/dedupe · 150→100 라인 · 소문자 국가 · 빈 카트 · sanitize 멱등) 전부 통과.
⚠️ klow_web 에 테스트 러너가 없어 **프레임워크 없이 tsx 로 도는 순수 함수 검사만** 뒀다(의존성 추가 0).
**프로덕션 빌드 실측 라우팅**(`Host` 헤더 + resolve 스텁): 본 도메인 4종 무변경(`X-Robots-Tag` 없음) ·
커스텀 도메인 전 응답에 `noindex` · `/`→브랜드관 rewrite(주소창 유지) · `/{다른브랜드}`→**브랜드 A**
브랜드관 · `/{자기slug}`→307 `/` · **`/{다른브랜드}/{seg}`→404** · www 페어→apex 307(경로·쿼리 유지) ·
쿼리 보존(`?purchased=`·`?keep=`) 및 `mode` 만 제거 · klow.kr 전용 8경로 307 · `/track/x?t=` 통과 ·
`/handoff` 404 · `/sitemap.xml` 404 · **API 다운 시 `/`는 pass-through, `/{seg}`는 503**(F11 폴백).

### 정리 라운드에서 더 고친 것 (`/simplify` 4개 관점 리뷰)

구현 직후 재사용·단순화·효율·고도(altitude) 4관점 리뷰를 돌려 **같은 PR 안에서** 반영했다.
동작이 바뀐 것은 ①뿐이고 나머지는 구조 정리다.

1. ⚠️⚠️ **예약어 pass-through(허용적) → `STOREFRONT_SEGMENTS` 허용목록(제한적).** 기본값의 방향이
   틀려 있었다 — 새 최상위 라우트를 추가하면 **아무도 미들웨어를 안 고쳐도 전 브랜드 도메인에서
   세션 없이 열렸다.** 게다가 `RESERVED_BRAND_SLUGS` 는 **klow_server 미러라 klow_web 이 편집할 수
   없는 파일**인데 그게 브랜드 도메인 라우팅을 지배하고 있었다. 이제 모르는 경로는 404 다.
2. **`HOST_RE` 가 미들웨어에 복사돼 있었다** — `handoff.ts` 가 바로 위에서 "정규식을 export 하면
   검사를 잊는 두 번째 호출부가 생긴다"고 적어 놓고, 같은 diff 가 그 두 번째 호출부를 **사본으로**
   만들었다(export 보다 나쁘다). `host-classify.isHostShaped()` 한 벌로 통합.
3. **`MAX_HANDOFF_RAW_LENGTH` export 제거** — 같은 자기모순이었다. `encodeHandoff` 가 자기 상한을
   직접 검사하고 **`string | null`** 을 돌려준다(호출부가 잊을 수 없다).
4. **결제 진입점 2곳 → `useGoCheckout()` 하나.** 두 사본이 "**둘 다** 바꿔야 한다"는 주석으로
   동기화를 지키고 있었는데, 그 주석이 곧 초크포인트가 없다는 신호였다(세 번째 결제 버튼이
   생기는 날 깨진다). 현장 분기 중복도 같이 사라졌다.
5. **자격증명 정책의 소유자를 전송 계층으로.** `api.ts` 가 `canAuthenticate()` 를 노출하고
   `useSession`·`useSessionSync` 가 그걸 쓴다 — 세션 계층이 주소창(DNS)을 다시 묻지 않는다.
6. `dedupeLines()` 를 sanitize·decode 가 공유 · `dropIfUnmatched` 모듈 스코프화 ·
   `pass()`/`redirect()` 원시 함수(307 결정이 호출부 관례가 아니라 구조로 강제된다) ·
   빈 `if (!seg1) {}` 분기 제거 · `CustomDomainMount` effect 2개→1개 + 파생 ref 제거.
7. **효율**: `isCustomDomain()` 지연 캐시(모든 API 요청·매 렌더에서 재계산하던 것) ·
   `bareHost` 배열 할당 제거 · 문법 검사를 캐시 히트 뒤로 · `API_BASE` 4곳 통합 ·
   matcher 에 정적 자산 2건 추가 · `flushPendingVisit` 의 진 타이머 정리.
8. ⚠️ **정리 중에 스스로 만든 회귀를 잡았다** — onsite 상수를 `useOnsiteStore`(`'use client'` +
   최상위 `create()` 부수효과)에서 import 했더니 **zustand 가 통째로 edge 번들에 들어가** 미들웨어가
   77.4 → 82.1 kB 로 늘었다. 값 없는 `lib/onsite-entry.ts` 로 분리해 77.5 kB 로 복귀.
   **미들웨어가 import 하는 모듈에 부수효과를 들이지 말 것.**

**남긴 것**(리뷰가 제안했으나 이번 범위 밖): 라우트별 정책 테이블(`route-policy.ts`) 전면 도입 ·
`/checkout` 핸드오프를 라우트 자체로 내리는 안(그쪽은 `useCheckoutGate` 가 먼저 도는 마운트 경합이
생긴다) · `/shop` 링크를 그리는 나머지 지점(`useSmartBack` 폴백 등)의 일괄 처리.
ℹ️ 미들웨어가 **klow.kr 요청에서도 매번 호출**되어 즉시 bail 하는 비용은 Next 14 matcher 가
경로 기준이라 피할 수 없다 — 의식적으로 감수한 것이다.

⚠️ **아직 브라우저 E2E 는 하지 않았다** — 핸드오프 왕복·`credentials:'omit'` 실측(Chrome·Safari)·
결제 완주 후 `?purchased=` 정리는 §8-2 의 스테이징 수동 항목으로 남아 있다.


### 4-0. 왜 프록시가 아니라 핸드오프인가

프록시가 필요했던 이유는 [flow.md §1-2](./flow.md#1-2-shopbrandacom-에서-깨지는-것-4가지) 의 4가지다.
**결제·로그인을 klow.kr 에서 하기로 정하면 그중 2개가 소멸한다:**

| # | 깨지던 것 | 핸드오프에서 |
|---|---|---|
| 1 | 세션 쿠키 3rd-party (Safari ITP) | **소멸** — 커스텀 도메인에서 세션을 아예 쓰지 않는다 |
| 2 | Origin CSRF 가드 | **남는다** (트래킹 비콘 2개) → P1 §2-5 술어로 해결. 프록시는 필요 없다 |
| 3 | CORS | **남는다** → 같은 술어 |
| 4 | 결제 리턴이 `FRONTEND_URL` 하드코딩 | **소멸** — 결제가 klow.kr 에서 시작하므로 리턴도 klow.kr 이 정답이다 |

**그래서 없어지는 작업**: `/api-proxy` Route Handler · 쿠키 host-only 전환 + `clear` 대칭 수정 ·
`clientIp()` 확장 + `X-Klow-Proxy-Secret` · `KlowThrottlerGuard` · `Order.storefrontHost` 마이그레이션 ·
리턴 host 재검증(오픈 리다이렉트 표면이 **생기지 않는다**) · 구글 로그인 숨김/핸드오프 ·
**[README #0 Eximbay 확인](./README.md#0--eximbay-도메인-제한-2026-08-20-조사--남은-질문-1개)**
(결제창 호출 도메인이 오늘과 동일한 `klow.kr` 이라 PG 쪽에 바뀌는 게 0 이다).

**대가 — 이건 절충이다:**

- ⚠️ **결제 직전에 도메인이 바뀐다.** README 「확정된 요구사항」의 "사이트 전체"를 **좁힌 결정**이다.
  되돌리는 경로는 §6-1 에 그대로 남겨 뒀다.
- ⚠️ **커스텀 도메인은 항상 비로그인 화면**이다. 릴리즈 노트·CS 가이드 필수.

**근거로 삼은 두 가지 사실:**

- 같은 이음매가 **이미 운영 중**이다 — 카페24 임베드 버튼이 브랜드 자사몰에서
  `klow.kr/product/{id}?brand={slug}` 로 **더 이른 지점에서** 손님을 넘긴다.
- `useCheckoutGate`(`useAuthGate.ts:104`)가 **결제 진입 시점에 로그인/비회원을 다시 묻는다.**
  즉 도메인이 바뀌는 지점과 로그인 화면이 원래 겹쳐 있어, 이음매를 놓기에 가장 덜 어색한 자리다.

### 4-1. `klow_web/src/middleware.ts` 신설

지금 klow_web 에는 미들웨어가 **없다**. 책임은 딱 넷:

1. **본 도메인 즉시 bypass** — `klow.kr`, `*.vercel.app`, `localhost`, staging 호스트는 첫 줄에서
   `next()`. 트래픽 대부분이 여기서 끝나야 한다
2. **host → slug 해석** (커스텀 도메인일 때만)
3. **경로 재작성** ([flow.md §2-2 표](./flow.md#2-2-미들웨어-경로-판정))
4. **`X-Robots-Tag: noindex, follow` 부착** — 본 도메인이 아니면 **무조건**. host 해석 실패 중에
   크롤러가 중복 콘텐츠를 긁는 것까지 막는다

**host 해석 캐시** — 모듈 레벨 `Map`(양성 TTL 60초 / 음성 TTL 300초). Next 의 Data Cache 는 미들웨어에서
동작하지 않으므로 직접 관리한다.
**fetch 실패 시 stale 값 우선** — fail-closed 로 하면 API 가 3초 흔들릴 때 전 브랜드 도메인이 동시에
죽는다. 다만 **stale 도 없을 때의 폴백은 경로마다 다르다:**

기준은 **"이 경로를 처리하는 데 slug 가 필요한가"** 다. 예약어 판정은 klow_web 안의 정적 목록이라
resolve 없이도 되므로, 대부분의 경로는 폴백이 필요 없다:

| 경로 | slug 필요? | stale 없음 + resolve 실패 |
|---|---|---|
| `/` (루트) | 필요(rewrite 대상) | **pass-through**(fail-open). 최악이 "브랜드 도메인 루트에 KLOW 홈이 잠깐 뜬다"이고 되돌릴 수 있다 |
| 예약어 경로(`/product/…` `/cart` …) | **불필요** | **pass-through — 완전 정상 동작.** 여기까지 막으면 API 가 3초 흔들릴 때 멀쩡한 PDP·장바구니가 같이 죽는다 |
| `.` 포함 세그먼트 | 불필요 | pass-through |
| **`/{seg}`** (예약어 아닌 단일 세그먼트) | 필요(rewrite 대상) | ⚠️ **중립 오류(503). pass-through 금지** |
| `/{seg}/…` (2세그먼트 이상) | 불필요 | pass-through → 404 (원래도 404) |

⚠️⚠️ **`/{seg}` 만은 fail-open 하면 F11 이 통째로 무력화된다.** pass-through 된
`shop.brandA.com/brandB` 는 `[brandSlug]` 라우트에 **그대로 걸려 브랜드 B 의 브랜드관을 브랜드 A
도메인에 렌더**한다 — rewrite 규칙이 유일한 방어인데 그 방어를 건너뛰는 경로가 폴백이 되는 것이다.
"잠깐 KLOW 홈이 뜬다"는 **루트에만** 해당하는 이야기다.
ℹ️ `X-Robots-Tag: noindex` 는 **폴백 경로에서도 그대로 붙인다**(본 도메인이 아니면 무조건).

```ts
export const config = {
  matcher: [
    '/((?!_next/static|_next/image|api/|favicon\\.ico|icon.*\\.png|apple-icon\\.png).*)',
  ],
};
```

ℹ️ 프록시가 없으므로 **`api-proxy` 제외 항목도 없다**(구 계획에는 있었다).
ℹ️ `_next/data` 는 제외하지 **않는다** — App Router 의 RSC 요청은 같은 경로 + `?_rsc=` 로 오므로 rewrite
가 일관되게 걸려야 한다.

### 4-2. klow_web — "비로그인 전제" 배선

`src/lib/host.ts` 신설(정본 호스트 Set + `isCustomDomain()`). 그 위에서:

| 대상 | 커스텀 도메인에서 | 왜 |
|---|---|---|
| `api.ts` `BASE` | **절대 API URL 그대로** (`NEXT_PUBLIC_API_URL`) | 프록시가 없다. klow.kr 과 완전히 같은 경로라 회귀 위험 0 |
| `api.ts` `credentials` | **`'omit'` 로 고정** | ⚠️ 아래 |
| 헤더의 **로그인·내정보 진입점** | **렌더하지 않는다**(숨김) | 아래 ⚠️⚠️ |
| 직접 URL 로 들어온 세션 경로 — `/login` `/signup` `/my` `/orders` · **`/seed/*`** | **klow.kr 로 보낸다** | 진입점은 없앴지만 손님이 주소를 직접 칠 수는 있다. 아래 ⚠️ |
| `SessionSyncMount` | **마운트하지 않는다** | 세션이 없어 카트 머지·프로필 승격이 전부 no-op 인데 `/v1/auth/me` 만 계속 친다 |

⚠️⚠️ **`credentials:'omit'` 이 핵심이다.** 그냥 두면 `SameSite=None` 이라 **Chrome 은 쿠키를 실어
보내 로그인 상태로 보이고, Safari(ITP)는 차단해 비로그인으로 보인다** — 같은 사이트가 브라우저마다
다르게 동작한다. 더 나쁜 건 그 상태로 담으면 **서버 카트에 replicate 되어** klow.kr 카트와 어긋나는
것이다. "세션이 없다"를 우연에 맡기지 말고 **코드로 고정**한다.

⚠️⚠️ **로그인 진입점은 링크로 두지 않고 숨긴다.** klow.kr 로 보내면 **돌아오는 길이 없다** — 손님은
브랜드 도메인에 담아 둔 채 klow.kr 로 넘어가고, 거기서 로그인해도 그 도메인은 여전히 비로그인(F8)이며
장바구니는 오리진이 달라 비어 보인다. 실제로는 그대로 있지만 손님은 알 수 없어 **"장바구니가
사라졌다"** 가 된다.
**숨겨도 손님이 못 하는 일이 없다** — 로그인은 `useCheckoutGate` 가 **결제 진입에서 다시 묻고**(§4-0),
주문 조회는 확인 메일의 **URL 서명 링크**(`/track/{id}?t=`)로 열린다(부록 V7). 잃는 것은 "브랜드
도메인에서 주문내역 보기" 하나뿐이고, 그건 P5 승격(세션 핸드오프) 전에는 어차피 성립하지 않는다.

⚠️⚠️ **경로를 열거하지 말고 "쿠키가 필요한가"로 판정한다.** 특히 **`/seed/*` 를 빠뜨리기 쉽다** —
`seed` 는 예약 슬러그(P0-1)라 미들웨어가 pass-through 시키므로 **커스텀 도메인에서 그대로 렌더되는데**,
시딩 claim/checkout 은 **`klow_order` 게스트 쿠키에 의존한다**(`public-seeding.controller.ts:95` —
결제 이탈 후 예약 재사용 `resumeOrderId` 를 그 쿠키에서 복원하고, `payment/prepare` 의 게스트
ownership 검증도 같은 쿠키다). `credentials:'omit'` + cross-site 라 **그 쿠키는 절대 붙지 않는다** →
예약이 조용히 새로 잡히거나 결제가 막힌다.
⚠️ 더 나쁜 건 **시딩 페이지가 자체 결제 흐름을 돈다**는 점이다 — `seed/[token]/page.tsx:457` 의
`requestEximbayPay` 가 **그 페이지에서 바로** 같은 탭을 Eximbay 로 보낸다. 커스텀 도메인에 두면
**결제창 호출 도메인이 브랜드 도메인이 되어**(핸드오프로 피하려던 바로 그것) PG 전제가 깨지고,
리턴은 klow.kr `/checkout/redirect` 로 떨어지는데 시딩 복귀 breadcrumb 은 브랜드 도메인
`sessionStorage` 에 있어 **복귀도 실패**한다.

ℹ️ **`/track/{id}?t=` 는 예외로 남겨도 된다** — 쿠키가 아니라 **URL 서명 토큰**으로 여는 화면이기
때문이다(부록 V7). 이 근거를 규칙 옆에 적어 둘 것. 안 적으면 다음 사람이 "세션 비슷하니까" 하고 통째로
옮기거나, 반대로 `/seed` 를 여기 끼워 넣는다.

⚠️ `GoogleButton` 은 **손댈 필요가 없다**(로그인 진입점 자체가 klow.kr 로 나가므로 커스텀 도메인에서
렌더되지 않는다). 구 계획의 "P3 에서는 숨김"·"P5 구글 핸드오프"는 **둘 다 불필요**해졌다.

### 4-3. 핸드오프 송신부

- **진입점은 정확히 둘이다**(확인 완료): 카트 화면의 결제 버튼(`cart/page.tsx:244`)과 **PDP 바로구매**
  (`product/[id]/page.tsx:181` `handleBuyNow`). ⚠️ **둘 다 바꿔야 한다** — 하나만 바꾸면 나머지 하나가
  커스텀 도메인의 `/checkout` 으로 들어가 **세션 없는 결제**를 시도한다.
  ℹ️ `handleBuyNow` 는 `addToCart` 먼저 하고 이동하므로, 그 뒤 스토어에서 payload 를 만들면 **그 상품이
  이미 들어 있다**(zustand `set` 은 동기다). 담기 비콘도 정상적으로 한 번만 나간다.
  ⚠️ **PDP 담기 자체는 넘기지 않는다** — 담기까지 커스텀 도메인에서 끝내는 것이 이 설계의 전부다.
  ⚠️ 두 곳 다 `onsiteMode` 분기(`/checkout/onsite`)를 갖고 있는데 **현장 모드는 커스텀 도메인 대상이
  아니다**(§4-1) — 핸드오프는 일반 결제 분기에만 건다
- `location.assign(...)` 로 **top-level 이동**.
  ⚠️ **새 탭·`window.open` 금지** — 모바일 인앱 브라우저에서 컨텍스트가 끊긴다.
  결제 확정이 정확히 그 문제로 한 번 크게 데였다(CLAUDE.md 「결제 확정 3중 방어선」)
- payload 의 `o` 는 **`location.host`**(자기 자신). 받는 쪽이 재검증하므로 여기서는 그냥 싣는다
- `visitorId` 는 **`peekVisitorId()`** 로 읽는다. ⚠️ **`getVisitorId()` 금지** — 없으면 만들어 버리는데,
  브랜드관을 거쳤다면 반드시 있고 **없다는 건 트래킹이 꺼진 손님**이라 새 토큰은 원장 없는 쓰레기가 된다

**⚠️⚠️ `visitorId` 이관 규칙 (F5)**

- klow.kr 에 vid 가 **없으면** → 핸드오프 vid 를 그대로 심는다
- **있으면 덮지 않고** `sessionStorage['klow-handoff-vid']` 에 두고, **주문 생성 경로만**
  `handoffVisitorId() ?? peekVisitorId()` 를 쓴다

이유: 퍼널 원장은 `(brandId, date, visitorId)` 이고 그 행은 **커스텀 도메인에서 만들어졌다.** 주문이 다른
vid 로 들어가면 `recordPurchase` 가 행을 못 찾아 **그 브랜드의 결제 단계가 영구 0** 이다(서버는 조용히
버린다 — 2일 룩백도 못 구한다). 반대로 klow.kr 상용 손님의 vid 를 덮으면 그 사람의 klow.kr 원장 연속성이
끊긴다. 그래서 **"없을 때만 심고, 있으면 이번 주문에만 쓴다."**

### 4-4. 결제 리턴 — **변경 없음**

`/checkout` 부터가 klow.kr 이라 `POST /v1/orders` → `prepare` → 결제창 → `POST /payment/return` →
`/checkout/redirect` → `/checkout/success` 가 **전부 오늘과 같은 오리진**에서 일어난다.

- `Order.storefrontHost` 컬럼·마이그레이션 **없음**
- 리턴 host 재검증·`buildReturnRedirectUrl` **없음** — 오픈 리다이렉트 표면이 **생기지 않는다**
- `/checkout/redirect` 의 `sessionStorage` 의존(결제한 상품만 카트에서 제거 · 시딩 링크 복귀)이
  **원래대로 동작**한다. 프록시 안에서 가장 조마조마하던 부분이 통째로 사라진다
- **`payment.service.ts` 를 이 기능이 건드리지 않는다**

### 4-5. 결제 후 카트 정리 — 커스텀 도메인 수신부

브랜드관 진입 시 `?purchased=<id,id,…>` 가 있으면 (§3-4 의 반대편):

1. `useCartStore.removeProducts(ids)` — **klow.kr `/checkout/redirect` 가 쓰는 것과 같은 함수**
2. `router.replace` 로 **파라미터 제거** (F15 와 같은 이유 — 주소창·히스토리에 남기지 않는다)

ℹ️ `removeProducts` 는 비동기화 상태에서 묘비(tombstone)를 남기지만, **커스텀 도메인에서는 그게
아무 일도 하지 않는다** — 묘비는 그 오리진의 `localStorage` 에 있고 그 오리진은 **세션이 없어 서버
머지를 영원히 하지 않는다**(F8). 무해하게 쌓일 뿐이다.
⚠️ 반대로 말하면 **이 정리는 그 브라우저의 그 도메인에만 반영된다** — 같은 사람의 klow.kr 카트나 서버
카트에는 영향이 없다(그쪽은 `/checkout/redirect` 가 이미 정리했다).

⚠️ **`?purchased=` 는 검증하지 않는다.** 하는 일이 "그 손님 자기 브라우저 카트에서 그 id 를 뺀다"뿐이라
조작해도 **남에게 영향이 없다**(최악은 자기 카트를 자기가 비우는 것). 반면 `o` 는 **링크 href 로
렌더**되므로 반드시 검증한다(F21) — **둘의 취급이 다른 이유가 이것이다.**

---

## 5. P4 — klow_brand 설정 UI ✅ **코드 완료 (2026-08-21) · ⚠️ 미배포**

코드는 `klow_brand` `develop/custom-domain` 에 있다. 아래 절들은 착수 시점의 설계 그대로이고,
**어긋난 전제만 이 절에 기록한다.**

### 착수 중 어긋난 전제 (다음 사람이 믿어야 할 것)

| # | 계획이 가정한 것 | 실제 | 결과 |
|---|---|---|---|
| 1 | §5 가 `verifying` 을 **"SSL 발급 중"** 이라고 적었다 | ⚠️⚠️ **아니다.** `decideDomainStatus` 에서 `verifying` 은 `!verified && verification 有` — **다른 Vercel 계정이 그 도메인을 이미 쓰고 있어 소유권 TXT 챌린지가 필요한 상태**다. "발급 중" 으로 안내하면 브랜드가 **기다리기만 하고 TXT 를 영원히 안 넣는다** | 화면 문구를 "소유권 확인 필요"로 쓰고 `verification` 배열을 레코드 행으로 그린다. 위 본문도 정정했다 |
| 2 | §5 "`useSlugAvailability` 를 베껴 `useDomainAvailability.ts`" | ⚠️ **서버에 도메인용 availability 엔드포인트가 없다.** 중복은 `POST` 시점 409(`domain_taken`/`domain_already_in_use`)로만 알 수 있고, P4 는 brand 단독 배포라 새로 만들 수도 없다 — 베끼면 비동기 취소 로직이 **빈 껍데기**로 남는다 | 훅 파일을 만들지 않았다. `lib/domain.ts` 의 순수 `checkDomainInput()` + **기존** `hooks/useDebounced.ts`. `CheckBadge` 는 상태 종류가 같아 그대로 재사용하되 **`CheckMessage` 는 재사용하지 않았다**(그 `switch` 가 슬러그 전용 한국어를 하드코딩하고 `storefrontLabel(slug)` 를 부른다) |
| 3 | §5 "검증 폴링(`refetchInterval: 10s`)" — 대상이 안 적혀 있었다 | ⚠️ `POST :id/check` 는 **6회/분** 상한이고 1건이 Vercel API 를 2~3회 태운다. 10초 폴링이면 정확히 천장에 닿아 **브랜드의 수동 클릭이 429** 가 된다 | 폴링 대상은 **`GET /v1/brand/domains`**(전역 60/분). 서버 cron 이 5분마다 pending/verifying 을 다시 확인하므로 결과가 따라 들어오고, 즉시 확인은 "지금 확인" 버튼이 맡는다. `pending`·`verifying` 행이 하나도 없으면 폴링을 끈다 |
| 4 | (언급 없음) | ⚠️⚠️ **`lastError` 는 "에러가 있다"의 신호가 아니다.** `refreshOne` 이 확인할 때마다 덮어써서 **정상 `pending` 에도** `'DNS 레코드가 아직 확인되지 않았습니다'` 가 들어 있다 | 톤은 **`status` 가 정하고** `lastError` 는 `error` 행의 사유 줄로만 쓴다. `lastError != null` 로 빨간 배너를 그리면 **갓 만든 도메인이 전부 고장난 것처럼 보인다** |
| 5 | F3 = "Vercel 응답을 그대로 표시" | ⚠️ 그 값이 **빈 문자열일 수 있다**(`recommendedRecord` 가 rank:1 권장값이 없으면 의도적으로 `''`, 페어 실패 행도 `''`) | 복사 박스 대신 **"확인 중…"** 을 그리고 복사 버튼을 감춘다. **폴백 상수를 채우지 않는다** — 그럴듯한 옛 IP 를 띄우면 벤더가 타겟을 옮긴 날 신규 연결이 전부 조용히 실패한다 |
| 6 | §2-5b 4번 "페어 실패는 primary 를 막지 않는다" | ⚠️ 그 외에 **`pair: null` 이 두 가지 뜻**이다 — ① 서브도메인이라 페어 없음(정상) ② apex 인데 **도메인 개수 상한을 넘겨 서버가 조용히 생략**(로그에만 남는다) | 둘을 **`domain.recordType === 'A'`** 로 가른다. ⚠️ 이건 apex 를 우리가 판정하는 게 아니라(F2) **서버가 Vercel `apexName` 으로 정한 결과를 읽는 것**이다 — 그래서 F2 를 어기지 않는다 |
| 7 | §5 "구독 `active` 가 아니면 잠금 안내" | ⚠️ 서버 게이트는 `approved && (**어드민 생성 브랜드** \|\| 구독 active)` 인데 klow_brand `BrandDTO` 에 **`submittedById` 가 없어** 그 예외를 구분할 수 없다. 잠그면 그런 브랜드는 도메인을 붙일 **방법이 아예 없다**(어드민 도메인 UI 가 없다) | **안내만 띄우고 입력은 열어 둔다.** 최종 게이트는 서버 403 이고 그 한국어 문구를 그대로 토스트한다. (`MAX_PHONES` 가 폼을 미리 닫는 것과 다른 이유: 거긴 클라가 진실을 **정확히** 안다) |
| 8 | (언급 없음) | ⚠️ 이 API 의 에러 본문이 **세 가지 모양**이다 — A `{code,message}` / B Nest 기본 `{statusCode,message,error}`(**502 는 message 가 Vercel 영문 디버그 문자열**, 429 는 `ThrottlerException: …`) / C zod `{error,issues}`(message 키 없음) | `extractApiError` 를 그대로 쓰면 **벤더 영문이 브랜드 화면에 뜬다.** 반대로 `describeApiError` 만 쓰면 403 `subscription_required` 의 좋은 문구가 "이 항목을 수정할 권한이 없어요" 로 뭉개진다 → **`code` 유무로 가르는** 로컬 헬퍼 하나(`domainErrorMessage`) |
| 9 | §5 "`customDomain?` 을 세 함수에 추가" | `productLinkUrl` 은 P4 에 **호출부가 없다**(§6-2 에서 생긴다) | 호출부가 있는 **`storefrontUrl`·`storefrontLabel` 둘만** 열었다. ⚠️ 그리고 **`lib/onsite.ts` 의 `onsiteStoreUrl()` 에는 영원히 넘기면 안 된다** — 미들웨어가 커스텀 도메인에서 `?mode=onsite` 를 **떼어 내고 307** 해서 부스 QR 이 조용히 일반 모드로 떨어진다. 근거를 `storefront.ts` 주석에 박아 뒀다(§6-2 가 가장 먼저 밟을 지뢰다) |

### 이 PR 이 실제로 남긴 것

- 신규: `lib/domain.ts`(서버 `domain-host.ts` 의 의도된 크로스 레포 미러 — 정규화·거부·상한만,
  **apex 판정 없음**) · `settings/_components/DomainSection.tsx`
- 수정: `lib/api-types.ts`(`BrandDomainDTO`·`BrandDomainStatus`·`BrandDomainCreateDTO`) ·
  `lib/api.ts`(`domains` 네임스페이스 4개) · `lib/query-keys.ts`(`brandDomains`) ·
  `lib/storefront.ts`(선택 인자 2개 + onsite 금지 주석) · `settings/page.tsx`(1블록)
- **서버·web·admin 무변경. 마이그레이션 없음. 신규 서버 라우트 없음. 미들웨어 무변경**
  (`/settings/:path*` 가 이미 matcher 에 있다).

**검증 결과**: `type-check` · `npx eslint <바꾼 파일>`(경고 0) · `build` 통과.
`lib/domain.ts` 는 서버 `domain-host.spec.ts` 가 잠근 케이스(정규화 8종 · punycode 2종 ·
거부 17종 · **over-match 금지 3종** `myklow.kr`/`klow.kr.brand.com`/`notvercel.app`)를 그대로
돌려 **32/32 통과**를 확인했다. 라우트 4개는 실제 부팅한 klow_server 에서 매핑 확인(`GET` 401 /
쓰기 3개는 Origin 없는 curl 이라 403 = CSRF 가드 정상).
⚠️ **브라우저 E2E 는 아직 안 했다** — §8-2 A-1·1-1(실도메인 연결·apex 페어)과 함께 스테이징에서.

### P5 로 넘기는 메모

- `storefrontUrl`/`storefrontLabel` 의 `customDomain` 인자를 넘기는 곳은 지금 `DomainSection`
  **하나뿐**이다. §6-2 에서 ShareModal·QR·인스타·프로모션 링크에 붙일 때 **`onsiteStoreUrl` 만
  제외**할 것(위 9번).
- 카드가 접혀 있으면 목록을 아예 안 읽으므로 **`error` 로 떨어진 도메인을 브랜드가 먼저 알
  방법이 없다.** 알림이 필요하면 그건 카드가 아니라 스튜디오 상단 배너 쪽 일이다(구독 배너 선례).

`settings/_components/DomainSection.tsx` 신설 + `settings/page.tsx` 에 **1줄**.
근거: `AccountSection.tsx:35` 의 읽기전용 "브랜드 링크" 바로 아래 맥락이라 발견성이 좋고,
`/settings` 는 `klow_brand/src/middleware.ts` matcher 에 **이미 있다**.

- `_components/PhoneSection.tsx` 가 교본 — 자기 `useMutation` + `useToast()` 소유
- ⚠️ **`CollapsibleCard` 는 접히면 children 을 언마운트**하므로 검증 폴링(`refetchInterval: 10s`)이
  카드를 접는 순간 자동 정지한다. **별도 정리 코드가 없어도 되는 이유를 주석에 남길 것**
- ⚠️ **자동저장(`useBrandAutoSave.ts` 의 `buildBrandPayload()` 화이트리스트) 경로에 태우지 않는다.**
  도메인은 비동기 검증 상태가 붙는 값이라 800ms 디바운스와 맞지 않고, 화이트리스트 누락 함정도 피한다.
  전용 엔드포인트 + 명시 저장
- **재사용**: `hooks/useSlugAvailability.ts` 를 베껴 `useDomainAvailability.ts`
  (⚠️ **제네릭화 금지** — 슬러그는 `[a-z0-9-]`, 도메인은 점·punycode·PSL 로 규칙이 완전히 다르다),
  `components/auth/SlugCheck.tsx` 의 `CheckBadge`/`CheckMessage` 는 상태 타입이 같아 **그대로 import**.
  `lib/domain.ts` 는 서버 `domain-host.ts` 의 **의도된 크로스 레포 미러**(reserved-slugs 선례처럼 주석으로 못 박을 것)
- **API 계약은 §2-4 의 표·DTO·에러코드가 정본**이다(다른 레포라 여기서 다시 정의하지 말 것).
- **화면 상태** — 미연결(입력) / `pending`(A/CNAME 안내) / `verifying`(**소유권 TXT 챌린지** — ⚠️ SSL 발급 중이 **아니다**, 아래 정정 1) / `active`(링크 + 연결 해제) / `error`(사유 + 재시도). 목록을 10초 폴링한다(⚠️ `check` 가 아니다 — 정정 3)
  ⚠️ 상태는 **`role='primary'` 하나를 기준**으로 크게 그리고, `www` 페어는 그 아래 **한 줄**로 붙인다
  (§2-5b). 둘을 대등하게 그리면 "입력은 하나였는데 왜 두 개죠?" 를 매번 묻는다
  ⚠️ **안내가 두 가지다** — ① A/CNAME 접속 레코드 ② **소유권 TXT 챌린지**. 계획은 둘 다 `pending` 안에
  있다고 적었지만 실제로는 TXT 가 붙는 순간 status 가 **`verifying` 으로 갈린다**(둘은 동치라 지시는
  그대로 옳고, **status 로 나누는 편이 읽기 쉽다**). 값은 **서버가 준 타입·값 그대로** 표시하고
  클라에서 판정하지 않는다
- 구독 `active` 가 아니면 잠금 안내. `settings/page.tsx` 에 이미 있는 `qk.subscription` 값을 prop 으로 내린다

**`lib/storefront.ts`** — 링크 문자열의 단일 출처(소비처 13곳). **선택 인자를 뒤에 추가**해 기존 호출부가
그대로 컴파일되게 한다:

```ts
storefrontUrl(slug?, customDomain?)     // ✅ P4
storefrontLabel(slug?, customDomain?)   // ✅ P4
productLinkUrl(slug, productId)         // 무변경 — 호출부가 §6-2 에서 생긴다
// embedScriptUrl() 은 API 호스트라 무변경
```

⚠️ 값 규칙은 P3 미들웨어 rewrite 와 **정확히 대칭**이어야 한다(`https://{domain}/` — slug 세그먼트 없음).
P4 에서 실제로 갱신하는 곳은 `DomainSection` 뿐이고, ShareModal·QR·인스타·프로모션 링크의 도메인화는
**§6 으로 미룬다**(`DesignTab.tsx:198` 은 미리보기 플레이스홀더라 영구히 그대로 둔다).

---

## 6. P5 — 선택 항목

### 6-1. 풀 프록시 승격 — 로그인·결제까지 커스텀 도메인

**브랜드가 "결제까지 우리 도메인" 을 실제로 요구하면** 그때 올린다. 여기 적힌 것이 그 작업 목록이고,
**2026-08-20 이전 계획의 P2·P3 본문을 압축해 보존한 것**이다. 착수 전
[README #0](./README.md#0--eximbay-도메인-제한-2026-08-20-조사--남은-질문-1개) **회신이 반드시 선행**한다
(결제창 호출 도메인이 브랜드별로 갈리는 건 이 승격에서만 발생한다).

**(a) 쿠키 host-only 전환** — `cookieOptions()` 는 전역 단일 함수라 5개 쿠키가 `Domain=.klow.kr` 을
공유한다. 그 헤더는 `shop.brandA.com` 응답에 실리면 **브라우저가 통째로 버린다.**
`cookieOptions(opts?: { hostOnly?: boolean })` + `makeCookieHelpers(name, ttl, opts)` 로 확장하고
**klow_web 소유 쿠키만**(`klow_sid`·`klow_return_to`·`klow_google_state`·`klow_order`) 전환한다.

- ⚠️⚠️ **`clear` 를 `set` 과 대칭으로 고칠 것.** `set` 은 레거시 `.klow.kr` 쿠키를 지우는 2줄
  (`cookies.ts:45-46`)이 있어 **자동 마이그레이션을 겸하는데**, `clear` 는 한 줄뿐이라 그대로 두면
  **로그아웃해도 레거시 세션 쿠키가 남는다.**
- ⚠️ **`COOKIE_DOMAIN` 을 전역 제거하면 안 된다** — `klow_brand/src/middleware.ts` 가 `.klow.kr` 공유에
  의존해 프론트 호스트에서 브랜드 세션 쿠키를 읽는다. 어드민도 같다.
- `sameSite:'none'` 은 유지(admin/brand 는 여전히 cross-site).

**(b) `/api-proxy/[...path]` Route Handler** (`runtime:'nodejs'`, `dynamic:'force-dynamic'`)

⚠️⚠️ **`next.config.js` rewrites 로는 안 된다.** `main.ts:43-55` 가 `trust proxy = 1` 을 "Railway 엣지
정확히 1단" 전제로 고정하고 **"앞단에 프록시를 새로 붙이면 홉 수가 2가 된다"고 이미 경고**한다.
rewrites 를 쓰면 `req.ip` 가 Vercel IP 가 되어 **`Order.agreementIp`(PG 분쟁 증거)가 오염**되고,
`trust proxy` 를 2로 올리면 직접 호출 경로에서 **XFF 위조**가 열린다. rewrites 는 헤더도 못 붙인다.

| 항목 | 처리 | 이유 |
|---|---|---|
| 응답 Set-Cookie | `res.headers.getSetCookie()` 배열로 읽어 개별 `append`. **`get()` 금지** | 콤마로 합쳐져 쿠키가 손상된다 |
| 요청 `Cookie` 헤더 | **그대로 전달** | 빠뜨리면 **인증이 통째로 안 된다** |
| `Origin` | **원본 그대로** | 위장하면 프록시가 CSRF 우회로가 된다 |
| `X-Klow-Client-IP` + `X-Klow-Proxy-Secret` | Vercel XFF 의 leftmost, 서버가 secret 일치 시에만 신뢰 | `trust proxy` 는 1 유지 |
| 경로 허용 | **`/v1/` 접두만** | 어드민 표면을 브랜드 도메인에 노출시키지 않는다 |
| body | `await req.arrayBuffer()` | klow_web 은 multipart 0건 |

⚠️⚠️ **`clientIp()` 만 고치면 절반이다** — 전역 `ThrottlerGuard` 가 커스텀 tracker 없이 `req.ip` 를 쓰므로
(`app.module.ts:45`) **커스텀 도메인 전체 트래픽이 IP 하나로 합산**돼 정상 방문자가 429 를 맞는다.
`getTracker` 를 `clientIp()` 와 **같은 규칙**으로.

**(c) 결제 리턴 되돌리기** — `Order.storefrontHost` 추가 + 프록시 헤더로만 기록(바디 금지) +
**리턴 시점 재검증**(active + 주문 브랜드 일치, 스킴은 서버가 `https://` 구성). 폴백은 우아한 폴백이
아니라 **보안장치**이고 발동 시 Sentry 경고 — [flow.md §4-2](./flow.md#4-2-승격-시-결제-왕복-p5).

**(d) 구글 로그인 핸드오프** — 이메일/OTP 는 프록시로 그냥 되지만 구글만 3중으로 깨진다
(상대경로 302 · 콜백이 api 도메인에서 세션을 굽는다 · `FRONTEND_URL` redirect).

```
GoogleButton → https://api.klow.kr/v1/auth/google?returnTo=/&origin=https://shop.brandA.com  (절대 URL)
  → googleStart 가 origin 을 검증(BrandDomain active)해 klow_return_to 에 담는다 (state nonce 구조 유지)
  → googleCallback: 검증된 커스텀 도메인이면 setSessionCookie 대신 1회용 AuthHandoff 토큰(60초) 발급
  → 303 https://shop.brandA.com/auth/handoff?t=<raw> → /api-proxy 경유 POST /v1/auth/session/exchange
```

⚠️ **세션 토큰을 URL 에 직접 싣지 않는다**(Referer 유출·히스토리 잔존). 교환은 **`/api-proxy` 경유**로
해서 Origin 이 정상적으로 실리게 한다 → `origin-exempt.ts` 무변경.

**(e) 승격 시 되돌아오는 것** — P2 핸드오프(`/handoff`)는 **지우지 않는다.** 커스텀 도메인을 아직 안 붙인
브랜드, 그리고 승격 배포 창에서 여전히 유효한 경로다. 승격 후에는 송신부(§4-3)만 끄면 된다.

### 6-2. 링크 도메인화

임베드 딥링크(`embed.service.ts`) · 프로모션 pretty 링크(`promotions.service.ts:61`) · 현장 QR
(`klow_brand/src/lib/onsite.ts:106`) · 인스타 답글 링크(`instagram.service.ts:28`)를 primary 도메인으로.
시딩 링크(`/seed/{token}`)는 **그대로 둔다** — 크리에이터 운영 링크지 브랜드 마케팅 표면이 아니다.

### 6-3. SEO index 개방

`BrandDomain.seoCanonical Boolean @default(false)` 를 켠 브랜드만 index + self-canonical 로 전환하고,
그때 `[brandSlug]/page.tsx` 와 `layout.tsx` **둘만** `headers()` 기반으로 바꾼다(전면 전환 아님 —
`sitemap.ts`·`robots.ts`·`opengraph-image.tsx` 까지 dynamic 이 되면 ISR 이점을 통째로 잃는다).

---

## 7. 배포 순서

| PR | 순서 | 이유 |
|---|---|---|
| P0 | **P1 과 함께** | 코드는 이미 커밋됨(미배포). ⚠️ 예약 슬러그는 **klow_web + klow_server 를 같은 창에** — 미러가 갈리면 서버는 가입을 허용하는데 프론트가 못 연다. klow_web 배포 후 `curl -s https://klow.kr/shop \| grep canonical` 이 apex 인지 확인 |
| P1 | server (마이그레이션 포함) | 프론트가 아직 아무것도 안 부른다 |
| **P2** | **web** | klow.kr 에서 불가시 — `/handoff` 를 가리키는 링크가 아직 없다(§3-3) |
| **P3** | **web 단독** | **서버 변경이 없다.** P1 이 Origin 술어를 이미 열어 뒀다 |
| P4 | brand | **반드시 마지막** — P3 전에 UI 를 열면 브랜드가 도메인을 연결했는데 사이트가 안 뜬다 |

⚠️ **P2 → P3 순서는 필수다.** 송신부(P3)가 먼저 나가면 손님이 klow.kr 의 **없는 `/handoff` 로 튕겨 404**
를 본다. 반대는 무해하다.

ℹ️ 프록시 방식과 달리 **P3 에 서버 배포가 없다** — 결제·쿠키·IP·Throttler 를 건드리지 않기 때문이다.
그만큼 롤백도 klow_web 하나만 되돌리면 끝난다.

---

## 8. 검증

### 8-1. 자동 (klow_server — 테스트 인프라가 있는 유일한 곳)

| 파일 | 잠그는 것 |
|---|---|
| `test/app.e2e-spec.ts` **수정** | cron 목록에 `'brand-domain-verify'` 추가 → **8 → 9** |
| `modules/brand-domains/__tests__/domain-host.spec.ts` **신규** | 정규화(대문자·trailing dot·스킴·포트 제거) · 거부 목록(`klow.kr`/`*.klow.kr`/`*.vercel.app`/IP 리터럴/localhost/253자·63자 초과) · punycode · **`brandA.co.kr` 을 코드가 apex 로 판정하지 않고 Vercel `apexName` 에 위임함** |
| `modules/brand-domains/__tests__/verified-origin.spec.ts` **신규** | `active` 만 통과 / `https://` 만 / **와일드카드·서브도메인 확장 없이 정확 일치** / 삭제 즉시 반영 / 빈 스냅샷에서 false. **여기가 느슨하면 전 브랜드 도메인이 CSRF 우회로가 된다** |
| `modules/brand-domains/__tests__/domain-status.spec.ts` **신규** | **F29** — `verified:true` + `misconfigured:true` 조합이 `active` 가 **되지 않음** / 둘 다 만족할 때만 active / `verification` 있으면 `verifying` |
| `modules/brand-domains/__tests__/resolve-host.spec.ts` **신규** | **F13** — 구독 비-active·탈퇴·미승인 브랜드 미해석 / `Brand.slug` 이 null 이면 미해석 / www redirect 파생과 **오픈 리다이렉트 차단**(짝 primary 검증) / 미등록 host 는 404 가 아니라 200 |
| `modules/brand-domains/__tests__/domain-pairing.spec.ts` **신규** | apex 입력 → `www` redirect 동반 생성 / **서브도메인 입력 → 페어 없음**(F28) / 페어 실패가 primary 를 롤백하지 않음 / primary 삭제 시 페어 동반 삭제 |
| `common/__tests__/origin-exempt.spec.ts` | **무변경으로 통과해야 한다** — 통과 안 하면 설계가 틀어진 것 |

**검증 3층** (CLAUDE.md):
1. `npm run typecheck` — `tsconfig.json` **과** `tsconfig.scripts.json` **둘 다**
2. `npm run test:e2e` — DI 그래프 + **cron 9개**
3. `npm run start` — env 가드 + 라우트 매핑(**298 → 303**, 실측)

⚠️⚠️ **핸드오프 로직은 전부 klow_web 에 있고 klow_web 에는 테스트 인프라가 없다**
(`package.json` scripts = dev/build/start/lint/type-check). 즉 **F1·F4~F9·F15·F16·F21~F26 을 잠글 자동
테스트가 없다** — §8-2 의 수동 항목이 **유일한 방어선**이다. 대충 하면 안 된다.
(`encodeHandoff`/`decodeHandoff` 는 순수 함수라 **P3 에서 가장 먼저 잠갔다** — 프레임워크 없이 tsx 로
도는 `npm run check:handoff`(`klow_web/scripts/check-handoff.ts`). 러너를 들이면 그걸 그대로 옮기면 된다.)

### 8-2. 수동 E2E (스테이징)

⚠️ **핸드오프 불변식은 자동 잠금이 없다**(§8-1) — 이 목록이 유일한 방어선이다. 대충 하면 안 된다.

**A. 도메인 연결·라우팅**

1. 테스트 서브도메인 연결 → DNS 설정 → `pending → verifying → active` 전이
1-1. **F28** — **apex** 를 입력하면 `www` 페어가 자동 생성되고(화면엔 primary 한 줄 + www 부속 줄),
    **서브도메인**을 입력하면 페어가 **생기지 않는지**. primary 삭제 시 페어도 함께 지워지는지
2. `https://<도메인>/` 이 브랜드관 렌더 (rewrite, **주소창 유지**)
3. `shop.brandA.com/{다른브랜드}` → **브랜드 A 브랜드관**(남의 브랜드관이 안 뜬다) · `/{자기slug}` → 308 `/`
4. **F11 폴백** — resolve 를 강제로 실패시킨 채(서버 중단·네트워크 차단)
   `/{다른브랜드}` → **503**(브랜드 B 브랜드관이 뜨면 실패) · **`/` 는 KLOW 홈 폴백** ·
   **`/product/{id}` 는 정상 렌더**(여기까지 막으면 과잉이다)
5. 구독 강제 해지 → 커스텀 도메인이 더 이상 서빙하지 않는지

**B. 커스텀 도메인의 네트워크·세션 (비로그인 전제)**

6. 네트워크 탭 — API 가 **`api.klow.kr` 로 직접** 나가고 `Origin` 이 커스텀 도메인이며,
   **브랜드관 제품이 정상 로드**되고 **트래킹 비콘 2개가 200**(CORS 실패면 화면이 비고, 403 이면 집계만 유실)
7. **요청에 `Cookie` 헤더가 실리지 않는지**(`credentials:'omit'`) — **Chrome·Safari 둘 다**
8. **F8·F26** — klow.kr 에 로그인한 채로 커스텀 도메인 방문 → **양쪽 브라우저에서 똑같이 비로그인**이고
   헤더에 **로그인·내정보 진입점이 아예 없는지**. `/my` 를 주소로 직접 치면 klow.kr 로 가는지
9. **F24** — `shop.brandA.com/seed/{token}` 진입 시 **klow.kr 로 보내지는지**

**C. 핸드오프**

10. 기본 — 담기 → 결제 → `klow.kr/handoff?h=…` → `/checkout` 에 **카트·국가·가격이 그대로**이고
    주소창에 **`?h` 가 남지 않는지**(뒤로가기도 확인). **PDP 바로구매**로도 같은지
11. **F25** — 느린 회선(네트워크 스로틀)에서 → **`/cart` 로 튕기지 않고** 로딩 후 `/checkout`
12. **F6** — `shop.brandA.com/{promotionSlug}` 진입해 세일가 확인 → 핸드오프 → 결제 금액이 **세일가 그대로**
13. **F7** — klow.kr 카트를 US 로 채워둔 뒤 JP 기준 커스텀 도메인에서 핸드오프 →
    **기존 카트 폐기 + 안내**가 뜨고 남은 라인이 전부 JP 가격인지
14. **F23 (로그인)** — 로그인 상태로 핸드오프 → `/checkout` 카트가 그대로이고 **새로고침 후에도**
    유지되는지(= 서버 카트에 올라갔다). 13 의 폐기분이 **되살아나지 않는지**
15. **F23 (프로필 국가)** — 프로필 국가가 **다른** 계정으로 커스텀 도메인에서 다른 국가를 골라 핸드오프
    → 국가·가격이 **핸드오프 국가로 유지**되는지(프로필 국가로 되돌아가면 실패)
16. **F23 (프로모션)** — 로그인 + 할인 링크 → 핸드오프 → 카트가 **세일가**인지
    (정상가면 서버 카트 응답을 그대로 쓴 것)
17. **F21** — `?h` 의 `o` 를 임의 도메인(`example.com`)으로 바꿔 진입 → 성공 화면의 "계속 쇼핑" 이
    **그 도메인을 가리키지 않는지**(폴백 또는 버튼 숨김)

**D. 결제 완주 후**

18. **결제한 상품만** klow.kr 카트에서 빠지고 나머지는 남는지(시딩 결제면 시딩 링크로 복귀하는지)
19. **§3-4** — 성공 화면의 "계속 쇼핑" 이 **커스텀 도메인**을 가리키고, 눌러 돌아갔을 때
    **결제한 상품만** 그 도메인 카트에서 빠지며 주소창에 `?purchased=` 가 남지 않는지
20. **F5** — 브랜드 `/stats` 에서 **방문·담기·결제 3단계가 모두** 오르는지.
    **결제만 0 이면 `visitorId` 이관 실패다**
21. **F1** — 같은 시나리오에서 `총 N번 담음` 이 **1 만** 오르는지

**E. 회귀**

22. **klow.kr 회귀 없음** — 로그인·담기·결제 완주 + `www.klow.kr` 정상

### 8-3. 문서

- `docs/server/modules/brand-domains.md` 신설 + `docs/server/README.md` 색인 (컨트롤러 변경 시 함께 갱신 — CLAUDE.md 규칙)
- `docs/deploy-custom-domain-runbook.md` (`deploy-free-text-product-tags-runbook.md` 형식)
- 워크스페이스 `CLAUDE.md` Key Facts 항목 추가 — **핸드오프 경계**(브라우징·담기 = 커스텀 도메인 /
  로그인·결제 = klow.kr) · 넘기는 상태 4개 · 배포 순서(P2 → P3)
- **릴리즈 노트/CS 가이드**: "커스텀 도메인은 **둘러보기·담기 전용**이고 **로그인·결제는 klow.kr 에서**
  진행됩니다. 두 주소의 장바구니·로그인은 별개입니다."

---

## 9. 불변식 체크리스트 (착수 전 필독)

아래는 전부 **틀려도 컴파일과 테스트가 통과**한다. 각 PR 착수 전 해당 항목을 확인한다.
⚠️ F1·F4~F9·F15·F16·F21~F26 은 **klow_web 이라 자동 테스트가 없다**(§8-1).

| # | 불변식 | 어기면 | PR |
|---|---|---|---|
| **F1** | 핸드오프 복원에 **`addToCart` 를 쓰지 않는다**(`replaceCart` 로 직접 쓴다) | 담기 비콘이 재발사돼 `cartAdds` 2배 — 순담기자는 flip-once 라 **전환율만 조용히 망가진다** | P2 |
| **F2** | apex 판정은 **Vercel `apexName`** 에 위임. 직접 레이블 수를 세지 않는다 | `brandA.co.kr` 에 **잘못된 DNS 레코드를 안내** — 첫 한국 고객부터 | P1 |
| **F3** | DNS 레코드 값은 **Vercel 응답을 저장해 그대로 표시**. 하드코딩 금지 | Vercel 이 값을 바꾼 날 신규 연결이 전부 실패 | P1 |
| **F4** | 핸드오프 payload 에 **가격을 싣지 않는다**(제품 id + 수량만) | 옛 국가·옛 프로모션 가격이 굳어 표시가 ≠ 청구가. 게다가 **서명이 필요해진다** | P2 |
| **F5** | **`visitorId` 이관** — klow.kr 에 없으면 심고, **있으면 덮지 말고 그 주문에만** 사용 | **그 브랜드의 결제 단계 퍼널이 영구 0**(서버가 조용히 버린다) | P2·P3 |
| **F6** | **`promotionCode` 이관** | **세일가가 정상가로 조용히 되돌아간다** | P2·P3 |
| **F7** | **국가를 먼저** 세팅하고 카트를 재조회. 기존 klow.kr 국가와 다르면 **기존 카트 폐기** | 두 국가 가격이 섞인 카트 → 표시가 ≠ 청구가 | P2 |
| **F8** | 커스텀 도메인 클라는 **`credentials:'omit'`** | Chrome 은 로그인·Safari 는 비로그인으로 **브라우저마다 화면이 갈리고**, 서버 카트가 어긋난다 | P3 |
| **F9** | 송신은 **`location.assign`(top-level)** + **`peekVisitorId()`** | 새 탭이면 인앱 브라우저에서 컨텍스트 유실 / `getVisitorId()` 면 **원장 없는 토큰**만 생성 | P3 |
| **F10** | **`handoff` 를 예약 슬러그**에 넣는다 | 그 슬러그를 가진 브랜드가 브랜드관을 잃는다 | P0 |
| **F11** | 미들웨어 `/{seg}` 규칙을 **pass-through 로 바꾸지 않는다.** ⚠️ **resolve 실패 폴백도 마찬가지** — fail-open 은 **`/` 에만**, 그 외는 503 | 브랜드 A 도메인에서 **브랜드 B 브랜드관**이 렌더된다(폴백 경로로도 뚫린다) | P3 |
| **F12** | `[influencer]/page.tsx` 의 `source` 를 **code 유무로 분기** | 미매칭 경로·봇이 전부 **할인 링크 유입으로 집계** | P0 |
| **F13** | `resolveHost` 가 **`PUBLIC_BRAND_WHERE` + 구독 게이트**를 함께 태운다 | 구독이 끊긴 브랜드의 도메인만 계속 살아남는다 | P1 |
| **F14** | `isVerifiedOrigin` 은 **정확 일치**. 와일드카드·서브도메인 확장 금지 | 전 브랜드 도메인이 **CSRF 우회로** | P1 |
| **F15** | 복원 직후 **`router.replace` 로 `?h` 제거** | 뒤로가기가 복원을 재실행 → F7 규칙이 다시 돌아 **손님 카트를 두 번 날린다** | P2 |
| **F16** | **커스텀 도메인에서 열린 `/handoff` 는 복원하지 않는다**(`/cart` 로) | 손님이 브랜드 도메인에 남은 채 결제까지 진행 → 이 설계의 전제가 깨진다 | P2 |
| **F17** | `test/app.e2e-spec.ts` cron 기대값 **8 → 9** | `@Cron` 미등록이 **완전 무음**(로그도 없다) | P1 |
| **F18** | 배포는 **P2(수신) → P3(송신)** | 손님이 klow.kr 의 없는 `/handoff` 에서 **404** | — |
| **F21** | 복귀 host(`o`)는 **`/v1/storefront/resolve` 로 재검증**한 뒤에만 저장하고, **스킴은 클라가 `https://` 로 조립** | 결제 성공 화면의 "계속 쇼핑" 이 **임의 사이트로 보내는 링크**가 된다(오픈 리다이렉트) | P2 |
| **F22** | `setBrandReturn(…?purchased=)` 갱신을 `removeProducts` 와 **같은 블록**에 둔다 | 한쪽만 도는 조합이 생겨 **브랜드 도메인 카트가 정리되지 않는다** | P2 |
| **F23** | 복원은 **`session.ready` 이후**. 로그인 상태면 **프로필 국가 업로드 → `api.cart.merge(lines, removedIds)` → `repriceCartForCountry`** 순서를 지킨다 | 순서가 어긋나면: sync 가 복원 카트를 덮거나 / **프로필 국가가 핸드오프 국가를 되돌리거나**(F7 무력화) / **서버 카트 가격에 프로모션이 없어 세일가가 정상가로 보인다**(F6 무력화) | P2 |
| **F25** | 복원이 **끝난 뒤에만** `/checkout` 으로 보낸다(그동안 로딩) | `checkout/page.tsx:295` 의 빈 카트 가드가 손님을 **`/cart` 로 튕긴다** | P2 |
| **F24** | **쿠키가 필요한 경로는 전부 klow.kr** — 특히 **`/seed/*`**(예약 슬러그라 pass-through 된다) | 시딩 claim 이 `klow_order` 게스트 쿠키를 못 받아 **예약 재사용·결제가 조용히 깨진다** | P3 |
| **F26** | 커스텀 도메인에 **로그인·내정보 진입점을 그리지 않는다**(§4-2) | klow.kr 로 편도 이탈 → 손님에게는 **"장바구니가 사라졌다"** 로 보인다 | P3 |
| **F27** | `/v1/storefront/resolve` 에 **`@SkipThrottle()`**(그 라우트에만) | 미들웨어 호출이 Vercel IP 하나로 뭉쳐 60/분 천장에 닿고, 429 → fail-open → **전 브랜드 도메인이 동시에** KLOW 홈/503 | P1 |
| **F28** | apex 입력에만 `www` 페어를 만든다. **서브도메인 입력 → apex 자동 등록 금지** | 브랜드의 **기존 홈페이지를 뺏는다** | P1 |
| **F29** | `active` 전이는 **`verified && !misconfigured`** — 두 API 를 모두 본다 | Vercel `verified` 는 소유권 축이라 **DNS 를 한 줄도 안 건 도메인이 즉시 "연결 완료"** 로 표시된다(2026-08-21 실측) | P1 |
| **F19** | `origin-exempt.spec.ts` 가 **무변경으로 통과** | 통과하지 않으면 설계가 틀어진 것 | P1 |
| **F20** | Vercel 추가 후 DB insert 실패 시 **보상 제거** + 해지 도메인 **정리 경로** | Vercel 쿼터 누수 · orphan 누적 | P1 |

---

## 10. 부록 — 코드로 검증한 사실 (2026-08-19, #0 은 2026-08-20)

이 계획의 전제들이다. **재조사하지 말고, 대신 구현 시점에 어긋나면 계획을 의심할 것.**

| # | 사실 | 왜 중요한가 | 근거 |
|---|---|---|---|
| V1 | **`@/lib/api` 의 소비자는 전부 `'use client'` 컴포넌트다** (importer 중 `'use client'` 없는 파일 0건) | `credentials` 를 브라우저에서만 분기해도 **SSR 이 깨지지 않는다**. 서버 사이드 fetch 는 `lib/brand-server.ts`·`app/sitemap.ts` 가 각자 절대 URL 로 따로 한다 | §4-2 |
| V2 | **`repriceCartForCountry`(`lib/cart-reprice.ts`)가 이미 `productId` + 국가 + 프로모션으로 카트 라인을 재구성한다** | 핸드오프 복원은 **새 로직이 아니라** 그 헬퍼(`toCartItem` · `qk.productDetail` 캐시)의 재사용이다. 사본을 만들면 같은 자원을 두 경로가 각자 읽는다 | §3-3 |
| V3 | **`useCartStore.addToCart` 가 `trackStorefrontCartAdd` 비콘을 쏜다** (`useCartStore.ts:7`) | 복원에 쓰면 **담기가 두 번 집계**된다 | F1 |
| V4 | **`useCheckoutGate` 가 결제 진입마다 로그인/비회원을 다시 묻는다** (`useAuthGate.ts:104`, `?guest=1`) | 도메인이 바뀌는 지점과 로그인 화면이 **원래 겹쳐 있다** → 이음매를 놓기 가장 덜 어색한 자리 | §4-0 |
| V5 | **`OnboardingModal.select()` 는 가격 기준국이 실제로 바뀔 때만 카트를 비운다** | 핸드오프의 국가 규칙(F7)은 **그 기존 규칙의 재사용**이지 새 정책이 아니다 | §3-3 |
| V6 | **`checkout/success` 는 API 를 부르지 않는다** (주문번호·이메일 쿼리로만 렌더) | 결제 완료 화면에 세션이 필요 없다 | `flow.md` §4 |
| V7 | **주문 확인 이메일의 배송조회는 쿠키가 아니라 URL 서명 토큰** (`/track/{id}?t=signGuestOrderToken(...)`) | 이메일 링크가 klow.kr 이어도 정상 동작 | `order-confirmation-email.ts:86` |
| V8 | **Eximbay 는 결제창 호출 도메인을 런타임에 검사하지 않는다** — 샌드박스 3지점(CORS preflight / `POST /v1/payments` / 게이트웨이 form POST) 전부 Origin·Referer 무관 (2026-08-20 실측). 남은 건 **심사·계약 축** | 핸드오프에서는 결제창 호출 도메인이 **오늘과 동일한 klow.kr** 이라 **이 축 자체가 P3 전제에서 빠진다** | `README.md` #0 |
| V9 | **klow_web 에 `src/middleware.ts` 가 없다** | 신규 생성이라 기존 미들웨어와의 충돌을 걱정할 필요가 없다 | §4-1 |
| V10 | **klow_web·klow_brand 에 테스트 인프라가 없다** (`package.json` scripts = dev/build/start/lint/type-check) | **핸드오프 불변식을 잠글 자동 테스트가 없다** → 수동 E2E 가 유일한 방어선 | §8-1 |
| V11 | **`RESERVED_BRAND_SLUGS` 에 실제 라우트인 `customer-center`·`track`·`seed` 가 빠져 있다** | 이미 존재하는 잠재 버그이고, 미들웨어가 이 목록을 재사용하므로 P0 에서 먼저 고친다 | §1-1 |
| V12 | **cron 실제 개수는 8개** (워크스페이스 `CLAUDE.md` 의 "6개"는 낡았다) | 새 cron 추가 시 기대값은 **8 → 9** | F17 |
| V13 | **klow.kr ↔ api.klow.kr 은 eTLD+1 이 같아 브라우저에게 same-site** | 지금 세션이 정상인 이유이자, **klow.kr 흐름을 한 줄도 안 건드려도 되는 근거** | `flow.md` §1-1 |
| V14 | **klow_web 클라 `StorefrontVisitSource` 는 `direct \| promotion` 둘뿐** (서버 enum 에는 `onsite` 도 있지만 클라가 보내지 않는다) | 커스텀 도메인 방문도 이 둘로만 기록한다 — **값을 늘리지 않는 근거** | §2-9 |
| V15 | **`[influencer]/page.tsx` 는 프로모션 code 가 null 이어도 `notFound()` 하지 않는다** | 미들웨어 `/{seg}` 규칙의 결과가 404 가 아니라 **자기 브랜드관**이다. 그래서 P0-5 의 `source` 분기가 필요하다 | F11, F12 |

> **승격(§6-1) 전제로만 유효한 사실** — 지금은 쓰지 않는다.
> **VP1** klow_web 에 multipart/파일 업로드가 **0건**(`api.upload` 는 컨시어지 제거 때 삭제) → 프록시가
> `arrayBuffer()` 로 바디를 통째 읽어도 된다.
> **VP2** 전역 `ThrottlerGuard` 에 커스텀 tracker 가 **없다**(기본 `req.ip`, `app.module.ts:45`) →
> 프록시를 붙이면 **커스텀 도메인 전체가 한 rate-limit 버킷**이 된다.
> **VP3** `clientIp()` 소비처는 **3곳뿐** — `public-orders.controller.ts:70,88`,
> `public-seeding.controller.ts:102`.
