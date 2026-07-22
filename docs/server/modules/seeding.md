# seeding — 크리에이터 시딩(샘플) 프로그램

- **모듈 경로**: `src/modules/seeding/`
- **주 클라이언트**: `klow_brand`(시딩 링크 발급·요율/비교 미리보기·이용계약서 서명) + `klow_web`(바이어 공개 페이지 `/seed/:token` claim/checkout) + `klow_admin`(시딩비용·해외배송 비교요율 표 편집).
- **데이터 모델**: `SeedingLink`(발급 링크 — token·국가·무게·결제주체/선택모드 2×2 매트릭스·통관 스냅샷 + 수화인 입력 `recipientInstagram`·브랜드 메모 `recipientSnsMemo`(발송대기 "받을 사람 SNS 주소", 2026-07-02 `add_seeding_link_recipient_sns_memo`)·`reviewCompleted`(후기 제작 완료 토글, 2026-06-29 `seeding_instagram_review`)), `ManualSeedingRecord`(KLOW 이전 자체 시딩 수동 import 기록 — `data` JSON + `reviewCompleted`, brand scope), `SeedingServiceAgreement`(후청구 이용계약서, `brandUserId` 당 1행), `SeedingRate`(국가×무게 시딩 배송비, 모든 비용/마진 포함), `ShippingRate`(carrier=EMS|DHL **비교가** 티어 — rateKrw 가 곧 표시가), `Order`/`OrderItem`(시딩 주문, `isSeeding=true`).
- **시딩이란**: 브랜드가 크리에이터에게 보낼 무료/유료 샘플 발송 링크(`/seed/:token`)를 발급하면, 크리에이터(바이어)가 이메일·배송지를 입력해 **무료 claim** 하거나 **유료 checkout**(배송비 결제)으로 신청한다. 한 링크 = 한 샘플 = 한 EFS 송장.
- **2×2 매트릭스**: 링크는 `paymentBy`(brand=후청구 무료 / customer=바이어 배송비 결제) × `selectionMode`(brand=브랜드 지정 / customer=후보 중 바이어 선택)로 분기한다. 선택 후보(`selectionSkus`)는 등록 product ID 가 아니라 **자유 텍스트 제품명 라벨**이라 소유 검증 없이 trim·중복제거만 하고, 바이어 선택은 claim/checkout 의 `validateSelection`(후보 멤버십·개수·`selectionLimit` 검증)으로 검증한다.
- **국가 확정 시점 (2026-07)**: `SeedingLink.countryCode` 는 **nullable**(`add_seeding_link_country_optional`). **고객 결제**는 정액 배송비를 확정해야 하므로 발급 시점에 국가 필수(`CreateSeedingLinkInput` superRefine 이 `paymentBy='customer'` 면 `countryCode` 강제). **브랜드 결제**는 국가 없이 발급(`countryCode=null`, `feeKrw=0`)하고 **바이어가 claim 시 배송지 국가를 직접 고른다**. `getByToken` 은 국가 미정 링크에 `country:null` + `countryOptions`(=`supportedCountries`, 브랜드 발급 드롭다운과 동일 목록)를 실어 내리고, claim 은 `effectiveCountry = link.countryCode ?? dto.countryCode`(미정 링크만 후보 멤버십 검증)로 캐리어/EFS 필드/주문 국가를 해석하고 링크에 확정 저장한다. klow_brand 발급 패널은 결제방식을 첫 단계로 올려 고객 결제일 때만 국가→무게를 점진적으로 노출한다.
- **무료 claim** (`paymentBy='brand'`, `POST /v1/seeding/:token/claim`): 바이어 이메일·전화·배송지(+ 국가 미정 링크면 `countryCode`)를 입력하면 즉시 `Order`(`isSeeding=true`, `totalUsd=0`, `shippingFeeUsd=0`)를 생성하고 `paymentStatus=paid`/`status=processing`/`paidAt` 자동 세팅 → PG 안 거치고 바로 출고 대기 큐로 간다. 링크는 `claimed` 로 전이(동시 claim 은 트랜잭션 내 재확인으로 차단). 커밋 후 주문확인 메일(`/track/:id?t=서명토큰`) + EFS 송장 자동 발급을 best-effort 로 실행하되 **await 하지 않고 백그라운드(`Promise.allSettled`)로 보내** claim 응답을 막지 않는다(외부 Resend/EFS 지연 제거 → 확인 화면 즉시 표시; 실패 흡수 → 어드민 미발급 대기 폴백). 중국(`CN`) 배송은 수취인 신분증 번호(`recipientTaxId`) 필수.
- **유료 checkout** (`paymentBy='customer'`, `POST /v1/seeding/:token/checkout`): 무료 주문을 즉시 paid 로 만들지 않고 `paymentStatus=pending` 주문(`totalUsd=shippingFeeUsd=배송비 USD 센트`)을 만든 뒤 기존 결제 플로우에 태운다. 비로그인이면 컨트롤러가 게스트 결제 쿠키(HMAC)를 내려주고, 클라가 `/v1/payment/prepare → Eximbay SDK → /v1/payment/verify` 로 배송비만 결제한다. 로그인 상태면 주문을 그 사용자에 귀속(prepare 가 user-ownership 검증). 결제 성공(`markPaid`) 후에야 링크가 `claimed` 로 전이되고 송장·확인메일이 발급된다. PG 심사용 동의 3종(`termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`) + IP 를 주문 생성 시 저장. 두 엔드포인트 모두 `THROTTLE_TIGHT`(IP당 5회/분)로 enumeration·스팸 차단.
- **배송비 = SeedingRate**: 발급 시 `seedingRate.resolveCost(iso2, weightG)` 가 국가×무게 표에서 **무게 올림** 조회한 `costKrw` 를 그대로 배송비로 쓴다 — 운영팀이 원가·캐리어·할증·마진을 미리 반영한 정본값이라 **런타임 비교·할증 가산·구 ₩1000 정액수수료 전부 없음**. 캐리어는 비교·선택하지 않고 제품 `ShippingCountry.productCarrier`(국가 고정값, 직통=EFS/그 외=EMS)를 재사용한다(`shipping.service.resolveCarrier`, EFS 제외구역이면 차단). 고객 결제 링크만 이 요율을 바이어에게 청구(`shippingFeeKrw`), 브랜드 결제 링크는 `shippingFeeKrw=null`(현재 미청구).
- **EMS/DHL 비교가 (shipping-rate.service)**: 발급 화면에서 "KLOW 시딩가 vs EMS vs DHL 직접발송" 비교를 보여주기 위한 별도 표(`ShippingRate`, carrier=EMS|DHL). **표시가 = `ShippingRate.rateKrw` 그대로** — 업로드 요율표가 EMS 특별운송수수료·DHL 유류할증료까지 이미 통합한 최종가라 재조합 없음(2026-07). 어드민 **해외배송 비교요율** 탭(`admin-shipping-rate.controller`)에서 EMS/DHL 별 셀 편집·엑셀 업로드(셀 값을 그대로 저장). 구 컬럼 `ShippingCountry.emsSpecialFeePerKgKrw`·`ShopSettings.dhlFuelSurchargeRate` 는 **dormant**(계산 미사용, 컬럼·편집 UI 만 유지).
- **통관(customs) 스냅샷**: 시딩은 `Product` 가 없으므로 `OrderItem.productId=null` + 통관 스냅샷을 박는다. 통관 신고가(EFS field 26)는 0 이면 거부되므로 발급 시 링크별 **$8.50~$12.50 랜덤**(`declaredValueUsd`, USD 센트 850~1250)을 저장해 `OrderItem.unitPriceUsd` 로 사용(이 때문에 `totalUsd = Σ(unit×qty)` 불변식이 깨지지만 PG 청구가 없는 시딩 주문에 한한 의도된 예외). 통관 품명은 한글 brand.name 대신 영문 3종(`Korean Skincare Serum/Toner/Cream`) 중 링크별 랜덤(`itemName`). HS/카테고리는 `null` 로 두고 송장 빌더의 화장품 **fallback HS `3304991000`** 을 탄다.
- **이용계약서 서명**: 후청구(브랜드 결제) 시딩 이용계약서는 `BrandUser` 계정당 1회 동의 — 클라이언트 서명 캔버스 PNG data URL 을 디코드해 R2(`seeding-agreements/`, `brandUserId` scope)에 업로드하고 DB(`SeedingServiceAgreement`)엔 공개 URL 만 저장한다(data URL 을 행에 박지 않음). 재동의 시 `acceptedAt` 갱신. 브랜드 미연결 계정(`brandId=null`)도 서명 가능하므로 `requireBrandId` 가 아니라 `user.id` 로 스코프.
- **발급 가능국**: `seedingRate.supportedCountries()` = SeedingRate 티어 보유 ∩ `productCarrier` 설정 국가(배송지원 `enabled` 무관). 캐리어 없는 국가를 드롭다운에서 빼 "목록엔 뜨는데 발급 실패"를 막는다.
- **초기 시드**: `npm run seed:seeding-rates`(`prisma/data/seeding_rates.json`, 엑셀 `KLOW_시딩_가격표` 고객_가격표 기준).
- **관련 파일**: `seeding.service.ts`(링크 발급·claim·checkout·계약서 서명·review/sns-memo 토글), `manual-seeding.service.ts`(KLOW 이전 수동 시딩기록 엑셀 추출·CRUD), `seeding-rate.service.ts`(SeedingRate 표 조회·편집·엑셀), `shipping-rate.service.ts`(EMS/DHL 비교가), `xlsx-grid.ts`(캐리어 시트 파서), 컨트롤러 4개(brand·public·admin-seeding-rate·admin-shipping-rate).
- **교차링크**: [shipping](./shipping.md)(productCarrier·EFS 제외구역·resolveCarrier), [orders](./orders.md)(게스트 주문 토큰·동의), [payment](./payment.md)(유료 checkout prepare/verify), [shipments](./shipments.md)(EFS 송장 자동 발급).

