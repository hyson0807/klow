# seeding — 크리에이터 시딩(샘플) 프로그램

- **모듈 경로**: `src/modules/seeding/`
- **주 클라이언트**: `klow_brand`(시딩 링크 발급·요율/비교 미리보기·이용계약서 서명, + 제품 가격 탭의 배송비 청구 계산기가 `GET /v1/brand/seeding/quote` 재사용) + `klow_web`(바이어 공개 페이지 `/seed/:token` claim/checkout) + `klow_admin`(배송비용·해외배송 비교요율 표 편집).
- **데이터 모델**: `SeedingClaim`(**신청 1건 = 1명 = 1주문 = 1송장** — `linkId`+`orderId @unique`, `state`(reserved/confirmed/released/cancelled)·`reservedUntil`·신청자별 `countryCode`/`selectedSkus`/`recipientInstagram`/`snsMemo`/`reviewCompleted`. 단일·다인원 링크가 **같은 모델**을 쓰며 브랜드 목록의 행 단위다), `SeedingLink`(발급 링크 — token·국가·무게·결제주체/선택모드 2×2 매트릭스·통관 스냅샷 + 고객 결제용 금액 `shippingFeeKrw`/`productPriceKrw`(물품가, 선택) + 발급 배치 라벨 `campaignName`(≤40자) + 브랜드 담당자 메모 `memo`(≤80자) + 수화인 입력 `recipientInstagram`·브랜드 메모 `recipientSnsMemo`(발송대기 "받을 사람 SNS 주소", ≤200자, 2026-07-02 `add_seeding_link_recipient_sns_memo`)·`reviewCompleted`(후기 제작 완료 토글, 2026-06-29 `seeding_instagram_review`)), `ManualSeedingRecord`(KLOW 이전 자체 시딩 수동 import 기록 — `data` JSON + `reviewCompleted`, brand scope), `SeedingServiceAgreement`(후청구 이용계약서, `brandUserId` 당 1행), `SeedingRate`(국가×무게 배송비 요율표, 모든 비용/마진 포함 — 시딩·일반주문 공용), `ShippingRate`(carrier=EMS|DHL **비교가** 티어 — rateKrw 가 곧 표시가), `Order`/`OrderItem`(시딩 주문, `isSeeding=true`).
- **시딩이란**: 브랜드가 크리에이터에게 보낼 무료/유료 샘플 발송 링크(`/seed/:token`)를 발급하면, 크리에이터(바이어)가 이메일·배송지를 입력해 **무료 claim** 하거나 **유료 checkout**(배송비 결제)으로 신청한다. **한 링크가 몇 명을 받는지는 `mode` 가 정한다** — `single` 은 1명(기존), `multi` 는 정원(`maxClaims`)까지 선착순으로 여러 명이 신청하고 신청자 수만큼 EFS 송장이 나간다. 신청 1건 = 1주문 = 1송장은 두 모드 모두 동일하다.
- **2×2 매트릭스**: 링크는 `paymentBy`(brand=후청구 무료 / customer=바이어가 배송비 + 선택 물품가 결제) × `selectionMode`(brand=브랜드 지정 / customer=후보 중 바이어 선택)로 분기한다. 선택 후보(`selectionSkus`)는 등록 product ID 가 아니라 **자유 텍스트 제품명 라벨**이라 소유 검증 없이 trim·중복제거만 하고, 바이어 선택은 claim/checkout 의 `validateSelection`(후보 멤버십·개수·`selectionLimit` 검증)으로 검증한다.
- **다인원 링크 (선착순, 2026-08)**: `SeedingLink.mode`(single|multi) + `maxClaims`(정원 2~500) + `closedAt`(브랜드 수동 마감/재개방). 발급 위저드의 **첫 질문**이 방식 선택이고, multi 를 고르면 "링크 몇 개" 대신 "최대 몇 명"을 묻고 **링크는 1개만** 만든다. `paymentBy`·`selectionMode` 두 축과 모두 조합 가능.
  - **정원 판정은 `SeedingClaim` 라이브 COUNT 하나뿐**이다(카운터 컬럼 없음). `reserveSlot()` 이 트랜잭션 첫 문장으로 `SELECT … FOR UPDATE` 로 링크 행을 잠그고(`brand-auth.lockBrandUser` 와 같은 이유 — read-committed 재확인만으로는 동시 요청 둘이 같은 스냅샷을 통과한다) 활성 신청 수를 센다. 점유 조건 = `confirmed` ∨ (`reserved` ∧ `reservedUntil > now`). 만료 예약은 **시계가 지나는 순간** 정원에서 빠지므로 보정 쓰기가 없고 드리프트가 불가능하다.
  - **락 구간은 3왕복까지만.** 동시 신청이 이 구간에서 직렬화되므로 문장 하나가 곧 N명의 대기시간이다. 잠금+읽기를 한 문장으로 합치고 만료 예약 청소(`sweepExpiredReservations`, 위생 목적)는 락 밖으로 뺐다. Prisma 기본 트랜잭션 타임아웃 5초로는 십수 명만 몰려도 500 이 나므로 `SEEDING_TX_OPTS`(timeout 20s / maxWait 15s)를 명시한다.
  - **고객 결제 예약(10분)**: checkout 진입이 `state=reserved` 로 자리를 선점한다. 정원이 작을 때 이탈 한 번이 링크를 얼려버리지 않도록 세 겹으로 막는다 — (1) **본인 예약 재사용**: 로그인 사용자는 `userId` 로, 게스트는 **`klow_order` 쿠키에서 복원한 주문 id**(`guestOrderIdFromToken`)로 자기 예약을 찾아 새 자리를 잡지 않고 그 주문을 갱신한다(안 그러면 한 사람이 두 번 시도해 정원 2를 혼자 소진한다). 쿠키가 이미 서명된 orderId 를 담고 있어 **클라이언트가 따로 보관·전송하지 않는다**, (2) **결제 실패·취소 시 즉시 반납**(`payment.reportFailure` → `released`), (3) TTL 10분. 만료 후 결제가 도착하면 **확정하고 경고 로그**를 남긴다 — 거절하면 결제한 고객이 아무것도 못 받기 때문이고, 그 대가로 드물게 정원을 1 초과할 수 있다(화면은 `3/2명` 처럼 정직하게 표시).
  - **취소는 자리를 돌려준다**: 송장 취소(`performEfsCancel`)는 그 **신청만** `cancelled` 로 바꾸고, 정원에서 빠져 한 자리가 다시 열린다(안 돌려주면 정원 10명 링크에서 9명만 받게 된다). single 링크는 기존 동작대로 링크까지 `cancelled`, multi 는 링크를 계속 열어둔다.
  - **`SeedingLink` 미러는 single 전용**이다(`mirrorLinkAfterClaim`) — multi 는 주문이 여러 개라 `orderId @unique` 에 담을 수 없고, 그래서 `status` 도 pending 에 머문다. "아직 받는가"의 답은 언제나 claim 라이브 카운트(`accepting`)이지 `status` 가 아니다. ⚠️ 어드민 통계의 "열린 링크 수"(`stats.service`)는 이 이유로 다인원 링크를 과대 계상하는 근사값이다.
  - **송장 화면은 `order.seedingClaim` 을 읽는다** — 다인원 주문은 구 1:1 관계(`order.seedingLink`)가 null 이라, 그것만 읽으면 라벨·상세 모달에서 선택 제품·인스타·캠페인명이 조용히 빈 값이 된다. klow_brand 는 `seedingOf(order)`(shipping.model.ts) 한 곳에서 claim 우선·링크 폴백으로 푼다.
  - **정원 판정은 `summarizeCapacity()` 하나**가 한다 — 바이어 페이지(`getByToken`)와 브랜드 목록(`toLinkDTO`)이 같은 함수를 호출하므로 "받는 중인가"가 두 화면에서 갈라질 수 없다. 브랜드 DTO 는 그 결과를 **`accepting`**(아직 신청받는가)·**`deletable`**(삭제 가능한가, `deleteLink` 규칙과 동일)로 내려주고 클라는 mode·정원·마감을 재조합하지 않는다.
  - **바이어 화면은 사유를 구분**한다 — `unavailableReason`: `claimed`(1인용 링크가 이미 사용됨) / `full`(다인원 정원 소진) / `reserved`(다른 사람이 결제 중, 곧 열릴 수 있음 + `retryAfter`) / `closed`(브랜드 수동 마감) / `cancelled`. ⚠️ `single`·`multi` 를 구분하지 않으면 1인용 링크 재방문자에게 "캠페인 정원이 찼습니다" 같은 다인원 문구가 나간다. 남은 자리는 **≤5 일 때만** 노출한다(100명 링크의 "97자리 남음"은 소음).
  - **쓰로틀**: 다인원은 통신사 NAT·같은 사무실 뒤에서 여러 사람이 신청하므로 claim/checkout 제한을 IP당 **20회/분**으로 완화했다(구 5회는 정상 신청자끼리 서로를 429 로 막는다).
  - 마이그레이션 `20260803081904_add_seeding_claims_multi`(CREATE TYPE ×2 + CREATE TABLE + ADD COLUMN ×3 — **전 과정 롤링 배포 안전**) + 백필 `npm run backfill:seeding-claims`(멱등, dry-run 기본. **배포 순서: migrate → 백필 → 코드 → 백필 재실행** — 마지막 재실행이 배포 창에서 구 코드로 신청된 링크를 주워 담는다). `SeedingLink` 의 `orderId`/`selectedSkus`/`recipientInstagram`/`reviewCompleted`/`claimedAt` 은 **dormant 미러**로 남고(single 만 이중쓰기) 읽기는 전부 claim 을 쓴다. ⚠️ **`countryCode` 는 claim 시 절대 쓰지 않는다** — 다인원에서 첫 신청자의 국가가 링크에 박히면 이후 신청자가 엉뚱한 나라로 발송된다(배송지 국가 정본은 `SeedingClaim.countryCode`).
