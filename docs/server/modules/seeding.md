# seeding — 크리에이터 시딩(샘플) 프로그램

- **모듈 경로**: `src/modules/seeding/`
- **주 클라이언트**: `klow_brand`(시딩 링크 발급·요율/비교 미리보기·이용계약서 서명, + 제품 가격 탭의 배송비 청구 계산기가 `GET /v1/brand/seeding/quote` 재사용) + `klow_web`(바이어 공개 페이지 `/seed/:token` claim/checkout) + `klow_admin`(배송비용·해외배송 비교요율 표 편집).
- **데이터 모델**: `SeedingLink`(발급 링크 — token·국가·무게·결제주체/선택모드 2×2 매트릭스·통관 스냅샷 + 수화인 입력 `recipientInstagram`·브랜드 메모 `recipientSnsMemo`(발송대기 "받을 사람 SNS 주소", 2026-07-02 `add_seeding_link_recipient_sns_memo`)·`reviewCompleted`(후기 제작 완료 토글, 2026-06-29 `seeding_instagram_review`)), `ManualSeedingRecord`(KLOW 이전 자체 시딩 수동 import 기록 — `data` JSON + `reviewCompleted`, brand scope), `SeedingServiceAgreement`(후청구 이용계약서, `brandUserId` 당 1행), `SeedingRate`(국가×무게 배송비 요율표, 모든 비용/마진 포함 — 시딩·일반주문 공용), `ShippingRate`(carrier=EMS|DHL **비교가** 티어 — rateKrw 가 곧 표시가), `Order`/`OrderItem`(시딩 주문, `isSeeding=true`).
- **시딩이란**: 브랜드가 크리에이터에게 보낼 무료/유료 샘플 발송 링크(`/seed/:token`)를 발급하면, 크리에이터(바이어)가 이메일·배송지를 입력해 **무료 claim** 하거나 **유료 checkout**(배송비 결제)으로 신청한다. 한 링크 = 한 샘플 = 한 EFS 송장.
- **2×2 매트릭스**: 링크는 `paymentBy`(brand=후청구 무료 / customer=바이어 배송비 결제) × `selectionMode`(brand=브랜드 지정 / customer=후보 중 바이어 선택)로 분기한다. 선택 후보(`selectionSkus`)는 등록 product ID 가 아니라 **자유 텍스트 제품명 라벨**이라 소유 검증 없이 trim·중복제거만 하고, 바이어 선택은 claim/checkout 의 `validateSelection`(후보 멤버십·개수·`selectionLimit` 검증)으로 검증한다.
- **국가 확정 시점 (2026-07)**: `SeedingLink.countryCode` 는 **nullable**(`add_seeding_link_country_optional`). **고객 결제**는 정액 배송비를 확정해야 하므로 발급 시점에 국가 필수(`CreateSeedingLinkInput` superRefine 이 `paymentBy='customer'` 면 `countryCode` 강제). **브랜드 결제**는 국가 없이 발급(`countryCode=null`, `feeKrw=0`)하고 **바이어가 claim 시 배송지 국가를 직접 고른다**. `getByToken` 은 국가 미정 링크에 `country:null` + `countryOptions`(=`supportedCountries`, 브랜드 발급 드롭다운과 동일 목록)를 실어 내리고, claim 은 `effectiveCountry = link.countryCode ?? dto.countryCode`(미정 링크만 후보 멤버십 검증)로 캐리어/EFS 필드/주문 국가를 해석하고 링크에 확정 저장한다. klow_brand 발급 패널은 결제방식을 첫 단계로 올려 고객 결제일 때만 국가→무게를 점진적으로 노출한다.
- **무료 claim** (`paymentBy='brand'`, `POST /v1/seeding/:token/claim`): 바이어 이메일·전화·배송지(+ 국가 미정 링크면 `countryCode`)를 입력하면 즉시 `Order`(`isSeeding=true`, `totalUsd=0`, `shippingFeeUsd=0`)를 생성하고 `paymentStatus=paid`/`status=processing`/`paidAt` 자동 세팅 → PG 안 거치고 바로 출고 대기 큐로 간다. 링크는 `claimed` 로 전이(동시 claim 은 트랜잭션 내 재확인으로 차단). 커밋 후 주문확인 메일(`/track/:id?t=서명토큰`) + EFS 송장 자동 발급을 best-effort 로 실행하되 **await 하지 않고 백그라운드(`Promise.allSettled`)로 보내** claim 응답을 막지 않는다(외부 Resend/EFS 지연 제거 → 확인 화면 즉시 표시; 실패 흡수 → 어드민 미발급 대기 폴백). 중국(`CN`) 배송은 수취인 신분증 번호(`recipientTaxId`) 필수.
- **유료 checkout** (`paymentBy='customer'`, `POST /v1/seeding/:token/checkout`): 무료 주문을 즉시 paid 로 만들지 않고 `paymentStatus=pending` 주문(`totalUsd=shippingFeeUsd=배송비 USD 센트`)을 만든 뒤 기존 결제 플로우에 태운다. 비로그인이면 컨트롤러가 게스트 결제 쿠키(HMAC)를 내려주고, 클라가 `/v1/payment/prepare → Eximbay SDK → /v1/payment/verify` 로 배송비만 결제한다. 로그인 상태면 주문을 그 사용자에 귀속(prepare 가 user-ownership 검증). 결제 성공(`markPaid`) 후에야 링크가 `claimed` 로 전이되고 송장·확인메일이 발급된다. PG 심사용 동의 3종(`termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`) + IP 를 주문 생성 시 저장. 두 엔드포인트 모두 `THROTTLE_TIGHT`(IP당 5회/분)로 enumeration·스팸 차단.
- **배송비 = SeedingRate 요율표**: 발급 시 `logisticsRate.resolveCost(iso2, weightG)` 가 국가×무게 표에서 **무게 올림** 조회한 `costKrw` 를 그대로 배송비로 쓴다 — 운영팀이 원가·캐리어·할증·마진을 미리 반영한 정본값이라 **런타임 비교·할증 가산·구 ₩1000 정액수수료 전부 없음**. **2026-07-29 부터 일반 주문도 같은 표를 쓴다**(일반 주문은 500g 티어가 곧 고객 배송비 — [shipping](./shipping.md)). 서비스는 `shipping/logistics-rate.service.ts` `LogisticsRateService`(ShippingModule 소유·export, 구 `seeding/seeding-rate.service.ts` `SeedingRateService`). 캐리어는 비교·선택하지 않고 `shipping.service.resolveCarrier(iso2, addr, weightG)` 가 무게 분기(`seedingCarrierSplitWeightG`, 있으면 무게≤분기값 EFS/초과 EMS) 또는 국가 고정 `productCarrier` 로 결정한다(EFS 제외구역이면 차단). 고객 결제 링크만 이 요율을 바이어에게 청구(`shippingFeeKrw`), 브랜드 결제 링크는 `shippingFeeKrw=null`(현재 미청구).
- **EMS/DHL 비교가 (shipping-rate.service)**: 발급 화면에서 "KLOW 시딩가 vs EMS vs DHL 직접발송" 비교를 보여주기 위한 별도 표(`ShippingRate`, carrier=EMS|DHL). **표시가 = `ShippingRate.rateKrw` 그대로** — 업로드 요율표가 EMS 특별운송수수료·DHL 유류할증료까지 이미 통합한 최종가라 재조합 없음(2026-07). 어드민 **해외배송 비교요율** 탭(`shipping/admin-shipping-rate.controller` — 파일은 shipping 모듈 소유, 2026-07 이동)에서 EMS/DHL 별 셀 편집·엑셀 업로드(셀 값을 그대로 저장). 구 컬럼 `ShippingCountry.emsSpecialFeePerKgKrw`·`ShopSettings.dhlFuelSurchargeRate` 는 **dormant**(계산 미사용, 컬럼·편집 UI 만 유지).
- **통관(customs) 스냅샷**: 시딩은 `Product` 가 없으므로 `OrderItem.productId=null` + 통관 스냅샷을 박는다. 통관 신고가(EFS field 26)는 0 이면 거부되므로 발급 시 링크별 **$8.50~$12.50 랜덤**(`declaredValueUsd`, USD 센트 850~1250)을 저장해 `OrderItem.unitPriceUsd` 로 사용(이 때문에 `totalUsd = Σ(unit×qty)` 불변식이 깨지지만 PG 청구가 없는 시딩 주문에 한한 의도된 예외). 통관 품명은 한글 brand.name 대신 영문 후보 중 링크별 랜덤(`itemName`)이고, 후보 목록이 **발급 시점 `Brand.category` 별로 갈린다** — 화장품 `Korean Skincare Serum/Toner/Cream`, 치과재료 `Dental Impression Material/Dental Modelling Paste/Dental Wax Preparation`. 후보는 HS 코드와 같은 행(`BRAND_CATEGORY_CUSTOMS[category].seedingItemNames`)에 묶여 있다 — 품명과 HS 가 어긋나면 통관에서 걸리기 때문. `itemName` 은 발급 시점에 동결되므로 브랜드가 나중에 품목을 바꿔도 기존 링크의 품명은 옛 값으로 남는다. HS/카테고리는 `null` 로 두고 **송장 빌더가 `Brand.category` 에서 파생**한다(→ [shipments](./shipments.md) 통관 항목) — 링크에 스냅샷하지 않으므로 품목 변경이 미발송 링크에 곧바로 반영된다.
- **이용계약서 서명**: 후청구(브랜드 결제) 시딩 이용계약서는 `BrandUser` 계정당 1회 동의 — 클라이언트 서명 캔버스 PNG data URL 을 디코드해 R2(`seeding-agreements/`, `brandUserId` scope)에 업로드하고 DB(`SeedingServiceAgreement`)엔 공개 URL 만 저장한다(data URL 을 행에 박지 않음). 재동의 시 `acceptedAt` 갱신. 브랜드 미연결 계정(`brandId=null`)도 서명 가능하므로 `requireBrandId` 가 아니라 `user.id` 로 스코프.
- **발급 가능국**: `logisticsRate.supportedCountries()` = 요율표 티어 보유 ∩ 캐리어 결정 가능(`productCarrier` 또는 `seedingCarrierSplitWeightG`) 국가. **배송지원 `enabled` 무관** — 그 게이트는 일반 주문 전용이다. 캐리어 없는 국가를 드롭다운에서 빼 "목록엔 뜨는데 발급 실패"를 막는다.
- **초기 시드**: `npm run seed:seeding-rates`(`prisma/data/seeding_rates.json`, 엑셀 `KLOW_시딩_가격표` 고객_가격표 기준).
- **관련 파일**: `seeding.service.ts`(링크 발급·claim·checkout·계약서 서명·review/sns-memo 토글), `manual-seeding.service.ts`(KLOW 이전 수동 시딩기록 엑셀 추출·CRUD), `shipping/logistics-rate.service.ts`(요율표 조회·편집·엑셀 — shipping 모듈 소유·export, 2026-07-29 이동), `shipping/rate-sheet-ai.service.ts`(임의 포맷 요율표 AI 추출), `shipping/shipping-rate.service.ts`(EMS/DHL 비교가 — shipping 모듈 소유·export, 2026-07 이동), `shipping/xlsx-grid.ts`(캐리어 시트 파서), 컨트롤러 3개(brand·public·admin-seeding-rate) + shipping 모듈의 admin-shipping-rate.
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

