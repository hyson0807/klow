# brands — 브랜드

- **모듈 경로**: `src/modules/brands/`
- **공개 필터**: `PUBLIC_BRAND_WHERE` = `Brand.status NOT IN (rejected, withdrawal_pending, withdrawn)` — 즉 `draft`/`pending`/`approved` 는 브랜드관 자체가 노출된다(탈퇴 신청 즉시 공개 surface 에서 제거). ⚠️ **제품 노출/판매 게이트는 이보다 엄격**해서 `Brand.status='approved'` + 구독 active 를 요구한다([products](./products.md) `PUBLIC_PRODUCT_WHERE`) — 두 필터를 혼동하지 말 것. 이미 fetch 한 row 검증용 JS 짝은 `isPublicBrand()`.
- **공통 select**: `brand-selects.ts` — `PUBLIC_BRAND_SELECT` 는 공개 노출 필드만 화이트리스트(`id`/`name`/`slug`/`tagline`/`description`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`logoLayout`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`/`order`/`status`/`createdAt`/`updatedAt`). 송화인·계좌·탈퇴 이력·`pgCustomerKey`·`category` 등 내부 필드는 공개 응답에 실리지 않는다.
- **공개 단건 select (2026-08-25, 2026-09-28 메뉴 추가)**: `PUBLIC_BRAND_DETAIL_SELECT = {...PUBLIC_BRAND_SELECT, story, desktopColumns, desktopHeroUrls, desktopFeaturedIds, menuItems{…page{…chapters}}}` — `by-slug`/`:id` 만 쓴다. ⚠️⚠️ **메뉴는 전용 라우트가 아니라 중첩 select 다** — klow_web `[brandSlug]/page.tsx` 는 non-async 서버 컴포넌트이고 왕복을 더하면 이 서비스 최다 트래픽 페이지의 TTFB 에 그대로 얹힌다. 공지 팝업이 전용 라우트로 뺀 이유는 `now` 가 필요해 모듈 최상위 `as const` 상수에 넣을 수 없어서였고 **메뉴에는 `now` 가 없다**(정적 `orderBy` 하나뿐). ⚠️ `story` Json 도 당분간 함께 내리지만 **dormant** 이고 읽기 정본은 `menuItems` 다. ⚠️ **`story` 를 `PUBLIC_BRAND_SELECT` 에 바로 넣으면 안 된다**: 그 select 는 목록(`findAll`)이 함께 쓰는데 거기는 **최대 200건**을 돌려주고 스토리는 챕터 12개면 10KB 를 넘어, 브랜드관과 무관한 shop 캐러셀 응답이 통째로 부푼다. ⚠️ 반드시 스프레드로 파생시킬 것 — 손으로 두 벌 쓰면 공개 필드가 한쪽에만 추가되어 목록과 단건의 노출 범위가 조용히 갈린다.
- **다국어**: 공개 단건(`by-slug`/`:id`)만 `?lang=` 을 받아 `BrandTranslationService.localize()` 로 brand 텍스트를 로케일 번역한다(목록은 번역 없음).
- **관련 파일**: `brands.service.ts`, `admin-brands.controller.ts`, `public-brands.controller.ts`, `admin-brand-withdrawals.controller.ts`, `brand-withdrawals.service.ts`, `brand-translation.service.ts`(브랜드 텍스트 다국어 — [translation](./translation.md) 래퍼), `brand-selects.ts`

## admin-brands.controller.ts (`@Controller('admin/brands')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/admin/brands`            | 브랜드/구독 통합 목록 → `{ data, total }`. `q`(name), `status`, `subStatus`(active/past_due/canceled/**none**=구독 없음), `take`(1~200, 기본 50)/`skip`. 각 행에 `subscription`(+`billingKey`) 과 `_count.products` 포함 (구 `/admin/brand-subscriptions` 목록 흡수) |
| GET    | `/admin/brands/:id`        | 브랜드 상세                                         |
| POST   | `/admin/brands`            | 브랜드 직접 생성                                    |
| PATCH  | `/admin/brands/:id`        | 브랜드 정보 수정                                    |
| DELETE | `/admin/brands/:id`        | 브랜드 삭제                                         |

## admin-brand-withdrawals.controller.ts (`@Controller('admin/brand-withdrawals')`)

> 전체 라우트 `AdminGuard`. 브랜드 탈퇴(철회) 처리 — 브랜드가 [brand-auth](./brand-auth.md) 의 `withdrawal-request` 로 `withdrawal_pending` 전환한 건을 어드민이 마무리한다.

| Method | Path                                 | 기능                                                          |
|--------|--------------------------------------|---------------------------------------------------------------|
| GET    | `/admin/brand-withdrawals`           | 탈퇴 요청 목록 → `{ items, total }`. `status`(`pending`\|`scheduled`\|`withdrawn`\|`all`, 그 외 값은 무시), `q` 검색, `take`(1~200, 기본 100)/`skip`. 각 행에 `submittedBy` + `_count{products, shipments, brandUsers}` + 미출고 송장 카운트 |
| GET    | `/admin/brand-withdrawals/:id`       | 탈퇴 요청 상세 (path 는 **brandId**). 탈퇴 대상 브랜드가 아니면 404 |
| POST   | `/admin/brand-withdrawals/:id/ready` | 해당 브랜드 정리 완료(ready) 표시 → 30일 뒤로 `withdrawalScheduledAt` 예약. `withdrawal_pending` 이 아니거나 이미 예약됐으면 400. 200 OK |
| POST   | `/admin/brand-withdrawals/process-due` | 예정일이 지난(due) 탈퇴 일괄 확정 (`withdrawn`). 200 OK        |

## public-brands.controller.ts (`@Controller('v1/brands')`)

> 전체 라우트 public.

| Method | Path                       | 기능                                                |
|--------|----------------------------|-----------------------------------------------------|
| GET    | `/v1/brands`               | 브랜드 목록 — **쿼리 파라미터 없음**(`publicOnly` 는 컨트롤러가 항상 true 로 고정). `order` asc → `createdAt` desc, 최대 200건 |
| GET    | `/v1/brands/by-slug/:slug` | 슬러그로 브랜드 조회 (`?lang=`). slug 는 trim+lowercase 정규화. 라우트 순서상 `:id` 보다 먼저 선언 |
| GET    | `/v1/brands/:id`           | 브랜드 ID 로 조회 (`?lang=`)                        |

> 공개 단건은 행을 찾아도 `isPublicBrand()` 를 통과하지 못하면 **404**(존재 여부를 흘리지 않음).

## brand-menu.controller.ts (`@Controller('v1/brand')`) — 브랜드관 메뉴·PC 설정 (2026-09-28)

> 전체 라우트 `BrandGuard`. 경로에 brandId 가 없다 — 세션에서 꺼내므로 남의 브랜드를 가리킬 방법이 구조적으로 없다(`brand-notices`·`brand-storefront-translations` 와 같은 판단).

⚠️⚠️ **`PUT /v1/brand/applications` 에 얹지 않고 줄 단위로 뗀 것이 이 컨트롤러의 존재 이유다.** 구 모델은 메뉴를 `Brand.story` Json 한 칸에 담아 전체 문서 PUT 으로 보냈고, 그 한 칸의 400 이 배경색·폰트·링크 저장까지 통째로 죽였다.

| Method | Path                                | 기능 |
|--------|-------------------------------------|------|
| GET    | `/v1/brand/menu`                    | `{ items[], desktop{columns, heroUrls, featuredIds} }`. `items` 는 `sort asc`, 각 줄에 `page`(+`chapters` sort asc) 중첩 |
| POST   | `/v1/brand/menu`                    | 줄 하나 생성. `kind` 는 **만들 때만** 정하고 이후 못 바꾼다. `story`/`page` 면 **빈 페이지를 함께** 만든다 |
| POST   | `/v1/brand/menu/bulk`               | 줄 N개 생성(≤16). ⚠️ 상점 자동 칸 굳히기(`materializeShopRows`) 전용 — **하나씩 POST 하면 안 된다**(첫 칸이 저장된 순간 klow_brand `shopRows` 의 "직접 만든 칸이 있으면 그것만 목차" 규칙에 걸려 나머지 자동 칸이 통째로 사라진다) |
| PUT    | `/v1/brand/menu/reorder`            | `{ ids[] }` 순서 일괄. 보낸 id 가 앞에, 빠진 줄은 뒤에 원래 순서로 |
| PATCH  | `/v1/brand/menu/:itemId`            | `label`/`hidden`/`url`/`productIds`/`categoryKey`. ⚠️ 종류에 안 맞는 칸은 **400 이 아니라 무시**(클라가 한 폼에서 모든 칸을 들고 보내는 것이 정상) |
| DELETE | `/v1/brand/menu/:itemId`            | 줄 삭제 — **그 줄이 열던 페이지도 함께** 지운다(가리키는 줄이 없는 페이지는 어디서도 열 수 없다) |
| PATCH  | `/v1/brand/menu/:itemId/page`       | 페이지 필드(커버·제목·소개·사진틀·배경·글자크기). 페이지가 아직 없으면 여기서 만든다 |
| POST   | `/v1/brand/menu/:itemId/chapters`   | 챕터 추가(≤12) → **서버가 만든 챕터를 돌려준다** |
| PUT    | `/v1/brand/menu/:itemId/chapters`   | 챕터 일괄 — 보낸 id 는 제자리에서 고치고, 안 보낸 id 는 지우고, 배열 순서가 표시 순서 |
| PATCH  | `/v1/brand/desktop`                 | PC 설정 — `columns`(2\|3\|4) / `heroUrls`(≤20) / `featuredIds`(≤200) |

⚠️⚠️ **`sort` 쓰기는 2단계다.** `BrandMenuItem` 과 `BrandPageChapter` 에 `@@unique([_, sort])` 가 걸려 있어 최종값을 바로 쓰면 중간에 중복이 생겨 트랜잭션이 통째로 실패한다(멀쩡한 재정렬이 500 이 된다). 서비스는 먼저 음수(`PARKING_OFFSET`)로 밀고 나서 최종값을 쓴다.

⚠️⚠️ **챕터 id 는 서버가 만들고 프론트는 받은 그대로 쓴다.** 클라가 임시 id 로 먼저 그리면 응답이 도착할 때 `key` 가 바뀌어 입력칸이 remount 되고 **타이핑 중 커서와 포커스가 날아간다**(구 `BrandStoryChapterSchema.id` 가 같은 이유로 `default` 를 금지했다). 그래서 "추가"가 일괄이 아니라 전용 POST 다.

⚠️ 상한은 `common/validation/brand-menu.ts` 가 갖고 klow_brand `src/lib/brand-story.ts` 상수와 **글자 단위로 같아야 한다**(줄 이름 24 / 최상위 줄 8 / 상점 칸 16 / productIds 200 / 링크 URL 500 / 제목 60 / 소개 200 / 소제목 60 / 본문 1200 / 챕터 12 / PC 히어로 20 / PC 강조 200). `prisma/schema.prisma` 의 `@db.VarChar` 까지 **세 곳이 한 표**를 본다.

### 스토리는 특별 취급을 받지 않는다 — 보통 메뉴 행이다

정규화의 부수 효과가 가장 중요한 이득이다. 구 klow_brand `normalizeMenu` 는 스토리를 **항상 존재하는 한 줄**로 합성했고 `enabled` 기본값이 `true` 였다. 그 규칙을 손님 화면에 그대로 내면 **스토리를 만든 적 없는 브랜드가 빈 페이지로 가는 "Brand Story" 줄을 얻는다**(운영 기준 최대 41곳). 지금은 `kind='story'` 인 **보통 행**이고 **내용이 있는 브랜드에만** 행이 있다 — 행이 없으면 줄이 없으므로 프론트 가드가 필요 없고 회귀가 구조적으로 불가능하다.

메뉴 행이 0개인 브랜드에는 `상점` 한 줄만 **읽기 시점에 합성**한다(저장하지 않는다). 상점의 칸은 제품 `categoryKey` 에서 파생되므로 저장할 것이 없고, 브랜드가 손대는 순간에만 실제 행이 생긴다.

## 참고

- `Brand` 모델 주요 컬럼: `status`(draft/pending/approved/rejected/withdrawal_pending/withdrawn), `slug`(@unique, `klow.kr/{slug}`), `submittedById`, `submittedAt`, `approvedAt`, `approvedById`, `rejectionReason`, `pgCustomerKey`(@unique, 결제 준비 게이트), 브랜드관 표현(`logoLayout`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`/`story`), EFS 송화인(`senderName`/`senderAddress`/`senderPostalCode`/`senderPhone`), 정산 계좌(`bankName`/`bankAccountNumber`/`bankAccountHolder`), 탈퇴 이력(`withdrawalRequestedAt`/`withdrawalReadyAt`/`withdrawalScheduledAt`/`withdrawnAt`/`withdrawalProcessedAt` + 요청자·처리자 id·연락처).
- **`Brand.category` (2026-07-31)**: prisma enum `BrandCategory`(`cosmetics` | `dental_materials`), **nullable — `null` = 아직 안 고름**. 이 브랜드에서 나가는 **모든 송장(일반 주문 + 시딩)의 EFS 통관 분류(24-6)·HS 코드(24-8) 단일 출처**이고 제품별 오버라이드는 없다(`Product.hsCode` 등은 dormant). 값이 없으면 제품 생성이 거부된다(`assertBrandCategoryChosen` — [brand-applications](./brand-applications.md) 의 단건/일괄 초안 양쪽). 송장/시딩은 `null` 을 화장품으로 폴백. 편집은 어드민 브랜드 폼(`PATCH /admin/brands/:id`) 과 klow_brand 스튜디오.
- **`Brand.story` (2026-08-25 · 2026-09-28 dormant)**: ⚠️⚠️ **더 이상 쓰지 않는다.** 브랜드관 메뉴·페이지는 `BrandMenuItem`/`BrandPage`/`BrandPageChapter` 테이블이 정본이다(위 절). 이 컬럼은 `DROP COLUMN` 이 롤링 비안전이고 백필 롤백 여지를 남기려고 **dormant 로 둔 것**이며, 서버는 여기에 쓰지 않고 들어온 legacy `story` 를 [brand-applications](./brand-applications.md) 의 **이행 어댑터**가 테이블로 번역한다. 아래는 그 시절의 서술이다 — `Json?` 이고 **`@default` 가 없다** — `isBrandStoryPublic` 이 "만든 적 없음(null)"과 "만들었다 비웠음"을 구분해야 한다(`linkStyle` 과 같은 자리). 저장·형식 규칙은 [brand-applications](./brand-applications.md) 의 브랜드 스토리 절. **어드민은 이 필드를 다루지 않는다**(`BrandInput`/`BrandPatch` 에 없음).
- `PATCH /admin/brands/:id` 에 `name` 이 포함되면 트랜잭션으로 비정규화 캐시 `Product.brand` 를 일괄 갱신한다. `DELETE` 는 소속 제품의 `brandId` 를 먼저 `null` 로 떼어낸 뒤 삭제(제품은 남는다).
- **PC 브랜드관 설정 (2026-09-28)**: `Brand.desktopColumns`(Int @default(3)) / `desktopHeroUrls`(String[]) / `desktopFeaturedIds`(String[]). ⚠️ **스칼라 3개이고 서로 독립·중첩이 없어 테이블로 빼지 않았다** — 메뉴와 같은 취급을 하지 말 것. `@default(3)` 가 기존 전 행을 자동으로 덮고 대표사진은 `desktopHeroUrls → logosWide → logosTall → circle 폴백` 순으로 내려가므로 **어느 경로에서도 빈 화면이 없고 백필이 필요 없다**.
- ⚠️ `homepageUrl` / `targetCountries[]` 컬럼은 현재 스키마에 **없다**(과거 문서 잔재).
- 브랜드 입점 신청 워크플로우는 [brand-applications](./brand-applications.md), 승인/구독 게이트는 [subscription](./subscription.md) 참고.

