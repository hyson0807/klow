# brand-crm — 브랜드 고객 관리(CRM) + 메일 발송

- **모듈 경로**: `src/modules/brand-crm/`
- **주 클라이언트**: `klow_brand` (`/crm` 탭)
- **데이터 모델**: `BrandCrmNote` · `BrandCrmTemplate` · `BrandCrmEmail` · `BrandCrmOptOut`
  (고객 행 자체는 **저장하지 않는다** — `Order`/`OrderItem`/`ManualSeedingRecord` 에서 파생)

## 왜 만들었나

브랜드는 주로 시딩 탭에서 해외 바이어·크리에이터에게 샘플을 보내는데, **그렇게 보낸 사람들이 어느 화면에도
"사람" 단위로 모이지 않았다**. `GET /v1/brand/shipments/*` 는 PII 를 내려주지만 송장 단위라 "이 사람에게
3월에도 보냈다"를 알 수 없고, `GET /v1/brand/seeding/links` 는 PII 를 아예 안 준다. 시딩은 한 번 보내고
끝나는 게 아니라 후기를 받고 다시 보내는 반복 관계인데 브랜드에게 그 명단도 연락 수단도 없었다.

---

## 설계의 뼈대

### 1. 고객 목록은 저장하지 않고 파생한다

`BrandCustomer` 실체 테이블이 **없다**. 신원·이력은 이미 `Order` 에 전부 있고, 복제하면 동기화 코드가 생겨
곧 갈린다(`SeedingLink.recipientInstagram` 등 dormant 미러가 그 선례). 저장하는 건 **브랜드가 직접 쓴 것**
뿐이라 백필이 필요 없고 배포 즉시 과거 주문 전부가 목록에 뜬다.

### 2. `customerKey` — 동일인 판정 (`customer-key.ts`)

주문마다 **정확히 하나로 확정되는 문자열**이 곧 고객의 신원이다:

```
e:{email}  →  p:{iso2}:{phone}  →  a:{합성주소}
```

- 원시 정규화는 `orders/recipient-match.ts` 를 **재사용**한다(시딩 중복신청 차단·중복수령 경고와 같은 출처).
- ⚠️ **OR 매칭(`isSameApplicant`)을 쓰지 않는다** — 전이적이지 않아(A~B, B~C 인데 A≁C) union-find 가
  필요해지고, 온 가족이 같은 주소를 쓰면 한 명으로 뭉갠다. 사다리는 답이 하나라 그룹핑이 곧 끝난다.
- ⚠️⚠️ **실측: 주문은 예외 없이 `e:` 가지를 탄다.** `Order.email` 이 non-null 이고 생성 경로 셋 모두 빈
  값을 400 으로 막는다(web `orders.service.ts:321` · onsite `:553` · 시딩 zod). `p:`/`a:` 는 **email
  컬럼 자체가 없는 `ManualSeedingRecord` 전용**이고 주문 쪽은 legacy fail-safe 다.
- ⚠️ **전화 키에 국가코드를 섞는다.** `normalizePhone` 은 "숫자만 남기고 끝 10자리"인데 그건 *한 시딩 링크
  안* 중복 차단용 규칙이다. 브랜드 전체 고객 병합으로 그대로 승격하면 다른 나라 두 사람이 같은 키가 되고,
  그 오병합의 결과는 **A 에게 갈 메일이 B 에게 가는 것**이다.
- **알려진 한계**: 같은 사람이 이메일을 바꿔 신청하면 두 명으로 보인다. v1 은 병합하지 않는다.

### 3. 브랜드 귀속

정본 규칙은 `orders/item-brands.ts` — **`productId` 가 있으면 `Product.brandId`, 없으면
`OrderItem.brandId` 스냅샷**(우선순위지 OR 가 아니다). 실측상 `OrderItem.brandId` 는 **시딩 라인에만**
채워진다(web `orders.service.ts:466` · onsite `:643` 생성 코드에 그 키가 아예 없다).