- **국가 확정 시점 (2026-07)**: `SeedingLink.countryCode` 는 **nullable**(`add_seeding_link_country_optional`). **고객 결제**는 정액 배송비를 확정해야 하므로 발급 시점에 국가 필수(`CreateSeedingLinkInput` superRefine 이 `paymentBy='customer'` 면 `countryCode` 강제). **브랜드 결제**는 국가 없이 발급(`countryCode=null`, `feeKrw=0`)하고 **바이어가 claim 시 배송지 국가를 직접 고른다**. `getByToken` 은 국가 미정 링크에 `country:null` + `countryOptions`(=`supportedCountries`, 브랜드 발급 드롭다운과 동일 목록)를 실어 내리고, claim 은 `effectiveCountry = link.countryCode ?? dto.countryCode`(미정 링크만 후보 멤버십 검증)로 캐리어/EFS 필드/주문 국가를 해석하고 링크에 확정 저장한다. klow_brand 발급 패널은 결제방식을 첫 단계로 올려 고객 결제일 때만 국가→무게를 점진적으로 노출한다.
- **무료 claim** (`paymentBy='brand'`, `POST /v1/seeding/:token/claim`): 바이어 이메일·전화·배송지(+ 국가 미정 링크면 `countryCode`)를 입력하면 즉시 `Order`(`isSeeding=true`, `totalUsd=0`, `shippingFeeUsd=0`)를 생성하고 `paymentStatus=paid`/`status=processing`/`paidAt` 자동 세팅 → PG 안 거치고 바로 출고 대기 큐로 간다. 링크는 `claimed` 로 전이(동시 claim 은 트랜잭션 내 재확인으로 차단). 커밋 후 주문확인 메일(`/track/:id?t=서명토큰`) + EFS 송장 자동 발급을 best-effort 로 실행하되 **await 하지 않고 백그라운드(`Promise.allSettled`)로 보내** claim 응답을 막지 않는다(외부 Resend/EFS 지연 제거 → 확인 화면 즉시 표시; 실패 흡수 → 어드민 미발급 대기 폴백). 중국(`CN`) 배송은 수취인 신분증 번호(`recipientTaxId`) 필수.
- **유료 checkout** (`paymentBy='customer'`, `POST /v1/seeding/:token/checkout`): 무료 주문을 즉시 paid 로 만들지 않고 `paymentStatus=pending` 주문을 만든 뒤 기존 결제 플로우에 태운다. **청구액 = 배송비 + (선택)물품가** — `shippingFeeUsd` 에는 배송비만 남기고 `totalUsd = 배송비 + 물품가`(둘 다 링크의 KRW 값을 주문 시점 `fxRate` 로 USD 센트 환산)라 정산·EFS 리포트가 둘을 구분한다. 물품가가 있으면 `OrderItem.settlementPriceKrw` 에 **PG 5% 를 뺀 순정산가**(`settlementKrwFromCustomerUsd`, 일반 주문과 동일 기준)를 박아 브랜드 매출로 정산되고, 물품가가 없으면 0(배송비만 시딩). 비로그인이면 컨트롤러가 게스트 결제 쿠키(HMAC)를 내려주고, 클라가 `/v1/payment/prepare → Eximbay SDK → /v1/payment/verify` 로 그 금액(배송비 + 물품가)을 결제한다. **바이어는 결제 직전 국내/해외 카드를 고른다**(2026-08) — `/seed/:token` 요약 카드의 결제수단 블록이 일반·현장 체크아웃과 같은 `checkout.payment.*` 라벨을 쓰고, 국내카드면 `prepare` 에 `issuerCountry:'KR'` 을 실어 국내 전용 MID + KRW 로 결제창을 띄운다(해외 MID 는 acquirer 제약으로 한국 발급 카드를 `PC04` 로 막는다). 시딩 주문도 checkout 이 `fxRateSnapshot` 을 동결하므로 KRW 환산액이 prepare↔verify 간 흔들리지 않는다. 서버는 주문 종류를 가리지 않고 같은 경로를 탄다 — [payment](./payment.md) 참고. 로그인 상태면 주문을 그 사용자에 귀속(prepare 가 user-ownership 검증). 결제 성공(`markPaid`) 후에야 링크가 `claimed` 로 전이되고 송장·확인메일이 발급된다. PG 심사용 동의 3종(`termsAgreedAt`/`refundAgreedAt`/`pgDataSharingAgreedAt`) + IP 를 주문 생성 시 저장. 두 엔드포인트 모두 IP당 **20회/분** 쓰로틀로 enumeration·스팸 차단(컨트롤러 로컬 `THROTTLE_TIGHT` — 이름은 그대로지만 다인원 링크가 같은 NAT 뒤에서 신청되므로 5회/분에서 완화했다).
- **배송비 = SeedingRate 요율표**: 발급 시 `logisticsRate.resolveCost(iso2, weightG)` 가 국가×무게 표에서 **무게 올림** 조회한 `costKrw` 를 그대로 배송비로 쓴다 — 운영팀이 원가·캐리어·할증·마진을 미리 반영한 정본값이라 **런타임 비교·할증 가산·구 ₩1000 정액수수료 전부 없음**. **2026-07-29 부터 일반 주문도 같은 표를 쓴다**(일반 주문은 500g 티어가 곧 고객 배송비 — [shipping](./shipping.md)). 서비스는 `shipping/logistics-rate.service.ts` `LogisticsRateService`(ShippingModule 소유·export, 구 `seeding/seeding-rate.service.ts` `SeedingRateService`). 캐리어는 비교·선택하지 않고 `shipping.service.resolveCarrier(iso2, addr, weightG)` 가 무게 분기(`seedingCarrierSplitWeightG`, 있으면 무게≤분기값 EFS/초과 EMS) 또는 국가 고정 `productCarrier` 로 결정한다(EFS 제외구역이면 차단). 고객 결제 링크만 이 요율을 바이어에게 청구(`shippingFeeKrw`, 선택 물품가 `productPriceKrw` 는 별도 컬럼으로 저장해 checkout 이 합산 청구), 브랜드 결제 링크는 `shippingFeeKrw=null`(현재 미청구, `feeKrw=0`).
- **EMS/DHL 비교가 (shipping-rate.service)**: 발급 화면에서 "KLOW 시딩가 vs EMS vs DHL 직접발송" 비교를 보여주기 위한 별도 표(`ShippingRate`, carrier=EMS|DHL). **표시가 = `ShippingRate.rateKrw` 그대로** — 업로드 요율표가 EMS 특별운송수수료·DHL 유류할증료까지 이미 통합한 최종가라 재조합 없음(2026-07). 어드민 **해외배송 비교요율** 탭(`shipping/admin-shipping-rate.controller` — 파일은 shipping 모듈 소유, 2026-07 이동)에서 EMS/DHL 별 셀 편집·엑셀 업로드(셀 값을 그대로 저장). 구 컬럼 `ShippingCountry.emsSpecialFeePerKgKrw`·`ShopSettings.dhlFuelSurchargeRate` 는 **dormant**(계산 미사용, 컬럼·편집 UI 만 유지).
- **통관(customs) 스냅샷**: 시딩은 `Product` 가 없으므로 `OrderItem.productId=null` + 통관 스냅샷을 박는다. 통관 신고가(EFS field 26)는 0 이면 거부되므로 발급 시 링크별 **$8.50~$12.50 랜덤**(`declaredValueUsd`, USD 센트 850~1250)을 저장해 `OrderItem.unitPriceUsd` 로 사용(이 때문에 `totalUsd = Σ(unit×qty)` 불변식이 깨지지만 PG 청구가 없는 시딩 주문에 한한 의도된 예외). 통관 품명은 한글 brand.name 대신 영문 후보 중 링크별 랜덤(`itemName`)이고, 후보 목록이 **발급 시점 `Brand.category` 별로 갈린다** — 화장품 `Korean Skincare Serum/Toner/Cream`, 치과재료 `Dental Impression Material/Dental Modelling Paste/Dental Wax Preparation`. 후보는 HS 코드와 같은 행(`BRAND_CATEGORY_CUSTOMS[category].seedingItemNames`)에 묶여 있다 — 품명과 HS 가 어긋나면 통관에서 걸리기 때문. `itemName` 은 발급 시점에 동결되므로 브랜드가 나중에 품목을 바꿔도 기존 링크의 품명은 옛 값으로 남는다. HS/카테고리는 `null` 로 두고 **송장 빌더가 `Brand.category` 에서 파생**한다(→ [shipments](./shipments.md) 통관 항목) — 링크에 스냅샷하지 않으므로 품목 변경이 미발송 링크에 곧바로 반영된다.
- **고객 대면 제품명 = 읽기 시점 파생 (2026-08):** 위 `itemName` 이 `OrderItem.productName` 으로 박히는데, 이 컬럼은 **EFS 송장 24-5 영문 통관 상품명**이라(→ [shipments](./shipments.md)) 한글 자유 텍스트를 넣으면 통관이 거부된다 — **절대 바꾸지 않는다**. 대신 `selectionMode='customer'`(고객이 선택) 링크에 한해 **주문 확인 메일 · `/track` 배송추적에서만** `SeedingClaim.selectedSkus`(바이어가 실제 고른 제품명)로 표시 이름을 갈아끼운다. 단일 출처는 `seeding/seeding-display-name.ts` 의 `SEEDING_DISPLAY_CLAIM_SELECT` + `buyerSelectedNames()` + `displayLines()` 이고, 메일 경로(`orders/order-confirmation-email.ts` — `PaymentService`·`SeedingService` 두 발송부 공용)와 추적 경로(`orders.service.getTracking`)가 같은 함수를 거친다. 고른 제품 N개면 **표시 라인 N행으로 펼친다**(시딩 `OrderItem` 은 항상 1행이라 안전). `selectionMode='brand'` 는 고를 대상이 없으므로 랜덤 영문 통관명 그대로다. ⚠️ **시딩 주문은 메일에서 라인 금액을 숨긴다** — `unitPriceUsd` 가 통관 신고가라 실결제액(무료 claim $0 / 유료 checkout 배송비+물품가)과 무관하기 때문이고, 무료 시딩은 라인·총액 모두 `Free` 로 표기한다. 총액(`totalUsd`)은 그대로 정확하다. 회귀 가드: `seeding/__tests__/seeding-display-name.spec.ts`, `orders/__tests__/order-confirmation-email.spec.ts`.
- **이용계약서 서명**: 후청구(브랜드 결제) 시딩 이용계약서는 `BrandUser` 계정당 1회 동의 — 클라이언트 서명 캔버스 PNG data URL 을 디코드해 R2(`seeding-agreements/`, `brandUserId` scope)에 업로드하고 DB(`SeedingServiceAgreement`)엔 공개 URL 만 저장한다(data URL 을 행에 박지 않음). 재동의 시 `acceptedAt` 갱신. 브랜드 미연결 계정(`brandId=null`)도 서명 가능하므로 `requireBrandId` 가 아니라 `user.id` 로 스코프.
- **발급 가능국**: `logisticsRate.supportedCountries()` = 요율표 티어 보유 ∩ 캐리어 결정 가능(`productCarrier` 또는 `seedingCarrierSplitWeightG`) 국가. **배송지원 `enabled` 무관** — 그 게이트는 일반 주문 전용이다. 캐리어 없는 국가를 드롭다운에서 빼 "목록엔 뜨는데 발급 실패"를 막는다. 응답의 `isDirect`(고정 캐리어가 EFS 이거나 무게 분기국)는 **서버가 단일 판정한 직통 여부**라 클라가 캐리어 규칙을 재구현하지 않는다. 같은 목록을 바이어 페이지(`getByToken` 의 `countryOptions`)와 claim 의 국가 검증이 그대로 재사용한다.
- **초기 시드**: `npm run seed:seeding-rates`(`prisma/data/seeding_rates.json`, 엑셀 `KLOW_시딩_가격표` 고객_가격표 기준).
- **관련 파일**: `seeding.service.ts`(링크 발급·claim·checkout·정원 게이트 `reserveSlot`·계약서 서명·review/sns-memo/memo 토글·`closeLink`), `manual-seeding.service.ts`(KLOW 이전 수동 시딩기록 엑셀 추출·CRUD), `shipping/logistics-rate.service.ts`(요율표 조회·편집·엑셀 — shipping 모듈 소유·export, 2026-07-29 이동), `shipping/rate-sheet-ai.service.ts`(임의 포맷 요율표 AI 추출), `shipping/shipping-rate.service.ts`(EMS/DHL 비교가 — shipping 모듈 소유·export, 2026-07 이동), `shipping/xlsx-grid.ts`(캐리어 시트 파서), 컨트롤러 3개(brand·public·admin-seeding-rate) + shipping 모듈의 admin-shipping-rate.
- **교차링크**: [shipping](./shipping.md)(productCarrier·EFS 제외구역·resolveCarrier), [orders](./orders.md)(게스트 주문 토큰·동의), [payment](./payment.md)(유료 checkout prepare/verify), [shipments](./shipments.md)(EFS 송장 자동 발급).

