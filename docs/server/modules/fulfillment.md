# fulfillment — 3PL 창고 재고 · 출고신청 (v1 = 콜로세움)

- **모듈 경로**: `src/modules/fulfillment/`
- **관련 파일**: `fulfillment.service.ts`(재고·출고신청 전부), `fulfillment-xlsx.ts`(라이터 2벌 +
  파서 1벌), `admin-inventory.controller.ts`, `admin-fulfillment.controller.ts`,
  `brand-fulfillment.controller.ts`, 검증 스키마 `common/validation/fulfillment.ts`,
  회귀 스펙 `__tests__/fulfillment-xlsx.spec.ts`
- **모델**: `BrandInventoryItem` · `FulfillmentRequest` · `FulfillmentRequestItem`
  + `enum FulfillmentRequestStatus { requested exported cancelled }`
- **프론트**: klow_admin 브랜드 상세 `재고` 탭(`brands/_components/inventory/BrandInventoryPanel.tsx`,
  `?tab=inventory` 딥링크) + 사이드바 배송 > 출고신청(`(authed)/fulfillment/page.tsx`),
  API 클라이언트 `lib/api/fulfillment.ts` · klow_brand 스튜디오 홈 `재고` 탭
  (`studio/_components/tabs/InventoryTab.tsx` + `tabs/inventory/`)
- **계획 문서**: [`plan/3pl-fulfillment/implementation-plan.md`](../../plan/3pl-fulfillment/implementation-plan.md)

브랜드가 **콜로세움 3PL 창고**에 재고를 미리 넣어두고, 그 재고로 출고한다.
흐름은 한 줄이다 — **어드민이 브랜드별 재고를 입력 → 브랜드 재고 탭에 보임 → 브랜드가 출고신청
→ 재고 자동 차감 → 어드민이 콜로세움 엑셀 다운로드(= `exported` 전이).**

## ⚠️⚠️ v1 의 출고신청은 KLOW 주문에서 오지 않는다

브랜드가 **수취인·제품을 직접 입력하는 독립 엔티티**다. 그래서 이 모듈은 EFS·`Shipment`·
`ShippingCarrier`·라우팅 코드를 **한 줄도 건드리지 않는다.** 유럽 라우팅·일반주문 자동 유입·
배송 추적·물류비 후청구는 전부 다음 트랙이다(계획 문서 §5).

콜로세움은 EFS 와 달리 **API 가 없다.** 운영자가 주문서 엑셀을 콜로세움 대시보드에 수작업으로
올린다 — 그래서 "내보내기"가 곧 발송 지시이고, 그 시각(`exportedAt`)이 중복 출고 방지의 정본이다.

## ⚠️⚠️ `Product.stockLeft` 와 다른 축이다 — 재사용 금지

`Product.stockLeft` 는 이미 있지만 klow_web 제품 상세의 희소성 문구(`Only {n} left in stock`,
8개 로케일)를 띄우는 **어드민 수기 표시값**이고, 주문이 들어와도 차감하는 코드가 **어디에도
없다.** 3PL 재고를 거기 넣으면 창고 수량을 고칠 때마다 고객 상품 페이지의 "N개 남음"이 같이
움직인다. 창고 재고의 정본은 `BrandInventoryItem` 하나다.

**재고 0 이 판매를 막지는 않는다** — `PURCHASABLE_PRODUCT_WHERE` 는 이 축을 보지 않는다.

## 재고 차감 규칙

| 사건 | 재고 |
|---|---|
| 출고신청 생성 | **즉시 차감.** 부족하면 아무것도 만들지 않고 400 |
| 취소 (`requested` 상태) | **반납** |
| 어드민 내보내기 (`exported` 전이) | 변화 없음 — 이미 차감돼 있다 |
| `exported` 이후 취소 | **불가** (409) — 창고가 이미 받았다고 본다 |

- 재고 부족은 400 + `code: 'insufficient_inventory'` + `shortages[]`(제품명 · 신청 수량 · 남은 수량).
  ⚠️ **부분 출고로 깎아주지 않는다** — 창고가 무엇을 집을지 브랜드가 모르는 채 절반만 나가는 게
  재고 부족보다 나쁘다.
