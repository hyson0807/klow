# 배포 런북 — 브랜드 커스텀 도메인 (2026-08-22)

브랜드가 자기 도메인(`shop.brandA.com`)으로 **브랜드관·PDP·장바구니**를 열고, **로그인·결제·
주문조회는 `klow.kr`** 로 넘기는(핸드오프) 기능의 프로덕션 배포 절차. 코드는 P0~P4 가 세 레포
`staging` 에 머지돼 있고 스테이징에서 실도메인 라우팅까지 확인했다.

관련: [`custom-domain/README.md`](./custom-domain/README.md) ·
[`custom-domain/implementation-plan.md`](./custom-domain/implementation-plan.md)(정본) ·
[`server/modules/brand-domains.md`](./server/modules/brand-domains.md)

## 왜 순서가 중요한가

**마이그레이션이 아니라 레포 간 순서가 위험 요소다.** `20260821052240_add_brand_domains` 는
`CREATE TYPE ×2 + CREATE TABLE` 뿐이라 **롤링 배포 안전 · 백필 없음 · 롤백 시에도 되돌릴 필요가
없다**(아무도 안 읽는 빈 테이블로 남는다). 대신 세 가지가 순서에 걸린다.

| # | 걸리는 것 | 뒤집으면 |
|---|---|---|
| 1 | **예약 슬러그 미러**(`reserved-slugs.ts` — klow_web + klow_server) | 갈리면 서버는 그 슬러그 가입을 허용하는데 프론트가 그 브랜드관을 못 연다. **같은 창에** 나가야 한다 |
| 2 | **P2(핸드오프 수신) → P3(송신)** | 뒤집으면 손님이 klow.kr 의 **없는 `/handoff` 에서 404** 를 본다. 반대는 무해하다(아무도 링크하지 않는 라우트가 하나 생길 뿐) |
| 3 | **P3(서빙) → P4(브랜드 등록 UI)** | 뒤집으면 브랜드가 도메인을 연결했는데 그 주소가 안 뜬다 |

P1(서버)은 프론트가 아직 아무것도 부르지 않으므로 언제 나가도 무해하고, **P3 에는 서버 변경이
없다** — 그래서 롤백은 klow_web 하나만 되돌리면 끝난다.

## 사전 확인 (배포 창 전에)

```bash
# ── 0) 네 레포가 전부 빌드되는지
cd klow_server && npm run typecheck && npm run test:e2e   # ⚠️ cron 기대값 9
cd ../klow_web   && npm run type-check && npm run check:handoff && npm run build
cd ../klow_brand && npm run type-check && npm run build
```

**운영 env 를 먼저 채운다** (Railway — 없으면 도메인 API 가 `503 domain_service_unavailable`):

| env | 값 | 함정 |
|---|---|---|
| `VERCEL_TOKEN` | 프로젝트 도메인 관리 권한 토큰 | — |
| `VERCEL_PROJECT_ID` | **운영은 `klow-web`** | ⚠️⚠️ 운영·스테이징이 **서로 다른 프로젝트**다(`klow-web` / `klow-web-staging`). 스테이징 서버가 운영 id 를 들고 있으면 **테스트로 붙인 브랜드 도메인이 운영 사이트에 꽂힌다.** 배포 전에 양쪽 값을 각각 눈으로 확인할 것 |
| `VERCEL_TEAM_ID` | `team_…` | 팀 소속이면 필수 |
| `BRAND_DOMAIN_CRON_ENABLED` | (미설정 = on) | `false` 일 때만 폴링 cron 이 꺼진다 |

⚠️ **부팅 fail-closed 가드는 일부러 없다** — 미설정은 "조용히 깨지고 돈이 사라지는" 종류가 아니라
브랜드가 즉시 503 을 보는 종류다. 그래서 **env 를 빠뜨려도 배포는 성공한다**. 확인은 사람이 한다.

## 순서

```bash
# ── 1) klow_server (마이그레이션 포함) + klow_web 예약 슬러그를 같은 창에
#      ⚠️ 마이그레이션은 추가 전용이라 롤링 안전 — 유지보수 모드가 필요 없다.
#      배포 후: 라우트 매핑 · cron 9개 등록 로그 확인

# ── 2) klow_web (P2 수신부 + P3 서빙·송신부)
#      P2 와 P3 가 한 커밋에 있으므로 이 배포로 둘 다 나간다.
#      ⚠️ 1번보다 먼저 내면 그 창의 커스텀 도메인 요청이 전부 503/KLOW 홈이다.

# ── 3) klow_brand (P4 설정 > 도메인 연결)
#      ⚠️ 반드시 마지막. 먼저 내면 브랜드가 연결했는데 사이트가 안 뜬다.
```

## 배포 후 검증

