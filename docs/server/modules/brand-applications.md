# brand-applications — 브랜드 입점 신청 + 셀프 상품 관리

- **모듈 경로**: `src/modules/brand-applications/`
- **주 클라이언트**: `klow_brand` (port 3002)
- **데이터 모델**: `Brand`(status draft/pending/approved/rejected/withdrawal_pending/withdrawn) + `Product`(status pending/approved/rejected)
- **자기 브랜드 연결**: `BrandUser.brandId` (승인 후에도 본인 상품 추가 가능; 추가 상품은 `pending` 으로 시작)
- **승인은 구독 게이트로 이관됨**: 결제 = 자동 승인 정책이라 **어드민 검수 큐가 없다**. 과거 `admin-brand-applications.controller.ts`(approve/reject/unapprove/product approve·reject) 는 제거되었고, 그 기능은 [subscription](./subscription.md) 의 `/admin/brand-subscriptions/*` 로 옮겨졌다. 이 모듈은 이제 **브랜드 셀프-서비스(공개) 컨트롤러만** 남았다.
- **입점 흐름**: studio OnboardingGate 에서 송화인 4 + 계좌 3 필드를 저장 → `submit-for-review` 가 `pgCustomerKey` 발급 → NicePay 포스타트 빌링 결제 → `approveApplication()` 자동 승인 (자세히는 [subscription](./subscription.md) + `../../../docs/brand-subscription.md`).
- **관련 파일**: `brand-applications.service.ts`, `brand-applications.controller.ts`, `draft-brand.ts`(공통 draft 데이터·P2002 매핑)

## brand-applications.controller.ts (`@Controller('v1/brand')`)

> 전체 라우트 `BrandGuard` (자기 brandId scope).

### 번역 유틸 (스튜디오 공용)

| Method | Path                  | Throttle   | 기능                                                                 |
|--------|-----------------------|------------|----------------------------------------------------------------------|
| POST   | `/v1/brand/translate` | 20회 / 분  | `{texts[], target, source?}` → `{translated: string[]}` (Google Translate 유료 호출이라 IP 당 제한) |

- `texts` 는 **1~20개** (각 2000자 이하) — 태그처럼 개수가 많은 입력은 클라가 20개씩 청크해서 보낸다.
- `target` 은 `en|ja|zh|vi|th|id|ru` (서버가 실제 지원하는 로케일). `source` 는 생략 가능(자동 감지, 허용값에 `ko` 추가).
- 두 용도 공용: **입력 영문화**(스튜디오 폼 한글 → `target:'en'`) + **목업 라이브 번역**(선택 국가 로케일).
  표시/입력 보조라 제품 소유권 체크가 없다(로그인 브랜드면 충분). 빈 문자열은 위치를 보존해 그대로 반환.

### 입점 신청 (Brand)

| Method | Path                                          | 기능                                                              |
|--------|-----------------------------------------------|-------------------------------------------------------------------|
| POST   | `/v1/brand/applications`                      | 신청 제출 (단일 step submit)                                      |
| PUT    | `/v1/brand/applications`                      | 신청 내용 수정 — **전체 문서 저장**(delta 아님). 디자인 자동저장(색·폰트·`links`·`linkStyle`·`story`)이 이 라우트를 탄다 |
| GET    | `/v1/brand/applications/me`                   | 내 신청 조회 (홈페이지/타겟국가/송화인/계좌 등 포함)              |
| POST   | `/v1/brand/applications/init-draft`           | 드래프트 생성 — `{ slug, category? }`. klow_brand `/start` 2단계가 주소+업종을 한 번에 보낸다. idempotent (기존 brand 가 있으면 slug 불변, category 는 **비어 있을 때만** 채움) |
| POST   | `/v1/brand/applications/submit-for-review`    | 드래프트 → 검토 제출 (모든 필드 완성 확인, `pgCustomerKey` 발급)  |
| PATCH  | `/v1/brand/applications/operational-profile`  | 운영 프로필(송화인 4 + 계좌 3 필드) 저장 — OnboardingGate         |

### 셀프 상품 관리 (Product)

