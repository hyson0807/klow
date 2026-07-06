# shipments — EFS 송장 발급/추적

- **모듈 경로**: `src/modules/shipments/`
- **주 클라이언트**: 어드민 송장 탭(`klow_admin`, `/admin/shipments/*`) + 브랜드 스튜디오 발송 화면(`klow_brand`, `/v1/brand/shipments/*`).
- **데이터 모델**: `Shipment`(1 브랜드 송장 = 1 박스, `status`/`carrier`/`efsServiceType`/`efsTrackingNumber`/`requestPayload`/`responseRaw`/추적 캐시 `latestStatusCode`/`latestStatusName`/`latestStatusAt`/`trackingCarrier`/`trackingEvents`/`trackedAt` + `submittedAt`/`cancelledAt`/`brandConfirmedShippedAt`/`createdById`), `ShipmentItem`(`orderItemId` @unique 로 OrderItem 1:1 연결 — 동시 발급 race 방지), `ShipmentStatus` enum.
- **한 브랜드 = 한 EFS 송장 = 한 박스**: 한 주문이 N 개 브랜드 제품을 담으면 송장도 N 장 발급된다 — `Shipment` 1개 + `ShipmentItem` N개(그 브랜드의 OrderItem 라인들). 각 브랜드가 자기 박스만 EFS 창고로 발송하기 위함. 제품 라인은 `Product.brandId`, 제품 없는(직접 입력) 시딩 라인은 `OrderItem.brandId` 스냅샷으로 브랜드 그룹핑한다(`groupByBrand`).
- **발급 단위 = (orderId, brandId) 그룹**: 단일 그룹 발급은 `createForBrand`(어드민 `POST /admin/shipments/order/:orderId/brand/:brandId`), 주문 전체 미발급 그룹 일괄 발급은 `createForOrder`(`POST /admin/shipments`). `createForOrder`/`createForBrand` 는 `adminId=null` 로도 호출 가능(결제/시딩 완료 시 시스템 자동 발급, `createdById=null`).
- **송장 상태 전이 (`ShipmentStatus`)**: `pending`(row 생성 + EFS 호출 전) → EFS 회신 성공이면 `submitted`(+`efsTrackingNumber`/`localCarrierName`/`localTrackingNumber`/`submittedAt`), 회신 N 또는 네트워크 throw 면 `failed`(+`errorMessage`). 어드민이 EFS 관리자페이지에서 취소한 송장은 `markCancelled` 로 `cancelled`(+`cancelledAt`, 멱등). `failed`/`cancelled` 는 **재발급 가능 상태**(`isReissuableStatus`) — 같은 row 를 `pending` 으로 리셋해 재발급(`retry` → `createForBrand`). `submitted`/`pending` 은 재발급 거부(`ConflictException`). **수화인 수정 재발급**: 이미 `submitted` 된 송장은 수화인(주소)을 고쳐도 EFS `ChangeCnee` 가 US City,State 를 못 담으므로, 어드민이 `PATCH /admin/orders/:id/recipient` 로 수화인을 고친 뒤 `cancelAndReissue`(`POST /admin/shipments/:id/cancel-reissue`)로 **취소+즉시 재발급**해 새 송장번호를 받는다(EFS 픽업 후면 502).
- **EFS 연동 (`efs.client.ts`)**: `EFS_API_BASE`(기본 `http://www.efs.asia:200/api/in/`) 로 form-encoded(`apikey`/`req_function`/`send_data`) POST, 15s 타임아웃. `newCreateShipment`(발급) + `getTrackStatusALL`(추적) 두 호출. `EFS_API_KEY` 가 비어 있으면 **dev mock** — 가짜 송장번호 `XXX...` 발급 + 합성 추적 이벤트(01/03/11) 반환. 응답 봉투는 단일행(문서/mock) / 둘째 줄 데이터(실서버 QT) 두 포맷 모두 파싱(`parseEfsEnvelope`), ack 실패만 `BadGatewayException`. 발급 성공 판정은 데이터필드 `Y`. `EFS_DELIVERED_CODE='33'`(배송완료)은 이 모듈이 정본으로 소유.
- **payload 빌드 (`payload-builder.ts`)**: `buildPayload` 가 33 필드를 `|` join 한 `sendData` 를 만든다. 핵심:
  - **24번 itemCapsule (multi-item)**: 그룹 라인 수만큼 `{"...",...},{"...",...}` 콤마로 이어붙인 블록(라인별 쇼핑몰명 KLOW/주문번호/상품번호/영문 상품명/통관 카테고리/HS code/수량/USD 단가/상품 URL). `,`/`|`/`{}`/`"` 충돌은 sanitize.
  - **27번 배송비 = 송장별 균등 안분**: `perBrandShareUsd = order.shippingFeeUsd(센트)/100 / brandCount` — 한 주문의 모든 송장 share 합 = 총배송비. (배송비 정본·절반 분할 규칙은 [shipping](./shipping.md) 모듈.)
  - **통관**: 26번 수출입 신고가 = 라인 `unitPriceUsd` 합(무가 시딩 주문 대비 `order.totalUsd` 아님). HS code/영문 카테고리 미입력 시 fallback(`3304991000`/`Cosmetics`) + warning. 31번 세금식별코드 = 중국 배송 시 수취인 신분증(`recipientTaxId`). 송화인은 브랜드 `senderName`/`senderAddress`/`senderPostalCode`/`senderPhone`(미입력 시 발급 차단), 출고국/공항은 KR/ICN 고정. 25번 상품 무게는 EFS 입고 시 재측정하므로 비워 보낸다.
  - **캐리어 → EFS 서비스 타입**: EFS→`Premium` / EMS→`EMS` / DHL→`DHL`. 캐리어는 주문 시점 스냅샷 `Order.shippingCarrierByBrand[brandId]` 우선, 없으면 대표 `Order.shippingCarrier` 폴백(`carrierForBrand`).
