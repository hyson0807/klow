# cafe24 — 브랜드 자사몰(카페24) 연동

- **모듈 경로**: `src/modules/cafe24/`
- **관련 파일**: `cafe24.service.ts`, `cafe24.client.ts`(카페24 API 지식의 소유자),
  `cafe24-crypto.ts`(AES-256-GCM), `cafe24-oauth-cookies.ts`,
  `brand-cafe24-connect.controller.ts`(OAuth 왕복), `brand-cafe24.controller.ts`(리소스),
  검증 스키마 `common/validation/cafe24.ts`, SSRF 회귀 스펙 `__tests__/cafe24-ssrf.spec.ts`
- **모델**: `Cafe24Connection` · `Cafe24ProductMap` · `Cafe24Order` · `Cafe24OrderItem`
  + `FulfillmentRequest.source`(`enum FulfillmentSource { manual bulk_xlsx cafe24 }`)
- **프론트**: klow_brand 스튜디오 `재고 > 출고신청` 의 **자사몰 연동 모달**
  (`studio/_components/tabs/inventory/Cafe24ConnectModal.tsx` + `ui.tsx` 의 `DashedEmpty`).
  진입 버튼·`needsReauth` 배너는 `RequestsPanel.tsx`, 콜백 결과 토스트는 `studio/page.tsx`.
  ⚠️ 매핑·불러오기·전환 화면은 아직 없다
- **계획 문서**: [`plan/cafe24-fulfillment/implementation-plan.md`](../../plan/cafe24-fulfillment/implementation-plan.md)

브랜드가 자사몰을 OAuth 로 연결 → 카페24 상품을 KLOW 제품에 매핑 → 주문을 불러와 → 고른 주문을
**3PL 출고신청으로 전환**(재고 차감). **출고 이후는 [fulfillment](./fulfillment.md) 경로 그대로**이고,
이 모듈은 `Order`·`Shipment`·EFS 를 만나지 않는다.

## 현재 구현 범위 — 연동·매핑·상품목록까지. **실 API 로 검증됐다**

2-1·5-1·3-1·2-2·3-2 까지의 코드다. ✅ **2026-09-23, 테스트 몰 `simsgood1` 로 실왕복 검증** —
연결 → `GET /connection` `connected:true` → `DELETE` → `connected:false`, lazy refresh·동시 요청
경합, 그리고 **상품 40개를 실제로 읽어왔다**(검색·페이지네이션 포함).

⚠️ 아직 없는 것: **주문 불러오기 · 전환**(4-1·4-2)과 **매핑 화면**(5-2). 서버는 상품 목록까지
준비됐고, 브랜드가 쓸 화면이 아직 없다.
⚠️⚠️ **주문 상태 코드를 아직 한 번도 못 봤다** — 테스트 몰에 3개월간 주문이 0건이라 실측이
비어 있다(계획 문서 §2 B). **4-1 착수 전에 테스트 주문을 넣고 확인할 것** — 추측해서 상수로
박지 말 것.

## 엔드포인트

전부 `/v1/brand/cafe24/*`.

| 메서드 | 경로 | 가드 | 하는 일 |
|---|---|---|---|
| GET | `/connect` | `BrandGuard` | 쿼리 `mallId`·`returnTo` → 베타 한도·몰 중복 선검사 → 쿠키 4종 심고 카페24 동의 화면으로 302 |
| GET | `/callback` | **없음** | 카페24의 top-level 이동. `state` 쿠키 대조 → 토큰 교환 → 저장 → `BRAND_FRONTEND_URL{returnTo}` 로 302 |
| GET | `/connection` | `BrandGuard` | 판별 유니온 `{connected:false}` 또는 `{connected:true, mallId, scopes, connectedAt, lastSyncedAt, defaultCountryCode, needsReauth, reauthRequiredAt, daysUntilReauth}` |
| PATCH | `/connection` | `BrandGuard` | **몰 기본 배송국** 변경(`{defaultCountryCode}`). 갱신된 상태를 그대로 돌려준다. 연동이 없으면 404 |
| DELETE | `/connection` | `BrandGuard` | 연동 해제 — 토큰 폐기 + **미전환 미러 파기** |
| GET | `/catalog` | `BrandGuard` | **카페24 상품 목록**(`limit`≤100 · `skip` · `q` 부분일치) + 그 상품에 걸린 매핑 동봉 |
| GET | `/product-maps` | `BrandGuard` | 내 매핑 목록(`take`·`skip` · `total` 동봉). KLOW 제품 이름·이미지를 함께 싣는다 |
| POST | `/product-maps` | `BrandGuard` | 매핑 저장 — **보낸 줄만 반영**(`PUT` 이 아니다) |
| DELETE | `/product-maps/:id` | `BrandGuard` | 매핑 해제. 없거나 남의 것이면 **같은 404** |

