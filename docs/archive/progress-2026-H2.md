# 진행표 아카이브 — 2026 H2

> 📦 **회수된 상태 행과 인계 메모다.** 현행 상태의 정본은 [`../PROGRESS.md`](../PROGRESS.md) 하나다.
> ⚠️ 여기 있는 것은 **그때의 기록**이고 현행 사양이 아니다 — 사양은 트랙 문서와 `decisions/`·`server/modules/` 가 갖는다.

---

### 3pl-fulfillment · cafe24-fulfillment — 완료 단계 18건 (staging 배포 완료 · 운영 남음)

**회수 사유 (2026-09-28)**: 두 트랙이 **staging 에 배포 완료**되어 완료 18행이 `§7` 에서 할 일과
섞여 읽히고 있었다. 트랙은 살아 있다 — 남은 단계(운영 배포 · 실브랜드 시범 · 심사 제출)는 `§7` 에 있다.

⚠️ **운영은 아직 미배포다.** 그래서 `운영 배포` 칸이 전부 `✗` 인 채로 내려왔다.

**2026-09-28 실측** (읽기 전용 HTTP + 마이그레이션 수)

| 대상 | 3PL `/v1/brand/inventory` | 카페24 `/v1/brand/cafe24/callback` | 마이그레이션 |
|---|---|---|---|
| `api-staging.klow.kr` | **401** (라우트 있음 · 가드가 막음) | **302** (머지 전 실측은 404였다) | — |
| `api.klow.kr` (운영) | **404** (라우트 없음) | **404** | **164개** (dev 167 — 3개 미적용) |

| # | 트랙 | 단계 | 상태 | 운영 배포 | 날짜 | 커밋 (server/admin/brand/web/docs) |
|---|---|---|---|---|---|---|
| 1 | 3pl-fulfillment | 1. 스튜디오 탭 스왑 | 완료 | ✗ | 2026-09-22 | - / - / `8677002` / - / (이 커밋) |
| 2 | 3pl-fulfillment | 2. 스키마 + 마이그레이션 | 완료 | ✗ | 2026-09-22 | `29511f2` / - / - / - / (이 커밋) |
| 3 | 3pl-fulfillment | 3. 서버 API (재고 + 출고신청) | 완료 | ✗ | 2026-09-22 | `70cc676` / - / - / - / (이 커밋) |
| 4 | 3pl-fulfillment | 4. 엑셀 (브랜드 업로드 · 콜로세움 내보내기) | 완료 | ✗ | 2026-09-22 | `43400e5`·`28a2f6f` / - / - / - / (이 커밋) |
| 5 | 3pl-fulfillment | 5. 어드민 화면 | 완료 | ✗ | 2026-09-22 | - / `78e3ef3` / - / - / (이 커밋) |
| 6 | 3pl-fulfillment | 6. 브랜드 화면 | 완료 | ✗ | 2026-09-22 | - / - / `6fb35d8` / - / (이 커밋) |
| 7 | cafe24-fulfillment | 0. 카페24 개발자센터 앱 생성 (사용자 작업) | 완료 | — | 2026-09-23 | - / - / - / - / `d75a3cc` |
| 8 | cafe24-fulfillment | 1. 스키마 + 마이그레이션 | 완료 | ✗ | 2026-09-23 | `4c9a912` / - / - / - / (이 커밋) |
| 9 | cafe24-fulfillment | 2-1. 서버 — OAuth 왕복 | 완료 | ✗ | 2026-09-23 | `0c28ea8` / - / - / - / (이 커밋) |
| 10 | cafe24-fulfillment | 2-2. 서버 — OAuth 실왕복 + 토큰 갱신 | 완료 | ✗ | 2026-09-23 | `1addc5a` / - / - / - / `8ce4f03` |
| 11 | cafe24-fulfillment | 3-1. 서버 — 매핑 CRUD | 완료 | ✗ | 2026-09-23 | `1bb91c4` / - / - / - / `0735642` |
| 12 | cafe24-fulfillment | 3-2. 서버 — 카페24 상품 목록 (`/catalog`) | 완료 | ✗ | 2026-09-23 | `d7b9a55` / - / - / - / `81b8054` |
| 13 | cafe24-fulfillment | 4-0. 출고신청 목록 기간 필터 (R3) | 완료 | ✗ | 2026-09-23 | `99fa1e4` / - / `15f17ef` / - / `af88cb1` |
| 14 | cafe24-fulfillment | 5-1. 브랜드 화면 — 연동 | 완료 | ✗ | 2026-09-23 | `73c578a` / - / `0ba23e6` / - / `0735642` |
| 15 | cafe24-fulfillment | 4-1. 서버 — 주문 불러오기 | 완료 | ✗ | 2026-09-23 | `71bccc0` / - / - / - / (이 커밋) |
| 16 | cafe24-fulfillment | 4-2. 서버 — 전환 (재고 차감 + 역기록) | 완료 | ✗ | 2026-09-23 | `71bccc0` / - / - / - / (이 커밋) |
| 17 | cafe24-fulfillment | 5-2. 브랜드 화면 — 매핑 | 완료 | ✗ | 2026-09-23 | - / - / `19e690c` / - / (이 커밋) |
| 18 | cafe24-fulfillment | 5-3. 브랜드 화면 — 주문 목록 + 전환 | 완료 | ✗ | 2026-09-23 | - / - / `19e690c` / - / (이 커밋) |

