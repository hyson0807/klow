# brand-menu-schema — 구현 계획 (빌드 스펙 정본)

결정 요약과 논거는 [`README.md`](./README.md). 여기엔 **무엇을 어떤 순서로 만드는가**만 둔다.
상태는 [`../../PROGRESS.md`](../../PROGRESS.md).

---

## §1 착수 게이트 — 불변식

착수 전에 읽고, 어기면 되돌아간다.

- **G1. 디자인을 바꾸지 않는다.** b2bpc 의 프레젠테이션 컴포넌트(`brand-menu/` 6파일 ·
  `storefront-preview/menu/` 3파일 · `BrandPageDesktop`)는 **손대지 않는 것이 목표**다. 이 트랙이
  바꾸는 것은 데이터 흐름뿐이다.
- **G2. `PUT /v1/brand/applications` 에 메뉴를 얹지 않는다.** 줄 단위 엔드포인트로 가는 것이
  "한 칸 400 이 전 저장을 죽인다"는 함정의 해소 그 자체다.
- **G3. 상한은 klow_brand 상수를 글자 단위로 옮긴다.** 어긋나면 zod 400 이 나고, 그 400 은 브랜드가
  원인을 알 수 없는 저장 실패로 보인다.
  | 값 | 상한 | klow_brand 상수 |
  |---|---|---|
  | 메뉴 줄 이름 | 24 | `BRAND_MENU_LABEL_MAX` |
  | 최상위 줄 수 | 8 | `BRAND_MENU_MAX_ITEMS` |
  | 상점 아래 칸 수 | 16 | `BRAND_MENU_SHOP_SECTION_MAX` |
  | `productIds` | 200 | (`normalizeMenu` 내 slice) |
  | 외부 링크 URL | 500 | (`newMenuItem` 주석) |
  | 페이지 제목 / 소개 | 60 / 200 | `STORY_TEXT_LIMITS` |
  | 챕터 소제목 / 본문 | 60 / 1200 | `STORY_TEXT_LIMITS` |
  | 챕터 수 | 12 | `BRAND_STORY_MAX_CHAPTERS` |
  | PC 대표사진 | 20 | `BRAND_DESKTOP_HERO_MAX` |
  | PC 칸 수 | 2 \| 3 \| 4 | `BRAND_DESKTOP_COLUMN_OPTIONS` |
  | PC 강조 제품 | 200 | (`normalizeDesktop` 내 slice) |
- **G4. `id` 는 서버가 만들고 프론트는 받은 그대로 쓴다.** 서버가 id 를 새로 만들어 돌려주거나 프론트가
  임시 id 를 `key` 로 쓰면, 응답이 도착할 때 입력칸이 remount 되어 **타이핑 중 커서와 포커스가
  날아간다.** 기존 `BrandStoryChapterSchema.id` 주석이 같은 이유로 `default` 를 금지한다.
- **G5. 빈 스토리에는 메뉴 행을 만들지 않는다.** 백필과 어댑터 양쪽에서. 이것이 최대 41곳에 걸리는
  회귀를 막는 유일한 지점이다.
- **G6. `Brand.story` Json 컬럼에 새로 쓰지 않는다.** 읽기 정본은 테이블 하나다.

---

## §2 스키마

`CREATE TABLE` 3개 + `Brand` 컬럼 3개 + enum 3~4개. **DROP 0건 → 롤링 안전.**

