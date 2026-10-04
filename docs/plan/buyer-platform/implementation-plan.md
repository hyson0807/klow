# buyer-platform — 구현 계획 (빌드 스펙 정본)

결정 요약 [`README.md`](./README.md) · 흐름·매핑표 [`flow.md`](./flow.md).
상태는 [`../../PROGRESS.md`](../../PROGRESS.md) `§7` 20·21·22행이 정본이다 — 여기엔 적지 않는다.

## §1 착수 게이트 (불변식)

| # | 불변식 |
|---|---|
| G1 | **원본 테이블(`Product`·`Brand`)에 쓰지 않는다.** 바이어 공간은 1:1 오버레이(`BuyerBrand.brandId @unique` · `BuyerProduct.productId @unique`)이고 원본은 읽기만 한다. 브랜드 스튜디오·소비자 PDP·번역이 무변경이어야 한다 |
| G2 | **기존 `B2b*` 테이블을 읽지도 쓰지도 않는다** (README 결정 2) |
| G3 | **노출 판정은 서버 한 곳**(`buyer` 모듈의 순수 함수 `buyerProductCompleteness()`)이 한다. 어드민 배지와 공개 API 가 같은 함수를 쓴다 — 두 벌이면 "어드민은 7/7 인데 손님 화면에 없다" 가 생긴다 |
| G4 | 공개 API 는 `BuyerBrand.published && BuyerProduct.published && 필수 7 완비 && Brand.status = approved && Product.status = approved && Brand.slug != null` 만 낸다. `Product.hidden`·구독 상태는 **보지 않는다**(README 결정 5). 어드민 응답은 노출 불가 사유(`필수 누락 · slug 없음 · 브랜드 미승인 · 제품 미승인`)를 함께 싣는다. 브랜드는 노출 가능한 제품이 1개 이상일 때만 목록에 뜬다 |
| G5 | **이미지 추종 규칙**: `BuyerProduct.images = []` 이면 응답 시점에 원본 **대표사진 1장**(`image`, 비었으면 `detailImages` 의 첫 비동영상)만 싣는다. `detailImages` 전체를 싣지 않는다(README 결정 6). 응답에 `imagesSource: 'original' \| 'custom'` 를 함께 실어 어드민이 구분한다. 로고도 동일(`logoUrl` null → 원본) |
| G6 | 가격은 **USD 센트 정수**(`unitUsdCents Int`). Decimal·환율을 쓰지 않는다 |
| G7 | 문의 POST 는 완전 공개 쓰기라 `@Throttle(THROTTLE_TIGHT)` 필수 + 메일 HTML 의 모든 입력 `escapeHtml`(선례 `b2b-order-email.ts`) |
| G8 | klow_web 바이어 CSS 는 **`.kb` 루트 아래로 전부 스코프**한다. 전역 셀렉터(`body`·`a`·`button`·`:root` 변수) 0건 — **유일한 예외는 `body:has(.kb)` 배경색 한 줄**(소비자 `globals.css` 의 `body{background:#f1f2f4}` 가 오버스크롤에 비치는 것을 막는다. 같은 파일에 `body:has(main[data-shell=desktop])` 선례) |
| G10 | **MOQ 정본 = 구간가 표**: `tiers[0].minQty = 1`(샘플) · `tiers.length >= 2` · MOQ = `tiers[1].minQty` · minQty 엄격 오름차순. 제품·브랜드 MOQ 컬럼은 **만들지 않는다**. 브랜드 `Opening order` = 노출 제품 MOQ 최솟값, `Avg. retail multiple` = 노출 제품 `msrp / MOQ가` 평균 — 둘 다 응답 시 계산(README 결정 9) |
| G11 | 카드·패널·선반의 대표 도매가 = **MOQ 구간 단가**(`tiers[1]`). 공개 매퍼 한 곳(`cardPrice()`)만 이 규칙을 안다 |
| G12 | 공개 단건 조회(`brands/:slug`·`products/:id`)는 **노출 불가면 존재 여부와 무관하게 동일한 404** — 비공개 행의 존재를 새지 않는다. `BuyerProduct` 의 브랜드와 `Product.brandId` 가 다르면(제품의 브랜드가 바뀐 경우) 노출 불가 + 어드민 사유 `브랜드 불일치` |
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
  leadDays         Int?
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
model BuyerInquiry   { id · kind · subject(VarChar 200 — 디자인 "Brand or product", 필수) · needs(VarChar 2000) · market(VarChar 200 — "Business & market") · email(VarChar 254, 필수) · brandId?(SetNull) · productId?(SetNull) · qty? · ip(VarChar 64) · status @default(new) · adminNote · createdAt · updatedAt · @@index([status, createdAt]) }
// ⚠️ 필드는 디자인 `RequestBrand.tsx` 드로어 4칸(brand/product* · detail · market · email*)에 맞춘다 — 회사명 칸은 디자인에 없다
// 브랜드·제품 FK 는 SetNull: 문의는 영업 기록이라 브랜드가 바이어 공간에서 빠져도 남아야 한다
```

전부 `CREATE TABLE` + `Brand`·`Product` 의 역관계 필드(`buyerBrand BuyerBrand?` · `buyerProduct BuyerProduct?` — 스키마
전용, DB 컬럼 없음)라 **롤링 안전**. **Decimal 컬럼 0개**(돈은 센트 Int, 배수는 계산값) — b2b 매퍼가 Decimal→number 변환
주석을 길게 단 이유를 반복하지 않는다.

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
     - 시드 SQL 은 `prisma migrate dev --create-only --name add_buyer_platform` 로 만든 파일 끝에 붙이고 `migrate dev` 로 적용.
       ⚠️ `@default(cuid())` 는 **Prisma 클라이언트 쪽 기본값**이라 SQL INSERT 에는 안 걸린다 — id 를 명시(`'bcat_skincare'` 등)
  2. `src/modules/buyer/` 신설(평면 파일 규칙): `buyer.module.ts` · `buyer-admin.service.ts` ·
     `buyer-public.service.ts` · `buyer.mapper.ts` · `buyer-completeness.ts`(G3 순수 함수 + 프리필 함수
     `prefillFromProduct()` + 원본 대표사진 선택 — 서버엔 동영상 판별 헬퍼가 없어 **확장자 판별(mp4·mov·webm)을 여기 둔다**, klow_web `isVideoUrl` 과 같은 규칙) · `buyer-inquiry-email.ts` · 검증 `common/validation/buyer.ts`(배럴 등록)
  3. `admin-buyer.controller.ts` (`admin/buyer`, AdminGuard) ← **정지점 ②**
     - 브랜드: `GET brands`(완비 집계 + 필수 칸별 누락 수 + 노출 제품 수) · `GET brand-candidates?q=`(**승인 브랜드만**, 이미 올린 것은 `added:true` — 기존 `GET /admin/brands` 는 승인 필터·추가 여부가 없어 재사용하지 않는다) ·
       `POST brands {brandId}` · `GET/PATCH/DELETE brands/:brandId`(⚠️ DELETE 는 입력한 제품 정보까지 cascade 로 지운다 — 어드민은 확인 모달 필수, 평소엔 공개 토글 OFF 를 권한다) · `PUT brands/order {ids[]}`
     - 제품: `GET brands/:brandId/products`(그 브랜드 **승인** 제품 + 바이어 행 유무·필수 칸별 누락·노출 불가 사유) ·
       `POST products {productId}`(**승인 제품만** · 프리필 — 원본은 영어로 저장돼 있어 그대로 옮긴다: `name`→nameEn · `volume`→Size · `ingredients` · `countryOfOrigin`→Made in · `expiryInfo` 개월수 · `keyIngredients`→Key actives · `basePriceUsd`→msrp. ⚠️ 운영 실측상 대부분 **빈칸**이라 프리필이 해결책이 아니다 — 아래 §4) · `GET/PATCH/DELETE products/:productId`(GET 은 이미지 편집기용 원본 상세컷 목록 `originalImages` 포함) ·
       구간가는 **`PATCH products/:productId` 의 `tiers` 필드로 같은 트랜잭션에서 전체 교체**(2~6행, G10 규칙, 단가 >0 — 위반은 400 으로 막는다. 완비 판정이 아니라 **입력 검증**이다) — 별도 PUT 로 떼면 편집기 저장 한 번이 요청 둘이 되어 반쪽 저장이 생긴다. GET 응답에 `preview`(공개 매퍼로 만든 PDP 모양, published 무시)와 `nextIncompleteProductId`(같은 브랜드의 다음 미완비 제품)를 싣는다 ·
       `PATCH products/bulk {productIds[], categoryId?, published?}`
     - 홈: 카테고리 CRUD + `PUT categories/order`(⚠️ **소속 제품이 있으면 DELETE 409** — `SetNull` 로 두면 그 제품들이 필수 미달이 되어 바이어 화면에서 **조용히 사라진다**) · 히어로 CRUD + order · 선반 CRUD + order + `PUT shelves/:id/items`
     - 문의: `GET inquiries?status=` · `PATCH inquiries/:id {status, adminNote}`
     - 이미지 재크롭용: `GET image-source?url=` — 기존 이미지(브랜드 원본·이미 올린 것)를 받아 크롭 모달에 넣기 위한 프록시.
       ⚠️ **SSRF 축**이라 호스트를 `R2_PUBLIC_BASE` 와 운영 CDN(`cdn.klow.kr`) 로 **고정 화이트리스트**한다. 2단계 착수 시
       R2 CORS 가 어드민 오리진 GET 을 이미 허용하면 이 라우트는 만들지 않는다(그 판정을 인계 메모에 남길 것)
     - 모든 PATCH 스키마는 **`patchOf()`**(`common/validation/shared.ts`) — `.partial()` 은 zod v4 에서 default 를 주입해
       보내지 않은 칸을 덮는다(2026-07 사고)
  4. `public-buyer.controller.ts` (`v1/buyer`, public) — ⚠️ 완비·노출 판정은 **읽을 때 계산**한다(원본 `image`·`status`
     가 다른 화면에서 바뀌므로 저장된 `complete` 컬럼은 낡는다). 규모가 수백 행이라 `include` 한 번 + 메모리 판정으로
     충분하고 N+1 을 만들지 않는다. 서버 캐시 없음
     - `GET home` → `{ heroSlides, categories, shelves(+items 카드), brands(로고월+패널 요약) }` — 노출 제품이 0개인 카테고리·선반·브랜드는 빼고, 연결 제품이 비노출인 히어로는 **이미지만 남기고 링크를 뗀다**
     - `GET products?category=&q=&take=&cursor=` → 카드 목록
     - `GET brands/:slug` → 브랜드 + 노출 제품 카드
     - `GET products/:id` → PDP 전체(구간가·인증·스펙·이미지·같은 브랜드 다른 제품)
     - `POST inquiries` (`THROTTLE_TIGHT` — 공용 상수가 아니라 **컨트롤러 로컬 상수**다, contact·admin-auth 선례) → `brandId`·`productId` 가 오면 **노출 중인 것만** 연결(아니면 null) · 숨은 필드 honeypot(채워지면 200 을 주고 저장 안 함) · `req.ip` 저장 → 저장 + 메일(`BUYER_INQUIRY_EMAIL`, 없으면 `CONTACT_INBOX_EMAIL`).
       메일 실패는 저장이 됐으므로 **삼키고 로그**(contact 와 반대 — 정본이 테이블이라서)
  5. `app.module.ts` 등록(`BuyerModule` imports `WebAuthModule` — `EmailService`. b2b 선례대로 순환 없음) · `.env.example`
     에 `BUYER_INQUIRY_EMAIL=` 한 줄 · cron 없음(e2e 의 cron 기대 목록 무변경). 순서 변경 `PUT …/order` 는 **현재 id 집합과
     정확히 같은 목록**만 받는다(일부만 오면 400) — 동시 편집에서 순서가 반쯤 섞이지 않게
     - 이미지 URL 검증: `https://` 문자열 · 500자 · 배열 최대 12. 호스트 제한은 두지 않는다(환경마다 R2 공개 주소가 달라서 — 기존 제품 `image` 와 같은 수준)
  6. 문서: `docs/server/modules/buyer.md` 신규 + `docs/server/README.md` 색인 + CLAUDE.md `Server modules` 목록에 `buyer`
