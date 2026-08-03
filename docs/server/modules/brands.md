# brands — 브랜드

- **모듈 경로**: `src/modules/brands/`
- **공개 필터**: `PUBLIC_BRAND_WHERE` = `Brand.status NOT IN (rejected, withdrawal_pending, withdrawn)` — 즉 `draft`/`pending`/`approved` 는 브랜드관 자체가 노출된다(탈퇴 신청 즉시 공개 surface 에서 제거). ⚠️ **제품 노출/판매 게이트는 이보다 엄격**해서 `Brand.status='approved'` + 구독 active 를 요구한다([products](./products.md) `PUBLIC_PRODUCT_WHERE`) — 두 필터를 혼동하지 말 것. 이미 fetch 한 row 검증용 JS 짝은 `isPublicBrand()`.
- **공통 select**: `brand-selects.ts` — `PUBLIC_BRAND_SELECT` 는 공개 노출 필드만 화이트리스트(`id`/`name`/`slug`/`tagline`/`description`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`logoLayout`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`/`order`/`status`/`createdAt`/`updatedAt`). 송화인·계좌·탈퇴 이력·`pgCustomerKey`·`category` 등 내부 필드는 공개 응답에 실리지 않는다.
- **다국어**: 공개 단건(`by-slug`/`:id`)만 `?lang=` 을 받아 `BrandTranslationService.localize()` 로 brand 텍스트를 로케일 번역한다(목록은 번역 없음).
- **관련 파일**: `brands.service.ts`, `admin-brands.controller.ts`, `public-brands.controller.ts`, `admin-brand-withdrawals.controller.ts`, `brand-withdrawals.service.ts`, `brand-translation.service.ts`(브랜드 텍스트 다국어 — [translation](./translation.md) 래퍼), `brand-selects.ts`

## admin-brands.controller.ts (`@Controller('admin/brands')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/brands`            | 브랜드/구독 통합 목록 → `{ data, total }`. `q`(name), `status`, `subStatus`(active/past_due/canceled/**none**=구독 없음), `take`(1~200, 기본 50)/`skip`. 각 행에 `subscription`(+`billingKey`) 과 `_count.products` 포함 (구 `/admin/brand-subscriptions` 목록 흡수) |
| GET    | `/admin/brands/:id`        | 브랜드 상세                                         |
| POST   | `/admin/brands`            | 브랜드 직접 생성                                    |
| PATCH  | `/admin/brands/:id`        | 브랜드 정보 수정                                    |
| DELETE | `/admin/brands/:id`        | 브랜드 삭제                                         |

## admin-brand-withdrawals.controller.ts (`@Controller('admin/brand-withdrawals')`)

> 전체 라우트 `AdminGuard`. 브랜드 탈퇴(철회) 처리 — 브랜드가 [brand-auth](./brand-auth.md) 의 `withdrawal-request` 로 `withdrawal_pending` 전환한 건을 어드민이 마무리한다.

| Method | Path                                 | 기능                                                          |
|--------|--------------------------------------|---------------------------------------------------------------|
| GET    | `/admin/brand-withdrawals`           | 탈퇴 요청 목록 → `{ items, total }`. `status`(`pending`\|`scheduled`\|`withdrawn`\|`all`, 그 외 값은 무시), `q` 검색, `take`(1~200, 기본 100)/`skip`. 각 행에 `submittedBy` + `_count{products, shipments, brandUsers}` + 미출고 송장 카운트 |
| GET    | `/admin/brand-withdrawals/:id`       | 탈퇴 요청 상세 (path 는 **brandId**). 탈퇴 대상 브랜드가 아니면 404 |
| POST   | `/admin/brand-withdrawals/:id/ready` | 해당 브랜드 정리 완료(ready) 표시 → 30일 뒤로 `withdrawalScheduledAt` 예약. `withdrawal_pending` 이 아니거나 이미 예약됐으면 400. 200 OK |
| POST   | `/admin/brand-withdrawals/process-due` | 예정일이 지난(due) 탈퇴 일괄 확정 (`withdrawn`). 200 OK        |

## public-brands.controller.ts (`@Controller('v1/brands')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/brands`               | 브랜드 목록 — **쿼리 파라미터 없음**(`publicOnly` 는 컨트롤러가 항상 true 로 고정). `order` asc → `createdAt` desc, 최대 200건 |
| GET    | `/v1/brands/by-slug/:slug` | 슬러그로 브랜드 조회 (`?lang=`). slug 는 trim+lowercase 정규화. 라우트 순서상 `:id` 보다 먼저 선언 |
| GET    | `/v1/brands/:id`           | 브랜드 ID 로 조회 (`?lang=`)                        |

> 공개 단건은 행을 찾아도 `isPublicBrand()` 를 통과하지 못하면 **404**(존재 여부를 흘리지 않음).

## 참고

- `Brand` 모델 주요 컬럼: `status`(draft/pending/approved/rejected/withdrawal_pending/withdrawn), `slug`(@unique, `klow.kr/{slug}`), `submittedById`, `submittedAt`, `approvedAt`, `approvedById`, `rejectionReason`, `pgCustomerKey`(@unique, 결제 준비 게이트), 브랜드관 표현(`logoLayout`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`), EFS 송화인(`senderName`/`senderAddress`/`senderPostalCode`/`senderPhone`), 정산 계좌(`bankName`/`bankAccountNumber`/`bankAccountHolder`), 탈퇴 이력(`withdrawalRequestedAt`/`withdrawalReadyAt`/`withdrawalScheduledAt`/`withdrawnAt`/`withdrawalProcessedAt` + 요청자·처리자 id·연락처).
- **`Brand.category` (2026-07-31)**: prisma enum `BrandCategory`(`cosmetics` | `dental_materials`), **nullable — `null` = 아직 안 고름**. 이 브랜드에서 나가는 **모든 송장(일반 주문 + 시딩)의 EFS 통관 분류(24-6)·HS 코드(24-8) 단일 출처**이고 제품별 오버라이드는 없다(`Product.hsCode` 등은 dormant). 값이 없으면 제품 생성이 거부된다(`assertBrandCategoryChosen` — [brand-applications](./brand-applications.md) 의 단건/일괄 초안 양쪽). 송장/시딩은 `null` 을 화장품으로 폴백. 편집은 어드민 브랜드 폼(`PATCH /admin/brands/:id`) 과 klow_brand 스튜디오.
- `PATCH /admin/brands/:id` 에 `name` 이 포함되면 트랜잭션으로 비정규화 캐시 `Product.brand` 를 일괄 갱신한다. `DELETE` 는 소속 제품의 `brandId` 를 먼저 `null` 로 떼어낸 뒤 삭제(제품은 남는다).
- ⚠️ `homepageUrl` / `targetCountries[]` 컬럼은 현재 스키마에 **없다**(과거 문서 잔재).
- 브랜드 입점 신청 워크플로우는 [brand-applications](./brand-applications.md), 승인/구독 게이트는 [subscription](./subscription.md) 참고.