#### 함께 내려온 인계 메모 6건

⚠️⚠️ **아래 메모는 전부 staging 머지 *이전* 에 쓰였다.** "세 레포 모두 `feat/3pl-fulfillment`
브랜치이고 `staging` 미머지다" 같은 문장은 **2026-09-28 에 이미 거짓**이다(머지·배포됨).
브랜치·배포 상태는 믿지 말고, **함정과 미확인 항목만** 읽을 것.

### cafe24-fulfillment 4-1 · 4-2 · 5-2 · 5-3단계 — 주문 축 전체 (완료 · 한 세션에 넷)

- **한 것**: 불러오기(`POST /orders/import` · `GET /orders` · 미러 보존 cron) · 전환
  (`convert/preview` · `convert` · 품목 제외 토글) · 브랜드 화면 2개(`Cafe24MappingModal`
  매핑, `Cafe24OrdersModal` 불러오기·전환) + 출고신청 목록 **유입 배지**(`source`).
  라우트 **370 → 375** · cron **11 → 12** · **스키마 변경 0**
- **검증**: typecheck(2개) · jest **1310 pass**(신규 56) · e2e 3 pass(cron **12**) · 부팅 375 ·
  eslint · klow_brand `npm run build` · **실 몰 왕복 전 구간** — 불러오기 멱등(재수집이
  `updated` 로 잡히고 미러가 안 늘어남) · 쿨다운 429 · 전환(재고 10→9 · `source=cafe24` ·
  미러 PII 파기 · 재전환 `already_converted` 차단 · **재수집이 PII 를 되살리지 않음**)
- ⚠️ **사용자 지시로 한 세션에 네 단계를 했다**(`§1` 의 "한 세션 한 단계"에 대한 예외).
  커밋은 서버(`71bccc0`)와 브랜드(`19e690c`) 둘로 끊었다
- ⚠️⚠️ **브랜드 화면 2개를 브라우저로 못 봤다.** :3002 가 사용자 dev 서버이고 스타일이 빠진
  채 렌더돼(내 변경 전부터) 눈으로 확인할 수 없었다. **6단계 배포 확인 때 먼저 볼 것**
- ⚠️ **포트 4000 의 dev 서버를 한 번 죽였다**(라우트 수 확인 뒤 `pkill -f "nest start"`).
  사용자 서버였다면 다시 띄워야 한다
- ⚠️⚠️ **§2 B 를 실측으로 채웠다 — `status_code` 는 상태가 바뀌어도 `"N1"` 그대로다.**
  정본은 품목 `order_status`, 주문 최상위에는 상태 칸이 `paid`/`canceled` 뿐이다.
  ⚠️ 관측 코드가 둘뿐이라 **상태 필터도 한국어 라벨도 만들지 않았다**
- ⚠️ **명세에 없던 결정 둘** — ① **배송지가 여러 개인 주문은 미러를 만들지 않는다**
  (`skipReasons.multi_address` 로 보고). ② 미러 보존 축을 `importedAt` 이 아니라 **`updatedAt`**
  으로 잡았다(매일 재수집하는 브랜드의 주문이 90일째 조용히 사라지지 않게)
- ⚠️ **`FulfillmentService` 를 export 했다**(`createManyInTx`) — 재고를 건드리는 두 번째 경로를
  만들지 않기 위해서다. 방향은 **cafe24 → fulfillment** 뿐이고 반대는 금지다
- **문서를 고친 것**: `server/modules/cafe24.md`(엔드포인트 5행 + 불러오기·전환 절 신설 ·
  구현 범위 재작성) · `server/modules/fulfillment.md`(유입 경로 + `createManyInTx` 절),
  `decisions/shipping-seeding.md#2026-09-23-2` + 색인 2곳, `CLAUDE.md`(라우트 365→375 ·
  cron 10→12)