콜백의 결과는 쿼리로 전달된다 — 성공 `cafe24_connected=1`, 실패 `cafe24_error=<사유>`
(`state_mismatch` · `missing_brand` · `missing_mall` · `mall_mismatch` · `mall_in_use` ·
`limit_reached` · `connect_failed` · **카페24가 준 `error` 값 그대로**). ⚠️ 마지막 항목 때문에
화면에는 **모르는 코드의 폴백 문구가 반드시 있어야 한다**(`cafe24ConnectErrorLabel`).

⚠️ `returnTo` 는 **쿼리를 가질 수 있다**(`/studio?tab=inventory&sub=requests` — 돌아올 탭을
거기 싣는다). 그래서 콜백이 `?`/`&` 를 가려 붙인다. 그냥 `?` 를 붙이면 두 번째부터가 첫
파라미터 값에 삼켜져 **화면이 결과를 영영 못 읽는다.**

## 몰 기본 배송국 (`defaultCountryCode`)

⚠️⚠️ **카페24 주문에는 국가 칸이 없다.** `FulfillmentRequestInput.countryCode` 는 ISO2 필수이고
zod `.default()` 가 금지돼 있어 **어딘가에서 국가를 정해야 하는데**, 그 자리가 이 컬럼이다.
DB 기본값 `KR` 은 1단계가 마이그레이션용으로 둔 값이지 "브랜드가 고른 값"이 아니다 —
**비-KR 몰이 이걸 안 고치면 주문이 전량 국내 배송으로 창고에 나간다.**

- 연결 **왕복에 싣지 않는다.** 쿠키가 하나 더 늘고, 나중에 바꾸려면 재연동해야 한다 →
  별도 `PATCH` 다. 몰 운영국은 바뀐다.
- 화면은 연결 **전에** 고르게 하고, 돌아온 뒤 그 값을 `PATCH` 로 올린다(`sessionStorage`
  1회 전달). ⚠️ 시크릿 모드 등에서 저장이 막혀도 **연결 자체는 진행한다** — 기본 배송국은
  나중에 고칠 수 있지만 연결은 다시 처음부터다.
- ⚠️ 변경은 **다음 전환부터** 적용된다. 이미 만들어진 `FulfillmentRequest` 는 소급해 바꾸지
  않는다 — 창고로 이미 나간 송장의 배송국이라 여기서 손대면 이력이 사실과 달라진다.
- 검증 스키마는 `common/validation/shared.ts` 의 `Iso2Code` 로, `FulfillmentRequestInput`
  과 **같은 정의**다(이 값이 그대로 저기 들어간다).

## ⚠️⚠️ `mallId` 는 SSRF 벡터다 — 방어가 두 겹이고 둘 다 필요하다

브랜드가 친 값이 그대로 `https://{mallId}.cafe24api.com` 의 **호스트가 된다.**

| 겹 | 위치 | 하는 일 |
|---|---|---|
| ① 입력 경계 | `common/validation/cafe24.ts` 의 `CAFE24_MALL_ID_REGEX` | zod 가 `^[a-z0-9][a-z0-9-]{1,30}$` 로 거른다 |
| ② 조립 경계 | `cafe24.client.ts` 의 `cafe24ApiOrigin()` | 같은 정규식을 **다시** 돌리고, `new URL()` 조립 뒤 protocol·port·userinfo·hostname 을 재확인 |

②가 따로 있는 이유는 **DB 값·쿠키가 zod 를 거치지 않고 들어오기 때문**이고, ②가 정규식을 다시
도는 이유는 **hostname 검사만으로는 `..` 이 통과하기 때문**이다(`https://...cafe24api.com`).
`__tests__/cafe24-ssrf.spec.ts` 가 두 겹을 따로 검사한다 — **tsc 도 e2e 도 이걸 못 잡는다.**

## 토큰

- access **2시간** / refresh **14일**. ⚠️⚠️ **갱신 시 refresh token 도 회전**되어 기존 것이 즉시
  무효다 — 새 값을 저장하지 못하면 다음 갱신이 **영구 실패**한다(저장은 한 UPDATE 로).
