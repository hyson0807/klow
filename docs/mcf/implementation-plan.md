# ② Amazon MCF 실제 구현 계획 (living doc)

> **이 문서가 구현·스키마의 정본이다.** 현재 버전: **v1 (2026-07-08)**. 모든 경로는 `klow_server/` 기준(별도 표기 제외). 프론트는 `klow_brand/`.
>
> **처음 보고 착수한다면**: (1) 빌드 순서는 **§10 로드맵 체크리스트** 그대로, (2) 각 단계 착수 전 **§13 통합 불변식**(F1~F7·R5~R7)을 먼저 읽는다.
>
> **⚠️ 라인번호는 2026-07-08 스냅샷**(예: `executeCreate` :630, settlement `:100/:193`). 구현 시점엔 밀려 있을 수 있으니
> **심볼명(함수/상수)으로 재확인** 후 편집한다. §13 "근거" 열이 심볼명을 함께 준다.

## 0. 스코프

**해야 할 것 (v1)**
1. 브랜드 Amazon 계정 OAuth 연결 + 마켓플레이스별 SKU 매핑 + FBA 재고 주기 동기화.
2. **일반주문 결제 확정 시**, 도착국 Amazon 창고에 브랜드 전 제품 재고가 있으면 **`createFulfillmentOrder`**
   로 Amazon 출고(= 자동 발송), 아니면 기존 EFS.
3. Amazon 출고 상태·추적 갱신, 정산(매출) delivered gate 확장.
4. **MCF 마진 트랙**: 제품마다 MCF 판매가·정산가를 일반과 별도로(기본값=일반과 동일, `MCF마진`으로 조절). Amazon 수수료는 브랜드가 자기 계정에서 부담 — KLOW 조회·보전 없음(§7·§8).

**안 할 것 (v1)**
- **시딩 MCF.** 시딩 라인은 `OrderItem.productId=null` 이고 `SeedingLink.selectedSkus`/`selectionSkus` 는
  자유텍스트 제품명 라벨이라 SKU/재고 판정을 못 탄다 → 시딩은 항상 EFS. MCF 는 선택 필드에 실제 productId 를
  심는 스키마 변경(v2) 이후.
- 크로스보더 MCF(재고국≠도착국). 도메스틱만.
- 라인 분할(브랜드 내 Amazon+EFS 혼합). 브랜드 all-or-nothing.
- Notifications 이벤트 구독(폴링으로 대체).
- Amazon 마켓플레이스에 리스팅/판매(무관).

## 1. 데이터 모델 (Prisma)

### 신규 모델
```prisma
// 브랜드 Amazon 계정 연결 — BillingKey 선례 미러. refresh token 은 암호화 저장.
model BrandAmazonConnection {
  id             String    @id @default(cuid())
  brandId        String
  region         String    // 'na' | 'eu' | 'fe' (SP-API 리전)
  marketplaceIds String[]  // 이 계정으로 커버되는 마켓플레이스들
  sellerId       String
  refreshToken   String    // AES-256-GCM 암호화 (ADMIN_TOTP 방식 재사용/신규 키)
  status         String    @default("active") // active | reauth_required | disconnected
  lastSyncedAt   DateTime?
  createdAt      DateTime  @default(now())
  deletedAt      DateTime?
  brand          Brand     @relation(fields: [brandId], references: [id])
  @@index([brandId])
}

// 제품 ↔ Amazon SKU (마켓플레이스별) + MCF 마진 트랙. ProductCountryPrice 에 얹지 않음(그건 replace-all).
model ProductAmazonListing {
  id            String  @id @default(cuid())
  productId     String
  marketplaceId String  // 'US' | 'JP' | ... (iso2 또는 Amazon marketplaceId — 아래 열린질문)
  sellerSku     String
  asin          String?
  fnSku         String?
  // MCF 마진(§7-1). null = 기본값(일반 마진 + 물류비/2 자동 → MCF 판매가=일반가). 값 있으면 MCF 트랙 독립 조절.
  mcfMarginKrw  Int?
  createdAt     DateTime @default(now())
  product       Product  @relation(fields: [productId], references: [id])
  @@unique([productId, marketplaceId])
  @@index([marketplaceId, sellerSku])
}

// FBA 재고 동기화 스냅샷 — 라우팅 1차 판정 소스.
model FbaInventoryCache {
  id            String   @id @default(cuid())
  brandId       String
  marketplaceId String
  sellerSku     String
  available     Int
  reserved      Int      @default(0)
  inbound       Int      @default(0)
  syncedAt      DateTime
  @@unique([marketplaceId, sellerSku])
  @@index([brandId])
}
```