조회는 두 축의 OR 이다:

```
items.some.OR[ productId in (브랜드 제품), (productId=null AND brandId=브랜드) ]
  OR  shipments.some.brandId = 브랜드
```

⚠️ **두 번째 축을 빼면 안 된다** — `Shipment.brandId` 는 발급 시점 **동결 컬럼**이라 나중에 제품이 하드
삭제돼도(`products.service.ts` 에 실제 `product.delete` 가 있다) 살아남는다. 라인 축만 쓰면 "송장은 나갔는데
제품이 삭제된 과거 고객"이 통째로 사라진다. relation 필터라 큰 `in` 절 없이 `Shipment(brandId)` 인덱스를 탄다.

신규 `OrderItem.@@index([brandId])` 는 **첫 번째 축의 시딩 분기 전용**이다(제품 분기는 기존
`Product(brandId)` + `OrderItem(productId)` 가 받는다).

### 4. 주문 필터

```
paymentStatus = 'paid'  AND  status <> 'cancelled'
```

- ⚠️ `settlement.service.ts` 의 `SETTLEABLE_ORDER_WHERE` 를 **상속하면 안 된다** — 그건 "돈 받을 대상"이라
  무가 시딩을 의도적으로 제외하는데, CRM 은 무가 시딩 수령자가 핵심 모집단이다.
- ⚠️ **시딩이 전부 `paid` 로 박히는 게 아니다.** 브랜드 결제 시딩만 `paid + processing` 으로 생성되고
  **고객 결제 시딩은 `paymentStatus` 기본값 `pending`** 이다 — 이 조건이 결제 대기(reserved)·실패(released)
  신청자를 걷어내는 유일한 장치다.
- ⚠️ **취소된 시딩은 `paymentStatus` 로 못 거른다.** 송장 취소(`shipments.service.ts:775`)는
  `Order.status=cancelled` + `SeedingClaim.state=cancelled` 만 쓰고 `paymentStatus` 는 `paid` 로 남긴다
  (일반 주문 환불이 `refunded` 로 전이하는 것과 다르다). `status <> cancelled` 가 선택이 아닌 이유다.

### 5. 채널 3분할 — `isSeeding` 을 먼저 본다

```
시딩 : isSeeding = true
현장 : isSeeding = false AND channel = 'onsite'
구매 : isSeeding = false AND channel = 'web'
```

⚠️⚠️ **`Order.channel` 기본값이 `web` 이고 시딩 주문 생성 경로 둘 다 `channel` 을 지정하지 않는다** — 즉
모든 시딩 주문의 channel 이 `web` 이다. channel 만 보고 나누면 시딩 수령자가 "일반 구매자"에 통째로 섞여
**같은 사람이 두 번 세어진다**(`orders.service.ts:191` 이 같은 경고를 남겼다).

### 6. 공개 id 는 불투명 해시

목록 DTO 의 `id` 는 `sha256(brandId + ' ' + customerKey)` 앞 32자다. ⚠️ **base64url 로는 부족하다** —
가역이라 `e:foo@bar.com` 이 URL·액세스 로그·Sentry breadcrumb 에 사실상 평문으로 남는다
(`Order.visitorId` 가 난수인 것이 이 레포의 PII 취급 결이다). 단방향이라 서버는 id → key 를 되돌리지 못하고
그 브랜드의 키 집합을 계산해 해시로 맞춘다(어차피 목록 계산과 같은 스캔이다). `brandId` 를 섞어 브랜드 간
id 가 겹치지 않게 한다.

### 7. 수기 시딩 기록 (`manual-record-contact.ts`)

`ManualSeedingRecord.data` 는 `{ fullName, phone, address, postalCode, fields[] }` 이고 **email 컬럼이
없다**. 이메일이 없으면 그 고객에게 메일을 한 통도 못 보내므로 기능의 절반이 죽는다 — 다행히 임포트가
매핑되지 않은 컬럼을 전부 `fields[]`(label=원본 헤더)로 보존한다.

