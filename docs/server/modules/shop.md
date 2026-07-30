# shop — 쇼핑 메타 (환율)

- **모듈 경로**: `src/modules/shop/`
- **목적**: 결제·가격 미리보기에 쓸 운영 환율 + 국가별 현지통화 노출.
- **관련 파일**: `shop.service.ts`, `public-shop.controller.ts`

## public-shop.controller.ts (`@Controller('v1/shop')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                              |
|--------|----------------------------|-------------------------------------------------------------------|
| GET    | `/v1/shop/fx-rate`         | 운영 환율 (KRW per USD, `CurrencyFxRate['KRW']`) — 주문 생성 시점 snapshot + 브랜드/어드민 입력 미리보기 환율의 단일 소스 |
| GET    | `/v1/shop/currency`        | 국가→현지통화(ISO 4217) 맵 + 통화별 환율(1 USD 당 현지통화). 현지통화 표시/입력용 (currency 모듈, `public-currency.controller.ts`) |

> **[2026-07 제거]** 구 `GET /v1/shop/price-preview`(정산가→노출가 미리보기)는 판매가 고정 모델
> 전환으로 삭제됨. 클라 입력 미리보기는 `/v1/shop/fx-rate` 환율 + `cost-pricing.ts` 미러로 대체.
>
> **[2026-07-30 제거]** `GET /v1/shop/today`(오늘의 픽)와 `admin-shop.controller.ts` 전체
> (`GET`/`PATCH /admin/shop/settings`)는 고정 고민 키워드 폐지와 함께 삭제됐다. 오늘의 픽은
> `ShopSettings.todaysPickConcern` 으로 제품을 골랐고, 어드민 설정 페이지의 유일한 필드가
> 그 값이었다. `ShopSettings` 모델 자체는 `dhlFuelSurchargeRate` 때문에 남아 있다.