### 기존 모델 확장
- **`Shipment`**: 채널·Amazon 식별자·**전용 상태 컬럼**·출고원가 추가.
  ```prisma
  channel                  String   @default("EFS") // 'EFS' | 'AMAZON_MCF'  (현재 채널 컬럼 없음 → 신규, 충돌 없음)
  amazonFulfillmentOrderId String?  @unique
  amazonShipmentId         String?
  amazonTrackingNumber     String?  // 대표 추적번호(복수면 첫 패키지)
  // 한 MCF 주문이 여러 박스로 쪼개질 수 있음 → 패키지별 추적을 배열로 저장(§7). getFulfillmentOrder 회신.
  amazonPackages           Json?    // [{ packageNumber, carrier, trackingNumber, status }]
  // MCF 전용 상태 — EFS 의 latestStatusCode(@db.VarChar(2)) 재사용 금지(Amazon 상태 문자열 부적합)
  mcfStatus                String?  // Amazon fulfillment status 원문(예: PROCESSING/COMPLETE)
  mcfStatusUpdatedAt       DateTime?
  // (분석용·옵션) Amazon MCF 수수료 실비. 브랜드가 자기 계정서 부담하므로 money flow·정산과 무관 — 수익성 분석용. 없어도 됨.
  mcfChargeKrw             Int?
  mcfChargeSource          String?  @db.VarChar(10)
  mcfChargeUpdatedAt       DateTime?
  ```
  - **주의(R3)**: 현재 `Shipment` 에는 채널 관련 컬럼이 전혀 없다(암묵적 EFS 전용). `channel`/`amazon*`/`mcf*` 는 전부 신규 — 충돌 없음.
  - **주의(R2)**: `latestStatusCode @db.VarChar(2)`·`efsTrackingNumber @db.VarChar(13)`·`efsServiceType @db.VarChar(10)` 는
    EFS 전용 폭 제약이라 Amazon 값이 안 들어감 → MCF 는 위 `mcfStatus`/`amazonTrackingNumber` 전용 컬럼을 쓴다.
  - **⚠️ F1 (필수 컬럼 nullability — 반드시 마이그레이션에 포함)**: 실측 결과 `Shipment` 의 **`carrier ShippingCarrier`·`efsServiceType String @db.VarChar(10)`·`requestPayload Json`
    셋은 non-null 필수**다. "EFS 전용 컬럼은 MCF 행 null" 은 이 셋엔 적용 불가 — 그냥 두면 MCF 행 INSERT 가 실패한다. 처리:
    - `efsServiceType` → **마이그레이션에서 nullable 로 변경**(MCF 는 EFS service type 없음). `String? @db.VarChar(10)`.
    - `carrier` → resolveFulfillmentChannel 이전에 `carrierForBrand(order, brand.id)` 로 이미 구하므로 **그 값을 그대로 저장**(스키마 변경 없이 채움 가능). 단 EFS-제외구역으로 carrier 가 없어 throw 하는 경우가 있어, MCF 행에서도 필요 없다면 nullable 화가 더 안전 — **권장: `carrier` 도 nullable**.
    - `requestPayload` → MCF 요청 스냅샷(`sellerFulfillmentOrderId`, items, destinationAddress)을 담아 non-null 유지.
  - 3-state UI enum(requested/shipping/delivered)은 두 채널(EFS `latestStatusCode` / MCF `mcfStatus`)을 각각 매핑하는 레이어에서 산출.
  - 정산 delivered 판정: EFS `'33'` + MCF 종료상태를 함께 인식하는 **`settleableDeliveredWhere(): Prisma.ShipmentWhereInput` where-프래그먼트**로 처리 — JS 불리언 헬퍼가 아니다(§8·F5).
- **`OrderItem`**: 스키마 변경 불요. 일반주문 라우팅은 `OrderItem.productId`(nullable) 를 읽는다. **시딩 라인은 productId=null 이라
  v1 에서 항상 EFS**(§5). `settlementPriceKrw`(nullable) 는 **발급 시 실제 채널 정산가로 세팅**(MCF→MCF정산가, EFS→일반정산가)해 정산에 그대로 쓴다(§8-1·F8).
- **`Order`**: 스키마 변경 불요. 라우팅 키 `order.countryCode` 는 **nullable(`@db.VarChar(2)`, legacy 주문 null)** — 라우팅 0단계에서
  null → EFS 로 가드. 주소는 `Order` 인라인 컬럼(§4·R7).
- **`ShippingCountry`**: (열린질문) 도착국→마켓플레이스 판정을 위해 `amazonMarketplaceId` 추가할지, 아니면
  `ProductAmazonListing` 존재 여부로만 판정할지 결정.
- **`ShippingCarrier` enum**: MCF 는 `Shipment.channel` 판별자로 분리하므로 enum 에 값 추가는 하지 않는
  방향(권장). `carrierForBrand`/`buildPayload` 가 EFS service type 을 전제하기 때문.

마이그레이션: `npx prisma migrate dev --name add_amazon_mcf` (interactive → 사용자 실행). **포함 사항**: 신규 3모델 +
`Shipment` 신규 컬럼(channel/amazon*/mcf*) + **기존 `efsServiceType`(및 권장 `carrier`) 를 nullable 로 변경**(F1). `channel`
은 `@default("EFS")` 라 기존 행 자동 backfill.

## 2. 모듈 구성 — `src/modules/amazon/`

`EfsClient`/`TrackingRefreshCron`/`shipments.module` 패턴을 미러.