- **Order.status 연동**: 송장 발급 성공/취소가 주문 상태를 구동한다. 발급 후 `maybeMarkOrderShipped` — 주문의 **모든** OrderItem 이 `submitted` Shipment 에 묶이면 `Order.status='shipped'`(이미 shipped/completed/cancelled 면 멱등). 송장 취소 후 `maybeRevertOrderFromShipped` — `shipped` 였는데 더 이상 전부 submitted 가 아니면 `processing` 으로 되돌려 재발급 가능하게 한다. 발급은 `paymentStatus=paid` + 비-cancelled + `shippingCarrier` 존재일 때만(`assertOrderCanShip`).
- **추적 갱신**: `refreshTracking`(단건) 은 `submitted` + `efsTrackingNumber` 있는 송장만 EFS `getTrackStatusALL` 폴링 → 이벤트를 timestamp 오름차순 정렬해 `trackingEvents` 캐시 + 최신 이벤트로 `latestStatus*` 갱신. 외부 API 비용 보호로 마지막 폴링 후 **30초** 미만이면 거부(`TRACKING_REFRESH_MIN_INTERVAL_MS`). `refreshTrackingBulk` 는 5건씩(`BULK_TRACKING_CONCURRENCY`) chunk 직렬화하며 결과를 `ok`/`skipped`(30s throttle·미존재·검증 실패) / `failed`(외부·DB 에러)로 분리. **라스트마일 배송번호 backfill**: `localTrackingNumber` 가 비어 있으면(발급 응답엔 보통 미배정) `getTrackStatus`(단수) 를 함께 조회해 `localTrackingNumber`(+비어 있으면 `localCarrierName`) 를 채운다 — `getTrackStatusALL` 회신엔 이 값이 없기 때문. efs-billing 월 리포트 조회도 같은 값을 opportunistic backfill.
- **추적 자동 갱신 cron (`tracking-refresh.cron.ts`)**: KST 0/6/12/18시(`0 0,6,12,18 * * *`, Asia/Seoul)에 `refreshTrackingDue` 호출 — `submitted` + `efsTrackingNumber` 존재 + 비-terminal 코드(종료 코드 `TERMINAL_TRACKING_CODES = ['33','47','74','42']` 제외)인 송장을 오래 미갱신순으로 일괄 폴링(내부적으로 `refreshTrackingBulk` 재사용). `TRACKING_CRON_ENABLED=false` 일 때만 비활성(미설정 기본 on). 어드민 수동 일괄 갱신 버튼과 별개로 도는 보강 경로.
- **dev-set-tracking (게이트)**: `POST /admin/shipments/:id/dev-set-tracking` 은 EFS 폴링 없이 추적 상태를 수동 주입(local/staging 배송 상태별 동작 테스트용). `devSetTrackingStatus` 가 `ALLOW_DEV_TRACKING_OVERRIDE=true` 를 **service 단에서 재확인**하므로 운영에선 `403`(`ForbiddenException`). 선택 코드로 합성 이벤트를 타임라인 끝에 append + latest 갱신.
- **브랜드 발송 확인**: 어드민이 EFS 송장을 발급(`submitted`)하면 브랜드 스튜디오 "발송 대기"(`listPendingForBrand`: submitted + `brandConfirmedShippedAt=null`)에 뜨고, 브랜드가 `confirmShippedForBrand`(`POST /v1/brand/shipments/:id/confirm-shipped`)로 패킹 확인하면 `brandConfirmedShippedAt` 기록 → "배송 현황"(`listConfirmedForBrand`)으로 이동. 브랜드 라우트는 자기 `brandId` 송장만 접근(아니면 404).
- **관련 파일**: `shipments.service.ts`(발급/재발급/취소/추적/상태전이 본체), `efs.client.ts`(EFS HTTP + 응답 파싱), `payload-builder.ts`(33필드 sendData 빌드), `tracking-refresh.cron.ts`(추적 폴링 cron), `shipment-include.ts`(`SHIPMENT_INCLUDE`/`SHIPMENT_LIST_OMIT`), `shipments.types.ts`, 2 개 컨트롤러.

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
| POST   | `/admin/shipments/:id/cancel`                         | EFS 취소 동기화 → cancelled (주문 shipped→processing 복귀)        |
| POST   | `/admin/shipments/:id/cancel-reissue`                 | EFS 송장 취소 + 같은 그룹 즉시 재발급(수화인 수정 반영, 새 송장번호) |
| POST   | `/admin/shipments/:id/refresh-tracking`               | 단건 EFS 추적 갱신 (30s throttle)                                |
| POST   | `/admin/shipments/:id/dev-set-tracking`               | [DEV] 추적 상태 수동 주입 (`ALLOW_DEV_TRACKING_OVERRIDE` 게이트)  |
| POST   | `/admin/shipments/refresh-tracking`                   | 여러 송장 EFS 추적 일괄 갱신 (ok/skipped/failed 분리)            |

