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
| **P0** | 정지 작업(예약 슬러그·하드코딩·집계 버그) | web, server, brand | 없음 (독립 배포 가능) |
| **P1** | 서버 기반: `BrandDomain` 모델 + Vercel 연동 + resolve + Origin 술어 | server | 없음 (아직 서빙 안 함) |
| **P2** | 쿠키 host-only 전환 | server | 없음 |
| **P3** | klow_web 미들웨어 + API 프록시 + 결제 리턴 | web, server | **커스텀 도메인이 실제로 동작** |
| **P4** | klow_brand 설정 UI | brand | 브랜드가 직접 등록 가능 |
| **P5** (선택) | 구글 핸드오프 · 링크 도메인화 · SEO index 개방 | 전부 | |

**순서: P0 → P1 → P2 → P3(web → server) → P4.**
⚠️ **P4 를 P3 보다 먼저 내면 브랜드가 도메인을 연결했는데 사이트가 안 뜬다.**

**롤백 지점**: P4 를 되돌리면 신규 등록만 막히고 기존 도메인은 계속 동작한다. P3 를 되돌리면 커스텀
도메인이 전부 죽지만 klow.kr 은 무사하다.

---

## 1. P0 — 정지 작업

독립 배포 가능하고 되돌릴 일이 없다. 먼저 내보낸다.

1. **예약 슬러그 누락 보강** — `klow_web/src/lib/reserved-slugs.ts` 와
   `klow_server/src/common/reserved-slugs.ts`(**미러 2파일**)에 실제 최상위 라우트인
   `customer-center`·`track`·`seed` 와 신설 예정인 `api-proxy` 를 추가.
   P3 미들웨어가 이 목록으로 "브랜드 슬러그 경로인가"를 판정하므로 **선행 필수**다.
   ⚠️ 추가 전 `SELECT slug FROM "Brand" WHERE slug IN (...)` 로 **기존 보유 브랜드가 없는지 확인**.
   있으면 예약어에 넣지 말고 미들웨어 전용 상수로 분리한다(살아있는 브랜드관을 죽이면 안 된다).

2. `klow_web/src/lib/seo.ts:3` 의 기본값 `https://www.klow.kr` 을 실제 링크 생성값(`klow.kr`)과 통일.
   지금 og:url/canonical 과 브랜드가 공유하는 링크의 호스트가 어긋나 있다.

3. `klow_brand/src/components/auth/SlugCheck.tsx:48` 의 `klow.kr/${slug}` 하드코딩 →
   `storefrontLabel(slug)`. 부수효과로 로컬/스테이징 라벨이 정확해진다.

4. 워크스페이스 `CLAUDE.md` 의 "cron 6개" 서술을 실제값 **8개**로 정정
   (`klow_server/test/app.e2e-spec.ts:44-58` 이 정본).

5. **`klow_web/src/app/[brandSlug]/[influencer]/page.tsx` — code 가 null 이면 `source` 를 `'direct'` 로.**
   지금은 프로모션이 없거나 Off 여도 `source="promotion"` 을 고정으로 넘겨서
   `klow.kr/brandA/아무거나`(봇 포함)가 전부 **할인 링크 유입으로 집계**된다. 이미 존재하는 버그이고,
   P3 의 `/{seg}` rewrite 가 이걸 증폭시킨다(커스텀 도메인의 **모든** 미매칭 경로가 여기로 온다).
   ⚠️ **`notFound()` 로 바꾸지 말 것** — "Off 면 정상가로 렌더"는 의도된 graceful degradation 이다.

---

## 2. P1 — 서버 기반

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

`Brand` 에 `domains BrandDomain[]` 역참조 1줄 추가. 브랜드당 상한은 **앱 레벨 2개**(apex + www).

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

⚠️⚠️ **apex 판정을 우리가 하지 않는다.** `brandA.co.kr` 은 레이블 3개지만 apex 다 — 이중 TLD 는 Public
Suffix List 문제이고, 한국 브랜드가 주 대상이라 자체 판정하면 **첫 고객부터 잘못된 레코드를 안내**한다.
도메인 추가 응답의 **`apexName` 을 정본**으로 쓴다(`apexName === name` 이면 apex → A 레코드).
`domain-host.ts` 는 **정규화·거부만** 담당한다.

⚠️ **DNS 값을 하드코딩하지 않는다.** apex `A 76.76.21.21` / 서브도메인 `CNAME cname.vercel-dns.com` 은
현재값일 뿐이고 Vercel 이 리전별 타겟으로 옮겨가는 중이다. `getDomainConfig` 응답의 권장값을
`recordValue` 에 저장해 화면에 **그대로** 띄운다. 하드코딩하면 Vercel 이 값을 바꾼 날 신규 연결이 전부
실패한다. (폴백 상수는 응답에 권장값이 없을 때만)

