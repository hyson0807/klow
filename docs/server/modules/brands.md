# brands — 브랜드

- **모듈 경로**: `src/modules/brands/`
- **공개 필터**: `Brand.status='approved'` 인 브랜드만 노출 (옵션 `publicOnly`).
- **공통 select**: `brand-selects.ts`
- **관련 파일**: `brands.service.ts`, `admin-brands.controller.ts`, `public-brands.controller.ts`, `admin-brand-withdrawals.controller.ts`, `brand-withdrawals.service.ts`, `brand-translation.service.ts`(브랜드 텍스트 다국어 — [translation](./translation.md) 래퍼), `brand-selects.ts`

## admin-brands.controller.ts (`@Controller('admin/brands')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/brands`            | 브랜드 목록 (옵션: `q` 검색)                        |
| GET    | `/admin/brands/:id`        | 브랜드 상세                                         |
| POST   | `/admin/brands`            | 브랜드 직접 생성                                    |
| PATCH  | `/admin/brands/:id`        | 브랜드 정보 수정                                    |
| DELETE | `/admin/brands/:id`        | 브랜드 삭제                                         |

## admin-brand-withdrawals.controller.ts (`@Controller('admin/brand-withdrawals')`)

> 전체 라우트 `AdminGuard`. 브랜드 탈퇴(철회) 처리 — 브랜드가 [brand-auth](./brand-auth.md) 의 `withdrawal-request` 로 `withdrawal_pending` 전환한 건을 어드민이 마무리한다.

| Method | Path                                 | 기능                                                          |
|--------|--------------------------------------|---------------------------------------------------------------|
| GET    | `/admin/brand-withdrawals`           | 탈퇴 요청 목록 (`status` 필터, `q` 검색, 페이지)              |
| GET    | `/admin/brand-withdrawals/:id`       | 탈퇴 요청 상세 (brandId)                                      |
| POST   | `/admin/brand-withdrawals/:id/ready` | 해당 브랜드 탈퇴 처리 준비(ready) 표시                        |
| POST   | `/admin/brand-withdrawals/process-due` | 처리 예정(due) 탈퇴 일괄 확정 (`withdrawn`)                 |

## public-brands.controller.ts (`@Controller('v1/brands')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/brands`               | 브랜드 목록 (`publicOnly` 필터)                     |
| GET    | `/v1/brands/by-slug/:slug` | 슬러그로 브랜드 조회 (라우트 순서상 `:id` 보다 먼저) |
| GET    | `/v1/brands/:id`           | 브랜드 ID 로 조회                                   |

## 참고

- `Brand` 모델 컬럼: `status` (draft/pending/approved/rejected/withdrawal_pending/withdrawn), `homepageUrl`, `targetCountries[]`, `submittedById`, `submittedAt`, `approvedAt`, `approvedById`, `rejectionReason`, `pgCustomerKey`(결제 준비 게이트).
- 브랜드 입점 신청 워크플로우는 [brand-applications](./brand-applications.md), 승인/구독 게이트는 [subscription](./subscription.md) 참고.