```
src/modules/amazon/
  amazon.module.ts              // app.module.ts imports 에 추가
  amazon-spapi.client.ts        // EfsClient 미러: ConfigService, 빈 크레드→mock
  amazon-connection.service.ts  // OAuth 연결/해제/재연결, 토큰 암복호화
  amazon-listing.service.ts     // 제품↔SKU 매핑 CRUD
  fba-inventory.service.ts      // 재고 동기화(수동+크론 공용)
  fba-inventory-sync.cron.ts    // TrackingRefreshCron 미러(시간별, env kill-switch)
  mcf-fulfillment.service.ts    // createFulfillmentOrder / getFulfillmentOrder 래핑
  brand-amazon.controller.ts    // /v1/brand/amazon/* (브랜드 페이지 API)
  amazon.types.ts
```

`shipments.service.ts` 는 `McfFulfillmentService` + `FbaInventoryService` + `AmazonListingService` 를
주입받아 `executeCreate` 안에서 라우팅/발급을 호출한다.

## 3. SP-API 클라이언트 & 인증

- **앱 등록 위치**: Solution Provider Portal(`solutionproviderportal.amazon.com`)에 KLOW 앱이 등록돼 있다
  (앱 이름 `klow`, App ID = Solution ID). LWA client id/secret 은 그 포털 앱 목록의 **"LWA 자격 증명 → 샌드박스 자격 증명 보기"**
  에서 확인. **주의: 셀러 등록(`sell in our store`)은 다른 트랙이며 MCF 엔 불필요** — KLOW 는 셀러가 아니라 솔루션 제공자다.
- **`.env.example` 블록** (`# ===== Amazon SP-API / MCF =====`). **빈 값 → mock 모드**(dev):
  ```bash
  # 앱 식별자 — 브랜드 OAuth consent URL 의 application_id 파라미터에 사용(비밀 아님)
  AMAZON_APP_ID=amzn1.sp.solution.xxxxxxxx
  # LWA 크레드 — 포털 "샌드박스/프로덕션 자격 증명 보기"에서 발급 (비밀)
  AMAZON_LWA_CLIENT_ID=amzn1.application-oa2-client.xxxxxxxx
  AMAZON_LWA_CLIENT_SECRET=
  # 환경 스위치 + 리전별 base (sandbox|production). 리전 na/eu/fe 별로 host prefix 만 다름
  AMAZON_SP_API_ENV=sandbox
  AMAZON_SP_API_BASE_NA=https://sandbox.sellingpartnerapi-na.amazon.com   # prod: https://sellingpartnerapi-na.amazon.com
  # 샌드박스 self-authorization refresh token (프로덕션은 per-brand DB 저장, 아래 참고)
  AMAZON_SANDBOX_REFRESH_TOKEN=
  # refresh token 암호화 키 (32B base64) — ADMIN_TOTP 키와 분리(§11)
  AMAZON_TOKEN_ENCRYPTION_KEY=
  # 크론 kill-switch (미설정=on)
  AMAZON_SYNC_CRON_ENABLED=
  ```
  - LWA access token 발급(토큰 교환) 엔드포인트: `POST https://api.amazon.com/auth/o2/token`
    (`grant_type=refresh_token` + `refresh_token` + `client_id` + `client_secret` → access token, 1h). 메모리 캐시.
- **refresh token 저장 위치 — 환경별 상이**:
  - **샌드박스**: 실제 브랜드 OAuth 가 없으므로 포털에서 받은 **self-authorization refresh token 1개를 env**(`AMAZON_SANDBOX_REFRESH_TOKEN`)
    로 두고 e2e 검증에 쓴다.
  - **프로덕션**: 브랜드마다 OAuth 로 발급된 **per-brand `BrandAmazonConnection.refreshToken`**(암호화 저장).
- **프로덕션 전환 선행 작업**(포털 상단 2단계): ① 신원 확인(ID 확인, ~20분, 사업자등록+신원문서) ② **역할/사용사례/보안 설정 —
  여기서 Fulfillment Outbound + FBA Inventory Role 신청**(없으면 프로덕션 오퍼레이션 403). 샌드박스 검증엔 불필요.
- **RDT**: Amazon PII 를 *읽는* 오퍼레이션에만 필요. 배송지를 KLOW 가 제공하는 `createFulfillmentOrder`
  는 RDT 불필요 가능성이 크고, 주소를 응답으로 받는 `getFulfillmentOrder`(추적) 쪽이 대상일 수 있음 —
  Role Mappings 문서로 확정 후 필요한 것만 Tokens API 로 발급. (열린 질문 §11)
- **OAuth 연결 플로우**:
  - `GET /v1/brand/amazon/connect?region=na` → Amazon consent URL 리다이렉트.
  - `GET /v1/brand/amazon/callback` → authorization code → refresh token 교환 → 저장.
  - 목업 `ConnectModal` 자리를 실제 OAuth 리다이렉트로 교체.

## 4. 발급 분기 (핵심) — `shipments.service.ts executeCreate`

현재 `executeCreate(order, group, shippingFeeShareUsd, adminId)` (:630–749): `carrierForBrand`(:656) →
`buildPayload` → `Shipment` 저장 → `efs.newCreateShipment`(:719).