- **이메일**: 라벨이 이메일 열로 보이고 값도 이메일 모양이면 채택 → 없으면 레코드 전체에서 이메일 모양 값이
  **정확히 하나일 때만** 채택 → 둘 이상이면 **포기한다**(찍어서 보내는 것보다 못 보내는 게 낫다).
- **인스타 핸들**: 라벨이 인스타 열이면 `ID` 열을 `Link` 열보다 우선해 채택하고, `@` 제거 + 소문자로
  `SeedingClaim.recipientInstagram` 과 같은 모양으로 맞춘다.
- ⚠️ **수기 기록은 주소로는 KLOW 주문과 절대 합쳐지지 않는다** — 주문 쪽 주소 키는 `국가|우편|주소1|주소2|도시`
  5칸 합성인데 수기 쪽은 자유 문자열 하나이고 국가·도시가 없다. 합쳐지는 경로는 이메일, 그다음 전화뿐이다.
  버그가 아니라 데이터의 한계다.

> 실측(2026-08, dev): 구글폼 수출 수기 기록 81건에서 이메일 81/81 · 인스타 핸들 81/81 추출.

---

## 라우트

### brand-crm.controller.ts (`@Controller('v1/brand/crm')`)

> 전체 라우트 `BrandGuard` + `requireBrandId`.

| Method | Path                          | 기능 |
|--------|-------------------------------|------|
| GET    | `/customers`                  | 고객 목록 → `{ data, total, truncated, facets }` |
| GET    | `/tags`                       | 이 브랜드가 쓴 태그 전체(자동완성) |
| GET    | `/templates`                  | 메일 템플릿 목록 |
| POST   | `/templates`                  | 템플릿 생성 |
| PATCH  | `/templates/:tid`             | 템플릿 수정 |
| DELETE | `/templates/:tid`             | 템플릿 삭제 |
| POST   | `/emails`                     | 발송 (1~200명) — `THROTTLE_TIGHT` 5회/분 |
| GET    | `/emails/:eid`                | 보낸 메일 한 통의 발송본(제목·본문·받는 사람·상태) |
| GET    | `/customers/:id`              | 고객 상세 + 타임라인(발송 이력 포함) |
| PATCH  | `/customers/:id`              | 태그·메모 저장(lazy upsert) |

⚠️ 정적 라우트(`tags`·`templates`·`emails`)를 `customers/:id` **앞에** 선언한다
(`shipping-countries/export` 선례).

목록 쿼리: `q`(이름·이메일·인스타 부분일치) · `country`(ISO2) · `channel` · `tag` · `reviewed` ·
`optedOut` · `take`(≤200) · `skip`.

### public-crm.controller.ts (`@Controller('v1/crm')`)

> 가드 없음 — 수신자는 KLOW 계정이 없다. 인증은 링크의 HMAC 서명이 담당한다.

| Method | Path            | 기능 |
|--------|-----------------|------|
| GET    | `/unsubscribe`  | **확인 페이지만** 그린다(상태 변경 없음) |
| POST   | `/unsubscribe`  | 실제 수신거부 반영 → HTML 200 |

⚠️⚠️ **GET 이 상태를 바꾸면 안 된다.** 기업 메일 게이트웨이·보안 스캐너가 본문 링크를 미리 열어 보는 일이
흔해서, GET 에서 곧바로 해지하면 **읽지도 않은 수신자가 자동으로 수신거부된다.**

⚠️⚠️ POST 에는 Origin 헤더가 없다(메일 클라이언트가 부른다) — `common/origin-exempt.ts` 에
`/v1/crm/unsubscribe` 가 **있어야 한다.** 빠지면 원클릭 수신거부가 전부 403 이 되고, 수신자에게 남는 유일한
선택지가 스팸 신고가 된다 — 그 신고는 공유 발신 도메인 전체의 평판을 깎는다.

---

## 메일 발송

### 발신 도메인 분리 (중요)

