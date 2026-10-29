# dampenerlab — 댐프너랩 커스텀 댐프너 해외 판매 사이트

`dampenerlab.klow.kr` · 프론트 레포 `klow_dampenerlab`(신규) · 서버 모듈 `klow_server/src/modules/dampenerlab/`
(API: [`docs/server/modules/dampenerlab.md`](../../server/modules/dampenerlab.md)). 진행 상태는 `docs/PROGRESS.md §7` 50~52행.

## 왜

아이템샵(itemshop.com) 대표님이 **댐프너랩 커스텀 댐프너**(https://itemshop.com/products/129696696)를
해외 고객에게 팔고 싶어 한다. 원본 상품 페이지를 **영어로 똑같이 복제**하고, 구매는 **KLOW Eximbay(USD)**,
발송은 **KLOW EFS 송장**으로 한다.

## 결정 (사용자, 2026-10-29)

| # | 결정 |
|---|---|
| D1 | 편집기 **전부 복제** — 사진·텍스트·디자인 소스·배경색·레이어·undo/redo·앞/뒤 면 |
| D2 | 발송 = **KLOW EFS 송장** — 댐프너랩을 KLOW `Brand` 로(어드민 직접 생성 → 구독 게이트 면제), 기존 Order/Shipment/정산 재사용 |
| D3 | 가격 = **KLOW 표준 가격모델** — 제품별 `basePriceUsd`/국가 가격 + 배송비 요율표(500g)/브랜드 지정 배송비 |
| D4 | 원본 상품 이미지·디자인 소스·상세 이미지 **사용 허락**(대표님 본인 사이트) → R2 `dampenerlab/assets/` 로 복사해 쓴다 |
| D5 | 프로젝트명 `dampenerlab`, 도메인 `dampenerlab.klow.kr` |

## 설계 (A 단계에서 확정 — 서버)

- 주문은 **소비자 주문 그대로**(`kind=consumer`, `channel=web`) + `Order.shopSite='dampenerlab'` + `OrderItem.customization`.
- `customization` 은 **productId 단위**(주문 생성이 같은 제품 줄을 병합하므로) → v1 은 **한 주문 = 디자인 1개 × 수량**(+ 케이스 디자인 1개). 디자인이 다른 댐프너 여러 개를 한 번에 사는 장바구니는 범위 밖.
- 결제 return 303 은 `payment/shop-sites.ts` env 고정 맵 → `${DAMPENERLAB_FRONTEND_URL}/checkout/redirect`.
- 디자인 파일은 공개 presign(서버가 키를 정하고 크기 서명) → 주문 생성 때 `headObject` 로 실재 확인.

## 원본 실측 (2026-10-29 크롬)

- 스택: Nuxt + **Konva** 캔버스(canvas 5개), NHN shopby. 상품 목업 이미지
  `https://s3.ap-northeast-2.amazonaws.com/resource.itemshop.com/product/129696696/r_dam_<color>_small.webp`,
  아이콘 `https://resource.itemshop.com/custom/icon/*.svg`, 로고 `…/common/logo/LOGO.svg`.
- 레이아웃(1458px 뷰포트): 헤더(로고 · 신상품 · 커스텀 상품 · 검색 · 찜/장바구니/계정) → 좌 편집기 카드(툴바 + 캔버스 + 우하단 면 썸네일) · 우 옵션 카드(≈350px).
- 툴바: 사진 · 텍스트 · 디자인 · 배경색 | 처음으로 · 이전으로 · 다시실행 · 선택삭제. 객체 선택 시 우측 패널이 속성 패널로 바뀌고 캔버스 옆에 **레이어** 패널(표시/숨김).
- 텍스트 패널: 폰트 드롭다운(기본 노토 산스 KR) · B/I/U/S · 색 18종 + 커스텀(+) · 정렬 6개(좌/중/우 · 상/중/하) · 변형(회전·좌우·상하 뒤집기) · 순서(앞으로/뒤로).
- 디자인 모달: "아이템샵에서 제공하는 무료 디자인 소스" — 내폴더 · 타이포그래피 · 도형 · 문자 · 스티커 · (더 있음 — B 단계에서 전체 수집).
- 옵션: **모양** 사각/원형 · **색상** 10종(화이트 #FFF · 형광옐로우 #E7F56B · 핑크 #D782E5 · 오렌지 #DE773F · 레드 #CA1E08 · 스카이블루 #06D5D7 · 라이트그린 #6DA058 · 다크그린 #3A6525 · 코발트블루 #1C318D · 블랙 #000) — slug 는 목업 파일명(white·yellow·pink·orange·red·skyblue·green·darkgreen·navy·black) · **앞뒤 옵션** 동일/다름.
- 배송 정보: "1일 이내 배송 시작 / 배송비 3,000원(50,000원 이상 무료)" → 해외판은 서버 견적값.
- **추가상품 "커스텀 댐프너 케이스"** 5,000원 — 클릭하면 같은 편집기 모달(실버 틴 케이스 뚜껑 한 면, 색 실버 1종, 장바구니 버튼).
- 하단 탭: 상품설명(이미지 + FAQ 3개: 수명 · 배송 · 교환/반품) · 리뷰 0 · 자주 묻는 질문 · 상품문의 0. 문구는 영어로 옮긴다.
- 원본 가격 20,000원(댐프너) · 5,000원(케이스).

## 단계

| 단계 | 내용 | 끝 기준 |
|---|---|---|
| A | 서버 — 마이그레이션 · dampenerlab 모듈 · 결제 return 분기 · 스펙 | typecheck · jest 전체 · e2e · 실호출(presign → PUT → 주문 → DB 확인) |
| B | `klow_dampenerlab` 레포 생성 + 상품 페이지 클론 + Konva 편집기 전 기능 + 원본 자산 R2 복사 + 케이스 편집 모달 | 크롬에서 원본과 같은 뷰포트 나란히 비교 · 앞/뒤 인쇄 PNG 생성 |
| C | 체크아웃(배송지·견적·동의) → 업로드 → 주문 → Eximbay → `/checkout/redirect` · 어드민/브랜드 주문 상세에 디자인 미리보기·인쇄 PNG 다운로드 · **통관 품목(HS) 추가** · Vercel/DNS · staging → 운영 | 테스트 MID 결제 왕복 · 어드민에서 인쇄 파일 다운로드 |

## 열린 질문 (C 전에 사용자 확인)

- ⚠️⚠️ **통관 분류(HS 코드)** — `Brand.category` 가 EFS 24-6/24-8 의 단일 출처인데 지금 enum 이 `cosmetics`·`dental_materials` 뿐이다. 테니스 댐프너용 품목(enum + `common/constants.ts` `BRAND_CATEGORY_CUSTOMS` + klow_admin 미러)과 **HS 코드를 관세사/EFS 확인 후** 추가해야 실송장을 낼 수 있다. 추측 금지. 피처 DB 의 개발용 브랜드는 임시로 `cosmetics`.
- **해외 판매가** — 개발 데이터는 임시값(댐프너 $15.00 · 케이스 $4.00, `basePriceUsd`). 정산가(`salePrice`)·국가별 가격은 대표님과 정해 어드민에서 입력.
- 제품 무게(통관·참고용) — 임시 30g/60g.
- 상품문의 탭 — 빈 상태 UI 만 둘지, KLOW 문의 API 로 받을지.