**변경**: `carrierForBrand` 직후 채널 판정. **executeCreate 의 반환 계약을 반드시 지킨다** —
`Promise<{ shipment: ShipmentWithRelations; warnings: string[] }>` (void `return;` 아님).
```
const channel = await resolveFulfillmentChannel(order, group);
if (channel === 'AMAZON_MCF') {
  try {
    const res = await this.mcf.createFulfillmentOrder(order, group.lines); // 주소는 raw order.* (R7)
    // F2: EFS 경로와 동일하게 Shipment + ShipmentItem(items.create) 행 생성.
    //     channel=AMAZON_MCF, amazonFulfillmentOrderId, mcfStatus, status=submitted,
    //     carrier=이미 구한 값, efsServiceType=null, requestPayload=MCF 스냅샷.
    const shipment = await this.saveMcfShipment(order, group, res, existing);
    return { shipment, warnings: [] };           // ← 반환 계약 준수
  } catch (e) {
    if (isAmbiguous(e)) {                       // R5: 타임아웃/응답유실 등 접수 불명
      const accepted = await this.mcf.getFulfillmentOrder(sellerFulfillmentOrderId); // 또는 listAll
      if (accepted) { const shipment = await this.saveMcfShipment(...); return { shipment, warnings: [] }; }
    }
    // 명확한 재고부족/부적격, 또는 미접수 확인 → EFS 폴백 (아래 기존 경로로 진행)
  }
}
// 기존 EFS 경로(buildPayload → efs.newCreateShipment) 그대로
```
- **F2 (ShipmentItem 조인 불변식 — 치명적)**: MCF 경로도 EFS 처럼 **`Shipment` + 중첩 `items.create`(ShipmentItem, `orderItemId @unique`)** 를
  만들어야 한다. ShipmentItem 을 안 만들면 (a) `maybeMarkOrderShipped`(`order.items.every(i => i.shipmentItem?.shipment?.status===submitted)`)가
  영영 false → 주문이 shipped 로 안 넘어가고, (b) settlement 후보 쿼리의 `shipment.items → orderItem.settlementPriceKrw` 조인이 비어 **정산금 0**.
  상태는 `submitted`(EFS 와 동일 값) 로 저장해 두 불변식을 만족시킨다.
- **F3 (재발급 시 채널 전환)**: `existing` 이 있으면(=failed/cancelled 재발급) EFS 처럼 **같은 row 를 update** 로 재사용한다. MCF↔EFS 가
  시도마다 바뀔 수 있으므로 update 시 `channel` 을 새로 세팅하고 **반대 채널 컬럼을 clear** 해야 한다:
  EFS→MCF 재발급 → `efsTrackingNumber`/`localCarrierName`/`localTrackingNumber` null; MCF→EFS 재발급 → `amazonFulfillmentOrderId`/`amazonShipmentId`/`amazonTrackingNumber`/`mcfStatus` null.
  (현 EFS update 브랜치는 efs 컬럼만 리셋하므로 amazon* 초기화 로직 추가 필요.)
- **R5 (이중출고 방지)**: 모호 실패를 곧바로 EFS 폴백하면 Amazon+EFS 둘 다 발송될 수 있다. `sellerFulfillmentOrderId`
  가 발급마다 유일하므로 이를 키로 `getFulfillmentOrder`/`listAllFulfillmentOrders` 접수 확인 후 분기한다.
- **R7 (주소는 raw)**: Amazon `destinationAddress` 는 EFS payload-builder 의 `sanitize()`(`|{}"\r\n` strip)·길이컷·
  `buildCityState`(city+state 병합) 를 **거치지 않은 `order.*` 원본**(`fullName`/`addressLine1`/`addressLine2`/`city`/
  `recipientState`/`postalCode`/`countryCode`/`phone`/`email`)을 쓴다. 특히 병합된 city 를 재사용하지 말 것.
  (`loadOrderWithItems` 가 `order` 전체 컬럼을 include 하므로 raw 값은 그대로 접근 가능.)

`resolveFulfillmentChannel(order, group)` (신규, `mcf-fulfillment.service` 또는 shipments 내부 헬퍼):
0. `order.countryCode` 가 **null(legacy)** 이면 EFS.
1. `order.countryCode` 로 도착국 마켓플레이스 결정. 브랜드가 그 마켓플레이스에 **연결**돼 있나
   (`BrandAmazonConnection`)? 아니면 EFS.
2. **시딩 주문은 v1 에서 무조건 EFS** — `order.isSeeding === true`(스키마 :513, 이미 로드된 order 에 존재 → seedingLink 조회 불필요)면 EFS. productId 해석 불가(§5).
3. **브랜드 all-or-nothing**: group.lines 전부가
   - `OrderItem.productId` 존재(일반주문) &&
   - `ProductAmazonListing(productId, marketplaceId)` 존재 &&
   - `FbaInventoryCache.available ≥ line.quantity`
   를 만족? → `AMAZON_MCF`, 아니면 `EFS`.
4. 도메스틱 전제이므로 창고국 == 도착국 자동 성립.

`sellerFulfillmentOrderId` = **발급 시도마다 유일**해야 한다. `Shipment` 는 실패/취소 후 **재발급**을
지원하므로(`isReissuableStatus`), 고정 `klow-{orderId}-{brandId}` 를 재사용하면 Amazon 이 중복/취소 ID
로 거부할 수 있다 — EFS 가 취소된 refNo 재사용을 막아 발급마다 유일 `refNoToken` 을 붙이는 것과 동일한
제약. → `klow-{orderId}-{brandId}-{issueToken}`(EFS `refNoToken` 방식 미러) 로 발급마다 새 토큰을 부여.
동일 시도 내 재시도(네트워크 실패)는 같은 토큰으로 멱등 유지.

