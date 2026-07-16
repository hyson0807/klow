# ① Amazon SP-API 지원 기능 조사 (MCF 관점)

> KLOW 의 유스케이스(**KLOW 에서 판 주문을 Amazon FBA 재고로 대신 출고**)에 실제로 필요한 API 만
> 집중 정리한다. Amazon 에 리스팅/판매하는 게 아니라 **출고만 위임**하는 것이므로, SP-API 의 상당 부분
> (Listings·Feeds·Orders·Catalog 등)은 이 유스케이스에 **불필요**하다.

## 0. 핵심 요약

- KLOW 가 필요로 하는 것은 사실상 **두 개의 API** 뿐이다:
  1. **Fulfillment Outbound API** — Amazon 창고에서 다른 채널 주문을 출고(= MCF). 이 기능의 심장.
  2. **FBA Inventory API** — 어느 SKU 에 재고가 얼마 있는지 조회(라우팅 판정용).
- 인증은 **LWA(Login with Amazon) 토큰 + Role** 중심. 2023-10-02 이후 AWS SigV4/IAM 불필요.
- **RDT(Restricted Data Token)** 는 Amazon 에서 PII 를 *읽어올 때* 쓰는 토큰이다. MCF 는 배송지를 KLOW 가
  *제공*하므로 `createFulfillmentOrder` 는 RDT 가 불필요할 가능성이 크고, 주소를 되돌려받는
  `getFulfillmentOrder` 쪽이 RDT/PII Role 대상일 수 있다 — **착수 시 확인**(아래 §5).
- **한국은 Amazon 마켓플레이스가 없다** — 다만 KLOW 타깃(미국·일본 등)은 지원 리전이라 문제없음.
- v1 은 **도메스틱 MCF**(재고국 == 도착국)만 다룬다. 크로스보더 MCF 는 제한적이라 범위 밖.

---

## 1. Fulfillment Outbound API (MCF 핵심)

Amazon FBA 재고로 **Amazon 외부 채널 주문을 출고**하는 API. KLOW 주문을 Amazon 이 고객에게 직접 발송한다.

| 오퍼레이션 | 용도 | KLOW 사용처 |
|---|---|---|
| `getFulfillmentPreview` | 출고 전 배송 가능 여부·예상 배송비·ETA·배송옵션 미리보기 | (선택) 결제 전/발급 전 사전검증·비용 파악 |
| `createFulfillmentOrder` | **출고 주문 생성 = Amazon 이 자동 발송 시작** | **송장 발급 지점** (executeCreate 분기) |
| `getFulfillmentOrder` | 출고 주문 상태·패키지·추적번호 조회 | 추적 갱신 크론 |
| `listAllFulfillmentOrders` | 출고 주문 목록/변경분 조회 | (선택) 재동기화 |
| `cancelFulfillmentOrder` | 출고 취소(발송 전) | 주문 취소·환불 연동 |
| `updateFulfillmentOrder` | 출고 주문 수정(발송 전) | (선택) |

### `createFulfillmentOrder` 주요 요청 필드
- `sellerFulfillmentOrderId` — **KLOW 측 유니크 ID**(멱등키). 예: `klow-{orderId}-{brandId}`.
- `displayableOrderId`, `displayableOrderDate`, `displayableOrderComment` — 패킹슬립 표시용.
- `shippingSpeedCategory` — `Standard` | `Expedited` | `Priority`.
- `destinationAddress` — 수취인 이름/주소/도시/주/우편번호/국가/전화. KLOW 가 값을 *제공*하므로 이 호출
  자체는 RDT 가 불필요할 가능성(§5 확인). **소스는 `Order` 인라인 컬럼 원본**(`fullName`/`addressLine1`/
  `addressLine2`/`city`/`recipientState`/`postalCode`/`countryCode`/`phone`/`email`) 그대로 —
  EFS payload-builder 의 `sanitize()`(`|{}"\r\n` strip)·길이컷·`buildCityState`(city+state 병합) 를 **거치지 않는다**.
  특히 EFS 용으로 병합된 city 문자열을 재사용하지 말 것.
- `items[]` — `{ sellerSku, sellerFulfillmentOrderItemId, quantity, perUnitDeclaredValue? }`.
- `fulfillmentAction` — `Ship`(즉시 출고) | `Hold`.
- `fulfillmentPolicy` — `FillOrKill`(재고 부족 시 전체 실패) | `FillAll` | `FillAllAvailable`.
  → KLOW 는 **브랜드 all-or-nothing** 이므로 `FillOrKill` 이 정책과 일치(부족하면 실패 → EFS 폴백).