- **완료 기준**
  - 검증 3층(typecheck 2개 · `test:e2e` 모듈 수 +1 · `npm run start` 라우트 수 증가 기록)
  - jest: `buyer-completeness` 스펙(필수 7 각각 누락 → 미완비 · 이미지 원본 추종 시 완비 · 구간가 검증 규칙)
  - curl: 어드민 세션으로 브랜드 추가 → 제품 추가(프리필 값 확인) → 구간가·카테고리·필수 채움 →
    published → `GET /v1/buyer/home` 에 그 브랜드·제품이 나온다 / 한 칸 비우면 사라진다
  - `POST /v1/buyer/inquiries` 6회째 429 · ⚠️ dev 의 `RESEND_API_KEY` 가 **실발송**이다 — 테스트는 `RESEND_API_KEY= npm run start`
  - jest: G10(구간 1행·첫 행≠1·비오름차순 → 400) · G11 `cardPrice()` · 브랜드 Opening order·retail multiple 계산 · G12 404 동일성
- **선행 조건**: 없음. ⚠️ `§4` WIP — 다른 마이그레이션 단계가 `진행 중` 이면 착수하지 않는다

### 2. B — klow_admin: "바이어 공간" (`§7` 21행)

- **읽을 것**: `docs/server/modules/buyer.md`(1단계 산출) · `flow.md §1`(운영 흐름·편의 장치) ·
  CLAUDE.md `Admin UI Convention — Toast Feedback` · 1단계 인계 메모
