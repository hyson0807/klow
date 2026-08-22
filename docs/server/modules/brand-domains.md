# brand-domains — 브랜드 커스텀 도메인

- **모듈 경로**: `src/modules/brand-domains/`
- **목적**: 브랜드가 자기 도메인(`shop.brandA.com`)으로 **브랜드관을 열게** 한다. Vercel Domains API 로 도메인을 자동 등록·검증하고, klow_web 미들웨어가 물어볼 **Host → 슬러그 해석**을 제공하며, 그 도메인이 `api.klow.kr` 를 칠 수 있도록 **CORS·CSRF Origin 을 연다**.
- **설계 정본**: [`docs/custom-domain/implementation-plan.md`](../../custom-domain/implementation-plan.md) §2 (P1). 배경은 [`flow.md`](../../custom-domain/flow.md), 결정표는 [`README.md`](../../custom-domain/README.md).
- **관련 파일**: `brand-domains.service.ts`, `brand-domains.controller.ts`, `public-domains.controller.ts`, `brand-domains.cron.ts`, `vercel.client.ts`, `domain-host.ts`(정규화·거부), `domain-status.ts`(전이 판정·폴링 포기), 검증 스키마 `common/validation/brand-domain.ts`, 브랜드 게이트 `modules/brands/brand-selects.ts`, 오리진 정책표 `common/origin-policy.ts`

> ℹ️ **소비자 3곳** (2026-08-21 P4 까지 전부 붙었다 — 아직 미배포):
> ① klow_web `src/middleware.ts` 가 `GET /v1/storefront/resolve` 로 Host→슬러그를 해석해 서빙하고,
> ② klow.kr `/handoff` 가 같은 라우트로 복귀 host 를 재검증하며,
> ③ 브랜드 등록 UI 는 klow_brand **설정 > 도메인 연결**(`src/app/(authed)/settings/_components/DomainSection.tsx`)이다.
>
> ⚠️ 브랜드 UI 가 알아야 하는 것 세 가지: **(a) 폴링은 `GET /v1/brand/domains` 로** 한다 — `POST :id/check` 는 6회/분 상한이라 폴링하면 브랜드의 수동 클릭이 429 가 된다(cron 이 5분마다 갱신하므로 목록만 다시 읽으면 따라온다). **(b) `lastError` 는 "에러가 있다"의 신호가 아니다** — `refreshOne` 이 매번 덮어써서 정상 `pending` 에도 문구가 들어 있다(톤은 `status` 가 정한다). **(c) `recordValue` 는 빈 문자열일 수 있다** — 폴백 상수를 화면에서 채우지 말 것(F3).

## 데이터 모델 — `BrandDomain`

브랜드당 도메인 1개 = 1행. `Brand.customDomain` 단일 컬럼이 **아닌** 이유는 apex 와 `www` 가 Vercel 에 각각 등록해야 하는 별개 도메인이고(레코드 타입도 A vs CNAME), 검증 상태 머신과 Vercel 챌린지 원문을 담을 곳이 필요해서다.

| 컬럼 | 비고 |
|---|---|
| `host` `@unique VarChar(253)` | 소문자 punycode. 스킴·포트·trailing dot 없음. **라우팅 조회의 유일한 키** |
| `role` `primary \| redirect` | 브랜드가 입력한 호스트 = primary / apex 에 자동으로 딸려 붙는 www = redirect |
| `status` `pending \| verifying \| active \| error` | 아래 전이 규칙 |
| `recordType` / `recordValue` | 브랜드에게 안내할 DNS 레코드. **Vercel 응답을 그대로 저장**한다 |
| `verification` `Json?` | 소유권 TXT 챌린지 원문 배열. **재가공하지 않는다** |
| `lastError` `VarChar(300)` | 브랜드 UI 에 **그대로** 노출된다 — 민감정보·토큰 금지 |

- 마이그레이션 `20260821052240_add_brand_domains` — `CREATE TYPE ×2 + CREATE TABLE` 뿐 → **롤링 배포 안전 · 백필 없음**.
- ⚠️ **"primary 는 브랜드당 1개"를 DB 유니크로 못 박지 않았다.** Prisma 는 partial unique index(`WHERE role='primary'`)를 지원하지 않고 `@@unique([brandId, role])` 로 하면 `redirect` 까지 1개로 묶여 apex+www 페어가 두 벌 이상 존재할 수 없다. 서비스 + 상한(3개)이 강제하고 스펙이 잠근다.
- 상한 `MAX_DOMAINS_PER_BRAND = 3` (primary + redirect **합산**). 2개로 잡으면 `shop.brandA.com` 을 쓰는 브랜드가 apex·www 리다이렉트를 함께 걸 수 없다. Vercel 쿼터(Pro = 사실상 무제한)가 아니라 **운영 부담**을 막는 값이다.