## brand-seeding.controller.ts (`@Controller('v1/brand/seeding')`)

> 전체 라우트 `BrandGuard`. 발급·미리보기는 `requireBrandId`, 이용계약서(agreement)는 `brandId=null` 계정도 가능하도록 `user.id` 스코프.

| Method | Path                                        | 기능                                                              |
|--------|---------------------------------------------|-------------------------------------------------------------------|
| GET    | `/v1/brand/seeding/links`                   | 내 브랜드 시딩 링크 목록(cancelled 제외)                          |
| GET    | `/v1/brand/seeding/countries`               | 발급 가능국 목록(SeedingRate 티어 ∩ `productCarrier` 또는 무게 분기, + `isDirect`) |
| GET    | `/v1/brand/seeding/quote?weightG=`          | 적용무게(g, 1~50,000 아니면 400)에 대한 국가별 1개당 시딩 배송비(KRW) 맵 |
| GET    | `/v1/brand/seeding/comparison?weightG=`     | 국가별 KLOW vs EMS vs DHL 표시가 맵(같은 1~50,000 범위 검증)     |
| GET    | `/v1/brand/seeding/comparison-table?iso2=`  | 한 국가의 시딩 티어별 KLOW/EMS/DHL 비교 표(iso2 2자리 아니면 400) |
| POST   | `/v1/brand/seeding/links`                   | 시딩 링크 발급 — single 은 `count`(1~100) 개, multi 는 `maxClaims`(2~500) 정원 링크 1개 |
| DELETE | `/v1/brand/seeding/links/:id`               | 신청자 없는 링크 취소(soft, `cancelled`)                        |
| PATCH  | `/v1/brand/seeding/links/:id/close`         | 다인원 링크 수동 마감/재개방(`closed`) — 정원이 남아도 신청을 닫는다 |
| PATCH  | `/v1/brand/seeding/claims/:id/review`       | "후기 제작 완료" 토글 — **신청자 단위**(`reviewCompleted`)      |
| PATCH  | `/v1/brand/seeding/claims/:id/sns-memo`     | 신청자별 SNS 주소 메모 저장/삭제(`snsMemo` ≤200자, null=삭제)  |
| PATCH  | `/v1/brand/seeding/links/:id/sns-memo`      | 링크 단위 "이 링크를 누구에게 보낼지" 메모(발급/복사 탭 전용)   |
| PATCH  | `/v1/brand/seeding/links/:id/memo`          | 브랜드 담당자용 링크 메모 저장/삭제(`memo` ≤80자, null=삭제)     |
| GET    | `/v1/brand/seeding/agreement`               | 내 이용계약서 동의/서명 조회                                     |
| POST   | `/v1/brand/seeding/agreement`               | 이용계약서 동의·서명 저장(PNG → R2)                             |
| POST   | `/v1/brand/seeding/manual-records/extract`  | 수동 시딩기록 엑셀 업로드 → OpenAI 추출 → 후보 반환(미저장, `THROTTLE_TIGHT`) |
| GET    | `/v1/brand/seeding/manual-records`          | 내 브랜드 수동 시딩기록 목록                                     |
| POST   | `/v1/brand/seeding/manual-records`          | 추출 후보 중 선택분 일괄 적재                                    |
| PATCH  | `/v1/brand/seeding/manual-records/:id`      | 수동 기록 수정                                                   |
| PATCH  | `/v1/brand/seeding/manual-records/:id/review`| 수동 기록 "후기 제작 완료" 토글(`reviewCompleted`)             |
| DELETE | `/v1/brand/seeding/manual-records/:id`      | 수동 기록 1건 삭제                                              |