- 생성·취소는 재고 증감과 **한 트랜잭션**이고, 대상 행을 `SELECT … FOR UPDATE` 로 잠근다
  (`seeding.service.ts` `reserveSlot()` 선례). 락 구간은 **3왕복**(잠금+읽기 / 증감 1문장 / 신청
  생성)으로 묶고 타임아웃 20초 · maxWait 15초를 준다 — Prisma 기본 5초는 Neon Singapore 왕복
  앞에서 너무 좁다.
- ⚠️ 잠금은 항상 `ORDER BY "productId"` 다. 두 신청이 같은 두 제품을 반대 순서로 잠그면 서로를
  기다린다.
- ⚠️ 증감은 `CASE "productId" … END` **한 문장**이다. 줄마다 UPDATE 를 날리면 락 보유 시간이
  줄 수(최대 50)만큼 늘어난다.
- ⚠️ `FulfillmentRequestItem.productId` 는 **nullable + SetNull** 이다(제품 삭제 경로가 실제로
  있다). 취소 시 그 줄은 반납 대상이 없어 조용히 건너뛴다 — `BrandInventoryItem` 도 함께
  캐스케이드로 사라졌기 때문이다. 그 경우 `productName` 스냅샷이 유일한 기록이다.

## 엔드포인트

### admin-inventory.controller.ts (`@Controller('admin/brands/:brandId/inventory')`, `AdminGuard`)

| Method | Path | 기능 |
|--------|------|------|
| GET | `/admin/brands/:brandId/inventory` | 브랜드 제품 **전체** × 재고 수량(행 없는 제품은 0) |
| PUT | `/admin/brands/:brandId/inventory` | 수량 저장 — **보낸 줄만 반영** |

- ⚠️ 이 라우트를 `brands/admin-brands.controller.ts` 에 넣지 않는다. 거기엔 `@Get(':id')` 가 있고,
  무엇보다 재고의 정본 모델은 이 모듈이 소유한다.
- ⚠️ **보낸 줄만 반영한다** — 빠진 제품의 수량을 0 으로 떨어뜨리지 않는다. 어드민 화면이 제품
  목록을 페이지로 끊게 되면 "안 보낸 = 0" 규칙이 나머지 페이지를 지운다.
- 남의 브랜드 제품 id 가 섞이면 통째로 400(어느 id 인지 돌려준다).

### admin-fulfillment.controller.ts (`@Controller('admin/fulfillment/requests')`, `AdminGuard`)

| Method | Path | 기능 |
|--------|------|------|
| GET | `/admin/fulfillment/requests` | 전 브랜드 출고신청 목록 (`status`·`brandId`·`q`·`take`·`skip`) |
| POST | `/admin/fulfillment/requests/export` | **콜로세움 주문서 xlsx** — `SuperAdminGuard` |
| GET | `/admin/fulfillment/requests/:id` | 상세 |

- 목록과 내보내기(4단계)는 `FulfillmentService.adminWhere()` **하나**를 공유한다 — 두 곳이 갈리면
  화면에서 센 건수와 실제로 나간 행 수가 어긋난다.
- ⚠️ **어드민에는 기간 축(`since`/`until`)이 없다** — 브랜드 목록에만 있다(아래). 붙이려면
  `AdminFulfillmentListQuery` · `AdminFulfillmentExportInput` · `adminWhere` **세 곳을 함께**
  고쳐야 한다. 한 곳만 고치면 settlement·shipping-rates 에 남아 있는 **미작동 반쪽 구현**이
  하나 더 늘고, 목록과 내보내기의 건수가 갈린다.
- `q` 는 수취인명 · 브랜드가 붙인 주문번호(`externalOrderNo`) 부분일치다.
- ⚠️ 정적 `export` 를 `:id` **앞에** 선언한다(`shipping-countries/export` 선례).
- ⚠️⚠️ 내보내기가 **GET 이 아니라 POST + `SuperAdminGuard`** 인 이유는 감사 로그다. 수취인
  이름·주소가 통째로 나가는 PII 대량 반출인데 `AdminAuditInterceptor` 는 GET 을 기록하지
  않아 누가 뽑았는지 흔적이 남지 않는다(`admin-contacts` 선례).