## brand-domains.controller.ts (`@Controller('v1/brand/domains')`, `BrandGuard`)

| Method | Path | Throttle | 기능 |
|---|---|---|---|
| GET | `/v1/brand/domains` | 전역 60/분 | `{ domains: BrandDomainDTO[] }` |
| POST | `/v1/brand/domains` | 전역 60/분 | `{ host }` → `201 { domain, pair }` |
| POST | `/v1/brand/domains/:id/check` | **6/분** | "지금 확인" — cron 1건과 같은 로직 |
| DELETE | `/v1/brand/domains/:id` | 전역 60/분 | `204`. **페어 단위 삭제** |

```ts
type BrandDomainDTO = {
  id: string; host: string;
  role: 'primary' | 'redirect';
  status: 'pending' | 'verifying' | 'active' | 'error';
  recordType: string; recordValue: string;   // Vercel 이 준 값 그대로
  verification: unknown[] | null;            // Vercel 챌린지 원문 배열 그대로
  lastError: string | null;                  // 사람이 읽는 사유(그대로 표시)
  verifiedAt: string | null;
};
```

⚠️ `brandId`·`lastCheckedAt` 은 **싣지 않는다**(브랜드가 쓸 일이 없다).
⚠️ `verification` 은 **재가공하지 않는다** — 우리가 모양을 바꾸면 Vercel 이 값을 바꾼 날 조용히 깨진다.

**에러 코드** — `{ code, message }` 로 내린다. **표시 문구는 서버 `message` 를 그대로** 쓴다.

| code | HTTP | 언제 |
|---|---|---|
| `domain_invalid` | 400 | 정규화·거부 규칙 위반 |
| `domain_taken` | **409** | **다른 KLOW 브랜드**가 이미 연결 (Vercel 을 부르기 **전에** 잡는다) |
| `domain_already_in_use` | **409** | Vercel 쪽 충돌 — 다른 Vercel 계정 또는 **우리 팀의 다른 프로젝트** |
| `domain_limit` | 400 | 브랜드당 3개 초과 |
| `subscription_required` | 403 | 구독 `active` 아님 |
| `domain_service_unavailable` | 503 | `VERCEL_*` 미설정 |

## public-domains.controller.ts (`@Controller('v1/storefront')`, 공개)

| Method | Path | Guard | Throttle |
|---|---|---|---|
| GET | `/v1/storefront/resolve?host=` | public | **`@SkipThrottle()`** |

응답 `200 { slug: string \| null, redirectTo: string \| null }` + `Cache-Control: public, max-age=60, s-maxage=60`.