## brand-seeding.controller.ts (`@Controller('v1/brand/seeding')`)

> 전체 라우트 `BrandGuard`. 발급·미리보기는 `requireBrandId`, 이용계약서(agreement)는 `brandId=null` 계정도 가능하도록 `user.id` 스코프.

| Method | Path                                        | 기능                                                              |
|--------|---------------------------------------------|-------------------------------------------------------------------|
| GET    | `/v1/brand/seeding/links`                   | 내 브랜드 시딩 링크 목록(cancelled 제외)                          |
| GET    | `/v1/brand/seeding/countries`               | 발급 가능국 목록(SeedingRate 티어 ∩ productCarrier)              |
| GET    | `/v1/brand/seeding/quote?weightG=`          | 적용무게(g)에 대한 국가별 1개당 시딩 배송비(KRW) 맵              |
| GET    | `/v1/brand/seeding/comparison?weightG=`     | 국가별 KLOW vs EMS vs DHL 표시가 맵                              |
| GET    | `/v1/brand/seeding/comparison-table?iso2=`  | 한 국가의 시딩 티어별 KLOW/EMS/DHL 비교 표                       |
| POST   | `/v1/brand/seeding/links`                   | `count` 개 시딩 링크 발급(통관 품명·신고가 랜덤 스냅샷)          |
| DELETE | `/v1/brand/seeding/links/:id`               | pending 링크 취소(soft, `cancelled`)                            |
| PATCH  | `/v1/brand/seeding/links/:id/review`        | "후기 제작 완료" 토글(`reviewCompleted`)                        |
| PATCH  | `/v1/brand/seeding/links/:id/sns-memo`      | "받을 사람 SNS 주소" 메모 저장/삭제(`snsMemo`, null=삭제)        |
| GET    | `/v1/brand/seeding/agreement`               | 내 이용계약서 동의/서명 조회                                     |
| POST   | `/v1/brand/seeding/agreement`               | 이용계약서 동의·서명 저장(PNG → R2)                             |
| POST   | `/v1/brand/seeding/manual-records/extract`  | 수동 시딩기록 엑셀 업로드 → OpenAI 추출 → 후보 반환(미저장, `THROTTLE_TIGHT`) |
| GET    | `/v1/brand/seeding/manual-records`          | 내 브랜드 수동 시딩기록 목록                                     |
| POST   | `/v1/brand/seeding/manual-records`          | 추출 후보 중 선택분 일괄 적재                                    |
| PATCH  | `/v1/brand/seeding/manual-records/:id`      | 수동 기록 수정                                                   |
| PATCH  | `/v1/brand/seeding/manual-records/:id/review`| 수동 기록 "후기 제작 완료" 토글(`reviewCompleted`)             |
| DELETE | `/v1/brand/seeding/manual-records/:id`      | 수동 기록 1건 삭제                                              |