> 전체 라우트 `AdminGuard`. 국가×무게 배송비 요율표(`SeedingRate`, 모든 비용/마진 포함, 무게 올림 조회) — **시딩·일반주문 공용**. 어드민 **배송비용** 탭(`/seeding-cost`). 캐리어는 `productCarrier` + 무게 분기.

| Method | Path                                    | 기능                                          |
|--------|-----------------------------------------|-----------------------------------------------|
| GET    | `/admin/seeding-rates`                  | 국가 목록 + 티어 커버리지 + 고정 캐리어       |
| GET    | `/admin/seeding-rates/:iso2`            | 국가의 무게→비용 티어(오름차순)               |
| PUT    | `/admin/seeding-rates`                  | `(iso2, weightG, costKrw)` 셀 upsert          |
| DELETE | `/admin/seeding-rates`                  | `(iso2, weightG)` 셀 삭제                     |
| POST   | `/admin/seeding-rates/import/preview`   | 시딩 가격표 엑셀 파싱 → 국가별 상태 diff      |
| POST   | `/admin/seeding-rates/import/apply`     | 같은 파일 재파싱 + 선택 국가 티어 통째 교체   |
| POST   | `/admin/seeding-rates/:iso2/import/ai-preview` | 임의 포맷 요율표 엑셀 → AI 추출 + diff (적용 안 함) |
| PUT    | `/admin/seeding-rates/:iso2/tiers`      | 한 국가 티어 일괄 저장(`mode: replace \| merge`) |