### 패키징 (브랜드 중요)
- MCF 는 **비-Amazon(무지) 박스** 옵션 지원 — K뷰티 브랜드 경험상 Amazon 로고 박스가 아닌 blank-box
  로 나가도록 설정 필요. (계정/프로그램 설정 수준, API 페이로드에서 일부 제어)

### Sandbox
- Fulfillment Outbound 는 **dynamic sandbox** 지원 — 입력에 반응하는 상태성 응답. `createFulfillmentOrder`
  → `getFulfillmentOrder` 흐름을 실계정 없이 검증 가능. (restricted operation 은 production 에서 발급한
  RDT 를 sandbox 에 넘겨 시험)

---

## 2. FBA Inventory API (재고 동기화)

| 오퍼레이션 | 용도 |
|---|---|
| `getInventorySummaries` | SKU 별 재고 요약 — 가용(available)/예약(reserved)/입고예정(inbound). 전체 스냅샷·변경분·특정 SKU 조회 지원 |

- KLOW 는 이걸 **주기 동기화 크론**으로 호출해 `FbaInventoryCache` 를 채우고, 결제 시 라우팅 판정의
  1차 소스로 쓴다.
- **주의: 실시간이 아님** — Amazon 재고 반영에 지연이 있어 오버셀 가능. → 발급 시점 `createFulfillmentOrder`
  가 재고부족으로 실패할 수 있고, 그때 **EFS 자동 폴백**으로 흡수한다.

---

## 3. Notifications API (후속, 선택)

- `ORDER_CHANGE`, `FBA_INVENTORY_AVAILABILITY_CHANGES`, 출고/추적 이벤트 등을 SQS/EventBridge 로 수신.
- v1 은 폴링(크론)으로 충분. 규모가 커지면 재고 변경·출고 상태를 이벤트로 받아 GET 호출을 줄인다.

---

## 4. 이 유스케이스에 **불필요한** API (범위 축소 명시)

Amazon 에 상품을 등록/판매하는 게 아니라 **출고만 위임**하므로 아래는 쓰지 않는다:
- **Listings Items / Product Type Definitions / Feeds** — 리스팅 생성·대량 업로드용. 불요.
- **Orders API** — Amazon 마켓플레이스 주문 수집용. KLOW 주문은 KLOW DB 에 있으므로 불요.
- **Catalog Items** — Amazon 카탈로그 탐색용. 불요.
- **Finances API** — MCF 수수료 정밀 조회가 필요하면 참고(아래 6번). 필수 아님.

→ 덕분에 리스팅/피드 관련 무거운 컴플라이언스(레거시 feed 종료, 상품유형 스키마 검증 등)를 전부 회피.

---

## 5. 인증·권한 (klow_server 구현 반영)

- **LWA (Login with Amazon)**: 브랜드가 Seller Central OAuth 로 KLOW 앱에 권한 위임 → `refresh_token`
  발급. 런타임마다 `refresh_token` 으로 **access token(1시간 만료)** 을 발급받아 SP-API 호출.
  - app 레벨 크레드: `AMAZON_LWA_CLIENT_ID` / `AMAZON_LWA_CLIENT_SECRET` (env, 전 브랜드 공용).
  - per-brand: `refresh_token` → `BrandAmazonConnection` 에 **암호화 저장**.
- **앱 등록 (확정, 2026-07)**: KLOW 앱은 Solution Provider Portal 에 등록됨(앱 이름 `klow`, App ID `amzn1.sp.solution.*` = 샌드박스).
  - **조직 유형 = 퍼블릭 솔루션 제공자** — 여러 브랜드(셀링 파트너)가 각자 OAuth 로 승인하는 모델이라 Private(자체 계정) 아님.
    (퍼블릭이라도 앱스토어 공개 리스팅 없이 OAuth 동의 링크를 브랜드에 직접 배포 가능.)
  - **Role (확정)**: **아마존 주문 처리(Amazon Fulfillment)** = Fulfillment Outbound(MCF) + **재고 및 주문 추적(Inventory and Order Tracking)**
    = FBA Inventory. **제한(restricted) 역할은 선택하지 않음**(구매자 PII 부담 회피). 정확한 API↔Role 매핑은 공식 "Selling Partner API Roles" 로 최종 확인.
