# 카페24 연동 — 구현 계획

> 상태는 [진행표](../../PROGRESS.md) 참조. 이 문서는 **스펙**만 갖는다.
> 설계 논거는 [`flow.md`](./flow.md), 결정 요약은 [`README.md`](./README.md).

## 0. 이 트랙이 하는 일 (한 줄)

**브랜드가 카페24 자사몰을 OAuth 로 연결 → 카페24 상품을 KLOW 제품에 1:1 매핑 →
`쇼핑몰 주문 불러오기` → 불러온 주문을 골라 출고신청으로 전환(재고 차감) → 기존 3PL 경로로 출고.**

⚠️ **출고 이후는 무변경이다.** `FulfillmentRequest` 가 만들어지는 순간부터 브랜드가 손으로 입력한
건과 동작이 같고, 어드민 콜로세움 엑셀 내보내기도 그대로다. 그래서 이 트랙은 `klow_server` 의
**EFS·`Shipment`·`ShippingCarrier`·`Order` 코드를 한 줄도 건드리지 않는다.**

⚠️⚠️ 다만 **`fulfillment` 모듈은 두 군데 건드린다** — `FulfillmentRequest.source` 컬럼(§4-F)과
브랜드 목록의 `since`/`until` 서버 필터(§7 R3). "전혀 안 건드린다"가 아니다.

⚠️⚠️ **그리고 이 트랙은 3PL 과 한 배포로 묶인다**(2026-09-23 사용자 결정, §1-A) — 3PL 7단계
(운영 배포)가 §8 의 6단계에 흡수됐다. 두 트랙이 **함께 처음 운영에 나간다.**

## 1. 착수 게이트 (불변식)

| # | 게이트 | 어기면 |
|---|---|---|
| G1 | **3PL 과 한 배포에 묶는다** (2026-09-23 사용자 결정) — 3PL 7단계(운영 배포)를 단독으로 하지 않고, 이 트랙의 배포 단계가 **두 트랙을 함께** 내보낸다 | 아래 §1-A 의 브랜치·DB 규칙을 어기면 3PL 테이블이 없는 DB 위에서 개발하게 되거나, 배포 때 마이그레이션 순서를 사람이 기억해야 한다 |
| G2 | **0단계(앱 생성)는 1~2-1 과 병행한다.** ⚠️ **2-2 부터는 자격증명이 있어야 한다** | 2-1 까지는 코드를 쓸 수 있지만, 토큰 갱신·주문 API 는 **한 번도 실행해 보지 않은 코드**가 된다. 2-2 의 완료 기준이 전부 실호출이다 |
| G3 | **스키마를 바꾸는 단계는 git 브랜치를 판다.** ⚠️ **DB 브랜치는 새로 파지 않고 `ep-floral-sun` 을 이어 쓴다** | 새 DB 브랜치를 staging 기준선에서 파면 **3PL 테이블(`FulfillmentRequest`·`BrandInventoryItem`)이 없다.** 이 트랙은 그 위에 얹히므로 첫 마이그레이션부터 FK 가 깨진다 |
| G4 | **락 획득 순서는 항상 `Cafe24Order`(ORDER BY id) → 재고(ORDER BY productId)** | 순서가 뒤집힌 경로가 하나라도 생기면 데드락이다. `lockInventory()` 가 `ORDER BY "productId"` 를 쓰는 이유와 같은 문제 |

### 1-A. 3PL 과 한 배포로 묶는다 — 브랜치·DB 규칙

3PL 트랙은 1~6단계가 끝났지만 **운영 미배포**이고, 세 레포가 `feat/3pl-fulfillment` 에 있으며
마이그레이션이 전용 Neon 브랜치 `ep-floral-sun` 에만 있다. 그 상태를 **그대로 이어받는다.**

| 축 | 규칙 |
|---|---|
| **git 브랜치** | ⚠️ **`feat/3pl-fulfillment` 에 그대로 이어서 쌓는다.** 새 브랜치를 만들지 않는다(2026-09-23 사용자 결정) — 어차피 한 배포로 나가므로 나눌 이유가 없고, 나누면 머지 순서를 또 관리해야 한다 |
| **DB 브랜치** | ⚠️⚠️ **`ep-floral-sun` 을 이어 쓴다.** 새로 파지 않는다 — 3PL 마이그레이션이 거기에만 있다 |
| **배포** | 마이그레이션 **2개를 순서대로**: `20260922070013_add_3pl_fulfillment` → `add_cafe24_fulfillment`. 그다음 `klow_server → klow_admin → klow_brand` |

⚠️⚠️ **이 결정의 대가를 알고 간다 — 3PL 이 운영에서 한 번도 돌아본 적 없는 채로 카페24와 함께
나간다.** 배포 후에 문제가 생기면 **두 트랙 중 어느 쪽 때문인지 즉시 분리되지 않는다.**
그래서 배포 후 확인은 **3PL 왕복을 먼저 통과시키고 나서** 카페24를 켜는 순서다(§8 의 배포 단계).

⚠️ **브랜치 이름이 내용을 다 말하지 않는다.** `feat/3pl-fulfillment` 는 이제 **두 트랙을 담는다** —
어느 커밋이 어느 트랙인지는 **커밋 메시지로만** 구분된다. 카페24 커밋의 제목에 `cafe24` 를 넣는다.

⚠️ 되돌릴 일이 생기면 되돌림도 함께다. 3PL 만 남기고 카페24를 빼려면 **커밋 단위로 골라내야
하고**(브랜치 경계가 없다), **카페24 마이그레이션은 `DROP TABLE` 이라 롤링 안전하지 않다**
(단일 레플리카 컷오버가 필요하다). 둘을 따로 낼 수 있기를 원한다면 지금 브랜치를 나눠야 한다.

## 2. 착수 전 확인할 것

⚠️ **추측해서 구현하지 않는다.** 정해지기 전에는 잠정 처리로 두고, 정해지는 단계에서 채운다.

| # | 항목 | 결론 |
|---|---|---|
| A | **앱스토어 설치 진입점에서 `mall_id` 가 어떤 파라미터로 오는지** | **실측 불필요로 확정**(2026-09-23) — v1 은 앱스토어 진입을 지원하지 않는다(§7 R1). 그 경로를 열 때 실측한다 |
| B | **주문 상태 코드 값**과 기본으로 가져올 상태 | △ **정본은 확인, 코드 목록은 미완**(2026-09-23 실측, §2-C). 상태는 **품목 단위**이고 **정본은 `order_status`** 다(`N00` 입금전 / `N20` 배송준비중 관측). ⚠️⚠️ **`status_code` 는 상태가 바뀌어도 `"N1"` 그대로라 판정에 쓰면 안 된다** — 쓰면 미결제 주문이 전환 대상에 섞인다. ⚠️ 주문 최상위에는 `order_status` 가 **없다**. 관측 코드가 둘뿐이라 **기본 필터를 정하지 않는다** — 4-1 은 기간으로만 불러오고 상태를 미러에 저장해 화면이 고르게 한다 |
| C | **주문 목록 조회의 날짜 범위 최대 일수** | ✅ **3개월**(2026-09-23 실측 — 92일 요청이 422 `"within 3 months"`, 31일은 200). 우리 쪽 **14일 상한**은 그 안이라 그대로 둔다(§5-B) |
| D | 심사 요건에 **"앱 실행 화면(iframe)"이 포함되는지** | ✅ **포함되지 않는다**(2026-09-23 실측, STEP 03) — 아래 §2-A 참고. **§7 R1 의 회피안이 유지된다** |
| E | **카페24 주문 하나에 매핑 안 된 품목이 섞였을 때** | 그 주문은 **전환 불가**로 막고, 브랜드가 줄 단위로 `제외` 표시를 할 수 있게 한다(§4-D `excluded`). 매핑된 줄만 자동으로 보내지 않는다 — `reserveInventory` 의 "부분 출고 없음"과 같은 근거다 |
| F | **옵션 없는 상품의 매핑 키** — `variant_code` 실값인가 빈 문자열인가 | ✅ **실값이다**(2026-09-23 실측, §2-C). 옵션이 없어도 카페24가 variant 를 1줄 주고(`options: null`) **주문 품목도 그 실값을 싣는다** — 카탈로그 값과 정확히 일치함을 대조로 확인했다. ⚠️⚠️ **빈 문자열로 저장하면 전환 시점의 매핑 조회가 전부 빗나간다.** 스키마·zod 주석을 실측으로 고쳤다 |

### 2-A. 개발자센터 실측 (2026-09-23, 앱 `KLOW 해외배송 출고연동`)

0단계에서 앱을 만들며 확인한 것들. **추측이 아니라 화면에서 본 값이다.**

