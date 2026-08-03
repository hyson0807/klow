# cart — 장바구니

- **모듈 경로**: `src/modules/cart/`
- **주 클라이언트**: `klow_web` (`useCartStore`)
- **데이터 모델**: `CartItem` (User-scoped)
- **관련 파일**: `cart.service.ts`, `public-cart.controller.ts`

## public-cart.controller.ts (`@Controller('v1/cart')`)

> 전체 라우트 `UserGuard`.

| Method | Path                       | Body / 응답                                                                       | 기능                                                                              |
|--------|----------------------------|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| GET    | `/v1/cart`                 | → `{ items: CartLine[] }`                                                         | 내 장바구니 아이템 조회 (생성순 asc)                                              |
| POST   | `/v1/cart`                 | `{ productId, quantity: 1~99 }` → `{ ok: true }`                                  | 상품 추가 또는 수량 변경 (upsert, 수량은 덮어쓰기)                                |
| DELETE | `/v1/cart/:productId`      | → `{ ok: true }`                                                                  | 특정 상품 제거 (없어도 성공 — 멱등)                                               |
| DELETE | `/v1/cart`                 | → `{ ok: true }`                                                                  | 장바구니 전체 비우기                                                              |
| PUT    | `/v1/cart/merge`           | `{ items: [...]≤100, removed?: string[]≤200 }` → `{ items: CartLine[] }`          | 로컬(localStorage)→서버 병합 (수량 max-merge). 로그인 직후 `SessionSyncMount` 호출 |

## 규칙

- **구매 게이트 재적용**: `POST /v1/cart` 는 제품이 없으면 404(`product not found`), 검수 중(pending)·미승인
  브랜드·판매가 미완성(`isPurchasable` 실패)이면 400(`이 제품은 아직 검수 중이라 장바구니에 담을 수 없어요`).
  UI 가드를 우회해도 여기서 막힌다.
- **브랜드당 최대 5개**(`MAX_ITEMS_PER_BRAND`): 같은 브랜드의 다른 카트 항목 수량 합 + 이번 수량이 5를 넘으면
  400(`한 브랜드당 최대 5개까지만 담을 수 있습니다`). 한 브랜드 = 한 EFS 송장(박스)이라 걸어둔 상한이고,
  legacy(`brandId` 없음) 제품은 면제.
- **merge 의 `removed`(삭제 묘비)**: 게스트 상태에서 지운 상품 id 를 같이 보내면 서버 카트에서도 삭제된다
  (max-merge 로 되살아나는 걸 막는다). `items` 에 같은 id 가 있으면 재담기로 보고 보존이 우선. `items` 가 비고
  `removed` 만 있어도 호출 가능. merge 는 `PURCHASABLE_PRODUCT_WHERE` 로 한 번 더 좁혀 담을 수 없는 제품을
  **조용히 필터링**한다(로그인 UX 가 400 으로 깨지지 않도록).
- **응답 `CartLine`**: `{ productId, quantity, name, brand, image, weightG, discount, customerPriceUsd,
  listPriceUsd, customerDiscountPercent }`. 가격은 storefront 와 동일한 `attachCustomerPricing` 으로
  **유저 프로필 국가** 기준 계산된다.
- ⚠️ `CartLine` 에 **`freeShipping` 은 의도적으로 없다** — 무료배송은 국가별(`ProductCountryPrice.freeShipping`)
  이고 배송비는 주문의 **배송지** 국가로 청구되므로, 프로필 국가로 계산한 값을 카트에 실으면 체크아웃과
  어긋난다. 배송비 금액·무료 여부의 정본은 [`POST /v1/orders/quote`](./orders.md) 뿐이다.