- **Role 승인**: SP-API 는 operation 별 Role 승인이 필요(없으면 403). 프로덕션 전환 = Solution Provider Portal 신원확인 + 위 Role 신청.
- **RDT (Restricted Data Token)**: Amazon 에서 **PII 를 읽어올 때** 필요한 토큰. MCF 에서 배송지는 KLOW 가
  넘겨주는 값이라 `createFulfillmentOrder` 는 **RDT 불필요 가능성**이 크다. 반대로 주소·수취인을 **응답으로
  돌려받는** `getFulfillmentOrder`(추적 갱신)는 restricted operation 으로 RDT/PII Role 이 걸릴 수 있다.
  → **어느 오퍼레이션이 restricted 인지 착수 시 Role Mappings 문서로 확정**하고, 필요한 것만 Tokens API 로
  RDT 발급.
- **재승인 주기**: refresh token 365일, client secret 180일. → 만료 시 브랜드 **재연결 필요**(목업의
  `재연결 필요` 상태가 이 케이스).
- AWS SigV4/IAM: **불필요**(2023-10-02 이후).

---

## 6. 비용·제한·컴플라이언스

- **레이트리밋**(토큰 버킷, 기본값 — 실제는 `x-amzn-RateLimit-Limit` 헤더 확인):
  - `getFulfillmentPreview` ≈ 2 rps / burst 30
  - `getFulfillmentOrder` ≈ 2 rps / burst 30
  - `getInventorySummaries` ≈ 2 rps / burst 2 (확인 필요)
  - `createFulfillmentOrder` — 문서값 **확인 필요**. burst 여유 크지 않으니 결제 시 1건씩 호출 + 실패
    재시도 backoff.
- **MCF 수수료 — 누가 내나 (중요)**: Amazon 이 출고 건당 MCF fulfillment fee 를 **재고 소유자=브랜드의 셀러 계정에서 차감**한다
  (KLOW 엔 청구 안 됨 — Amazon 공식. KLOW 는 SP-API 사용료만 별도 부담). KLOW 설계는 **마진 트랙** — 브랜드가 이 수수료를
  **MCF마진**에 미리 반영해 값을 잡으므로 **KLOW 가 실제 수수료를 조회·보전하지 않는다**(상세 flow §7·implementation-plan §8).
  → `getFulfillmentPreview`/Finances API 로 실비를 뽑을 필요 없음(원하면 분석용으로만). `mcfChargeKrw` 는 옵션.
- **2026 usage fee**: SP-API 사용료가 2026 발효 예정. Solution Provider Portal 에서 실제 과금 정책 확인 필요.
- **DPP/AUP 컴플라이언스**(PII 취급): 자격증명 안전 저장, 배송 후 30일 내 PII 삭제, 로그 12개월 보관,
  PII 로깅 금지, 취약점 스캔/침투테스트 등. → KLOW 는 배송지만 최소 전달하고 로깅 금지.

---

## 7. 마켓플레이스·리전

- 엔드포인트 3개 리전: **북미(na)** / **유럽(eu)** / **극동(fe)**. 리전 단위로 refresh token/엔드포인트가
  묶임 → **같은 리전 마켓플레이스는 한 계정으로 커버**(목업의 `바로 추가` 로직이 이걸 반영).
- 주요 marketplaceId (구현 시 상수 테이블 필요):
  - 미국 US `ATVPDKIKX0DER`, 일본 JP `A1VC38T7YXB528`, 캐나다 CA, 영국 GB, 독일 DE … (전체는 공식
    Marketplace IDs 문서 기준으로 `amazon-marketplaces.ts` 와 매핑).
- **한국 없음** — KLOW 는 외국인 대상이라 무관.

---

## 8. 공식 참고

- Fulfillment Outbound API / Use Case Guide
- FBA Inventory API (`getInventorySummaries`)
- Tokens API / Restricted Data Token
- Connect to the SP-API (LWA), Selling Partner API Roles
- Selling Partner API Sandbox (dynamic)
- Marketplace IDs, SP-API Endpoints
- Solution Provider Portal FAQ (usage fees)

> 근거 원문: 대화 초기의 SP-API 심층 조사 보고서(`~/Downloads/deep-research-report.md`) 기반으로 MCF
> 관점만 발췌·재구성. 세부 수치(레이트리밋·수수료)는 구현 착수 시 공식 문서로 재확인한다.