- **다음 단계가 알 것**: **6단계(운영 배포)** 다. push 하지 않았고 브랜치는 두 레포 다
  `feat/3pl-fulfillment`. 프로브가 만든 세션·매핑·출고신청은 전부 지웠다
- ⚠️⚠️ **테스트 몰 연결은 세션 끝에 해제했다**(2026-09-23, 사용자 결정) — 카페24 쪽
  `simsgood1` 에서 앱을 삭제했고 우리 쪽도 `disconnect()` 를 돌렸다(연동 1 · 미러 1 · 품목 1 →
  전부 0). **dev 에서 카페24 API 를 다시 부르려면 재연동이 필요하다**: HTTPS 터널을 띄우고 →
  개발자센터 Redirect URI 에 그 주소를 추가하고 → 카페24 관리자 로그인 + 동의 1회.
  ⚠️ `http://localhost` 는 등록할 수 없다(HTTPS 전용 · IP 거부)
- ⚠️ **세션 끝에 스토어 리스팅 텍스트를 채워 저장했다**(개발자센터 STEP 03). 남은 것은
  이미지 4종이고 배포 뒤에야 만든다. **앱 이름 불일치는 의식적으로 남겨 둔 것**이다 — 위 §0 참고
- ⚠️⚠️ **"해외배송"이 이 트랙의 기본 경로가 아니다**(사용자 정정). 국내 출고 대행이 정상이고
  해외는 부가다. 계획 문서·결정 로그의 서술을 고칠지는 **정해지지 않았다**

### cafe24-fulfillment 3-2단계 — 카페24 상품 목록 (완료)

- **한 것**: `GET /v1/brand/cafe24/catalog`(`limit`≤100 · `skip` · `q` 부분일치) — 상품 목록 +
  **그 상품에 걸린 매핑 동봉**. 클라이언트에 `listProducts`/`countProducts`/`adminGet` 추가.
  라우트 **369 → 370** · cron 11 불변 · 스키마 변경 0
- **검증**: typecheck(2개) · jest **1254 pass**(신규 11) · e2e 3 pass · 부팅 370 · eslint ·
  **실 몰 왕복**(상품 40건 · `q=바디` total 2 · skip 39/40 경계 · limit 101·0 → 400 ·
  무세션 401 · 미연동 404 · 매핑 저장 후 그 행에 `maps` 실림)
- ⚠️⚠️ **실측으로 잡은 함정 둘**
  1. **`fields` 를 쓰면 `embed=variants` 가 조용히 빠진다** — 페이로드를 줄이려다 매핑 키를
     통째로 잃는다. 그래서 클라이언트가 `fields` 를 쓰지 않는다
  2. **`display`/`selling` 이 `"T"`/`"F"` 문자열** — 그대로 흘리면 `'F'` 가 truthy 라
     판매중지가 판매중으로 보인다. 서비스가 불리언으로 바꾼다
- ⚠️⚠️ **미확정을 하나 새로 열었다 — §2 F(옵션 없는 상품의 매핑 키).** 옵션이 없어도
  `variants` 가 1줄 오고 `variant_code` 가 실재하는데(`options: null`), 스키마 주석은
  "옵션 없으면 빈 문자열"이다. **주문 품목이 어느 값을 싣는지 못 봤으므로**(주문 0건) 짝짓기를
  하지 않고 `maps` 를 **상품 단위로 그대로** 실어 보낸다. **5-2·4-2 가 이걸 먼저 정해야 한다**
- ⚠️ 카페24 호출이 **2회**(목록 + 건수)다. 건수를 빼면 마지막 페이지가 꽉 찼을 때 빈 페이지를
  한 번 더 보여주고 "N개 중 M개 매핑"을 못 쓴다. 검색어는 **양쪽에 함께** 넘긴다
- ⚠️ **연결은 살려 뒀다**(테스트 몰 `simsgood1`) — 다음 세션이 터널·동의 없이 API 를 부를 수
  있다. 프로브 매핑·세션은 지웠고 `.env` 는 운영 주소로 되돌렸다
- **문서를 고친 것**: 트랙 문서 §2 **F 행 신설** + §2-B 상품 API 실측 절,
  `server/modules/cafe24.md`(엔드포인트 1행 · `/catalog` 절 · 구현 범위). `decisions/` 는
  안 건드렸다 — 2-2 항목이 이 트랙의 함정을 이미 담고 있고, 새 정책이 아니다
- **다음 단계가 알 것**: **4-1 은 테스트 주문 1건이 있어야 시작한다**(§2 B·F 둘 다 그것 없이는
  못 정한다). push 하지 않았고 브랜치는 `feat/3pl-fulfillment`

