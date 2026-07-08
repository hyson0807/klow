# Amazon MCF (멀티채널 풀필먼트) 통합 문서

KLOW 입점 브랜드 중 **이미 Amazon FBA 창고에 재고를 둔 브랜드**의 KLOW 주문·시딩을, 브랜드가 EFS
창고로 택배를 보내는 대신 **Amazon 창고에서 고객에게 바로 출고**(Amazon MCF, Multi-Channel
Fulfillment)되게 하는 기능의 설계·구현 문서 모음.

> **현재 상태: 📄 문서 단계.** klow_brand 의 `Amazon 창고` 페이지는 목업(프론트)까지 완성됐고, 백엔드
> 실동작은 아직 미구현이다. 이 문서들을 피드백으로 다듬은 뒤 klow_server 구현에 착수한다.

## 목표 동작 (한 줄)

주문/시딩 **결제가 확정되면 → 도착국 Amazon 창고에 그 제품 재고가 있으면 Amazon 송장 발급(=Amazon 이
자동 출고), 없으면 기존 EFS 송장**.

## 문서

| 문서 | 내용 |
|---|---|
| [`sp-api-capabilities.md`](./sp-api-capabilities.md) | Amazon SP-API 가 지원하는 기능 조사 — MCF 에 실제로 필요한 API 범위·인증·제약·비용 |
| [`implementation-plan.md`](./implementation-plan.md) | 실제 구현 계획(living doc) — 데이터 모델·발급 분기·동기화·정산·단계별 로드맵 |
| [`flow.md`](./flow.md) | 전체 Amazon 플로우 — 연결→동기화→결제→발급→출고→추적→정산 (시퀀스 다이어그램) |

## 확정된 핵심 결정 (2026-07-08)

| 항목 | 결정 |
|---|---|
| 아키텍처 | **klow_server 내부 모듈** `src/modules/amazon/` (별도 마이크로서비스 아님) |
| 혼합 주문 | **브랜드 단위 all-or-nothing** — 브랜드 라인 중 하나라도 재고 부족 시 그 브랜드 전체 EFS |
| 배송 범위(v1) | **도메스틱 MCF 만** — 도착국 == Amazon 마켓플레이스 창고국 (크로스보더 미시도) |
| 시딩 | **v1 에서 Amazon 라우팅 지원** — 시딩 라인에 productId 배선 |
| 고객 결제가 | **변동 없음** — MCF 는 내부 출고비용 라인만 바꿈, 고객가는 EFS 와 동일 |
| refresh token | **암호화 저장** (Admin TOTP AES-256-GCM 선례) |
| 정산 | MCF 출고분도 `Shipment` 정산 후보 포함, MCF 종료상태 매핑 + `mcfFeeKrw` 필드 |
| 재고 판정 | 동기화 캐시 1차 판정 + `createFulfillmentOrder` 실패 시 EFS 자동 폴백 |

## 관련 코드 (현재)

- 프론트 목업: `klow_brand/src/app/(authed)/amazon/`, `klow_brand/src/lib/amazon-mock.ts`,
  `amazon-marketplaces.ts`
- 발급 엔진(분기 지점): `klow_server/src/modules/shipments/shipments.service.ts` `executeCreate`
- 결제/시딩 트리거: `klow_server/src/modules/payment/payment.service.ts` `markPaid`,
  `klow_server/src/modules/seeding/seeding.service.ts` `claim`
