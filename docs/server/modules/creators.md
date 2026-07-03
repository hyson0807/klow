# creators — 크리에이터

- **모듈 경로**: `src/modules/creators/`
- **관련 파일**: `creators.service.ts`, `admin-creators.controller.ts`, `public-creators.controller.ts`

## admin-creators.controller.ts (`@Controller('admin/creators')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/creators`          | 크리에이터 목록                                     |
| GET    | `/admin/creators/:id`      | 크리에이터 상세                                     |
| POST   | `/admin/creators`          | 크리에이터 생성                                     |
| PATCH  | `/admin/creators/:id`      | 크리에이터 수정                                     |
| DELETE | `/admin/creators/:id`      | 크리에이터 삭제                                     |

## public-creators.controller.ts (`@Controller('v1/creators')`)

> 전체 라우트 public.

| Method | Path                              | 기능                                                              |
|--------|-----------------------------------|-------------------------------------------------------------------|
| GET    | `/v1/creators`                    | 크리에이터 목록                                                   |
| GET    | `/v1/creators/:id/products`       | 크리에이터의 연관 상품 목록 (`PUBLIC_PRODUCT_WHERE` 적용)         |
| GET    | `/v1/creators/:id`                | 크리에이터 상세                                                   |