### brand-fulfillment.controller.ts (`@Controller('v1/brand')`, `BrandGuard`)

| Method | Path | 기능 |
|--------|------|------|
| GET | `/v1/brand/inventory` | 내 창고 재고 + 제품별 출고 대기 수량 (읽기 전용) |
| GET | `/v1/brand/fulfillment/requests` | 내 출고신청 목록 (`status`·**`since`·`until`**·`take`·`skip`) |
| POST | `/v1/brand/fulfillment/requests` | 출고신청 생성 — 재고 차감 |
| POST | `/v1/brand/fulfillment/requests/:id/cancel` | 취소 — 재고 반납 |
| GET | `/v1/brand/fulfillment/template` | **KLOW 양식 xlsx** 다운로드 (+ `제품목록` 참조 시트) |
| POST | `/v1/brand/fulfillment/preview` | 업로드 미리보기 (multipart `file`) — **저장하지 않는다** |
| POST | `/v1/brand/fulfillment/bulk` | 미리보기 결과 적용 — 최대 50건, 한 트랜잭션 |

- ⚠️ **경로에 brandId 가 없다** — 세션(`requireBrandId`)에서 꺼내므로 남의 브랜드를 가리킬 방법이
  구조적으로 없다(`brand-notices` 와 같은 판단).
- ⚠️ 브랜드에게 **재고 쓰기는 없다.** 창고에 실제로 무엇이 들어왔는지 아는 쪽은 운영자뿐이다.

#### 목록의 기간 축 — `since` / `until` (스키마는 `BrandFulfillmentListQuery`)

**KST 달력일 'YYYYMMDD'** 한 칸씩이고 **둘 중 하나만 보내도 된다**(화면의 '최근 7일' 은 `since`
만 쓴다). `until` 은 **그날 끝까지** 포함이다 — 내부적으로 반열림 `[start, endExclusive)` 로
바뀐다(`common/kst-time.ts` `kstYmdRange`). 달력 유효성(`20260231`)과 `since <= until` 은 zod 가 본다.

응답은 셋이다.

| 키 | 모집단 | 쓰임 |
|---|---|---|
| `items` | 기간 **+ 상태** · 페이지(`take`/`skip`) | 목록 |
| `total` | 기간 **+ 상태** 전체 | `total > items.length` = 상한에 걸림 |
| `counts` | **기간만** (`{total,requested,exported,cancelled}`) | 상태 칩 건수 |

- ⚠️⚠️ **`counts` 는 상태로 또 좁히지 않는다.** 좁히면 '신청함' 을 고르는 순간 나머지 칩이 전부
  0 이 되어 고를 이유가 사라진다. 그리고 이 값을 **클라가 페이지 배열에서 세면 `take` 상한
  안에서만 센 수**가 된다 — 기간을 서버로 옮긴 이유가 화면에서 그대로 되살아난다.
- ⚠️ **검색어는 서버 축이 아니다.** 브랜드 화면의 수취인명·주문번호·제품명 검색은 받아온
  페이지 안에서 클라가 건다(어드민의 `q` 와 다르다).
- ⚠️⚠️ **배포는 klow_server → klow_brand.** 뒤집으면 400 이 아니라 **조용한 strip** 이다 —
  zod object 는 모르는 키를 버리므로 구 서버가 기간을 무시한 최신 N건을 돌려주고, 화면은
  "필터가 먹었다"고 믿는다.
- ⚠️ **인덱스를 추가하지 않았다.** 기존 `@@index([brandId, status])` 로 브랜드 축이 먼저 좁혀지고
  브랜드당 행 수가 작다. 정렬이 느려지면 그때 `@@index([brandId, createdAt])` 를 **독립 단계**로
  뗀다(마이그레이션은 독립 단계 규칙).

#### 재고 응답의 `outboundPending`

