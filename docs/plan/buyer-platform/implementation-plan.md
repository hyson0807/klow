# buyer-platform — 구현 계획 (빌드 스펙 정본)

결정 요약 [`README.md`](./README.md) · 흐름·매핑표 [`flow.md`](./flow.md).
상태는 [`../../PROGRESS.md`](../../PROGRESS.md) `§7` 20·21·22행이 정본이다 — 여기엔 적지 않는다.

## §1 착수 게이트 (불변식)

| # | 불변식 |
|---|---|
| G1 | **원본 테이블(`Product`·`Brand`)에 쓰지 않는다.** 바이어 공간은 1:1 오버레이(`BuyerBrand.brandId @unique` · `BuyerProduct.productId @unique`)이고 원본은 읽기만 한다. 브랜드 스튜디오·소비자 PDP·번역이 무변경이어야 한다 |
| G2 | **기존 `B2b*` 테이블을 읽지도 쓰지도 않는다** (README 결정 2) |
| G3 | **노출 판정은 서버 한 곳**(`buyer` 모듈의 순수 함수 `buyerProductCompleteness()`)이 한다. 어드민 배지와 공개 API 가 같은 함수를 쓴다 — 두 벌이면 "어드민은 7/7 인데 손님 화면에 없다" 가 생긴다 |
| G4 | 공개 API 는 `BuyerBrand.published && BuyerProduct.published && 필수 7 완비 && Brand.status != withdrawn && Brand.slug != null` 만 낸다. 브랜드는 노출 가능한 제품이 1개 이상일 때만 목록에 뜬다 |
| G5 | **이미지 추종 규칙**: `BuyerProduct.images = []` 이면 응답 시점에 원본 `[image, ...detailImages]` 를 싣는다. 응답에 `imagesSource: 'original' \| 'custom'` 를 함께 실어 어드민이 구분한다. 로고도 동일(`logoUrl` null → 원본) |
| G6 | 가격은 **USD 센트 정수**(`unitUsdCents Int`). Decimal·환율을 쓰지 않는다 |
| G7 | 문의 POST 는 완전 공개 쓰기라 `@Throttle(THROTTLE_TIGHT)` 필수 + 메일 HTML 의 모든 입력 `escapeHtml`(선례 `b2b-order-email.ts`) |
| G8 | klow_web 바이어 CSS 는 **`.kb` 루트 아래로 전부 스코프**한다. 전역 셀렉터(`body`·`a`·`button`·`:root` 변수) 0건 |
| G9 | **소비자 화면은 `/shop`·`/` 로 보내지 않는다** — 폴백·CTA·탭의 목적지는 `consumerReturnHref()`(브랜드관) 하나로만 정하고, 없으면 숨긴다(README 결정 7). 바이어 화면(`/`·`/shop/*`)과 소비자 화면 사이에 링크가 0건이어야 한다 |

## §2 스키마 초안 (1단계에서 확정)

