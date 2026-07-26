# payment — Eximbay 결제

- **모듈 경로**: `src/modules/payment/`
- **PG**: Eximbay (USD 결제)
- **흐름 요약**: `POST /v1/orders` (동의 + IP + fxRate snapshot) → `POST /v1/payment/prepare` → 클라 Eximbay JS SDK → `return_url 303` → `/checkout/redirect` → `POST /v1/payment/verify`
- **보강 경로**: `POST /webhooks/eximbay` (외부 IP 화이트리스트), `POST /v1/payment/report-failure` (pending→failed 멱등)
- **환불**: `payment.refundOrder` 가 `POST /v1/payments/{pgTid}/cancel` 호출
- **관련 파일**: `payment.service.ts`, `public-payment.controller.ts`, `webhook-payment.controller.ts`

## public-payment.controller.ts (`@Controller('v1/payment')`)

> 전체 라우트 `UserGuard`.

| Method | Path                              | 기능                                                                                       |
|--------|-----------------------------------|--------------------------------------------------------------------------------------------|
| POST   | `/v1/payment/prepare`             | 결제 준비 (동의 + ownership 재검증, Eximbay `fgkey` 등 발급, 클라 SDK 호출용 페이로드 반환)|
| POST   | `/v1/payment/verify`              | 결제 결과 검증 (Eximbay 재조회 + fxRateSnapshot 기준 금액 검증 + paymentStatus 멱등 전이)  |
| POST   | `/v1/payment/report-failure`      | 결제 실패 보고 (pending → failed 멱등 전이; 클라 SDK 실패 시 호출)                         |

## webhook-payment.controller.ts (`@Controller('webhooks')`)

| Method | Path                              | Guard                                       | 기능                                                  |
|--------|-----------------------------------|---------------------------------------------|-------------------------------------------------------|
| POST   | `/webhooks/eximbay`               | IP 화이트리스트 (`EXIMBAY_WEBHOOK_IPS`)     | Eximbay 비동기 알림. verify 누락 케이스 보강 처리     |

## 결제 완료(pending→paid) 부수효과

`markPaid()` 의 진짜 전이(`count === 1`) 분기에서만, 멱등하게 순차 실행 — 모두 실패 격리(에러가 결제 전이를 롤백하지 않음):

1. `clearCartItemsForOrder` — 주문에 포함된 카트 항목 서버측 삭제.
2. `sendOrderConfirmationSafe` — 구매자에게 주문 확인 이메일(Resend).
3. `createShipmentsForOrderSafe` — EFS 송장 자동 발급(onsite 제외).
4. `notifyBrandsOfPaidOrderSafe` — **주문에 담긴 제품의 브랜드(들)에게 "새 주문 접수" 카카오 알림톡**(onsite 제외). 브랜드가 스튜디오 주문현황 탭에서 발송처리를 놓치지 않도록. 브랜드 집합은 송장과 동일 규칙(productId→`Product.brandId`, 없으면 `OrderItem.brandId`), 수신번호는 `Brand.senderPhone` 우선·없으면 `BrandUser.phone` 폴백. 발송은 `KakaoService`(`auth/kakao.service.ts`) — 딥링크 `${BRAND_FRONTEND_URL}/studio?tab=orders&navTab=orders`. 알림톡 설정(`SOLAPI_KAKAO_PFID`/`SOLAPI_KAKAO_TEMPLATE_ORDER_PAID`)이 없으면 `[DEV kakao]` 콘솔 로그로 폴백.
5. `claimSeedingLinkSafe` — 유료 시딩 링크 pending→claimed.

## 환경변수

- `EXIMBAY_API_KEY` / `EXIMBAY_MID` / `EXIMBAY_RETURN_URL`
- `EXIMBAY_WEBHOOK_IPS` (CSV)
- `FRONTEND_URL` (verify 후 리다이렉트 base)
- `BRAND_FRONTEND_URL` (브랜드 알림톡 딥링크 base — 미설정 시 `http://localhost:3002`)
- `SOLAPI_KAKAO_PFID` / `SOLAPI_KAKAO_TEMPLATE_ORDER_PAID` (카카오 알림톡; 미설정 시 dev 콘솔 로그. 선행조건: 채널 심사 통과 + 발신프로필 + 템플릿 승인)

## PG 심사 안전망

- 약관 4종 동의 `Zod.literal(true)` + service 단 재가드.
- 동의 시각·IP·fxRate 모두 `Order` 에 저장.
- 이중언어 약관 페이지 `/legal/[slug]?lang=ko`.