## 5. 시딩 (결정: v1 제외 — 항상 EFS)

**시딩 MCF 는 현 스키마로 불가하다.** 코드 실측 결과:
- 시딩 `OrderItem.productId` 는 **항상 null**(`seeding.service` claim/checkout, 커스텀 스냅샷만).
- `SeedingLink.selectionSkus`/`selectedSkus` 는 **제품 ID 가 아니라 자유텍스트 제품명 라벨**이다. `createLink` 는
  trim/dedupe 만(Product 조회·소유검증 없음), `fetchProductCards` 는 `Product` 를 **`name` 으로** best-effort 조회하고
  `id: name`(문자열)로 카드를 만든다. 스키마 주석의 "제품 ID/Product 참조" 는 stale.

→ 따라서 productId → `ProductAmazonListing` → `FbaInventoryCache` 판정 경로를 **탈 수 없다.**

- **v1**: 시딩은 §4 라우팅 2단계(`order.isSeeding === true` → EFS)에서 자연히 EFS. 트리거는 이미 공통
  (`seeding.claim` → `createForOrder`) 이라 **추가 배선 불필요.**
- **v2(후속)**: `SeedingLink` 선택 필드에 실제 productId 를 심는 스키마 변경 + 시딩 발급 시 `OrderItem.productId`
  채우기. 그 뒤라야 §4 일반주문 경로 재사용이 가능하다.

## 6. 동기화 (기능 ①)

- `FbaInventoryService.syncBrand(brandId)` — `getInventorySummaries` → `FbaInventoryCache` upsert +
  `BrandAmazonConnection.lastSyncedAt` 갱신.
- `fba-inventory-sync.cron.ts` — `@Cron('0 * * * *', { timeZone: 'Asia/Seoul' })` 전 브랜드 순회
  (env `AMAZON_SYNC_CRON_ENABLED` kill-switch).
- 수동: `POST /v1/brand/amazon/sync` — 브랜드 페이지 '지금 동기화' 버튼.

## 7. 출고 상태·추적 (기능 ③)

- `createFulfillmentOrder` 성공 = Amazon 이 자동 발송. 별도 발송 작업 없음.
- `getFulfillmentOrder` 폴링 크론(또는 기존 tracking-refresh 확장)으로 상태·`amazonTrackingNumber` 를
  `Shipment` 에 갱신. MCF 종료상태(배송완료)를 정산 게이트가 인식하도록 매핑.
- **F7 (EFS cron 이 MCF 를 자연 제외 — 좋은 성질)**: 기존 `refreshTrackingDue()` 는 `efsTrackingNumber: { not: null }`
  로 대상을 거른다. MCF 행은 `efsTrackingNumber=null` 이라 **자동 제외** → EFS 폴링이 MCF 행을 건드릴 위험 없음.
  따라서 **기존 cron 확장보다 별도 MCF cron 이 깔끔**하다.
- **MCF 폴링 due-selection**: `channel='AMAZON_MCF'` + `amazonFulfillmentOrderId: { not: null }` + `status=submitted`
  + `mcfStatus` 가 아직 종료상태(`MCF_TERMINAL_STATUSES`) 아님. `fba-inventory-sync.cron` 과 같은 kill-switch 패턴.
- **⚠️ 한 MCF 주문 = 복수 패키지 가능**: 같은 브랜드 라인 N개를 한 `createFulfillmentOrder` 로 보내도 Amazon 이 여러 박스로 쪼갤 수 있어
  **추적번호가 여러 개** 나온다(`getFulfillmentOrder` 의 `fulfillmentShipments`/`packages`). 스키마의 `amazonTrackingNumber String?`(단일)로는
  부족 → **`amazonPackages Json?`(예: `[{packageNumber, carrier, trackingNumber, status}]`) 로 복수 저장**하고, 대표 1개를
  `amazonTrackingNumber` 에 두는 방식 권장. 종료상태 판정은 "전 패키지 delivered"로. UI(출고 현황·추적)도 복수 추적 대응.

## 8. 정산 — 채널별 정산가 (MCF 마진 트랙)

### 8-1. 실제 나간 채널의 정산가로 정산 (F8)
- 브랜드 정산액 = `Σ (라인이 실제 나간 채널의 정산가) × qty`.
  - EFS(폴백 포함) → 일반 정산가 `원가 + 마진`.
  - MCF → MCF 정산가 `원가 + MCF마진`(§1 `ProductAmazonListing.mcfMarginKrw`, null 이면 기본값 `마진 + 물류비/2`).
- **구현(권장): 발급 시점(`executeCreate`)에 확정된 채널로 `OrderItem.settlementPriceKrw` 를 세팅**한다 — MCF 발급이면 MCF 정산가, EFS(폴백 포함)면 일반 정산가.
  그러면 `settlement.service` 는 **기존 `Σ settlementPriceKrw × qty` 그대로**(채널 판별 불필요) 동작한다.
