# admin-contacts — 어드민 컨택트(시딩 수령인 · 바이어)

- **모듈 경로**: `src/modules/admin-contacts/`
- **주 클라이언트**: `klow_admin` (`고객 > 컨택트` 탭 `/contacts`)
- **데이터 모델**: **없다** — `Order` / `OrderItem` / `SeedingClaim` / `ManualSeedingRecord` 에서 파생
- **읽기 전용**. 스키마 변경·마이그레이션·백필 0건.

## 왜 만들었나

브랜드는 시딩으로 해외 인플루언서·바이어에게 샘플을 보내고, 그 사람들의 신원·연락처·접점 이력이
전부 DB 에 남는다. 그런데 **KLOW 쪽에는 그걸 "사람" 단위로 모아 보는 화면이 없었다.**

- 이웃 `/admin/customers`(가입 회원)는 **`User` 테이블 전용**이다. 시딩 수령인은 게스트라
  `User` 행이 아예 없어 **한 명도 뜨지 않는다**.
- 브랜드용으로는 같은 파생 로직이 이미 있다([brand-crm](./brand-crm.md), klow_brand `/crm`).
  하지만 **브랜드가 자기 고객만** 본다.

즉 플랫폼이 축적한 가장 활용도 높은 명단을 운영팀이 볼 수단이 DB 직접 조회뿐이었다.

## ⚠️ 두 화면의 숫자는 절대 일치하지 않는다

| | `/admin/customers` (가입 회원) | `/admin/contacts` (컨택트) |
|---|---|---|
| 모집단 | `User` — klow_web 가입 계정 | 결제완료·비취소 주문 + 수기 시딩기록에서 파생 |
| 게스트 | 안 보임 | **대부분이 게스트** |
| 시딩 수령인 | 안 보임 | 핵심 대상 |

이건 버그가 아니라 정의다. 화면의 `PageHeader.description` 한 줄이 그걸 설명하는 **유일한 자리**라
지우지 말 것. 사이드바 라벨도 그래서 `회원` → **`가입 회원`** 으로 바꿨다.

---

## 설계

### 1. 재사용 — 규칙을 새로 쓰지 않는다

| 무엇 | 어디 |
|---|---|
| 동일인 판정 사다리 `orderCustomerKey` / `manualCustomerKey` / `customerIdOf` | `brand-crm/customer-key.ts` |
| 정규화 원시함수 | `orders/recipient-match.ts` |
| 수기기록 이메일·인스타 추출 `manualContactOf` | `brand-crm/manual-record-contact.ts` |
| 브랜드 귀속 규칙 `itemBrandIdOf` | `orders/item-brands.ts` |
| 시딩 **진짜** 제품명 | `seeding/seeding-display-name.ts` |
| xlsx 응답 헤더 `sendXlsx` | `common/xlsx-download.ts` |

전부 순수 함수 import 라 **Nest 모듈 배선 변경이 없다**(모듈 31개 · cron 10개 불변).

### 2. 동일인은 브랜드를 가로질러 **한 명**이다

키는 brand-crm 과 같은 사다리(`e:` → `p:` → `a:`)이고, 공개 id 만 스코프가 다르다:

```ts
customerIdOf(ADMIN_CONTACT_SCOPE /* '*admin*' */, key)
```

⚠️⚠️ **같은 사람이라도 어드민 id 와 브랜드 CRM id 는 다르다.** 스코프가 다르니 당연하고 그게
의도다 — 두 화면 사이에서 id 를 넘기지 말 것. (`customerIdOf` 의 첫 인자명은 이 작업에서
`brandId` → `scope` 로 순수 rename 했다. 기존 호출부·스펙은 무변경.)

접점 브랜드는 행의 `brands[]` 로 나열된다. "이 인플루언서에게 A·B·C 가 다 보냈다"가 이 기능의
핵심 가치라 브랜드별로 행을 쪼개지 않는다.

### 3. ⚠️⚠️ DB 왕복은 **2단**이고 그 이상으로 늘리지 말 것

```
1단(7개 병렬): order · product · brand · manualSeedingRecord · shippingCountry · user · seedingLink
2단(3개 병렬): orderItem ∥ seedingClaim ∥ shipment      ← Prisma 가 order 결과를 받고 쏜다
```