- **건드리는 레포 · 배포 순서**: klow_admin. 서버(1단계)가 먼저 — 뒤집으면 모든 화면 404 토스트
- **스키마·데이터 위험**: 없음
- **할 일** (세션 안 순서 = 정지점)
  1. `lib/api/buyer.ts`(DTO + `buyerApi`, 배럴 export) · `Sidebar.tsx` `NAV` 에 그룹 **"바이어 공간"**(lucide 아이콘
     필수 · **모든 어드민** — `superOnly` 없음, 2026-10-04 사용자 결정; `/buyer` 브랜드 · `/buyer/home` 홈 구성 ·
     `/buyer/inquiries` 문의) · `components/tabs/routeLabels.ts` 에 `/buyer`·`/buyer/brands`·`/buyer/products`·
     `/buyer/home`·`/buyer/inquiries` 를 **각각** 등록(접두 최장일치라 상세 라우트도 이 라벨을 탄다 — 안 넣으면
     탭 제목이 경로 조각이 된다)
  2. `/buyer` — 올린 브랜드 카드 목록(로고·이름·공개 토글·`필수 완비 제품 n/m`·드래그 순서) +
     "브랜드 추가" 검색 모달
  3. `/buyer/brands/[brandId]` — 상단 브랜드 프로필 폼(지역은 칩 멀티선택, 로고 교체/원본으로) +
     하단 제품 표(썸네일·이름·**필수 7칸 누락 점 표시**·카테고리 드롭다운·노출 불가 사유·공개 토글·체크박스
     일괄 카테고리/공개). ⚠️ 표의 "빼기"는 **공개 OFF** 다 — 바이어 행 삭제(입력값 전부 소멸)는 행 메뉴의 별도
     항목 + 확인 모달. 공개 ON 인데 노출 제품 0 이면 브랜드 상단에 "바이어 화면에 안 보임" 경고
  4. `/buyer/products/[productId]` — ⚠️ **`useFormState` 를 쓰지 않는다** — 저장 후 `router.push(redirectPath)` 로
     떠나고 dirty 추적이 없어서 연속 편집과 맞지 않는다. 전용 상태 + 토스트 직접 호출(CLAUDE.md 규칙) +
     **미저장 경고**(`beforeunload` + 페이지 안 링크 이동 확인 — 어드민에 선례가 0건이라 새로 만든다).
     버튼은 `저장` / **`저장하고 다음 미완비 제품 →`**(`nextIncompleteProductId`, 2026-10-04 사용자 결정 — 대량 입력은
     화면 연속 편집으로 한다) / `← 브랜드로`(iframe 탭이라 같은 탭 안 이동이다). 2단 레이아웃. 좌: 섹션 카드(기본·인증·도매가·상세·이미지),
     우: sticky **미리보기**(바이어 카드 4:5 + PDP 상단 배지·구간가 표). 선례 `components/preview/ProductPreviewPanel.tsx`
     (klow_web PDP 의 **로컬 미러 컴포넌트**, iframe 아님)를 따라 `components/preview/BuyerPreview*.tsx` 로 만들고 파일
     머리에 "`KLOWBUYER/` · klow_web 바이어 화면과 동기화" 주석을 단다. CSS 는 `.kb-preview` 스코프, 폰트는 어드민에
     `next/font` 가 없으니 시스템 폰트 폴백을 허용한다(레이아웃 확인용). 가격 입력은 **달러로 받고 센트로 변환**. 구간가 "자동 채우기"(MOQ·기준가는 **생성용 입력일 뿐 저장되지 않는다** — 저장되는 건 표, G10) · 이미지 업로드(`lib/upload.ts`)·
     4:5 크롭(`ImageCropModal` 은 `aspect={4/5}` 그대로 됨. `MultiImageUpload` 는 크롭이 없어 **새 `BuyerImageList`** 를
     만든다 — 업로드 시 크롭 + 기존 이미지 재크롭(1단계 `image-source` 또는 R2 CORS) · preset `product-main`)·
     **`@dnd-kit` 추가로 드래그 정렬**(어드민에 DnD 라이브러리 0개 — klow_brand 버전에 맞춘다)·**원본 상세컷에서 골라 넣기**(`originalImages` 피커)·원본으로 되돌리기 ← **정지점**
  5. `/buyer/home` — 탭 3개: 카테고리(이름 인라인 편집·드래그 순서·소속 제품 수 표시·**제품이 있으면 삭제 비활성**) ·
     히어로(이미지는 디자인 프레임 비율 4/4.6 로 크롭·연결 제품·캡션·순서) · 선반(제목·리드·4/8·**노출 제품만 고르는**
     피커 모달·태그·순서). 선반·히어로가 가리키는 제품이 비노출이 되면 "비노출" 배지(공개 API 는 자동 제외)
  6. `/buyer/inquiries` — 목록(종류·브랜드/제품·회사·이메일·상태) + 상세 드로어(처리 완료·메모)