```prisma
enum BuyerBrandTier   { icon gem }
enum BuyerInquiryKind { quote brand_request }
enum BuyerInquiryStatus { new handled }

model BuyerBrand {
  id               String   @id @default(cuid())
  brandId          String   @unique
  published        Boolean  @default(false)
  sort             Int      @default(0)
  tier             BuyerBrandTier @default(gem)
  tagline          String   @default("") @db.VarChar(200)
  city             String   @default("") @db.VarChar(60)
  founded          Int?
  moq              Int?
  leadDays         Int?
  retailMultiple   Decimal? @db.Decimal(4, 2)
  exportRegions    String[] @default([])
  exclusiveRegions String[] @default([])
  marketingSupport String[] @default([])
  derm             Boolean  @default(false)
  logoUrl          String?  @db.VarChar(500)
  products         BuyerProduct[]
  brand            Brand    @relation(fields: [brandId], references: [id], onDelete: Cascade)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model BuyerProduct {
  id              String   @id @default(cuid())
  productId       String   @unique
  buyerBrandId    String
  published       Boolean  @default(false)
  sort            Int      @default(0)
  categoryId      String?
  nameEn          String   @default("") @db.VarChar(200)
  size            String   @default("") @db.VarChar(60)
  about           String   @default("") @db.VarChar(4000)
  keyActives      String[] @default([])
  forText         String   @default("") @db.VarChar(500)
  shelfLifeMonths Int?
  madeIn          String   @default("") @db.VarChar(120)
  ingredients     String   @default("") @db.VarChar(8000)
  cpnp            Boolean  @default(false)
  fdaOtc          Boolean  @default(false)
  spf             String   @default("") @db.VarChar(40)
  gmp             Boolean  @default(false)
  moq             Int?
  msrpUsdCents    Int?
  badge           String?  @db.VarChar(30)
  images          String[] @default([])
  tiers           BuyerPriceTier[]
  // relations: product(Cascade) · buyerBrand(Cascade) · category(SetNull) · shelfItems
  @@index([buyerBrandId, sort])
  @@index([categoryId])
}

model BuyerPriceTier { id · buyerProductId · minQty Int · unitUsdCents Int · @@unique([buyerProductId, minQty]) }
model BuyerCategory  { id · slug @unique · name · sort · products BuyerProduct[] }
model BuyerHeroSlide { id · imageUrl · buyerProductId? (SetNull) · caption · sort }
model BuyerShelf     { id · title · lede · preview Int @default(4) · sort · published · items BuyerShelfItem[] }
model BuyerShelfItem { id · shelfId(Cascade) · buyerProductId(Cascade) · sort · tag · @@unique([shelfId, buyerProductId]) }
model BuyerInquiry   { id · kind · brandId? · productId? · qty? · company · email · market · message · status @default(new) · adminNote · createdAt · updatedAt · @@index([status, createdAt]) }
```

전부 `CREATE TABLE` + `Brand`·`Product` 의 역관계 필드(스키마 전용, DB 컬럼 없음)라 **롤링 안전**.

## §3 단계

### 1. A — klow_server: 스키마 · 마이그레이션 · 어드민 API · 공개 API · 문의 (`§7` 20행)

- **읽을 것**: 이 문서 §1·§2 · `flow.md §2` 매핑표 · `docs/server/modules/b2b.md`(모듈 구조 선례) ·
  `docs/server/modules/contact.md`(공개 폼 + 메일 선례) · CLAUDE.md `klow_server 코드 구조 규칙`
- **건드리는 레포 · 배포 순서**: klow_server 단독. 이 단계만 배포돼도 아무 화면이 안 바뀐다(새 라우트뿐)
- **스키마·데이터 위험**: 마이그레이션 `add_buyer_platform` — 신규 테이블 8 + enum 3, 롤링 안전.
  ⚠️ **git 브랜치 `feat/buyer-platform` + Neon DB 브랜치(staging fork)를 먼저 판다**(CLAUDE.md Prisma 절).
  카테고리 7종 시드는 **마이그레이션 SQL 안의 `INSERT … ON CONFLICT DO NOTHING`** 으로 넣는다(별도
  스크립트 없이 staging·운영 동일하게 — `20260930042335` 의 같은 SQL 백필 선례)