**에러 매핑** (Vercel 공식 코드):

| Vercel | 우리 처리 | 브랜드에게 |
|---|---|---|
| `domain_already_in_use` | **row 를 만들지 않고 400** | "다른 Vercel 계정/프로젝트가 이미 사용 중입니다. 소유권 TXT 검증이 필요합니다" |
| `invalid_domain` | 400 | 형식 오류 |
| `forbidden` | 502 + Sentry | "일시적 오류" (서버 설정 문제) |
| `rate_limit_exceeded` | 지수 백오프 재시도 | — |

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

### 2-5. Origin 술어 (CSRF 가드 + CORS)

프록시를 타도 **원본 `Origin` 이 그대로 전달**되므로 서버는 `Origin: https://shop.brandA.com` 을 본다
→ 지금 코드면 403.

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
- ⚠️ **프록시가 Origin 을 위장하게 만들지 않는다.** 그러면 프록시 경로가 CSRF 가드의 **우회로**가 되고
  감사도 불가능해진다. 서버가 검증된 origin 을 허용하는 쪽이 정답이다
- `common/origin-exempt.ts` 는 **손대지 않는다** — 새 예외 경로가 없다.
  `common/__tests__/origin-exempt.spec.ts` 가 **그대로 통과해야 하고, 통과하지 않으면 설계가 틀어진 것**이다
- ⚠️ `/embed/*` 의 수동 CORS(`res.setHeader`, `res.append` 금지, 영구 simple request)를 깨뜨리지 않는지 확인

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
`take: 20`(rate limit 보호). `getDomainConfig` → `verify` → `active` 전이 + **origin 스냅샷 즉시 갱신**.
`createdAt` 7일 초과 pending 은 `error` 로 내려 무한 폴링을 막는다.

브랜드의 "지금 확인" 버튼은 같은 로직 1건: `POST /v1/brand/domains/:id/check` (Throttle 6/분).

⚠️ 새 cron 이라 **`test/app.e2e-spec.ts` 의 cron 기대 목록이 8개 → 9개**. 안 늘리면 `@Cron` 미등록이
**완전 무음**이다(typecheck 통과·로그 없음).

### 2-8. env

```
VERCEL_TOKEN=          # 프로젝트 도메인 관리 권한
VERCEL_PROJECT_ID=     # klow_web 프로젝트 (prj_xxx)
VERCEL_TEAM_ID=        # 팀 소속이면 필수 (team_xxx)
KLOW_PROXY_SECRET=     # P3 프록시 ↔ 서버 공유 비밀
```

⚠️ **부팅 fail-closed 가드를 붙이지 않는다.** 기존 fail-closed 3종(Eximbay·`GUEST_ORDER_SECRET`·OTP)은
"조용히 깨지고 돈이 사라지는" 경로다. 도메인은 미설정 시 브랜드가 즉시 에러를 보므로 부팅을 막을 성질이
아니다. 대신 서비스가 `503 도메인 기능이 아직 활성화되지 않았습니다` 로 명시 거부.

### 2-9. (권장) 유입 경로 enum 값 추가

커스텀 도메인 루트 방문이 전부 `direct` 로 뭉쳐 브랜드가 "내 도메인 유입"을 구분하지 못한다.
`StorefrontVisitSource` 에 `custom_domain` 을 **P1 에서** 추가하는 것을 권한다 — 나중에 넣으면 그
기간 데이터는 **영영 복구 불가**(전부 direct 로 섞임)다.

⚠️ Postgres 는 `ALTER TYPE … ADD VALUE` 로 추가한 enum 값을 **같은 트랜잭션에서 쓰지 못하고** Prisma 는
마이그레이션을 트랜잭션으로 감싼다(국내배송 `DOMESTIC` 선례) → **마이그레이션과 코드 배포를 분리**한다.

---

## 3. P2 — 쿠키 host-only 전환

`cookieOptions()` 는 전역 단일 함수라 5개 쿠키가 모두 `Domain=.klow.kr` 을 공유한다. 그 헤더가
`shop.brandA.com` 응답에 실리면 브라우저가 쿠키를 **통째로 버린다**(도메인 불일치).

`cookieOptions(opts?: { hostOnly?: boolean })` + `makeCookieHelpers(name, ttl, opts)` 로 확장하고
**klow_web 소유 쿠키만** 전환한다:

| 쿠키 | 파일 | 변경 |
|---|---|---|
| `klow_sid`, `klow_return_to`, `klow_google_state` | `modules/web-auth/session.ts` | **host-only** |
| `klow_order` | `modules/orders/guest-order-token.ts` | **host-only** |
| `klow_admin_sid` | `modules/admin-auth/admin-session.ts` | 무변경 |
| `klow_brand_sid` 외 | `modules/brand-auth/brand-session.ts` | 무변경 |
| `klow_ig_oauth_*` | `modules/instagram/instagram-oauth-cookies.ts` | 무변경 |