### cafe24-fulfillment 0 · 2-2단계 — 앱 생성 · OAuth 실왕복 (완료)

- **한 것**: (0) 개발자센터 앱 `KLOW 해외배송 출고연동` — 실측은 트랙 문서 **§2-A**.
  (2-2) `cafe24-token.ts` 직렬화 lazy refresh + `cafe24-errors.ts` + 429 분기 +
  `cafe24-token-refresh.cron.ts`. **cron 10 → 11 · 라우트 369 불변 · 스키마 변경 0**
- **검증**: typecheck(2개) · jest **1243 pass**(신규 21) · e2e 3 pass(cron **11**) · 부팅 369 ·
  **실 OAuth 왕복**(연결 → `connected:true` → `DELETE` → `connected:false`) · 만료를 과거로 돌린
  뒤 **동시 요청 2개 → 둘 다 성공·같은 토큰·회전 1회** · 주문 API HTTP 200
- ⚠️⚠️ **운영에서만 터질 버그를 하나 잡았다** — 만료 문자열에 **타임존이 없고 값이 KST** 라,
  UTC 서버(Railway)가 9시간 늦게 읽는다. 개발 맥북은 로컬 TZ 가 KST 라 **영원히 재현 안 된다.**
  `parseCafe24Expiry` 가 `+09:00` 을 붙이고 스펙이 **절대 인스턴트**로 잠갔다. 자세히는
  `decisions/shipping-seeding.md#2026-09-23`
- ⚠️⚠️ **§2 B(주문 상태 코드)·§4-D(품목 필드)를 못 봤다** — 테스트 몰 `simsgood1` 에 3개월간
  주문이 **0건**이다. **4-1 착수 전에 테스트 주문을 넣고 실측할 것. 추측 금지.**
- ⚠️ **Redirect URI 에 localhost 를 못 쓴다**(HTTPS 전용·IP 거부) — 로컬 왕복은 cloudflared
  터널로 했다. 이 세션의 터널 주소는 **이미 죽었다**. 다음 세션은 새 터널을 띄워 개발자센터
  목록에 한 줄 추가하고 `CAFE24_BRAND_CALLBACK_URL` 을 맞춘다(`.env` 는 운영 주소로 되돌려 뒀다)
- ⚠️ **`Retry-After` 미검증** — 429 를 실제로 맞아 본 적이 없다. 쿼터 헤더는
  `x-api-call-limit: 4/40` 로 관측됐다
- ⚠️ **연결은 해제된 상태로 끝났다**(DELETE 검증 때문). 3-2 에서 API 를 부르려면 재연동이 필요하고,
  그건 카페24 관리자 로그인 + 동의 1회다
- **문서를 고친 것**: 트랙 문서 §2(A·C·D 실측 · §2-A·§2-B 신설) · 0단계 · R1,
  `server/modules/cafe24.md`(토큰 절 재작성 · 직렬화 절 · 쿼터 절), `.env.example`,
  `decisions/shipping-seeding.md` + 색인 2곳
- **다음 단계가 알 것**: 3-2 다. push 하지 않았고 브랜치는 `feat/3pl-fulfillment`

### cafe24-fulfillment 5-1 · 3-1단계 — 브랜드 연동 화면 · 매핑 CRUD (완료 · 한 세션에 둘)

- **한 것**: (5-1) `PATCH /v1/brand/cafe24/connection {defaultCountryCode}` + `GET` 응답에 그 값 ·
  브랜드 `Cafe24ConnectModal`(3상태) · `needsReauth` 배너 · 툴바 2×2 · 복귀 토스트.
  (3-1) `GET|POST /product-maps` · `DELETE /product-maps/:id`. 라우트 **365 → 366 → 369**
- **검증**: typecheck(2개) · jest **1222 pass**(신규 22) · e2e 3 pass(cron 10 불변) · 부팅 369 ·
  klow_brand build · **실 DB 왕복** — PATCH `us`→`US` 반영/400/401/404, `/connect` 가 카페24
  도메인으로 302, 매핑 10스텝(보낸 줄만·소유권 400·중복 400·남의 매핑 404 + 실제 생존)
- ⚠️ **사용자 지시로 한 세션에 두 단계를 했다**(`§1` 의 "한 세션 한 단계"에 대한 예외).
  두 단계가 같은 컨트롤러를 건드리므로 커밋은 따로 끊었다
- ⚠️ **명세보다 하나 더 했다 — 콜백 리다이렉트의 쿼리 join(`?`/`&`)**. `returnTo` 가
  `/studio?tab=inventory&sub=requests` 라 그냥 `?` 를 붙이면 결과가 첫 파라미터 값에 삼켜져
  **화면이 영영 못 읽는다.** 5-1 의 복귀 경로가 그 위에 서 있다
