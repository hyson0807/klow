# cafe24 — 브랜드 자사몰(카페24) 연동

- **모듈 경로**: `src/modules/cafe24/`
- **관련 파일**: `cafe24.service.ts`, `cafe24.client.ts`(카페24 API 지식의 소유자),
  `cafe24-crypto.ts`(AES-256-GCM), `cafe24-oauth-cookies.ts`,
  `brand-cafe24-connect.controller.ts`(OAuth 왕복), `brand-cafe24.controller.ts`(리소스),
  검증 스키마 `common/validation/cafe24.ts`, SSRF 회귀 스펙 `__tests__/cafe24-ssrf.spec.ts`
- **모델**: `Cafe24Connection` · `Cafe24ProductMap` · `Cafe24Order` · `Cafe24OrderItem`
  + `FulfillmentRequest.source`(`enum FulfillmentSource { manual bulk_xlsx cafe24 }`)
- **프론트**: 아직 없다 — 브랜드 화면은 5단계다
- **계획 문서**: [`plan/cafe24-fulfillment/implementation-plan.md`](../../plan/cafe24-fulfillment/implementation-plan.md)

브랜드가 자사몰을 OAuth 로 연결 → 카페24 상품을 KLOW 제품에 매핑 → 주문을 불러와 → 고른 주문을
**3PL 출고신청으로 전환**(재고 차감). **출고 이후는 [fulfillment](./fulfillment.md) 경로 그대로**이고,
이 모듈은 `Order`·`Shipment`·EFS 를 만나지 않는다.

## ⚠️ 현재 구현 범위 — OAuth 왕복만 있고 **실행된 적이 없다**

2-1 단계까지의 코드다. 카페24 자격증명 없이 쓴 코드라 **토큰 교환은 한 번도 실행되지 않았다**
(2-2 에서 실왕복으로 확인한다). 아래 표의 `연동`만 존재하고, 상품 매핑·주문 불러오기·전환
엔드포인트는 3~4단계에서 이 모듈에 붙는다.

## 엔드포인트

전부 `/v1/brand/cafe24/*`.

| 메서드 | 경로 | 가드 | 하는 일 |
|---|---|---|---|
| GET | `/connect` | `BrandGuard` | 쿼리 `mallId`·`returnTo` → 베타 한도·몰 중복 선검사 → 쿠키 4종 심고 카페24 동의 화면으로 302 |
| GET | `/callback` | **없음** | 카페24의 top-level 이동. `state` 쿠키 대조 → 토큰 교환 → 저장 → `BRAND_FRONTEND_URL{returnTo}` 로 302 |
| GET | `/connection` | `BrandGuard` | 판별 유니온 `{connected:false}` 또는 `{connected:true, mallId, scopes, connectedAt, lastSyncedAt, needsReauth, reauthRequiredAt, daysUntilReauth}` |
| DELETE | `/connection` | `BrandGuard` | 연동 해제 — 토큰 폐기 + **미전환 미러 파기** |

콜백의 결과는 쿼리로 전달된다 — 성공 `?cafe24_connected=1`, 실패 `?cafe24_error=<사유>`
(`state_mismatch` · `missing_brand` · `missing_mall` · `mall_mismatch` · `mall_in_use` ·
`limit_reached` · `connect_failed` · 카페24가 준 `error` 값).

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