- **할 일** (세션 안 순서 = 정지점)
  1. 스키마 + 마이그레이션 + 카테고리 시드 ← **정지점 ①**
  2. `src/modules/buyer/` 신설(평면 파일 규칙): `buyer.module.ts` · `buyer-admin.service.ts` ·
     `buyer-public.service.ts` · `buyer.mapper.ts` · `buyer-completeness.ts`(G3 순수 함수 + 프리필 함수
     `prefillFromProduct()`) · `buyer-inquiry-email.ts` · 검증 `common/validation/buyer.ts`(배럴 등록)
  3. `admin-buyer.controller.ts` (`admin/buyer`, AdminGuard) ← **정지점 ②**
     - 브랜드: `GET brands`(완비 집계 포함) · `GET brand-candidates?q=`(미등록 전 브랜드 검색) ·
       `POST brands {brandId}` · `GET/PATCH/DELETE brands/:brandId` · `PUT brands/order {ids[]}`
     - 제품: `GET brands/:brandId/products`(그 브랜드 원본 제품 전부 + 바이어 행 유무·완비) ·
       `POST products {productId}`(프리필) · `GET/PATCH/DELETE products/:productId` ·
       `PUT products/:productId/tiers {tiers[]}`(전체 교체, 최대 6, 첫 행 minQty=1, minQty 오름차순·단가 >0) ·
       `PATCH products/bulk {productIds[], categoryId?, published?}`
     - 홈: 카테고리 CRUD + `PUT categories/order` · 히어로 CRUD + order · 선반 CRUD + order + `PUT shelves/:id/items`
     - 문의: `GET inquiries?status=` · `PATCH inquiries/:id {status, adminNote}`
  4. `public-buyer.controller.ts` (`v1/buyer`, public)
     - `GET home` → `{ heroSlides, categories, shelves(+items 카드), brands(로고월+패널 요약) }`
     - `GET products?category=&q=&take=&cursor=` → 카드 목록
     - `GET brands/:slug` → 브랜드 + 노출 제품 카드
     - `GET products/:id` → PDP 전체(구간가·인증·스펙·이미지·같은 브랜드 다른 제품)
     - `POST inquiries` (`THROTTLE_TIGHT`) → 저장 + 메일(`BUYER_INQUIRY_EMAIL`, 없으면 `CONTACT_INBOX_EMAIL`).
       메일 실패는 저장이 됐으므로 **삼키고 로그**(contact 와 반대 — 정본이 테이블이라서)
  5. `app.module.ts` 등록 · `.env.example` 에 `BUYER_INQUIRY_EMAIL=` 한 줄
  6. 문서: `docs/server/modules/buyer.md` 신규 + `docs/server/README.md` 색인 + CLAUDE.md `Server modules` 목록에 `buyer`
- **완료 기준**
  - 검증 3층(typecheck 2개 · `test:e2e` 모듈 수 +1 · `npm run start` 라우트 수 증가 기록)
  - jest: `buyer-completeness` 스펙(필수 7 각각 누락 → 미완비 · 이미지 원본 추종 시 완비 · 구간가 검증 규칙)
  - curl: 어드민 세션으로 브랜드 추가 → 제품 추가(프리필 값 확인) → 구간가·카테고리·필수 채움 →
    published → `GET /v1/buyer/home` 에 그 브랜드·제품이 나온다 / 한 칸 비우면 사라진다
  - `POST /v1/buyer/inquiries` 6회째 429
- **선행 조건**: 없음. ⚠️ `§4` WIP — 다른 마이그레이션 단계가 `진행 중` 이면 착수하지 않는다

### 2. B — klow_admin: "바이어 공간" (`§7` 21행)

- **읽을 것**: `docs/server/modules/buyer.md`(1단계 산출) · `flow.md §1`(운영 흐름·편의 장치) ·
  CLAUDE.md `Admin UI Convention — Toast Feedback` · 1단계 인계 메모
