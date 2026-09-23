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

## ⚠️ 현재 구현 범위 — 연동만 있고 **OAuth 가 실행된 적이 없다**

2-1·5-1·3-1 까지의 코드다. 카페24 자격증명 없이 썼으므로 **토큰 교환은 한 번도 실행되지 않았다**
(2-2 에서 실왕복으로 확인한다). ⚠️ 화면이 "연결됨"을 그릴 수는 있어도 **그 경로가 통과된
적은 없다** — "연동이 된다"고 읽지 말 것. 상품 매핑·주문 불러오기·전환 엔드포인트는 3~4단계에서
이 모듈에 붙는다. ⚠️ 매핑 CRUD 는 있지만 **카페24 상품 목록(`/catalog`)이 아직 없어**
브랜드가 상품 번호를 손으로 알아낼 방법이 없다 — 매핑 화면은 3-2·5-2 다.

## 엔드포인트

전부 `/v1/brand/cafe24/*`.

| 메서드 | 경로 | 가드 | 하는 일 |
|---|---|---|---|
| GET | `/connect` | `BrandGuard` | 쿼리 `mallId`·`returnTo` → 베타 한도·몰 중복 선검사 → 쿠키 4종 심고 카페24 동의 화면으로 302 |
| GET | `/callback` | **없음** | 카페24의 top-level 이동. `state` 쿠키 대조 → 토큰 교환 → 저장 → `BRAND_FRONTEND_URL{returnTo}` 로 302 |
| GET | `/connection` | `BrandGuard` | 판별 유니온 `{connected:false}` 또는 `{connected:true, mallId, scopes, connectedAt, lastSyncedAt, defaultCountryCode, needsReauth, reauthRequiredAt, daysUntilReauth}` |
| PATCH | `/connection` | `BrandGuard` | **몰 기본 배송국** 변경(`{defaultCountryCode}`). 갱신된 상태를 그대로 돌려준다. 연동이 없으면 404 |
| DELETE | `/connection` | `BrandGuard` | 연동 해제 — 토큰 폐기 + **미전환 미러 파기** |
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
- 응답의 만료 시각 문자열은 **믿을 수 있을 때만** 쓴다(`parseCafe24Expiry`) — 타임존 표기가 없는
  형식이면 서버 로컬로 읽혀 최대 9시간이 어긋나므로, 폴백의 2배를 넘는 값은 버리고 상수를 쓴다.
  ⚠️ 실제 형식은 2-2 에서 실응답으로 확인한다.
- 만료 직렬화(`FOR UPDATE` 기반 lazy refresh)와 갱신 cron 은 **2-2 에서 추가된다.**

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
