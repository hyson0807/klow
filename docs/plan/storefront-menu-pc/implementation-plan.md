# storefront-menu-pc — 손님 화면(klow_web) 메뉴 서랍 + PC 브랜드관

`klow_brand` 의 `b2bpc` 브랜치가 **스튜디오 목업 안에만** 만든 메뉴 서랍과 PC 레이아웃을
**손님이 실제로 보는 klow_web** 에 구현한다. 상태는 [`../../PROGRESS.md`](../../PROGRESS.md).

⚠️⚠️ **선행 게이트: 트랙 [`brand-menu-schema`](../brand-menu-schema/implementation-plan.md) 완료.**
서버가 `menuItems` 와 desktop 컬럼을 내려주지 않으면 그릴 것이 없다. klow_web 단독 트랙이다.

---

## §1 왜 이 트랙이 따로 있나

b2bpc 의 PC 화면(`BrandPageDesktop` 1560줄)과 메뉴 서랍은 **klow_brand 스튜디오 목업 안에서만
존재한다.** 손님이 보는 브랜드관의 정본은 klow_web 이고, 그쪽은 지금 이렇다.

- `BrandStorefront.tsx`(1422줄)와 `components/product/*` 전체에 **`md:`/`lg:`/`xl:` 브레이크포인트가
  0개**이고 `max-w-[580px] mx-auto` 로 고정돼 있다 — **데스크톱 레이아웃이 아예 없다.**
- 브랜드관 진입 글자는 `BrandStoryChip` 하나이고 메뉴 서랍이라는 개념이 없다.

즉 "PC 버전을 만든다"는 것은 목업을 옮겨 붙이는 일이 아니라 **klow_web 에 데스크톱 경로를 신설하는
일**이다. 그래서 스키마·스튜디오 트랙과 분리했다.

## §2 착수 게이트 — 불변식