- **건드리는 레포 · 배포 순서**: klow_admin. 서버(1단계)가 먼저 — 뒤집으면 모든 화면 404 토스트
- **스키마·데이터 위험**: 없음
- **할 일** (세션 안 순서 = 정지점)
  1. `lib/api/buyer.ts`(DTO + `buyerApi`, 배럴 export) · `Sidebar.tsx` 에 그룹 **"바이어 공간"**
     (`/buyer` 브랜드 · `/buyer/home` 홈 구성 · `/buyer/inquiries` 문의) · `components/tabs/routeLabels.ts`
  2. `/buyer` — 올린 브랜드 카드 목록(로고·이름·공개 토글·`필수 완비 제품 n/m`·드래그 순서) +
     "브랜드 추가" 검색 모달
  3. `/buyer/brands/[brandId]` — 상단 브랜드 프로필 폼(지역은 칩 멀티선택, 로고 교체/원본으로) +
     하단 제품 표(썸네일·이름·추가 토글·카테고리 드롭다운·완비 배지(hover 로 빠진 항목)·공개 토글·
     체크박스 일괄 카테고리/공개)
  4. `/buyer/products/[productId]` — 2단 레이아웃. 좌: 섹션 카드(기본·인증·도매가·상세·이미지),
     우: sticky **미리보기**(바이어 카드 4:5 + PDP 상단 배지·구간가 표). 바이어 CSS 의 해당 부분만
     admin 에 `.kb-preview` 스코프로 복사. 구간가 "자동 채우기" · 이미지 업로드(`lib/upload.ts`)·
     4:5 크롭(`ImageCropModal` 재사용)·**`@dnd-kit` 추가로 드래그 정렬**·원본으로 되돌리기 ← **정지점**
  5. `/buyer/home` — 탭 3개: 카테고리(이름 인라인 편집·드래그 순서·삭제 시 소속 제품 수 경고) ·
     히어로(이미지·연결 제품·캡션·순서) · 선반(제목·리드·4/8·제품 피커 모달·태그·순서)
  6. `/buyer/inquiries` — 목록(종류·브랜드/제품·회사·이메일·상태) + 상세 드로어(처리 완료·메모)
- **완료 기준**
  - 모든 저장/삭제/오류가 토스트(CLAUDE.md 규칙) · `npm run build` 통과
  - 화면: 브랜드 추가 → 제품 3개 추가·채움 → 미리보기가 입력과 함께 바뀜 → 이미지 순서 바꾸고 새로고침
    후 유지 → "원본으로" 시 브랜드 원본 이미지 복귀 → 홈 구성에서 선반에 넣은 제품이 `GET /v1/buyer/home` 에 보임

### 3. C — klow_web: 바이어 공간 화면 + 구 /shop 제거 + 마무리 (`§7` 22행)

제목과 순서만 둔다 — 전제(공개 API 응답 모양)는 1단계가 끝나야 확정된다. 착수 세션에서 §5 템플릿으로 명세한다.

#### ① 먼저 — 브랜드관 이탈 버그 수정 (README 결정 7 · G9)

**바이어 공간과 독립이라 세션 첫 순서로 하고 커밋을 따로 뗀다** — 서버 배포와 무관하게 먼저 내보낼 수 있다.
`lib/brandReturn.ts` 에 `consumerReturnHref(ctx)` 를 두고(우선순위: 현장 복귀 → 화면이 아는 브랜드 →
`readBrandReturn()` → `null`) 아래 호출부를 전부 그걸로 바꾼다. `null` 이면 버튼·링크·탭을 **숨긴다.**

| 위치 (2026-10-04 실측) | 지금 | 바꿀 것 |
|---|---|---|
| `components/brand/BrandStorefront.tsx:127` (`BrandError` 뒤로가기) | `useSmartBack("/shop")` | 히스토리 없으면 `readBrandReturn()`, 없으면 숨김 |
| `app/product/[id]/page.tsx:107` 뒤로가기 | `brandHref ?? "/shop"` | `?brand=` 없으면 **제품 응답의 브랜드 slug**(착수 시 DTO 필드 확인) |
| `app/product/[id]/page.tsx:182` 담기 후 이동 | `readOnsiteReturn() \|\| "/shop"` · `brandHref ?? "/shop"` | 같은 헬퍼 |
| `app/cart/page.tsx:64-68` `backHref`(헤더 뒤로 + 빈 카트 CTA) | 현장/브랜드 없으면 `/shop` | 헬퍼 + 카트 아이템의 브랜드 |
| `app/checkout/onsite/page.tsx:29` | `useSmartBack('/shop')` | `readOnsiteReturn()` |
| `app/orders/page.tsx:145` 빈 주문 "쇼핑 시작" | `href="/shop"` | 헬퍼, 없으면 CTA 숨김 |
| `components/layout/BottomTabBar.tsx:21` shop 탭(`/cart`·`/my` 에서 보임) | `/shop` | **"브랜드관" 탭 → `readBrandReturn()`**, 없으면 탭 생략 |
| `app/my/page.tsx:125` 로그아웃 후 | `router.replace('/')` | 헬퍼, 없으면 `/login` |
| `app/login/page.tsx:65·76` 뒤로 폴백 · 로고 링크 | `'/'` | 헬퍼 / 로고는 링크 해제 |
| `components/auth/{LoginForm:41,SignupForm:80}` `returnTo` 기본값 | `'/'` | 헬퍼, 없으면 `/my` |
| `middleware.ts:45` 주석 | `/shop` 언급 | 갱신 |