제품별 **출고 대기 수량**(= 그 제품이 실린 `requested` 신청의 수량 합)을 서버가 `groupBy` 로 낸다.

- ⚠️ "곧 나갈 물량"이지 **"재고에서 더 빠질 물량"이 아니다** — 재고는 신청 시점에 이미 차감됐다.
  `quantity` 에서 또 빼면 이중 차감이다.
- ⚠️⚠️ 이 합을 서버가 내는 이유는 **상한**이다. 브랜드 화면이 `requested` 목록을 200건 받아 직접
  더하던 구조라, 신청이 200건을 넘는 순간 제품마다 실제보다 적은 수가 **조용히** 떴다.
- `productId` 는 nullable(제품 삭제 시 SetNull)이라 null 그룹은 버린다 — 지워진 제품은 재고 행이 없다.
- 어드민 `GET /admin/brands/:brandId/inventory` 가 같은 서비스 메서드를 쓰므로 **거기에도 실려
  나간다**(additive — 어드민 화면은 아직 읽지 않는다).

## 입력 제약 (`common/validation/fulfillment.ts`)

⚠️ 문자열 상한은 **두 곳이 같은 값을 본다** — zod 와 `schema.prisma` 의 `@db.VarChar`. 한쪽만
올리면 브랜드가 친 값이 저장 단계에서 22001 로 터진다. 그리고 ⚠️ **이 상한들은 콜로세움이 정한
값이 아니다**(양식 제약 미확인 — 계획 문서 §2). 확인되면 그때 좁힌다.

| 상수 | 값 | 뜻 |
|---|---|---|
| `FULFILLMENT_MAX_ITEMS` | 50 | 신청 1건의 제품 줄 수 |
| `FULFILLMENT_MAX_QTY` | 9,999 | 한 줄 최대 수량 |
| `INVENTORY_MAX_ITEMS` | 500 | 어드민이 한 번에 저장하는 재고 줄 수 |
| `INVENTORY_MAX_QTY` | 999,999 | 재고 수량 상한 |

- ⚠️ **`.default()` 를 쓰지 않는다** — 구 클라가 안 보낸 필드를 서버가 조용히 채우면 배포 창에서
  "기본값으로 덮어쓰기"가 일어난다. DB 의 `@default("KR")` 는 마이그레이션용이고, API 입력은
  국가를 **항상 명시**한다.
- 같은 제품이 두 줄로 오면 400 이다. 합산해 받아주면 "재고 부족" 안내가 어느 줄을 가리키는지
  흐려지고, 엑셀에도 같은 제품이 두 행으로 나가 창고가 두 번 집는다.
- `externalOrderNo` 는 **유일성을 강제하지 않는다** — 브랜드가 자기 쇼핑몰에서 가져오는 값이라
  브랜드끼리 겹칠 수 있고, 겹쳐도 우리 쪽 식별자(`id`)가 따로 있다. 빈 문자열은 `null` 로 정규화.

## 엑셀 — 라이터 2벌 + 파서 1벌 (`fulfillment-xlsx.ts`)

**라이터와 파서를 한 파일에 둔다** — "내보낸 포맷 == 파서가 읽는 포맷"이 왕복의 전부라, 헤더
문자열을 한쪽에서만 고치면 조용히 깨진다(`shipping/seeding-declared-xlsx.ts` 선례).
시트명 둘 다 `common/xlsx-sheet-names.ts` 의 **`EXPORT_SHEET_NAMES` 에 등재**돼 있다 —
빠뜨리면 이 파일이 배송비용·비교요율 탭 업로드에서 첫 시트 폴백으로 조용히 먹힌다.

### ① 브랜드 업로드 — KLOW 양식 (시트 `출고신청`)

다운로드 → 작성 → 미리보기 → 적용 4단계. ⚠️ **콜로세움 양식을 그대로 받지 않는다** — 거기
제품이 자유 텍스트 상품명이라 재고 차감 대상을 특정할 수 없다. KLOW 양식은 `제품코드`
(= `Product.id`)를 요구하고, 같은 파일의 두 번째 시트 `제품목록` 에 그 브랜드의 제품코드·
제품명·현재 재고를 실어 복사해 갈 수 있게 한다.