- **F8 (폴백 정산가 정합)**: MCF 표시가로 결제됐어도 EFS 로 폴백되면 `settlementPriceKrw` 는 **일반 정산가**여야 한다(그래야 KLOW 가 EFS 물류비를 내면서 브랜드에 물류비/2 를 이중 지급하지 않음). 발급 시 실제 채널로 세팅하면 자동 충족.
- Amazon 수수료는 브랜드가 자기 계정서 부담(§8-3) — KLOW 보전·조회 없음.

### 8-2. delivered 게이트 (F5)
- **F5 (게이트는 boolean 이 아니라 Prisma where 프래그먼트)**: delivered 게이트 `latestStatusCode: EFS_STATUS_DELIVERED` 는
  **Prisma `where` 안에 인라인**된다(4곳: `getBrandSummary` :100, `listAdminCandidates` :193, `listAdminBrandCandidates` :298,
  `settle()` 트랜잭션 :328 — 모두 `...SETTLEABLE_SHIPMENT_WHERE`·`settledAt:null`·`brandId` 와 형제). 따라서 공유물은
  JS 불리언 헬퍼가 아니라 **where-빌더**여야 한다:
  ```ts
  const MCF_TERMINAL_STATUSES = ['COMPLETE']; // getFulfillmentOrder 종료 상태(착수 시 확정)
  function settleableDeliveredWhere(): Prisma.ShipmentWhereInput {
    return { OR: [
      { channel: 'EFS', latestStatusCode: EFS_STATUS_DELIVERED },
      { channel: 'AMAZON_MCF', mcfStatus: { in: MCF_TERMINAL_STATUSES } },
    ] };
  }
  ```
  4곳에서 `latestStatusCode: EFS_STATUS_DELIVERED` 를 `...settleableDeliveredWhere()` 로 치환(Prisma 가 top-level 키를 AND
  하므로 `{ brandId, settledAt:null, order:…, OR:[…] }` 로 안전하게 합성).
  - 이 "정산용 delivered" 는 tracking 폴링 중단용 `TERMINAL_TRACKING_CODES=['33','47','74','42']`(shipments.service)
    와 **다른 집합** — where-빌더로 정의를 명시적으로 분리한다.
  - `settle()` 트랜잭션은 게이트를 재확인하고 `updated.count !== shipmentIds.length` 면 throw 하므로, **같은 where-빌더를
    read 4곳·write 1곳이 공유**해야 candidate 로 보였던 MCF 행이 settle 에서 튕기지 않는다.

### 8-3. Amazon 수수료는 브랜드 부담 (KLOW 보전·조회 없음)
- Amazon MCF 이행 수수료는 **재고 소유자=브랜드의 셀러 계정에서 자동 차감**된다(KLOW 엔 청구 안 됨 — KLOW 는 SP-API 사용료만 별도).
- 브랜드가 이 수수료를 **MCF마진에 미리 반영**해 값을 책정하므로, KLOW 는 실제 수수료를 **조회·보전하지 않는다** →
  `getFulfillmentPreview`/Finances API·**Finance and Accounting Role 불필요**(앱 등록 Role 은 Fulfillment + Inventory 만으로 충분).
- **`mcfChargeKrw` 는 분석용(옵션)** — 브랜드 MCF 수익성 분석에나 쓰고, money flow·정산과는 무관(없어도 됨).
- efs-billing 의 브랜드 청구 리포트는 여전히 **시딩 전용**(`order:{isSeeding:true}` + `paymentBy='brand'`) — MCF 와 무관.

## 9. 프론트 연결 (mock → real)

`klow_brand/src/lib/api.ts` 의 `api.amazon.*` 목업 함수 본문만 실제 엔드포인트로 교체:
| 목업 | 실제 |
|---|---|
| `connections()` | `GET /v1/brand/amazon/connections` |
| `inventory()` | `GET /v1/brand/amazon/inventory` |
| `mappings()` / `catalog()` | `GET /v1/brand/amazon/products` / `.../catalog` |
| `fulfillments()` | `GET /v1/brand/amazon/fulfillments` |
| (연결) | `GET /v1/brand/amazon/connect` (OAuth 리다이렉트) |
| (동기화) | `POST /v1/brand/amazon/sync` |
| (SKU 매핑) | `PUT /v1/brand/amazon/products/:productId/listing` |

타입(`api-types.ts`)·쿼리키(`query-keys.ts`)·컴포넌트는 그대로. `amazon-mock.ts` 는 제거.

## 10. 단계별 로드맵 (구현 체크리스트)

순서대로 진행. 각 단계 착수 전 **§13 불변식** 확인. "완료기준"을 만족해야 다음 단계로.