- ⚠️ `Iso2Code` 를 `validation/shared.ts` 로 올렸다(fulfillment + cafe24). 몰 기본 배송국이
  **그대로** `FulfillmentRequestInput.countryCode` 가 되므로 두 곳이 한 정의를 봐야 한다
- ⚠️ 기본 배송국은 연결 **전에** 고르고 **후에** PATCH 로 올린다(`sessionStorage` 1회 전달).
  막혀도 연결은 진행한다 — 국가는 나중에 고치지만 연결은 다시 처음부터다
- ⚠️ **매핑 화면은 만들지 않았다**(5-2). `/catalog`(3-2·자격증명 필요)가 없어 브랜드가 상품
  번호를 알아낼 경로가 없다 — 3-1 은 지금 **화면 없는 API** 다
- ⚠️⚠️ **OAuth 는 여전히 한 번도 실행되지 않았다.** 연동 화면이 "연결됨"을 그릴 수는 있어도
  그 경로가 통과된 적은 없다(실 DB 검증은 연결 행을 직접 심어서 했고, 그 행은 지웠다)
- **문서를 고친 것**: `server/modules/cafe24.md`(엔드포인트 표 3행 · '몰 기본 배송국' 절 ·
  '상품 매핑' 절 · 프론트 행 · 구현 범위 경고). `decisions/` 는 안 건드렸다 — 계획된 단계의
  실행이고 규칙은 모듈 문서가 갖는다
- **다음 단계가 알 것**: **0단계(사용자 작업)가 유일한 다음 관문**이다. push 하지 않았고
  브랜치는 두 레포 다 `feat/3pl-fulfillment`

### cafe24-fulfillment 4-0단계 — 출고신청 목록 기간 필터 (완료)

- **한 것**: `BrandFulfillmentListQuery`(= 공용 + `since`/`until`, KST 'YYYYMMDD') · 응답에
  `counts`(status groupBy) · `listInventory` 에 제품별 `outboundPending` · `KstYmd` 를
  `validation/shared.ts` 로 승격. 브랜드는 기간 pill → 서버 파라미터, 칩 건수는 서버값,
  `StockPanel` 의 200건 재조회 제거. **라우트 365 불변 · cron 10 불변 · 스키마 변경 0**
- **검증**: typecheck(2개) · `npx jest src/modules src/common/__tests__` **1212 pass**(신규 12) ·
  e2e 3 pass · 부팅 365 · klow_brand build · **실 DB 5건으로 `take=1` 왕복** —
  `since` 가 5→3 으로 좁히고 `counts` 가 take=1/200 에서 동일, `outboundPending` 이 원장 합계와 일치
- ⚠️⚠️ **배포는 klow_server → klow_brand.** 뒤집으면 400 이 아니라 **조용한 strip** 이다
- ⚠️ **명세보다 하나 더 했다** — `listInventory` 의 `outboundPending`. 계획의 "StockPanel 도"가
  가리킨 것은 기간이 아니라 **같은 200건 상한**이었다(그 화면엔 기간 축이 없다). 어드민 재고
  응답에도 additive 로 실린다 — 어드민은 아직 읽지 않는다(배포 불필요)
- ⚠️ **상한을 없애지 않고 보이게 했다** — `total > items.length` 면 "최근 200건만 표시했어요".
  페이지네이션은 안 넣었다(이 화면은 무한 스크롤도 페이저도 없다). 넣을 때 `skip` 은 이미 있다
- ⚠️ **상태는 서버로 보내지 않는다** — 보내면 `counts` 모집단이 같이 좁아져 칩이 서로를 0 으로
  만든다. 어드민에 기간을 붙이려면 **세 곳**(`AdminFulfillmentListQuery`·`AdminFulfillmentExportInput`·
  `adminWhere`)을 함께 고칠 것. 지금은 손대지 않았다
- **문서를 고친 것**: `server/modules/fulfillment.md`(기간 축 절 + `outboundPending` 절 신설,
  화면 쪽 규칙의 "클라에서 건다" 문단 교체, 어드민 표에 "기간 축 없음" 근거). `decisions/` 는
  **안 건드렸다** — 새 정책이 아니라 계획된 부채 상환이고, 규칙은 모듈 문서가 갖는다
- **다음 단계가 알 것**: 5-1 이다. push 하지 않았고 브랜치는 두 레포 다 `feat/3pl-fulfillment`

### 3pl-fulfillment 3~6단계 — 서버 API · 엑셀 · 어드민 화면 · 브랜드 화면 (완료)