- **완료 기준**
  - 모든 저장/삭제/오류가 토스트(CLAUDE.md 규칙) · `npm run build` 통과
  - 화면: 브랜드 추가(후보에 승인 브랜드만) → 제품 3개 추가 → **"저장하고 다음"** 으로 셋을 연달아 채움 → 미저장 상태로
    탭 이동 시 경고 → 브랜드 원본 이미지를 4:5 로 재크롭해 저장 → 미리보기가 입력과 함께 바뀜 → 이미지 순서 바꾸고 새로고침
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

세션 안 순서: ② **라우트 그룹 `app/(buyer)/`** 신설 — `(buyer)/layout.tsx`(중첩 레이아웃: Geist `next/font` · `.kb`
래퍼 · 바이어 Header/Footer · 메타데이터) + `(buyer)/page.tsx` · `(buyer)/shop/brands/[slug]` · `(buyer)/shop/products/[id]`.
⚠️ **`app/page.tsx`(redirect)를 같은 커밋에서 지운다** — `/` 가 두 곳에서 정의되면 빌드가 깨진다. `KLOWBUYER/app/globals.css`
를 `.kb` 스코프로 이식(G8). 소비자 크롬 정리: `Footer.tsx` 의 숨김 판정에 바이어 경로 추가(선례 `isB2bBuyerPath`) ·
BottomTabBar·Onboarding 은 `/` 가 원래 대상 밖이라 무변경 → ③ `/` 홈(HeroSlides · Collection:
Curated 선반 / All / 카테고리 탭 + 검색 · 브랜드 로고월 + 패널) → ④ `/shop/brands/[slug]` · `/shop/products/[id]`
(갤러리 · 인증 배지 · 구간가 표 + 수량 계산기 · 상세 스펙 · More from brand) → ⑤ Request 드로어 →
`POST /v1/buyer/inquiries` → ⑥ 구 `/shop`·`/shop/search`·`/shop/recommendations` 삭제(①로 참조가 이미 0건),
onboarding 자동 노출 경로·`sitemap.ts` 정리 → ⑦ 결정 기록(`decisions/storefront.md` +
`decisions/README.md` + CLAUDE.md 색인) · CLAUDE.md `klow_web pages` 갱신 · staging push 안내

