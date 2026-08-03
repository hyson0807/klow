# shipments — EFS 송장 발급/추적

- **모듈 경로**: `src/modules/shipments/`
- **주 클라이언트**: 어드민 송장 탭(`klow_admin`, `/admin/shipments/*`) + 브랜드 스튜디오 발송 화면(`klow_brand`, `/v1/brand/shipments/*`).
- **데이터 모델**: `Shipment`(1 브랜드 송장 = 1 박스, `status`/`carrier`/`efsServiceType`/`efsTrackingNumber`/`requestPayload`/`responseRaw`/추적 캐시 `latestStatusCode`/`latestStatusName`/`latestStatusAt`/`trackingCarrier`/`trackingEvents`/`trackedAt` + `submittedAt`/`cancelledAt`/`brandConfirmedShippedAt`/`createdById`), `ShipmentItem`(`orderItemId` @unique 로 OrderItem 1:1 연결 — 동시 발급 race 방지), `ShipmentStatus` enum.
- **한 브랜드 = 한 EFS 송장 = 한 박스**: 한 주문이 N 개 브랜드 제품을 담으면 송장도 N 장 발급된다 — `Shipment` 1개 + `ShipmentItem` N개(그 브랜드의 OrderItem 라인들). 각 브랜드가 자기 박스만 EFS 창고로 발송하기 위함. 제품 라인은 `Product.brandId`, 제품 없는(직접 입력) 시딩 라인은 `OrderItem.brandId` 스냅샷으로 브랜드 그룹핑한다(`groupByBrand`).
- **발급 단위 = (orderId, brandId) 그룹**: 단일 그룹 발급은 `createForBrand`(어드민 `POST /admin/shipments/order/:orderId/brand/:brandId`), 주문 전체 미발급 그룹 일괄 발급은 `createForOrder`(`POST /admin/shipments`). `createForOrder`/`createForBrand` 는 `adminId=null` 로도 호출 가능(결제/시딩 완료 시 시스템 자동 발급, `createdById=null`).
- **송장 상태 전이 (`ShipmentStatus`)**: `pending`(row 생성 + EFS 호출 전) → EFS 회신 성공이면 `submitted`(+`efsTrackingNumber`/`localCarrierName`/`localTrackingNumber`/`submittedAt`), 회신 N 또는 네트워크 throw 면 `failed`(+`errorMessage`). 취소는 **실제 EFS 취소**다 — `markCancelled`(어드민) / `cancelForBrand`(브랜드, 소유권 확인 후) 모두 `performEfsCancel` 로 EFS `changeShipment` 에 `{송장번호}|Cancel` 을 보내고, 성공해야 `cancelled`(+`cancelledAt`)로 마킹한다(이미 `cancelled` 면 멱등 반환). 취소 가능 대상은 `submitted` + EFS 송장번호가 있는 송장뿐이고(아니면 400), EFS 가 거부하면(예: 픽업 후) **DB 를 건드리지 않고 502** 로 사유를 그대로 올린다. 취소 후처리는 주문 종류로 갈린다 — **시딩 주문이면 완전 취소**(`Order.status='cancelled'` + `SeedingLink.status='cancelled'` 한 트랜잭션 → 재사용 불가), 일반 주문이면 `maybeRevertOrderFromShipped` 로 `processing` 복귀(재발급 가능). `failed`/`cancelled` 는 **재발급 가능 상태**(`isReissuableStatus`) — 같은 row 를 `pending` 으로 리셋해 재발급(`retry` → `createForBrand`). `submitted`/`pending` 은 재발급 거부(`ConflictException`). **수화인 수정 재발급**: 이미 `submitted` 된 송장은 수화인(주소)을 고쳐도 EFS `ChangeCnee` 가 US City,State 를 못 담으므로, 어드민이 `PATCH /admin/orders/:id/recipient` 로 수화인을 고친 뒤 `cancelAndReissue`(`POST /admin/shipments/:id/cancel-reissue`)로 **취소+즉시 재발급**해 새 송장번호를 받는다(EFS 픽업 후면 502).
- **EFS 연동 (`efs.client.ts`)**: `EFS_API_BASE`(기본 `http://www.efs.asia:200/api/in/`) 로 form-encoded(`apikey`/`req_function`/`send_data`) POST, 15s 타임아웃. 호출은 네 가지 — `newCreateShipment`(발급) · `changeShipment`(취소, `{송장번호}|Cancel`) · `getTrackStatusALL`(추적 이벤트 타임라인) · `getTrackStatus`(단수/배치 — 라스트마일 배송번호·실측무게·EFS 배송비 `chargeKrw` 를 주는 유일한 호출, efs-billing 이 재사용). `EFS_API_KEY` 가 비어 있으면 **dev mock** — 가짜 송장번호 `XXX...` 발급 + 합성 추적 이벤트(01/03/11) 반환. 응답 봉투는 단일행(문서/mock) / 둘째 줄 데이터(실서버 QT) 두 포맷 모두 파싱(`parseEfsEnvelope`), ack 실패만 `BadGatewayException`. 발급 성공 판정은 데이터필드 `Y`. `EFS_DELIVERED_CODE='33'`(배송완료)은 이 모듈이 정본으로 소유.
- **payload 빌드 (`payload-builder.ts`)**: `buildPayload` 가 33 필드를 `|` join 한 `sendData` 를 만든다. 핵심:
  - **24번 itemCapsule (multi-item)**: 그룹 라인 수만큼 `{"...",...},{"...",...}` 콤마로 이어붙인 블록(라인별 쇼핑몰명 KLOW/주문번호/상품번호/영문 상품명/통관 카테고리/HS code/수량/USD 단가/상품 URL). `,`/`|`/`{}`/`"` 충돌은 sanitize.
  - **27번 배송비 = 브랜드별 스냅샷 안분**: `perBrandShareUsd(order, brandId, brandCount)` 가 주문 시점 스냅샷 `Order.shippingFeeByBrand[brandId]` 를 읽는다 — 무료배송 브랜드는 0. 스냅샷이 없는 legacy 주문(2026-07-28 이전)만 `shippingFeeUsd/brandCount` 균등분배로 폴백한다. 한 주문의 모든 송장 share 합 = 총배송비. (배송비 정본·절반 분할 규칙은 [shipping](./shipping.md) 모듈.)
  - **2번 발송품 참조번호(20자)**: EFS 가 취소된 송장의 참조번호 재사용을 거부하므로(QT 확인), 발급마다 service 가 유일 토큰(`Date.now().toString(36)`)을 주입해 `order.id 끝7 + brand.id 끝4 + 토큰` 으로 만든다. 토큰이 없는 preview/test 경로만 `(orderId, brandId)` prefix 로 derive(EFS 미전송이라 무방).
  - **수화인 필드**: 23번은 `buildCityState` 로 "city state"(US 주 결합, 100자 캡), 15/16번 영문 수화인명·주소1 은 **PREMIUM JP 전용**(그 외 주문은 null → 빈값), 20/21번엔 같은 `order.phone` 을 넣는다.
  - **통관**: 26번 수출입 신고가 = 라인 `unitPriceUsd` 합(무가 시딩 주문 대비 `order.totalUsd` 아님). **24-6 영문 통관 분류 / 24-8 HS 코드는 송화인 브랜드의 취급 품목(`Brand.category`)에서 파생한다**(미선택 `null` 이면 화장품으로 신고 + warning — 발급을 막지는 않는다) — `common/constants.ts` 의 `BRAND_CATEGORY_CUSTOMS` 가 단일 출처이고(화장품 `Cosmetics`/`3304991000`, 치과재료 `Dental Materials`/`3407002000`), 한 송장 = 한 브랜드라 그 송장의 모든 캡슐이 같은 값을 갖는다. 24-7 옵션은 항상 빈 값. ⚠️ `Product.hsCode`/`customsCategoryEn`·`OrderItem`/`SeedingLink` 통관 스냅샷 컬럼은 **dormant** — 빌더가 읽지 않으므로 제품별 오버라이드는 존재하지 않는다(품목을 바꾸려면 브랜드 취급 품목을 바꾼다). 31번 세금식별코드 = 중국 배송 시 수취인 신분증(`recipientTaxId`). 송화인은 브랜드 `senderName`/`senderAddress`/`senderPostalCode`/`senderPhone`(미입력 시 발급 차단), 출고국/공항은 KR/ICN 고정. 25번 상품 무게는 EFS 입고 시 재측정하므로 비워 보낸다.
  - **캐리어 → EFS 서비스 타입**: EFS→`Premium` / EMS→`EMS` / DHL→`DHL`. 캐리어는 주문 시점 스냅샷 `Order.shippingCarrierByBrand[brandId]` 우선, 없으면 대표 `Order.shippingCarrier` 폴백(`carrierForBrand`).