```prisma
enum BrandMenuKind { story shop page products link }
// StoryPhotoRatio(wide square portrait tall) · StoryTextScale(sm md lg) ·
// StoryTextAlign(left center right) — 기존 zod enum 과 값이 글자 단위로 같아야 한다.

model BrandMenuItem {
  id          String  @id @default(cuid())
  brandId     String
  /// 서랍에 서는 순서. 배열 순서 = 표시 순서.
  sort        Int
  kind        BrandMenuKind
  /// 빈 값이면 프론트가 종류별 기본 이름으로 폴백한다(서버는 채우지 않는다).
  label       String  @default("") @db.VarChar(24)
  hidden      Boolean @default(false)
  /// kind=link 전용.
  url         String  @default("") @db.VarChar(500)
  /// kind=products 전용. 비어 있으면 categoryKey 를, 그것도 없으면 전체 제품을 뜻한다.
  productIds  String[]
  /// 레거시 프리셋 분류. productIds 가 빌 때만 본다.
  categoryKey String?
  /// kind=story|page 전용.
  pageId      String? @unique
  page        BrandPage? @relation(fields: [pageId], references: [id], onDelete: SetNull)
  brand       Brand @relation(fields: [brandId], references: [id], onDelete: Cascade)
  @@unique([brandId, sort])
  @@index([brandId])
}

/// 스토리 본체와 자유 페이지가 같은 테이블이다 — 둘은 같은 뷰가 그리는 같은 것이다.
/// 어느 페이지가 '스토리'인지는 그것을 가리키는 BrandMenuItem.kind 가 말한다.
model BrandPage {
  id         String  @id @default(cuid())
  brandId    String
  coverImage String? @db.VarChar(500)
  coverRatio StoryPhotoRatio @default(portrait)
  title      String  @default("") @db.VarChar(60)
  subtitle   String  @default("") @db.VarChar(200)
  /// 챕터 사진 프레임은 페이지 공통이다(한 페이지에서 비율이 섞이지 않게).
  photoRatio StoryPhotoRatio @default(square)
  photoBleed Boolean @default(false)
  /// null = 브랜드관 배경을 그대로 따른다.
  bgColor    String? @db.VarChar(9)
  bgGradient Int     @default(0)
  textScale  StoryTextScale @default(md)
  chapters   BrandPageChapter[]
  menuItem   BrandMenuItem?
  brand      Brand @relation(fields: [brandId], references: [id], onDelete: Cascade)
  @@index([brandId])
}

model BrandPageChapter {
  id      String  @id @default(cuid())
  pageId  String
  sort    Int
  image   String? @db.VarChar(500)
  heading String  @default("") @db.VarChar(60)
  body    String  @default("") @db.VarChar(1200)
  align   StoryTextAlign @default(left)
  page    BrandPage @relation(fields: [pageId], references: [id], onDelete: Cascade)
  @@unique([pageId, sort])
}
```

`Brand` 에 PC 설정 스칼라 3개 — **기본값이 기존 전 행을 자동으로 덮는다(백필 불필요).**

```prisma
  /// PC 브랜드관 한 줄 칸 수. 4칸은 큰 모니터에선 시원하지만 노트북(1280)에서 카드가 작아지고,
  /// 2칸은 제품이 열 개만 돼도 스크롤이 길다 — 그래서 3이 기본이다.
  desktopColumns     Int      @default(3)
  /// PC 전용 16:9 대표사진. 비면 logosWide → logosTall → circle 폴백 순으로 내려간다.
  desktopHeroUrls    String[]
  /// 2×2 로 크게 세울 제품 id. 지워진 제품 id 가 남아 있어도 해가 없다(그리는 쪽이 목록과 교집합만 쓴다).
  desktopFeaturedIds String[]
```

⚠️ **`Brand.story` Json 은 드롭하지 않는다** — dormant 로 남긴다(§1 G6 · README 결정 5).

---

## §3 단계

### 1. b2bpc → `feat/storefront-b2b` 머지 · 정합

- **읽을 것**: 이 문서 `§1`, [`decisions/brand-account.md`](../../decisions/brand-account.md) 의
  2026-09-18 3항목(탭 재편 · 재고 탭 · 주문 탭 톤),
  [`decisions/storefront.md`](../../decisions/storefront.md) 의 2026-08-25 브랜드 스토리
- **건드리는 레포 · 배포 순서**: klow_brand 단독 · **배포 없음**
- **스키마·데이터 위험**: 없음
- **할 일**
  - `staging` 기준으로 `feat/storefront-b2b` 를 판 뒤 `origin/b2bpc` 를 머지한다.
    ⚠️ b2bpc 는 `d9dea8a`(2026-09-18) 이후 staging 의 8커밋을 모른다 — 특히 스튜디오 `재고` 탭
    복귀(`8677002`)와 3PL·카페24 머지(`343424b`).
  - 충돌 후보 **7파일**을 아래 규칙으로 정합한다.
    | 파일 | 규칙 |
    |---|---|
    | `studio/page.tsx` | ⚠️ b2bpc 의 `pinnedStudioTab` 에 `'inventory'` 가 없다 → **staging 쪽을 살린다** |
    | `IdlePanel.tsx` | 상위탭 `TABS`(`통계│디자인│주문│재고`)는 **staging 이 정본** |
    | `StudioPillHeader.tsx` | 양쪽이 각자 값을 추가했다(staging 정산 pill / b2bpc `'b2b'` pill) → **둘 다 남긴다** |
    | `DesignSubTabs.tsx` | b2bpc 의 5칸(`브랜드관│메뉴│꾸미기│링크│SNS`)을 취한다 |
    | `EditorPanel.tsx` | b2bpc 가 `EditorMode` 에서 `'brand-story'` 를 뺐다 → 그쪽을 취하되 재고 탭 배선은 유지 |
    | `StudioSkeleton.tsx` | 양쪽 변경이 겹치지 않는다 → 둘 다 |
    | `StorefrontStatsBoard.tsx` | 양쪽 변경이 겹치지 않는다 → 둘 다 |