⚠️ 브랜드 마케팅 메일을 기존 `EMAIL_FROM=KLOW <no-reply@klow.kr>` 로 보내면 **한 브랜드의 스팸 신고가
OTP·주문확인 메일의 도달률까지 끌어내린다.** `CRM_EMAIL_FROM_ADDRESS`(기본 `hello@mail.klow.kr`)를 Resend 에
**별도 도메인으로 검증**해 쓴다(SPF/DKIM/DMARC 별도).

- `From` = `${브랜드명} <hello@mail.klow.kr>` (표시명만 브랜드, 헤더 인젝션 문자는 제거)
- `Reply-To` = `BrandUser.email` — **없으면 발송을 막는다**(답장 갈 곳이 없고 스팸 판정도 나빠진다)
- 브랜드당 **일 300건** · 요청당 **200명**. ⚠️ 상한은 **env 가 아니라 코드 상수**다(이 레포엔 env 수치 상한이
  0건이고 `=0` 오타 하나가 전 브랜드 발송을 조용히 막는다).

### 큐 + 인라인 선발송

1. `POST /emails` 가 수신자별 `BrandCrmEmail(status:'queued')` 행을 **먼저 적재**한다.
2. 같은 요청에서 **최대 20건 · 8초 예산**으로 인라인 드레인 → 1:1 발송은 즉시 결과가 나온다.
3. 남은 건은 `crm-email-dispatch.cron.ts`(**매분**, `LIMIT 50`, 재진입 가드)가 가져간다.
4. 실패는 백오프 **2분→10분→30분**, 상한 3회. ⚠️ **카운터는 호출 前에 올린다**(도중에 죽어도 같은 건을
   무한히 다시 집지 않는다 — `shipment-retry` 와 같은 규칙).

⚠️ **fire-and-forget 금지** — 이 레포는 결제 확정이 fire-and-forget 이라 조용히 유실됐던 이력이 있다
(2026-08-17). 큐 행이 곧 영수증이다.

### 템플릿 변수

`instagram.service.ts renderTemplate` 과 **같은 단일 중괄호 규약**: `{name}` `{brand}` `{country}`
`{product}` `{link}`.

- ⚠️ `{name}` 폴백은 **한국어가 아니라 이메일 local-part** 다 — 수신자 대부분이 해외 크리에이터이고 본문도
  브랜드가 그 나라 말로 쓴다(인스타 DM 의 `고객` 폴백과 의도적으로 다르다).
- ⚠️ `{country}` 는 `Order.country`(**영문** 표시명)다. 화면에 쓰는 `ShippingCountry.nameKo` 는 한국어라
  본문에 끼면 문장이 깨진다.
- ⚠️ 본문은 **평문만** 받는다. HTML 을 허용하면 KLOW 소유 발신 도메인 + 브랜드 임의 마크업이 곧 피싱
  벡터가 된다. 렌더는 `치환 → escapeHtml → nl2br` 순서이고 이 순서가 스펙으로 잠겨 있다.

### 발송 이력 열람

발송 이력은 **별도 목록 라우트가 아니라** `GET /customers/:id` 의 타임라인에 주문과 함께 섞여
내려간다(최근 50통, `createdAt desc`). 각 메일 줄은 `emailId` + `emailStatus` 를 달고 오고,
화면은 그걸 눌러 `GET /emails/:eid` 로 본문 한 통을 받는다.

- 타임라인에 **본문을 싣지 않는다** — 50통 × 최대 5000자면 고객 상세 응답 하나가 수백 KB 다.
- `emailStatus` 는 예전에 DB 에서 select 해 놓고 매핑에서 버리던 값이다. 그래서 **실패한 메일이
  성공한 것과 화면에서 구분되지 않았다.**