- **Order.status 연동**: 송장 발급 성공/취소가 주문 상태를 구동한다. 발급 후 `maybeMarkOrderShipped` — 주문의 **모든** OrderItem 이 `submitted` Shipment 에 묶이면 `Order.status='shipped'`(이미 shipped/completed/cancelled 면 멱등). 송장 취소 후 `maybeRevertOrderFromShipped` — `shipped` 였는데 더 이상 전부 submitted 가 아니면 `processing` 으로 되돌려 재발급 가능하게 한다. 발급은 `paymentStatus=paid` + 비-cancelled + `shippingCarrier` 존재일 때만(`assertOrderCanShip`).
- **추적 갱신**: `refreshTracking`(단건) 은 `submitted` + `efsTrackingNumber` 있는 송장만 EFS `getTrackStatusALL` 폴링 → 이벤트를 timestamp 오름차순 정렬해 `trackingEvents` 캐시 + 최신 이벤트로 `latestStatus*` 갱신. **자동 발송처리**: 브랜드가 버튼을 안 눌러도 예약('01', `PRE_PICKUP_TRACKING_CODES`)이 아닌 첫 실제 픽업 이벤트가 잡히면 `brandConfirmedShippedAt` 을 그 이벤트 시각으로 찍어 발송대기 → 배송중으로 넘긴다(이미 수동 확인된 건은 덮지 않음). 외부 API 비용 보호로 마지막 폴링 후 **30초** 미만이면 거부(`TRACKING_REFRESH_MIN_INTERVAL_MS`). `refreshTrackingBulk` 는 5건씩(`BULK_TRACKING_CONCURRENCY`) chunk 직렬화하며 결과를 `ok`/`skipped`(30s throttle·미존재·검증 실패) / `failed`(외부·DB 에러)로 분리. **라스트마일 배송번호 backfill**: `localTrackingNumber` 가 비어 있으면(발급 응답엔 보통 미배정) `getTrackStatus`(단수) 를 함께 조회해 `localTrackingNumber`(+비어 있으면 `localCarrierName`) 를 채운다 — `getTrackStatusALL` 회신엔 이 값이 없기 때문. efs-billing 월 리포트 조회도 같은 값을 opportunistic backfill. 두 경로 모두 컬럼 폭(`VarChar(40)`)을 넘는 회신은 버린다(`LOCAL_TRACKING_MAX_LEN`, shipments.service 소유 — efs-billing 이 import). ⚠️ **2026-07-30 이전엔 이 캡이 20 이라 22자 USPS 번호가 통째로 버려져** 라스트마일 번호가 비어 있었다(마이그레이션 `20260730014355_widen_local_tracking_number` 로 `VarChar(20)→(40)` 확장. 순수 확장이라 롤링 배포 안전 / 배포 전 발급된 누락분은 추적 "지금 갱신"으로 자동 backfill).
- **라스트마일 캐리어 판별 = 번호 포맷** (`klow_admin`·`klow_brand` `src/lib/tracking-url.ts`, 두 파일 동일 내용): EFS 는 미국 건의 로컬 배송사를 **GOFO·USPS 구분 없이 전부 `localCarrierName='USCOS'`** 로 회신하므로, 추적 링크는 캐리어명이 아니라 **송장번호 패턴**으로 갈라야 한다 — `^\d{20,}` = **USPS** IMpb(`9261…` 22자) → `tools.usps.com/tracking/{num}`, `^GFUS` = **GOFO**(18자) → `gofo.com/us/track?searchID=`, `^SPA` 또는 목적국 SG = **SingPost**(15자) → `singpost.com/track-items?tracknumber=`. EFS 외 캐리어는 우체국 EMS 조회.
- **추적 자동 갱신 cron (`tracking-refresh.cron.ts`)**: KST 0/6/12/18시(`0 0,6,12,18 * * *`, Asia/Seoul)에 `refreshTrackingDue` 호출 — `submitted` + `efsTrackingNumber` 존재 + 비-terminal 코드(종료 코드 `TERMINAL_TRACKING_CODES = ['33','47','74','42']` 제외)인 송장을 오래 미갱신순으로 일괄 폴링(내부적으로 `refreshTrackingBulk` 재사용). `TRACKING_CRON_ENABLED=false` 일 때만 비활성(미설정 기본 on). 어드민 수동 일괄 갱신 버튼과 별개로 도는 보강 경로.
- **dev-set-tracking (게이트)**: `POST /admin/shipments/:id/dev-set-tracking` 은 EFS 폴링 없이 추적 상태를 수동 주입(local/staging 배송 상태별 동작 테스트용). `devSetTrackingStatus` 가 `ALLOW_DEV_TRACKING_OVERRIDE=true` 를 **service 단에서 재확인**하므로 운영에선 `403`(`ForbiddenException`). 선택 코드로 합성 이벤트를 타임라인 끝에 append + latest 갱신.
- **브랜드 발송 확인**: 어드민이 EFS 송장을 발급(`submitted`)하면 브랜드 스튜디오 "발송 대기"(`listPendingForBrand`: submitted + `brandConfirmedShippedAt=null`)에 뜨고, 브랜드가 `confirmShippedForBrand`(`POST /v1/brand/shipments/:id/confirm-shipped`)로 패킹 확인하면 `brandConfirmedShippedAt` 기록 → "배송 현황"(`listConfirmedForBrand`)으로 이동. 되돌리기(`unconfirmShippedForBrand`, `POST /:id/unconfirm-shipped`)는 **아직 픽업 전인 송장만** — `latestStatusCode` 가 null 이거나 `'01'`(배송예약)일 때만 허용하고 그 외엔 400. 브랜드도 자기 송장을 직접 취소할 수 있다(`POST /:id/cancel` → 위 `performEfsCancel` 과 동일 경로 = 시딩이면 주문·링크까지 완전 취소). 두 목록 모두 기본 무제한(take 미지정 — 100 캡이면 프론트 탭 분류가 어긋난다). 브랜드 라우트는 자기 `brandId` 송장만 접근(아니면 404).
- **시딩 중복 수령 경고 (`seedingDuplicates`)**: `listPendingForBrand` 응답의 시딩 건에는 "같은 사람이 전에도 받았는지" 매칭 결과가 붙는다. 비교 대상은 **이 브랜드의 발급된(submitted) 모든 시딩 송장 ∪ 수기 적재한 과거 기록(`ManualSeedingRecord`)** 두 출처라 KLOW↔수동 cross-check 가 된다. 수취인 정규화(이름/주소 소문자·공백압축, 우편번호 공백제거, 전화 숫자 끝 10자리)로 비교하되 **동일인 판정은 주소 또는 연락처 일치**만 인정하고(이름·우편번호 단독은 오탐이 커서 강조 표시용), 결과에 `source`(`klow`|`manual`)·`matchedFields` 를 실어 준다.
- **배송비 share (EFS 27번)**: 이 송장이 부담할 고객 선결제 배송비는 `orders/chargeable-brands.ts` 의 `perBrandShareUsd`(스냅샷 `Order.shippingFeeByBrand`, legacy 는 균등분배)로 정한다. **[efs-billing](./efs-billing.md) 의 브랜드 후청구가 같은 함수로 차감액을 구하므로** 둘이 어긋나면 송장과 청구서의 배송비가 달라진다 — 바꿀 땐 양쪽을 함께 본다.
- **관련 파일**: `shipments.service.ts`(발급/재발급/취소/추적/상태전이 본체), `efs.client.ts`(EFS HTTP + 응답 파싱), `payload-builder.ts`(33필드 sendData 빌드), `tracking-refresh.cron.ts`(추적 폴링 cron), `shipment-include.ts`(`SHIPMENT_INCLUDE`/`SHIPMENT_LIST_OMIT`), `shipments.types.ts`, 2 개 컨트롤러.
- **교차링크**: [efs-billing](./efs-billing.md)(EFS 실비 확정 → 브랜드 후청구), [settlement](./settlement.md)(delivered 송장 매출 정산), [seeding](./seeding.md)(시딩 claim 자동 발급).

