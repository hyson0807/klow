# buyer-platform — 흐름과 설계 논거

결정 요약은 [`README.md`](./README.md), 빌드 스펙은 [`implementation-plan.md`](./implementation-plan.md).

## 1. 관리자 운영 흐름

```
[어드민 /buyer]  "브랜드 추가" → 전 브랜드 검색 모달 → 선택
      │            (BuyerBrand 생성 · published=false · 원본 로고 추종)
      ▼
[/buyer/brands/:brandId]  브랜드 프로필(tier·tagline·city·리드타임…  MOQ 는 제품 구간가에서 계산)
      │                    + 그 브랜드 제품 표 → 제품마다 "추가" 토글
      │                      (BuyerProduct 생성 · 원본 값 프리필 · 이미지 원본 추종)
      │                    + 카테고리 인라인 지정 / 여러 개 골라 일괄 지정
      ▼
[/buyer/products/:productId]  인증 · 구간가 · About · Key actives · For · Size ·
      │                        Shelf life · Made in · Ingredients · 이미지
      │                        ── 우측에 바이어 카드 + PDP 실시간 미리보기
      │                        ── "필수 n/7" 이 7/7 이 되면 공개 토글이 의미를 갖는다
      ▼
[/buyer/home]  카테고리(이름·순서) · 히어로 슬라이드 · 큐레이션 선반(제품 피커)
      ▼
브랜드 공개 토글 ON  →  klow.kr/ 에 노출
```

**편하게 만드는 장치** (사용자 요구 "관리자가 편리하게"):

| 장치 | 왜 |
|---|---|
| 원본 값 프리필 (보조 — 운영 원본은 대부분 빈칸, `implementation-plan.md §4` R2) | 제품 추가 시 `volume`→Size, `ingredients`→Ingredients, `countryOfOrigin`→Made in, `expiryInfo` 에서 개월수 추출 시도→Shelf life, `keyIngredients`→Key actives. 빈칸에서 시작하지 않는다 |
| 완비 배지 `필수 n/7` · 칸별 누락 점 | 브랜드 카드·제품 표 양쪽. 노출 불가 사유(필수 누락·slug 없음·미승인)도 함께 |
| **저장하고 다음 미완비 제품 →** | 대량 입력의 본체(사용자 결정 — 엑셀·AI 초안 대신). 같은 브랜드 안에서 다음 미완비 제품으로 바로 넘어간다 |
| 구간가 "자동 채우기" | MOQ·기준 도매가를 넣으면(저장 안 됨 — 표만 저장) 디자인 비율(1~MOQ-1 샘플=기준가, MOQ=기준가, 3×MOQ ×0.94, 8×MOQ ×0.88, 20×MOQ ×0.82)로 5행 생성 → 수기 수정 |
| 카테고리 일괄 지정 | 브랜드 제품 표에서 체크 → 드롭다운 한 번 |
| 실시간 미리보기 | 바이어 공간의 카드(4:5)와 PDP 상단을 같은 CSS 로 렌더 — "예쁘게 다시 세팅" 하는 작업의 피드백 루프 |
| 이미지 드래그 정렬 · 4:5 크롭 · 원본 상세컷에서 골라 넣기 · 원본으로 되돌리기 | 이미지 재세팅이 이 트랙의 핵심 작업이다(사용자 강조) |

## 2. 디자인 필드 ↔ 스키마 매핑

### 제품 (`KLOWBUYER/components/ProductDetail.tsx`, `lib/detail.ts`)

| 디자인 표시 | 디자인 데이터 | 저장 위치 | 비고 |
|---|---|---|---|
| 제품명 | `Product.name` | `BuyerProduct.nameEn` → 없으면 원본 `Product.name` | 영어 단일 공간이라 영문명 덮어쓰기 칸 |
| CPNP 배지 | `certs` 에 `CPNP` | `BuyerProduct.cpnp` Boolean | |
| FDA OTC 배지 | `FDA OTC` | `BuyerProduct.fdaOtc` Boolean | |
| SPF 배지 | `SPF in-vivo` + claims 의 "SPF 50+ PA++++" | `BuyerProduct.spf` String (빈값 = 배지 없음) | 값 자체를 배지 노트로 |
| GMP 배지 | `ISO 22716` → GMP | `BuyerProduct.gmp` Boolean | |
| Wholesale price by quantity | `tiersFor()` (brand.moq 파생 5행) | `BuyerPriceTier(minQty, unitUsdCents)` | 첫 행 minQty=1 = sample, **둘째 행 시작 = MOQ**(정본, G10). 카드 대표가 = MOQ 구간 단가(G11) |
| About the product | `copy.about` | `BuyerProduct.about` | |
| Key actives | `copy.actives[]` | `BuyerProduct.keyActives String[]` | |
| For | `copy.use` | `BuyerProduct.forText` | |
| Size | `p.size` | `BuyerProduct.size` | |
| Shelf life | `copy.shelfMonths` | `BuyerProduct.shelfLifeMonths Int?` | "N months unopened" |
| Made in | `brand.city, Korea · on market since` | `BuyerProduct.madeIn` 자유 텍스트 | |
| Ingredients | `copy.inci` | `BuyerProduct.ingredients` | |
| 갤러리 | 팩샷 + 공용 연출컷 | `BuyerProduct.images String[]` (빈 배열 = 원본 대표사진 1장) | 카드 4:5. 상세컷은 골라 넣기로만 |
| 카테고리 | `category` 7종 | `BuyerProduct.categoryId → BuyerCategory` | 7종 시드 |
| 뱃지(Bestseller/New) | `badge` | `BuyerProduct.badge String?` | 선택 |
| MSRP | `msrp` | `BuyerProduct.msrpUsdCents Int?` | 선택 — 카드·선반 태그용. 소비자 `basePriceUsd` 프리필 |