15열: `신청번호` `국가코드` `수취인명` `주소` `상세주소` `우편번호` `연락처` `연락처2`
`배송메시지` `주문자명` `주문자연락처` `비고` `제품코드` `제품명(참고용)` `수량`.

- **`신청번호` 가 그룹 키**다 — 같은 값의 행들이 출고신청 1건(수취인 1명 + 제품 N줄)으로 묶이고,
  그 값이 `externalOrderNo` 로도 저장된다. 비어 있으면 **바로 앞 행에 이어지는 제품 줄**로 본다.
- 열은 **위치가 아니라 헤더 이름**으로 찾는다(브랜드가 참고 열을 끼워 넣어도 견딘다).
- ⚠️ 같은 묶음의 두 번째 수취인명은 **무시하되 `errors` 로 보고**한다. 말없이 첫 행이 이기게
  하면 브랜드는 두 번째 주소로 갔다고 믿는다 — 콜로세움 양식이 행마다 수취인을 반복하는
  구조라 이 실수가 잦다.
- 같은 묶음에 같은 제품코드가 두 번이면 **합산**하고 보고한다(안 합치면 서버 zod 의
  "같은 제품이 두 번 담겼습니다" 로 묶음 전체가 떨어진다).
- **빈 양식에 예시 행을 넣지 않는다** — 지우지 않고 그대로 올려 유령 신청이 생긴다.
- 미리보기는 **아무것도 저장하지 않고** 파싱 오류·모르는 제품코드·재고 부족을 전부 모아
  돌려준다. 재고 판정은 **파일 전체 합산**(적용이 그렇게 검사하므로 미리보기도 같아야 한다).
  ⚠️ 그 판정은 **스냅샷**이다 — 적용까지 사이에 다른 신청이 들어오면 적용이 400 으로 떨어진다.
  미리보기가 재고를 잡아두지는 않는다(만료 장치 없이 잡으면 떠난 사용자가 재고를 영영 묶는다).
- 적용은 **최대 50건 · 한 트랜잭션 · 부분 성공 없음.** 50건 중 37건만 들어간 상태를 브랜드가
  엑셀과 대조해 복구하는 건 불가능에 가깝다.

### ② 어드민 콜로세움 주문서 (시트 `양식`, 17열)

⚠️ 17열의 **순서도 철자도 콜로세움이 정한 것**이다(`배송메세지` 의 옛 철자 포함). 운영자가 이
파일을 콜로세움 대시보드에 그대로 올린다 — 콜로세움에는 API 가 없다.

- **신청 1건 = 제품 줄 수만큼의 행**이고, 그 행들이 같은 `쇼핑몰주문번호` 를 공유한다
  (창고가 그 값으로 한 상자로 묶는다).
- ⚠️⚠️ **`쇼핑몰주문번호` 는 내보내기 안에서 유일해야 한다.** `externalOrderNo` 는 브랜드가
  손으로 적는 값이라 `1`·`2` 같은 일련번호가 흔하고, 그대로 내보내면 **서로 다른 수취인의 행이
  한 상자로 합쳐진다.** 겹치는 값에는 우리 식별자 꼬리를 붙인다
  (`disambiguateOrderNos` — 첫 등장은 브랜드가 적은 값 그대로 둔다).
- `옵션명` 은 항상 빈칸이다(KLOW 에 옵션/변형 개념이 없고 `Product` 하나가 곧 SKU).
  `상품금액`·`택배사명`·`송장번호` 도 빈칸(용도·회신 주체 미확인 — 계획 문서 §2 C·D).
- 해외 주소는 잠정적으로 `[국가명] 주소1` 이다(§2 A 미확인). 국내는 그대로. 국가명은
  `ShippingCountry.nameKo`, 없으면 ISO2. **고칠 자리는 `colosseumAddress()` 하나다.**