- **404 를 쓰지 않는다** — 미등록 host 도 200 + `slug:null` 이라 미들웨어에 상태코드 분기가 없다(`/embed/v1/resolve` 가 `{found:false}` 로 뭉갠 것과 같은 이유).
- `redirectTo` 는 **호스트만** 담는다. 스킴·경로·쿼리는 부르는 쪽이 조립한다.
- ⚠️ **`role='redirect'`(www) 호스트는 `slug:null` + `redirectTo:'{apex}'`** 로 나온다. 즉 "이 host 가 우리 것인가"를 `slug !== null` 로만 판정하면 www 는 거짓이 된다. P3 미들웨어는 307 로 apex 에 넘기므로 실제로 손님이 www 에 머무르는 일이 없어 **F21 의 `slug !== null` 검증은 그대로 옳다** — 다만 그 이유가 "www 가 유효하지 않아서"가 아니라 **"애초에 도달할 수 없어서"** 라는 것을 알고 있을 것.
- **부르는 쪽이 둘이다**: ① klow_web 미들웨어(서버 사이드, P3 — Host→슬러그 라우팅) ② klow.kr 의 `/handoff` 페이지(**브라우저**, P2 — 복귀 host 재검증 `F21`). ⚠️ `/embed/*` 의 수동 CORS(`ACAO:*`)를 **복사하지 않은 이유는 "브라우저가 안 부른다"가 아니라** ②가 `klow.kr` 오리진이라 **정적 화이트리스트로 이미 통과**하기 때문이다. **비화이트리스트 오리진(=브랜드 커스텀 도메인)은 이 라우트를 부르지 않는다** — 그 판단이 바뀌면(예: 커스텀 도메인에서 직접 호출) `ACAO` 를 붙여야 하고, 그때는 `/embed/*` 의 "영구 simple request" 하드룰이 함께 따라온다.
- ⚠️⚠️ **`@SkipThrottle()` 이 이 라우트 하나에만** 붙는다. 부르는 쪽이 Vercel 엣지라 klow_server 가 보는 IP 가 하나로 뭉치는데 전역 스로틀은 60/분 per IP 다. 도메인이 몇 개만 붙어도 천장에 닿고, 429 가 나면 미들웨어가 fail-open 해서 **전 브랜드 도메인이 동시에** KLOW 홈(그리고 `/{seg}` 는 503)이 된다. 남용 방어는 ① 응답이 공개 정보(호스트→슬러그)뿐 ② `Cache-Control` 을 엣지가 흡수 ③ 미들웨어 캐시가 앞단에 있다는 것으로 갈음한다. (`payment/return`·`webhooks/eximbay` 가 같은 이유로 이미 SkipThrottle 이다.)
- ⚠️ **반영 지연이 최대 2분이다** — 응답 캐시 60초 + 미들웨어 양성 캐시 60초. 즉 **구독 해지·도메인 삭제 후에도 최대 2분간 계속 서빙**된다. 엣지에 분산된 미들웨어 캐시를 밖에서 무효화할 방법이 없어 설계상 수용했고, 두 값을 짧게 유지하는 것이 그 대가다.

### resolve 게이트 — 구독까지 함께 본다

⚠️⚠️ **`PUBLIC_BRAND_WHERE` 에는 구독 게이트가 없다**(status `notIn` 뿐이라 `pending`·`draft` 도 통과한다). 구독 게이트는 지금까지 **제품 쪽에만**(`products/product-selects.ts` `isPurchasable()`) 있었다.

그래서 브랜드 축의 규칙을 **`brands/brand-selects.ts` 한 곳이 소유**하게 바꿨다 — 세 형태를 한 블록에 둔다:

| 형태 | 심볼 | 쓰는 곳 |
|---|---|---|
| select | `BRAND_SERVICEABLE_SELECT` | `BRAND_GATE_SELECT` · resolve |
| JS 술어 | `isBrandServiceable()` (별칭 `canServeStorefront`) | `resolveHost` · `isPurchasable` |
| Prisma where | `BRAND_SERVICEABLE_WHERE` / `BRAND_NOT_SERVICEABLE_WHERE` | 오리진 스냅샷 · `cleanupOrphans` |

⚠️ **하나를 고치면 나머지 둘도 고칠 것.** `products/product-selects.ts` 는 브랜드 축을 다시 쓰지 않고 이걸 호출한다(legacy `brandId === null` 면제만 제품 쪽에 남는다 — 도메인은 늘 브랜드에 매달려 있다).

⚠️⚠️ **Prisma 짝이 없던 동안 실제로 어긋났다**: `cleanupOrphans` 가 부정형을 손으로 써서 구독 축만 봤고, 그래서 `pending`·`rejected`·`withdrawal_pending` 브랜드가 정리 후보에서 통째로 빠져 있었다(서빙은 막혔는데 Vercel 등록만 영원히 남는 상태). 테스트 스텁이 **정본 상수를 참조 동일성으로 확인**해 손으로 쓴 절이 들어오면 즉시 throw 한다.

해석하지 않는 경우(전부 `{slug:null, redirectTo:null}`): 미등록 host · `status !== 'active'` · 브랜드 미승인/탈퇴 · 가입 브랜드인데 구독 비-active · **`Brand.slug` 이 null**(nullable 컬럼이라 도메인은 붙었는데 슬러그가 없는 브랜드가 성립한다).

## Vercel 연동 (`vercel.client.ts`)

`@vercel/sdk` 대신 **native fetch**(`AbortController` 15s + `BadGatewayException`) — 이 서버의 외부 HTTP 관례(`instagram.client.ts`·`efs.client.ts`)와 같다. API 버전은 2026-08-21 스테이징 프로젝트에 실측해 확정했다.

