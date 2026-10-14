# buyer-sample-order — 빌드 스펙 (정본)

결정·스코프는 [`README.md`](./README.md). 상태는 `PROGRESS.md §7` 31~33행.

## §1 착수 게이트 (불변식)

| # | 게이트 |
|---|---|
| G1 | **소비자 `Order` 를 재사용**한다(`Order.kind = buyer_sample` + `buyerUserId`). 이유: `Shipment`·트래킹 cron·엑심베이 return/webhook/reconcile·환불이 전부 `Order.id` 기준이다. 별도 테이블이면 `order_id` 라우팅부터 다시 짜야 한다 |
| G2 | ⚠️⚠️ **엑심베이 공유 경로는 손대지 않는다** — `parseAndMarkPaid` 의 rescode 게이트([decisions/payment 2026-09-10](../../decisions/payment.md#2026-09-10)) · 금액 재검증 · `where paymentStatus: pending` 조건부 update. 분기는 그 **뒤**(후속효과)와 **앞**(prepare 소유권)에서만 |
| G3 | `markPaid` 후속효과는 kind 로 갈린다 — buyer_sample 은 **장바구니 비우기·스토어 통계·소비자 확인 메일·`createForOrderSystem`(자동 송장)·브랜드 알림톡을 전부 건너뛴다**. 하나라도 새면 브랜드 단위 EFS 송장이 브랜드 송화인 명의로 자동 발급된다 |
| G4 | **소비자 집계에서 `buyer_sample` 을 뺀다** — A 단계에서 `prisma.order.` 를 전수 grep 해 목록을 이 문서 §5 에 남긴다. 최소: 정산(`settlement.service`)·매출/대시보드 통계·어드민 주문 목록·`shipments` pending-groups·리뷰 요청 cron·결제 reconcile(이건 **포함**해야 한다) |
| G5 | 가격·배송비는 **서버가 재계산**한다 — 클라 스냅샷(`kb.samples`)의 가격은 무시. 샘플가 = `samplePrice(tiers)`(`buyer/buyer-completeness.ts`), 노출 판정은 공개 API 와 같은 함수. 배송비 = SKU ≥ 5 → 0, 아니면 `LogisticsRateService.customerShippingRateByIso2()[iso2]` 를 소비자와 같은 환산으로 USD 센트. 요율 없음·`enabled=false`·EFS 제외구역 = 주문 거부 |
| G6 | 바이어 주문 소유권 = `Order.buyerUserId === CurrentBuyer.id`. 소비자 쿠키(`klow_sid`)·게스트 HMAC 쿠키로는 바이어 주문을 prepare 할 수 없고 그 반대도 안 된다(buyer-auth G1 의 연장) |
| G7 | 브랜드 응답(`/v1/brand/sample-requests`)에 **바이어 회사·이메일·이름·주소·전화 없음** — 국가만(README D8) |
| G8 | 합포장 송장 = `Shipment.brandId = null` 1장. 발송인 = `ShopSettings.klowSender*`(비면 400 — 브랜드 송화인으로 폴백 금지). 통관 HS/카테고리 = **라인별** `OrderItem.hsCode`·`customsCategoryEn` |
| G9 | 부분환불은 `refund_type: 'P'` + 환불마다 유일한 `refund_id` + `balance` = 남은 결제액. ⚠️ 이 코드베이스는 전액(`F`)만 실호출해 봤다 → **테스트 MID 실왕복 전에는 운영 노출 금지** |
| G10 | 스키마 변경은 **git `feat/buyer-sample-order`(staging 에서) + Neon DB 브랜치(staging 기준선 fork)** — 없으면 멈추고 묻는다 |

## §2 데이터 모델 (A 단계 마이그레이션 1개 · `add_buyer_sample_order`)

```prisma
enum OrderKind { consumer buyer_sample }

model Order {
  // + 
  kind         OrderKind  @default(consumer)
  buyerUserId  String?
  buyerUser    BuyerUser? @relation(fields: [buyerUserId], references: [id])
  brandIntakes OrderBrandIntake[]
  partialRefunds OrderPartialRefund[]
  @@index([kind, paymentStatus])
  @@index([buyerUserId])
}

model OrderItem { /* + */ cancelledAt DateTime? }

enum OrderBrandIntakeStatus { requested brand_shipped received cancelled }

model OrderBrandIntake {
  id                String   @id @default(cuid())
  orderId           String
  brandId           String
  status            OrderBrandIntakeStatus @default(requested)
  brandShippedAt    DateTime?
  brandCourier      String?   // 국내 택배사 (선택)
  brandTrackingNo   String?   // 국내 송장번호 (선택)
  receivedAt        DateTime?
  receivedByAdminId String?
  brandEmailedAt    DateTime? // null = 이메일 받을 BrandUser 가 없었다 → 어드민 경고
  createdAt / updatedAt
  @@unique([orderId, brandId])
  @@index([brandId, status])
}

model OrderPartialRefund {
  id           String   @id @default(cuid())   // = 엑심베이 refund_id
  orderId      String
  amountUsd    Int      // 센트
  orderItemIds String[]
  reason       String
  adminId      String
  createdAt    DateTime @default(now())
}

model Shipment  { /* brandId String → String?  (null = KLOW 합포장) */ }

model ShopSettings {
  // +
  klowSenderName       String @default("")
  klowSenderAddress    String @default("")
  klowSenderPostalCode String @default("")
  klowSenderPhone      String @default("")
}
```

전부 nullable/default ADD + `Shipment.brandId` DROP NOT NULL → **롤링 안전 · 백필 없음**.
⚠️ `Shipment.brandId` 가 nullable 이 되면 `shipment.brandId!`/`shipment.brand.` 를 가정한 코드가 tsc 에서 터진다 — A 단계에서 **타입 오류를 전부 고치되 동작은 바꾸지 않는다**(기존 행은 전부 non-null).

## §3 API

| 표면 | 경로 | 단계 |
|---|---|---|
| 바이어 (BuyerGuard) | `POST /v1/buyer/orders/quote` `{productIds, countryCode}` → `{lines, subtotalUsd, shippingFeeUsd, totalUsd, freeShipping}` | A |
| | `POST /v1/buyer/orders` `{productIds, address{…Order 주소 칸}, consents{terms, refund, pgDataSharing}}` → `{orderId}` (pending) | A |
| | `POST /v1/buyer/payment/prepare` `{orderId, cardScope}` → 소비자 prepare 와 같은 payload | A |
| | `GET /v1/buyer/orders` · `GET /v1/buyer/orders/:id` (상태 · 품목 · 취소 품목 · 송장/추적 이벤트) | A (추적은 C) |
| 결제 공용 | `GET/POST /payment/return` · `POST /webhooks/eximbay` · `verify` · `report-failure` — **경로 그대로**, buyer_sample 이면 return 리다이렉트만 `/shop/checkout/complete?order=` | A |
| 브랜드 (BrandGuard) | `GET /v1/brand/sample-requests` · `POST /v1/brand/sample-requests/:intakeId/shipped` `{courier?, trackingNo?}` · `.../unshipped` · `GET /v1/brand/sample-requests/ship-to`(KLOW 주소) | B |
| 어드민 (AdminGuard) | `GET /admin/buyer/orders` · `GET /admin/buyer/orders/:id` · `POST …/:id/brands/:brandId/received` (+ 되돌리기) · `POST …/:id/items/cancel` `{orderItemIds, reason}`(부분환불) · `POST …/:id/cancel`(전액) · `GET/PATCH /admin/settings/klow-sender` | B |
| | `POST /admin/buyer/orders/:id/shipment`(합포장 발급) · 트래킹 새로고침은 기존 `POST /admin/shipments/:id/refresh-tracking` | C |

모듈: `src/modules/buyer-orders/` (평면 — `public-buyer-orders.controller.ts` · `brand-sample-requests.controller.ts` · `admin-buyer-orders.controller.ts` · `buyer-orders.service.ts` · `buyer-sample-pricing.ts` · `buyer-sample-email.ts`). 엔드포인트 문서 `docs/server/modules/buyer-orders.md`.
⚠️ 순환 주의: payment → buyer-orders(후속효과) / buyer-orders → payment(prepare·환불). 후속효과는 payment 쪽 훅 인터페이스로 받거나 buyer-orders 가 payment 를 import 하고 payment 는 Prisma 로 intake 를 직접 만든다 — A 에서 e2e(DI) 로 확인.

## §4 단계

### A. 서버 주문·결제 + klow_web 실결제 (31행)

- **읽을 것**: 이 문서 §1~§3 · `docs/server/modules/payment.md` · `docs/server/modules/buyer.md`(공개 API 절) · `decisions/payment.md` 2026-08-17·2026-09-10 · `plan/buyer-platform/mock-parity.md` 체크아웃·계정 행
- **코드 진입점**: `klow_server/src/modules/payment/payment.service.ts`(`prepare` :251 · `parseAndMarkPaid` :544 · `handleReturn` :628 · `markPaid` :984 후속효과 :1054~1077 · `buildOrderLines` :396) · `buyer/buyer-completeness.ts#samplePrice` · `shipping/logistics-rate.service.ts#customerShippingRateByIso2` · klow_web `components/buyer-space/{KbCheckout,KbPayment,KbComplete,KbAccount,KbRequestDetail,KbSampleBox,KbBuyer}.tsx` · `lib/buyer-space-mock.ts` · `lib/eximbay.ts`
- **세션 안 순서 (= 정지점)**
  1. git 브랜치 + DB 브랜치(G10) → §2 마이그레이션 → `Shipment.brandId` nullable 로 생긴 타입 오류 정리 → typecheck 2종 **[정지점 ①]**
  2. G4 전수 grep → 소비자 쿼리에 `kind: 'consumer'` 필터(목록을 §5 에 기록)
  3. `buyer-orders` 모듈: quote · create(G5) · 목록/상세 · prepare(G6) — payment.service 분기(G2·G3) · 결제 후 intake 행 생성 + 브랜드 메일 + 바이어 메일 → jest **[정지점 ②]**
  4. klow_web: KbCheckout 전체 배송지 폼(영문 주소·국가별 세금식별코드 — 소비자 체크아웃 검증 재사용) + 동의 + quote · KbPayment 실결제 · Complete/Account/RequestDetail 서버 주문 · 목업 `$18`·`placeOrder`·문의 API 전송 제거 · 샘플박스 "5개 이상 무료" 문구 · mock-parity 갱신 **[정지점 ③]**
- **완료 기준**: 검증 3층 · jest(가격/배송비 재계산 · SKU 4/5 경계 · 미지원국 거부 · 남의 주문 prepare 403 · 후속효과 분기 · rescode 게이트 회귀) · 로컬 서버 + DB 브랜치 + **엑심베이 테스트 MID** 로 Playwright 결제 왕복 → `Order.paymentStatus=paid` · intake 행 N개 · 브랜드 메일(Resend 싱크) · **`Shipment` 0행**(G3) · **소비자 결제 1건 회귀**(같은 return/webhook)
- **배포**: 배포 없음(B·C 와 함께 staging 병합) — 병합 시 migrate → server → web

### B. 입고 흐름 — klow_brand 샘플 요청 · 어드민 바이어 주문 · 부분환불 · 발송인 설정 (32행)

klow_brand `(authed)/samples/`(StudioPillHeader 버튼 + middleware matcher · 주소 복사 = `components/shipping/ui.tsx#EfsWarehouseRows` 패턴) · klow_admin `(authed)/buyer/orders` 목록/상세(브랜드별 intake 카드 · 48h 미발송 강조 · 메일 미발송 경고 · 입고 확인 · 품목 체크 → 부분환불) · 설정에 KLOW 발송인 4칸 · 서버 §3 B 행 · 부분환불 G9 실왕복. 배포 순서 server → admin → brand. 명세는 A 가 끝난 뒤 이 자리에 정밀화한다.

### C. 합포장 EFS 송장 + 라벨 + 트래킹 + 마무리 (33행)

`payload-builder.ts` 라인별 통관(G8) · `shipments.service.createConsolidatedForBuyerOrder` · 어드민 '송장 발급'(전 브랜드 received/cancelled 일 때만) · 라벨 출력(klow_brand `components/shipping/print.tsx`·`label-pdf.ts` 를 admin 으로 복사) · 바이어 요청 상세에 추적 이벤트 · 결정 기록(`decisions/storefront.md` 또는 `shipping-seeding.md`) + CLAUDE.md 색인. ⚠️ EFS 는 실계정 — 실발급은 **staging 1건, 사용자 확인 후**. 명세는 B 뒤에 정밀화한다.

## §5 G4 전수 목록 (A 단계가 채웠다 — 2026-10-14)

`prisma.order.(findMany|count|aggregate|groupBy|findFirst)` · `orderItem.*` 집계 · 원시 SQL(`"Order"`) 전수.

| 위치 | 판단 |
|---|---|
| `orders/contact-population.ts#CONTACT_ORDER_WHERE` | **`kind: consumer` 추가** — 브랜드 CRM · 어드민 컨택트 · 리뷰 요청 cron(웹·현장 스캔) · 고객 리뷰 링크가 이걸 쓴다. 브랜드 CRM 에 새면 G7 위반 |
| `orders.service#buildAdminOrderWhere` | **추가** — 어드민 주문 목록·건수·매출 카드(바이어 주문은 B 의 '바이어 주문' 화면) |
| `shipments.service#listPendingGroups` | **추가** — (주문, 브랜드) 자동 그룹 발급 대상 아님 |
| `settlement.service#SETTLEABLE_ORDER_WHERE` | **추가**(방어 — 송장 기반이라 지금도 자연 제외지만 C 의 합포장 송장도 Shipment 다). 스펙 `settlement-recognition.spec.ts` 에 회귀 케이스 |
| `storefront-stats/storefront-sales.service` 원시 SQL 2곳 | **추가** — 브랜드관 판매 분석(국가·제품)에 샘플이 섞이지 않게 |
| `stats.service#orderTypeTrend` 원시 SQL | **추가** — 주별 일반/시딩/현장 막대. ⚠️ `gmvKrw`(거래액)는 **그대로 포함** — "전체 결제" 정의라 KLOW 가 받은 샘플 대금도 거래액이다 |
| `payment.service#findReconcilableOrderIds` | **포함 유지** — 재확인 크론이 바이어 결제도 복구해야 한다 |
| `orders.service#findMine`(userId) · 시딩 조회 · `promotions#purchaseStats`(promotionId) · `pg-settlement`(id 목록) | 자연 제외(바이어 주문은 userId·promotionId 없음, 시딩 아님). `pg-settlement` 은 엑심베이 정산서에 바이어 주문 행이 있으면 주문을 찾지만 정산 추정치가 송장 기반이라 영향 없음 — 33행 합포장 송장 뒤에 다시 볼 것 |

## §6 A 단계에서 스펙과 다르게 한 것

- ⚠️ **`Shipment.brandId` nullable 은 C(33행)로 미뤘다.** 바꾸면 정산·EFS 청구·송장 코드 59곳의 타입이 깨지는데(`shipment.brand.name` 등), 실제로 brandId 없는 송장이 생기는 건 C 다. C 가 두 번째 마이그레이션(ALTER DROP NOT NULL — 롤링 안전)으로 한다.
- `Order.buyerNote`(VarChar 500) 추가 — 디자인의 메모 칸. **운영팀만 본다**(브랜드 메일·화면에 싣지 않는다 — 연락처를 적을 수 있어서). 그래서 바이어 화면 라벨을 "Note to the brands" → **"Note to the KLOW team"** 으로 바꿨다.
- 견적은 내려간 샘플을 400 대신 `unavailableProductIds` 로 알린다(화면이 그 줄에 표시) — 주문 생성만 400 `samples_unavailable`.
- 요청 상세의 "Reorder these samples" 는 뺐다 — 서버 주문 라인에 샘플박스 스냅샷(브랜드 slug·규격·MSRP)이 없다.
- 바이어 주문 상태는 서버가 계산한다(`buyerSampleStatus` — `server/modules/buyer-orders.md`).
