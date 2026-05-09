# Payment Integration

> ⚠️ **결제 시스템 전환 중 — Eximbay 도입 예정.**
>
> 이전에는 PortOne V2 + NICE 채널을 사용했으나 2026-05 시점에 제거되었다.
> Eximbay 도입 후 본 문서를 다시 작성한다.

## 현재 상태

- `klow_server`에 `payment` 모듈이 없다. `/v1/payment/*` 와 `/webhooks/portone` 라우트는 존재하지 않는다.
- `klow_web` `/checkout` 페이지는 비활성화되어 있다 (Place Order 버튼 disabled). 사용자는 카트까지만 쓸 수 있다.
- `Order` 모델의 결제 필드(`paymentStatus`, `paymentMethod`, `pgProvider`, `pgTid`, `paidAt`, `cancelledAt`)와 `PaymentStatus` enum은 PG 독립적이라 그대로 유지된다. `prisma/migrations/20260505041632_add_payment_fields/`도 그대로다.
- 기존 `paid` 주문 환불 흐름(`OrdersService.cancelByUser` / `refundByAdmin`의 `paid` 분기)은 결제사 환불 호출 자리가 비어있어 `BadRequestException`을 던진다 — Eximbay 도입 후 복원.

## 다음 단계 (Eximbay 도입 시)

1. `klow_server/src/modules/payment/` 모듈을 다시 추가 (prepare/complete + webhook).
2. `klow_web/src/app/checkout/page.tsx`의 `handleSubmit`에 새 SDK 호출 + Place Order 버튼 활성화.
3. `OrdersService`의 paid 분기에 환불 호출 복원.
4. 본 문서를 Eximbay 기준으로 다시 쓴다.
