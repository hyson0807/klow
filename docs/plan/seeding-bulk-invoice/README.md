# seeding-bulk-invoice — 엑셀로 자동 국제 송장 발급

브랜드가 링크를 보내 받는 사람 정보를 받는 대신, **정보가 들어 있는 엑셀을 올려 바로 EFS 송장을 발급**한다.
`klow_brand` 의 `taeyoung30` 브랜치(커밋 `ceba630`)가 서버 없이 만든 목업이 출발점이다.

## 결정 요약 (사용자 · 2026-09-30)

| 항목 | 결정 |
|---|---|
| 국가별 추가 정보 | **klow_web 결제 페이지와 같은 4종** — CN 신분증 18자리 · MX RFC (둘 다 `recipientTaxId` → EFS 31번) · US State(23번) · JP 영문 이름 + 영문 주소(15·16번). 정본은 서버 `common/efs-recipient.ts` `assertEfsCountryFields` |
| "중국 수출신고번호" | = CN 신분증(31번 세금식별코드). **EFS 30번(수출신고번호)은 다루지 않는다** — 운영 송장 651건 전부 30번 빈값·32번 `N`, `Shipment.efsExportDeclNo` 는 EFS 정산표에서 역으로 채워지는 값이다 |
| 마이그레이션 | 없음 — 필요한 컬럼은 전부 `Order` 에 있다 |
| 박스 무게 | 받지 않는다(KLOW 실측 후청구) |
| **송장 캐리어** | **언제나 어드민 '배송비용' 탭의 국가 고정 캐리어(`ShippingCountry.productCarrier`)**. 무게 분기(`seedingCarrierSplitWeightG`)는 **예상 배송비 확인용**으로만 남는다 — 브랜드 결제 시딩·고객 결제 시딩·일반 주문 전부. 발급 시점엔 박스 무게를 알 수 없기 때문이다 |
| 이메일 | 선택 — 있으면 수령인 배송 안내 메일, 없으면 `''` 저장 + 메일 생략 |
| 수정 대기 명단 | 브라우저 localStorage(목업 그대로) |
| 배송비 | 브랜드 후청구(링크의 "브랜드가 결제"와 같다). 신고가·수량은 서버 기존 정책 |
| 작업 위치 | git `staging` + staging DB 에서 직접 |

## 문서

| 파일 | 정본 범위 |
|---|---|
| [`implementation-plan.md`](./implementation-plan.md) | 빌드 스펙 — A(서버)·B(어드민·브랜드) 단계 명세와 검증 |