이미 맞게 된 선례: `checkout/_components/SuccessView.tsx` 의 "계속 쇼핑"(돌아갈 브랜드관을 알 때만 띄운다) —
같은 정책을 전 화면으로 넓히는 것이다. ⚠️ breadcrumb 는 **sessionStorage(탭 한정)** 라 새 탭에서는 비어 있다 —
그래서 "화면이 아는 브랜드"가 앞순위다.

완료 기준: 브랜드관 링크를 **새 탭(히스토리 없음)**으로 열고 → 제품 → 카트 → 카트 비우기 → 뒤로/CTA,
`/my`·`/orders` 탭 이동, 로그아웃까지 해도 **주소창이 `/shop`·`/` 가 되는 순간이 0번**. `grep -rn "'/shop'\|\"/shop\"" src`
결과가 바이어 페이지 외 0건.

#### ② 이후 — 바이어 공간

세션 안 순서: ② `KLOWBUYER/app/globals.css` 를 `.kb` 스코프로 이식 + Geist 폰트 + 바이어 전용 Header/Footer
(BottomTabBar·소비자 Footer·Onboarding 은 `/` 와 `/shop/*` 에서 숨김) → ③ `/` 홈(HeroSlides · Collection:
Curated 선반 / All / 카테고리 탭 + 검색 · 브랜드 로고월 + 패널) → ④ `/shop/brands/[slug]` · `/shop/products/[id]`
(갤러리 · 인증 배지 · 구간가 표 + 수량 계산기 · 상세 스펙 · More from brand) → ⑤ Request 드로어 →
`POST /v1/buyer/inquiries` → ⑥ 구 `/shop`·`/shop/search`·`/shop/recommendations` 삭제(①로 참조가 이미 0건),
onboarding 자동 노출 경로·`sitemap.ts` 정리 → ⑦ 결정 기록(`decisions/storefront.md` +
`decisions/README.md` + CLAUDE.md 색인) · CLAUDE.md `klow_web pages` 갱신 · staging push 안내

⚠️ 착수 시 확인할 것
- **커스텀 도메인**: `/` 는 커스텀 도메인에서 브랜드관으로 rewrite 되므로 영향 없음. `shop` 은 이미
  `KLOW_ONLY_SEGMENTS`(→ klow.kr 307) — `/shop/*` 바이어 페이지도 klow.kr 로 간다(의도와 일치)
- **SEO**: `/` 의 메타·OG 가 소비자 문구다 → 바이어 문구로. 구 `/shop` URL 은 `/` 로 301
- ⚠️ ⑥ 의 삭제는 **① 이 끝난 뒤에만** — 순서가 뒤집히면 남은 `/shop` 링크가 404 가 된다
- onboarding 자동 노출이 지금 `/shop` 한 곳에만 걸려 있다(`OnboardingMount.tsx:23`) — 삭제 후 국가 선택이
  브랜드관 유입의 `useGuestCountryPrompt` 로만 도는지 확인
- 디자인의 Sample 버튼·샘플박스 바·AskProduct·리뷰·`/match`·signin 은 **이식하지 않는다**(README 스코프 밖)

배포 순서: **klow_server → klow_admin → klow_web**. web 이 먼저면 공개 API 404 → `/` 가 빈 화면(구 `/shop`
은 이미 삭제됨) — **반드시 서버 배포 후**.
