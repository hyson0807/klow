# plan/ — 계획 폴더

**아직 구현되지 않았거나 진행 중인 일**의 설계·구현 계획을 트랙별 폴더로 모은다.
**상태는 여기 적지 않는다** — 무엇이 어디까지 왔는지는 [`../PROGRESS.md`](../PROGRESS.md) 가
유일한 정본이다.

| 트랙 | 무엇인가 |
|------|----------|
| [custom-domain/](./custom-domain/README.md) | 브랜드가 자기 도메인(`shop.brandA.com`)으로 브랜드관을 연다. 둘러보기·담기는 그 도메인 / 로그인·결제는 klow.kr(**핸드오프**). `purchase-plan.md` 는 KLOW 가 도메인을 대신 사서 연 이용료를 받는 P6, `deploy-runbook.md` 는 운영 배포 절차 |
| [mcf/](./mcf/README.md) | Amazon MCF(멀티채널 풀필먼트) — 이미 Amazon FBA 창고에 재고를 둔 브랜드의 KLOW 주문을 Amazon 이 바로 출고 |
| [3pl-fulfillment/](./3pl-fulfillment/implementation-plan.md) | 콜로세움 3PL — 어드민이 브랜드별 재고를 입력하고, 브랜드가 출고신청하면 재고가 차감되고, 어드민이 콜로세움 주문서 엑셀을 받아 수작업 업로드한다 |
| [aws-fargate/](./aws-fargate/implementation-plan.md) | `klow_server` 를 Railway 에서 AWS ECS Fargate 로 이전. Railway 전제로 맞춰진 함정(trust proxy·cron 이중 실행·리전·고정 IP)과 0~6단계 순서 |

## 새 트랙을 만들 때

`PROGRESS.md` [§1 계획 세션](../PROGRESS.md#새-계획을-추가할-때--계획-세션) 절차를 따른다.
폴더 하나에 문서 셋이 기본형이다.

| 파일 | 역할 |
|------|------|
| `README.md` | 결정 요약 · 읽는 순서 · 각 문서의 정본 범위 |
| `flow.md` | 전체 흐름과 설계 논거 — "왜 이렇게 하나" |
| `implementation-plan.md` | **정본 — 실제 빌드 스펙.** 단계별 명세와 착수 게이트(불변식) |

작은 트랙은 `implementation-plan.md` 하나로 시작해도 되지만 **폴더는 만든다**(나중에 쪼갤 때
링크가 안 깨진다).

## 끝난 트랙은 어디로 가나

구현이 끝나면 그 폴더는 `plan/` 을 떠난다. 판정 기준은 **"이 문서가 현행 동작의 유일한 설명인가"** 다.

- **유일한 설명이면 → [`../reference/`](../reference/)** 로 옮긴다. 계획 서술(단계·PR 분할·배포
  순서)을 걷어내고 "지금 어떻게 동작하나"만 남긴다
- **`server/modules/` 나 다른 reference 문서가 이미 그 역할을 하면 → [`../archive/`](../archive/README.md)**
  로 옮기고 📦 배너 + 정본 포인터를 단다

⚠️ 정리하지 않은 계획서를 그대로 `reference/` 에 넣지 말 것 — 그 순간 "무엇을 만들 것인가"와
"무엇이 동작하는가"가 한 문서에 섞이고, 다음 사람이 계획 단계의 문장을 현행 사양으로 읽는다.