- **한 것**: 라우트 **349 → 361**(어드민 재고 2 · 어드민 출고신청 3 · 브랜드 7),
  `fulfillment-xlsx.ts`(KLOW 양식 왕복 + 콜로세움 17열), 어드민 브랜드 상세 `재고` 탭 +
  `/fulfillment` 목록, 브랜드 스튜디오 `재고` 탭 실데이터 + `출고신청` 서브탭
- **검증**: typecheck(tsconfig 2개) · `npx jest src/modules` **1039 pass**(신규 14) ·
  `test:e2e` 3 pass(cron 10 불변) · 부팅 라우트 361 · admin/brand `npm run build`
  · **실 DB 스모크 20스텝**(차감·반납·부족 400·`exported` 후 409·재다운로드 `exportedAt` 불변)
- **문서를 고친 것**: `server/modules/fulfillment.md` 신규 + `server/README.md`(34→35 모듈),
  `decisions/shipping-seeding.md` 2026-09-22 항목 + 색인 2곳, `CLAUDE.md` 라우트 349→361 ·
  Where Things Live 행 · 어드민 페이지 목록
- ⚠️ **명세와 다른 판단 하나** — 2단계 메모가 "`AdminAuthModule` import 를 추가해야 한다"고
  적었는데 **불필요했다**(그 모듈이 `@Global` 이다). 모듈 주석에 근거를 남겼다
- ⚠️⚠️ **`shipping/xlsx-grid.ts` 리더를 고쳤다** — `t="str"` 분기가 없어 SheetJS 가 쓴 문자열
  셀이 숫자 추론으로 흘러 우편번호 `06234` 가 `6234` 가 됐다. **이 리더는 배송비용·비교요율·
  신고가 탭 공용**이라 건드리면 `npx jest src/modules` 전체를 돌릴 것
- ⚠️ **남은 목업 하나** — 브랜드 출고신청 서브탭 상단 '기간별 출고량'(`OutboundVolumeMock.tsx`).
  `예시` 칩과 상수를 **함께** 지울 것
- ⚠️ **미확인 3건**(콜로세움 확인 대기, 트랙 문서 §2): 해외 주소 칸 · `상품금액` 용도 ·
  송장번호 회신 방식. 해외 출고를 실제로 쓰기 전에 §2 A 를 반드시 확인한다
- **다음 단계가 알 것**: 마이그레이션이 **`ep-floral-sun` 에만** 있다. 세 레포 모두
  `feat/3pl-fulfillment` 브랜치이고 `staging` 미머지다. push 하지 않았다

---

### storefront-sales-analytics — 운영 배포 (완료 · 퇴출)

| 트랙 | 단계 | 완료 | 운영 배포 | 커밋 |
|---|---|---|---|---|
| storefront-sales-analytics | 운영 배포 | 2026-09-22 (사용자 확인) | ✓ | ⚠️ 체계 도입 전 배포라 해시 미기록 |

⚠️ `§7` 은 "커밋 해시 없이 `완료` 를 쓸 수 없다"가 규칙이다. 이 행은 **진행표가 생기기 전에 배포된
건**이라 예외로 사유를 적어 남겼다. 이후 완료되는 단계에는 해시를 채운다.

문서는 [`storefront-sales-analytics.md`](./storefront-sales-analytics.md), 현행 정본은
[`../server/modules/storefront-stats.md`](../server/modules/storefront-stats.md).

**회수 사유**: 2026-09-28 에 `PROGRESS.md` 가 743줄이 되어 `§7` 예산(40행 / 600줄)을 넘었다.
트랙 3개(`brand-menu-schema`·`storefront-menu-pc`·`b2b-wholesale`)가 표에 13행을 더한 세션이다.

---

### 체계 — 진행 관리 체계 전환 (1~3단계 완료 · 다음 단계 없음)

전환 자체를 자기 진행표 위에서 굴렸다. 산출물은 셋이고, 그 이후의 운영 규칙은 `§1` 절차 7번과
`README.md` 규칙 절에 상시 규칙으로 들어가 있다.

| 단계 | 산출물 |
|---|---|
| 1. 진행표 신설 | 이 문서 · `README.md` 문서 지도 · `CLAUDE.md` 진입 두 줄 |
| 2. Key Facts → decisions 이관 | [`decisions/`](../decisions/) 9개 주제 파일 + 색인 · `CLAUDE.md` 427KB → 53KB |
| 3. 상태 장치 정리 | 최상위 md 2개 · `reference/`·`plan/<트랙>/`·`archive/` · [`tools/linkcheck.py`](../tools/linkcheck.py) |

