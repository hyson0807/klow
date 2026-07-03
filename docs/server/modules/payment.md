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

## 환경변수

- `EXIMBAY_API_KEY` / `EXIMBAY_MID` / `EXIMBAY_RETURN_URL`
- `EXIMBAY_WEBHOOK_IPS` (CSV)
- `FRONTEND_URL` (verify 후 리다이렉트 base)

## PG 심사 안전망

- 약관 4종 동의 `Zod.literal(true)` + service 단 재가드.
- 동의 시각·IP·fxRate 모두 `Order` 에 저장.
- 이중언어 약관 페이지 `/legal/[slug]?lang=ko`.
