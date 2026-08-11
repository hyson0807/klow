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
| PUT    | `/v1/brand/applications`                      | 신청 내용 수정                                                    |
| GET    | `/v1/brand/applications/me`                   | 내 신청 조회 (홈페이지/타겟국가/송화인/계좌 등 포함)              |
| POST   | `/v1/brand/applications/init-draft`           | 드래프트 생성 (슬러그 기반 — 가입 시 brand 미생성 케이스 안전망, idempotent) |
| POST   | `/v1/brand/applications/submit-for-review`    | 드래프트 → 검토 제출 (모든 필드 완성 확인, `pgCustomerKey` 발급)  |
| PATCH  | `/v1/brand/applications/operational-profile`  | 운영 프로필(송화인 4 + 계좌 3 필드) 저장 — OnboardingGate         |

### 셀프 상품 관리 (Product)

| Method | Path                              | 기능                                                              |
|--------|-----------------------------------|-------------------------------------------------------------------|
| POST   | `/v1/brand/products`              | 상품 생성 (신청 진행 중 또는 승인 후 모두 `pending` 으로 시작)    |
| POST   | `/v1/brand/products/bulk`         | 상품 일괄 생성 (draft 다건)                                       |
| GET    | `/v1/brand/products`              | 내 브랜드 상품 목록                                               |
| PATCH  | `/v1/brand/products/reorder`      | 상품 노출 순서 변경 (드래그&드롭, `ids[]` 최대 500 — 자기 브랜드 소유만 반영) |
| PUT    | `/v1/brand/products/onsite`       | 현장(박람회 부스) QR 판매가 일괄 저장 (`items[]{id, onsitePriceUsd(센트\|null), onsiteExcluded, settleKrw(₩\|null), countryPrices[]{iso2, priceLocal}}` 최대 500, `:id` 위에 선언) |
| PATCH  | `/v1/brand/products/:id/hidden`   | 상품 가리기 On/Off 토글 (`Product.hidden`, status 유지·노출/판매만 제외; 단일 필드 전용 PATCH, `:id` 위에 선언) |
| PATCH  | `/v1/brand/products/:id`          | 상품 수정 (자기 brandId 확인)                                     |
| DELETE | `/v1/brand/products/:id`          | 상품 삭제                                                         |

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