| # | 작업 | 상세 | 완료기준 (DoD) | 관련 불변식 |
|---|---|---|---|---|
| 1 | Prisma 모델 + 마이그레이션 | §1 | 신규 3모델 + `Shipment` 컬럼 생성, `efsServiceType`(및 `carrier`) nullable 화, 마이그레이션 커밋. `npx prisma generate` 통과 | F1 |
| 2 | `.env` 블록 + `amazon.module` 스캐폴딩 | §2, §3 | `amazon.module` 이 app.module 에 import 되고 앱이 부팅됨(빈 크레드=mock) | — |
| 3 | `AmazonSpApiClient`(mock 모드) + 토큰 교환·암복호화 | §3 | 빈 크레드→mock 응답, 크레드 있으면 `auth/o2/token` 으로 access token 발급 확인. 공유 crypto 유틸(`AMAZON_TOKEN_ENCRYPTION_KEY`) | — |
| 4 | OAuth 연결(connect/callback) + `BrandAmazonConnection` CRUD | §3 | 샌드박스는 env refresh token 으로 대체 가능; 프론트 ConnectModal → 실제 리다이렉트 | — |
| 5 | SKU 매핑 CRUD(`ProductAmazonListing`) + FBA 재고 동기화(수동→크론) | §6 | `POST /sync` 로 `FbaInventoryCache` 채워지고 `lastSyncedAt` 갱신 | — |
| 6 | `executeCreate` 라우팅 분기 + `createFulfillmentOrder`(mock) + EFS 폴백 + **채널별 정산가 세팅** | §4, §8-1 | mock e2e: 재고 있으면 `Shipment(channel=AMAZON_MCF, status=submitted)` + `ShipmentItem` 생성 + `settlementPriceKrw`=MCF 정산가; 재고 0 이면 EFS 폴백 + `settlementPriceKrw`=일반 정산가. 주문 status=shipped 전이 | **F2·F2b·F3·F4·F8·R5·R6·R7** |
| 7 | MCF 출고 추적 cron + 정산 delivered 게이트 확장 | §7, §8 | MCF 배송완료 행이 정산 후보에 뜨고 `settle()` 통과(candidate=settle 일치); 정산액이 채널별 정산가로 정확(같은 상품 EFS/MCF 브랜드 net 동일) | **F5·F7** |
| — | MCF 마진 트랙 UI: `ProductAmazonListing.mcfMarginKrw` 편집 + MCF 판매가 표시 선택 | §7, §9 | 브랜드/어드민이 MCF마진 조절 → MCF 판매가 미리보기; Amazon 적격 제품은 MCF 판매가 표시 | **F8** |
| 8 | 프론트 mock→real 배선 | §9 | `api.amazon.*` 5개 read 실 엔드포인트 연결, `amazon-mock.ts` 제거, UI 동작 동일 | — |
| 9 | dynamic sandbox 실검증 → 프로덕션 Role/신원확인 → 파일럿 브랜드 | §3, §11 | sandbox `createFulfillmentOrder`→`getFulfillmentOrder` 실호출; 프로덕션 Role 승인 후 파일럿 1개 브랜드 실출고 | — |
| — | **(v2)** 시딩 MCF | §5 | `SeedingLink` 선택 필드 productId 화 스키마 변경 후 §4 경로 재사용 | — |

## 11. 열린 질문 (피드백으로 확정)

- 도착국→마켓플레이스 판정: `ShippingCountry.amazonMarketplaceId` 신설 vs `ProductAmazonListing` 존재.
- **(확정) 앱 유형·Role**: 퍼블릭 솔루션 제공자 + Role = **아마존 주문 처리(Fulfillment Outbound) + 재고 및 주문 추적(FBA Inventory)**,
  제한 역할 미선택 (상세 sp-api §5).
- **RDT 요구 범위**: 어느 Fulfillment Outbound 오퍼레이션이 restricted(PII)인지 — Role Mappings 문서로
  확정(`createFulfillmentOrder` 는 불필요 예상, `getFulfillmentOrder` 응답 주소는 대상 가능).
- **(확정) MCF 가격·수수료 = 마진 트랙**: 판매가·정산가 채널별 2벌, MCF 정산가=`원가+MCF마진`(기본값 `마진+물류비/2`). Amazon 수수료는
  브랜드가 자기 계정서 부담(MCF마진에 반영) → KLOW 조회·보전 없음, Finance Role 불필요(§7·§8).
- **MCF 판매가 식 확정**: 기존 `product-selects.ts priceLine()`·÷0.95 PG·별도 배송비 라인과 대조 — 특히 **MCF 주문에서 배송비 라인을 0 으로 둘지**.
- **MCF마진 조절 granularity**: 전역 1개 vs 국가별(`ProductCountryPrice` 미러). 도메스틱이라 마켓플레이스=국가 → 마켓플레이스별이 자연.
- **표시가격·폴백 정책**: MCF 표시가로 결제 후 EFS 폴백 시 차액 KLOW 흡수(기본값 동일이면 무영향) — 정책 확정.
- **(확정) refresh token 암호화**: `totp-crypto.ts` 의 범용 encrypt/decrypt 를 공유 유틸로 추출하되 키는 **신규
  `AMAZON_TOKEN_ENCRYPTION_KEY`** 로 분리(ADMIN_TOTP 키와 독립 회전).
- 취소·환불 시 `cancelFulfillmentOrder` 연동 시점.
- (v2) 시딩 MCF 를 위한 `SeedingLink` 선택 필드 productId 화 설계.
- 파일럿 브랜드 재고 리전 확정(도메스틱 lane 성립 확인).

## 12. 검증

- **mock 모드**(빈 크레드) e2e: 결제→라우팅→합성 fulfillment order id→`Shipment(channel=AMAZON_MCF)`→
  정산 후보 노출. EFS 폴백(재고 0 케이스)도 확인. **아래 §13 불변식을 각 단계에서 함께 확인**.
