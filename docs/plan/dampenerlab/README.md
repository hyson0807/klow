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

## 프론트 설계 (B 단계에서 확정 — klow_dampenerlab)

- 편집기 좌표계 = 원본 Konva stage **800×700**. 인쇄 영역·배경 위치·출력 배율은 원본 템플릿 값 그대로(`src/lib/template.ts`). 배경 목업 위치는 `image_render_params` 로 역산한다(편집 영역이 배경의 editorX/Y 에 오도록).
- 노드는 **중심 기준**(offset = w/2,h/2) — 회전·뒤집기가 제자리. 인쇄 파일은 `render.ts` 가 화면과 같은 규칙으로 off-screen 렌더: 인쇄 영역만 × export_ratio(댐프너 5 → 1865px, 케이스 10 → 3900×2600), 원형은 원 밖 투명.
- 면은 모양별로 따로다(원본과 같다) — 사각 앞/뒤 · 원형 앞/뒤 · 케이스 앞. 앞뒤 동일이면 앞면 하나만 편집·인쇄.
- 손님 사진은 브라우저에서 2000px 로 줄인 data URL 로 편집하고 **결제 직전에만** R2 로 올린다(편집 중 캔버스 오염(CORS)·고아 파일 방지). design JSON 에는 `r2:<key>` 로 남는다.
- 초안은 localStorage(`dl.design.*`, `dl.options.v1`) — 결제 성공 시 지운다. 상품 페이지 → 체크아웃은 모듈 변수 + sessionStorage.
- 가격·배송비는 전부 서버 견적(`/v1/orders/quote`) — 클라 계산 없음. 브랜드당 5개 한도라 댐프너+케이스 합 ≤ 5.
- 헤더의 검색·찜·장바구니·계정은 두지 않았다(상품 1개). 리뷰·상품문의 탭은 빈 상태 + team@klow.kr 안내.
- **랜딩 `/` = dampenerlab.com 메인 복제(영문, 2026-10-29)**, 상품 페이지(편집기)는 **`/custom`** — 랜딩 CTA·체크아웃의 "디자인으로 돌아가기" 링크가 모두 `/custom`. 섹션은 `src/components/landing/*`, 이미지는 `public/assets/landing/`(원본 cafe24 이미지 복사). 원본의 'Trending designs'(여기서 안 파는 상품)·업스트림스포츠 푸터는 뺐고, 제목 폰트 Gilroy(상용)는 Google **Outfit** 으로 대체. ⚠️ 가운데 Vimeo 영상(`1195337966`)은 원본 것을 그대로 임베드해 **한국어 "커스텀 댐프너 20,000 KRW" 자막이 영상에 박혀 있다** — 영문판 영상을 받으면 교체.
- 헤더(전 페이지 공용)는 **중앙 로고(→ `/`)만** — 원본의 좌측 "Dampener"·우측 아이콘 3개는 뺐다. 주문 조회는 결제 완료 화면의 "Track my order"(klow.kr/track)뿐.

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
- 상품문의 탭 — 지금은 빈 상태 + team@klow.kr 안내. 문의 저장이 필요하면 KLOW 문의 API 연결.
- 상세 이미지(원본 9장)는 한국어 문구가 박힌 이미지다 — 영문판 이미지를 받으면 `public/assets/detail/` 교체.
- 리뷰 — 원본도 0건. 고객 직접 리뷰(`reviews` 모듈)를 붙일지.
