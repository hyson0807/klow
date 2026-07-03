# brand-applications — 브랜드 입점 신청 + 셀프 상품 관리

- **모듈 경로**: `src/modules/brand-applications/`
- **주 클라이언트**: `klow_brand` (port 3002)
- **데이터 모델**: `Brand`(status draft/pending/approved/rejected/withdrawal_pending/withdrawn) + `Product`(status pending/approved/rejected)
- **자기 브랜드 연결**: `BrandUser.brandId` (승인 후에도 본인 상품 추가 가능; 추가 상품은 `pending` 으로 시작)
- **승인은 구독 게이트로 이관됨**: 결제 = 자동 승인 정책이라 **어드민 검수 큐가 없다**. 과거 `admin-brand-applications.controller.ts`(approve/reject/unapprove/product approve·reject) 는 제거되었고, 그 기능은 [subscription](./subscription.md) 의 `/admin/brand-subscriptions/*` 로 옮겨졌다. 이 모듈은 이제 **브랜드 셀프-서비스(공개) 컨트롤러만** 남았다.
- **입점 흐름**: studio OnboardingGate 에서 송화인 4 + 계좌 3 필드를 저장 → `submit-for-review` 가 `pgCustomerKey` 발급 → NicePay 포스타트 빌링 결제 → `approveApplication()` 자동 승인 (자세히는 [subscription](./subscription.md) + `../../../docs/brand-subscription.md`).
- **관련 파일**: `brand-applications.service.ts`, `public-brand-applications.controller.ts`, `draft-brand.ts`(공통 draft 데이터·P2002 매핑)

## public-brand-applications.controller.ts (`@Controller('v1/brand')`)

> 전체 라우트 `BrandGuard` (자기 brandId scope).

### 입점 신청 (Brand)

| Method | Path                                          | 기능                                                              |
|--------|-----------------------------------------------|-------------------------------------------------------------------|
| POST   | `/v1/brand/applications`                      | 신청 제출 (단일 step submit)                                      |
| PUT    | `/v1/brand/applications`                      | 신청 내용 수정                                                    |
| GET    | `/v1/brand/applications/me`                   | 내 신청 조회 (홈페이지/타겟국가/송화인/계좌 등 포함)              |
| POST   | `/v1/brand/applications/init-draft`           | 드래프트 생성 (슬러그 기반 — 가입 시 brand 미생성 케이스 안전망, idempotent) |
| POST   | `/v1/brand/applications/submit-for-review`    | 드래프트 → 검토 제출 (모든 필드 완성 확인, `pgCustomerKey` 발급)  |
| PATCH  | `/v1/brand/applications/operational-profile`  | 운영 프로필(송화인 4 + 계좌 3 필드) 저장 — OnboardingGate         |

### 셀프 상품 관리 (Product)

| Method | Path                              | 기능                                                              |
|--------|-----------------------------------|-------------------------------------------------------------------|
| POST   | `/v1/brand/products`              | 상품 생성 (신청 진행 중 또는 승인 후 모두 `pending` 으로 시작)    |
| POST   | `/v1/brand/products/bulk`         | 상품 일괄 생성 (draft 다건)                                       |
| GET    | `/v1/brand/products`              | 내 브랜드 상품 목록                                               |
| PATCH  | `/v1/brand/products/reorder`      | 상품 노출 순서 변경 (드래그&드롭)                                 |
| PATCH  | `/v1/brand/products/:id/hidden`   | 상품 가리기 On/Off 토글 (`Product.hidden`, status 유지·노출/판매만 제외; 단일 필드 전용 PATCH, `:id` 위에 선언) |
| PATCH  | `/v1/brand/products/:id`          | 상품 수정 (자기 brandId 확인)                                     |
| DELETE | `/v1/brand/products/:id`          | 상품 삭제                                                         |

## 참고

- 추가 정보: 송화인, 정산 계좌 정보 등은 `operational-profile` 로 저장.
- 승인/거부/제품 단위 승인·차단·환불은 모두 [subscription](./subscription.md) 의 어드민 `/admin/brand-subscriptions/*` 에서 처리한다.
- 브랜드 탈퇴(철회)는 [brand-auth](./brand-auth.md) `withdrawal-request` + 어드민 [brands](./brands.md) `brand-withdrawals` 참고.