⚠️⚠️ **`buildHtml()` 결과를 브랜드에게 돌려주면 안 된다.** 그 HTML 푸터에는
`unsubscribeUrl(brandId, toEmail)` 로 서명된 **살아 있는** 수신거부 링크가 박혀 있어서, 브랜드가
미리보기에서 그걸 누르면 **자기 고객이 실제로 수신거부된다**(`public-crm.controller.ts` 의 POST 는
가드 없이 HMAC 서명만 본다). 그래서 응답은 `bodyRendered` **평문**만 싣고, klow_brand 는
`whitespace-pre-wrap` 으로 그린다 — `dangerouslySetInnerHTML` 경로가 아예 생기지 않는다.
회귀 스펙이 응답 키 목록을 통째로 잠가 이 결정이 조용히 뒤집히지 않게 한다.

⚠️ 소유 검증은 `findFirst({ where: { id, brandId } })` 뿐이고 실패는 `Forbidden` 이 아니라
**`NotFound`** 다(id 를 넣어 보며 남의 브랜드 메일 존재를 열거하지 못하게).

### 수신거부

- 모든 CRM 메일 하단에 링크 자동 삽입 + RFC 8058 `List-Unsubscribe` / `List-Unsubscribe-Post` 헤더.
- 토큰은 `orders/guest-order-token.ts` 를 본뜬 **무상태 HMAC**(`base64url(payload).hex(hmac)`) — DB 컬럼도
  만료 스윕도 없다. **만료를 두지 않는다**(수신거부 링크는 받은편지함에 영구히 남는다).
- 옵트아웃 수신자는 **조용히 건너뛰지 않고** 응답 `skipped` 에 `opted_out` 으로 보고한다.
- 스코프는 **브랜드 단위** — A 브랜드를 거부해도 B 브랜드 메일은 계속 받는다.

---

## 성능

⚠️ **SQL `LIMIT` 으로 페이지네이션할 수 없다.** 고객 행은 파생이고 태그·메모는 별도 테이블이며 수기 기록은
앱에서 합쳐진다 — DB 에서 자른 뒤 앱에서 합치면 총계와 페이지가 조용히 거짓말을 한다
(`orders.service.ts:178` 이 같은 함정을 주석으로 남겼다). 그래서 브랜드 스코프를 전량 로드해 앱에서
그룹핑·필터·정렬·페이징하고, 상한(`ORDER_SCAN_CAP`/`MANUAL_SCAN_CAP` 각 5000)에 걸리면 응답이
`truncated: true` 로 **말한다** — "절단은 조용한 왜곡이다".

raw SQL 을 쓰지 않는다. 이 레포의 `$queryRaw` 는 차트/집계 전용 + `FOR UPDATE` 락 2건뿐이고 CRM 목록은
둘 다 아니다. Prisma-only 선례가 `orders.service.ts:204`·`settlement.service.ts:252` 에 이미 있다.

### 병목은 CPU 가 아니라 **직렬 왕복 수**다 (2026-09-02)

전량 로드라는 말 때문에 오해하기 쉬운데, **N+1 은 없다** — 요청당 Prisma 호출 수는 고객 수와
무관하게 고정이고 루프 안에서 DB 를 치는 곳은 0건이다. 실측 규모(주문 686건·송장 431건, 전 브랜드
합)에서 그룹핑 CPU 는 1ms 미만이다. 지배적인 것은 Neon(싱가포르) **왕복 단계 수**다.

⚠️ Prisma 는 `relationJoins` 프리뷰가 꺼져 있어 `order.findMany` 하나가 **부모 SELECT → `items`
∥ `seedingClaim`** 으로 쪼개진다. 즉 "Prisma 호출 6회"는 왕복 수가 아니다.

`loadBrandScope()` 가 그 단계를 **2단으로 묶는다.** `productIds` 에 의존하는 건 주문 조회 하나뿐이라
나머지(수기기록·노트·수신거부·국가명)를 전부 1단에 몰아넣었다:

```
1단: product ∥ manualSeedingRecord ∥ brandCrmNote ∥ brandCrmOptOut ∥ shippingCountry
2단: order  (→ 엔진이 items ∥ seedingClaim 을 뒤이어 발사)
상세만 3단: brandCrmEmail  (customerKey 를 알아야 해서 구조적으로 뒤다)
```