⚠️⚠️ **"쿼리 7개 = 왕복 1단"이 아니다.** `relationJoins` 프리뷰가 꺼져 있어 Prisma 는 relation 을
**부모 쿼리 뒤에 따로** 쏜다(실측 총 10쿼리 / 깊이 2). 그래서 중첩을 한 겹 더 파면 그만큼 직렬
단이 늘어난다 — 처음엔 `seedingClaim.link` 를 중첩해 **3단**이었고, 링크를 1단 전량 읽기로 빼서
2단으로 줄였다(실측 390행 · 29KB). **되돌리지 말 것.**

⚠️ 그래도 brand-crm 보다 한 단 적다. 저쪽은 주문 조회 where 가 `productIds`(그 브랜드 제품)에
의존해 `product` → `order` 가 직렬인데, 어드민은 브랜드로 좁히지 않아 `order` 가 1단에 들어간다.

⚠️ 참조 테이블 다섯(`product`·`brand`·`shippingCountry`·`user`·`seedingLink`)을 **`where` 없이
전량** 읽는 것도 같은 이유다 — `id: { in: [...] }` 를 걸면 주문 결과를 기다려야 해서, 작은 테이블
하나 아끼자고 왕복을 한 단 늘리게 된다.

⚠️ `decorate()` 는 **DB 를 치지 않는 순수 함수**다. `await` 를 하나라도 되돌리면 왕복이 늘고,
상세처럼 acc 가 1개인 경로에서도 전 브랜드 사전을 다시 읽는다.

회귀 잠금은 `__tests__/admin-contacts-scan.spec.ts` 의 **"왕복 2단"** 케이스(1단 일곱 개가 전부
발사됐는지)와 **"`seedingClaim` select 에 `link` 를 중첩하지 않는다"** 케이스다 — 타입도 응답도
안 바뀌므로 그 스펙이 없으면 되돌려 놔도 아무것도 못 잡고 느려지기만 한다.

> 실측(2026-09, dev · 주문 289건 · 컨택트 190명): 워엄 조회 **0.7~1.0초**(대부분 Neon 싱가포르
> 왕복) · 내보내기 190행 147KB 0.4초.

### 4. 주문 필터 · 채널 분할 — **정본은 `orders/contact-population.ts` 한 곳**

```ts
CONTACT_ORDER_WHERE = { paymentStatus: 'paid', status: { not: 'cancelled' } }
contactChannelOf(o)  // isSeeding → 'seeding' · channel==='onsite' → 'onsite' · 그 외 'store'
```

⚠️ 예전엔 이 상수와 함수가 brand-crm 과 admin-contacts 에 **복사돼 있고 "같은 값이어야 한다"는
주석으로만** 묶여 있었다. 두 화면이 같은 사람을 놓고 다른 모집단을 보면 대조가 불가능한데,
그 정합성을 지키는 장치가 주석뿐이었다 — `item-brands.ts`·`brand-selects.ts` 가 이미 같은 병을
고치며 만들어진 파일이라 같은 처방을 썼다. 두 모듈이 이제 한 벌을 import 한다.

⚠️ 스코프별로 **달라도 되는** 값(스캔 상한 5000↔10000)은 올리지 않았다.
⚠️ `common/validation/*.ts` 의 채널 zod enum은 여전히 별개다 — `common/` 은 `modules/` 를 import
할 수 없다는 구조 규칙 때문이고, 선택이 아니다.

각 절의 이유는 [brand-crm.md](./brand-crm.md) §4 와 동일하다:

- ⚠️ `settlement.service.ts` 의 `SETTLEABLE_ORDER_WHERE` 를 **상속하면 안 된다**(무가 시딩을
  의도적으로 빼는데, 여기서는 무가 시딩 수령인이 핵심이다).
- ⚠️ `status <> cancelled` 는 선택이 아니다 — 송장 취소는 `paymentStatus` 를 `paid` 로 남긴다.
- ⚠️ `paymentStatus='paid'` 가 고객 결제 시딩의 결제 대기·실패 신청자를 걷어내는 유일한 장치다.