## admin-shipments.controller.ts (`@Controller('admin/shipments')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                                                  | 기능                                                              |
|--------|-------------------------------------------------------|-------------------------------------------------------------------|
| GET    | `/admin/shipments`                                    | 송장 목록 (status/carrier/country/tracked/search/sort 필터)       |
| GET    | `/admin/shipments/count`                              | 같은 필터의 총 건수 (페이지네이션용)                              |
| GET    | `/admin/shipments/pending-groups`                     | 결제완료 + 미발급/실패 (orderId, brandId) 그룹 대기 목록          |
| GET    | `/admin/shipments/:id`                                | 단일 송장 상세 (추적 타임라인 포함)                              |
| POST   | `/admin/shipments/preview`                            | 발급 dry-run — 브랜드 그룹별 sendData/warnings 미리보기           |
| POST   | `/admin/shipments`                                    | 주문의 모든 미발급 브랜드 그룹 일괄 발급                          |
| POST   | `/admin/shipments/order/:orderId/brand/:brandId`      | 단일 (orderId, brandId) 그룹 발급                                |
| POST   | `/admin/shipments/:id/retry`                          | failed/cancelled 송장 그룹 재발급                                |
| POST   | `/admin/shipments/:id/cancel`                         | EFS 송장 실제 취소(changeShipment Cancel) → cancelled (일반주문은 shipped→processing 복귀, 시딩은 주문·링크까지 완전 취소, EFS 거부 시 502) |
| POST   | `/admin/shipments/:id/cancel-reissue`                 | EFS 송장 취소 + 같은 그룹 즉시 재발급(수화인 수정 반영, 새 송장번호) |
| POST   | `/admin/shipments/:id/refresh-tracking`               | 단건 EFS 추적 갱신 (30s throttle)                                |
| POST   | `/admin/shipments/:id/dev-set-tracking`               | [DEV] 추적 상태 수동 주입 (`ALLOW_DEV_TRACKING_OVERRIDE` 게이트)  |
| POST   | `/admin/shipments/refresh-tracking`                   | 여러 송장 EFS 추적 일괄 갱신 (ok/skipped/failed 분리)            |