| 동작 | REST |
|---|---|
| 추가 | `POST /v10/projects/{id}/domains?teamId=` |
| 상태 조회 | `GET /v9/projects/{id}/domains/{host}` (404 → `null`) |
| 검증 트리거 | `POST /v9/projects/{id}/domains/{host}/verify` |
| DNS 설정 확인 | `GET /v6/domains/{host}/config` |
| 제거 | `DELETE /v9/projects/{id}/domains/{host}` (404 관대) |

### ⚠️⚠️ `verified` 는 "접속이 되는가"가 아니라 "소유권이 다투지 않는가"다

2026-08-21 실측: 우리가 소유하지도 않은 `dtest.co.kr` 을 추가하니 **그 자리에서 `verified: true`** 였고(`POST …/verify` 도 그대로 true), 같은 시점 `getDomainConfig` 는 **`misconfigured: true`** 였다. DNS 를 한 줄도 걸지 않은 상태다.

**그래서 전이 조건은 반드시 두 API 를 모두 본다** (`domain-status.ts decideDomainStatus`):

```
verified && !misconfigured        → active
!verified && verification 有      → verifying   (소유권 TXT 안내) → POST …/verify 재시도
그 외                              → pending     (A/CNAME 안내 유지)
```

`verified` 만 보고 `active` 로 올리면 브랜드가 도메인을 입력한 **그 순간 "연결 완료"** 로 뜨고, 정작 주소를 열면 아무 데도 닿지 않는다.
⚠️ `error` 는 이 함수가 만들지 않는다 — 7일 초과 pending 을 접는 건 **cron 전용** 규칙이고, "지금 확인"은 반대로 error 를 되돌리는 복구 경로여야 한다.

### ⚠️⚠️ apex 판정을 우리가 하지 않는다

`brandA.co.kr` 은 레이블이 3개지만 apex 다 — 이중 TLD 는 Public Suffix List 문제이고 한국 브랜드가 주 대상이라, 레이블 수를 세면 **첫 고객부터 잘못된 DNS 레코드를 안내**한다. 도메인 추가 응답의 **`apexName === name`** 이 정본이다(실측: `dtest.co.kr → apexName dtest.co.kr` / `dtest.klow.kr → apexName klow.kr`). `domain-host.ts` 는 **정규화·거부만** 담당하고, `domain-host.spec.ts` 가 "apex 판정 함수를 export 하지 않음"을 직접 단언한다.

### ⚠️ DNS 값을 하드코딩하지 않는다

`getDomainConfig` 응답의 **`rank:1` 권장값을 저장해 그대로 표시**한다. 응답 모양이 단순 문자열이 아니다 — `rank` 가 붙은 배열이고 IPv4 는 `value` 가 다시 배열이다:

```json
{ "misconfigured": true,
  "recommendedIPv4":  [{"rank":1,"value":["216.150.1.1","216.150.16.1"]},{"rank":2,"value":["76.76.21.21"]}],
  "recommendedCNAME": [{"rank":1,"value":"49f87b35b8122d1a.vercel-dns-017.com."},{"rank":2,"value":"cname.vercel-dns.com."}] }
```

`rank:2` 는 legacy 폴백이라 **화면에 같이 띄우지 않고**(둘 중 뭘 넣냐는 문의가 생긴다), CNAME 값의 **후행 점을 제거**해야 브랜드가 그대로 복사해 넣을 수 있다. 하드코딩한 값(`76.76.21.21`/`cname.vercel-dns.com`)을 안내하면 Vercel 이 타겟을 옮긴 날 신규 연결이 전부 실패한다.

### ⚠️ `domain_already_in_use`(409)는 "다른 Vercel 계정" 전용이 아니다

**같은 팀의 다른 프로젝트**와 충돌해도 같은 코드가 온다. 응답에 실린 `error.domain.projectId` 로 갈라서 안내한다 — 우리 프로젝트면 내부 충돌(운영/스테이징 오지정), 아니면 다른 계정이라 소유권 TXT 안내가 필요하다. 같은 KLOW 브랜드끼리의 중복은 `host @unique` 로 **Vercel 을 부르기 전에** `domain_taken` 으로 잡는다.

### ⚠️ 리다이렉트를 설정하지 않는다

도메인 추가 시 redirect 를 **보내지 않는다.** Vercel 대시보드에서 "Redirect to primary domain" 이 붙으면 **브랜드 도메인이 전부 klow.kr 로 튕겨** 기능이 통째로 죽는다.

## apex ↔ www 페어 — 브랜드는 호스트를 하나만 입력한다