- **내보내기 = `exported` 전이**이고 그 시각이 중복 출고 방지의 정본이다. 필터 내보내기
  (`ids` 없음)는 `requested` 만 보므로 같은 건이 두 번 나가지 않는다. ⚠️ `ids` 를 준 선택
  내보내기는 이미 나간 건도 실어 **재다운로드**가 되지만 **`exportedAt` 은 건드리지 않는다**
  (밀어버리면 "언제 창고로 넘겼나"가 사라진다).
- 파일을 다 만든 **뒤에** 전이한다 — 빌드가 던지면 아무것도 나가지 않은 채 상태만 바뀌는
  상황을 막는다.
- 파일명 날짜는 `kstDateStr()` 다. ⚠️ `toISOString().slice(0,10)` 은 KST 00~09시 건을 하루 전
  날짜로 내보낸다.

### ⚠️⚠️ `t="str"` — 우편번호 앞자리 0 이 사라지던 리더 버그

이 양식을 붙이면서 `shipping/xlsx-grid.ts` 의 `readSheetAOA` 를 고쳤다. SheetJS 는 기본
(`bookSST:false`) 문자열 셀을 `<c t="str"><v>…</v></c>` 로 쓰는데, 리더에 그 분기가 없어
숫자 추론 분기로 흘러 **`06234` 가 `6234` 로 앞자리 0 을 잃었다.** 지금까지 안 보인 이유는
기존 왕복(요율·신고가)의 문자열이 전부 ISO2 같은 알파벳이었기 때문이다.

⚠️ 이 리더는 배송비용·비교요율·신고가 탭도 함께 쓴다. 고칠 때 `npx jest src/modules` 전체를
돌릴 것.

## 화면 쪽 규칙

- **어드민 브랜드 상세 `재고` 탭** — `NumericInputCell` 인라인 편집, **바뀐 줄만** 저장한다.
  ⚠️ 창고 수량 입력은 어드민 전용이다(브랜드에게 쓰기가 없다).
- **어드민 `출고신청` 목록** — 체크박스 선택 + 내보내기. ⚠️ **행 전체를 클릭 링크로 만들지
  않는다** — 선택 상태(로컬 state)가 날아간 채 같은 iframe 탭이 갈아끼워진다(어드민 관례).
  ⚠️ `Sidebar.tsx` 의 `NAV` **와** `components/tabs/routeLabels.ts` 의 `ROUTE_LABELS` 둘 다에
  등록돼 있다 — 후자를 빠뜨리면 탭 제목이 영문 슬러그로 뜬다.
- **브랜드 스튜디오 `재고` 탭** — `재고현황` / `출고신청` 2개 서브탭.
  `출고신청` 은 **콜로세움 3PL '출고 주문' 화면의 읽는 순서**를 따른다(기간 → 상태 → 검색 →
  건수 요약 → 액션 → 목록/빈 상태). ⚠️ 구조만 빌리고 **색·밀도는 가져오지 않았다** — 저쪽은
  파란 기업색 + 7열 테이블인데 이 패널은 가장 좁을 때 약 532px 이고, 스튜디오 전역 규칙이
  ink 한 가지 + 예외색 하나다.
  ⚠️ 상태만 pill 이 아니라 **select** 다(기간 4칸 + 상태 4칸이 375px 한 줄에 안 들어간다).
  ⚠️ 상태별 건수는 **기간만 건 모집단**에서 센다 — 상태로 또 좁힌 뒤 세면 하나를 고르는
  순간 나머지가 0 이 되어 고를 이유가 사라진다. 그 수는 **서버 `counts` 를 그대로** 쓴다.
  ⚠️⚠️ **기간 필터는 서버가 건다**(`since`, 위 절). 화면은 기간 pill → `since` 만 만들고
  `until` 은 보내지 않는다(기간이 전부 "오늘까지"라, 상한을 박으면 자정을 넘긴 탭이 방금 낸
  신청을 못 본다). **기간은 쿼리키에도 들어간다** — 빼면 '오늘' 응답이 '한달' 화면에 재사용된다.
  ⚠️ 상태는 **서버로 보내지 않는다** — 서버가 상태로 거르면 `counts` 의 모집단도 그만큼 좁아진다.
  ⚠️ 상한(200)은 사라진 게 아니라 **보이게** 됐다. `total > items.length` 면 목록 아래가
  "최근 200건만 표시했어요"를 띄운다. **말없이 자르지 않는 것**이 이 화면의 계약이다.
  ⚠️ 신청·취소 성공 시 **목록과 재고를 함께** 무효화한다(차감·반납이 같은 트랜잭션이다).
  ⚠️ `출고 대기` 는 서버 컬럼이 아니라 `requested` 신청의 합이고, **제품 행 우측 숫자 열**에
  둔다(보조줄 문장으로 흘려 쓰면 제품마다 위치가 달라 세로로 훑을 수 없다). 재고는 신청
  시점에 이미 차감됐으므로 합계에서 또 빼면 이중 차감이다.
  ⚠️ 우측 두 칸의 폭(보관 48 / 출고 38)을 키우지 말 것 — 375px 에서 제품명이 먼저 잘린다(실측).
  ⚠️ 구 목업의 '보충 필요'(안전재고) 상태를 **뺐다** — 서버에 안전재고 컬럼이 없다. 되살리려면
  `BrandInventoryItem` 에 컬럼을 먼저 추가할 것.