- 암호화 키는 `CAFE24_TOKEN_ENCRYPTION_KEY` **전용**이다.
  ⚠️⚠️ `META_TOKEN_ENCRYPTION_KEY` 를 재사용하지 말 것 — Meta 키를 돌리는 순간 카페24 토큰이
  전부 안 읽힌다. crypto 유틸이 세 번째 복사본인 것은 **의도된 격리**다.
- `GET /connection` 은 **access token 만료를 노출하지 않는다** — lazy refresh 가 숨기는 값이고,
  2시간짜리 만료를 화면에 띄우면 브랜드가 놀란다. 노출하는 것은 refresh 기준의 재연동 시한이다.
- ⚠️⚠️ **만료 시각 문자열에 타임존 표기가 없다**(2026-09-23 실측):
  `expires_at: "2026-09-23T19:16:43.000"` — 값은 **KST 벽시계**다. 그냥 `Date.parse` 하면
  **서버 로컬 시각**으로 읽히는데, **개발 맥북은 KST 라 맞고 운영(Railway·Docker)은 UTC 라
  9시간 늦게 읽는다** — 즉 **로컬에서는 영원히 재현되지 않는 버그**다. `parseCafe24Expiry` 가
  표기 없으면 `+09:00` 을 붙인다. 범위 검사("폴백의 2배 초과는 버린다")는 **안전망일 뿐
  주 방어가 아니다** — access 는 그게 잡아주지만 **refresh(14일+9시간)는 28일 안이라 통과한다.**
  ⚠️ 이 `+09:00` 은 개발자센터 앱 설정의 **Time zone(`Asia/Seoul`)과 묶여 있다.**
  회귀 잠금: `__tests__/cafe24-expiry.spec.ts`.
- **lazy refresh 는 `cafe24-token.ts` 가 직렬화한다**(아래 절).
- 갱신 cron `cafe24-token-refresh`(매일 KST 03:00) — refresh 만료 **3일 이내**를 미리 굴린다.
  ⚠️⚠️ 이게 없으면 **2주를 쉰 브랜드는 재연동해야 한다**(refresh 수명이 14일인데 갱신은 쓸 때만
  일어난다). 창을 하루로 줄이지 말 것 — cron 이 한 번 실패한 날 그 연동이 그대로 죽는다.

## 토큰 갱신 직렬화 (`cafe24-token.ts`)

⚠️⚠️ **갱신할 때 refresh token 도 함께 회전한다.** 두 요청이 동시에 갱신하면 한쪽이 **이미 죽은
토큰으로** 요청해 연동이 통째로 영구 실패한다. 이 파일이 존재하는 이유가 그것 하나다.

```
tx(20s):  SELECT … FOR UPDATE            ← NOWAIT 금지(두 번째 요청은 기다려야 한다)
          만료를 **다시** 확인 → 여유 있으면 그대로 반환   ← 회전 무효화를 막는 유일한 지점
          POST /api/v2/oauth/token (refresh_token)
          UPDATE … 한 문장 (access·refresh·만료 2개)
```

- **`getAccessToken(brandId)` 하나만 쓴다.** 토큰을 DB 에서 직접 읽는 두 번째 경로를 만들지 말 것 —
  그 경로는 회전을 모른 채 죽은 토큰을 쓴다. `Cafe24TokenService` 를 모듈 밖으로 export 하지 않는 이유다.
- 만료 **10분 전**부터 갱신한다(`CAFE24_REFRESH_SKEW_MS`) — 불러오기 한 번이 토큰 요청 1회를 넘지 않게.
- ⚠️ **이 트랜잭션을 비즈니스 트랜잭션과 합치지 말 것** — 락 구간에 외부 HTTP 가 들어 있어서,
  주문 불러오기 트랜잭션 안에서 갱신하면 커넥션 풀이 외부 지연만큼 묶인다. **토큰 먼저, 그다음 작업.**
- ⚠️ 실패 처리가 갈린다: **4xx = 복구 불가 → `needsReauth`**, **5xx·네트워크 = 일시 장애 → 그대로 둔다.**
  뒤집으면 카페24 쪽 장애가 멀쩡한 연동을 죽이거나, 죽은 연동이 영원히 "실패"만 띄운다.
- ✅ 2026-09-23 실측: 만료를 과거로 돌린 뒤 **동시 요청 2개 → 둘 다 성공 · 같은 토큰 · 회전 1회.**
- 회귀 잠금: `__tests__/cafe24-token.spec.ts`.


## 카페24 상품 목록 (`GET /catalog`)

매핑 화면이 고를 목록이다. ⚠️ 이름이 `products` 가 **아닌** 이유는 KLOW `Product` 와 축이
섞이기 때문이다(계획 문서 §5).