- **정산 금액 검증(F8)**: MCF 발급 라인은 `settlementPriceKrw`=MCF 정산가, EFS 폴백 라인은 일반 정산가로 세팅됐는지. 기본값(MCF마진=마진+물류비/2)에서
  같은 상품을 MCF/EFS 로 보낸 브랜드 net·고객가가 **동일**한지, MCF마진을 조절하면 MCF 판매가만 독립적으로 바뀌는지 확인.
- **dynamic sandbox**: `createFulfillmentOrder`→`getFulfillmentOrder` 실호출 검증.
- 마이그레이션은 `npx prisma migrate dev` (interactive — 사용자 실행 요청).

## 13. 통합 플로우 점검 — "문서 코드를 현재 프로젝트에 적용했다고 가정" 한 계약·조인 불변식

구현 시 이 불변식이 하나라도 깨지면 mock 에서 컴파일/실행은 되어도 플로우가 조용히 멈춘다. 실측 코드 기준 체크리스트.
(**F**# = 문서 코드를 적용했다고 가정하고 플로우를 따라가 발견한 통합 결함, **R**# = 설계 리뷰 단계의 리스크. 본문 각 섹션에서 이 번호로 참조.)

| # | 불변식 | 깨질 때 증상 | 근거(실측) |
|---|---|---|---|
| F1 | MCF 행도 `carrier`/`efsServiceType`/`requestPayload` 를 채우거나 컬럼을 nullable 로 | MCF `Shipment` INSERT 실패 | 세 컬럼 non-null (schema Shipment) |
| F2 | MCF 경로도 `Shipment` + `ShipmentItem`(items.create) 생성, status=`submitted` | 주문이 shipped 로 안 넘어감 + 정산금 0 | `maybeMarkOrderShipped`·settlement 후보 쿼리가 `items→orderItem` 조인 (shipments.service:1003, settlement.service:63-68,97-105) |
| F2b | `executeCreate` 반환은 `{ shipment, warnings }` (void 아님) | 타입 에러 / 상위 `createForOrder` 집계 깨짐 | executeCreate 시그니처(:630-635) |
| F3 | 재발급 update 시 `channel` 세팅 + 반대 채널 컬럼 clear | 재발급 후 EFS/MCF 식별자 혼재 → 폴링·정산 오작동 | 재발급은 같은 row update(:678-698), 현재 efs 컬럼만 리셋 |
| F4 | 시딩 판정은 `order.isSeeding` 사용(seedingLink 조회 불필요) | 불필요 쿼리 / v1 시딩이 MCF 로 새어 실패 | `Order.isSeeding`(schema:513), loadOrderWithItems 가 order 전체 로드 |
| F5 | delivered 게이트는 `settleableDeliveredWhere(): Prisma.ShipmentWhereInput` 로 4곳 치환 | MCF 배송완료분이 정산 후보에서 누락 (candidate/settle 불일치) | 게이트가 Prisma where 인라인 4곳(settlement.service:100/193/298/328) |
| F7 | MCF 는 별도 폴링 cron (기존 EFS cron 이 `efsTrackingNumber:{not:null}` 로 자동 제외) | (양성) 확장 시 MCF 를 EFS 로 잘못 폴링하지 않도록 | refreshTrackingDue where(:611) |
| F8 | 발급 시 `OrderItem.settlementPriceKrw` 를 **실제 채널 정산가**로 세팅(MCF→MCF정산가=`원가+MCF마진`, EFS폴백→일반정산가) | MCF 표시가로 결제 후 EFS 폴백 시 물류비/2 이중지급·브랜드 정산 오류 | 정산가 채널별 2벌(§8-1), MCF마진(§1) |
| F9 | 한 MCF 주문 = **복수 패키지/추적번호 가능** → `amazonPackages Json?` 로 배열 저장, 종료판정은 전 패키지 delivered | "한 주문=한 추적번호" 가정 시 추적 누락·조기 배송완료 오판 | getFulfillmentOrder `fulfillmentShipments`/`packages`(§7·§1) |
| R5 | 모호 실패 시 `getFulfillmentOrder` 접수 확인 후 폴백 | Amazon+EFS 이중출고 | executeCreate try/catch(:718-749) |
| R6 | 라우팅 0단계 `order.countryCode==null → EFS` | legacy 주문에서 마켓플레이스 판정 NPE | countryCode nullable(schema:490) |
| R7 | Amazon 주소는 raw `order.*` (EFS sanitize/buildCityState 미적용) | 주소 훼손·city+state 병합 오배송 | payload-builder sanitize/buildCityState |

**트리거 경로 재확인(적용 가정)**: `payment.markPaid`(await, 에러 삼킴→미발급 큐) / `seeding.claim`(fire-and-forget) →
둘 다 `shipments.createForOrder(orderId, null)` → 그룹별 `executeCreate` → (신규) 채널 분기. 라우팅/발급 실패가 상위
결제·시딩 트랜잭션을 되돌리지 않는 것은 **현 구조가 이미 보장**(두 caller 모두 에러 삼킴) — MCF 분기도 이 안에서 EFS 폴백으로 흡수된다.