- **완료 기준**
  - `npm run build` · `npx tsc --noEmit` · `npx eslint <바꾼 파일>` 통과
  - 브라우저로 스튜디오를 열어 **상위탭 4칸 + 디자인 서브탭 5칸 + 재고 탭 + 헤더 B2B pill** 이 모두
    살아 있음을 확인. ⚠️ dev 포트가 사용자 것과 겹치므로 `PORT=` 로 분리한다
- ⚠️ **순수 정합 단계다. 디자인을 고치지 않는다**(§1 G1).

### 2. 스키마 + 마이그레이션 + 백필

- **읽을 것**: 이 문서 `§1`·`§2`, `klow_brand/src/lib/brand-story.ts` 의 타입·상한 표 전문,
  `klow_server/src/common/validation/brand.ts` 의 `BrandStorySchema` 절 주석,
  [`decisions/storefront.md`](../../decisions/storefront.md) 의 2026-09-18 공지 팝업(Json 대신
  테이블을 고른 논거)
- **건드리는 레포 · 배포 순서**: klow_server 단독
- **스키마·데이터 위험**: ⚠️ **마이그레이션 + 백필이 있으므로 독립 세션**(PROGRESS `§4`).
  `CREATE TABLE` 3개 + `ADD COLUMN` 3개(전부 default 또는 배열) → **DROP 0건 · 롤링 안전.**
  `npx prisma migrate dev --name add_brand_menu_pages`.
  **DB 브랜치 `ep-solitary-morning-a1rygrkh`** 를 쓴다(실측 167개 적용 · 드리프트 없음).
- **할 일**
  - `§2` 스키마를 `prisma/schema.prisma` 에 넣는다.
  - 백필 `prisma/backfill/backfill-brand-menu.ts` + `npm run backfill:brand-menu`.
    **기본 dry-run · `-- --apply` 로만 반영**(`backfill:drop-logistics-markup` 선례).
    - 대상: `Brand.story` 가 있고 **내용이 비지 않은** 브랜드만. 판정은 klow_brand `isStoryPageEmpty`
      와 같은 규칙(커버·제목·소개·챕터가 모두 비었으면 빈 것)
    - 만드는 것: `BrandPage` 1행 + `BrandPageChapter` N행 +
      `BrandMenuItem{ kind:'story', sort:0, pageId, label: story.label, hidden: !(story.enabled ?? true) }`
    - ⚠️ **내용이 빈 브랜드에는 아무 행도 만들지 않는다**(§1 G5)
    - ⚠️ **멱등** — 이미 `BrandMenuItem` 행이 있는 브랜드는 건너뛴다. 배포 창에서 두 번 돌려도
      안전해야 한다(재실행이 구 코드로 저장된 건을 주워 담는다 — `backfill:brand-user-phones` 선례)
    - 운영 예상 대상: **6~9곳**
- **완료 기준**
  - dry-run 출력이 대상 브랜드 목록과 챕터 수를 정확히 보고한다
  - `-- --apply` 후 **재실행이 0건**(멱등 확인)
  - 검증 3층(PROGRESS `§4`). ⚠️ `typecheck` 는 **tsconfig 2개**를 돈다 — 백필 스크립트가
    `tsconfig.scripts.json` 쪽이라 `npx tsc --noEmit` 만으로는 안 잡힌다
  - ⚠️ `test:e2e` 의 **cron 기대 목록은 불변**(새 cron 없음)

### 3. 서버 API — 메뉴 줄 단위 CRUD · PC 설정 · 공개 응답

*(앞 단계가 끝나야 전제가 확정되므로 착수 세션에서 정밀화한다. 아래는 골격.)*