응답: `{ items: [{ productNo, productName, image, price, display, selling, variants[], maps[] }], total, limit, skip }`

- ⚠️ **매핑 상태를 같은 응답에 싣는다.** 화면이 `/catalog` 와 `/product-maps` 를 따로 불러
  맞추면 두 응답의 시점이 어긋나고(그 사이 저장이 끼면 "방금 매핑했는데 안 걸린 것처럼"
  보인다), 매핑 목록은 따로 페이지를 끊으므로 이 페이지 상품의 매핑이 저쪽 페이지에 있을 수 있다.
- ⚠️⚠️ **`maps` 를 `variantCode` 로 미리 짝지어 주지 않는다** — 옵션 없는 상품의 매핑 키를
  실제 `variant_code` 로 둘지 빈 문자열로 둘지가 **아직 미확정**이다(계획 문서 §2 F). 주문
  품목이 어느 값을 싣는지 못 봤기 때문이고, 여기서 한쪽으로 짝지으면 **그 추측이 응답 모양에
  굳는다.** 짝짓기는 화면이 한다.
- ⚠️ 카페24 호출이 **2회**(목록 + 건수)다. 건수를 빼고 `items.length === limit` 로 추정하면
  마지막 페이지가 정확히 꽉 찼을 때 빈 페이지를 한 번 더 보여주고, 화면이 "상품 N개 중 M개
  매핑"을 못 쓴다. 검색어는 **양쪽에 함께** 넘긴다(한쪽만 거르면 총계가 거짓말을 한다).
- ⚠️⚠️ **`display`/`selling` 은 카페24가 `"T"`/`"F"` 문자열로 준다.** 서비스가 불리언으로
  바꾼다 — 그대로 흘리면 `'F'` 가 truthy 라 **판매중지 상품이 판매중으로** 보인다.
- ⚠️⚠️ **클라이언트가 `fields` 파라미터를 쓰지 않는다** — 쓰면 `embed=variants` 가 **조용히
  빠진다**(실측). 매핑 키가 `(product_no, variant_code)` 라 variants 가 없으면 이 엔드포인트는
  쓸모가 없다. 큰 응답은 우리 서버와 카페24 사이에서만 오가고 DTO 는 서비스가 줄인다.
- `limit` 상한 **100 은 카페24가 정한 값**이다(101 → 422). 우리가 더 받으면 그 422 가 브랜드
  화면에 502 로 나타난다.
- 미연동이면 **404**, `needsReauth` 면 **409**(`cafe24_reauth_required`).
- 회귀 스펙: `__tests__/cafe24-catalog.spec.ts`.

## 상품 매핑 (`Cafe24ProductMap`)

카페24 **(상품번호, 옵션)** → KLOW 제품. `@@unique([brandId, cafe24ProductNo, variantCode])` 가
정본이고, 전환(4-2)이 이 표를 보고 출고신청의 제품 줄을 만든다.

- ⚠️⚠️ **`POST` 는 보낸 줄만 반영한다 — `PUT` 이 아니다.** 카페24 몰은 상품이 수백~수천 개라
  매핑 화면이 **반드시 페이지를 끊는다.** 전체 교체 규칙이면 한 페이지 저장이 **나머지
  페이지의 매핑을 전부 지운다**(계획 문서 §5-A, `BrandInventoryInput` 과 같은 규칙).
  지우는 경로는 `DELETE /product-maps/:id` 하나뿐이다.
- ⚠️⚠️ **저장은 `productId` 의 브랜드 소유권을 검사한다.** 남의 제품에 매핑하면 전환 시점에
  **다른 브랜드의 창고 재고가 차감된다** — 매핑 자체는 조용하고 사고는 한참 뒤 출고신청에서
  드러난다. 한 줄이라도 남의 것이면 **통째로 400**(부분 반영 없음).
- ⚠️ 삭제는 `where` 에 **`brandId` 를 함께** 넣는다. 없는 id 와 남의 id 를 **같은 404** 로
  합치는 것도 의도다 — 구분하면 존재 여부가 샌다.
- ⚠️ **N:1 을 허용한다**(옵션 여럿 → 같은 KLOW 제품). 그래서 전환이 `productId` 기준으로
  **수량을 합산**해야 한다 — 안 하면 `FulfillmentRequestInput.items` 의 refine 이
  "같은 제품이 두 번 담겼습니다"로 400 을 던진다(계획 문서 §5-D).
- ⚠️ **옵션 없음은 빈 문자열이다.** null 을 쓰면 Postgres 에서 NULL 끼리 같지 않아
  `@@unique` 가 중복을 못 막는다.
