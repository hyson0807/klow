# Payment Integration Plan

PG사 심사 통과 + 실제 결제 도입을 위해 각 레포에 추가/수정해야 할 항목과 결제 플로우를 큰 그림으로 정리한 문서. 세부 코드 설계는 진행하면서 PR 단위로 추가한다.

- **PG사:** 포트원(PortOne) V2
- **결제 수단:** 카드(필수, 카드사 심사 대상) · 카카오페이 · 네이버페이 등 포트원 채널로 추가
- **통화:** KRW
- **현재 상태:** `/v1/orders` MVP만 구축. 결제창 호출 자체가 코드에 없음 → 카드사 심사 차단 사유

---

## 1. 프론트 (klow_web)

### 추가
- 포트원 브라우저 SDK 설치 (`@portone/browser-sdk`)
- 결제 결과 페이지 — 성공 / 실패 / 대기 상태별 분기

### 수정
- **`/checkout` 결제 흐름 교체** — "Place order" 클릭 시 다음 4단계로 변경:
  1. `POST /v1/orders` — 주문 생성
  2. `POST /v1/payment/prepare` — 서버에서 결제 세션·금액 받기
  3. 포트원 SDK로 결제창 호출 → 카드 결제
  4. `POST /v1/payment/verify` — 서버에서 PG 거래 조회·금액 검증 후 paid 처리
- **`/orders/[id]`** — 결제 상태(`paymentStatus`) 뱃지, 결제 수단·결제 시각 표시
- **`/orders` (목록)** — 결제 상태 뱃지

### 그대로 둠
- 푸터 사업자정보, 상품 상세 환불·배송 카드, 약관 동의 4종, FAQ — 이미 PG 심사 표시 요건 충족

---

## 2. 어드민 (klow_admin)

### 추가
- 주문 상세에 **PG 결제 정보 패널** — `paymentStatus`, `paymentMethod`, `pgProvider`, `pgTid`, `paidAt`
- **환불 트리거 버튼** — `paid` 주문에 대해 운영자가 직접 환불 (사용자 취소 외 케이스)
  - 클릭 시 어드민 API → 서버가 포트원 환불 호출 → `refunded` 전이

### 수정
- 주문 목록 테이블에 **결제 상태 컬럼** 추가
- 주문 상세 상태 전이 UI에 결제 정보가 자연스럽게 흐르도록 정렬

---

## 3. 서버 (klow_server)

### 추가
- **`Order` 결제 필드 마이그레이션** (`prisma migrate dev --name add-payment-fields`, 사용자 직접 실행)
  - `paymentStatus` enum: `pending | paid | failed | cancelled | refunded`
  - `paymentMethod`, `pgProvider`, `pgTid @unique`, `paidAt`, `cancelledAt`
- **`payment/` 모듈 신설** — 엔드포인트 3개
  - `POST /v1/payment/prepare` — 주문 ID로 정확한 금액 조회·`paymentId` 발급
  - `POST /v1/payment/verify` — 클라이언트가 결제 완료 후 호출. **서버가 포트원 REST로 직접 조회해 금액 일치 검증** 후 `paid` 전이
  - `POST /webhooks/portone` — 서명 검증·멱등성. `verify` 보강용 (네트워크 끊김 등 대비)
- 환경 변수 — `PORTONE_API_SECRET`, `PORTONE_CHANNEL_KEY`, `PORTONE_WEBHOOK_SECRET`

### 수정
- **`orders.service.ts:cancel`** 보강 — `paymentStatus = paid`이면 포트원 환불 API 호출 후 `refunded`로 전이. `pending`은 기존대로 단순 상태 변경
- 어드민 환불 API — 위 cancel 로직 재사용 + 운영자 사유 필드

### 그대로 둠
- 기존 `/v1/orders` 계약은 손대지 않는다 (생성·조회·취소 인터페이스 유지). `payment/`가 그 위에 얹히는 구조

---

## 4. 결제 플로우

```
[사용자]                [klow_web]              [klow_server]              [포트원]
                            │
   ① "Place order" 클릭 ──▶ │
                            │
                            ├─ POST /v1/orders ───────────▶ Order 생성
                            │                              (status=pending,
                            │                               paymentStatus=pending)
                            │◀─────── { orderId } ─────────┤
                            │
                            ├─ POST /v1/payment/prepare ──▶ Order 금액 조회
                            │                              paymentId 발급
                            │◀── { paymentId, amount, ─────┤
                            │     channelKey }
                            │
                            ├─ PortOne.requestPayment() ─────────────────────▶ 결제창
   ② 카드/카카오페이 결제 ────────────────────────────────────────────────▶ 표시
                            │◀────────── 성공 콜백 ──────────────────────────┤
                            │
                            ├─ POST /v1/payment/verify ──▶ 포트원 REST 조회 ─▶ GET /payments/{id}
                            │                             ↓                  ◀┤
                            │                             서버 보유 금액 ===
                            │                             PG 응답 금액?
                            │                              ├ 같음: paid 전이
                            │                              └ 다름: 환불 + failed
                            │◀──── { status: 'paid' } ────┤
                            │
   ③ 주문 완료 페이지 ─────◀
                                                          ▲
                                                          │ ④ (비동기 보강)
                                                          │   webhook 멱등 처리
                                                          ◀──────────────────┤
```

### 상태 전이

| Order.status | paymentStatus | 의미 |
|---|---|---|
| pending | pending | 주문 생성, 결제 시도 전 (현재 MVP 종착점) |
| pending | paid | 결제 완료, 운영자 출고 준비 시작 |
| processing → shipped → completed | paid | 정상 진행 |
| cancelled | cancelled | paid 이전 단계에서 취소 |
| cancelled | refunded | paid 이후 환불 완료 |

### 핵심 원칙 (구현 시 절대 지킬 것)

1. **금액은 서버가 진실** — 클라이언트가 보낸 금액을 신뢰하지 않는다. `prepare`·`verify` 모두 `Order` DB값을 기준으로 검증
2. **`verify`에서 PG에 직접 조회** — 클라이언트의 "성공" 응답만 믿지 말고 서버가 포트원 REST로 한 번 더 확인
3. **웹훅은 보강용** — `verify`가 메인 경로. 웹훅은 멱등 처리 (이미 paid면 skip)
4. **취소·환불은 서버 → PG** — 클라이언트가 직접 PG 호출 금지. 항상 `PATCH /v1/orders/:id/cancel` → 서버가 PG 환불

---

## 작업 순서 권장

1. 포트원 가입 + 채널·키 발급 (외부 절차) — 모든 작업의 전제
2. 서버 `Order` 마이그레이션 + `payment/` 모듈 (백엔드 골조)
3. 프론트 `/checkout` 흐름 교체 + 결과 페이지 (사용자 흐름 완성 → 카드사 심사 가능)
4. 어드민 결제 패널 + 환불 버튼 (운영 가시성)
5. 운영 DB 점검 (실물 공개 상품 3개 이상, TEST·0원 제거)
6. 실 도메인 배포 + 카드사 심사 신청