- ⚠️ **`decorate()` 는 DB 를 치지 않는 순수 함수다.** 거기에 `await` 를 하나라도 되돌리면 왕복이
  한 단 늘고, 상세처럼 acc 가 1개인 경로에서도 브랜드 전 노트를 다시 읽게 된다.
- ⚠️ **`shippingCountry` 는 `iso2 in (...)` 없이 전량을 읽는다.** `in` 절은 주문 결과에 의존해서
  왕복을 한 단 강제했다. 233행 × 2컬럼(≈6KB)이라 그 한 단을 없애는 값이 훨씬 크다.
- ⚠️ **`ORDER_SELECT.items` 에 브랜드 필터가 걸린다**(`orderSelect()` 팩토리). 예전엔 없어서
  멀티브랜드 주문의 남의 라인까지 받아 놓고 앱에서 버렸다. 앱단 `isBrandOwnedItem` 필터는
  **그대로 둔다** — 같은 헬퍼(`orders/item-brands.ts`)를 쓰므로 규칙이 갈릴 수 없다.

### 상세 조회는 **대상 고객의 타임라인만** 만든다

예전엔 `loadCustomers(brandId, { timeline: true })` 라 게이트가 불리언이었다. 그래서 고객 한 명을
보려고 **브랜드 전 고객**의 타임라인 객체를 만든 뒤 1명분만 남기고 버렸다(최대 1만 건 × 객체 할당).

지금 게이트는 **`opts.timelineFor: ReadonlySet<공개 id>`** 이고, `touch()` 가 고객이 처음 등장할 때
`customerIdOf` 를 **1회만** 계산해 `Acc.id` 에 들고 있다가 그 집합과 대조한다.

- 부수 효과로 `decorate`·`resolveRecipients` 의 sha256 **재계산이 사라졌다**(같은 값을 두 번 돌렸다).
- ⚠️ **불리언 플래그로 되돌리지 말 것.** 회귀 잠금은 `__tests__/crm-scan-shape.spec.ts` 다.

### 아직 안 한 것 (규모가 커지면)

- **브랜드 스캔 스냅샷의 인메모리 TTL 캐시.** 선례는 `brand-domains/domain-search.service.ts:21-70`.
  ⚠️ 캐시 대상은 **주문 파생분만**이다 — `BrandCrmOptOut`·`BrandCrmNote` 를 캐시하면 안 된다
  (수신거부가 stale 이면 브랜드가 "보낼 수 있다"고 본 200명 중 일부가 발송 응답에서 `opted_out` 으로
  튕겨 나오고, 태그가 stale 이면 방금 저장한 태그로 필터했는데 안 나온다). 게다가 그 둘은 이미 위
  1단 안이라 **캐시해도 왕복이 안 줄어든다 = 이득 0, 리스크 >0.**
  ⚠️ 레플리카가 2 이상이면 캐시가 인스턴스마다 갈려 `updateNote`/`resolveRecipients` 가 방금 뜬
  고객을 404·`not_found` 로 놓칠 수 있다(fail-closed 라 잘못 쓰지는 않는다). 도입 전 레플리카 수 확인.
- **`BrandCrmNote.customerId`(정방향 해시) 컬럼 + 인덱스** — `updateNote` 의 전량 노트 로드 +
  앱 해시 비교가 단일 조회가 된다. 추가 전용 마이그레이션. 지금은 노트 행이 적어 이득이 1왕복 미만.