⚠️ **`COOKIE_DOMAIN` 을 전역 제거하면 안 된다** — `klow_brand/src/middleware.ts` 가 `Domain=.klow.kr`
공유에 의존해 **프론트 호스트에서 브랜드 세션 쿠키를 읽는다**(그 파일 주석이 명시). 어드민도 같다.

**klow.kr 사용자에게는 영향이 없다.** klow_web 쿠키는 어느 프론트 호스트에서 접속하든 `api.klow.kr` 이
발급하고 직접 호출로만 오간다 — host-only 여도 여전히 `api.klow.kr` 쿠키이고 www/apex 가 갈리지 않는다.

⚠️⚠️ **`clear` 를 반드시 `set` 과 대칭으로 고친다.** `set` 은 발급 전 레거시 `.klow.kr` 쿠키를 지우는
2줄(`cookies.ts:45-46`)이 있어 전환의 **자동 마이그레이션을 겸한다.** 그런데 `clear` 는
`res.clearCookie(name, cookieOptions())` **하나뿐**이라, 그대로 두면 **로그아웃해도 레거시 `.klow.kr`
세션 쿠키가 남는다.** `clear` 도 3줄(도메인 없음 / `.klow.kr` / 현재 옵션)로 만들 것.

`sameSite:'none'` 은 **유지**한다(admin/brand 는 여전히 cross-site).
**Safari ITP 는 host-only + same-origin 프록시만으로 해소된다** — 1st-party 쿠키가 되어 3rd-party
차단 대상이 아니고, `httpOnly` 라 script-writable 7일 캡에도 걸리지 않는다.

---

## 4. P3 — 라우팅 전환 (핵심)

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
**fetch 실패 시 stale 값 우선, 없으면 pass-through(fail-open)** — fail-closed 로 하면 API 가 3초 흔들릴
때 전 브랜드 도메인이 동시에 죽는다. fail-open 의 최악은 "브랜드 도메인 루트에 KLOW 홈이 잠깐 뜬다"이고
되돌릴 수 있다.

```ts
export const config = {
  matcher: [
    '/((?!_next/static|_next/image|api-proxy|api/|favicon\\.ico|icon.*\\.png|apple-icon\\.png).*)',
  ],
};
```

⚠️ **`api-proxy` 제외가 필수**다. 프록시 경로가 미들웨어를 타면 rewrite 규칙에 걸려 API 호출이
브랜드관으로 튄다.
ℹ️ `_next/data` 는 제외하지 **않는다** — App Router 의 RSC 요청은 같은 경로 + `?_rsc=` 로 오므로 rewrite
가 일관되게 걸려야 한다.

### 4-2. API 프록시 — Route Handler

`klow_web/src/app/api-proxy/[...path]/route.ts`
(`export const runtime = 'nodejs'`, `export const dynamic = 'force-dynamic'`, 모든 메서드 동일 핸들러)

⚠️⚠️ **`next.config.js` rewrites 를 쓸 수 없는 결정적 이유**
`main.ts:43-55` 는 `trust proxy = 1` 을 "Railway 엣지 정확히 1단" 전제로 고정하고,
**"앞단에 프록시 등을 새로 붙이면 홉 수가 2가 되므로 이 값을 함께 올릴 것"이라고 이미 경고한다.**
- rewrites 를 쓰면 `req.ip` 가 Vercel IP 가 되어 **`Order.agreementIp`(PG 분쟁 시 동의 증거)가 오염**된다
- `trust proxy` 를 2로 올려 고치려 하면 **직접 호출 경로에서 XFF 위조**가 열려 그 주석이 지키려던
  불변식이 깨진다. 두 경로의 홉 수가 다르므로 숫자 하나로는 못 맞춘다
- **rewrites 는 요청 헤더를 추가할 수 없어** 실 IP 를 따로 전달할 방법도 없다

**핵심 규칙 — 하나라도 틀리면 조용히 깨진다:**

