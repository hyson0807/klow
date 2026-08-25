# KLOW 워크스페이스 문서

KLOW K-beauty 플랫폼(5개 저장소: klow_server · klow_web · klow_admin · klow_brand · klow_search_server)의
크로스-레포 문서를 모아둔 곳이다. 저장소 하나에만 해당하는 문서는 각 저장소 안에 둔다
(예: `klow_web/docs/i18n.md`, `klow_search_server/docs/`).

## 문서 지도

| 문서 | 이런 질문일 때 |
|------|----------------|
| [architecture.md](./architecture.md) | 전체 구조가 어떻게 되나? 저장소·모듈·데이터 모델·URL surface·요청 흐름 |
| [server/README.md](./server/README.md) | **API 엔드포인트 레퍼런스** — 모듈별 컨트롤러/가드/엔드포인트 (`server/modules/<module>.md`) |
| [pricing-model.md](./pricing-model.md) | 가격이 어떻게 계산되나? **판매가 고정 → 마진 역산**, 국가별 판매가/할인, USD/KRW 통화 규칙, 물류비 |
| [deploy-drop-logistics-markup-runbook.md](./deploy-drop-logistics-markup-runbook.md) | **판매가 물류비 분리 + 무료배송 릴리스를 prod 에 어떻게 올리나?** 마이그레이션 → 백필 → 배포 순서, 스모크, 사전 공지 |
| [deploy-free-text-product-tags-runbook.md](./deploy-free-text-product-tags-runbook.md) | **제품 태그 자유 텍스트 전환을 prod 에 어떻게 올리나?** DROP COLUMN 8개 컷오버, 마이그레이션 → 코드 → 백필 순서와 그 이유 |
| [deploy-custom-domain-runbook.md](./deploy-custom-domain-runbook.md) | **브랜드 커스텀 도메인을 prod 에 어떻게 올리나?** 레포 간 순서(예약 슬러그 동일 창 · P2→P3 · P4 마지막), `VERCEL_PROJECT_ID` 환경별 분리, Vercel "Redirect to primary domain" 함정, 배포 후 curl 검증, 롤백 |
| [payment-integration.md](./payment-integration.md) | 고객 결제(Eximbay, USD)가 어떻게 흐르나? prepare→verify, 환불, 웹훅 |
| [brand-subscription.md](./brand-subscription.md) | 브랜드 구독 결제(NicePay 빌링, KRW)가 어떻게 되나? 빌키, 정기 청구, dunning, 노출 게이트 |
| [mcf/README.md](./mcf/README.md) | Amazon MCF(멀티채널 풀필먼트) — Amazon FBA 재고로 KLOW 주문 자동 출고. SP-API 조사·구현 계획·플로우 (📄 문서 단계) |
| [custom-domain/README.md](./custom-domain/README.md) | 브랜드 커스텀 도메인(`shop.brandA.com`) 연결 — 둘러보기·담기는 그 도메인 / 로그인·결제는 klow.kr(**핸드오프**), 쿠키·CSRF·CORS 처리, 미들웨어 경로 규칙 (✅ P0~P4 구현 완료 · 스테이징 배포 · 운영 대기) |
| [custom-domain/purchase-plan.md](./custom-domain/purchase-plan.md) | **KLOW 가 도메인을 대신 사서 자동 연결하고 연 이용료를 받는다** — 브랜드는 DNS 를 만지지 않는다. Cloudflare Registrar 계약·한계(`.kr` 미지원), 마진 30% 산식, **환불 불가 상품의 결제↔등록 순서와 보상**(타임아웃 ≠ 실패), 갱신 dunning (📝 계획 완료 · 코드 미착수) |
| [storefront-sales-analytics.md](./storefront-sales-analytics.md) | 브랜드 `/stats` 에 **국가·제품 수요 분석 + 현장 채널**을 어떻게 붙이나? 두 모집단(퍼널 vs 주문 원장)이 왜 다른 숫자를 내는지, 채널 탭 정의, 서버/브랜드 작업 목록 (✅ 구현 완료 · 배포 대기) |
| [preview-pages.md](./preview-pages.md) | klow_web 디자인 프리뷰 화면은 어디에 있나? 결제 완료(`/checkout/preview`)·배송추적(`/track/preview`)·시딩(`/seed/preview*`) |
| [archive/](./archive/README.md) | 완료된 마이그레이션/정리 노트, 스크래치 — **현행 시스템 설명 아님** |

## 규칙

- **server/** 는 klow_server 코드의 API 문서다 — 컨트롤러를 추가/변경하면 해당 `server/modules/<module>.md` 를 함께 갱신한다 (klow_server 저장소의 `docs/README.md` 는 이곳을 가리키는 포인터만 남아 있다).
- 실행이 끝난 일회성 계획/정리 노트는 **archive/** 로 옮기고 상단에 보관 배너를 단다.
- 워크스페이스 개발 규칙(포트, repo 독립성, Prisma 마이그레이션 규칙 등)은 [`../CLAUDE.md`](../CLAUDE.md) 참고.
