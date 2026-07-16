# shop — 쇼핑 메타 (Today's Pick, 환율, 설정)

- **모듈 경로**: `src/modules/shop/`
- **목적**: 메인 쇼핑 화면용 큐레이션 + 결제 시 사용할 환율 노출 + 어드민용 쇼핑 설정.
- **관련 파일**: `shop.service.ts`, `admin-shop.controller.ts`, `public-shop.controller.ts`

## admin-shop.controller.ts (`@Controller('admin/shop')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/shop/settings`     | 쇼핑 설정 조회 (환율 정책, 큐레이션 등)             |
| PATCH  | `/admin/shop/settings`     | 쇼핑 설정 수정                                      |

## public-shop.controller.ts (`@Controller('v1/shop')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                              |
|--------|----------------------------|-------------------------------------------------------------------|
| GET    | `/v1/shop/today`           | 오늘의 추천 상품 (`PUBLIC_PRODUCT_WHERE`, 최대 50개)              |
| GET    | `/v1/shop/fx-rate`         | 운영 환율 (KRW per USD, `ShopSettings.usdKrwRate`) — 주문 생성 시점 snapshot + 브랜드/어드민 입력 미리보기 환율의 단일 소스 |
| GET    | `/v1/shop/currency`        | 국가→현지통화(ISO 4217) 맵 + 통화별 환율(1 USD 당 현지통화). 현지통화 표시/입력용 (currency 모듈, `public-currency.controller.ts`) |

> **[2026-07 제거]** 구 `GET /v1/shop/price-preview`(정산가→노출가 미리보기)는 판매가 고정 모델
> 전환으로 삭제됨. 클라 입력 미리보기는 `/v1/shop/fx-rate` 환율 + `cost-pricing.ts` 미러로 대체.
