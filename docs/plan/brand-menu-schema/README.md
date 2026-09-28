# brand-menu-schema — 브랜드관 메뉴·PC 설정 정규화

`klow_brand` 의 `b2bpc` 브랜치가 목업으로 만든 **메뉴탭**과 **PC 버전 설정**을 서버에 정규화해 얹는다.
세 트랙(`brand-menu-schema` → `storefront-menu-pc` · `b2b-wholesale`)의 **기반**이고, 나머지 둘은
이 트랙이 끝나야 착수할 수 있다.

## 읽는 순서

| 파일 | 정본 범위 |
|---|---|
| `README.md` (이 문서) | 결정 요약 · 무엇이 왜 이렇게 되었나 |
| [`implementation-plan.md`](./implementation-plan.md) | **빌드 스펙 정본** — 1~4단계 명세와 불변식 |

상태(어디까지 왔나)는 여기 적지 않는다 — [`../../PROGRESS.md`](../../PROGRESS.md) 가 유일한 정본이다.

## 한 문단 요약

b2bpc 는 브랜드관의 진입 구조를 **`Brand Story` 글자 하나 → ☰ 메뉴 서랍**으로 바꿨다. 서랍의 줄은
스토리·상점·자유 페이지·제품 묶음·외부 링크 5종이고, 브랜드가 이름과 순서를 직접 정한다. 같은 작업에서
**PC(데스크톱) 브랜드관**이 생겨 칸 수·강조 제품·PC 전용 대표사진 3가지 설정이 추가됐다.

그 값들은 지금 **아무 데도 저장되지 않는다.** b2bpc 는 `Brand.story` Json 에 `menu`·`desktop` 키를
얹어 보내는데, 서버 `BrandStorySchema` 가 `.strict()` 없는 평범한 `z.object` 라 **모르는 키를 400 없이
조용히 버린다.** 그래서 프론트가 `localStorage['klow.brand.menu.v1']` 에 임시 보관하고 있고, 다른
기기·다른 사람·손님 화면에는 아무것도 나가지 않는다.

이 트랙은 그 값을 **정규화한 테이블 3벌**(`BrandMenuItem` · `BrandPage` · `BrandPageChapter`)과
**`Brand` 스칼라 컬럼 3개**(PC 설정)로 받아 저장한다.

## 결정 요약

### 1. Json 에 더 쌓지 않고 정규화한다 (2026-09-28 사용자 결정)

`Brand.story` Json 한 칸에 `menu` 를 넣는 것이 가장 작은 작업이지만 셋을 포기하게 된다.

- **번역이 구조적으로 막힌다.** `BrandTranslation` 은 스칼라 컬럼 모델이라 Json 배열을 번역할 수 없다.
  이것이 [공지 팝업](../../decisions/storefront.md#2026-09-18)이 Json 대신 테이블을 고른 바로 그 이유다.
  메뉴 `label` 과 페이지 본문은 **해외 손님이 읽는 글자**다.
- **`PUT /v1/brand/applications` 의 400 트랙이 커진다.** `story` 는 그 PUT 의 **전체 문서 한 칸**이라
  스토리 한 글자가 상한을 넘으면 색·폰트·링크까지 아무것도 저장되지 않는다(그 파일 주석이 명시한
  함정). 메뉴가 들어오면 최대 `8줄 × 12챕터 = 96챕터` + 강조 제품 200개가 한 PUT 에 실리고 800ms
  자동저장마다 전부 왕복한다.
- **`story` 라는 이름이 거짓이 된다.** 그 칸이 브랜드관 전체의 내비게이션과 PC 레이아웃과 N개 페이지를
  담게 된다.

### 2. 스토리는 특별 취급을 받지 않는다 — 보통 메뉴 행이다

정규화의 부수 효과가 이 트랙의 **가장 중요한 이득**이다.

b2bpc 의 손님측 필터 `isMenuItemVisible` 은 스토리 줄에 `story.enabled` 만 보고, 현행 klow_web 의
`enabled && !empty` 가드가 빠져 있다. `enabled` 기본값이 `true` 라 그대로 내면 **스토리를 만든 적 없는
브랜드가 빈 페이지로 가는 "Brand Story" 줄을 얻는다** — 운영 기준 최대 41곳이다.

정규화하면 스토리가 `kind='story'` + `pageId` 인 **보통 메뉴 행**이 되고, 백필은 **내용이 있는
브랜드에만** 그 행을 만든다. 행이 없으면 줄이 없다. **프론트 가드가 필요 없고 회귀가 구조적으로
불가능하다.**

ℹ️ b2bpc 의 B2B 쪽(`buyer-menu.ts` `buyerMenuStory()`)은 이미 **빈 페이지 줄을 제거**한다. 즉 같은
브랜치 안에서 B2B 는 옳게 처리했고 홈 메뉴만 빠뜨린 것이다.

### 3. 기본 메뉴는 데이터가 아니라 규칙 — 읽기 시점에 합성, 백필 없음

메뉴 행이 0개인 브랜드에는 `상점` 한 줄만 합성한다. `상점`은 제품 `categoryKey` 에서 파생되므로
저장할 것이 없다 — b2bpc 의 `shopRows`/`materializeShopRows` 가 이미 그 방식이고, 브랜드가 손대는
순간에만 실제 행이 생긴다. **전 브랜드에 기본 메뉴를 심는 백필을 하지 않는다.**

### 4. PC 설정은 `Brand` 스칼라 컬럼 — DB 기본값이 빈 화면을 원천 차단

`desktopColumns Int @default(3)` 이 기존 전 행을 자동으로 덮고, 대표사진은
`desktopHeroUrls → logosWide → logosTall → circle 폴백` 순으로 내려간다. **어느 경로에서도 빈 화면이
나오지 않고 백필이 필요 없다.**

⚠️ `hero`/`columns`/`featured` 는 서로 독립된 스칼라 3개이고 중첩 구조가 없어서 테이블로 뺄 이유가
없다. 메뉴와 같은 취급을 하지 말 것.

### 5. `Brand.story` Json 은 드롭하지 않는다 + 이행 어댑터

`DROP COLUMN` 은 롤링 배포에 안전하지 않고, 원본을 지우면 백필이 틀렸을 때 되돌릴 수 없다.
dormant 로 남긴다(`ShippingCountry.productLogisticsCostKrw` 선례).

⚠️⚠️ 그래서 **배포 창 동안 구 klow_brand 가 계속 `story` 를 PUT 한다.** 무시하면 그 창의 스토리 편집이
조용히 유실되고, 그대로 Json 에 쓰면 Json 과 테이블이 갈려 정본이 둘이 된다.
→ **서버가 들어온 legacy `story` 를 테이블로 번역한다**(expand/contract). Json 컬럼에는 더 이상 쓰지
않는다. klow_brand 배포가 끝나면 그 어댑터는 죽은 코드가 되고 이후에 걷어낸다.

## 운영 실측 (2026-09-28 · SELECT 만)

브랜드 47곳(approved 26 · draft 13 · pending 8). 스토리 실사용: `story` 있음 **14** ·
**챕터 있음 6** · 제목 3 · `enabled:true` 6.

→ **백필 대상은 내용이 있는 행만 6~9곳.** 나머지 33곳은 `story` 자체가 없다.

⚠️ dev DB 브랜치에는 같은 질의가 다른 그림(브랜드 51곳 · 챕터 0건)을 준다. **판단 근거는 운영 수치다.**
