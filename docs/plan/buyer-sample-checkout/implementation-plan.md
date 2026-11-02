# buyer-sample-checkout — 빌드 스펙 (정본)

결정은 [`README.md`](./README.md) D1~D10. 이 문서는 **어떻게**만 다룬다. 상태는 `PROGRESS.md §7`.

## 1. 착수 게이트 (불변식 — 어기면 돈이 샌다)

| # | 게이트 |
|---|---|
| G1 | **가격·배송비는 서버가 다시 계산한다.** 클라이언트는 `{ product 종류 · id · 배송지 }` 만 보낸다. 서버가 제품의 `sampleQty`·`sampleUnitUsdCents` 와 목적국 7,000g 요율로 총액을 만들고, 결제 검증(`verify`)은 지금처럼 주문에 저장된 금액과 대조한다 |
| G2 | **바이어 주문은 소비자 축에서 빠진다.** `Order.kind`(enum `consumer` 기본 · `buyer_sample`)를 두고, 2026-10-29 에 걷은 `kind: consumer` 필터를 **같은 자리에 다시 건다** — 정산 `SETTLEABLE_ORDER_WHERE` · 연락처 `CONTACT_ORDER_WHERE` · 대시보드 주문 유형 · 브랜드관 판매 통계 · 송장 대기 그룹 · 결제 prepare 소유권 · 소비자 주문 조회. 걷은 목록은 결정 [storefront 2026-10-29](../../decisions/storefront.md#2026-10-29) 셋째 줄이 정본이고, 자리는 klow_server `9f6e1c2` diff 의 `kind` 줄로 찾는다. ⚠️ 새 필터를 하나라도 빠뜨리면 그 바이어 주문이 **브랜드 정산 후보**가 된다 |
| G3 | **바이어 주문은 브랜드 단위 송장 발급 경로로 못 간다** — `createForOrder`/`createForBrand` 는 `kind = buyer_sample` 이면 400. 바이어 주문의 송장은 KLOW 송장 엔드포인트 하나뿐 |
| G4 | **`Shipment.brandId IS NULL` = KLOW 송장.** 브랜드에 묶이는 조회(정산·EFS 청구·브랜드 화면)는 brandId NOT NULL 조건을 명시한다 — `1b89c2b` 의 `onlyBrandShipments()` 패턴 |
| G5 | **efs-billing: KLOW 송장은 '매칭됨 + KLOW 부담'.** 정산표 행이 HAWB 로 KLOW 송장에 붙으면 미매칭·`extraInFile` 이 아니고, 브랜드 청구서(`toInvoiceDoc`)에 절대 들어가지 않는다. 리포트에 별도 배열(`klowShipments`)로 실비를 보인다 — `4e580c4` 참고. 통관(관세·수출신고비) 행도 같은 사다리로 KLOW 송장에 붙으면 KLOW 부담 |
| G6 | **카드 정보 전송 금지** — 지금처럼 엑심베이 결제창만 쓴다 |
| G7 | 메이저 제품은 `Product` 가 없다 → `OrderItem.productId` NULL + `OrderItem.majorProductId`(FK `BuyerMajorProduct`, SET NULL). 인디는 `productId` = `BuyerProduct.productId`. 줄에 이름·이미지·브랜드명 **스냅샷**(기존 칸) |

## 2. 데이터 모델

마이그레이션 2개 — A 에서 1개, C 에서 1개(둘 다 nullable/ADD 라 롤링 안전).

**A: `add_buyer_sample_checkout`**
- `BuyerProduct.sampleQty Int?` · `sampleUnitUsdCents Int?`
- `BuyerMajorProduct.sampleQty Int?` · `sampleUnitUsdCents Int?`
- enum `OrderKind { consumer buyer_sample }` · `Order.kind OrderKind @default(consumer)` · `Order.buyerUserId String?`(FK `BuyerUser`, SET NULL) + 인덱스 `(kind, createdAt)`
- `OrderItem.majorProductId String?`(FK SET NULL)
- 인디 백필(같은 SQL, 멱등): 구간표 `minQty = 1` 행이 있으면 그 단가를 `sampleUnitUsdCents` 로 복사, `sampleQty` 는 NULL — **개수는 어드민이 넣어야 버튼이 뜬다**(D2). 구간표 행 자체는 지우지 않는다

**C: `shipment_brand_nullable`** — `ALTER TABLE "Shipment" ALTER COLUMN "brandId" DROP NOT NULL`. (타입이 깨지는 곳이 많아 A 와 떼어 둔다 — 지운 트랙의 같은 판단.)

## 3. 단계

### A. klow_server — 스키마 + 주문·결제 + 소비자 축 제외 + 어드민 API

- **읽을 것**: 이 문서 §1·§2 · `server/modules/{buyer,orders,payment}.md` · 결정 [storefront 2026-10-29](../../decisions/storefront.md#2026-10-29) · [payment 2026-08-17](../../decisions/payment.md#2026-08-17)(결제 확정 3중 방어선) · [payment 2026-09-10](../../decisions/payment.md#2026-09-10) · git `9f6e1c2`(제거 diff — `kind` 필터 자리) · `b593ec1`(옛 바이어 주문 생성·결제 — 참고만)
- **건드리는 레포 · 배포 순서**: klow_server 단독(이 단계는 배포하지 않는다 — C 끝에 한 번에)
- **스키마·데이터 위험**: 마이그레이션 `add_buyer_sample_checkout`(ADD COLUMN·CREATE TYPE + 멱등 백필, 롤링 안전). **git `feat/buyer-sample-checkout` + Neon DB 브랜치(staging 기준선 fork) 필요** — 없으면 멈추고 사용자에게 요청
- **할 일 (세션 안 순서 = 넘칠 때 정지점)**
  1. 스키마 + 마이그레이션(`migrate dev` — 비대화형이면 사용자 실행) + 백필
  2. G2 필터 재부착 + 회귀 스펙(정산 후보에 `buyer_sample` 주문이 안 들어감)
  3. 공개 API(BuyerGuard): `GET /v1/buyer/sample-quote?type=indie|major&id=&country=` → `{ qty, unitUsdCents, shippingUsdCents, totalUsdCents }` (국가 = 시딩 `supportedCountries()` 기준 · `enabled` 무관 · 7kg 티어 없으면 400 `no_sample_rate`. 같은 목록을 `GET /v1/buyer/sample-countries` 로 주문서 드롭다운에 준다) · `POST /v1/buyer/sample-orders` `{ type, id, 배송지 }` → `Order(kind=buyer_sample, buyerUserId, isSeeding=false, channel=web)` + 줄 1개(qty = `sampleQty`) — 노출(`published`) · 샘플 칸 둘 다 있어야 · 동의 3종은 소비자와 같은 zod
  4. 결제: prepare/verify/report-failure 소유권을 **바이어 세션**으로도 통과(소비자 `userId`·게스트 토큰과 별개 분기) · return 303 목적지를 바이어 결제 결과 화면(`/shop/sample-orders/:id/complete` 류 — B 에서 확정)으로 · 결제 확정 시 메일 2통(바이어 확인 · 운영팀 — 수신 주소는 바이어 문의 메일과 같은 env)
  5. 어드민 API: 인디·메이저 제품 PATCH 에 `sampleQty`(1~100)·`sampleUnitUsdCents` · `GET /admin/buyer/orders`(목록 — 결제 상태 필터) · `GET /admin/buyer/orders/:id`(상세 — 바이어 계정·배송지·줄·결제·송장) · 어드민 주문 목록 `type=buyerSample` 필터 + 응답에 `kind`
  6. 공개 제품 응답에 `sample: { qty, unitUsdCents } | null`
- **완료 기준**: 검증 3층(`npm run typecheck` · `npm run test:e2e` · `npm run start`) · G2 회귀 스펙 통과 · 로컬에서 테스트 바이어로 sample-quote(US) → sample-orders → prepare 응답까지 curl 왕복 · `server/modules/{buyer,orders,payment}.md` 갱신

### B. klow_admin + klow_web — 입력칸 · 바이어 주문 탭 · 상세 버튼 · 주문서·결제

제목과 순서만(A 응답 모양이 확정된 뒤 정밀화).
- **세션 안 순서**: ① admin 제품 편집 샘플 2칸(인디·메이저) ② admin 주문 목록 유형 '바이어주문'(`orderTypeOf`·`ORDER_TYPE_BADGE`) ③ admin `/buyer/orders` 목록·상세(Sidebar 바이어 그룹 한 줄) — 송장 버튼 자리만 ④ web Retail price 전면 제거(`KbMajorPricing` · `KbProductCard` · 그 외 `msrpUsdCents` 렌더 전부) ⑤ web 상세 샘플 단가 표시 + "Get N samples" 버튼(Discuss wholesale **아래**, 인디 `KbPricing` · 메이저 `KbMajorPricing`) + 인디 구간표 1행 샘플 표시 제거(D4) ⑥ web 주문서(배송지 · 견적 · 동의) → 엑심베이 → 결과 화면 ⑦ `kb` 사전 8개 언어(`npm run kb:check`)
- **배포 순서**: server(A) → admin → web. web 이 먼저면 버튼이 404 견적을 받는다

### C. KLOW 송장 + efs-billing KLOW 부담 + 배포

제목과 순서만.
- **세션 안 순서**: ① 마이그레이션 `shipment_brand_nullable` + G4 타입 정리 ② `POST /admin/buyer/orders/:id/shipment` — 발송인 `ShopSettings.klowSender*`(비면 400) · 통관 1줄(인디: 브랜드 품목 HS · 메이저: 화장품 기본 HS — **착수 전 사용자 확인**) · 신고가 = 결제 상품가 · 캐리어 = 국가 고정 `productCarrier` · 발급 실패·재시도 · G3 · 발급 성공 시 **바이어 추적 메일**(송장번호 + `/track` 링크, 송장당 1회 — `Shipment` 에 발송 시각을 남겨 재발급·재시도 중복 방지. 칸이 필요하면 C 마이그레이션에 nullable 로 함께) ③ 추적 cron 이 brandId NULL 송장을 견디는지 ④ efs-billing G5(리포트 `klowShipments` · 미매칭 제외 · 청구서 제외) + 스펙 ⑤ admin 상세 송장 버튼·라벨 · efs-billing 화면 'KLOW 부담' 섹션 ⑥ 결정 기록(`storefront.md` 또는 `shipping-seeding.md`) + CLAUDE.md 색인 · 모듈 문서 ⑦ staging: DB `migrate deploy`(Railway 가 자동으로 돈다 — 53행 메모) → server → admin → web · 테스트 결제 1건 · **EFS 실발급 1건은 사용자 확인 후**
- ⚠️ 운영 배포는 사용자 결정