- **G1. 라우트를 만들지 않는다.** 메뉴는 **화면 상태**(서랍 열림 + 선택된 줄)로만 둔다.
  [브랜드 스토리 결정](../../decisions/storefront.md#2026-08-25-2)이 `/{slug}/story` 를 포기한 이유가
  그대로 적용된다 — `[brandSlug]/[influencer]`(할인 링크)와 충돌하고, 미들웨어에 단어를 넣으면 그
  단어가 브랜드/인플루언서 슬러그로 **영구 예약**된다.
- **G2. 방문 통계를 건드리지 않는다.** 서랍 열기·메뉴 줄 전환은 비콘을 쏘지 않는다. 방문 중복 가드가
  **모듈 레벨 `Set`** 이라 새 진입점을 만들면 그 가드 밖이고, 퍼널 정의(`uniqueCartAdds ≤ uniqueVisits`)
  가 흔들린다.
- **G3. 모바일 폭은 무회귀여야 한다.** 이 트랙은 `lg:` 이상에 경로를 **추가**하는 것이고 기존 580px
  화면의 픽셀을 바꾸는 것이 아니다.
- **G4. 토큰 복제를 없앤다.** ⚠️⚠️ b2bpc 의 `brand-page-tokens.ts` 는 지금 **모바일 하드코딩 값의
  복제**이고 드리프트가 코드로 막혀 있지 않다(그 파일 주석이 수동 동기화를 인정한다). 이식하면서
  **모바일 컴포넌트가 그 토큰을 실제로 참조하도록** 바꾼다 — 안 하면 같은 값이 3벌(brand 목업 ·
  web 모바일 · web PC)로 갈린다.
- **G5. `@container` 유틸리티를 쓸 수 없다.** `tailwind.config.ts` 의 `plugins` 가 비어 있다(기존
  제약 — `StorefrontStatsBoard` 가 같은 이유로 `variant` prop 으로 갈렸다). b2bpc 처럼 arbitrary
  variant(`[container-type:size]`) + inline style 로 간다.

## §3 단계

⚠️⚠️ **이 트랙 전체가 대화 세션 하나다**(`PROGRESS.md` `§7` 2행). 아래 1~3은 세션 안의 순서이자
넘칠 때의 정지점이다. 마이그레이션이 없어 셋 중 가장 가볍다.


### 1. 메뉴 서랍 + 메뉴 페이지 렌더

- **읽을 것**: 이 문서 `§2`, `klow_web/src/lib/brand-story.ts` 의 크로스 레포 미러 주석,
  `klow_web/src/components/brand/{BrandStorefront.tsx, story/}`,
  [`decisions/storefront.md`](../../decisions/storefront.md) 의 2026-08-25 브랜드 스토리
- **건드리는 레포 · 배포 순서**: klow_web 단독(서버·brand 는 선행 트랙에서 이미 나갔다)
- **스키마·데이터 위험**: 없음
- **할 일**
  - `src/lib/brand-menu.ts` 신설 — `BrandMenuItem` 타입 + `shopRows` · `inMenuCategory` ·
    `menuItemLabel` 의 **읽기 전용 부분집합**. klow_brand 원본에서 편집용 옵션표(한국어 라벨)와
    `useBrandStory` 훅을 뺀 형태로, `brand-story.ts`·`brand-tags`·`page-fonts` 와 같은
    **의도된 크로스 레포 미러** 관례를 따른다
  - `StorefrontMenu` 서랍 + `MenuButton`(☰) + `MenuLocaleRow` 이식. 기존 `BrandStoryChip` 은 ☰ 로 대체
  - `BrandStoryView` 를 `page` 인자로 일반화 → `story` 줄과 `page` 줄이 **같은 뷰**를 쓴다
  - `products` 줄은 그리드를 `productIds` 로 좁히고, `shop` 줄은 제품 `categoryKey` 에서 그 자리에서
    만든다(서버에 저장된 행이 없을 수 있다 — 그게 정상이다)
  - ⚠️ 서랍 바닥 언어 줄은 i18n 이 아니라 `LOCALE_NAME` 상수(각 언어를 **그 언어 자국어로** 적은 표시명)다.
    klow_web 의 기존 로케일 전환에 배선하되 표기는 b2bpc 상수를 그대로 쓴다
- **완료 기준**
  - 5종 줄(`story`/`shop`/`page`/`products`/`link`)이 모두 정상 동작
  - 스튜디오 목업과 **같은 brand slug 로 좌우 비교**해 같은 것이 보인다
  - ⚠️ **메뉴 행이 0개인 브랜드는 `상점` 한 줄만** 보인다(빈 "Brand Story" 줄이 없다)

### 2. 브랜드관 PC 레이아웃 + circle 폴백 신설

- **할 일 (골격)**
  - `BrandStorefront` 를 `max-w-[580px]` 모바일 경로 + `lg:` 이상 데스크톱 경로로 가른다
  - `brand-page-tokens.ts` 를 klow_web 으로 가져오고 **모바일도 그것을 참조하게 한다**(§2 G4)
  - `desktopColumns` / `desktopHeroUrls` / `desktopFeaturedIds` 반영
  - **circle 전용 PC 히어로 폴백 신설** (2026-09-28 사용자 결정) — 대표사진 풀이 비면
    `엑센트 그라데이션 + 큰 원형 로고 + 브랜드명`, 로고도 없으면 그라데이션 + 브랜드명.
    b2bpc 의 `overPhoto=false` 경로를 그 디자인으로 대체한다
  - ⚠️ b2bpc PC 는 `BrowserFrame` 안에서 `transform: scale()` 로 축소돼 그려진다. **실물에는 프레임이
    없어 `position: fixed` 의 기준이 달라진다** — 모달·바텀시트를 눈으로 확인한다
  - ⚠️ `cqh` 단위를 쓰므로 실물에 **`100dvh` 래퍼**가 필요하다(b2bpc 주석이 그 전제를 명시한다)
- **완료 기준**: 칸 수 2/3/4 · 강조 2×2 · PC 대표사진 반영 ·
  ⚠️ **circle 폴백이 운영의 해당 4곳에서 제대로 보인다** · 모바일 폭 **무회귀**(§2 G3)

### 3. 제품 상세 PC 레이아웃 + 운영 배포

- **할 일 (골격)**: `product/[id]` + `components/product/*` 에 데스크톱 경로
  (b2bpc `ProductDetailPreview` 의 `variant="desktop"` = `grid-cols-[1fr_440px]`, hero aspect `1/1`).
  가격·환율·번역 훅은 공유한다. `addToCart` i18n 키를 8로케일에 추가
- **완료 기준**: PC 로 브랜드관을 보다가 제품을 눌러도 **모바일 폭으로 튕기지 않는다** ·
  장바구니·바로구매 2버튼 동작 · 스테이징 확인 → 운영 배포
- **배포 순서**: klow_server → klow_brand → klow_web.
  ⚠️ **운영 마이그레이션 큐** — 운영은 마이그레이션 164개로 dev(167)보다 3개 적다. 3PL·카페24가 아직
  운영에 없어 이 트랙의 마이그레이션은 **그 뒤 4번째**로 줄을 선다(cafe24 배포가 선행)

## §4 운영 실측 — PC 히어로 가용성 (2026-09-28 · SELECT 만)

approved 26곳 기준. `desktopHeroUrls` 가 비면 `logosWide → logosTall` 로 내려간다.

| 로고 레이아웃 | 브랜드 | PC 히어로 사진 있음 | 원형 로고 | 로고 전무 |
|---|---|---|---|---|
| wide | 18 | 17 | 7 | 1 |
| circle | 5 | 2 | 4 | 1 |
| tall | 3 | 3 | 2 | 0 |
| **합계** | **26** | **22 (85%)** | 13 | 2 |

→ 운영은 `wide` 가 주류라 **85%가 이미 PC 16:9 히어로에 쓸 사진을 갖고 있다.** 사진이 없는 곳은
**4곳**이고 그중 2곳은 원형 로고가 있다 — 2단계의 circle 폴백이 그 4곳을 받는다.

⚠️ **dev DB 브랜치는 circle 이 주류라 정반대 그림(26곳 중 5곳만 사진 보유)을 준다.**
판단 근거는 운영 수치다.