⚠️ 웹 점검에서 정한 것 (2026-10-04, `§6` 표가 근거)
- **렌더링**: 페이지는 **서버 컴포넌트**가 `API_BASE` 로 `/v1/buyer/*` 를 받아 그리고(`sitemap.ts`·`lib/brand-server.ts` 선례),
  `generateMetadata` 로 브랜드·제품별 메타. 탭·검색·계산기·드로어·히어로 슬라이드만 클라이언트 컴포넌트.
  fetch 는 **`revalidate: 60`** — 어드민 수정이 최대 1분 뒤 보인다(어드민 화면에 한 줄 안내).
  ⚠️ Vercel 서버의 SSR fetch 는 **같은 egress IP 묶음**이라 서버 전역 throttle(60회/분/IP)에 걸릴 수 있다 — ISR 캐시가
  그걸 막는 장치이므로 `cache: 'no-store'` 로 바꾸지 말 것
- **카테고리 탭·검색**은 클라이언트에서 `GET /v1/buyer/products?category=&q=` (TanStack Query). 홈 SSR 은 선반·브랜드·카테고리만
- **Next 15 → 14 변환**: 디자인은 `params: Promise<…>` + `await params` · `generateStaticParams`(mock) 를 쓴다 →
  Next 14 동기 `params`, `generateStaticParams` 삭제(데이터가 동적). `?ask=`·`?lang=` 쿼리 처리도 뺀다