### 5. 채널 3분할 — `isSeeding` 을 **먼저** 본다 (`contactChannelOf`)

```
시딩 : isSeeding = true
현장 : !isSeeding && channel = 'onsite'
구매 : !isSeeding && channel = 'web'
수기 : ManualSeedingRecord
```

⚠️ `Order.channel` 기본값이 `web` 이고 시딩 주문 생성 경로 둘 다 channel 을 지정하지 않는다.
channel 만 보면 **시딩 수령인이 일반 구매자에 통째로 섞인다.**

### 6. 브랜드 귀속 — 축이 둘이다

정본은 `orders/item-brands.ts` 이고, 어드민용 역방향 헬퍼 `itemBrandIdOf(item, brandIdByProduct)`
를 **그 파일에** 추가하면서 기존 `resolveItemBrands` 도 그 헬퍼를 쓰게 고쳤다(안 그러면 "규칙을
한 번만 적는다"는 그 파일의 존재 이유가 파일 **안에서** 깨진다). 규칙은
**`productId` 우선, 없을 때만 `OrderItem.brandId` 스냅샷**(우선순위지 OR 가 아니다).

⚠️ **`Shipment.brandId` 축을 반드시 함께 본다.** 발급 시점 **동결 컬럼**이라 제품이 하드
삭제돼도 살아남는다 — 빼면 "송장은 나갔는데 제품이 삭제된 과거 고객"의 브랜드가 빈칸이 된다.
어드민은 브랜드로 좁히지 않으므로 where 절이 아니라 `order.shipments` 중첩 select 로 읽는다
(Prisma 가 `items`/`seedingClaim` 과 **병렬로** 발사해 왕복 1단이 유지된다).

⚠️ `Product.brandId` 는 nullable(legacy)이라 맵에 아예 넣지 않는다.

### 7. 회사메일 추정 (`email-domain.ts`)

무료 이메일 제공자 사전에 없으면 `corporate` — 자기 도메인을 가진 조직일 가능성이 높다는
**추정**이다. 목록·요약·필터·도메인 그룹이 이 값을 쓴다.

⚠️⚠️ **접미사·부분일치 매칭을 쓰지 말 것.** `yandex.*`/`mail.*` 같은 suffix 규칙은
`mail.acme.com`(실재하는 회사 메일 호스트)을 개인메일로 오분류해 **바이어를 목록에서 지운다.**
명시 집합만 쓴다(한국·글로벌·중국·일본·동남아·CIS·유럽·미주 주요 무료 제공자 + 일회용 메일,
현재 ~250개). 정확도는 곧 사전 커버리지이고 추가는 한 줄이다.

⚠️⚠️ **이건 사실이 아니라 추정이다.** 학교 메일(`.ac.kr`/`.edu`)·소국가 ISP·개인 도메인이
전부 `corporate` 로 잡힌다. 그래서 화면 라벨이 "회사메일"이 아니라 **"도메인 메일"** 이고
상세에 "바이어 추정(확정 아님)"을 병기한다 — 운영팀이 확정 사실로 읽으면 잘못된 영업 판단으로
이어진다.

**도메인 그룹**: 응답 `domains[]`(corporate 만, count desc, 상위 50)이 셀렉트 옵션이자
"같은 회사에서 N명" 인사이트다. **국가 선택지 `countries[]`** 도 같은 규칙이다.

⚠️ 두 목록의 모집단은 **그 축을 뺀** 결과다(`applyFilters` 는 도메인·국가를 아예 안 보고,
`narrowByFacets` 가 마지막에 적용한다) — 적용 후로 세면 하나를 고르는 순간 선택지가 그것만 남아
되돌아갈 수 없다. 모든 조건이 AND 라 순서를 바꿔도 결과가 같고, 그래서 이 규칙이 주석이 아니라
**함수 두 개의 모양**으로 드러난다.

⚠️ 국가를 서버 facet 으로 내리는 이유: 예전엔 화면이 **현재 페이지 50행에 보이는 국가**로
datalist 를 만들었는데, 필터를 거는 이유가 "그 국가가 지금 안 보여서"라 구조적으로 쓸모가 없었다.

### 8. KLOW 회원 여부는 **이메일로** 조인한다

식별 축이 이메일이고 `User.email` 은 `@unique` 다. ⚠️ `Order.userId` 만 보면 **게스트로 결제한
회원이 통째로 비회원**이 된다. 행의 `member` 를 눌러 기존 `/customers/{id}` 로 넘어간다.

⚠️ `User` 전량 읽기는 `USER_SCAN_CAP`(10000)로 막는다. 회원 수가 캡에 닿으면
`email: { in: [...] }` 타깃 조회로 바꾸는데, 그건 주문 결과에 의존하므로 **왕복이 한 단 는다.**

### 9. 시딩 제품명은 통관 별칭이 아니라 진짜 제품명

⚠️ `OrderItem.productName` 은 시딩 라인에서 EFS 24-5 통관 신고용 일반 품명
(`Korean Skincare Toner`)이지 제품명이 아니다. `SEEDING_ITEM_NAMES_SELECT` 를 claim select 에
끼우고 `seedingItemNames()` + `displayLines()` 를 태운다 — 2026-08-31 에 `/track`·메일·송장·
어드민을 한 벌로 합쳐 둔 그 경로다. (brand-crm 에는 아직 이 처리가 없다 — 알려진 갭.)

### 10. 절단은 조용한 왜곡이다

`ORDER_SCAN_CAP` / `MANUAL_SCAN_CAP` / `USER_SCAN_CAP` = 10000. 닿으면 `truncated: true` 이고
화면이 배너를 띄운다.

⚠️ **SQL LIMIT 으로 페이지네이션할 수 없다** — 컨택트 행은 파생이고 수기기록은 앱에서 합쳐진다.
DB 에서 자른 뒤 앱에서 합치면 총계와 페이지가 조용히 거짓말을 한다.
⚠️ 스캔이 `createdAt desc` 라 잘리는 건 **가장 오래된 쪽**이다. 절단 상태의
`sort=purchase|contacts` 는 최근 구간 위의 정렬이라 그대로 신뢰할 수 없다.

캡에 닿기 시작하면 고칠 곳은 이 숫자가 아니라 구조다(서버 집계 또는 실체 테이블).

---

## 라우트

### admin-contacts.controller.ts (`@Controller('admin/contacts')`)

> 클래스 레벨 `AdminGuard`.

| Method | Path | 권한 | 기능 |
|---|---|---|---|
| GET | `/admin/contacts` | AdminGuard | 목록 → `{ data, total, truncated, facets, domains }` |
| POST | `/admin/contacts/export` | **+ SuperAdminGuard** | 현재 필터 그대로 xlsx |
| GET | `/admin/contacts/:id` | AdminGuard | 상세(연락처 전체 + 타임라인) |

⚠️ 정적 `export` 를 `:id` **앞에** 선언한다(`shipping-countries/export` 선례).

⚠️⚠️ **내보내기가 GET 이 아니라 POST 인 이유는 감사 로그**다. `AdminAuditInterceptor` 는 GET 을
기록하지 않는데, 이건 플랫폼 전체 PII 대량 반출이라 누가 언제 뽑았는지 흔적이 남아야 한다.
(인터셉터는 **요청 body** 만 redact·clamp 해 기록하고 응답은 `id` 추출용으로만 읽으므로,
`@Res()` 로 스트림하는 이 핸들러는 안전하다.)

⚠️ 조회는 AdminGuard, **반출만 SuperAdminGuard** 다(`PUT /admin/shipments/alert-recipients` 선례).
화면은 슈퍼가 아니면 버튼을 숨길 뿐이고 **최종 게이트는 서버 403** 이다.

⚠️ 없는 id 는 `Forbidden` 이 아니라 **`NotFound`** 다(id 를 넣어 보며 존재를 열거하지 못하게).

### 목록 쿼리 (`AdminContactListQuery`)

`q`(이름·이메일·인스타·전화) · `brandId` · `channel` · `country`(ISO2, `.toUpperCase()`) ·
`emailKind` · `domain` · `member` · `repeat` · `since`/`until`(최근 접점일) ·
`sort`(recent|contacts|purchase) · `take`(≤200) · `skip`.

⚠️ **`.default()` 는 `take`/`skip`/`sort` 에만.** 필터 축에 default 를 주면 klow_admin 이 안 보낸
축이 조용히 좁혀져 "고객이 사라졌다"가 된다.
⚠️ `country` 는 `.toUpperCase()` 정규화 필수(`kr`/`KR` 이 갈리면 같은 나라가 두 번 뜬다).

### 행 DTO

```ts
{ id, name, email, phone, emailDomain, emailKind,
  countryCode, countryName, instagram,
  channels[], brands: {id,name}[],
  contactCount, purchaseUsd, firstAt, lastAt,
  member: { id, createdAt } | null }
```

- `purchaseUsd` = **시딩 제외** Σ `Order.totalUsd`(USD 센트, 배송비 포함). "이 사람이 바이어인가"의
  축이라 시딩 수령인은 0 이다.
- ⚠️ **목록에는 주소가 없다**(PII 노출 최소화 + 열 폭). 상세와 내보내기에만 있다 —
  `decorate` 에 주소를 넣는 순간 목록 API 가 전 컨택트의 주소를 내려보낸다. 회귀 스펙이 잠근다.

상세는 `+ { addressLine1, addressLine2, city, postalCode, timeline[] }`.
타임라인 항목 `{ orderId, at, channel, brands[], label, amountUsd, orderStatus }` — `orderId` 가
있으면 화면이 `/orders/{id}` 로 링크하고, 수기기록은 `null` 이라 클릭되지 않는다.

⚠️ 타임라인 게이트는 **요청한 id 하나만** 담은 `ReadonlySet` 이다. 불리언으로 되돌리면 상세
한 번에 전 컨택트의 타임라인을 만든 뒤 1명분만 남기고 버린다(brand-crm 이 실제로 그랬다).

### facets

`{ all, seeding, store, onsite, manual, repeat, member, personalEmail, corporateEmail, noEmail }`
— **필터 적용 후 rows 위에서 단일 순회**로 센다(화면 숫자와 목록이 갈리면 어느 쪽이 맞는지 알
방법이 없다). ⚠️ 축을 더할 때 `rows.filter().length` 를 새로 달지 말고 그 루프에 한 줄 더한다.
한 사람이 여러 채널을 가질 수 있어 **채널 합은 `all` 을 넘을 수 있다.**

---

## 내보내기

`admin-contacts-xlsx.ts` — SheetJS `aoa_to_sheet`, 시트명 **`컨택트`**, 목록 열 + 주소·우편번호.

⚠️ **`common/xlsx-sheet-names.ts` 의 `EXPORT_SHEET_NAMES` 에 등록돼 있어야 한다**
(`ADMIN_CONTACTS_SHEET_NAME`). 빠뜨리면 이 파일이 배송비용·비교요율 탭 업로드에서 첫 시트
폴백으로 조용히 먹힌다. 이 레지스트리는 원래 `modules/shipping/xlsx-grid.ts` 안에 있었는데,
컨택트 내보내기가 문자열 상수 하나 때문에 shipping 의 OOXML 파서를 통째로 import 하게 돼
**이름만** `common/` 으로 올렸다(파서·라이터는 shipping 소유 그대로).

⚠️ 날짜는 Date 가 아니라 `YYYY-MM-DD` 문자열로 쓴다(엑셀 직렬 날짜로 나가면 로케일에 따라
`#####` 이거나 미국식으로 뒤집힌다).

⚠️⚠️ 그 문자열은 **`common/kst-time.ts` 의 `kstDateStr`** 로 만든다. `toISOString().slice(0,10)`
은 KST 00:00 = UTC 전날 15:00 이라 **새벽 기록이 하루 전 날짜로 나가** 화면(`formatDateKo`,
브라우저 KST)과 어긋난다 — `efs-billing.service.ts` 가 같은 함정을 주석으로 남겨 뒀다.

klow_admin 은 `downloadFile(url, name, init)` 로 POST 한다 — 그 세 번째 인자가 이 작업에서
추가됐다(기존 4개 GET 내보내기는 무변경).

---

## klow_admin

| 파일 | 역할 |
|---|---|
| `src/app/(authed)/contacts/page.tsx` | 목록 |
| `src/app/(authed)/contacts/[id]/page.tsx` | 상세 |
| `src/app/(authed)/contacts/filters.ts` | 필터 타입·기본값·`sessionStorage`·직렬화 |
| `src/app/(authed)/contacts/_components/ContactFilterBar.tsx` | 필터 바 |
| `src/lib/api/contacts.ts` | DTO + 호출 |
| `src/lib/contact-status.ts` | 채널·이메일유형 배지 정본(페이지 로컬 맵 금지) |
| `src/lib/status-badge.ts` | `optionsOf` — 배지 맵 → 셀렉트 선택지(orders 페이지 로컬 사본을 승격) |
| `src/lib/list-filters.ts` | `isDefaultFilters` — orders 와 공유 |

⚠️ **필터 영속화는 `sessionStorage`**(키 `klow_admin.contacts.filters`)다. URL 쿼리는 구조적으로
불가 — 이 어드민은 iframe 탭 셸이라 `TabsContext.normalizeHref` 가 쿼리를 떼어낸다. 페이지
번호는 저장하지 않는다(orders·tracking 과 같은 패턴).

⚠️ 어드민 미들웨어는 **deny-by-default** 라 새 라우트를 등록할 필요가 없다(klow_brand 와 다르다).

---

## 마이그레이션 · 배포

**없다.** 스키마 변경·마이그레이션·백필·cron 전부 불변. 배포 즉시 과거 데이터 전부가 뜬다.

- 라우트 **328 → 331**(부팅 실측. ⚠️ brand-crm.md 가 한동안 적어 둔 326 은 낡은 값이라 함께 정정).
- 모듈 **31 → 32**(`AdminContactsModule`). cron 10개 불변이라 `test/app.e2e-spec.ts` 무변경.
- 배포 순서: **klow_server → klow_admin**(반대면 `/contacts` 가 404).

## 회귀 잠금

`customers/__tests__/`

- `email-domain.spec.ts`(10) — ⚠️ 핵심은 **접미사 매칭이 아님**(`mail.acme.com`·`notgmail.com`
  이 personal 로 새지 않는다) + `lastIndexOf('@')` + FQDN 끝점 제거 + 사전 비어있지 않음.
- `admin-contacts-scan.spec.ts`(18) — ⚠️ **왕복 2단**(1단 일곱 개가 전부 발사) · ⚠️ **`seedingClaim`
  에 `link` 중첩 없음** · 주문 where · 전량 읽기(where 없음) · 브랜드 통합 1행 · 동결 송장 축 ·
  시딩이 `channel='web'` 이어도 seeding · `purchaseUsd` 에 시딩 미포함 · **목록에 주소 없음** ·
  **시딩 라벨이 진짜 제품명** · 상세 타임라인 1명분 · ⚠️ **대문자 주문 이메일도 회원으로 매칭**
  (조회 키 정규화) · facets 필터 후 · **도메인·국가 목록은 그 축을 빼고 셈** · NotFound ·
  현장 빈 값이 대표값을 안 지움.

## 알려진 갭

- 같은 사람이 **이메일을 바꿔** 신청하면 두 명으로 보인다(수동 병합 UI 없음 — brand-crm 과 동일).
- 수기 시딩 기록은 **주소로는 KLOW 주문과 합쳐지지 않는다**(주문은 5칸 합성 키, 수기는 자유
  문자열 하나). 합쳐지는 경로는 `fields[]` 에서 건진 이메일, 그다음 전화뿐이다.
- **인플루언서 프로필 결합 안 함** — 인스타 핸들로 `CuratedInfluencer.username` 을 조인하면
  팔로워·인게이지먼트를 붙일 수 있다(양쪽 다 `@` 제거·소문자로 정규화돼 있어 조인 가능).
  v1 범위에서 뺐다.
- **시딩 캠페인명·프로모션 유입·후기 제작 여부** 미노출(v1 범위 밖).
- **어드민 태그·메모 없음**(읽기 전용). 브랜드가 단 `BrandCrmNote` 는 브랜드 소유라 노출하지 않는다.
- `brandId` 필터를 걸어도 **전 주문을 스캔한다**(앱에서 거른다). 현재 규모에선 문제가 아니고,
  전환 트리거는 절단 캡에 닿을 때다.