| Method | Path                              | 기능                                                              |
|--------|-----------------------------------|-------------------------------------------------------------------|
| POST   | `/v1/brand/products`              | 상품 생성 (신청 진행 중 또는 승인 후 모두 `pending` 으로 시작)    |
| POST   | `/v1/brand/products/bulk`         | 상품 일괄 생성 (draft 다건)                                       |
| GET    | `/v1/brand/products`              | 내 브랜드 상품 목록                                               |
| PATCH  | `/v1/brand/products/reorder`      | 상품 노출 순서 변경 (드래그&드롭, `ids[]` 최대 500 — 자기 브랜드 소유만 반영) |
| PUT    | `/v1/brand/products/onsite`       | 현장(박람회 부스) QR 판매가 일괄 저장 (`items[]{id, onsitePriceUsd(센트\|null), onsiteExcluded, settleKrw(₩\|null), discountPct(0~90\|생략=현재값 유지), countryPrices[]{iso2, priceLocal}}` 최대 500, `:id` 위에 선언) |
| PATCH  | `/v1/brand/products/:id/hidden`   | 상품 가리기 On/Off 토글 (`Product.hidden`, status 유지·노출/판매만 제외; 단일 필드 전용 PATCH, `:id` 위에 선언) |
| PATCH  | `/v1/brand/products/:id`          | 상품 수정 (자기 brandId 확인)                                     |
| DELETE | `/v1/brand/products/:id`          | 상품 삭제                                                         |

### 브랜드 수동 번역 오버라이드 (2026-08-25)

