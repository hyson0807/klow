# orders — 주문

- **모듈 경로**: `src/modules/orders/`
- **결제 통화**: USD
- **주문 생성 시 저장**: 약관동의(4종) + IP + `fxRateSnapshot` (결제 시점 환율 고정용). 라인 단가·정산가·원가는
  `OrderItem`에 주문 시점 스냅샷(`unitPriceUsd`/`settlementPriceKrw`/`costKrw`). 가격은 표시·견적과 동일한 `priceLine` 사용.
- **과청구 가드**: 현지통화 핀(`priceLocal`) 상품인데 목적국 통화의 유효 환율이 없으면 `OrdersService.billingRate`가
  주문/견적을 차단한다(1로 폴백해 현지가를 USD로 오인 → 과청구하는 사고 방지). 핀 없는 상품은 영향 없음. 자세히는 [`../../pricing-model.md`](../../pricing-model.md).
- **상태 흐름**: `pending → paid → fulfilled / cancelled / refunded`
- **관련 파일**: `orders.service.ts`, `admin-orders.controller.ts`, `public-orders.controller.ts`, `guest-order-token.ts`(비회원 주문 HMAC 토큰)

## admin-orders.controller.ts (`@Controller('admin/orders')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                          | 기능                                                |
|--------|-------------------------------|-----------------------------------------------------|
| GET    | `/admin/orders`               | 주문 목록 (`status`, `paymentStatus` 필터, 페이지) |
| GET    | `/admin/orders/:id`           | 주문 상세                                           |
| PATCH  | `/admin/orders/:id/status`    | 주문 상태 변경 (fulfillment 흐름)                   |
| PATCH  | `/admin/orders/:id/refund`    | 환불 처리 (Eximbay cancel API 호출 포함)            |

## public-orders.controller.ts (`@Controller('v1/orders')`)

> 가드는 라우트별 상이 — 회원 전용은 `UserGuard`, 회원/비회원 공용은 `OptionalUserGuard`, 비회원 흐름은 public + `THROTTLE_TIGHT`.

| Method | Path                                | Guard            | 기능                                                                          |
|--------|-------------------------------------|------------------|-------------------------------------------------------------------------------|
| POST   | `/v1/orders`                        | OptionalUser     | 주문 생성 (약관 4종 동의 + IP + fxRateSnapshot 저장, `Zod literal(true)` 검증). 비회원이면 `userId=null` + 해당 주문 한정 HMAC 게스트 쿠키 발급 |
| POST   | `/v1/orders/quote`                  | public           | 결제 전 가격 견적 — 목적국 기준 라인 단가/배송비/합계(read-only). 주문 생성과 **동일 `priceLine`** 이라 견적가 == 청구가. 배송 불가면 `shippable:false` |
| GET    | `/v1/orders/mine`                   | User             | 내 주문 목록                                                                  |
| POST   | `/v1/orders/lookup`                 | public (TIGHT)   | 비회원 주문 조회 — `orderId`(cuid) + `email` 매칭                              |
| POST   | `/v1/orders/guest-cancel/request-otp` | public (TIGHT) | 비회원 취소 1단계 — 주문/이메일 매칭 시에만 OTP 발송. 응답은 항상 `{ ok: true }`(존재 oracle 차단) |
| POST   | `/v1/orders/guest-cancel`           | public (TIGHT)   | 비회원 취소 2단계 — 주문 바인딩 OTP 검증 후 취소/환불                          |
| GET    | `/v1/orders/:id/tracking`           | OptionalUser     | 고객용 배송추적 — 결제완료 메일 서명 토큰(`?t=`) / 회원 세션 / 게스트 쿠키 중 하나로 인증, 캐시된 추적 데이터 반환 |
| GET    | `/v1/orders/:id`                    | User             | 주문 상세 (본인 ownership 확인)                                               |
| PATCH  | `/v1/orders/:id/cancel`             | User             | 주문 취소 (결제 전 / 결제 후 분기)                                            |

## 참고

- 결제 흐름 전체는 [payment](./payment.md) 참고. 게스트(비회원) 주문은 `guest-order-token.ts` 의 HMAC 토큰 쿠키로 `prepare`/`report-failure` 를 인증한다.
- 배송 송장/추적 발급은 [shipments](./shipments.md) 참고.
- 약관 동의 텍스트는 `/legal/[slug]?lang=ko` (이중언어 약관) 에서 제공.