⚠️ **되살아나는 부채는 하나 — `CLAUDE.md` 가 다시 부푸는 것.** 새 결정의 본문은 `decisions/` 에
쓰고 `CLAUDE.md` 에는 **색인 한 줄**만 넣는다. 본문을 다시 `CLAUDE.md` 에 쓰기 시작하면 2단계가
없앤 402KB 자동 로드가 그대로 돌아온다.

### 체계 2단계 — Key Facts → decisions 이관 (완료 · 체계 트랙 1~3단계 메모를 여기 합쳤다)

- **한 것**: `CLAUDE.md` 의 날짜 붙은 결정 71건(383,099 B)을 `docs/decisions/` 9개 주제 파일로
  **스크립트 이관**. `CLAUDE.md` **426,668 → 52,974 B**(상시 사실 17개 + 색인 71줄 + 규칙).
  `decisions/README.md` 표 71행, `docs/README.md` 문서 지도에 등재
- **무결성 검증**(스크립트, scratchpad): **(제목,본문) multiset 완전 일치** · 본문 바이트
  377,201 B 양쪽 동일 · 상시 사실 17개 원문 그대로 · 색인 71 ↔ 앵커 71 · 깨진 앵커 0
- ⚠️ **본문의 상대 링크 82개를 재작성했다** — 원문은 워크스페이스 루트(`./docs/...`) 기준이라
  `docs/decisions/` 로 내려가며 전부 깨졌다(linkcheck 73건). href 만 `../server/...` 로 바꾸고
  **링크 텍스트의 루트 기준 경로 표기는 그대로 뒀다**(그게 실제 경로다)
- ⚠️ **명세와 다르게 한 것 하나** — 색인에 `⚠️⚠️` 등급 마커를 **넣지 않았다.** 실측에서 71건 중
  **55건**이 본문에 `⚠️⚠️` 를 갖고 있어 마커가 거의 모든 줄에 붙는다(신호가 아니라 잡음). 대신
  그 사실과 "제목만 보고 넘기지 말 것"을 색인 머리말에 적었다
- **`linkcheck.py` 에 `#앵커` 검사를 추가**했다 — 명시 `<a id>` 를 가진 파일만 본다(자동 슬러그는
  뷰어마다 규칙이 달라 오탐). 일부러 깨뜨려 잡히는 것까지 확인했다.
  **현재 기준선: 79파일 · 깨진 링크 0 · 깨진 앵커 0**
- ⚠️ 문서를 옮길 때 **링크 텍스트도 같이 봐야 한다** — href 만 고치면 표시 문자열이 옛 위치를
  말한다(3단계에서 49곳 + 26곳을 밟았다). 자동 수정은 텍스트가 API 라벨인 경우를 오검출한다
- ⚠️ `reference/payment-integration.md` **본문 전체가 아직 pre-launch 시점 서술**이다(머리말만 3단계에서
  경고 블록으로 고쳤다). 별도 감사가 필요하고 어느 트랙에도 안 올라가 있다
- **다음 단계가 알 것**: 새 결정은 `decisions/<주제>.md` 맨 뒤에 `<a id="<날짜>"></a>` + `## 제목 (날짜)`
  로 더하고 **`decisions/README.md` 와 `CLAUDE.md` 색인 두 곳**에 한 줄씩 넣는다(`§1` 절차 7번).
  본문을 `CLAUDE.md` 에 쓰면 이 단계가 없앤 402KB 자동 로드가 그대로 돌아온다

### cafe24-fulfillment 2-1단계 — 서버 OAuth 왕복 (완료)

- **한 것**: `src/modules/cafe24/` 7파일(crypto·oauth-cookies·client·service·컨트롤러 2·module)
  + `common/validation/cafe24.ts` + 배럴 + `origin-exempt` 등록 + env 5개(`.env.example` 포함).
  라우트 **361 → 365**(`/connect`·`/callback`·`GET|DELETE /connection`)
- **검증**: typecheck(tsconfig 2개) · `test:e2e` 3 pass(cron **10 불변**) · 부팅 라우트 365 실측 ·
  `npx jest src/modules/cafe24 src/common/__tests__` **160 pass**(신규 48) ·
  authorize URL 눈 검증(호스트 `klowshop.cafe24api.com` · `/api/v2/oauth/authorize` ·
  `redirect_uri`·`scope=mall.read_order,mall.read_product`·`state` 확인)
- ⚠️⚠️ **OAuth 는 한 번도 실행되지 않았다.** 토큰 교환 URL·응답 모양·만료 시각 형식은 전부
  2-2 의 실왕복에서 처음 확인된다. "동작한다"고 적지 말 것