- ⚠️ `cafe24ProductName` 은 **표시용 스냅샷**이고 판정에 쓰지 않는다 — 매핑은 번호로 산다.
- `product` 관계는 **`onDelete: Cascade`** 다. 기본값 `Restrict` 이면 매핑이 걸린 제품 삭제가
  P2003 으로 깨진다(= 기존 기능 회귀). 매핑은 `productId` 없이는 의미가 없다.
- 회귀 스펙: `__tests__/cafe24-product-map.spec.ts`.

## 쿼터 (429)

카페24는 **초당 2회 누수 버킷(용량 40)** 이고 응답에 **`x-api-call-limit: 4/40`**(소문자,
`사용/용량`)을 싣는다. `cafe24.client.ts` 는 429 를 **502 로 접지 않고** `Cafe24RateLimitError`
(HTTP 429)로 그대로 흘린다 — ⚠️ 502 면 사용자는 "실패"로 읽고 **더 누르는데**, 그게 정확히
상황을 악화시킨다.

⚠️ **`Retry-After` 는 미검증이다** — 429 를 실제로 맞아 본 적이 없다. 헤더가 없으면 초를 빼고
"잠시 후 다시" 문구만 나간다(안전한 폴백). 실제로 관측하면 여기를 실측으로 바꿀 것.

## ⚠️ 한 몰은 한 브랜드에만 — Instagram 의 `deleteMany` 를 복제하지 않는다

`instagram.service.ts` 는 같은 IG 계정이 다른 브랜드에 물려 있으면 이전 연동을 지운다. 근거는
*"그 계정으로 OAuth 로그인했다는 것 자체가 통제권 증명"* 이다. **자사몰은 법인 자산이라 그
논거가 성립하지 않고**, 한 몰이 두 브랜드에 물리는 것은 사고 신호다 → **409 + 로그**.

## ⚠️ 베타 한도 5개 몰

퍼블릭앱 심사 전에는 최대 5개 쇼핑몰에만 설치된다. `CAFE24_MAX_BETA_CONNECTIONS` 가 연결
시점에 막는다 — 안 막으면 6번째 브랜드의 실패가 **카페24 쪽 화면**에서 나서 원인을 아무도 모른다.
검사는 `/connect`(선검사)와 `saveConnection()`(최종) **두 번** 돈다. 동의 화면에 머무는 사이
다른 브랜드가 먼저 연결할 수 있기 때문이다.

## ⚠️ v1 은 카페24 앱스토어(iframe) 진입을 지원하지 않는다

퍼블릭앱의 기본 진입은 몰 관리자 화면 안의 **iframe** 인데, `klow_brand_sid` 는 운영에서
`sameSite:'none'` 이라 3rd-party 차단에 걸려 전송되지 않을 수 있다 — 즉 **로그인 상태가 아니다.**
진입은 KLOW 스튜디오에서만 시작한다. 계획 문서 §7 R1.

## env

`CAFE24_CLIENT_ID` · `CAFE24_CLIENT_SECRET` · `CAFE24_BRAND_CALLBACK_URL` ·
`CAFE24_TOKEN_ENCRYPTION_KEY`(base64 32바이트) · (선택) `CAFE24_API_VERSION`.
정본은 `klow_server/.env.example`.
⚠️ 개발자센터의 Redirect URI 에 `CAFE24_BRAND_CALLBACK_URL` 과 **글자 그대로 같은 값**이
등록돼 있어야 한다.

⚠️⚠️ **`http://localhost:...` 은 Redirect URI 로 등록할 수 없다**(2026-09-23 실측) — 개발자센터가
HTTPS 만 받고 IP 주소도 거부한다. **이 레포의 다른 연동(`GOOGLE_*`·`META_*`)은 localhost 를
등록해 두고 로컬에서 왕복을 돌리므로, 그 관례를 여기에 복사하면 막힌다.** 로컬에서 OAuth 를
돌리려면 **HTTPS 터널**(cloudflared/ngrok)이 필요하고, 터널 주소가 바뀔 때마다 개발자센터
목록(최대 10줄)과 이 env 를 **함께** 고쳐야 한다.

⚠️ 개발자센터 앱 설정의 **Time zone(`Asia/Seoul`)이 토큰 만료 시각과 주문 조회 날짜 축 둘 다**에
걸린다. 주문 날짜를 KST 로 맞추는 쪽을 택했으므로, 만료 문자열의 타임존 문제는
`parseCafe24Expiry` 한 곳에서 흡수한다.