## public-seeding.controller.ts (`@Controller('v1/seeding')`)

> public. claim/checkout 은 `@Throttle`(IP당 5회/분). checkout 만 `OptionalUserGuard`(로그인 시 주문 귀속, 게스트면 결제 쿠키 발급).

| Method | Path                          | 기능                                                                 |
|--------|-------------------------------|----------------------------------------------------------------------|
| GET    | `/v1/seeding/:token`          | 링크 공개 정보(상태·국가·결제주체·선택후보·배송비)                  |
| POST   | `/v1/seeding/:token/claim`    | 무료 claim — ₩0 주문 생성, paid 자동, 송장/메일 발급                |
| POST   | `/v1/seeding/:token/checkout` | 유료 checkout — pending 주문 생성, 게스트 쿠키, 이후 /v1/payment/*   |

## admin-seeding-rate.controller.ts (`@Controller('admin/seeding-rates')`)

> 전체 라우트 `AdminGuard`. 국가×무게 시딩 배송비 표(`SeedingRate`, 모든 비용/마진 포함, 무게 올림 조회). 어드민 **시딩비용** 탭(`/seeding-cost`). 캐리어는 제품 `productCarrier` 재사용.

| Method | Path                                    | 기능                                          |
|--------|-----------------------------------------|-----------------------------------------------|
| GET    | `/admin/seeding-rates`                  | 국가 목록 + 티어 커버리지 + 고정 캐리어       |
| GET    | `/admin/seeding-rates/:iso2`            | 국가의 무게→비용 티어(오름차순)               |
| PUT    | `/admin/seeding-rates`                  | `(iso2, weightG, costKrw)` 셀 upsert          |
| DELETE | `/admin/seeding-rates`                  | `(iso2, weightG)` 셀 삭제                     |
| POST   | `/admin/seeding-rates/import/preview`   | 시딩 가격표 엑셀 파싱 → 국가별 상태 diff      |
| POST   | `/admin/seeding-rates/import/apply`     | 같은 파일 재파싱 + 선택 국가 티어 통째 교체   |

## admin-shipping-rate.controller.ts (`@Controller('admin/shipping-rates')`)

> 전체 라우트 `AdminGuard`. EMS/DHL **비교가** 티어(`ShippingRate`, carrier=EMS|DHL, rateKrw=표시가) — KLOW 시딩가가 직접발송보다 얼마나 싼지 보여주는 표시 전용. `carrier` 쿼리/파라미터(`EMS`|`DHL`) 필수(아니면 400). 어드민 **해외배송 비교요율** 탭.

| Method | Path                                        | 기능                                               |
|--------|---------------------------------------------|----------------------------------------------------|
| GET    | `/admin/shipping-rates?carrier=`            | 캐리어 국가 목록 + 요율 티어 커버리지(개수·무게·요율 범위) |
| GET    | `/admin/shipping-rates/:carrier/:iso2`      | 캐리어·국가의 base 무게 티어(오름차순)             |
| PUT    | `/admin/shipping-rates`                     | `(carrier, iso2, weightG, rateKrw)` 셀 upsert      |
| DELETE | `/admin/shipping-rates`                     | `(carrier, iso2, weightG)` 셀 삭제                 |
| POST   | `/admin/shipping-rates/import/preview`      | 캐리어 요율표 엑셀 파싱 → 국가별 상태 diff         |
| POST   | `/admin/shipping-rates/import/apply`        | 같은 파일 재파싱 + 선택 국가 요율 티어 통째 교체(셀 값 그대로 저장) |
