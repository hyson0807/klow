# KLOW 워크스페이스 문서

KLOW K-beauty 플랫폼(5개 저장소: klow_server · klow_web · klow_admin · klow_brand · klow_search_server)의
크로스-레포 문서를 모아둔 곳이다. 저장소 하나에만 해당하는 문서는 각 저장소 안에 둔다
(예: `klow_web/docs/i18n.md`, `klow_search_server/docs/`).

## 문서 지도

| 문서 | 이런 질문일 때 |
|------|----------------|
| [architecture.md](./architecture.md) | 전체 구조가 어떻게 되나? 저장소·모듈·데이터 모델·URL surface·요청 흐름 |
| [server/README.md](./server/README.md) | **API 엔드포인트 레퍼런스** — 모듈별 컨트롤러/가드/엔드포인트 (`server/modules/<module>.md`) |
| [pricing-model.md](./pricing-model.md) | 가격이 어떻게 계산되나? 원가+마진, 국가별 마진/할인, USD/KRW 통화 규칙, 물류비 |
| [payment-integration.md](./payment-integration.md) | 고객 결제(Eximbay, USD)가 어떻게 흐르나? prepare→verify, 환불, 웹훅 |
| [brand-subscription.md](./brand-subscription.md) | 브랜드 구독 결제(NicePay 빌링, KRW)가 어떻게 되나? 빌키, 정기 청구, dunning, 노출 게이트 |
| [concern-matching.md](./concern-matching.md) | 피부 고민 키워드가 추천에 어떻게 반영되나? CONCERN_EXPANSION, 스코어링 |
| [archive/](./archive/README.md) | 완료된 마이그레이션/정리 노트, 스크래치 — **현행 시스템 설명 아님** |

## 규칙

- **server/** 는 klow_server 코드의 API 문서다 — 컨트롤러를 추가/변경하면 해당 `server/modules/<module>.md` 를 함께 갱신한다 (klow_server 저장소의 `docs/README.md` 는 이곳을 가리키는 포인터만 남아 있다).
- 실행이 끝난 일회성 계획/정리 노트는 **archive/** 로 옮기고 상단에 보관 배너를 단다.
- 워크스페이스 개발 규칙(포트, repo 독립성, Prisma 마이그레이션 규칙 등)은 [`../CLAUDE.md`](../CLAUDE.md) 참고.