## brand-shipments.controller.ts (`@Controller('v1/brand/shipments')`)

> 전체 라우트 `BrandGuard` — 자기 `brandId` 송장만 접근.

| Method | Path                                      | 기능                                                   |
|--------|-------------------------------------------|--------------------------------------------------------|
| GET    | `/v1/brand/shipments/pending`             | 발송 대기 (submitted + 미확인) + 시딩 `seedingDuplicates` |
| GET    | `/v1/brand/shipments/confirmed`           | 배송 현황 (패킹 확인 완료)                             |
| GET    | `/v1/brand/shipments/:id`                 | 단일 송장 상세 (추적 타임라인 포함)                    |
| POST   | `/v1/brand/shipments/:id/confirm-shipped` | 패킹/발송 확인 (`brandConfirmedShippedAt` 기록)         |
| POST   | `/v1/brand/shipments/:id/unconfirm-shipped` | 발송 처리 되돌리기 (배송예약 `01`/추적 전만, 그 외 400) |
| POST   | `/v1/brand/shipments/:id/cancel`          | EFS 송장 실제 취소 (시딩은 주문·링크까지 완전 취소)     |

## 관련 모듈

- [orders](./orders.md) — 송장 발급의 입력(OrderItem/캐리어 스냅샷/배송비)이자 발급/취소가 구동하는 `Order.status`.
- [shipping](./shipping.md) — 캐리어 산출(`resolveCarrier`)·국가별 고정 배송비 정본(송장 27번 share 의 원천).
- [seeding](./seeding.md) — 크리에이터 시딩 주문도 같은 송장 경로(제품 없는 라인은 `OrderItem.brandId` 스냅샷으로 그룹핑)를 탄다.