1. 입력한 호스트 = **`role='primary'`**. 화면도 이것 하나를 기준으로 그린다.
2. **그 호스트가 apex 이면** `www.{host}` 를 `role='redirect'` 로 자동 함께 등록한다(Vercel 에도 추가). 서브도메인(`shop.brandA.com`)이면 **페어를 만들지 않는다.**
3. ⚠️⚠️ **거꾸로(서브도메인 입력 → apex 자동 등록)는 절대 하지 않는다** — apex 는 브랜드의 기존 홈페이지일 가능성이 높고, 그걸 가져가면 **브랜드 사이트를 죽인다.**
4. **페어 실패는 primary 를 막지 않는다.** redirect row 의 `lastError` 에 사유를 남기고 브랜드가 재시도한다.
5. **삭제는 페어 단위** — primary 를 지우면 그 apex 의 www redirect 도 Vercel·DB 양쪽에서 함께 지운다.
6. `redirectTo` 는 `www.` 를 벗겨 파생한다(페어가 `www.{apex}` 로만 생기므로 성립). ⚠️ 벗긴 호스트가 **같은 브랜드의 active primary 인지 확인한 뒤에만** 내린다 — 검증 없이 파생하면 오픈 리다이렉트가 된다.

## 생명주기 — 등록 실패 롤백 · 해지 시 정리

- 순서는 **Vercel 추가 → DB insert**. ⚠️ insert 가 실패하면 **보상으로 Vercel 에서 제거**하고, 그마저 실패하면 Sentry 로 올린다. 안 되돌리면 그 도메인은 우리 UI 어디에도 안 뜨는데 Vercel 쿼터를 먹고, 재시도하면 `domain_already_in_use` 로 영원히 막힌다.
- 삭제 시 Vercel 제거가 실패해도 **DB 는 지운다** — 브랜드 화면에서 사라지는 게 우선이고, 남은 Vercel 등록은 정리 cron 이 최종 안전망이다.
- `cleanupOrphans()` — 브랜드 `withdrawn` 은 즉시(이미 30일 탈퇴 유예를 거친 뒤다), 그 밖의 서비스 불가 브랜드는 **60일 유예 후** Vercel 제거 + row 삭제. ⚠️ 즉시 제거하면 결제 실패로 잠깐 `past_due` 가 된 브랜드가 재결제 후 DNS 를 처음부터 다시 설정해야 한다. **유예 동안에도 서빙은 `resolveHost` 가 이미 막는다** — 남는 건 Vercel 등록뿐이다.
- ⚠️⚠️ **유예 시계는 `BrandDomain.updatedAt` 이 아니다** (2026-08-22 정정 — 그전엔 그랬고, 그래서 유예가 사실상 0이었다). `active` 행은 다시 쓰이지 않으므로(폴링 cron 이 `pending`/`verifying` 만 집는다) 그 값이 **활성화된 순간에 얼어붙어**, 60일 넘게 잘 돌던 도메인이 구독이 끊기는 **첫 사이클에 즉시** 삭제됐다. 반대로 `pending` 행은 cron 이 매번 값을 올려 유예가 영원히 리셋됐다. 정본은 `brands/brand-selects.ts` 의 **`brandUnserviceableSinceWhere()` + JS 짝 `brandUnserviceableSince()`** 이고, 시계는 **원인 축의 행**이 쥔다(`status` 로 배타적인 세 분기 — 승인 축이면 `Brand.updatedAt` / 구독 축이면 `BrandSubscription.updatedAt` / 구독 행이 없으면 `Brand.updatedAt` 폴백). 두 시계 모두 무관한 편집으로 **늘어날 수는 있어도 줄지 않아** 틀려도 안전한 방향으로만 틀린다.
- ⚠️ 유예 절은 `BRAND_NOT_SERVICEABLE_WHERE` 옆에 **`AND:` 로 얹는다**(relation 필터를 한 객체에 두 번 쓸 수 없다). 스텁의 참조 동일성 가드가 살아 있어야 하므로, 런타임 날짜가 박힌 유예 절은 팩토리 옆의 **`unserviceableSinceOf()`** 가 되꺼내 정본 JS 짝으로 판정한다 — 스텁이 판정을 복제하지 않는다.

## brand-domains.cron.ts — `@Cron('*/5 * * * *')` name `brand-domain-verify`