발급 입력(`CreateSeedingLinkInput`) 교차검증: `paymentBy='customer'` 면 `countryCode`·`estimatedWeightG` 필수, `selectionMode='customer'` 면 `selectionSkus` 1개 이상 + `selectionLimit` 이 1~후보 개수, **`mode='multi'` 면 `maxClaims` 필수 / `single` 이면 `maxClaims` 금지**(클라 버그를 조용히 무시하지 않고 400 으로 드러낸다). 브랜드 결제 링크는 `countryCode` 를 보내도 서버가 무시하고 `null` 로 저장한다. 링크 계열 mutation 은 전부 자기 브랜드 소유가 아니면 404 `링크를 찾을 수 없습니다`, claim 계열은 `claim.link.brandId` 로 소유를 검증해 404 `시딩 신청을 찾을 수 없습니다`. `DELETE links/:id` 는 **신청자가 한 명이라도 있으면 400** — 지우면 그 사람들의 발송이 목록에서 사라지므로 '지금 마감'으로 유도한다.

## public-seeding.controller.ts (`@Controller('v1/seeding')`)

> public. claim/checkout 은 `@Throttle`(IP당 **20회/분** — 다인원 링크는 같은 NAT 뒤 여러 사람이 신청한다). checkout 만 `OptionalUserGuard`(로그인 시 주문 귀속, 게스트면 결제 쿠키 발급).