## 아직 없는 것

- **기간별 출고량 집계**(국내/해외) — 서버에 집계 엔드포인트가 없다. 디자인 목업이 잠깐
  있었으나 제품별 실데이터 옆에 가짜 집계를 두면 어느 쪽이 실적인지 갈려 **제거했다**.
- **배송 추적·송장번호** — 콜로세움 회신 방식 미확인(계획 문서 §2 D). v1 은 추적 없음이다.
- **해외 주소를 콜로세움 양식의 어느 칸에 넣는지** 미확인(§2 A). 내보내기는 잠정적으로 국가명을
  `수취인주소` 접두로 붙인다.

## 유입 경로 (`FulfillmentRequest.source`)

`enum FulfillmentSource { manual bulk_xlsx cafe24 }` — 브랜드·어드민 목록의 **유입 배지**가
이 값을 읽는다. 세 생성 경로가 각자 명시한다: 단건 신청 `manual` · 엑셀 일괄 `bulk_xlsx` ·
카페24 전환 `cafe24`.

- ⚠️⚠️ **`Cafe24Order` 역조인으로 배지를 그리지 않는다.** 그러면 브랜드 목록·어드민 목록·
  콜로세움 엑셀 **세 곳이 같은 조인을 타야** 표시가 일치한다
  (`plan/cafe24-fulfillment/implementation-plan.md` §4-F).
- ⚠️⚠️ **`externalOrderNo` 에 유입 접두사를 붙이지 않는다** — 그 값은 콜로세움 엑셀
  `쇼핑몰주문번호` 칸으로 **그대로** 나간다.
- `@default(manual)` 은 기존 행과 구 클라를 위한 것이다. **새 생성 경로는 항상 명시한다** —
  `createManyInTx(tx, brandId, requests, source)` 가 `source` 에 기본값을 두지 않는 이유다.

### ⚠️ 트랜잭션 안에서 부르는 진입점 — `createManyInTx`

카페24 전환은 **미러 역기록이 재고 차감과 같은 트랜잭션**이어야 해서 그쪽이 트랜잭션을 열고
이 서비스를 불러온다(`FulfillmentModule` 이 `FulfillmentService` 를 export 하는 유일한 이유).

⚠️⚠️ **락 순서를 지킬 책임은 호출부에 있다.** 이 메서드 안에서 재고가 `ORDER BY "productId"`
로 잠기므로, 그 **앞에** 다른 행을 잠글 거면 항상 같은 순서여야 한다
(카페24 전환: `Cafe24Order`(ORDER BY id) → 재고). 한 경로라도 뒤집히면 데드락이다.

⚠️ **재고를 건드리는 두 번째 경로를 만들지 않기 위한 export 다.** 그 경로는 잠금 순서도
부족 판정도 따로 갖게 되고, 그 둘이 갈리는 순간 재고가 음수가 된다.