- `status IN (pending, verifying)` 중 `lastCheckedAt` 오래된 순 `take: 20`(rate limit 보호), 외부 호출 동시성 cap 5.
- `createdAt` 7일 초과 pending → `error` (무한 폴링 차단). "지금 확인"이 복구 경로다. 임계값·대상 status 는 `domain-status.ts` 의 **`pendingGiveUpWhere(now)`** 가 소유하고 `verifyDue()` 가 그 where 를 **그대로** 쓴다(스펙은 `verifyDue()` 를 통째로 돌려 잠근다). ⚠️ **`pending` 만 대상**이다 — `verifying` 을 포함시키면 소유권 확인 중인 도메인이 일주일 만에 조용히 죽는다.
- ⚠️ 외부 호출은 `mapWithConcurrency`(5개씩)로 돈다. **순차로 돌리면 안 된다** — 한 건이 15초 타임아웃에 걸리면 배치 20건이 최대 5분이라 cron 주기를 넘겨 다음 사이클이 재진입 가드에 막힌다.
- 같은 배치에서 `cleanupOrphans()` 를 겸한다.
- **재진입 가드** `running` — 한 사이클이 Vercel API 를 최대 20건 × 2~3회 태우므로 주기를 넘길 수 있다(`payment-reconcile.cron.ts` 와 같은 가드).
- kill switch `BRAND_DOMAIN_CRON_ENABLED=false` (미설정 = on).
- ⚠️ 이 cron 때문에 `test/app.e2e-spec.ts` 의 기대 목록이 **8 → 9개**가 됐다. `@Cron` 클래스를 모듈 providers 에 안 넣으면 **완전 무음**으로 실행되지 않는다.

## Origin 술어 — `main.ts` (§2-5)

⚠️⚠️ **이게 없으면 비콘이 아니라 브랜드관 화면이 통째로 빈다.**

| 걸리는 것 | 무엇이 | 없으면 |
|---|---|---|
| **CORS** (더 크다) | 브랜드관·PDP 의 **모든 데이터 GET**. `BrandStorefront` 는 `'use client'` 라 브라우저가 `api.klow.kr` 를 직접 친다 | 제품·브랜드가 하나도 안 뜬다 |
| **Origin CSRF 가드** | 방문·담기 트래킹 비콘 2개 (`/v1/storefront-stats/track/{visit,cart-add}`) | 403 (집계만 유실) |

`main.ts` 는 `app.get(BrandDomainsService)`(이 파일의 첫 DI 접근)로 서비스를 꺼내 술어 2개를 만들고, **CSRF 미들웨어와 `enableCors` 가 그 둘을 그대로 공유**한다 — 두 판정이 갈리면 반드시 사고가 난다.