**AI 요율표 추출 (국가 상세, 2026-08)** — 위의 `import/preview`·`import/apply` 는 `고객_가격표`(국가×무게 매트릭스) **고정 포맷 전용**이라, 캐리어에서 받은 국가 하나짜리 요율표(헤더 이름·단위·열 위치가 매번 다름)에는 못 쓴다. 그래서 국가 상세(`/seeding-cost/[iso2]`)에 별도 경로를 뒀다 — **목록 페이지의 기존 업로드와 무관하게 병존**한다.

- **AI 는 레이아웃만 판단하고 금액은 서버가 원본 셀에서 직접 읽는다.** 71~140행 금액을 LLM 이 옮겨 적으면 자릿수 환각이 나므로, AI 응답은 `{sheetName, orientation, weightIndex, priceIndex, weightUnit, dataStart/EndIndex, currency, notes}`(`RateSheetLayout`) 뿐이다. 저장되는 값은 항상 파일값과 일치한다.
- 서비스는 `shipping/rate-sheet-ai.service.ts`(`RateSheetAiService`, ShippingModule 소유) — `inferLayout()`(OpenAI, `OPENAI_MODEL ?? gpt-4o-mini`, 시트당 앞 40행×30열만 프롬프트에 실음) + `extract()`(**LLM 미경유 결정론적 파싱**) + 후보 열 수집. `LogisticsRateService.aiImportPreview()` 가 이를 호출하고 기존 `buildTierDiff` 로 diff 를 만든다.
- **열 오선택 복구**: 응답에 `candidates`(숫자 5개 이상 든 열/행 + 헤더)를 함께 실어, 어드민이 미리보기에서 무게/가격 열을 바꾸면 **같은 파일 + `layout` 을 재전송해 AI 없이 즉시 재추출**한다. 추출 0건이어도 400 을 던지지 않고 candidates 와 함께 돌려주는 이유가 이것 — 던지면 어드민이 바로잡을 화면 자체가 안 뜬다.
- **버리는 행은 노출한다**: `SeedingRateUpsert` 와 같은 상한(무게 1~50,000g / 0~10,000,000원)을 벗어난 행은 `skipped[]` 에 사유와 함께 담겨 경고 배너로 뜬다(예: 50kg 초과 티어). 통화가 KRW 가 아니면 400.
- **적용**은 AI 를 다시 타지 않는다 — 미리보기에서 확인한 티어를 그대로 `PUT :iso2/tiers` 로 되돌려 보낸다. `replace` 는 그 국가 티어 전체 교체(목록 업로드와 같은 의미), `merge` 는 들어온 무게만 갱신. 전체 교체가 지울 기존 티어는 미리보기 `removed[]` 로 먼저 보여준다(표준 소형 티어 100g/250g/750g 이 조용히 사라지지 않도록).