| Method | Path                          | 기능                                                                 |
|--------|-------------------------------|----------------------------------------------------------------------|
| GET    | `/v1/seeding/:token`          | 링크 공개 정보(상태·`claimable`·`mode`/`maxClaims`/`remaining`/`unavailableReason`/`retryAfter`·국가 또는 `countryOptions`·2×2·선택후보 카드·`shippingFeeKrw/Usd`·`productPriceKrw/Usd`) |
| POST   | `/v1/seeding/:token/claim`    | 무료 claim — ₩0 주문 생성, paid 자동, 송장/메일 발급                |
| POST   | `/v1/seeding/:token/checkout` | 유료 checkout — pending 주문 생성, 게스트 쿠키, 이후 /v1/payment/*   |

에러: 없는 토큰 404, 정원 마감·수동 마감·취소된 링크 409, 결제주체가 맞지 않으면 400(고객 결제 링크에 claim / 브랜드 결제 링크에 checkout). 고객 선택 링크의 `selectedSkus` 는 후보 멤버십·중복·`selectionLimit` 위반 시 400. 표시용 USD(`shippingFeeUsd`/`productPriceUsd`)는 조회 시점 fxRate 환산이고, 결제 정본은 checkout 이 주문에 동결하는 `fxRateSnapshot` 이다.

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

- **AI 는 레이아웃만 판단하고 금액은 서버가 원본 셀에서 직접 읽는다.** 71~140행 금액을 LLM 이 옮겨 적으면 자릿수 환각이 나므로, AI 응답은 `{mode, sheetName, orientation, weightIndex, priceIndex, weightUnit, dataStart/EndIndex, currency, weight/priceHeader, notes}`(`RateSheetLayout`) 뿐이다. 저장되는 값은 항상 파일값과 일치한다. 유일한 예외가 `mode:'pairs'` — 격자로 표현이 안 되는 변칙 파일에서만 AI 가 `pairs[{weight,price}]`(≤1000쌍)를 직접 돌려주고, 그 외에는 항상 `'grid'`(스키마 `.catch('grid')`).
- 서비스는 `shipping/rate-sheet-ai.service.ts`(`RateSheetAiService`, ShippingModule 소유) — `inferLayout()`(OpenAI, `OPENAI_MODEL ?? gpt-4o-mini`, `temperature:0` + `json_object`, 시트당 앞 40행×30열·셀당 40자만 프롬프트에 실음) + `extract()`(**LLM 미경유 결정론적 파싱**) + 후보 열 수집. `LogisticsRateService.aiImportPreview()` 가 이를 호출하고 기존 `buildTierDiff` 로 diff 를 만든다. AI 가 없는 시트명을 지어내면 첫 시트로 보정하고, 인덱스를 `-1` 로 두고 헤더 이름만 맞춘 경우(`repairIndexes`)엔 후보 목록에서 이름으로 되찾는다. OpenAI 응답이 비었거나 스키마에 안 맞으면 502.
- 숫자 파싱은 **일부러 엄격하다**(`toNumber`) — 통화기호·콤마·kg/g/원 표기만 떼고 **나머지 전체가 숫자일 때만** 받는다("3지역" 같은 헤더에서 3kg 을 주워오는 사고 방지). `0.5~1` 같은 구간 표기는 **상한**을 쓴다(요율 무게는 "이 무게까지" 상한 티어). 같은 무게가 두 번 나오면 뒤 값이 이긴다.
- **열 오선택 복구**: 응답에 `candidates`(숫자 5개 이상 든 열/행 + 헤더)를 함께 실어, 어드민이 미리보기에서 무게/가격 열을 바꾸면 **같은 파일 + `layout` 을 재전송해 AI 없이 즉시 재추출**한다. 추출 0건이어도 400 을 던지지 않고 candidates 와 함께 돌려주는 이유가 이것 — 던지면 어드민이 바로잡을 화면 자체가 안 뜬다.
- **버리는 행은 노출한다**: `SeedingRateUpsert` 와 같은 상한(무게 1~50,000g / 0~10,000,000원)을 벗어난 행은 `skipped[]` 에 사유와 함께 담겨 경고 배너로 뜬다(예: 50kg 초과 티어). 통화가 KRW 가 아니면 400.
- **적용**은 AI 를 다시 타지 않는다 — 미리보기에서 확인한 티어를 그대로 `PUT :iso2/tiers` 로 되돌려 보낸다(`tiers` 1~300개, `mode` 기본 `replace`). `replace` 는 그 국가 티어 전체 교체(목록 업로드와 같은 의미), `merge` 는 들어온 무게만 지우고 다시 깔아 나머지 기존 티어를 보존한다. 전체 교체가 지울 기존 티어는 미리보기 `removed[]` 로 먼저 보여준다(표준 소형 티어 100g/250g/750g 이 조용히 사라지지 않도록). 없는 국가면 404, 응답은 `{saved, removed}`.

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
| POST   | `/admin/shipping-rates/:carrier/:iso2/import/ai-preview` | 임의 포맷 요율표 엑셀 → AI 추출 + diff (적용 안 함) |
| PUT    | `/admin/shipping-rates/:carrier/:iso2/tiers` | 한 캐리어·국가 티어 일괄 저장(`mode: replace \| merge`) |

**AI 요율표 추출 (국가 상세, 2026-08)** — 위 배송비용(`/admin/seeding-rates/:iso2/import/ai-preview`)과 **같은 기능·같은 엔진**(`RateSheetAiService`)을 비교요율에도 붙인 것이다. 동작 규칙(레이아웃만 AI·금액은 서버가 원본 셀에서 직접·엄격한 숫자 파싱·`candidates` 로 열 재선택 시 AI 재호출 없음·`skipped[]` 노출·KRW 아니면 400·적용은 AI 미경유)은 전부 동일하므로 위 절을 참고한다. 다른 점만:

- **캐리어 축이 하나 더 있다.** `(carrier, iso2)` 가 URL 파라미터이고 body 에는 없다(`ShippingRateBulkReplace` = `{tiers, mode}`). `ShippingRateService.aiImportPreview()` / `replaceTiers()` 가 담당하며, ⚠️ **조회·삭제 범위에 `carrier` 가 반드시 들어간다** — 빠지면 같은 국가의 반대 캐리어 요율이 통째로 지워진다(`__tests__/shipping-rate-ai-import.spec.ts` 가 이걸 잠근다).
- 금액 필드명이 다르다 — 추출기는 시딩과 공용이라 `costKrw` 로 돌려주므로 서비스가 `rateKrw` 로 옮긴다. 상·하한은 `ShippingRateUpsert` 와 동일(무게 1~50,000g / 0~10,000,000원).
- 목록 페이지의 `import/preview`·`import/apply`(고정 포맷 다국가 매트릭스)와 **병존**한다 — 그쪽은 `원본요율(할인전)`/`DHL수출요율(개인·물품)` 시트 전용이고, 이쪽은 캐리어가 보내온 국가 하나짜리 임의 포맷용이다.
- 어드민 UI 는 `/shipping-rates/[iso2]?carrier=EMS|DHL` 국가 상세이고, 미리보기 모달은 배송비용과 **같은 컴포넌트**(`klow_admin/src/components/AiRateImportModal.tsx`)를 쓴다 — 모달은 금액 필드를 읽지 않아(무게·개수·중립 `diff` 만) 두 도메인 DTO 를 그대로 받는다.