⚠️⚠️ **Redirect URI 에 `http://localhost` 를 등록할 수 없다 — 이 문서의 0단계가 틀렸었다.**
개발자센터가 **HTTPS 만** 받고 **IP 주소도 거부**한다("HTTPS must be included in the URL.
(HTTP not supported)" / "IP address cannot be used as a redirect URI"). 이 레포의 다른 연동
(`GOOGLE_*`·`META_*`)은 전부 localhost 를 등록해 두고 로컬에서 왕복을 돌리므로, **그 관례를
여기에 복사하면 2-2 착수 시점에 막힌다.**
→ 로컬 OAuth 왕복에는 **HTTPS 터널 도메인**이 필요하다(cloudflared / ngrok). Redirect URI 는
**최대 10줄**이라 운영·터널을 함께 등록해 둘 수 있다. ⚠️ 터널 주소가 바뀌면 개발자센터와
`CAFE24_BRAND_CALLBACK_URL` 을 **함께** 고쳐야 한다(한 글자만 달라도 토큰 교환 실패).

| 항목 | 실측값 |
|---|---|
| App type | **Web**(표준 서비스 앱). Android/iOS 는 네이티브용 |
| App URL 실행 방식 | **`New window`(기본)** / `Pop-up` 선택. ⚠️ **iframe 이 아니다** — top-level 이라 `klow_brand_sid` 가 1st-party 로 전송된다. §7 R1 의 위험이 예상보다 작다 |
| Redirect URI | HTTPS 필수 · IP 불가 · **최대 10줄, 각 150바이트** |
| 권한(Store admin) | `Apps(Application) / read and write` 가 **기본으로 박혀 있고 삭제 불가**. 그 위에 `Orders(Order) / read` + `Products(Product) / read` 를 추가했다 |
| 권한(Customer) | `Customer identifier / read` **기본·삭제 불가** |
| Time zone | `Asia/Seoul` 유지. ⚠️ 이 설정이 **토큰 만료 시각과 주문 조회 날짜 축 둘 다**에 걸린다. 주문 날짜를 KST 로 맞추는 쪽을 택했고, 만료 문자열 문제는 `parseCafe24Expiry` 한 곳에서 처리한다(2-2 에서 실응답 확인) |
| 스토어 버전 | **Korea 만.** Japan/Global 은 그 시장 현지 몰용이라 축이 반대다 |
| 심사 제출물 | 스토어 리스팅(이름·아이콘·설명·**스크린샷 필수**·FAQ·가격). **앱 실행 화면을 iframe 으로 요구하는 문구는 없다** |
| 가격 | **Free 로 낸다.** 카페24 결제를 태우면 수수료를 물고 청구 경로가 NicePay 구독과 **두 개**가 된다 |

⚠️ **심사 제출(8단계)까지 스토어 리스팅을 채우지 않는다** — 스크린샷에 들어갈 화면(매핑·주문
목록)이 5-2·5-3 에서야 생긴다. 지금 쓰면 그때 전부 다시 쓴다.

### 2-B. OAuth·API 실측 (2026-09-23, 2-2 단계 · 테스트 몰 `simsgood1`)

**OAuth 왕복이 처음으로 실제로 통과했다.** 그전까지의 모든 기록은 "코드가 있다"였고, 여기서
"동작한다"로 바뀐다.

| 항목 | 실측값 |
|---|---|
| authorize 진입 | `https://{mall}.cafe24api.com/api/v2/oauth/authorize` → 미로그인이면 `eclogin.cafe24.com` 으로 한 번 더 튄다(우리 URL 을 `submenu` 쿼리에 담아서) |
| 토큰 교환 | 성공. `scopes` 응답은 **공백 구분**(`"mall.read_order mall.read_product"`) — 요청은 쉼표 구분인데 응답은 공백이다 |
| access / refresh 수명 | **정확히 2시간 / 14일** |
| ⚠️⚠️ **만료 시각 문자열** | **타임존 표기가 없다** — `"2026-09-23T19:16:43.000"`, 값은 **KST 벽시계**. 아래 별도 절 |
| 주문 조회 | `GET /api/v2/admin/orders` · `Authorization: Bearer` · **HTTP 200** |
| 기간 상한 | **3개월**(92일 → 422, 31일 → 200). 422 메시지가 `+09:00` 을 말해 카페24가 KST 로 답하는 것을 한 번 더 확인 |
| 쿼터 헤더 | **`x-api-call-limit: 4/40`**(소문자, `사용/용량`). ⚠️ **`Retry-After` 는 관측하지 못했다** — 429 를 실제로 맞아 보지 않았다(R5 분기의 `retryAfterSec` 는 **미검증**이고 null 폴백 문구가 뜬다) |
| 주문 상태 코드 | ⚠️ **못 봤다** — 테스트 몰에 3개월간 주문 0건(§2 B) |


#### 상품 API 실측 (3-2, 테스트 몰 `simsgood1` · 상품 40개)

| 항목 | 실측값 |
|---|---|
| 목록 | `GET /api/v2/admin/products?limit&offset&embed=variants` · `limit` 상한 **100**(101 → 422) |
| 건수 | `GET /api/v2/admin/products/count` — **`product_name` 필터를 똑같이 받는다**(검색 중 총계에 필요) |
| 검색 | `product_name` 은 **부분일치**(이름 조각으로 검색된다) |
| `offset` | 총 건수를 넘으면 빈 배열(에러 아님). 상한은 관측되지 않았다 |
| `display`/`selling` | ⚠️ **`"T"`/`"F"` 문자열**이다 — 불리언이 아니다. 그대로 흘리면 `'F'` 가 truthy 라 **판매중지가 판매중으로 보인다** |
| variants | ⚠️ **옵션이 없는 상품도 1줄 온다** — `options: null` 이고 `variant_code` 는 실재한다(`P00000BY000A`). §2 F 의 미확정이 여기서 나왔다 |

⚠️⚠️ **`fields` 파라미터를 쓰면 `embed=variants` 가 조용히 빠진다**(실측 — 응답에 `variants`
키 자체가 없다). 페이로드를 줄이려다 매핑 키를 통째로 잃는다. 큰 응답은 **우리 서버와 카페24
사이**에서만 오가므로 그대로 받고 **서비스가 DTO 로 줄인다**.

#### ⚠️⚠️ 만료 시각 — 로컬에서는 영원히 재현되지 않는 버그

응답이 `expires_at: "2026-09-23T19:16:43.000"` 처럼 **타임존 없이** 온다. 타임존 없는 ISO
문자열을 `Date.parse` 에 그냥 넘기면 **서버 로컬 시각**으로 읽는다.

- 개발 맥북은 로컬 TZ 가 KST 라 **우연히 맞는다**
- 운영(Railway·Docker)은 **UTC** 라 같은 문자열을 9시간 늦게 읽는다 → 이미 죽은 토큰을 살아
  있다고 믿고 호출해 **401**

→ `parseCafe24Expiry` 가 **표기가 없으면 `+09:00` 을 붙인다.** 기존의 "폴백의 2배 초과는
버린다" 범위 검사는 **안전망일 뿐 주 방어가 아니다** — 실측상 access 는 그 검사가 잡아주지만
(2h 짜리가 11h 로 읽혀 4h 상한 초과), **refresh 는 14일+9시간이 28일 안이라 그대로 통과한다.**
회귀 잠금은 `cafe24/__tests__/cafe24-expiry.spec.ts`(기대값을 `Date.parse` 가 아니라 절대
인스턴트로 적는다 — 그러지 않으면 스펙이 버그와 같이 틀려서 통과한다).

⚠️ 이 `+09:00` 은 **개발자센터 앱 설정의 Time zone(`Asia/Seoul`)과 묶여 있다.** 거기를 바꾸면
여기도 바꿔야 하고, 그 설정은 **주문 조회 날짜 축에도** 걸리므로 바꾸는 쪽이 훨씬 비싸다.

### 2-C. 주문 API 실측 (2026-09-23 · 테스트 몰 `simsgood1` · 수동 테스트 주문 1건)

**`GET /api/v2/admin/orders?start_date&end_date&limit&embed=items`.**

#### ⚠️⚠️ 상태는 품목 단위이고, 정본은 `order_status` 다

같은 주문을 `입금전` → (입금 확인처리) → `배송준비중` 으로 옮기며 두 번 찍었다.

| 상태 | 품목 `order_status` | 품목 `status_code` | 품목 `status_text` | 주문 `paid` |
|---|---|---|---|---|
| 입금전 | **`"N00"`** | `"N1"` | `"입금전"` | `"F"` |
| 배송준비중 | **`"N20"`** | `"N1"` | `"배송준비중"` | `"T"` |

⚠️⚠️ **`status_code` 는 상태가 바뀌어도 `"N1"` 그대로다 — 상태 판정에 쓰면 안 된다.**
이걸로 필터를 걸면 **입금전(미결제) 주문이 전환 대상에 섞여** 돈을 받지도 않은 건이 창고로 나간다.
**정본은 `order_status`** 이고 사람이 읽을 이름은 `status_text` 다.

⚠️ 주문 최상위에는 **`order_status` 가 아예 없다** — 있는 것은 `paid`/`canceled`/`shipping_status`
(전부 `"T"`/`"F"`)와 `payment_date` 다. 최상위에서 상태를 읽으려 하면 칸 자체가 없다.

관측된 코드는 **둘뿐**(`N00`·`N20`)이다. ⚠️ 나머지 코드를 추측해 상수로 박지 않는다 —
4-1 은 **기간으로만** 불러오고 `order_status`·`status_text` 를 미러에 저장해 **화면이 고르게** 한다.
`order_item_code` 는 `20260923-0000014-01` 꼴(주문번호 + 순번)이다.

#### ⚠️⚠️ 매핑 키는 실제 `variant_code` 다 (§2 F 확정)

```
주문 품목  variant_code = "P000000V000A"   (options: [], option_value: "" → 옵션 없는 상품)
카탈로그   variant_code = "P000000V000A"   (options: null)
➜ 정확히 일치
```

옵션이 **없어도** 카페24는 상품마다 variant 를 1줄 주고 주문 품목도 **그 실값**을 싣는다.
빈 문자열로 저장했다면 전환 시점의 매핑 조회가 **전부 빗나갔을 것**이다.
→ `schema.prisma` 와 `common/validation/cafe24.ts` 의 "옵션 없으면 빈 문자열" 주석을 실측으로 고쳤다.

#### 전환에 쓸 품목 칸

`order_item_code` · `product_no` · `variant_code` · `quantity` · `product_price` ·
`order_status`/`status_code`/`status_text` · `gift`(사은품 여부 — §4-D 의 `excluded` 판단 재료) ·
`claim_quantity`/`cancel_date`(부분 취소 흔적) · `shipping_code`.

⚠️ 주문 최상위에 `currency`·`order_date`·`market_id`·`shipping_type_text`(`"국내배송"`)가 있고,
수취인 정보는 **개인정보**라 이 문서에 칸 이름만 남긴다.

## 3. 실측으로 확정된 전제

구현 중 이 전제를 그대로 쓴다. 코드 위치는 심볼명으로 재확인한 뒤 편집한다.

### 카페24 API

- **토큰**: access **2시간** / refresh **14일**. ⚠️⚠️ **갱신 시 refresh token 도 회전**되어 기존 것이
  즉시 무효다. 토큰 요청은 **2시간당 15회** 제한
- **도메인**: `{mall_id}.cafe24api.com` — authorize URL 을 만들기 전에 `mall_id` 가 필요하다
- **주문 조회**: `GET /api/v2/admin/orders`, scope `mall.read_order`, **요청당 100건**.
  하위 리소스는 `embed` 로 함께 가져온다
- ⚠️ **주문 상태는 품목(`order_item_code`) 단위**다. 부분 취소·부분 배송이 정상 상태다
- **쿼터**: 10분당 3,000회 + 초당 2회 누수 버킷(용량 40) → 초과 시 **429** + `X-Api-Call-Limit` 헤더.
  **Access Token 기준 집계**라 브랜드별로 독립이다
- **앱 설치**: 심사 전 **최대 5개 쇼핑몰**
- **필요 scope**: `mall.read_order` · `mall.read_product` (+ 몰 정보 `mall.read_store`).
  **쓰기 권한은 요구하지 않는다**

### KLOW 쪽

- ⚠️⚠️ **`Product.stockLeft` 를 만지지 말 것** — 창고 재고가 아니라 klow_web PDP 희소성 문구용
  어드민 수기 표시값이다([3PL 계획서 §3](../3pl-fulfillment/implementation-plan.md))
- **재고 차감은 `fulfillment.service.ts` 가 소유한다** — `reserveInventory()` → `lockInventory()`
  (`SELECT … FOR UPDATE ORDER BY "productId"`) → `applyInventoryDelta()` 단일 UPDATE.
  **이 경로를 우회해 재고를 건드리는 코드를 새로 만들지 않는다**
- **`createBulk(brandId, requests)` 가 `{ok, created, ids}`** 를 돌려주고 `ids` 는 **입력 순서**다.
  한 트랜잭션 · 한 번의 재고 잠금 · **부분 성공 없음**. `FULFILLMENT_TX_OPTS = {timeout:20_000, maxWait:15_000}`
- ⚠️ **`shortages[]` 는 `productId` 단위**라 "어느 주문이 걸렸는지"를 서버가 알려주지 않는다.
  주문 단위 차단 사유는 **프리뷰가 만든다**(§5)
- **zod 에 `.default()` 를 쓰지 않는다** — 구 클라가 새 필드를 모르는 배포 창에서 기본값 덮어쓰기가
  일어난다(이 레포의 반복 사고). 클라는 빈 문자열 포함 **모든 칸을 항상 보낸다**
- ⚠️ **상한 상수를 env 로 빼지 않는다** — `FULFILLMENT_MAX_ITEMS` 주석: *"이 레포엔 env 수치 상한이
  0건이고, `=0` 오타 하나가 전 브랜드의 출고신청을 조용히 막는다."*
- **OAuth 선례는 `src/modules/instagram/` 8파일 전부** — connect 컨트롤러(콜백은 가드 없음, 쿠키로
  주체 복원) · state/brand/returnTo httpOnly 쿠키 3종 · AES-256-GCM(`iv:tag:ct`) · 갱신 cron ·
  중앙 `fetchJson` 관문(AbortController 15초 + `BadGatewayException` + context 문자열, **재시도 없음**)
- **crypto 유틸은 공용화하지 않는다** — `totp-crypto.ts` ↔ `instagram-crypto.ts` 가 이미 동일한
  복제본 둘이고, 키를 공유하면 회전 blast radius 가 합쳐진다. 카페24는 **세 번째 복사본**이 맞다.
  ⚠️⚠️ **`META_TOKEN_ENCRYPTION_KEY` 를 재사용하지 말 것** — Meta 키를 돌리는 순간 카페24 토큰이
  전부 안 읽힌다
- **콜백 경로는 `common/origin-exempt.ts` 의 `ORIGIN_EXEMPT_EXACT` 에 등록**하고 **그 `__tests__`
  스펙도 고친다**. ⚠️ 콜백이 GET 이면 Origin 가드는 원래 안 탄다(`main.ts` 가 상태변경 메서드만
  검사) — **빠뜨려도 조용히 동작하므로 더더욱 스펙으로 잠근다**
- **cron 은 현재 10개**이고 `test/app.e2e-spec.ts` 가 개수와 이름을 검사한다.
  ⚠️ `@Cron` 클래스를 모듈 providers 에 안 넣으면 **조용히 실행되지 않는다**
- ⚠️ **Prisma 는 명시 `select` 가 없으면 모델 스칼라를 전부 SELECT 한다** — 2026-09-22
  `externalProductCode` 드롭 사고가 정확히 이 성질에서 나왔다([`decisions/storefront.md`](../../decisions/storefront.md#2026-09-22))

## 4. 스키마

**`CREATE TABLE` ×4 · `CREATE TYPE` ×1 · `ADD COLUMN` ×1.**

⚠️ **"`ALTER` 0건"이 아니다.** 역방향 relation 때문에 `Brand`·`Product`·`FulfillmentRequest` 세
기존 테이블에 **FK 제약(`ADD CONSTRAINT`)이 붙는다**. `ShareRowExclusiveLock` 을 순간 잡지만
세 테이블 모두 소규모이고, `FulfillmentRequest` 는 **이 마이그레이션이 운영에 나갈 때 아직 데이터가
0건**이다(3PL 이 같은 배포에서 처음 나가므로 — §1-A). 실질 무해하다. **롤링 안전 · 백필 없음**은 유지된다.

### 4-A. `Cafe24Connection` — 브랜드 1 : 몰 1

`id` · `brandId @unique` · `mallId @unique` · `accessTokenEnc` / `accessTokenExpiresAt` ·
**`refreshTokenEnc` / `refreshTokenExpiresAt`** · `scopes String` ·
**`needsReauth Boolean`**(refresh 가 400 으로 죽어 복구 불가가 된 상태) ·
**`defaultCountryCode @db.VarChar(2)`** · `lastSyncedAt DateTime?` · `lastRefreshedAt DateTime?` ·
`connectedAt` · `updatedAt`. `brand` 관계 `onDelete: Cascade`.
`@@index([refreshTokenExpiresAt])`(갱신 cron 조회축).

- ⚠️⚠️ **`needsReauth` 가 없으면 브랜드는 영원히 "불러오기 실패"만 본다.** refresh token 이
  만료·폐기되면 우리가 할 수 있는 일이 없고, 재연동을 시키려면 그 사실이 화면에 떠야 한다
- ⚠️ **`defaultCountryCode` 는 선택이 아니다** — 카페24 국내 주문은 수취인 국가 코드가 비어서
  온다. `FulfillmentRequestInput.countryCode` 는 ISO2 필수이고 zod `.default()` 가 금지돼 있어
  **어딘가에서 국가를 정해야 한다.** 연결 시점에 브랜드가 고르고(기본 `KR`) 미러가 그걸 채운다
- ⚠️⚠️ **`mallId` 충돌에 Instagram 의 `deleteMany` 를 복제하지 말 것.** 그쪽은 *"그 IG 계정으로
  OAuth 로그인했다는 것 자체가 통제권 증명"* 이라는 근거가 있다. **자사몰은 법인 자산이라 그
  논거가 성립하지 않고**, 한 몰이 두 브랜드에 물리는 건 사고 신호다 → **409 + 로그**
- ⚠️ **`shopNo` 컬럼을 두지 않는다.** `mallId @unique` 인 한 멀티샵을 지원할 수 없는데 컬럼만 있으면
  다음 사람이 지원된다고 읽는다. 상수 1 로 고정하고, 지원할 때 `@@unique([mallId, shopNo])` 로 연다

### 4-B. `Cafe24ProductMap` — 매핑의 정본

`id` · `brandId` · `cafe24ProductNo Int` · `variantCode String`(옵션 없으면 빈 문자열) ·
`cafe24ProductName @db.VarChar(200)`(스냅샷, 표시용) · `productId` · `createdAt`/`updatedAt`.
`@@unique([brandId, cafe24ProductNo, variantCode])` · `@@index([brandId])` · **`@@index([productId])`**.

⚠️⚠️ **`product` 관계는 `onDelete: Cascade`.** Prisma 기본은 `Restrict` 이고, 이 레포에는 **실제
제품 삭제 경로가 있다**(`products.service.ts` — `FulfillmentRequestItem` 이 `SetNull` 인 이유).
기본값대로 두면 매핑이 걸린 제품을 지울 때 **P2003 으로 실패한다 = 기존 기능 회귀**.
매핑은 `productId` 가 없으면 의미가 없으므로 `SetNull` 이 아니라 `Cascade` 가 맞다.

⚠️ **N:1 을 허용한다** — 카페24 옵션 여러 개가 같은 KLOW 제품을 가리켜도 된다.
그 결과가 §5-D 의 수량 합산 요구로 이어진다.

### 4-C. `Cafe24Order` — 미러

- `id` · `brandId` · `cafe24OrderId @db.VarChar(50)` · `orderedAt` · `orderStatus @db.VarChar(20)`
  · `orderTotal` + `currency`(브랜드가 목록에서 주문을 식별하는 가장 강한 단서)
- **수취인 스냅샷** — 이름은 `FulfillmentRequest` 와 맞추되 **상한은 넉넉히**(§4-E):
  `countryCode(2)` · `recipientName` · `recipientAddress1` · `recipientAddress2` ·
  `recipientPostalCode` · `recipientPhone` · `recipientPhone2` · `deliveryMemo` ·
  `ordererName` · `ordererPhone` · **`truncatedFields String`**(잘린 칸 이름 목록)
- `fulfillmentRequestId String? @unique` — **전환 여부의 정본**.
  ⚠️ **`onDelete: SetNull`** — `Brand` 삭제 시 `FulfillmentRequest` 와 `Cafe24Order` 가 동시에
  캐스케이드되는데 PG 가 순서를 보장하지 않는다. `Restrict` 면 **브랜드 삭제가 실패한다**
- `importedAt` · **`updatedAt @updatedAt`**(재수집 갱신의 축)
- `@@unique([brandId, cafe24OrderId])` — **중복 유입 방지의 정본**
- **`@@index([brandId, orderedAt])`** — 목록이 `brandId` + 미전환 + `orderedAt desc` 로 읽는다.
  `@@unique` 는 정렬에 못 쓴다

⚠️ **`raw Json` 을 두지 않는다.** 원본 JSON 에는 수취인 PII 가 **한 번 더** 들어 있어 사본이
둘이 되고, 스냅샷 칸만 정리해도 PII 가 남는다. 게다가 Prisma 의 암묵 전체 SELECT 때문에
**목록 응답이 원본 JSON 을 통째로 브라우저에 쏜다**. 진단이 필요하면 PII 를 걷어낸 부분집합만
따로 둔다.

⚠️⚠️ **모듈 상수 `CAFE24_ORDER_SELECT` 를 반드시 만든다** — `fulfillment.service.ts` 의
`REQUEST_SELECT` 선례. 명시 select 가 없으면 컬럼이 늘 때마다 응답이 조용히 넓어진다.

### 4-D. `Cafe24OrderItem` — 품목 단위가 핵심이다

`id` · `orderId`(Cascade) · **`orderItemCode @db.VarChar(40)`** · **`itemStatus @db.VarChar(20)`** ·
`cafe24ProductNo Int` · `variantCode String` · `productName @db.VarChar(200)` · `quantity Int` ·
`productId String?`(매핑 해석 캐시, `onDelete: SetNull`) · **`excluded Boolean`** ·
`@@unique([orderId, orderItemCode])` · `@@index([orderId])`.

⚠️⚠️ **주문 단위 상태 하나로 접으면 부분 취소를 표현할 수 없다.** 카페24는 상태가 품목 단위라,
취소된 품목까지 출고신청으로 전환돼 **창고에서 나가 버린다.** `orderItemCode` 는 재수집 때 행을
매칭하는 유일한 키이기도 하다.

⚠️ **`excluded`** 는 사은품처럼 "매핑 대상이 아닌 줄"을 브랜드가 끄는 스위치다. 없으면 사은품
한 줄 때문에 주문 전체가 영영 전환 불가가 된다(§2 E).

⚠️ `productId` 는 **불러오기 시점의 캐시**다. 전환은 이 값을 믿지 말고 **그 시점에 매핑을 다시
읽는다** — 사이에 브랜드가 매핑을 고칠 수 있고, 안 그러면 *"매핑을 고쳤는데 여전히 전환이 안 돼요"* 가 된다.

⚠️⚠️ **`Cafe24OrderItem.productName`(카페24 상품명)과 `FulfillmentRequestItem.productName`
(**KLOW 제품명**)을 혼동하지 말 것.** 후자는 `snapshotNames()` 가 KLOW `Product.name` 으로 채우고
**창고 작업자가 그 문자열로 물건을 찾는다.** 카페24 상품명을 넣으면 창고가 못 찾는다.

### 4-E. 잘린 값 — 미러는 넉넉히 받고, 잘렸다는 사실을 남긴다

⚠️⚠️ **미러 상한을 `FulfillmentRequest` 와 똑같이 두면 import 가 통째로 죽는다.** 그 상한들은
**콜로세움이 정한 값이 아니라 추정치**이고(3PL zod 헤더 주석이 명시), 배송메모가 201자인 주문
하나가 섞이면 **불러오기 전체가 22001 로 실패한다.** 카페24 `shipping_message` 는 실제로 넘길 수 있다.

→ 미러는 **잘라서 저장하고 `truncatedFields` 에 어느 칸이 잘렸는지 남긴다.** 전환 시점에 zod 가
다시 검사하므로 안전성은 그대로고, 브랜드는 전환 전에 고칠 기회를 얻는다.
⚠️ 반대로 `Text` 로 열어 버리면 **전환 시점에 400 이 나서 어느 주문이 문제인지 알 수 없다** —
`previewBulk` 가 해결한 것과 같은 문제다.

### 4-F. `FulfillmentRequest.source` — 유일하게 기존 테이블에 붙는 컬럼

`enum FulfillmentSource { manual bulk_xlsx cafe24 }` + `source FulfillmentSource @default(manual)`.
`CREATE TYPE` + `ADD COLUMN NOT NULL DEFAULT` → **PG11+ 는 테이블 rewrite 없음 = 롤링 안전.**

왜 필요한가: "출고신청 목록에서 카페24 유입 건을 구별해 보여준다"의 답이 이것 말고는 전부 나쁘다.

| 대안 | 왜 버리는가 |
|---|---|
| `Cafe24Order` 역조인 | `fulfillment` 모듈이 `cafe24` 모델을 알게 되고, **브랜드 목록·어드민 목록·콜로세움 엑셀 세 곳이 같은 조인을 타야** 표시가 일치한다 |
| `externalOrderNo` 에 접두사 | ⚠️⚠️ **절대 금지.** 그 값은 콜로세움 엑셀 `쇼핑몰주문번호` 칸으로 **그대로 나간다** |

⚠️ **1단계 마이그레이션에 같이 넣는다.** 나중에 따로 내면 배포 창이 두 번 생긴다
([PROGRESS §4](../../PROGRESS.md): *마이그레이션은 항상 독립 단계로 뗀다*).
⚠️ `REQUEST_SELECT` 와 klow_admin·klow_brand DTO 미러가 함께 바뀐다.

### 4-G. 재수집 정책 (스키마가 아니라 규칙)

| 상황 | 동작 |
|---|---|
| 처음 보는 주문 | insert |
| **미전환** 주문이 또 옴 | **갱신** — 주소 수정·부분 취소가 실제로 일어난다 |
| **전환된** 주문이 또 옴 | **`orderStatus`·`itemStatus` 만 갱신**, 수취인·품목은 건드리지 않는다 |

⚠️ 마지막 줄은 §7 R7(카페24 취소를 우리가 모른다)의 최소 방어다. 전환 후 취소를 **자동으로
되돌리지는 않는다** — 재고는 이미 나갔을 수 있다.

## 5. 엔드포인트 (예정)

전부 `/v1/brand/cafe24/*`. 파일은 **평면**이고 접미사로 분류한다([`CLAUDE.md`](../../../CLAUDE.md) 규칙 1·4).

```
src/modules/cafe24/
  brand-cafe24-connect.controller.ts   connect(BrandGuard) · callback(가드 없음) · install(가드 없음)
  brand-cafe24.controller.ts           @UseGuards(BrandGuard) 리소스 전부
  cafe24.service.ts · cafe24.client.ts · cafe24.module.ts
  cafe24-crypto.ts · cafe24-oauth-cookies.ts
  cafe24-token.ts                      ← refresh 직렬화(§6)
  cafe24-order-mapper.ts               ← 카페24 주문 → 미러 행 (순수 함수)
  cafe24-token-refresh.cron.ts · cafe24-retention.cron.ts
```

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| GET | `/connect` | 302 → 카페24 동의. 쿠키 3종(state/brand/returnTo) + **mallId** 심기 |
| GET | `/callback` | **가드 없음.** state 검증 → 토큰 교환 → 저장 → 프론트 302 |
| GET | `/connection` | 판별 유니온. ⚠️ **access token 만료는 노출하지 않는다**(lazy refresh 가 숨기는 값이고 2시간짜리 만료를 보여주면 브랜드가 놀란다). `refreshTokenExpiresAt` 기준 "N일 후 재연동" + `needsReauth` 를 싣는다 |
| DELETE | `/connection` | 연동 해제. 토큰 폐기 + **미전환 미러 PII 파기**(§7 R4) |
| GET | `/catalog` | 카페24 상품 목록(매핑 화면용, cursor + q). ⚠️ 이름을 `products` 로 하지 않는다 — KLOW `Product` 와 축이 섞인다(`externalProductCode` 때 겪은 혼동) |
| GET | `/product-maps` | 저장된 매핑 목록 |
| POST | `/product-maps` | 매핑 upsert — **보낸 줄만 반영** |
| DELETE | `/product-maps/:id` | 매핑 해제 |
| POST | `/orders/import` | 기간·상태로 조회 → 미러 upsert → `{fetched, inserted, updated, skipped, hasMore}` |
| GET | `/orders` | 미러 목록. **기본 필터 = 미전환**(§7 R7) |
| POST | `/orders/convert/preview` | **아무것도 저장하지 않는다.** 주문 단위 차단 사유 목록 |
| POST | `/orders/convert` | 선택한 미러 → `FulfillmentRequest` 일괄 생성(재고 차감) + 역기록 |

라우트 **361 → 372** 예상(부팅 로그가 정본).

### 5-A. `PUT` 이 아니라 `POST` + `DELETE` 인 이유

⚠️⚠️ **매핑을 전체 교체하면 반드시 사고가 난다.** 카페24 몰은 상품이 수백~수천 개라 매핑 화면은
**반드시 페이지를 끊는다**. `PUT` 의 "안 보낸 = 없음" 규칙이 **나머지 페이지의 매핑을 전부 지운다.**
이건 `BrandInventoryInput` 주석이 이미 같은 이유로 못박아 둔 규칙이다 — *"보낸 줄만 반영한다."*

### 5-B. `import` 범위 상한

zod 에 **최대 기간 14일 + 최대 페이지 5(=500건)** 를 **코드 상수**로 박는다. 초과분은
`hasMore: true` 로 돌려 사용자가 버튼을 다시 누르게 한다.
⚠️ 동기로 무한 페이지를 돌면 응답이 수십 초가 되어 엣지 타임아웃에 걸린다.
⚠️ **env 로 빼지 않는다**(§3 KLOW 쪽).

### 5-C. `fulfill` 이 아니라 `convert`

"fulfill" 은 창고가 하는 일이고, `POST /v1/brand/fulfillment/bulk` 가 이미 다른 의미로 있다.
여기서 하는 것은 **전환**이다.

### 5-D. 전환 전 수량 합산 — 이걸 빼면 400 이 난다

⚠️⚠️ 매핑이 N:1 이라 `variantCode` 가 다른 두 줄이 **같은 `productId`** 로 해석될 수 있다.
그대로 넘기면 `FulfillmentRequestInput.items` 의 refine 이 **"같은 제품이 두 번 담겼습니다"로
400** 을 던진다. → 전환 전에 **`productId` 기준으로 수량을 합산**한다(`reserveInventory` 의
demand map 과 같은 모양).

### 5-E. 프리뷰가 주문 단위 사유를 만든다

`shortages[]` 가 `productId` 단위라 서버는 "어느 주문이 걸렸는지"를 모른다.
`convert/preview` 가 건별로 `FulfillmentRequestInput.safeParse` + 재고 스냅샷 판정을 돌려
**주문 단위 차단 사유**를 돌려준다. 근거는 `previewBulk` 주석 그대로 —
*"적용 단계에서야 400 이 나면 사용자는 어느 행이 문제인지 알 수 없다."*
⚠️ 프리뷰는 **재고를 잡아두지 않는다.**

### 5-F. `common/` 경계

zod 는 `common/validation/cafe24.ts` + `index.ts` 배럴 re-export.
⚠️ **카페24 상태코드 표·API URL 같은 도메인 지식을 여기 넣지 말 것** — 그건 `cafe24.client.ts` 다.
`common/` 은 `modules/` 를 import 할 수 없고(`eslint.config.mjs` 의 `no-restricted-imports`),
역방향 도메인 지식이 쌓이면 다음 사람이 그걸 정본으로 읽는다.

## 6. 토큰 갱신 직렬화 (스펙)

레포에 advisory lock 은 0건이다. 쓸 수 있는 것은 `FOR UPDATE` 하나이고 선례가 셋이다
(`fulfillment.service.ts` · `seeding.service.ts` · `brand-auth.service.ts`).

```
tx({ timeout: 20_000, maxWait: 15_000 }):
  1) SELECT … FROM "Cafe24Connection" WHERE "brandId" = $1 FOR UPDATE
  2) accessTokenExpiresAt - now > SKEW  → 그대로 반환      ← 경쟁자가 이미 갱신함
  3) POST /api/v2/oauth/token (grant_type=refresh_token)
  4) UPDATE … SET accessTokenEnc, refreshTokenEnc, 만료 2개, lastRefreshedAt   ← 한 문장
```

| # | 규칙 | 이유 |
|---|---|---|
| 1 | **락 안에서 만료를 다시 확인한다**(2번) | 이 재확인이 회전 무효화를 막는 유일한 지점이다 |
| 2 | **`NOWAIT` 을 쓰지 않는다** | 두 번째 요청이 그냥 실패한다. 기다렸다 2번으로 가야 한다 |
| 3 | **토큰 갱신 트랜잭션을 비즈니스 트랜잭션과 합치지 않는다** | 락 구간에 외부 HTTP 가 들어간다. import 트랜잭션 안에서 refresh 하면 커넥션 풀이 외부 지연만큼 묶인다 |
| 4 | **클라이언트 타임아웃을 8~10초로** (instagram 의 15초보다 짧게) | 위와 같은 이유 |
| 5 | **UPDATE 는 한 문장** | 나눠 쓰면 중간에 죽었을 때 refresh 만 새것이 되어 **다음 갱신이 영구 실패**한다 |
| 6 | **SKEW 는 만료 10분 전** | import 한 번이 토큰 요청 1회를 넘지 않는다 |
| 7 | **낙관적 버전 컬럼을 쓰지 않는다** | 충돌한 쪽이 재시도하면 **이미 회전된 refresh token 으로 또 요청**해서 2시간당 15회를 태운다 |
| 8 | **refresh 가 400 이면 복구 불가** | 토큰 칸을 비우고 `needsReauth = true`. 502 만 던지면 브랜드는 영원히 실패만 본다 |

⚠️ row lock 은 DB 레벨이라 Railway 단일 → ECS 다중(`aws-fargate` 트랙)이 돼도 그대로 동작한다.

## 7. 알려진 위험

### R1. ⚠️⚠️ 카페24 앱은 iframe 안에서 열린다 — 세션 쿠키가 죽는다

퍼블릭앱의 기본 진입은 몰 관리자 화면 안의 **iframe** 이다. `klow_brand_sid` 는 운영에서
`sameSite:'none', secure:true` 인데(`common/cookies.ts`), **3rd-party 컨텍스트에서 Safari ITP /
Chrome 3rd-party 차단에 걸려 전송되지 않을 수 있다.** 앱스토어에서 설치해 우리 화면이 떠도
**로그인 상태가 아니다.**

→ **v1 은 앱스토어 진입을 지원하지 않는다.** KLOW 스튜디오에서 시작하는 경로만 만들고, 설치
진입 URL 은 `target=_top` 으로 탈출시키는 "KLOW 에 로그인해 주세요" 랜딩으로 둔다.

✅ **2026-09-23 실측 — 회피안이 유지된다**(§2-A).

- 심사 제출물은 **스토어 리스팅**(이름·아이콘·설명·스크린샷·FAQ·가격)뿐이고, **앱 실행 화면을
  iframe 으로 요구하는 문구가 없다.** 스크린샷은 필수지만 KLOW 스튜디오 화면을 찍으면 된다
- 더 나아가 **App URL 의 기본 실행 방식이 `New window` 다**(다른 선택지는 `Pop-up`) — 즉
  **top-level 이라 `klow_brand_sid` 가 1st-party 로 전송된다.** 이 위험 자체가 예상보다 작다
- ⚠️ 그래도 v1 범위는 그대로 둔다 — 앱스토어 설치 흐름(설치 직후 화면·미로그인 랜딩)을
  만들지 않았다는 사실은 변하지 않는다. 열려면 §2 A 를 그때 실측한다

### R2. mall_id 입력값이 SSRF 벡터다

브랜드가 넣은 값으로 `https://{mall_id}.cafe24api.com/…` 을 호출한다. `evil.com/`·`..`·`@` 를
넣으면 요청이 다른 호스트로 간다.
→ zod 에서 `/^[a-z0-9][a-z0-9-]{1,30}$/` 로 제한하고, `new URL()` 로 조립한 뒤
**hostname 이 `.cafe24api.com` 으로 끝나는지 재확인**한다.

### R3. `REQUEST_TAKE = 200` — 브랜드 출고신청 목록이 조용히 잘린다

`RequestsPanel.tsx` 가 서버에서 200건을 받아 **클라에서 기간 필터**를 건다. 그 주석이 이미
경고한다 — *"200건을 넘기기 시작하면 서버에 `since`/`until` 을 붙일 차례다."*
카페24 유입은 하루 수십 건이 자연스러워 **몇 주 만에 넘는다.** 넘는 순간 오래된 건이 안 보이고
**기간 칩의 건수가 거짓말을 한다**(모집단 자체가 잘렸으므로).
→ **이 트랙에 `FulfillmentListQuery` 의 `since`/`until` + 서버 필터링을 포함시킨다.**
⚠️ `fulfillment` 모듈 변경이라 모듈 문서 갱신 계약과 배포 순서에 걸린다.

### R4. 미러의 PII

- **전환된 주문은 전환 직후 같은 트랜잭션에서 수취인 스냅샷을 빈 문자열로 덮는다.** 정본이
  `FulfillmentRequest` 로 옮겨갔으므로 사본을 하나로 줄이고, `fulfillmentRequestId` 가 링크를 유지한다
- **미전환 주문은 보존기간 경과분을 파기한다** — `cafe24-retention.cron.ts`.
  보존기간·삭제 조건은 서비스가 소유하고 cron 은 스케줄만 갖는다(`storefront-stats-retention.cron.ts` 형태)
- **연동 해제 시에도 미전환 미러를 파기한다**(§5 `DELETE /connection`)
- 개인정보처리방침 갱신이 심사 제출물에 필요할 수 있다 — `klow_brand/src/app/legal/`

### R5. 쿼터 — "불러오기 연타"가 그 브랜드를 자기 손으로 막는다

초당 2회 누수 버킷(용량 40)이고 `instagram.client.ts` 의 관문은 **재시도가 없고 비-200 을 전부
`BadGatewayException`** 으로 접는다. 그대로 복제하면 429 가 사용자에겐 그냥 "502" 다.
→ (a) `cafe24.client.ts` 관문에 **429 전용 분기**(`X-Api-Call-Limit` 을 읽어 "잠시 후 다시" 로 번역),
(b) import 루프에 **페이지 간 최소 간격**, (c) `lastSyncedAt` 기준 **브랜드별 서버 쿨다운**.
⚠️ `ThrottlerGuard` 는 IP 기준이라 이 축을 못 막는다 — DB 컬럼 쿨다운이 맞다.

### R6. 심사 전 5개 몰 제한 — 6번째 브랜드가 원인 불명으로 실패한다

연결 시점에 `Cafe24Connection` 수를 세서 5를 넘으면 **명시적 에러**("현재 베타 연동 한도에
도달했습니다")로 끊는다. 안 막으면 실패가 카페24 쪽 화면에서 나서 **브랜드도 우리도 원인을 모른다.**

### R7. 회신이 없어서 브랜드가 두 화면을 왕복한다

송장 자동 회신이 v1 밖이라 브랜드는 카페24 관리자에서 수동으로 배송 처리해야 하고, 안 하면
카페24가 그 주문을 계속 "배송대기"로 들고 있어 **다음 불러오기에 또 뜬다.**
→ `GET /orders` 기본 필터를 **미전환만**으로 두고, 전환 성공 토스트에
"카페24 관리자에서 배송 처리해 주세요"를 넣는다.

### R8. 전환된 출고신청이 취소되면 그 미러는 영구히 막힌다

`cancelRequest` 가 재고를 반납해도 `Cafe24Order.fulfillmentRequestId` 는 남아 **다시 전환할 수
없다.** 주소를 잘못 받아 취소하는 건 흔하다.
→ **v1 은 재전환 불가로 확정한다.** 화면에 "취소됨 — 다시 보내려면 단건 신청"을 안내한다.
미러에 `status` enum 을 두고 재전환을 여는 안은 `fulfillment` 모듈의 취소 경로를 건드려야 해서
v1 범위를 넘는다. **의식적 결정이고, 뒤집으려면 그 불변식부터 본다.**

### R9. ⚠️⚠️ 심사자가 우리 앱을 테스트할 방법이 없다

App URL(`brand.klow.kr/studio`)은 **KLOW 로그인 + 활성 구독**이 있어야 들어간다. 카페24 심사자는
둘 다 없으므로 앱을 설치해도 **빈 로그인 화면**만 본다 — "동작 확인 불가"는 거절 사유다.

⚠️ 이 트랙의 어느 단계도 이걸 만들지 않는다. 8단계(제출)에 가서야 드러나면 그때 급하게 만들게
되고, 그 사이 심사 순번이 밀린다. **6단계(운영 배포) 때 함께 준비한다.**

후보 셋(8단계 착수 시 결정):

| 안 | 내용 | 비용 |
|---|---|---|
| **A. 심사용 계정** | 구독 게이트를 통과한 테스트 브랜드 계정 1개를 제출물에 동봉 | 가장 단순. ⚠️ 심사 기간 내내 살아 있어야 하고, 카페24 테스트 몰도 연결돼 있어야 한다 |
| B. 시연 영상 | 전체 흐름을 녹화해 제출 | ⚠️ 카페24가 영상을 대체 수단으로 받아주는지 **미확인** |
| C. 심사자 전용 우회 | 특별 토큰으로 게이트를 비켜가는 경로 | ⚠️ **기각 쪽에 가깝다** — 인증·구독 게이트에 예외 경로가 생기고, 그게 영구히 남는다 |

⚠️ A 를 고르면 그 계정은 **구독 결제를 실제로 태운 상태**여야 한다(`BrandSubscription.status='active'`
가 노출·판매 게이트다). 어드민에서 수기로 만들 수 있는지부터 확인할 것.

## 8. 단계 분할

⚠️ **첫 두 단계만 정밀하게 쓴다.** 뒤 단계의 전제는 앞 단계가 끝나야 확정되고,
**틀린 명세는 없는 명세보다 나쁘다**([PROGRESS §1](../../PROGRESS.md) 절차 5번).
특히 **2-2 에서 카페24 주문 API 를 실제로 때려봐야** 품목 단위 상태(§4-D)와 응답 모양이 확정되고,
그게 4단계 스펙의 전제다.

### ⚠️ 번호 순서 ≠ 실행 순서 — 자격증명 대기 동안 앞당기는 세 단계

2-2 부터는 자격증명이 필요한데(G2) 0단계가 사용자 작업이라 **대기가 생긴다.** 그 사이에
**카페24 API 를 한 번도 부르지 않는 단계**를 앞당긴다. 2026-09-23 사용자 결정.

| 실행 | 단계 | 왜 지금 되나 |
|---|---|---|
| 1 | **4-0** 출고신청 목록 서버 기간 필터 | 카페24와 무관한 3PL 부채(R3). **4-1 유입이 켜지기 전에** 끝나 있어야 한다 |
| 2 | **5-1** 브랜드 화면 — 연동 | 붙일 엔드포인트가 2-1 에서 이미 생겼다. ⚠️ **4-2 보다 먼저**여야 한다(아래) |
| 3 | **3-1** 매핑 CRUD | 우리 테이블만 읽고 쓴다. 외부 호출 0 |

⚠️⚠️ **자격증명이 도착하면 그 즉시 2-2 로 전환한다.** 위 셋은 OAuth 코드 **위에 쌓이지
않아서**(DB·UI 축이라) 예외인 것이지, G2 가 느슨해진 것이 아니다. **3-2·4-1·4-2 는 그대로
2-2 뒤다** — 실행해 보지 않은 OAuth 위에 또 한 겹을 쌓으면 어느 층이 틀렸는지 모른다.

⚠️⚠️ **5-1 은 4-2 보다 반드시 먼저 나간다.** `Cafe24Connection.defaultCountryCode` 를 고르는
화면이 5-1 이고, 그게 없으면 **비-KR 몰의 주문이 전부 `KR` 로 채워진 채 창고로 나간다**
(2-1 이 DB 기본값 `KR` 로 두고 왔다).

### 0. 카페24 개발자센터 앱 생성 (사용자 작업 — 코드 없음 · **2-2 의 선행 조건**)

⚠️ **이 단계를 기다리지 않는다** (2026-09-23 사용자 결정 — 개발자센터 가입에 하루쯤 걸린다).
1단계와 2-1 은 자격증명 없이 썼고, 대기 중에는 **4-0 → 5-1 → 3-1** 을 앞당긴다(위 표).
그래도 **2-2 는 이것 없이 시작하지 않는다.**
**2-2 를 시작할 때까지 도착하면 된다**(G2).

- **할 일**: 개발자센터 계정 → 앱 생성(Web) → 권한 `Orders/read`·`Products/read` 추가
  → redirect URI 등록 → 테스트 쇼핑몰 1개 연결
- **redirect URI**: ⚠️⚠️ **로컬 `http://localhost:4000/...` 은 등록할 수 없다**(§2-A 실측) —
  개발자센터가 HTTPS 만 받고 IP 도 거부한다. **HTTPS 터널 도메인**(cloudflared/ngrok)과
  운영 `https://api.klow.kr/v1/brand/cafe24/callback` 을 등록한다(최대 10줄)
- **완료 기준**: `client_id`·`client_secret` 확보 + **§2 의 A·D 를 실측값으로 채움**
  (B 는 실응답이 필요해 2-2 로 넘어갔다)
- ⚠️⚠️ **D 를 가장 먼저 본다** — 심사 요건에 "앱 실행 화면(iframe)"이 포함되면 §7 R1 의 회피안이
  무너져 계획을 다시 짜야 한다. 코드를 많이 쓴 뒤에 알면 그만큼 버린다
- **스키마·데이터 위험**: 없음

**실측 결과는 §2-A 에 있다.** 요약: 앱 `KLOW 해외배송 출고연동`(Web) · Korea 스토어 ·
권한 3줄(기본 `Apps` + `Orders/read` + `Products/read`) · **D 는 "포함되지 않음"** ·
그리고 **redirect URI 의 HTTPS 제약**이 이 단계의 가장 큰 수확이다.

### 1. 스키마 + 마이그레이션

- **읽을 것**: 이 문서 `§4` 전체, `klow_server/prisma/schema.prisma` 의 `FulfillmentRequest`·
  `BrandInventoryItem`·`InstagramConnection` 블록
- **건드리는 레포 · 배포 순서**: klow_server 만. **배포 없음**(마이그레이션만)
- **스키마·데이터 위험**: `CREATE TABLE` ×4 + `CREATE TYPE` ×1 + `ADD COLUMN` ×1(`source`,
  `NOT NULL DEFAULT` → rewrite 없음) + 기존 3테이블에 **FK `ADD CONSTRAINT`**.
  DROP 0건 · 백필 없음 → **롤링 안전**.
  ⚠️⚠️ **DB 브랜치를 새로 파지 않는다 — `ep-floral-sun` 을 이어 쓴다**(G3). 3PL 마이그레이션이
  거기에만 있어서, staging 기준선에서 새로 파면 `FulfillmentRequest` 가 없어 FK 가 깨진다.
  ⚠️ **git 브랜치도 새로 파지 않는다 — `feat/3pl-fulfillment` 에 이어서 커밋한다**(§1-A)
- **할 일**: `§4` 의 4모델 + `FulfillmentSource` enum + `FulfillmentRequest.source` →
  역관계 필드 추가 → `npx prisma migrate dev --name add_cafe24_fulfillment`
- **완료 기준**: `npm run typecheck`(tsconfig **2개**) 통과 · 마이그레이션 SQL 에 **`DROP` 0건**
  확인 · `Cafe24ProductMap.productId` 가 **Cascade**, `Cafe24Order.fulfillmentRequestId` 가
  **SetNull** 인지 SQL 에서 확인 · 4테이블 생성 확인
- **불변식**: G3 · §1-A

### 2-1. 서버 — OAuth 왕복

- **읽을 것**: 이 문서 `§3`·`§5`·`§7 R1·R2`, `klow_server/src/modules/instagram/` 8파일,
  `docs/server/modules/instagram.md`
- **건드리는 레포 · 배포 순서**: klow_server 만
- **스키마·데이터 위험**: 없음
- **할 일**
  - `src/modules/cafe24/` 신설 — `cafe24-crypto.ts` · `cafe24-oauth-cookies.ts` ·
    `cafe24.client.ts`(뼈대) · `brand-cafe24-connect.controller.ts` · `brand-cafe24.controller.ts`
    (`GET`/`DELETE /connection`) · `cafe24.service.ts` · `cafe24.module.ts`
  - env: `CAFE24_CLIENT_ID` · `CAFE24_CLIENT_SECRET` · `CAFE24_BRAND_CALLBACK_URL` ·
    `CAFE24_TOKEN_ENCRYPTION_KEY`(base64 32바이트) · (선택) `CAFE24_API_VERSION`.
    ⚠️ **`.env.example` 에도 넣는다** — META_* 가 거기 빠져 있는 선례를 반복하지 않는다
  - `common/origin-exempt.ts` 에 `/v1/brand/cafe24/callback` + **그 스펙의 긍정/부정 목록 갱신**
  - **R2 SSRF 가드**(mall_id 정규식 + hostname 재확인) · **R6 5개 한도 가드**
- **완료 기준** — ⚠️ **자격증명 없이 여기까지 온다**(G2). 실왕복은 2-2 로 미룬다
  - `npm run typecheck`(tsconfig 2개) · `npm run test:e2e` 통과(cron 은 아직 10개)
  - 부팅 라우트 수 실측(361 → 365 예상)
  - `GET /connect` 가 만드는 authorize URL 을 **로그로 찍어 눈으로 검증** — 호스트가
    `{mall_id}.cafe24api.com` 이고 `state`·`redirect_uri`·`scope` 가 붙는지
  - **R2 SSRF 가드 단위 테스트** — `evil.com`·`..`·`@` 가 거절되는지. ⚠️ 이건 외부 호출이
    없어 자격증명 없이 잠글 수 있고, **가장 먼저 잠가야 하는 것**이다
- ⚠️ **이 단계가 끝나도 OAuth 는 한 번도 실행되지 않았다.** 2-2 전까지는 "동작한다"고 적지 않는다
- **불변식**: §1-A

### 2-2. 서버 — OAuth 실왕복 + 토큰 갱신 직렬화

⚠️⚠️ **여기서부터 0단계 산출물이 필요하다**(G2). 자격증명이 아직이면 이 단계를 시작하지 말고
3단계(매핑 API)의 **순수 로직 부분**을 먼저 하거나 멈춘다 — 실행해 보지 않은 OAuth 코드 위에
또 한 겹을 쌓으면 나중에 어느 층이 틀렸는지 모른다.

- **읽을 것**: 이 문서 `§6` 전체, `fulfillment.service.ts` 의 `lockInventory`
- **할 일**: `cafe24-token.ts`(§6 스펙) · `cafe24-token-refresh.cron.ts` ·
  `cafe24.client.ts` 의 **429 분기**(R5) · `GET /api/v2/admin/orders` 첫 실호출로 응답 모양 확인
- **완료 기준**
  - **실제 테스트 몰로 1회 왕복**: 연결 → `GET /connection` `connected:true` →
    `DELETE /connection` → `connected:false` (2-1 에서 미룬 것)
  - ⚠️ **토큰 만료 경로를 실제로 확인한다** — `accessTokenExpiresAt` 을 과거로 수동 수정한 뒤
    API 호출이 성공하는지(= lazy refresh 동작)
  - ⚠️ **동시 요청 2개로 경합을 확인한다** — 둘 다 성공하고 토큰이 한 번만 회전하는지
  - **cron 10 → 11**: `test/app.e2e-spec.ts` 의 개수·이름 목록을 함께 고치고 통과
  - **§4-D 의 품목 단위 필드(`order_item_code`·품목 상태)를 실응답으로 확인**하고 §2 B 를 채움
  - `docs/server/modules/cafe24.md` 신규 + `docs/server/README.md` 모듈 수 갱신

### 4-0. 서버+브랜드 — 출고신청 목록 기간 필터 (R3) · **자격증명 무관**

§7 R3 를 단계로 승격한 것이다. 카페24 API 를 부르지 않으므로 0단계와 무관하게 지금 한다.
⚠️ **4-1(주문 불러오기)이 켜지기 전에 끝나 있어야 한다** — 유입이 시작되면 하루 수십 건이라
몇 주 만에 상한을 넘고, 넘는 순간 오래된 건이 **조용히** 안 보인다.

- **읽을 것**: `server/modules/fulfillment.md` 의 브랜드 목록 절, 이 문서 `§7 R3`,
  `klow_brand .../studio/_components/tabs/inventory/RequestsPanel.tsx` 머리말 주석(13~18행)
- **건드리는 레포 · 배포 순서**: **klow_server → klow_brand**
  ⚠️ 뒤집으면 **조용한 strip** 이다 — zod object 는 모르는 키를 **버린다**. 구 서버는 400 을 내지
  않고 그냥 기간을 무시한 최신 200건을 돌려주므로, 화면은 "필터가 먹었다"고 믿는다
- **스키마·데이터 위험**: **없음.** ⚠️ **인덱스도 추가하지 않는다** — 기존
  `@@index([brandId, status])` 로 브랜드 축이 먼저 좁혀지고 브랜드당 행 수가 작다. 정렬이 느려지면
  그때 `@@index([brandId, createdAt])` 를 **독립 단계로** 뗀다(마이그레이션은 독립 단계 규칙)
- **할 일**
  - **klow_server**
    - ⚠️⚠️ **`FulfillmentListQuery` 에 직접 넣지 말 것.** `AdminFulfillmentListQuery` 가 그걸
      extend 하므로, 어드민이 **받고도 쓰지 않는 필드**가 생긴다 = settlement·shipping-rates 에
      남아 있는 **미작동 반쪽 구현**의 재현이다. **브랜드 전용
      `BrandFulfillmentListQuery = FulfillmentListQuery.extend({ since, until })`** 를 새로 만든다
    - ⚠️ 어드민까지 하려면 **세 곳(`AdminFulfillmentListQuery` · `AdminFulfillmentExportInput` ·
      `adminWhere`)을 함께** 고쳐야 한다 — *"어드민 목록·내보내기가 같은 필터를 본다. 두 곳이
      갈리면 화면에서 센 건수와 실제로 나가는 건수가 다르다"*(서비스 주석). **이 단계 범위 밖**
    - `listRequestsForBrand` 의 where 에 `createdAt` 범위. 경계는 **KST**(`common/kst-time.ts` 재사용),
      `until` 은 **그날 끝까지**(= +1일 exclusive)
    - ⚠️ **상태별 건수를 서버가 함께 돌려준다**(`groupBy status`). 지금 상태 칩 건수는 클라 배열에서
      세는데, 기간이 서버로 가면 그 값은 **`take` 상한 안에서만 센 수**가 된다 — 필터를 옮기면서
      건수를 안 옮기면 **틀린 숫자가 화면에 남는다**
  - **klow_brand** — `RequestsPanel`·`StockPanel` 의 `period` 를 서버 파라미터로 보내고 건수는
    서버값을 쓴다. ⚠️ `qk.fulfillmentRequests` **쿼리키에 기간이 들어가야** 캐시가 안 섞인다.
    `REQUEST_TAKE` 머리말 주석(“200건을 넘기면 서버에 since/until 을 붙일 차례다”)을 **결과로 교체**
- **완료 기준**
  - `take=1` 로 줄여 호출해 **기간 필터가 서버에서 먹는지** + **상태 칩 건수가 페이지 크기와
    무관한지** 확인(실데이터가 200건 미만이라 이게 유일한 재현 수단이다)
  - `npx jest src/modules` 전체 통과 · klow_brand `npm run build`
  - ⚠️ **어드민 출고신청 목록의 건수와 내보내기 건수가 여전히 일치**하는지 눈으로 확인
    (= 어드민을 안 건드렸다는 확인)

### 5-1. 브랜드 화면 — 연동 · **자격증명 무관**

⚠️⚠️ **4-2(전환)보다 먼저 나간다.** `defaultCountryCode` 를 고르는 화면이 여기이고, 없으면
**비-KR 몰의 주문이 전부 `KR` 로 채워진 채 창고로 나간다**(2-1 이 DB 기본값으로 두고 왔다).

- **읽을 것**: `server/modules/cafe24.md`, 이 문서 `§5`·`§7 R1·R4·R7`,
  `RequestsPanel.tsx`(액션 툴바·`EmptyState` 로컬 정의), [PROGRESS §9](../../PROGRESS.md) 의 2-1 인계 메모
- **건드리는 레포 · 배포 순서**: klow_server → klow_brand. **배포 없음**(6단계에서 함께 나간다)
- **스키마·데이터 위험**: **없음**
- **할 일**
  - **klow_server** — `PATCH /v1/brand/cafe24/connection { defaultCountryCode }` 하나.
    라우트 **365 → 366**. ⚠️ zod `.default()` 금지 — 클라가 칸을 항상 보낸다.
    ⚠️ 연결 **후에도** 바꿀 수 있어야 한다(몰 운영국이 바뀐다) → connect 쿼리가 아니라 PATCH 다
  - **klow_brand** — 출고신청 서브탭 액션 툴바 **2×2**(기존 2열 grid 에 연동 버튼이 들어간다) ·
    연동 카드 **3상태**(미연동 / 연동됨 / `needsReauth` 배너) · `mallId` 입력 · 국가 select ·
    해제 확인 모달 · 콜백 쿼리(`cafe24_connected` / `cafe24_error` **7종**) 토스트
    - ⚠️ **`EmptyState` 는 `RequestsPanel` 안에 지역 정의돼 있다** — 새 패널에서 쓰려면 끌어올린다
    - ⚠️ **`mallId` 정규식이 클라에도 생기면 정본이 둘이 된다.** 서버
      `CAFE24_MALL_ID_REGEX` 와 **같은 값**이어야 하고, 주석으로 서로를 가리킨다(`slug.ts` 선례)
    - ⚠️ 해제 문구에 **"불러온 주문 중 아직 전환하지 않은 건은 함께 삭제됩니다"** 를 넣는다(R4)
- **완료 기준**
  - 미연동 상태에서 연동 버튼 → `/connect` 가 **카페24 도메인까지 이동**하는지(자격증명이 없으므로
    카페24 에러 화면이 뜨는 것이 정상 — **거기까지가 이 단계의 끝**이다)
  - 국가를 바꾸면 `GET /connection` 응답에 반영
  - klow_brand `npm run build` · klow_server typecheck·e2e(cron 10 불변)
- ⚠️ **실연동 확인은 2-2 다.** 이 단계가 끝나도 "연동이 된다"고 적지 않는다

### 3-2 · 4-1 · 4-2 · 5-2 · 5-3 · 7~8 (제목과 범위만 — 4-0·5-1·6 은 따로 명세한다)

| # | 단계 | 범위 |
|---|---|---|
| **4-0** | **서버+브랜드 — 출고신청 목록 기간 필터(R3)** | **자격증명 무관 · 아래에 정밀 명세.** `since`/`until` 서버 필터 + 상태별 건수 서버 집계 |
| **3-1** | **서버 — 매핑 CRUD** | **자격증명 무관.** `GET/POST /product-maps` · `DELETE /product-maps/:id`(**보낸 줄만** — §5-A) |
| 3-2 | 서버 — 카페24 상품 목록 | `GET /catalog`(페이지네이션·쿼터·429 분기). ⚠️ **자격증명 필요 — 2-2 뒤** |
| 4-1 | 서버 — 주문 불러오기 | `import`(기간 14일·5페이지 상한 · 미러 upsert · §4-E 잘림 처리 · §4-G 재수집 정책) · `GET /orders` · `cafe24-retention.cron.ts`(**cron 11 → 12**) |
| 4-2 | 서버 — 전환 | `convert/preview` · `convert`(⚠️ **G4 락 순서** · §5-D 수량 합산 · 역기록이 재고 차감과 **같은 트랜잭션** · 전환 후 PII 파기) |
| **5-1** | **브랜드 화면 — 연동** | **자격증명 무관 · 아래에 정밀 명세.** 액션 툴바 2×2 · 연결/해제 · `needsReauth` 배너 · **배송 국가 선택** |
| 5-2 | 브랜드 화면 — 매핑 | ⚠️ 가장 어렵다. 패널 폭 ~532px 에서 행당 select 하나 + 검색·페이지네이션. **독립 페이지가 될 수도 있다**(인스타 선례) — 착수 시 판단 |
| 5-3 | 브랜드 화면 — 주문 목록 + 전환 | 불러오기 모달 · 프리뷰 차단 사유 · 유입 배지(`source`) · R7 안내 |
| 7 | 실브랜드 1~2곳 시범 | **5개 몰 한도 안에서.** 심사 전에도 실사용이 된다 |
| 8 | 퍼블릭앱 심사 제출 | **외부 대기.** 심사자는 동작하는 앱을 본다 — 6·7 이 먼저다. ⚠️⚠️ **심사자 접근 수단(R9)을 6단계에서 함께 준비한다** — 없으면 제출 시점에 막힌다 |

### 6. 운영 배포 — **3PL + 카페24 한 번에**

2026-09-23 사용자 결정으로 3PL 7단계가 이 단계에 흡수됐다(G1). **두 트랙이 함께 처음 운영에 나간다.**

- **읽을 것**: 이 문서 `§1-A`, `server/modules/fulfillment.md`·`server/modules/cafe24.md` 의 엔드포인트 표
- **건드리는 레포 · 배포 순서**: **klow_server → klow_admin → klow_brand**
  (뒤집으면 어드민 재고 저장 · 브랜드 출고신청 · `/v1/brand/cafe24/*` 가 전부 404)
- **스키마·데이터 위험**: 마이그레이션 **2개를 순서대로** 적용한다
  1. `20260922070013_add_3pl_fulfillment` — `CREATE TYPE` ×1 + `CREATE TABLE` ×3
  2. `add_cafe24_fulfillment` — `CREATE TABLE` ×4 + `CREATE TYPE` ×1 + `ADD COLUMN` ×1 + FK 3건

  둘 다 DROP 0건 · 백필 없음 → **롤링 안전**. ⚠️ **`staging`·운영 DB 에는 둘 다 아직 없다**
- **할 일**: 세 레포 `feat/3pl-fulfillment` → `staging` 머지(**두 트랙이 그 브랜치 안에 함께 있다**) →
  staging DB 마이그레이션 2개 → staging 배포·확인 → 운영 마이그레이션 2개 → 운영 배포
- **완료 기준** — ⚠️⚠️ **순서를 지킨다. 3PL 왕복이 통과한 뒤에 카페24를 켠다**
  (둘을 동시에 처음 켜면 문제가 났을 때 어느 트랙 때문인지 분리되지 않는다)
  1. **3PL 왕복**: 어드민 브랜드 상세 `재고` 탭 입력 → 브랜드 스튜디오 `재고` 탭에 반영 →
     출고신청 1건 → 어드민 `출고신청` 탭에서 콜로세움 엑셀 내보내기
  2. **카페24 왕복**: 연결 → 매핑 1건 → 불러오기 → 전환 1건 → 그 건이 위 1번의 엑셀에 실림
- ⚠️ 되돌릴 때도 함께다. 카페24만 빼려면 **`DROP TABLE` 이라 롤링 안전하지 않다**(§1-A)
- **불변식**: §1-A

⚠️ **6~8 의 순서가 중요하다.** 심사 제출에는 운영 도메인 redirect URI·개인정보처리방침 URL·
앱 소개가 필요하고, 그것들은 배포가 끝나야 생긴다.

## 9. 다음 트랙 후보 (이 트랙이 일부러 하지 않는 것)

- **송장번호 카페24 되돌려쓰기** — `주문 배송 정보 등록 및 수정` API 는 있다. 막혀 있는 것은 우리
  쪽이다: 콜로세움 회신 방식이 미확정이라([3PL §2 D](../3pl-fulfillment/implementation-plan.md))
  **쓸 값 자체가 없다.** ⚠️ 풀리면 scope 에 쓰기 권한이 늘어 **심사를 다시 받아야 할 수 있다**
- **앱스토어 진입(iframe) 지원** — §7 R1. 3rd-party 쿠키를 우회하는 별도 세션 수립이 필요하다
- **주문 자동 수집(cron) · 웹훅** — import 서비스 메서드를 재사용하면 된다.
  ⚠️ 브랜드 수 × 쿼터와 **안 본 주문의 PII 적체**를 함께 봐야 한다
- **전환 후 취소의 재전환** — §7 R8. `fulfillment` 모듈의 취소 경로를 건드려야 한다
- **카페24 외 채널**(스마트스토어 등) — 미러·매핑 구조가 그대로 일반화된다.
  ⚠️ 그때 `Cafe24*` 이름이 발목을 잡는다. 3PL 이 모델 이름을 **벤더 중립**으로 둔 이유와 같다 —
  두 번째 채널이 정해지는 시점에 rename 하고, **순수 rename 은 `migrate dev` 가 DROP+CREATE 를
  만들므로 수동 SQL 이 유일한 예외**다([`CLAUDE.md`](../../../CLAUDE.md) Prisma 절)
- **KLOW 재고 → 카페24 상품 재고 동기화** — 축이 둘로 갈리면 어느 쪽이 정본인지 즉시 모호해진다.
  하려면 "카페24 재고는 KLOW 가 덮어쓴다"를 먼저 결정해야 한다