### 브랜드 (`BrandDetail.tsx`, `Brands.tsx`)

| 디자인 | 저장 위치 |
|---|---|
| tier (K-Beauty icon / Hidden gem) | `BuyerBrand.tier` enum |
| tagline | `BuyerBrand.tagline` (원본 `Brand.tagline` 프리필) |
| From city · est. year | `city` · `founded Int?` |
| Opening order MOQ | **계산값** — 노출 제품 MOQ 최솟값 (입력 칸 없음) |
| Dispatch lead days | `leadDays Int?` |
| Avg. retail multiple | **계산값** — 노출 제품 `MSRP ÷ MOQ 구간가` 평균 (MSRP 있는 제품만) |
| Export documents (지역) | `exportRegions String[]` (us·ca·uk·eu·gcc·sea·au·latam) |
| Exclusivity open | `exclusiveRegions String[]` |
| Marketing support | `marketingSupport String[]` |
| Derm / K-doctor | `derm Boolean` |
| 로고월 로고 | `logoUrl String?` (null = 원본 `logosWide[0] ?? logosCircle[0]`, 그것도 없으면 디자인처럼 텍스트 워드마크) |

## 3. 왜 이렇게 하나

**왜 전용 테이블인가 (B2B 테이블을 안 쓰나).** 기존 `B2bProductTerm` 은 **브랜드가** 자기 바이어 링크에
쓰는 값이다. 바이어 공간은 **KLOW 가** 편집한다. 한 행을 두 주인이 쓰면 마지막 저장이 이기고 서로의
값을 모르게 덮는다. 필드도 다르다(통화 5종 vs USD 고정, 인증·스펙은 B2B 에 없음).

**왜 Product 컬럼을 늘리지 않나.** 인증·스펙을 `Product` 에 넣으면 브랜드 스튜디오·소비자 PDP·번역
파이프라인이 모두 그 컬럼을 알게 된다. 바이어 공간은 어드민 큐레이션 레이어라 1:1 오버레이 테이블
(`BuyerProduct.productId @unique`)로 두면 다른 표면이 무변경이다. 원본은 읽기만 한다.

**왜 카테고리를 enum 이 아니라 테이블로.** 기존 `ProductCategoryKey`(cleanser…mask) 는 소비자 화면
분류라 디자인 7종(Skincare·Sun Care·Cleansing·Masks·Haircare·Body·Makeup)과 맞지 않는다.
관리자가 이름·순서를 바꾸고 추가할 수 있어야 하므로(사용자 요구 "세팅을 편하게") enum 은 탈락이다.
제품당 카테고리는 **하나**다(디자인 필터 `p.category === view`).

**왜 `.kb` 스코프 CSS 인가.** 디자인은 BEM 순수 CSS(전역 `body`·`a`·`button` 리셋 포함)이고 klow_web 은
Tailwind 다. 그대로 전역 import 하면 소비자 화면이 깨진다. 바이어 페이지 루트에 `.kb` 를 두고 모든
셀렉터를 그 아래로 스코프한다. 폰트는 디자인과 같이 Geist(`next/font/google`) 를 바이어 레이아웃에서만.

**왜 문의는 저장까지 하나 (contact 모듈은 메일만인데).** 바이어 문의는 브랜드에 전달·후속 처리하는
영업 파이프라인이라 어드민 목록·처리 상태가 필요하다. 메일은 알림이고 정본은 테이블이다.

**왜 폴백을 `/` 로 바꾸지 않나.** 지금 소비자 폴백 목적지가 `/shop` 인 것 자체가 버그다 — 브랜드가 SNS·자사몰로
보낸 손님이 경쟁 브랜드 목록으로 샌다(카트·PDP 주석이 이미 같은 경고를 한다). `/` 가 바이어 공간이 되면 그대로
바꿔 끼우는 것은 손님을 **도매 화면**으로 보내는 것이라 더 나쁘다. 소비자 화면과 바이어 화면은 서로 링크하지
않고, 소비자의 "홈" 은 그 손님의 브랜드관이다(README 결정 7).