- **이름 충돌**: klow_web 에 이미 `components/b2b/Buyer{Storefront,ProductCard,ProductDetail,Cart}` 가 있다(브랜드 B2B 링크).
  새 코드는 **`components/buyer-space/`** + `Kb*` 접두, API 네임스페이스 `api.buyerSpace` — 같은 "Buyer" 이름 둘이면 다음 세션이 헷갈린다
- **이미지**는 디자인처럼 `<img loading="lazy">`(어드민이 이미 WebP 1600w 로 올린다 — Vercel 이미지 변환 비용을 늘리지 않는다)
- **검색 노출**(2026-10-04 사용자 결정): `/`·브랜드·제품 **index**. `sitemap.ts` 에서 `/shop*` 3줄을 빼고 바이어 브랜드·제품을
  **노출 중인 것만** 추가. 루트 `app/opengraph-image.tsx`(소비자 KLOW)를 `/` 가 물려받으므로 `(buyer)/opengraph-image.tsx` 를 따로 둔다
- ⚠️⚠️ **배포 후 점진 등록**(사용자): 운영에 나가는 순간 `/` 는 브랜드 0~몇 개 상태다. **비어도 깨져 보이지 않아야 한다** —
  노출 제품 0 인 선반·카테고리 탭·로고월은 섹션째 숨기고, 히어로가 0장이면 디자인 기본 히어로(정적 이미지)로,
  Collection 이 비면 "New brands are being added" + Request a brand CTA. 완료 기준에 **빈 DB 로 `/` 렌더**를 넣는다
- ⚠️ **정적 이미지 저작권**: 디자인 `public/img/` 의 연출컷(`hero.jpg`·`dark.jpg`·`facial.jpg` 등)은 출처가 확인되지 않았다.
  `p01~p24.jpg` 는 **가짜 브랜드 제품 사진**이라 절대 가져오지 않는다. 연출컷은 착수 시 출처·라이선스를 사용자에게 확인하고,
  불명이면 히어로 기본값을 어드민 업로드로 대신한다
- 사이트 트래픽 대시보드(19행)는 klow_web 전체 요청을 센다 — 배포 후엔 바이어 트래픽이 섞인다(결정 기록에 한 줄)

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

## §4 어드민 점검 기록 (2026-10-04)

계획 단계에서 어드민 코드와 **운영 DB(읽기 전용 SELECT)** 를 대조해 찾은 것. 위 1·2단계 명세에 이미 반영했다.