기계번역이 부정확한 자유 텍스트를 브랜드가 스튜디오 목업에서 직접 고치는 통로. 저장 모양·overlay·우선순위는 [`products.md`](./products.md) "브랜드 수동 번역 오버라이드" 절이 소유하고, 여기서는 HTTP 표면만 적는다.

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/v1/brand/products/:id/translations`          | 전 로케일 리포트 → `{productId, locales: {ja: {entries, drifted, count}, …}}` |
| PATCH  | `/v1/brand/products/:id/translations/:locale`  | 엔트리 1건 저장. `{field, src, value}` — **`value: ''` 는 삭제**(자동번역으로 되돌리기) |
| DELETE | `/v1/brand/products/:id/translations/:locale`  | 그 로케일 통째 초기화 |
| POST   | `/v1/brand/products/:id/translations/resolve`  | 고아 엔트리 일괄 처리 `{items: [{locale, field, from, to?, action:'keep'\|'reset'}]}` (≤200) |

- 소유권은 `requireOwnedProduct(brandUserId, productId)` 공용 헬퍼. ⚠️ 실패는 `Forbidden` 이 아니라 **`NotFound`** 다 — id 를 넣어 보며 남의 제품 존재를 열거하지 못하게(brand-reviews 와 같은 방침).
- ⚠️⚠️ **GET 은 `localize()` 를 부르면 안 된다.** 부르면 `translateAndCache()` 가 돌아 브랜드가 제품 패널을 열 때마다 **Google 번역 과금 + 캐시 write** 가 난다. 목업의 기계번역은 klow_brand 가 이미 `POST /v1/brand/translate` 로 라이브 조회한다.
- `@Throttle` **없음** — 넷 다 Google 을 안 부르는 순수 DB 경로다(`/translate` 와 다르다).
- ⚠️ `:locale` 은 **`ZodValidationPipe(OverrideLocale)` 로 검증**한다. 컨트롤러 본문에서 `OverrideLocale.parse()` 를 부르면 지원하지 않는 로케일(`en` 등)이 raw ZodError 로 던져져 **400 이 아니라 500** 이 된다(실제로 그랬다).
- ⚠️⚠️ zod 에서 **`value` 에 `EnglishText`/`isAsciiPrintable` 를 걸면 안 된다** — 정의상 일본어·중국어·태국어다. 반대로 **`src` 는 반드시 ASCII 검증**한다(영문 정본을 가리키는 키라, 한글 `src` 는 스튜디오가 blur 영문화 전 값을 보냈다는 뜻이고 그대로 받으면 영원히 매칭되지 않는 고아가 된다). 이 파일의 이웃 스키마가 전부 ASCII 전용이라 **가장 나기 쉬운 복붙 버그**다.
- ⚠️ 번역문 길이 상한(`OVERRIDE_VALUE_MAX`)에 **영문 원문 상한을 그대로 쓰지 않는다** — ru/vi 번역은 영문보다 길어지는 게 흔해 정당한 번역이 400 으로 튕긴다. 남용 방지용으로만 넉넉히 잡는다.
- `resolve` 가 **전 로케일을 한 요청**으로 받는 이유: 오버라이드는 로케일마다 있는데 영문 원문은 하나라, 목업(한 번에 한 나라)만으로는 브랜드가 6개국을 순회해야 정리가 끝난다.
- `BrandApplicationsModule` 이 `ProductsModule` 을 import 한다(`ProductTranslationService` 사용). `ProductsModule` 은 `TranslationModule` 만 import 하고 그 모듈은 imports 가 없어 순환이 없다 — `SeedingModule` 이 같은 이유로 이미 같은 일을 한다.
- 동시성: PATCH 는 jsonb read-modify-write 라 `$transaction` 으로 감싸지만 READ COMMITTED 라 **탭 두 개가 동시에 저장하면 lost update 가 가능**하다(`countryPrices` replace-all 과 같은 급의 수용된 위험 — UI 가 한 번에 한 필드만 커밋한다).

### 브랜드 스토리 (2026-08-25)

브랜드관 상단 정중앙의 진입 글자가 여는 소개 페이지(커버 + 챕터 N, 최대 12). 저장은 **신규 라우트 없이** `PUT /v1/brand/applications` 의 `story` 한 칸으로 한다 — 색·폰트·링크와 같은 디자인 자동저장 큐를 타는 문서라, 전용 엔드포인트를 만들면 저장 타이밍이 두 벌로 갈린다. 형식은 `common/validation/brand.ts` 의 `BrandStorySchema`, 저장은 `Brand.story Json?`([brands](./brands.md)).

- `null` = 스토리를 만든 적 없음. 공개 노출 조건은 `enabled && 내용 있음`(klow_web `isBrandStoryPublic`).
- ⚠️⚠️ **`updateApplication` 은 `dto.story === undefined` 면 update data 에서 키를 통째로 뺀다.** 이웃 Json 필드처럼 `?? Prisma.JsonNull` 로 쓰면 안 된다 — 이 PUT 은 delta 가 아니라 **전체 문서 저장**이라, story 를 안 싣는 클라이언트(배포 창에 남은 구버전 탭·브라우저 캐시·klow_brand 롤백)가 **배경색 하나만 바꿔도 저장된 스토리가 통째로 지워진다**. 리뷰어가 "옆 줄과 모양을 맞추려고" 고치기 딱 좋은 자리라 `__tests__/brand-story.spec.ts` 가 이 분기를 잠근다. 같은 이유로 zod 에도 **`.default()` 를 붙이지 않는다**.
- ⚠️⚠️ **`chapters[].id` 는 받은 그대로 왕복해야 한다.** klow_brand 챕터 카드가 `key={chapter.id}` 로 그려져서, 서버가 id 를 새로 만들면 800ms 자동저장이 끝날 때마다 입력칸이 remount 되어 **타이핑 중 커서와 포커스가 날아간다**. 그래서 zod 에 default 가 없다.
- ⚠️ **이 스키마의 400 은 스토리만 죽이지 않는다** — 전체 문서 PUT 의 한 칸이라 배경색·폰트·링크까지 그 브랜드는 아무것도 저장되지 않는다. 그래서 문자열 상한은 klow_brand 입력칸 `maxLength` 와 **정확히 같은 값**이고(label 24 / title 60 / subtitle 200 / heading 60 / body 1200 / chapters 12), 세 곳이 `STORY_TEXT_LIMITS` 한 표를 본다(편집 입력칸 · 클라 `normalizeBrandStory` 의 slice · 서버 zod).
- **어드민은 story 를 다루지 않는다** — `BrandInput`/`BrandPatch` 에 없다. 편집 UI 가 없고, `patchOf` 가 미전송을 '변경 없음'으로 만들어 클로버 위험이 0 이라 넣을 이유가 없다. 나중에 어드민 편집이 필요해지면 `BrandInput` 과 `brands.service.ts` 의 `toPrismaBrandData()`(현재 `linkStyle` 만 destructure)를 **같이** 고칠 것.
- **번역하지 않는다** — `BrandTranslation` 은 tagline/description 만 다룬다. 해외 손님은 당분간 원문을 본다.

## 참고

- **취급 품목 게이트**: 두 생성 경로(`POST /v1/brand/products`, `/products/bulk`)는 `Brand.category` 가 `null` 이면 `400 "제품을 등록하기 전에 브랜드 카테고리를 먼저 선택해 주세요"` 로 거부한다(`assertBrandCategoryChosen`). 품목이 EFS 통관 신고값의 정본이라 첫 제품보다 먼저 정해져야 하기 때문 — 안 그러면 첫 제품이 화장품 전제로 등록된 뒤에야 바꿀 수 있다. 품목은 `PUT /v1/brand/applications` 의 `category` 로 저장하며, klow_brand 스튜디오가 **제품 등록 진입점(빈 그리드의 "상품 추가" · "브랜드 소개서로 일괄 등록하기")에서 관문으로 한 번** 묻는다. 수정 경로(`PATCH /products/:id` 등)는 게이트하지 않는다.
- **제품 텍스트 필드는 영문(ASCII) 전용** — 국제 노출 원문이자 `ProductTranslation`(en 소스) 번역의
  입력이라 non-ASCII 를 거부한다. 두 종류로 갈린다:
  **①서술형(`EnglishText`: usage·precautions·qualityAssuranceStandard·volume·manufacturer 등)** 은
  **여러 줄 허용**(`\t\r\n`) — klow_web PDP 의 `StatutoryInfo` 가 `whitespace-pre-line` 으로 렌더한다.
  **②단일 라인(`EnglishProductName`·`EnglishTag`)** 은 개행 불가(제품명은 EFS 24-5 에 그대로 들어간다).
  예외는 전성분(`ingredients`) 하나뿐 — 번역 대상이 아니라 입력 언어 그대로 노출된다.
  ⚠️ 2026-07-31 이전에는 서술형도 개행을 막아, **주의사항에 엔터 한 번만 쳐도 그 제품의 저장이 영구히
  400** 이 됐다(자동저장은 그 값을 조용히 건너뛰어 화면엔 "저장됨"만 떠서 발견이 늦었다).
  klow_brand 는 `src/lib/ascii.ts` 의 `sanitizeToAscii` 로 `※ ℃ ㎖ ’ —` 같은 기호를 ASCII 근사로 바꿔
  보내고(번역 결과에도 유니코드 문장부호가 남으므로 **번역 전후 양쪽**에서 통과시킨다), ASCII 아닌
  **글자**만 번역 대상으로 남긴다 — 글자를 스트립하면 사용자 텍스트가 소실되기 때문.
- **자유 텍스트 태그**: 주요 고민(`concerns` 최대 8개) · 추천 피부 타입(`recommendedFor` 최대 6개)은 고정 enum
  이 아니라 **영문 자유 텍스트 태그**(각 40자, `EnglishTag`)다. 브랜드가 한글로 입력하면 klow_brand 가
  위 `POST /v1/brand/translate` 로 영문화해 보낸다(요청당 20개 상한 → 20개씩 청크).
  일괄 초안(`/products/bulk`)만 예외로 **EnglishTag 를 통과 못한 항목을 버리고** 진행한다(AI 가 한글을
  섞어 보내도 30개 생성이 400 나지 않게).
- **현장 QR 판매가(`PUT /products/onsite`)**: `onsitePriceUsd=null` 이면 기본가로 되돌리고,
  `onsiteExcluded` 는 그 제품을 현장 판매에서 제외한다. 서버가 `brandId` 로 소유권을 재검증해
  남의 productId 가 섞여 오면 조용히 무시하고, `{ ok, saved }`(반영된 건수)를 돌려준다.
  - `settleKrw` 는 브랜드가 친 정산가(₩) **원문**이다 — 표시 전용이고 청구는 `onsitePriceUsd`(USD 센트).
    `salePrice ↔ basePriceUsd` 와 같은 관계로, USD 센트 왕복 시 붙는 ceil/floor 잔차(~13원)가 입력칸에
    되비치는 걸 막는다. `null` 이면 클라가 `onsitePriceUsd` 에서 역산해 보여준다.
  - `countryPrices[]{iso2, priceLocal}` 는 국가별 현장가 핀. **현지통화 major** 로 저장하며 일반 판매의
    `ProductCountryPrice.priceLocal` 과 의미가 같다(현장은 할인·무료배송이 없어 가격 하나뿐).
    ⚠️ **제품별 replace-all** 이라 클라는 늘 그 제품의 전체 배열을 보내야 한다.
  - ⚠️ 저장 테이블이 `ProductOnsiteCountryPrice` 로 **분리돼 있다**. 이유는 스키마 주석 참고 —
    핵심은 한 테이블 + `scope` 컬럼이면 기존 리더가 필터를 빠뜨릴 때 현장 핀이 소매가로 새는
    **fail-open** 이 되기 때문이다(테이블 분리는 fail-closed).
  - 저장은 보낸 제품 전체를 **deleteMany + createMany 한 쌍**으로 처리한다(제품 수와 무관하게 2문).
    스칼라 UPDATE 는 **값이 실제로 바뀐 제품만** — `Product.updatedAt` 이 튀면 `ProductTranslation`
    캐시가 로케일마다 무효화돼 가격 한 글자 수정이 카탈로그 전체 재번역을 부른다.
    클라(klow_brand)도 같은 이유로 **건드린 제품만** 보낸다.
  - `settleKrw`/`countryPrices` 는 신규 필드라 nullable / `.default([])` — 서버를 먼저 배포해도
    구 klow_brand 가 400 을 맞지 않는다.
  - `discountPct` (2026-08-13, → `Product.onsiteDiscountPct`)는 **취소선 표시용 할인율**이다.
    세팅한 가격이 이미 할인가라 청구·정산은 불변이고, 손님 화면에만 할인 전 가격이 그어져 함께 보인다
    (파생 규칙은 [`products.md`](./products.md) `mode=onsite` 항목).
    ⚠️ 위 두 필드의 `.default()` 패턴을 **일부러 따르지 않고 `.nullish()`** 다 — `.default(0)` 이면
    배포 창에 열려 있던 구 klow_brand 탭이 저장할 때 브랜드가 켠 할인율을 조용히 0 으로 지운다.
    **안 보내면 현재 값 유지**가 계약이고, 서버가 `owned` 행에서 현재 값을 읽어 폴백한다.
- 추가 정보: 송화인, 정산 계좌 정보 등은 `operational-profile` 로 저장.
- **무료배송·박스 규격은 전용 엔드포인트가 없다** (2026-07-29). 무료배송은 국가별 설정
  (`countryPrices[].freeShipping`)이 됐고, 박스 규격(`weightG`/`box*Cm`)과 함께 제품 create/PATCH payload 에
  실려 저장된다 — 가격 탭 저장 한 번에 전부 반영된다.
  ⚠️ `countryPrices` 저장은 **replace-all** 이라 클라는 언제나 그 제품의 **전체 국가 배열**을 보내야 한다
  (한 국가만 고치려고 부분 배열을 보내면 나머지 국가의 핀·할인·무료배송이 전부 삭제된다).
- **응답의 국가별 설정**: 목록/단건은 `pins{iso:priceLocal}` · `discounts{iso:pct}` · `freeShippingCountries[iso]`
  세 맵으로 국가별 원본을 돌려준다(폼 재구성용). 자세히는 [`../../pricing-model.md`](../../pricing-model.md).
- **초안 일괄 등록(`POST /v1/brand/products/bulk`)은 `countryPrices` 를 아예 받지 않는다** —
  `createMany` 라 `writeProductCountryPrices` 를 못 타므로 `BrandProductDraftInput` 에서 omit 했다
  (받아놓고 버리지 않는다). 국가별 설정은 발행 전 편집 폼에서 채운다.
- 승인/거부/제품 단위 승인·차단·환불은 모두 [subscription](./subscription.md) 의 어드민 `/admin/brand-subscriptions/*` 에서 처리한다.
- 브랜드 탈퇴(철회)는 [brand-auth](./brand-auth.md) `withdrawal-request` + 어드민 [brands](./brands.md) `brand-withdrawals` 참고.