- **건드리는 레포 · 배포 순서**: klow_server 단독(2단계 마이그레이션 선행)
- **스키마·데이터 위험**: 없음
- **할 일 (골격)**
  - `src/modules/brands/brand-menu.controller.ts` (`@Controller('v1/brand/menu')` · BrandGuard) —
    목록 · 줄 생성/수정/삭제 · 순서 일괄 · 페이지 수정 · 챕터 일괄
  - `PATCH /v1/brand/desktop` — `columns` / `heroUrls` / `featuredIds`
  - `src/common/validation/brand-menu.ts` — 상한은 `§1 G3` 표 그대로
  - ⚠️ **이행 어댑터**: `updateApplication` 이 legacy `story` 를 받으면 테이블로 번역한다(README 결정 5).
    Json 컬럼에는 쓰지 않는다. 빈 스토리는 행을 만들지 않는다(§1 G5)
  - 공개 응답: `brand-selects.ts` 의 `PUBLIC_BRAND_DETAIL_SELECT` 에 `menuItems`(정적
    `orderBy: { sort: 'asc' }` + 중첩 `page.chapters`)와 desktop 컬럼 3개를 **중첩 select 로 얹는다**
    - ⚠️ **전용 라우트를 새로 만들지 않는다** — klow_web `[brandSlug]/page.tsx` 는 non-async 서버
      컴포넌트이고, 왕복을 더하면 이 서비스 최다 트래픽 페이지의 TTFB 에 얹힌다
      ([`storefront-stats`](../../decisions/storefront.md#2026-08-19-3) 결정문의 근거).
      공지 팝업이 전용 라우트로 뺀 이유는 `now` 였고 **메뉴는 `now` 가 없다**
    - ⚠️ `PUBLIC_BRAND_SELECT`(목록)에는 **넣지 않는다** — shop 캐러셀이 메뉴를 쓰지 않는다
  - [`server/modules/brands.md`](../../server/modules/brands.md) +
    [`brand-applications.md`](../../server/modules/brand-applications.md) 갱신(**필수**)
- **완료 기준**: `GET /v1/brands/by-slug/<slug>` 응답에 `menuItems`·`desktopColumns` 가 실림 ·
  구 klow_brand 가 보낸 `story` PUT 이 테이블에 반영됨(어댑터 확인) · 검증 3층 · 라우트 수 증가 확인

### 4. klow_brand 재배선 — 줄 단위 mutation · 로컬 보관소 은퇴

*(착수 세션에서 정밀화. 분량이 넘치면 `4-1`(메뉴) / `4-2`(PC 설정)로 쪼갠다.)*

- **건드리는 레포 · 배포 순서**: **klow_server(2·3단계) → klow_brand**(뒤집으면 새 엔드포인트가 404)
- **할 일 (골격)**
  - `useBrandStory` 클로저 + 단일 `applyBrandPatch({ story })` → `v1/brand/menu/*` 줄 단위 mutation
    (TanStack Query + optimistic update). **화면은 그대로 두고 데이터 흐름만 갈아끼운다**(§1 G1)
  - `src/lib/brand-menu-local.ts` **삭제** + `useBrandAutoSave` 의 `withLocalMenu` ·
    `rememberMenuIfDropped` · `lastSentStoryRef` 배선 제거 + `BrandMenuPane` 의 "브라우저에만 저장"
    amber 꼬리표 제거
    - ⚠️ 꼬리표만 지우고 보관소를 남기면 **로컬분이 서버값을 영구히 덮는다.** 함께 지운다
      (재고 탭 `DEMO_STOCK` 선례: 칩만 지우면 예시가 실데이터로 읽힌다)
  - PC 설정은 `PATCH /v1/brand/desktop`
  - ⚠️ `materializeShopRows` 는 이제 **서버 왕복**이다(여러 행을 한 번에 만든다) — `POST` 를 N번
    부르지 말고 일괄 엔드포인트나 트랜잭션 하나로 묶는다. 하나만 굳히면 "custom 이 있으면 custom 만"
    규칙에 걸려 나머지 칸이 사라진다
  - ⚠️ `id` 는 서버가 만든다(§1 G4)
- **완료 기준**
  - 메뉴 줄 추가·이름변경·정렬·숨김·삭제 / PC 칸 수·강조·PC히어로가 **새로고침 후 유지**
  - **다른 브라우저에서 같은 값**이 보인다
  - `localStorage` 에 `klow.brand.menu.v1` 가 더 이상 생기지 않는다
  - ⚠️ **스토리가 없던 브랜드의 메뉴에 빈 "Brand Story" 줄이 생기지 않는다**(핵심 회귀 확인)

---

## §4 이 트랙이 끝나면

- **트랙 `storefront-menu-pc`** (손님 화면)와 **트랙 `b2b-wholesale`** 의 게이트가 풀린다.
  후자는 `B2bMenu.hidden[]` 이 이 트랙의 메뉴를 물려받으므로 특히 직접적이다.
- 이 폴더는 `plan/` 을 떠난다. 판정은 *"이 문서가 현행 동작의 유일한 설명인가"* —
  `server/modules/brands.md` 가 엔드포인트를 갖게 되므로 **`archive/`** 가 될 가능성이 높다.
- 승격 후보: **"정규화가 빈 스토리 줄 회귀를 데이터에서 없앴다"** 와 **이행 어댑터** 는
  `decisions/storefront.md` 에 항목으로 올릴 값이 있다(다음에 코드를 만지는 사람이 몰라서 사고를
  내는가 → 예).