| 항목 | 처리 | 이유 |
|---|---|---|
| **응답 Set-Cookie** | `res.headers.getSetCookie()`(배열)로 읽어 하나씩 `append`. **`get('set-cookie')` 금지** | `get()` 은 여러 Set-Cookie 를 콤마로 합쳐 쿠키를 손상시킨다 |
| **Domain 속성** | 남아 있으면 제거(방어적 2중화) | P2 가 정본이지만, 배포 순서가 어긋난 창에서 쿠키가 통째로 버려지는 것을 막는다 |
| **요청 `Cookie` 헤더** | **반드시 그대로 전달** | 빠뜨리면 **인증이 통째로 안 된다.** `Content-Type`·`Accept-Language` 도 함께. `Host`·`Content-Length`·`Connection` 등 hop-by-hop 은 제외 |
| **Origin** | **원본 그대로 전달** | 위장하면 프록시가 CSRF 우회로가 된다 (§2-5) |
| **`X-Klow-Client-IP`** + **`X-Klow-Proxy-Secret`** | Vercel 이 준 XFF 의 leftmost | 서버가 secret 일치 시에만 신뢰. `trust proxy` 는 1 유지 |
| **`X-Klow-Storefront-Host`** | 요청 Host | 결제 리턴(§4-3)의 신뢰 입력 |
| **body** | `await req.arrayBuffer()` | klow_web 은 **multipart 0건 · JSON 만**(`api.upload` 는 컨시어지 제거 때 삭제됨) |
| **경로 허용** | **`/v1/` 접두만.** `/admin/`·`/webhooks/`·`/embed/` 는 400 | 프록시가 어드민 표면을 브랜드 도메인에 노출시키면 안 된다 |
| redirect / cache | `redirect:'manual'` + Location 그대로 전달 / `cache:'no-store'` | |

**서버측 짝 — IP 신뢰**

`common/client-ip.ts` 의 `clientIp(req)` 확장: `X-Klow-Proxy-Secret` 일치 시 `X-Klow-Client-IP` 우선.
env 만 읽으므로 `common/` 규칙 2 유지. 소비처는 `public-orders.controller.ts:70,88` ·
`public-seeding.controller.ts:102` **셋뿐**이고(확인 완료), 어드민·웹훅 경로는 프록시를 안 타므로 무영향.

⚠️⚠️ **`clientIp()` 만 고치면 절반이다 — 전역 `ThrottlerGuard` 가 자기 tracker 를 따로 쓴다.**
`app.module.ts:45` 는 `ThrottlerModule.forRoot({ throttlers: [{ ttl: 60_000, limit: 60 }] })` 에 커스텀
tracker 가 없어 **기본값 `req.ip`** 를 쓴다. 프록시 fetch 에는 XFF 가 없어 Railway 가 **Vercel 함수 IP**
를 넣으므로, 그대로 두면 **커스텀 도메인 전체 트래픽이 IP 하나로 합산**된다 → 브랜드 몇 곳만 붙어도
정상 방문자가 429 를 맞고, 그건 조용한 장애다(트래킹 120/분·담기 60/분도 같이 죽는다).
→ `ThrottlerGuard` 를 상속한 `KlowThrottlerGuard` 의 `getTracker(req)` 가 **`clientIp()` 와 같은 규칙**을
쓰게 하고 `APP_GUARD` 등록을 그 클래스로 바꾼다. **규칙은 한 함수에 둔다.**

**klow_web 클라이언트 전환**

`src/lib/host.ts` 신설(정본 호스트 Set + `isCustomDomain()`), `src/lib/api.ts:77`:

```ts
const BASE =
  typeof window !== 'undefined' && isCustomDomain()
    ? '/api-proxy'
    : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4000');
```

- **klow.kr 은 경로가 그대로**라 회귀 위험 0, Vercel 함수 비용 0
- SSR 경로(`lib/brand-server.ts`, `app/sitemap.ts`)는 **절대 URL 유지** — 프록시를 타면 자기 자신을 호출한다
- ⚠️ **`GoogleButton.tsx:11` 은 BASE 를 쓰면 안 된다.** `${BASE}/v1/auth/google` 로 **top-level 이동**
  하는데, 서버가 돌려주는 **상대경로 302**(`public-auth.controller.ts:150`)가
  `shop.brandA.com/v1/auth/google/authorize` 로 해석돼 404 가 난다. `googleStartUrl` 은 항상 절대 API
  base 를 쓰도록 분리한다

### 4-3. 결제 리턴

