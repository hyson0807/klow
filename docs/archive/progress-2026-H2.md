# 진행표 아카이브 — 2026 H2

> 📦 **회수된 상태 행과 인계 메모다.** 현행 상태의 정본은 [`../PROGRESS.md`](../PROGRESS.md) 하나다.
> ⚠️ 여기 있는 것은 **그때의 기록**이고 현행 사양이 아니다 — 사양은 트랙 문서와 `decisions/`·`server/modules/` 가 갖는다.

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