- **인덱스 추가는 하지 않았다.** 686건 테이블에서는 어떤 인덱스가 있어도 플래너가 seq scan 을 고르고
  ms 안에 끝난다. 추가 트리거를 대신 못박는다: `pg_stat_statements` 의 `mean_exec_time` 이 20ms 를
  넘거나 브랜드 하나의 주문이 수만 건이 될 때. 후보는 `ManualSeedingRecord(brandId, createdAt)`
  (정렬 제거 효과가 명확)이고, `Order(paymentStatus, status, createdAt)` 은 `paid` 선택도가 낮고
  `status <> cancelled` 가 부정 조건이라 **효과가 의심스럽다 — EXPLAIN before/after 없이 넣지 말 것.**

---

## 환경변수

```bash
CRM_EMAIL_FROM_ADDRESS=hello@mail.klow.kr   # Resend 에 mail.klow.kr 별도 검증 필수
CRM_UNSUBSCRIBE_SECRET=                     # 운영 필수(main.ts fail-closed 부팅 가드)
SERVER_PUBLIC_URL=                          # 미설정 시 EXIMBAY_RETURN_BASE_SERVER 로 폴백
CRM_EMAIL_CRON_ENABLED=                     # 'false' 로만 비활성(기본 on)
```

## 마이그레이션 · 배포

`20260827083149_add_brand_crm` — `CREATE TABLE ×4` + `CREATE INDEX ×7` + `ADD FK ×4` +
`OrderItem.@@index([brandId])`. **추가 전용 → 롤링 배포 안전 · 백필 없음.**

- 라우트 **315 → 325**, cron **9 → 10**(`brand-crm-email-dispatch`).
  (2026-08-28 발송본 열람 라우트가 붙어 지금은 **326**. ⚠️ 예전에 이 줄이 327 이라고 적혀
  있었는데 부팅 실측과 어긋나 실측값으로 정정했다.)
- **배포 전 선행**: Resend 콘솔에 `mail.klow.kr` 도메인 추가 + DNS 등록. 안 하면 발송이 전부 실패한다.
- 배포 순서: **klow_server → klow_brand**(반대면 `/crm` 이 404).

## 회귀 잠금

`brand-crm/__tests__/` — `customer-key.spec.ts`(19) · `crm-template.spec.ts`(20, 수기 연락처 추출 포함) ·
`unsubscribe-token.spec.ts`(8) · `crm-email-queue.spec.ts`(7) ·
`crm-email-detail.spec.ts`(7 — brandId 스코프 · batchSize · **응답에 발송 HTML/수신거부 링크 없음**) ·
`crm-scan-shape.spec.ts`(6 — 스캔의 *모양*: 상세 타임라인이 대상 1명분만 · 목록에 timeline 없음 ·
facets 단일 순회 동치 · **왕복 2단**(product 를 붙잡아 두고 나머지 넷이 이미 발사됐는지 단언) ·
`shippingCountry` 에 `where` 없음 · `items` 브랜드 필터).
⚠️ 왕복 스펙이 없으면 `await` 하나를 되돌려 놓아도 타입도 응답도 그대로라 **아무것도 안 잡힌다** —
느려질 뿐이다.
⚠️ 마지막 스펙의 prisma 스텁은 `where` 와 `select` 를 **둘 다 실제로 적용한다** — 하나라도
무시하면 유출 가드가 아무것도 잡지 못한 채 통과한다.
`common/__tests__/origin-exempt.spec.ts` 에 `/v1/crm/unsubscribe` 케이스 추가.

## 알려진 갭

- 같은 사람이 이메일을 바꿔 신청하면 두 명으로 보인다(수동 병합 UI 없음).
- 하드 삭제된 제품의 과거 주문은 `Shipment` 축으로만 잡힌다 — 송장이 없는 현장 주문이면 사라진다.
- 메일 **열람·클릭 추적 없음**(추적 픽셀·링크 리라이트를 v1 범위에서 뺐다).
- Gmail API 발송(브랜드 지메일에서 직접)은 `email-sender.ts` 어댑터 뒤 2단계 — Google 앱 검증 필요.
  `gmail.send` 는 **sensitive** 스코프라 CASA 보안심사는 없지만, 검증 전엔 refresh token 이 7일마다
  만료돼 운영이 불가능하다.