## admin-shipping-rate.controller.ts (`@Controller('admin/shipping-rates')`) — 파일 위치: `src/modules/shipping/`

> 전체 라우트 `AdminGuard`. EMS/DHL **비교가** 티어(`ShippingRate`, carrier=EMS|DHL, rateKrw=표시가) — KLOW 시딩가가 직접발송보다 얼마나 싼지 보여주는 표시 전용. `carrier` 쿼리/파라미터(`EMS`|`DHL`) 필수(아니면 400). 어드민 **해외배송 비교요율** 탭.

| Method | Path                                        | 기능                                               |
|--------|---------------------------------------------|----------------------------------------------------|
| GET    | `/admin/shipping-rates?carrier=`            | 캐리어 국가 목록 + 요율 티어 커버리지(개수·무게·요율 범위) |
| GET    | `/admin/shipping-rates/:carrier/:iso2`      | 캐리어·국가의 base 무게 티어(오름차순)             |
| PUT    | `/admin/shipping-rates`                     | `(carrier, iso2, weightG, rateKrw)` 셀 upsert      |
| DELETE | `/admin/shipping-rates`                     | `(carrier, iso2, weightG)` 셀 삭제                 |
| POST   | `/admin/shipping-rates/import/preview`      | 캐리어 요율표 엑셀 파싱 → 국가별 상태 diff         |
| POST   | `/admin/shipping-rates/import/apply`        | 같은 파일 재파싱 + 선택 국가 요율 티어 통째 교체(셀 값 그대로 저장) |
