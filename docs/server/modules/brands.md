# brands — 브랜드

- **모듈 경로**: `src/modules/brands/`
- **공개 필터**: `PUBLIC_BRAND_WHERE` = `Brand.status NOT IN (rejected, withdrawal_pending, withdrawn)` — 즉 `draft`/`pending`/`approved` 는 브랜드관 자체가 노출된다(탈퇴 신청 즉시 공개 surface 에서 제거). ⚠️ **제품 노출/판매 게이트는 이보다 엄격**해서 `Brand.status='approved'` + 구독 active 를 요구한다([products](./products.md) `PUBLIC_PRODUCT_WHERE`) — 두 필터를 혼동하지 말 것. 이미 fetch 한 row 검증용 JS 짝은 `isPublicBrand()`.
- **공통 select**: `brand-selects.ts` — `PUBLIC_BRAND_SELECT` 는 공개 노출 필드만 화이트리스트(`id`/`name`/`slug`/`tagline`/`description`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`logoLayout`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`/`order`/`status`/`createdAt`/`updatedAt`). 송화인·계좌·탈퇴 이력·`pgCustomerKey`·`category` 등 내부 필드는 공개 응답에 실리지 않는다.
- **공개 단건 select (2026-08-25)**: `PUBLIC_BRAND_DETAIL_SELECT = {...PUBLIC_BRAND_SELECT, story}` — `by-slug`/`:id` 만 쓴다. ⚠️ **`story` 를 `PUBLIC_BRAND_SELECT` 에 바로 넣으면 안 된다**: 그 select 는 목록(`findAll`)이 함께 쓰는데 거기는 **최대 200건**을 돌려주고 스토리는 챕터 12개면 10KB 를 넘어, 브랜드관과 무관한 shop 캐러셀 응답이 통째로 부푼다. ⚠️ 반드시 스프레드로 파생시킬 것 — 손으로 두 벌 쓰면 공개 필드가 한쪽에만 추가되어 목록과 단건의 노출 범위가 조용히 갈린다.
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

## 참고

- `Brand` 모델 주요 컬럼: `status`(draft/pending/approved/rejected/withdrawal_pending/withdrawn), `slug`(@unique, `klow.kr/{slug}`), `submittedById`, `submittedAt`, `approvedAt`, `approvedById`, `rejectionReason`, `pgCustomerKey`(@unique, 결제 준비 게이트), 브랜드관 표현(`logoLayout`/`logosCircle`/`logosWide`/`logosTall`/`logoPoster`/`shareImageUrl`/`pageFont`/`accentColor`/`gradientStrength`/`links`/`linkStyle`/`story`), EFS 송화인(`senderName`/`senderAddress`/`senderPostalCode`/`senderPhone`), 정산 계좌(`bankName`/`bankAccountNumber`/`bankAccountHolder`), 탈퇴 이력(`withdrawalRequestedAt`/`withdrawalReadyAt`/`withdrawalScheduledAt`/`withdrawnAt`/`withdrawalProcessedAt` + 요청자·처리자 id·연락처).
- **`Brand.category` (2026-07-31)**: prisma enum `BrandCategory`(`cosmetics` | `dental_materials`), **nullable — `null` = 아직 안 고름**. 이 브랜드에서 나가는 **모든 송장(일반 주문 + 시딩)의 EFS 통관 분류(24-6)·HS 코드(24-8) 단일 출처**이고 제품별 오버라이드는 없다(`Product.hsCode` 등은 dormant). 값이 없으면 제품 생성이 거부된다(`assertBrandCategoryChosen` — [brand-applications](./brand-applications.md) 의 단건/일괄 초안 양쪽). 송장/시딩은 `null` 을 화장품으로 폴백. 편집은 어드민 브랜드 폼(`PATCH /admin/brands/:id`) 과 klow_brand 스튜디오.
- **`Brand.story` (2026-08-25)**: 브랜드관 상단 진입 글자가 여는 소개 페이지 문서(커버 + 챕터 N). `Json?` 이고 **`@default` 가 없다** — `isBrandStoryPublic` 이 "만든 적 없음(null)"과 "만들었다 비웠음"을 구분해야 한다(`linkStyle` 과 같은 자리). 저장·형식 규칙은 [brand-applications](./brand-applications.md) 의 브랜드 스토리 절. **어드민은 이 필드를 다루지 않는다**(`BrandInput`/`BrandPatch` 에 없음).
- `PATCH /admin/brands/:id` 에 `name` 이 포함되면 트랜잭션으로 비정규화 캐시 `Product.brand` 를 일괄 갱신한다. `DELETE` 는 소속 제품의 `brandId` 를 먼저 `null` 로 떼어낸 뒤 삭제(제품은 남는다).
- ⚠️ `homepageUrl` / `targetCountries[]` 컬럼은 현재 스키마에 **없다**(과거 문서 잔재).
- 브랜드 입점 신청 워크플로우는 [brand-applications](./brand-applications.md), 승인/구독 게이트는 [subscription](./subscription.md) 참고.

## 브랜드관 수동 번역 오버라이드 (2026-08-25)

브랜드가 스튜디오 **브랜드관 목업**에서 국가를 고른 채 **한 줄 소개·브랜드 태그**를 눌러 직접 고친다. 제품 쪽(`ProductTranslationOverride`)과 **같은 규칙·같은 저장 모양**이고, 판정 로직도 `common/translation-overrides.ts` **한 벌을 공유**한다(드리프트 규칙은 여러 번 다듬은 미묘한 로직이라 두 벌로 두면 반드시 갈라진다). 각 모듈은 `*-translation-overrides.ts` 에서 **필드 목록만** 바인딩한다.

- 저장은 신규 테이블 `BrandTranslationOverride`(`@@unique([brandId, locale])` + `entries Json`). 테이블이 나뉜 이유는 규칙이 달라서가 아니라 FK 가 `brandId` 라 한 테이블에 담을 수 없어서다.
- 필드는 2종 — `description`(스칼라) / `brandTag`(배열). ⚠️ **브랜드명은 번역 대상이 아니다**(`BrandTranslation` 에 컬럼이 없고 klow_web 도 고유명사로 그대로 쓴다). 넣으면 저장은 되는데 아무 데도 안 보인다.
- ⚠️⚠️ **`brandTag` 의 조회 키는 `Brand.tagline` 인코딩 문자열 전체가 아니라 디코딩된 개별 태그**다(`__klow_brand_tags_v1__:a,b,c` → `a`/`b`/`c`). 통째로 키를 잡으면 태그 하나만 바꿔도 전체 오버라이드가 빗나간다. overlay 는 캐시의 번역 태그를 디코딩 → 영문 원문 기준으로 치환 → **같은 마커로 재인코딩**해 돌려놓는다(클라 `parseBrandTags` 가 그대로 읽어야 한다).
- ⚠️ 태그 배열은 **영문 스냅샷 길이가 정본**이고, 캐시의 번역 태그는 **길이가 정확히 같을 때만** 인덱스로 재사용한다(제품 배열과 같은 규칙 — legacy/torn 캐시를 억지로 짝지으면 라벨이 한 칸 밀린다).
- ⚠️ `localize()` 의 `if (!t) continue` 가 `if (t) { … }` 로 바뀌었다 — 오버라이드는 캐시 행이 없어도(신규 브랜드 첫 조회·번역 실패) 적용돼야 한다. 캐시와 오버라이드는 `Promise.all` 병렬 조회이고, **읽기 경로가 `Brand` 를 쓰지 않는다**(`@updatedAt` 이 오르면 6개 로케일이 전부 재번역).
- 라우트는 `v1/brand/storefront-translations` 4개(GET / PATCH·DELETE `:locale` / POST `resolve`) — `brand-storefront-translations.controller.ts`. ⚠️ **경로에 브랜드 id 가 없다**(세션의 `user.brandId` 를 쓴다) → 남의 브랜드를 가리킬 방법이 구조적으로 없어 제품 라우트와 달리 소유권 조회가 필요 없다. ⚠️ GET 은 `localize()` 를 부르지 않는다(패널 열 때마다 Google 과금).
- 태그를 지우면 원문이 없어진 엔트리는 **묻지 않고 정리**한다 — `updateApplication` 이 tagline/description 이 **실제로 달라졌을 때만** `pruneOverridesForBrand` 를 태운다(이 PUT 은 전체 문서 저장이라 색만 바꿔도 매번 호출된다). 규칙은 제품과 동일하게 `driftOf` 가 보고하지 않는 고아 = 정리 대상.
- 마이그레이션 `20260825064047_add_brand_translation_override` 는 `CREATE TABLE` 뿐 → **롤링 배포 안전 · 백필 없음 · 재번역 0**.
- 회귀 잠금은 `brands/__tests__/brand-translation-override.spec.ts`(11케이스 — 태그 인코딩 왕복 · 재정렬 · 길이 불일치 · 캐시 미스 · fail-safe · Brand write 없음).