| # | 찾은 것 | 근거 | 반영 |
|---|---|---|---|
| R1 | 원본 텍스트는 **영어**다(제품명 한글 0/263 · 브랜드명 0/49). 번역 캐시(`ProductTranslation` en)는 0행 | 운영 SELECT | 프리필은 원본 그대로. 한글 감지 로직 불필요 |
| R2 | 원본이 **대부분 빈칸** — 성분 83% · 용량 76% · 원산지 ~76% · 유통기한 ~78% · 상세설명 거의 전부 · **이미지 아예 없음 35%(93/263)** | 운영 SELECT | 프리필은 보조일 뿐. **연속 편집**(`저장하고 다음 미완비 →`) + 칸별 누락 표시가 본체. 엑셀 왕복·AI 초안은 하지 않는다(사용자 결정) |
| R3 | 제품명에 운영 메모가 섞여 있다 — `(ONLY@ SURF EXPO SAMPLE SALE 15$) …`, `(MIN 1 BOX 72EA, ONLY FOR RETAILER …` | 운영 SELECT | `nameEn` 덮어쓰기 칸을 편집기 첫 칸에 둔다 |
| R4 | 브랜드 49 = 승인 28 · pending 8 · draft 13, 제품 263 중 pending 57 | 운영 SELECT | 후보·노출 = **승인만**(사용자 결정, G4) |
| R5 | `useFormState` 는 저장 후 다른 경로로 이동하고 dirty 추적이 없다 · 어드민 전체에 미저장 경고 선례 0건 | `hooks/useFormState.ts` | 제품 편집기는 전용 상태 + 미저장 경고 신설 |
| R6 | `MultiImageUpload` 는 크롭·정렬 불가, DnD 라이브러리 없음 · `ImageCropModal` 은 `File` 만 받는다 | `components/*Upload.tsx` | `BuyerImageList` 신설 + `@dnd-kit`. 기존 URL 재크롭은 R2 CORS 확인 → 안 되면 화이트리스트 프록시 |
| R7 | 탭 라벨은 접두 최장일치 정적 목록 · iframe 탭이라 `<Link>` 이동은 같은 탭을 갈아끼운다 | `components/tabs/*` | `/buyer/*` 라벨 5개 · 편집기에 `← 브랜드로` |
| R8 | 감사 로그는 본문 **10KB 초과 시 잘린다** — 성분 8000자 + About 4000자 PATCH 는 잘릴 수 있다 | `admin-audit.interceptor.ts:14` | 수용(앞부분으로 충분). 한도를 올리지 않는다 |
| R9 | zod v4 `.partial()` default 주입 버그 | `common/validation/shared.ts:60` | 모든 Patch 스키마 `patchOf()` |
| R10 | 카테고리 삭제가 `SetNull` 이면 소속 제품이 필수 미달 → 바이어 화면에서 **조용히 사라진다** | 설계 검토 | 소속 제품 있으면 409 · 화면에서 삭제 비활성 |
| R11 | 브랜드 표의 "빼기"가 행 삭제면 입력한 12칸이 cascade 로 소멸 | 설계 검토 | 빼기 = 공개 OFF, 삭제는 별도 메뉴 + 확인 |
| R12 | 편집기 저장이 필드 PATCH + 구간가 PUT 둘이면 반쪽 저장 가능 | 설계 검토 | `tiers` 를 PATCH 에 넣어 한 트랜잭션 |
| R13 | 원본 로고 없음: 승인 브랜드 28 중 3 | 운영 SELECT | `logoUrl` 업로드 or 텍스트 워드마크 폴백(디자인과 동일) — 필수 아님 |

## §5 서버 점검 기록 (2026-10-04)

1단계 명세를 코드와 대조해 찾은 것. 위 §1·§2·1단계에 이미 반영했다.

