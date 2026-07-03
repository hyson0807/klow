# cart — 장바구니

- **모듈 경로**: `src/modules/cart/`
- **주 클라이언트**: `klow_web` (`useCartStore`)
- **데이터 모델**: `CartItem` (User-scoped)
- **관련 파일**: `cart.service.ts`, `public-cart.controller.ts`

## public-cart.controller.ts (`@Controller('v1/cart')`)

> 전체 라우트 `UserGuard`.

| Method | Path                       | 기능                                                                              |
|--------|----------------------------|-----------------------------------------------------------------------------------|
| GET    | `/v1/cart`                 | 내 장바구니 아이템 조회                                                           |
| POST   | `/v1/cart`                 | 상품 추가 또는 수량 변경 (upsert)                                                 |
| DELETE | `/v1/cart/:productId`      | 특정 상품 제거                                                                    |
| DELETE | `/v1/cart`                 | 장바구니 전체 비우기                                                              |
| PUT    | `/v1/cart/merge`           | 로컬(localStorage)→서버 병합 (수량 max-merge). 로그인 직후 `SessionSyncMount` 호출 |