## brand-shipments.controller.ts (`@Controller('v1/brand/shipments')`)

> 전체 라우트 `BrandGuard` — 자기 `brandId` 송장만 접근.

| Method | Path                                      | 기능                                                   |
|--------|-------------------------------------------|--------------------------------------------------------|
| GET    | `/v1/brand/shipments/pending`             | 발송 대기 (submitted + 미확인)                         |
| GET    | `/v1/brand/shipments/confirmed`           | 배송 현황 (패킹 확인 완료)                             |
| GET    | `/v1/brand/shipments/:id`                 | 단일 송장 상세 (추적 타임라인 포함)                    |
| POST   | `/v1/brand/shipments/:id/confirm-shipped` | 패킹/발송 확인 (`brandConfirmedShippedAt` 기록)         |

## 관련 모듈

- [orders](./orders.md) — 송장 발급의 입력(OrderItem/캐리어 스냅샷/배송비)이자 발급/취소가 구동하는 `Order.status`.
- [shipping](./shipping.md) — 캐리어 산출(`resolveCarrier`)·국가별 고정 배송비 정본(송장 27번 share 의 원천).
- [seeding](./seeding.md) — 크리에이터 시딩 주문도 같은 송장 경로(제품 없는 라인은 `OrderItem.brandId` 스냅샷으로 그룹핑)를 탄다.