- ⚠️ **SSRF 가드는 두 겹이고 스펙이 둘을 따로 본다** — zod(입력) + `cafe24ApiOrigin()`(조립).
  ②가 정규식을 다시 도는 이유는 `..` 이 hostname 검사만으로는 통과하기 때문이다
  (`https://...cafe24api.com`). 한 겹만 남기지 말 것
- ⚠️ **명세와 다르게 한 것 하나** — `Cafe24Connection.defaultCountryCode` 를 **연결 시점에 받지
  않았다**(계획 §4-A 는 "연결 시점에 브랜드가 고른다"). 쿠키가 5개가 되고 UI 모양이 5-1 에서야
  정해져서다. **DB 기본값 `KR` 로 시작하고, 선택 UI 와 그 저장 엔드포인트는 5-1 에서 붙인다** —
  그전에 4-2 전환이 나가면 비-KR 몰의 주문이 전부 KR 로 채워진다
- ⚠️ **`parseCafe24Expiry` 는 폴백 우선 설계다** — 타임존 없는 만료 문자열을 그대로 믿으면 9시간이
  어긋나므로 "폴백의 2배 초과"는 버린다. 2-2 에서 실응답 형식을 확인하고 주석을 실측으로 바꿀 것
- ⚠️ 429 분기(R5)·토큰 갱신 직렬화(§6)·cron 은 **일부러 안 넣었다**(2-2). 지금은 비-200 이 전부 502 다
- **다음 단계가 알 것**: `META_*` 5개가 `.env.example` 에 여전히 **없다**(이번엔 `CAFE24_*` 만
  넣었다). push 하지 않았고 브랜치는 `feat/3pl-fulfillment` 그대로다

### cafe24-fulfillment 1단계 — 스키마 + 마이그레이션 (완료)

- **한 것**: `Cafe24Connection`·`Cafe24ProductMap`·`Cafe24Order`·`Cafe24OrderItem` 4모델 +
  `FulfillmentSource` enum + `FulfillmentRequest.source`. 마이그레이션
  `20260923052254_add_cafe24_fulfillment` (`CREATE TABLE` ×4 · `CREATE TYPE` ×1 ·
  `ADD COLUMN` ×1 · FK 7건 · **DROP 0건 · 백필 없음** → 롤링 안전)
- **검증**: `prisma validate` · `npm run typecheck`(tsconfig 2개) · `npm run test:e2e` 3 pass ·
  SQL 로 `DROP` 0건 확인 · 실 DB 에서 4테이블 + `source` 컬럼 + enum 3값(`manual|bulk_xlsx|cafe24`) 조회
- ⚠️⚠️ **FK 동작 셋이 이 마이그레이션의 핵심이다**(설계 검증에서 잡은 것) —
  `Cafe24ProductMap.productId` **Cascade**(Prisma 기본 `Restrict` 면 매핑 걸린 제품 삭제가
  P2003 으로 깨진다 = 기존 기능 회귀) · `Cafe24Order.fulfillmentRequestId` **SetNull**
  (Brand 삭제 캐스케이드 순서를 PG 가 보장하지 않아 Restrict 면 브랜드 삭제 실패) ·
  `Cafe24OrderItem.productId` **SetNull**(스냅샷 캐시)
- ⚠️ **미러 문자열 상한을 `FulfillmentRequest` 와 일부러 다르게 넓혔다** — 그쪽 상한은 추정치이고
  미러는 외부 데이터라, 긴 배송메모 한 건이 불러오기 전체를 22001 로 죽인다.
  넓게 받아 **잘라 저장하고 `truncatedFields` 에 남긴다**
- ⚠️ **주문 상태는 품목 단위**(`Cafe24OrderItem.itemStatus`) — 주문 단위로 접으면 취소된 품목까지
  전환돼 창고에서 나간다. `excluded` 는 사은품 줄을 브랜드가 끄는 스위치다
- ⚠️⚠️ **DB·git 브랜치를 새로 파지 않는다** — DB 는 `ep-floral-sun`(3pl 마이그레이션이 거기에만
  있다), git 은 `feat/3pl-fulfillment` 에 이어서 커밋. 그 브랜치가 **두 트랙을 담으므로** 카페24
  커밋 제목에 `cafe24` 를 넣는다. **push 하지 않았다**
- **다음 단계가 알 것**: 2-1 은 **자격증명 없이** 간다(끝나도 OAuth 는 한 번도 실행되지 않는다 —
  "동작한다"고 적지 않는다). cron 은 10 → 12 가 될 예정(2-2 토큰 갱신 · 4-1 미러 파기) —
  `test/app.e2e-spec.ts` 를 그때 함께 고친다
