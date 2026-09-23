# KLOW 워크스페이스 문서

KLOW K-beauty 플랫폼(5개 저장소: klow_server · klow_web · klow_admin · klow_brand · klow_search_server)의
크로스-레포 문서를 모아둔 곳이다. 저장소 하나에만 해당하는 문서는 각 저장소 안에 둔다
(예: `klow_web/docs/i18n.md`, `klow_search_server/docs/`).

> **작업을 시작하려면 [PROGRESS.md](./PROGRESS.md) 를 연다.** 진행 중인 단계, 다음에 할 일, 세션
> 절차가 전부 거기 있다. 새 세션에는 둘 중 한 줄만 보낸다.
>
> - 실행 — `docs/PROGRESS.md 를 읽고 다음 단계를 진행해 줘.`
> - 계획 — `docs/PROGRESS.md 를 읽고 <할 일>을 계획에 추가해 줘.`
>
> 계획 세션은 조사해서 단계로 쪼개고 `docs/<트랙>/` 폴더에 계획 문서를 쓰고 **멈춘다**(코드 변경
> 없음). 실행은 그다음 세션부터 한 세션에 한 단계씩.

## 문서 지도

**상태는 여기 적지 않는다.** 무엇이 어디까지 왔는지는 [PROGRESS.md](./PROGRESS.md) 가 유일한 정본이다.
이 표는 "이런 질문일 때 이 문서"라는 라우팅만 한다.

| 문서 | 이런 질문일 때 |
|------|----------------|
| [PROGRESS.md](./PROGRESS.md) | **지금 뭘 할 차례인가?** 진행 중인 단계, 세션 절차, 진입/퇴출 기준, 트랙별 다음 단계 |
| **[decisions/](./decisions/README.md)** | **과거 결정 71건의 본문 — 왜 이렇게 됐나, 되돌리면 뭐가 깨지나.** `CLAUDE.md` 의 `## 결정 기록` 색인에서 항목을 찾고 여기서 읽는다 — 코드를 건드리기 전에 그 주제 파일을 읽는다 |
| **[reference/](./reference/)** | **현행 시스템 — "지금 어떻게 동작하나"** |
| [reference/architecture.md](./reference/architecture.md) | 전체 구조가 어떻게 되나? 저장소·모듈·데이터 모델·URL surface·요청 흐름 |
| [reference/pricing-model.md](./reference/pricing-model.md) | 가격이 어떻게 계산되나? **판매가 고정 → 마진 역산**, 국가별 판매가/할인, USD/KRW 통화 규칙, 물류비 |
| [reference/payment-integration.md](./reference/payment-integration.md) | 고객 결제(Eximbay, USD)가 어떻게 흐르나? prepare→verify, 환불, 웹훅 |
| [reference/brand-subscription.md](./reference/brand-subscription.md) | 브랜드 구독 결제(NicePay 빌링, KRW)가 어떻게 되나? 빌키, 정기 청구, dunning, 노출 게이트 |
| [reference/instagram-integration.md](./reference/instagram-integration.md) | 브랜드 Instagram 연동(댓글→DM)을 어떻게 세팅하나? Meta 앱·토큰·private reply 제약 |
| [reference/preview-pages.md](./reference/preview-pages.md) | klow_web 디자인 프리뷰 화면은 어디에 있나? 결제 완료(`/checkout/preview`)·배송추적(`/track/preview`)·시딩(`/seed/preview*`) |
| [server/README.md](./server/README.md) | **API 엔드포인트 레퍼런스** — 모듈별 컨트롤러/가드/엔드포인트 (`server/modules/<module>.md`) |
| **[plan/](./plan/README.md)** | **아직 안 만들었거나 만드는 중인 것 — 상태는 [PROGRESS.md](./PROGRESS.md)** |
| [plan/custom-domain/](./plan/custom-domain/README.md) | 브랜드 커스텀 도메인(`shop.brandA.com`) — 둘러보기·담기는 그 도메인 / 로그인·결제는 klow.kr(**핸드오프**). 대행 구매(P6)와 배포 런북 포함 |
| [plan/mcf/](./plan/mcf/README.md) | Amazon MCF(멀티채널 풀필먼트) — Amazon FBA 재고로 KLOW 주문 자동 출고 |
| [plan/3pl-fulfillment/](./plan/3pl-fulfillment/implementation-plan.md) | 콜로세움 3PL — 브랜드가 창고에 맡긴 재고, 출고신청, 콜로세움 주문서 엑셀(API 가 없어 수작업 업로드) |
| [plan/cafe24-fulfillment/](./plan/cafe24-fulfillment/README.md) | 브랜드 카페24 자사몰 주문을 KLOW 로 불러와 콜로세움 3PL 로 출고 — OAuth 연결 · 상품 매핑 · 주문 미러 · 출고신청 전환 |
| [plan/aws-fargate/](./plan/aws-fargate/implementation-plan.md) | **klow_server 를 Railway 에서 AWS ECS Fargate 로 어떻게 옮기나?** Railway 전제로 맞춰진 함정(trust proxy·cron 이중 실행·리전·고정 IP), 0~6단계 순서 |
| [archive/](./archive/README.md) | 실행이 끝난 런북·마이그레이션 노트, 제거된 기능 문서, 배포 완료된 계획, 외부 제출 원고 — **현행 시스템 설명 아님** |
| [tools/linkcheck.py](./tools/linkcheck.py) | 문서를 옮긴 뒤 상대 링크·`#앵커` 가 깨지지 않았는지 — `python3 docs/tools/linkcheck.py` (인자 없으면 `docs/` + `CLAUDE.md`) |

## 규칙

- **작업 상태는 [PROGRESS.md](./PROGRESS.md) 한 곳에만 적는다.** 트랙 문서(`custom-domain/`, `mcf/` 등)는 **스펙**을 갖고, 제목·blockquote 에 "코드 완료"·"계획 수립 완료"·"문서 단계" 같은 **상태 문자열과 그 이모지를 넣지 않는다** — 제목은 다른 문서가 거는 앵커라서 상태가 바뀔 때마다 링크가 깨진다. `⚠️` `🔴` 같은 **위험 마커는 상태가 아니므로 그대로 쓴다.**
- **체크박스(`- [ ]`)는 한 세션 안에서 소비되는 절차(런북 실행 등)에만 쓴다.** 장기 상태에 쓰지 않는다 — 아무도 체크하지 않아 조용히 거짓이 된다.
- **server/** 는 klow_server 코드의 API 문서다 — 컨트롤러를 추가/변경하면 해당 `server/modules/<module>.md` 를 함께 갱신한다 (klow_server 저장소의 `docs/README.md` 는 이곳을 가리키는 포인터만 남아 있다).
- **계획 문서는 `plan/<트랙>/` 폴더 안에 쓴다.** 최상위에 평평하게 두지 않는다 — 트랙이 늘면 최상위가 다시 뒤섞인다.
- 구현이 끝난 계획은 `plan/` 을 떠난다. **현행 동작의 유일한 설명이면 `reference/`, 이미 `server/modules/` 등이 그 역할을 하면 `archive/`**([`plan/README.md`](./plan/README.md) 참고).
- 실행이 끝난 일회성 계획/정리 노트는 **archive/** 로 옮기고 상단에 📦 보관 배너를 단다.
- 워크스페이스 개발 규칙(포트, repo 독립성, Prisma 마이그레이션 규칙 등)은 [`../CLAUDE.md`](../CLAUDE.md) 참고.