```bash
# ── 서버 ──────────────────────────────────────────────────────────────
# resolve 가 200 + Cache-Control 을 주는지 (미등록 host 도 404 가 아니라 200 + slug:null)
curl -sD- -o/dev/null 'https://api.klow.kr/v1/storefront/resolve?host=nope.example.com'
#   기대: 200 · Cache-Control: public, max-age=60, s-maxage=60

# 브랜드 도메인 오리진에 ACAO 는 붙고 **ACAC 는 안 붙는지** (F8 을 서버가 fail-closed 로 강제)
curl -sD- -o/dev/null -H 'Origin: https://<연결한도메인>' 'https://api.klow.kr/v1/brands/<slug>'
#   기대: Access-Control-Allow-Origin 有 / Access-Control-Allow-Credentials **無**

# /embed/* 무회귀 — 여전히 ACAO:* 여야 한다
curl -sD- -o/dev/null 'https://api.klow.kr/embed/v1.js' | grep -i access-control-allow-origin
#   기대: *

# cron 9개 — 부팅 로그에 'brand-domain-verify' 가 있는지
#   ⚠️ @Cron 미등록은 **완전 무음**이다(typecheck 통과·로그 없음).

# ── 커스텀 도메인 (브랜드 하나를 실제로 연결한 뒤) ───────────────────
curl -sD- -o/dev/null 'https://<도메인>/'                 # 200 + X-Robots-Tag: noindex, follow
curl -sD- -o/dev/null 'https://<도메인>/<남의브랜드슬러그>' # ⚠️ 404 (200 이면 F11 이 뚫린 것)
curl -sD- -o/dev/null 'https://<도메인>/<자기슬러그>'       # 307 → /
curl -sD- -o/dev/null 'https://<도메인>/my'                # 307 → klow.kr/my
curl -sD- -o/dev/null 'https://<도메인>/seed/x'            # 307 → klow.kr (게스트 쿠키 경로)
curl -sD- -o/dev/null 'https://<도메인>/handoff'           # 404
curl -sD- -o/dev/null 'https://<도메인>/sitemap.xml'       # 404
curl -sD- -o/dev/null 'https://www.<apex>/'                # 307 → apex (경로·쿼리 유지)
```

**브라우저에서 (자동 잠금이 없는 구간 — §8-2 C·D 블록)**

1. 커스텀 도메인에서 담기 → 결제 → `klow.kr/handoff?h=…` → `/checkout` 에 **카트·국가·가격이
   그대로**이고 주소창에 `?h` 가 남지 않는지(뒤로가기도)
2. 네트워크 탭에서 API 요청에 **`Cookie` 헤더가 없는지** — **Chrome·Safari 둘 다**
3. 결제 완주 → 성공 화면의 "계속 쇼핑" 이 커스텀 도메인을 가리키고, 눌러 돌아갔을 때
   **결제한 상품만** 그 도메인 카트에서 빠지는지
4. 브랜드 `/stats` 에서 **방문·담기·결제 3단계가 모두** 오르는지
   (⚠️ **결제만 0 이면 `visitorId` 이관 실패**다 — F5)

## ⚠️ Vercel 대시보드 함정

도메인을 붙인 뒤 그 도메인에 **"Redirect to primary domain" 이 켜지면 기능이 통째로 죽는다** —
브랜드 도메인이 전부 klow.kr 로 튕긴다. 우리 코드는 도메인 추가 시 redirect 를 **보내지 않으므로**
켜졌다면 사람이 대시보드에서 켠 것이다. 연결 직후 한 번 확인할 것.

## 알아 둘 것 (CS·운영)

- **반영 지연 최대 2분** — resolve 응답 캐시 60초 + 미들웨어 양성 캐시 60초. 즉 **구독 해지·도메인
  삭제 후에도 최대 2분간 계속 서빙**된다. 엣지에 흩어진 미들웨어 캐시를 밖에서 무효화할 방법이
  없어 **설계상 수용**한 값이다.
- **커스텀 도메인은 항상 비로그인 화면**이다. 로그인·내정보 진입점이 아예 렌더되지 않고, 두 주소의
  장바구니·로그인은 별개다. 릴리즈 노트·CS 가이드에 명시할 것.
- **`verifying` 은 "SSL 발급 중"이 아니라 소유권 TXT 챌린지 대기**다. 그렇게 안내하면 브랜드가
  기다리기만 하고 TXT 를 영영 안 넣는다.
- **`lastError` 는 "에러가 있다"의 신호가 아니다** — 확인할 때마다 덮어써서 정상 `pending` 에도
  문구가 들어 있다. 톤은 `status` 가 정한다.
- **7일 넘게 `pending` 이면 `error` 로 접힌다.** 그 뒤엔 자동 확인이 멈추므로 브랜드가
  "지금 확인"을 눌러야 복구된다.

## 롤백

| 되돌릴 것 | 효과 |
|---|---|
| **klow_brand** | 신규 등록만 막힌다. 기존 도메인은 계속 동작 |
| **klow_web** | 커스텀 도메인이 전부 죽는다(브랜드 도메인 = 아무 데도 안 닿음). **klow.kr 은 무사** |
| **klow_server** | 도메인 CRUD·resolve 가 사라진다 → klow_web 미들웨어가 resolve 실패로 떨어져 루트는 KLOW 홈, `/{seg}` 는 503. 먼저 klow_web 을 되돌릴 것 |
| **마이그레이션** | **되돌릴 필요 없다** — 추가 전용이라 구 코드가 그 테이블을 아예 모른다 |

⚠️ 롤백 전에 **연결된 도메인을 Vercel 프로젝트에서 떼어야** 그 주소가 KLOW 의 다른 화면을 보여주지
않는다(도메인이 붙은 채 미들웨어만 사라지면 브랜드 도메인에 klow.kr 홈이 그대로 뜬다).