- **분류와 정책은 `common/origin-policy.ts` 가 소유하고 스펙이 잠근다.** ⚠️ 별도 파일인 이유는 `origin-exempt.ts` 와 같다 — `bootstrap()` 안의 익명 콜백에 두면 **테스트로 잠글 수가 없다**. 분류를 한 번만 하고(`classifyOrigin`) CSRF 가드는 `allowsStateChange`, CORS 는 `corsPolicyFor` 로 **같은 결과를 나눠 쓴다**. 새 오리진 분류가 생기면 `CORS_POLICY` 표에 **한 줄만** 추가한다(분기를 늘리지 말 것).
- `isVerifiedOrigin()` 은 **동기**다(express 미들웨어와 cors 의 origin 판정이 sync). 서비스가 `Set<string>` 스냅샷을 들고 TTL 60초로 **백그라운드 갱신**하되 현재값을 즉시 반환한다. 첫 로드 전엔 빈 Set → false(fail-closed). **생성·삭제·상태 전이는 그 자리에서 `await` 로 갱신**한다. ⚠️ TTL 시계는 **성공이 아니라 시도**에 찍는다 — 성공에만 찍으면 DB 가 흔들리는 동안 매 요청이 새 쿼리를 쏴 장애 때 부하를 더 얹는다.
- ⚠️ 스냅샷 조회는 브랜드 게이트를 **where 로 밀어넣는다**(JS 필터가 아니라). Prisma 기본 로드 전략이 관계마다 별도 쿼리라, `brand`·`subscription` 을 select 하면 한 번 갱신에 3왕복이 된다.
- ⚠️⚠️ **정확 일치만 한다.** 와일드카드·서브도메인 확장을 넣으면 브랜드 도메인 하나가 그 아래 전체를 CSRF 우회로로 만든다.
- 스냅샷은 `role='primary' && status='active'` **이면서 브랜드 게이트를 통과한** 호스트의 `https://{host}` 뿐이다. redirect 는 넣지 않는다(브라우저가 307 로 즉시 빠지므로 허용해도 얻는 게 없고 표면만 넓어진다).
- **`credentials` 를 오리진별로 가른다** — klow.kr 계열은 `credentials:true`(쿠키 세션), 브랜드 커스텀 도메인은 **`credentials:false`**. 커스텀 도메인은 설계상 세션을 쓰지 않으므로(클라가 `credentials:'omit'`), 서버가 ACAC 를 안 붙이면 실수로 `include` 를 써도 브라우저가 차단해 그 규칙이 **서버쪽에서 fail-closed** 가 된다. ⚠️ 커스텀 도메인 요청에 `Cookie` 헤더가 실린다면 설계가 어긋난 것이다.
- 비콘 POST 가 `Content-Type: application/json` 이라 방문마다 preflight 가 붙으므로 `maxAge: 86400` 을 함께 준다(없으면 요청 수가 2배).
- ⚠️ **`common/origin-exempt.ts` 는 손대지 않았다** — 새 예외 경로가 없다. `origin-exempt.spec.ts` 가 **무변경으로 통과해야 하고, 통과하지 않으면 설계가 틀어진 것**이다.
- ⚠️ **`/embed/*` 무회귀** — 그 컨트롤러가 `setHeader`(덮어쓰기)로 `ACAO:*` 를 쓰고 `ACAC` 를 `removeHeader` 하므로 delegate 가 뭘 붙이든 결과가 같다. **`res.append` 로 바꾸면 안 된다**(ACAO 중복 → 브라우저 전면 거부). 비화이트리스트 preflight 는 종전 배열 미스와 동일하게 ACAO 없이 끝나므로 "영구 simple request" 하드룰도 그대로다.

## 호스트 정규화 (`domain-host.ts`)

`normalizeHost(raw)` — 스킴을 붙여 `new URL()` 로 넘긴다. 소문자화·IDNA(punycode) 변환·포트/경로 제거가 **한 번에** 끝난다(Node 내장 — 새 의존성 없음). 직접 정규식으로 하면 IDNA 를 우리가 구현하게 된다.

- 흡수: `https://Shop.BRAND.com/products?a=1` · `shop.brand.com:443` · `shop.brand.com.` · `//shop.brand.com` · `쇼핑몰.한국` → `xn--352bl7khqr.xn--3e0b707e`
- 거부(`domain_invalid`): `klow.kr` · `*.klow.kr` · `*.vercel.app` · `*.vercel.sh` · `*.localhost` · IP 리터럴(v4/v6) · 단일 라벨 · 라벨 63자·전체 253자 초과 · 하이픈으로 시작/끝 · 허용되지 않는 문자
- ⚠️ 접미사 매칭이 과잉이면 안 된다 — `myklow.kr`·`klow.kr.brand.com`·`notvercel.app` 은 정당한 등록 대상이다(스펙이 잠근다).
- ⚠️ **`common/validation/brand-domain.ts` 는 형식·길이만 본다**(`BrandDomainHostField` = trim + 1~260자). 정규화를 그쪽에서 부르지 않는 이유는 **`common/` 이 `modules/` 를 import 할 수 없어서**다(CLAUDE.md 규칙 2 — eslint 가 막는다). 상한이 253 이 아니라 260 인 것도 같은 이유다: `https://foo.com/` 를 붙여넣은 입력을 받아 줘야 정규화가 그걸 벗길 기회를 얻는다.

⚠️⚠️ **쓰기와 읽기가 같은 표준형 함수를 쓴다** — `canonicalHost()`(거부 없이 표준형만, 실패 시 `null`)를 `normalizeHost()`(쓰기)와 `resolveHost()`(읽기)가 공유한다. 예전엔 조회 쪽이 `trim/toLowerCase/replace/split(':')` 를 손으로 다시 써서 **IDNA 변환이 빠져 있었다** — 한글 도메인이 저장은 punycode 로 되고 조회는 U-label 로 들어와 영영 안 맞는다.

## 환경변수