## 브랜드관 수동 번역 오버라이드 (2026-08-25)

브랜드가 스튜디오 **브랜드관 목업**에서 국가를 고른 채 **한 줄 소개·브랜드 태그**를 눌러 직접 고친다. 제품 쪽(`ProductTranslationOverride`)과 **같은 규칙·같은 저장 모양**이고, 판정 로직도 `common/translation-overrides.ts` **한 벌을 공유**한다(드리프트 규칙은 여러 번 다듬은 미묘한 로직이라 두 벌로 두면 반드시 갈라진다). 각 모듈은 `*-translation-overrides.ts` 에서 **필드 목록만** 바인딩한다.

- 저장은 신규 테이블 `BrandTranslationOverride`(`@@unique([brandId, locale])` + `entries Json`). 테이블이 나뉜 이유는 규칙이 달라서가 아니라 FK 가 `brandId` 라 한 테이블에 담을 수 없어서다.
- 필드는 2종 — `description`(스칼라) / `brandTag`(배열). ⚠️ **브랜드명은 번역 대상이 아니다**(`BrandTranslation` 에 컬럼이 없고 klow_web 도 고유명사로 그대로 쓴다). 넣으면 저장은 되는데 아무 데도 안 보인다.
- ⚠️⚠️ **`brandTag` 의 조회 키는 `Brand.tagline` 인코딩 문자열 전체가 아니라 디코딩된 개별 태그**다(`__klow_brand_tags_v1__:a,b,c` → `a`/`b`/`c`). 통째로 키를 잡으면 태그 하나만 바꿔도 전체 오버라이드가 빗나간다. overlay 는 캐시의 번역 태그를 디코딩 → 영문 원문 기준으로 치환 → **같은 마커로 재인코딩**해 돌려놓는다(클라 `parseBrandTags` 가 그대로 읽어야 한다).
- ⚠️ 태그 배열은 **영문 스냅샷 길이가 정본**이고, 캐시의 번역 태그는 **길이가 정확히 같을 때만** 인덱스로 재사용한다(제품 배열과 같은 규칙 — legacy/torn 캐시를 억지로 짝지으면 라벨이 한 칸 밀린다).
- ⚠️ `localize()` 의 `if (!t) continue` 가 `if (t) { … }` 로 바뀌었다 — 오버라이드는 캐시 행이 없어도(신규 브랜드 첫 조회·번역 실패) 적용돼야 한다. 캐시와 오버라이드는 `Promise.all` 병렬 조회이고, **읽기 경로가 `Brand` 를 쓰지 않는다**(`@updatedAt` 이 오르면 7개 로케일이 전부 재번역).
- 라우트는 `v1/brand/storefront-translations` 4개(GET / PATCH·DELETE `:locale` / POST `resolve`) — `brand-storefront-translations.controller.ts`. ⚠️ **경로에 브랜드 id 가 없다**(세션의 `user.brandId` 를 쓴다) → 남의 브랜드를 가리킬 방법이 구조적으로 없어 제품 라우트와 달리 소유권 조회가 필요 없다. ⚠️ GET 은 `localize()` 를 부르지 않는다(패널 열 때마다 Google 과금).
- 태그를 지우면 원문이 없어진 엔트리는 **묻지 않고 정리**한다 — `updateApplication` 이 tagline/description 이 **실제로 달라졌을 때만** `pruneOverridesForBrand` 를 태운다(이 PUT 은 전체 문서 저장이라 색만 바꿔도 매번 호출된다). 규칙은 제품과 동일하게 `driftOf` 가 보고하지 않는 고아 = 정리 대상.
- 마이그레이션 `20260825064047_add_brand_translation_override` 는 `CREATE TABLE` 뿐 → **롤링 배포 안전 · 백필 없음 · 재번역 0**.
- 회귀 잠금은 `brands/__tests__/brand-translation-override.spec.ts`(11케이스 — 태그 인코딩 왕복 · 재정렬 · 길이 불일치 · 캐시 미스 · fail-safe · Brand write 없음).