| # | 찾은 것 | 반영 |
|---|---|---|
| S1 | MOQ 가 브랜드·제품·구간표 세 곳에 따로 있어 모순 저장 가능 | 구간표가 정본(G10), MOQ 컬럼 삭제 — **사용자 결정** |
| S2 | 카드 대표가가 어느 구간인지 미정(디자인은 샘플가=MOQ가라 드러나지 않음) | MOQ 구간가(G11) — **사용자 결정** |
| S3 | `retailMultiple` 이 `Decimal` — 입력값이 실제 가격과 따로 놀고, Decimal 직렬화 부담 | 컬럼 삭제, 노출 제품에서 계산 |
| S4 | 문의 스키마가 디자인 드로어와 달랐다(`company` 필수인데 디자인엔 칸이 없고 `Brand or product` 칸이 스키마에 없음) | `subject`·`needs`·`market`·`email` 로 정정 · honeypot · ip |
| S5 | SQL 시드에 `cuid()` 기본값이 안 걸린다 | id 명시 + `--create-only` 로 SQL 편집 |
| S6 | 서버에 동영상 URL 판별 헬퍼가 없다(원본 대표사진 폴백에 필요) | `buyer-completeness.ts` 에 확장자 판별 |
| S7 | `THROTTLE_TIGHT` 는 공용 export 가 아니라 컨트롤러 로컬 상수 | 로컬 선언 |
| S8 | 완비를 컬럼으로 저장하면 원본 `image`·`status` 변경에 낡는다 | 읽을 때 계산(규모 수백 행) |
| S9 | 비공개 제품을 id 로 찌르면 존재가 샐 수 있다 · 제품의 브랜드가 바뀌면 오버레이가 엉뚱한 브랜드 밑에 남는다 | G12 |
| S10 | 순서 변경 API 가 일부 id 만 받으면 동시 편집 때 순서가 섞인다 | 정확한 id 집합만 허용 |
| S11 | 문의의 브랜드·제품 FK 가 Cascade 면 브랜드를 빼는 순간 영업 기록이 사라진다 | SetNull |
| S12 | dev Resend 키가 실발송 | 테스트 시 `RESEND_API_KEY=` |
| S13 | 이미지 재크롭 프록시는 SSRF 축 | 호스트 화이트리스트 + R2 CORS 로 대체 가능하면 만들지 않음(1단계 명세) |

## §6 웹 점검 기록 (2026-10-04)

3단계 명세를 klow_web 코드와 대조해 찾은 것. 위 3단계에 이미 반영했다.

| # | 찾은 것 | 근거 | 반영 |
|---|---|---|---|
| W1 | `/` 를 바이어 홈으로 만들면서 기존 `app/page.tsx`(redirect)를 두면 같은 경로 이중 정의로 빌드 실패 | `app/page.tsx` | 라우트 그룹 `(buyer)` + 같은 커밋에서 삭제 |
| W2 | 루트 레이아웃이 소비자 크롬(Footer·탭바·온보딩·Toaster·환율/세션 마운트)과 `body` 배경·폰트를 모든 경로에 깐다 | `app/layout.tsx` · `globals.css:37` | 중첩 레이아웃 `(buyer)/layout.tsx` + Footer 숨김(선례 `isB2bBuyerPath`) + `body:has(.kb)` 예외 1줄(G8) |
| W3 | 디자인은 Next 15(`await params`·`generateStaticParams` mock), klow_web 은 Next 14.2 · React 18 | `KLOWBUYER/app/*/[id]/page.tsx` | 동기 params, static params 삭제 |
| W4 | 디자인은 전부 클라이언트 + mock — 검색 노출에 SSR·메타가 필요 | 사용자 결정(index) | 서버 컴포넌트 + `generateMetadata` + `revalidate: 60` |
| W5 | Vercel SSR fetch 는 egress IP 를 공유해 서버 전역 throttle 에 걸릴 수 있다 | `main.ts` throttle 주석 | ISR 캐시 유지(no-store 금지) |
| W6 | `components/b2b/Buyer*` 와 이름 충돌 | `components/b2b/` | `components/buyer-space/` + `Kb*` |
| W7 | 루트 `opengraph-image.tsx`(소비자)를 `/` 가 물려받는다 · sitemap 이 `/shop*` 3줄을 싣는다 | `app/opengraph-image.tsx` · `app/sitemap.ts:18-20` | `(buyer)/opengraph-image.tsx` · sitemap 교체 |
| W8 | 배포 후 점진 등록이라 운영 `/` 가 거의 빈 상태로 index 된다 | 사용자 답변 | 빈 섹션 숨김 + 기본 히어로 + 빈 Collection 안내, 빈 DB 렌더를 완료 기준에 |
| W9 | 디자인 정적 이미지의 출처 불명 · `p01~p24` 는 가짜 브랜드 제품 사진 | `KLOWBUYER/public/img/` | 제품 사진 반입 금지, 연출컷은 착수 시 라이선스 확인 |
| W10 | 구 `/shop` 의 `shop`·`discover` i18n 네임스페이스·`components/shop`·`discover` 가 `/shop` 전용 | grep | ⑥ 에서 함께 삭제(en 원본 + 8개 로케일). `lib/shopCategories` 는 남은 소비자가 없는지 grep 후 |
| W11 | 사이트 트래픽 대시보드에 바이어 트래픽이 섞인다 | 19행 | 결정 기록에 명시 |