| env | 비고 |
|---|---|
| `VERCEL_TOKEN` | 프로젝트 도메인 관리 권한. 비면 도메인 API 가 **503 `domain_service_unavailable`** |
| `VERCEL_PROJECT_ID` | ⚠️⚠️ **운영·스테이징이 서로 다른 프로젝트다**(`klow-web` / `klow-web-staging`). 스테이징 서버가 운영 project id 를 들고 있으면 **테스트로 붙인 브랜드 도메인이 운영 사이트에 꽂힌다** |
| `VERCEL_TEAM_ID` | 팀 소속이면 필수 (`team_xxx`) |
| `BRAND_DOMAIN_CRON_ENABLED` | `false` 일 때만 폴링 cron 비활성 (미설정 = on) |

⚠️ **부팅 fail-closed 가드를 붙이지 않았다.** 기존 fail-closed 3종(Eximbay·`GUEST_ORDER_SECRET`·OTP)은 "조용히 깨지고 돈이 사라지는" 경로다. 도메인은 미설정 시 브랜드가 즉시 에러를 보므로 부팅을 막을 성질이 아니다.

ℹ️ Vercel 플랜은 **Pro** 라 도메인 수 상한(soft 100k)은 걱정하지 않아도 된다.

## 알려진 갭 (2026-08-22 검토 — 의도적으로 남긴 것)

ℹ️ 같은 검토에서 **고친 것 2건**: ① `shouldGiveUpPending()` 이 실행 경로에 없고 `verifyDue()` 가 같은 규칙을 Prisma where 로 다시 쓰던 것(→ `pendingGiveUpWhere(now)` 하나로 합치고 스펙을 `verifyDue()` 경유로 바꿨다) ② `rowFieldsFrom` 이 챌린지가 사라졌을 때 `verification` 에 `undefined` 를 써서 Prisma 가 "건드리지 않음"으로 해석 → `verifying` 을 벗어난 행이 **옛 TXT 를 영원히** 들고 DTO 로 내보내던 것(→ `Prisma.DbNull`).

| 갭 | 왜 남겼나 |
|---|---|
| `createForBrand` 의 `count`/`findUnique` → `create` 가 **비트랜잭션** | 더블 서브밋이면 상한 3개를 넘길 수 있고, `host @unique` P2002 가 보상 제거를 거친 뒤 **409 가 아니라 raw 500** 으로 나간다. 브랜드 자기 계정 안의 경합이라 피해가 자기 자신뿐이다 |
| `recommendedRecord` 가 `rank:1` IPv4 **2개 중 첫 번째만** 안내 | 단일 A 레코드로도 동작하고 잃는 건 이중화뿐이다. 배열로 바꾸면 DTO·UI·스펙이 함께 움직인다 |

## 회귀 잠금

| 스펙 | 잠그는 것 |
|---|---|
| `__tests__/domain-host.spec.ts` | 정규화·거부·punycode·접미사 과잉 매칭 + **apex 판정 함수를 export 하지 않음** |
| `__tests__/domain-status.spec.ts` | **`verified:true` + `misconfigured:true` 가 active 가 되지 않음** · 둘 다 만족해야 active · `error` 로는 전이하지 않음 |
| `__tests__/verified-origin.spec.ts` | **정확 일치**(서브도메인·접미사·포트 트릭 전부 차단) · active/primary 만 · 브랜드 구독 게이트 · 삭제 즉시 반영 · 로드 전 false |
| `__tests__/domain-pairing.spec.ts` | apex → www 동반 생성 / **서브도메인 → 페어 없음** / 페어 실패가 primary 를 롤백하지 않음 / 페어 동반 삭제 / **Vercel 성공 + DB 실패 → 보상 제거** / 게이트 4종 |
| `__tests__/resolve-host.spec.ts` | **F13** — 구독·탈퇴·미승인·`slug:null` 미해석 / redirect 파생과 **오픈 리다이렉트 차단** / 미등록 host 200 / **`cleanupOrphans` 후보가 서빙 게이트의 부정인지** / **F33** 유예 시계가 브랜드 쪽 행인지(구독이 **방금** 끊긴 오래된 도메인은 아직 정리 대상이 아니다) |
| `common/__tests__/origin-policy.spec.ts` **(신규)** | CSRF·CORS 가 **같은 분류**를 본다 / 브랜드 도메인에 **ACAC 미부착** / 비화이트리스트에 **ACAO 미반사**(`/embed/*` 하드룰의 근거) |
| `test/app.e2e-spec.ts` | cron 목록 **9개** |
| `common/__tests__/origin-exempt.spec.ts` | **무변경 통과** |