`return_url` 은 `EXIMBAY_RETURN_BASE_SERVER`(api 도메인)이라 **PG 쪽 도메인 등록 작업은 없다**
(단 [README #0](./README.md#0--eximbay-문의-잠재-블로커) 확인 필요). 고칠 것은 확정 후 303 대상뿐이다.

- `Order.storefrontHost String? @db.VarChar(253)` 추가 — **nullable ADD COLUMN → 롤링 안전 · 백필 없음**
- 기록은 `POST /v1/orders` 에서 **프록시가 실은 `X-Klow-Storefront-Host` 헤더**로만 한다.
  ⚠️ **바디 필드로 받지 않는다** — 클라이언트가 임의 값을 넣으면 오픈 리다이렉트가 된다
- **리턴 시 2중 검증** ([flow.md §4](./flow.md#4-결제-왕복)): ① 그 host 가 **지금 이 순간**
  `BrandDomain(active)` 에 있고 ② 그 브랜드가 이 주문의 아이템 브랜드 중 하나일 때만 사용, 아니면
  `FRONTEND_URL` 폴백 **+ Sentry 경고**. 스킴은 항상 서버가 `https://` 로 구성하고 host 는 DB 값만 쓴다
- 순수 함수 `buildReturnRedirectUrl(qs, origin)` 로 분리해 스펙이 잠그고, 서비스
  `resolveReturnRedirect(qs)` 가 조회·검증 후 호출한다.
  `handleReturn` 은 **무변경**(절대 throw 하지 않는 성질 유지 — 웹훅·재확인 크론 경로를 건드리지 않는다)

### 4-4. 구글 로그인 — P3 에서는 숨김

이메일+비밀번호/OTP 는 프록시로 완전히 동작한다. 구글만 3중으로 깨진다(§4-2 상대경로 302 / 콜백이 api
도메인에서 세션을 굽는다 / `public-auth.controller.ts:183` 이 `FRONTEND_URL` 로 redirect).

**P3 에서는 `GoogleButton` 이 `isCustomDomain()` 이면 `null` 을 반환**한다(파일 1개·3줄,
`LoginForm`/`SignupForm` 무변경 — 버튼이 스스로 사라진다). 정식 핸드오프는 §6.

---

## 5. P4 — klow_brand 설정 UI

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
- **화면 상태** — 미연결(입력) / `pending` / `verifying`(SSL 발급 중, 10초 폴링) / `active`(링크 + 연결 해제) / `error`(사유 + 재시도)
  ⚠️ **`pending` 안에 서로 다른 두 안내가 있다** — ① A/CNAME 접속 레코드(항상) ② **소유권 TXT 챌린지**
  (`verification` 이 있을 때만). `verification` 유무로 섹션을 나눠 렌더할 것. 값은 **서버가 준 타입·값
  그대로** 표시하고 클라에서 판정하지 않는다
- 구독 `active` 가 아니면 잠금 안내. `settings/page.tsx` 에 이미 있는 `qk.subscription` 값을 prop 으로 내린다

**`lib/storefront.ts`** — 링크 문자열의 단일 출처(소비처 13곳). **선택 인자를 뒤에 추가**해 기존 호출부가
그대로 컴파일되게 한다:

```ts
storefrontUrl(slug?, customDomain?)
storefrontLabel(slug?, customDomain?)
productLinkUrl(slug, productId, customDomain?)
// embedScriptUrl() 은 API 호스트라 무변경
```

⚠️ 값 규칙은 P3 미들웨어 rewrite 와 **정확히 대칭**이어야 한다(`https://{domain}/` — slug 세그먼트 없음).
P4 에서 실제로 갱신하는 곳은 `DomainSection` 뿐이고, ShareModal·QR·인스타·프로모션 링크의 도메인화는
**§6 으로 미룬다**(`DesignTab.tsx:198` 은 미리보기 플레이스홀더라 영구히 그대로 둔다).

---

## 6. P5 — 선택 항목

### 6-1. 구글 로그인 핸드오프

```
1. GoogleButton → https://api.klow.kr/v1/auth/google?returnTo=/&origin=https://shop.brandA.com
                  (절대 URL, top-level 이동 — 프록시 안 탐)
2. googleStart 가 origin 을 검증(BrandDomain active)해 klow_return_to 쿠키에 함께 담는다
   ⚠️ state nonce 구조는 유지 — 세션 발급 전 state 대조가 로그인 CSRF 방어선이다
3. googleCallback:
   - origin 없음        → 현재 동작 그대로 (회귀 0)
   - 검증된 커스텀 도메인 → setSessionCookie 를 호출하지 않고 AuthHandoff 토큰 발급 후
                          303 → https://shop.brandA.com/auth/handoff?t=<raw>&returnTo=<path>
4. klow_web /auth/handoff → /api-proxy 경유로 POST /v1/auth/session/exchange
   → 서버가 그 도메인의 host-only 쿠키 발급 → 303 returnTo
```

- 토큰은 **1회용 · 60초 TTL · 소비 즉시 삭제**. 전용 테이블 1개(`Session` 에 컬럼을 붙이는 것보다 깨끗 — 수명이 완전히 다르다)
- ⚠️ **세션 토큰을 URL 에 직접 싣지 않는다** — Referer 유출·액세스 로그·브라우저 히스토리에 영구 세션이 남는다
- ⚠️ 교환 호출을 **`/api-proxy` 경유**로 해서 Origin 을 정상적으로 싣는다 → `origin-exempt.ts` 무변경

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
| P0 | 아무 때나 | 독립 |
| P1 | server (마이그레이션 포함) | 프론트가 아직 아무것도 안 부른다 |
| P2 | server | klow.kr 사용자 영향 없음(§3) |
| **P3** | **web → server(payment)** | web 을 먼저 올려도 P1·P2 가 준비돼 있어 안전하다. 반대로 하면 리턴이 아직 열리지 않은 도메인으로 튄다 |
| P4 | brand | **반드시 마지막** — P3 전에 UI 를 열면 브랜드가 도메인을 연결했는데 사이트가 안 뜬다 |

---

## 8. 검증

### 8-1. 자동 (klow_server — 테스트 인프라가 있는 유일한 곳)

| 파일 | 잠그는 것 |
|---|---|
| `test/app.e2e-spec.ts` **수정** | cron 목록에 `'brand-domain-verify'` 추가 → **8 → 9** |
| `modules/brand-domains/__tests__/domain-host.spec.ts` **신규** | 정규화(대문자·trailing dot·스킴·포트 제거) · 거부 목록(`klow.kr`/`*.klow.kr`/`*.vercel.app`/IP 리터럴/localhost/253자·63자 초과) · punycode · **`brandA.co.kr` 을 코드가 apex 로 판정하지 않고 Vercel `apexName` 에 위임함** |
| `modules/brand-domains/__tests__/verified-origin.spec.ts` **신규** | `active` 만 통과 / `https://` 만 / **와일드카드·서브도메인 확장 없이 정확 일치** / 삭제 즉시 반영 / 빈 스냅샷에서 false. **여기가 느슨하면 전 브랜드 도메인이 CSRF 우회로가 된다** |
| `modules/payment/__tests__/return-redirect.spec.ts` **신규** | 미검증 host·타 브랜드 host → `FRONTEND_URL` 폴백 / `//evil.com` 류가 와도 `https://` 로만 구성 (**오픈 리다이렉트 회귀 잠금**) |
| `common/__tests__/cookie-options.spec.ts` **신규** | `hostOnly` 분기 + **`clear` 가 레거시 `.klow.kr` 까지 지운다** |
| `common/__tests__/client-ip.spec.ts` **신규** | secret 불일치면 `X-Klow-Client-IP` 를 **무시**(위조 차단) / 일치하면 헤더 우선 / **Throttler tracker 와 `clientIp()` 가 같은 값을 낸다** |
| `common/__tests__/origin-exempt.spec.ts` | **무변경으로 통과해야 한다** — 통과 안 하면 설계가 틀어진 것 |

**검증 3층** (CLAUDE.md):
1. `npm run typecheck` — `tsconfig.json` **과** `tsconfig.scripts.json` **둘 다**
2. `npm run test:e2e` — DI 그래프 + **cron 9개**
3. `npm run start` — env 가드 + 라우트 매핑(288 → **+4~5**)

klow_web / klow_brand 는 **테스트 인프라가 없다**(`package.json` scripts = dev/build/start/lint/type-check)
→ `npm run type-check` 로 `storefront.ts` 시그니처 파급만 확인한다.

### 8-2. 수동 E2E (스테이징)

1. 테스트 서브도메인 연결 → DNS 설정 → `pending → verifying → active` 전이
2. `https://<도메인>/` 이 브랜드관 렌더 (rewrite, **주소창 유지**)
3. PDP → 담기 → **네트워크 탭에서 모든 API 가 `/api-proxy/*` 로 나가는지**
4. 이메일 로그인 → **쿠키 탭에서 `klow_sid` 에 `Domain` 속성이 없고 커스텀 도메인 소속인지**
5. **Safari 에서 3~4 재현** (ITP 차단 여부는 여기서만 드러난다)
6. 결제 완주 → `/payment/return` 이 **커스텀 도메인**의 `/checkout/redirect` 로 303
7. 주문 상세에서 `agreementIp` 가 **Vercel IP 가 아닌 실제 클라이언트 IP** 인지
8. `shop.brandA.com/{다른브랜드}` → **브랜드 A 브랜드관**(남의 브랜드관이 안 뜬다) · `/{자기slug}` → 308 `/`
9. 구독 강제 해지 → 커스텀 도메인이 더 이상 서빙하지 않는지
10. 브랜드 `/stats` 에서 커스텀 도메인 방문·담기가 집계되는지 + 할인 링크 클릭이 계속 올라가는지
11. 결제 완주 후 **결제한 상품만** 카트에서 빠지고 나머지는 남는지(시딩 결제면 시딩 링크로 복귀하는지)
12. **부하** — 커스텀 도메인에서 짧은 시간에 여러 브라우저로 60회 이상 요청해 **429 가 뜨지 않는지**
    (Throttler tracker 가 실 IP 로 갈리는지). 이걸 안 보면 **브랜드가 늘어난 뒤에야 터진다**
13. **klow.kr 회귀 없음** — 로그인·담기·결제 완주 + `www.klow.kr` 정상

### 8-3. 문서

- `docs/server/modules/brand-domains.md` 신설 + `docs/server/README.md` 색인 (컨트롤러 변경 시 함께 갱신 — CLAUDE.md 규칙)
- `docs/deploy-custom-domain-runbook.md` (`deploy-free-text-product-tags-runbook.md` 형식)
- 워크스페이스 `CLAUDE.md` Key Facts 항목 추가 (쿠키 전략 변경 · 프록시 경로 · 배포 순서 주의)
- **릴리즈 노트/CS 가이드**: "커스텀 도메인과 klow.kr 은 로그인·장바구니가 별개"

---

## 9. 불변식 체크리스트 (착수 전 필독)

아래는 전부 **틀려도 컴파일과 테스트가 통과**한다. 각 PR 착수 전 해당 항목을 확인한다.

| # | 불변식 | 어기면 | PR |
|---|---|---|---|
| **F1** | `makeCookieHelpers` 의 **`clear` 를 `set` 과 대칭**으로(도메인 없음 / `.klow.kr` / 현재 옵션) | 로그아웃해도 레거시 `.klow.kr` 세션 쿠키가 남는다 | P2 |
| **F2** | apex 판정은 **Vercel `apexName`** 에 위임. 직접 레이블 수를 세지 않는다 | `brandA.co.kr` 에 **잘못된 DNS 레코드를 안내** — 첫 한국 고객부터 | P1 |
| **F3** | DNS 레코드 값은 **Vercel 응답을 저장해 그대로 표시**. 하드코딩 금지 | Vercel 이 값을 바꾼 날 신규 연결이 전부 실패 | P1 |
| **F4** | 결제 리턴 host 는 **리턴 시점에 재검증**(active + 주문 브랜드 일치), 스킴은 서버가 `https://` 구성 | **오픈 리다이렉트** | P3 |
| **F5** | 결제 리턴 host 는 **프록시 헤더로만** 받는다. 바디 금지 | 클라이언트가 임의 값 주입 → 오픈 리다이렉트 | P3 |
| **F6** | 프록시가 **실 클라이언트 IP 를 헤더로 전달**하고 서버가 secret 검증 후 신뢰 | `Order.agreementIp` 가 Vercel IP — **PG 분쟁 증거 손상** | P3 |
| **F7** | **`ThrottlerGuard.getTracker` 도 같은 IP 규칙**을 쓰게 한다 (`clientIp()` 만 고치면 절반) | 커스텀 도메인 전체가 한 rate-limit 버킷 → **정상 방문자 429** | P3 |
| **F8** | 프록시가 **요청 `Cookie` 헤더를 그대로 전달** | **인증이 통째로 안 된다** | P3 |
| **F9** | 응답 Set-Cookie 는 **`getSetCookie()` 배열**로 읽어 개별 `append` | 여러 쿠키가 콤마로 합쳐져 손상 | P3 |
| **F10** | 미들웨어 matcher 에서 **`api-proxy` 제외** | API 호출이 브랜드관으로 rewrite 되어 전부 깨진다 | P3 |
| **F11** | 미들웨어 `/{seg}` 규칙을 **pass-through 로 바꾸지 않는다** | 브랜드 A 도메인에서 **브랜드 B 브랜드관**이 렌더된다 | P3 |
| **F12** | `[influencer]/page.tsx` 의 `source` 를 **code 유무로 분기** | 미매칭 경로·봇이 전부 **할인 링크 유입으로 집계** | P0 |
| **F13** | `resolveHost` 가 **`PUBLIC_BRAND_WHERE` + 구독 게이트**를 함께 태운다 | 구독이 끊긴 브랜드의 도메인만 계속 살아남는다 | P1 |
| **F14** | `isVerifiedOrigin` 은 **정확 일치**. 와일드카드·서브도메인 확장 금지 | 전 브랜드 도메인이 **CSRF 우회로** | P1 |
| **F15** | 프록시가 **Origin 을 위장하지 않는다** | 프록시 경로가 CSRF 가드 우회로 + 감사 불가 | P3 |
| **F16** | 프록시 경로 허용은 **`/v1/` 접두만** | 어드민 표면이 브랜드 도메인에 노출 | P3 |
| **F17** | `test/app.e2e-spec.ts` cron 기대값 **8 → 9** | `@Cron` 미등록이 **완전 무음**(로그도 없다) | P1 |
| **F18** | `COOKIE_DOMAIN` 을 **전역 제거하지 않는다**(admin/brand 쿠키는 유지) | klow_brand 미들웨어의 세션 사전 게이트가 죽는다 | P2 |
| **F19** | `origin-exempt.spec.ts` 가 **무변경으로 통과** | 통과하지 않으면 설계가 틀어진 것 | P1 |
| **F20** | Vercel 추가 후 DB insert 실패 시 **보상 제거** + 해지 도메인 **정리 경로** | Vercel 쿼터 누수 · orphan 누적 | P1 |

---

## 10. 부록 — 코드로 검증한 사실 (2026-08-19)

이 계획의 전제들이다. **재조사하지 말고, 대신 구현 시점에 어긋나면 계획을 의심할 것.**

| # | 사실 | 왜 중요한가 | 근거 |
|---|---|---|---|
| V1 | **`@/lib/api` 의 소비자는 전부 `'use client'` 컴포넌트다** (importer 중 `'use client'` 없는 파일 0건) | `BASE` 를 브라우저에서만 프록시로 바꿔도 **SSR 이 깨지지 않는다**. 서버 사이드 fetch 는 `lib/brand-server.ts`·`app/sitemap.ts` 가 각자 절대 URL 로 따로 한다 | §4-2 |
| V2 | **klow_web 에 multipart/파일 업로드가 0건** (`api.upload` 는 컨시어지 제거 때 함께 삭제) | 프록시가 `arrayBuffer()` 로 바디를 통째 읽어도 된다 → 스트리밍(`duplex:'half'`) 불필요 | §4-2 |
| V3 | **`checkout/success` 는 API 를 부르지 않는다** (주문번호·이메일 쿼리로만 렌더) | 결제 완료 화면에 세션이 필요 없다 | `flow.md` §4 |
| V4 | **주문 확인 이메일의 배송조회는 쿠키가 아니라 URL 서명 토큰** (`/track/{id}?t=signGuestOrderToken(...)`) | 이메일 링크가 klow.kr 이어도 정상 동작 → 이메일 도메인화는 급하지 않다 | `order-confirmation-email.ts:86` |
| V5 | **전역 `ThrottlerGuard` 에 커스텀 tracker 가 없다** (기본 `req.ip`) | `clientIp()` 만 고치면 **커스텀 도메인 전체가 한 rate-limit 버킷**이 된다 | `app.module.ts:45`, F7 |
| V6 | **`clientIp()` 소비처는 3곳뿐** — `public-orders.controller.ts:70,88`, `public-seeding.controller.ts:102` | 어드민·웹훅 IP 기록은 프록시를 안 타므로 무영향 | §4-2 |
| V7 | **`[influencer]/page.tsx` 는 프로모션 code 가 null 이어도 `notFound()` 하지 않는다** | 미들웨어 `/{seg}` 규칙의 결과가 404 가 아니라 **자기 브랜드관**이다. 그래서 P0-5 의 `source` 분기가 필요하다 | F11, F12 |
| V8 | **Eximbay 결제 payload 에 도메인 파라미터가 없다** (`fgkey`/`payment`/`merchant`/`buyer`/`url`/`settings`/`product`) | 제한이 있다면 **가맹점 계정 설정** 쪽 → 코드로 확인 불가, 문의 필요 | `README.md` #0 |
| V9 | **klow_web 에 `src/middleware.ts` 가 없다** | 신규 생성이라 기존 미들웨어와의 충돌을 걱정할 필요가 없다 | §4-1 |
| V10 | **klow_web·klow_brand 에 테스트 인프라가 없다** (`package.json` scripts = dev/build/start/lint/type-check) | 회귀 잠금은 **전부 klow_server 스펙 + `type-check`** 로만 가능 | §8-1 |
| V11 | **`RESERVED_BRAND_SLUGS` 에 실제 라우트인 `customer-center`·`track`·`seed` 가 빠져 있다** | 이미 존재하는 잠재 버그이고, 미들웨어가 이 목록을 재사용하므로 P0 에서 먼저 고친다 | §1-1 |
| V12 | **cron 실제 개수는 8개** (워크스페이스 `CLAUDE.md` 의 "6개"는 낡았다) | 새 cron 추가 시 기대값은 **8 → 9** | F17 |
| V13 | **klow.kr ↔ api.klow.kr 은 eTLD+1 이 같아 브라우저에게 same-site** | 지금 세션이 정상인 이유이자, **klow.kr 을 프록시에서 제외해도 되는 근거** | `flow.md` §1-1 |
| V14 | **klow_web 클라 `StorefrontVisitSource` 는 `direct \| promotion` 둘뿐** (서버 enum 에는 `onsite` 도 있지만 클라가 보내지 않는다) | 유입 경로에 `custom_domain` 을 추가할 때 클라·서버 양쪽을 봐야 한다 | §2-9 |
