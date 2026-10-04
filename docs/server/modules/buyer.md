# buyer — 바이어 공간 (klow.kr/ · 어드민 큐레이션)

- **모듈 경로**: `src/modules/buyer/`
- **목적**: 해외 바이어가 `klow.kr/` 에서 둘러보는 **KLOW 가 골라 올린 브랜드·제품**의 데이터. 관리자가 klow_admin "바이어 공간"에서 채우고(`/admin/buyer/*`), klow_web 이 공개 API(`/v1/buyer/*`)로 그린다. 브랜드(klow_brand)는 무관하다.
- **설계 정본**: [`docs/plan/buyer-platform/`](../../plan/buyer-platform/README.md) — 불변식 G1~G12 는 `implementation-plan.md §1`.
- **관련 파일**: `buyer-completeness.ts`(노출 판정·이미지 추종·MOQ/카드가·프리필 — 순수 함수) · `buyer.mapper.ts`(공용 include·공개 DTO) · `buyer-admin.service.ts` · `buyer-public.service.ts` · `buyer-inquiry-email.ts` · `admin-buyer.controller.ts` · `public-buyer.controller.ts` · 검증 `common/validation/buyer.ts` · 메일 발송 `web-auth/email.service.ts#sendPrepared`(B2B 주문서 알림과 공용)
- **마이그레이션**: `20261004140057_add_buyer_platform` — 신규 테이블 8 + enum 3 + **카테고리 7종 SQL 시드**(id `bcat_<slug>`, `ON CONFLICT DO NOTHING`). 전부 `CREATE TABLE` 이라 롤링 안전.

## 데이터 모델

| 모델 | 역할 |
|---|---|
| `BuyerBrand` | 원본 `Brand` 의 1:1 오버레이(`brandId @unique`). 공개 토글·순서·tier·프로필(도시·설립·리드타임·지역·마케팅 지원·derm)·로고 덮어쓰기 |
| `BuyerProduct` | 원본 `Product` 의 1:1 오버레이(`productId @unique`). 공개 토글·카테고리·영문명·스펙·인증(CPNP/FDA OTC/SPF/GMP)·MSRP·이미지 |
| `BuyerPriceTier` | 도매 구간가(USD 센트). **MOQ 의 정본**(아래) |
| `BuyerCategory` | 홈 카테고리 탭 |
| `BuyerHeroSlide` | 홈 히어로(연결 제품 선택) |
| `BuyerShelf` · `BuyerShelfItem` | 홈 큐레이션 선반(수동으로 고른 제품) |
| `BuyerInquiry` | Request 드로어 문의. 브랜드·제품 FK 는 `SetNull`(영업 기록이라 남는다) |

⚠️⚠️ **원본 `Product`·`Brand` 에 쓰지 않고(G1) `B2b*` 테이블은 읽지도 않는다(G2).** 기존 B2B 도매(`/[slug]/b2b`, 브랜드가 입력)와 이 공간의 가격은 별개다.

## 노출 판정 — `buyer-completeness.ts` 한 곳(G3)

공개 = `BuyerBrand.published && BuyerProduct.published && 필수 7 완비 && Brand.status=approved && Product.status=approved && Brand.slug != null && Product.brandId == BuyerBrand.brandId`.

- **필수 7**: `category` · `tiers`(구간 규칙 충족) · `about` · `size` · `madeIn` · `ingredients` · `image`(원본 추종 포함)
- **노출 불가 사유**(어드민 표시용, 공개 토글과 별개): `incomplete` · `no_slug` · `brand_not_approved` · `product_not_approved` · `brand_mismatch`
- `Product.hidden`·구독 상태는 **보지 않는다** — 소비자 판매의 게이트(`PUBLIC_PRODUCT_WHERE`)와 무관하다.
- ⚠️ 판정은 **읽을 때 계산**한다(저장 컬럼 없음) — 원본 `image`·`status`·`slug` 가 다른 화면에서 바뀌어서다. 공개 API 는 값싼 조건을 where 로 먼저 줄이고 최종 판정은 `evaluate()` 가 한다.

**구간가 규칙(G10)** — `common/validation/buyer.ts#buyerTierIssue` 가 입력 검증과 완비 판정 둘 다의 정본: 첫 행 `minQty=1`(샘플가) · 2~6행 · 시작 수량 엄격 오름차순 · 단가 > 0. **MOQ = 둘째 행 시작 수량**, 카드·패널·선반의 대표 도매가 = **MOQ 구간 단가**(`cardPrice()`, G11). 제품·브랜드에 MOQ 컬럼은 없다.
브랜드 `openingOrder` = 노출 제품 MOQ 최솟값, `retailMultiple` = MSRP 있는 노출 제품의 `MSRP ÷ MOQ 구간가` 평균(소수 1자리) — 응답 시 계산.

**이미지(G5)**: `BuyerProduct.images = []` 이면 원본 **대표사진 1장**(`image`, 비었거나 동영상이면 `detailImages` 의 첫 비동영상 — 확장자 mp4/mov/webm 판별)을 실시간으로 쓴다. 한 장이라도 넣으면 그 배열이 정본. 로고도 같다(`logoUrl` null → `logosWide[0] ?? logosCircle[0]`).

## admin-buyer.controller.ts (`@Controller('admin/buyer')`, AdminGuard — 모든 어드민)

브랜드·제품은 **원본 id**(`Brand.id`·`Product.id`)로 가리킨다. 순서 변경(`PUT …/order {ids}`)은 **현재 id 집합과 정확히 같은 목록**만 받는다(아니면 400 `order_mismatch`). 모든 PATCH 는 `patchOf()`(보낸 칸만 바뀐다).

| Method | Path | 기능 |
|---|---|---|
| GET | `/admin/buyer/brands` | 올린 브랜드 목록 — 제품 수·완비 수·노출 수·**필수 칸별 누락 수**(`missingCounts`)·브랜드 단위 사유 |
| GET | `/admin/buyer/brand-candidates?q=` | **승인 브랜드만** 후보(최대 50) — `added`·승인 제품 수 |
| POST | `/admin/buyer/brands` `{brandId}` | 브랜드 올리기(승인만, 중복 409 `already_added`). tagline 은 원본 프리필 |
| PUT | `/admin/buyer/brands/order` `{ids: brandId[]}` | 브랜드 순서 |
| GET | `/admin/buyer/brands/:brandId` | 프로필 + 원본 로고/tagline + `openingOrder`·`retailMultiple` |
| PATCH | `/admin/buyer/brands/:brandId` | 프로필·공개 토글 (`logoUrl: null` = 원본 로고로) |
| DELETE | `/admin/buyer/brands/:brandId` | ⚠️ 입력한 제품 정보·구간가까지 cascade 삭제 — 평소엔 공개 OFF |
| GET | `/admin/buyer/brands/:brandId/products` | 그 브랜드 **승인 제품** + 이미 올린 행(승인이 풀린 것 포함). `buyer: null` = 안 올림, 있으면 `missing`·`reasons`·`visible`·썸네일 |
| POST | `/admin/buyer/products` `{productId}` | 제품 올리기(승인만 · 브랜드를 먼저 올려야 함 400 `brand_not_added`). 프리필: name→`nameEn` · volume→`size` · ingredients · countryOfOrigin→`madeIn` · expiryInfo→`shelfLifeMonths`(개월 파싱) · keyIngredients[].name→`keyActives` · basePriceUsd→`msrpUsdCents` |
| PATCH | `/admin/buyer/products/bulk` `{productIds, categoryId?, published?}` | 일괄 카테고리/공개 |
| GET | `/admin/buyer/products/:productId` | 편집기 — 전 필드 + `tiers` + `originalImages`(대표+상세컷, 동영상 제외) + `brand.marketingSupport`(미리보기 카드 줄) + `nextIncompleteProductId`(같은 브랜드 다음 미완비, 돌아서 처음부터) |
| PATCH | `/admin/buyer/products/:productId` | 필드 + **`tiers` 를 같은 트랜잭션에서 통째 교체**(빈 배열 허용 = 미완비 저장, 행이 있으면 G10 위반 400). `images: []` = 원본으로 되돌리기 |
| DELETE | `/admin/buyer/products/:productId` | 바이어 행 삭제(입력값 소멸) |
| GET/POST | `/admin/buyer/categories` | 목록(소속 제품 수) / 추가 `{name, slug}` |
| PUT | `/admin/buyer/categories/order` | 순서 |
| PATCH/DELETE | `/admin/buyer/categories/:id` | 수정 / 삭제 — ⚠️ **소속 제품이 있으면 409 `category_in_use`**(SetNull 이면 그 제품들이 조용히 사라진다) |
| GET/POST | `/admin/buyer/hero` | 목록 / 추가 `{imageUrl, productId?, caption?}` |
| PUT | `/admin/buyer/hero/order` | 순서 |
| PATCH/DELETE | `/admin/buyer/hero/:id` | 수정 / 삭제 |
| GET/POST | `/admin/buyer/shelves` | 목록(아이템 + 각 제품 `visible`) / 추가 `{title, lede?, preview?: 4\|8, published?}` |
| PUT | `/admin/buyer/shelves/order` | 순서 |
| PATCH/DELETE | `/admin/buyer/shelves/:id` | 수정 / 삭제 |
| PUT | `/admin/buyer/shelves/:id/items` `{items: [{productId, tag?}]}` | 선반 제품 통째 교체(최대 48). 바이어 공간에 올라간 제품만(400 `product_not_added`) |
| GET | `/admin/buyer/inquiries?status=new\|handled` | 문의 목록(최신순 500) + 연결 브랜드·제품 |
| PATCH | `/admin/buyer/inquiries/:id` `{status?, adminNote?}` | 처리 상태·메모 |

- 히어로·선반이 가리키는 제품이 비노출이 되면 어드민 응답의 `visible: false` 로 보이고, 공개 API 가 자동으로 뺀다(히어로는 이미지만 남기고 링크를 뗀다).
- ⚠️ 감사 로그(`AdminAuditInterceptor`)는 본문 10KB 초과분을 자른다 — 성분 8000자 PATCH 는 잘릴 수 있다(R8, 수용).
- 이미지 재크롭용 프록시(`image-source`)는 **만들지 않는다**(2026-10-04 판정) — R2 가 어드민 오리진 GET 을 CORS 로 허용해서 klow_admin 이 브라우저에서 직접 받아 크롭한다(운영 `cdn.klow.kr` → `admin.klow.kr` · dev 버킷 → `localhost:3000`·`admin-staging.klow.kr` 실측). ⚠️ dev 버킷은 **`localhost:3000` 만** 허용이라 어드민을 다른 포트로 띄우면 재크롭·업로드가 CORS 로 실패한다(화면은 토스트로 "파일로 다시 올려 달라"). 외부 호스트 원본 이미지도 같은 이유로 재크롭이 안 되고 파일 업로드로 대신한다.
- 프런트: klow_admin `/buyer`(브랜드) · `/buyer/brands/[brandId]` · `/buyer/products/[productId]`(편집기 + 미리보기 `components/preview/BuyerPreview.tsx`) · `/buyer/home` · `/buyer/inquiries`. 편집기는 **폼 값에서 직접** 카드·PDP 를 그리고(저장 전 반영 — 그래서 서버는 `preview` 를 싣지 않는다), 필수 7칸 판정도 화면에 미러가 있다(`_components/editor-form.ts#localMissing` — 정본은 서버, 규칙을 바꾸면 둘 다).

## public-buyer.controller.ts (`@Controller('v1/buyer')`, 인증 없음)

| Method | Path | Throttle | 기능 |
|---|---|---|---|
| GET | `/v1/buyer/home` | 전역 | `{ heroSlides, categories, shelves, brands }` — 노출 제품 0 인 카테고리·선반·브랜드는 빠진다. 히어로 `product` 는 노출 중일 때만 |
| GET | `/v1/buyer/products?category=&q=&take=&cursor=` | 전역 | 카드 목록 `{ items, total, nextCursor }` — `category` = 카테고리 slug, `q` 는 제품명·브랜드명·key actives 부분일치, `cursor` = 직전 페이지 마지막 제품 id |
| GET | `/v1/buyer/brands/:slug` | 전역 | 브랜드 프로필(계산된 `openingOrder`·`retailMultiple` 포함) + 노출 제품 카드 |
| GET | `/v1/buyer/products/:id` | 전역 | PDP — 이미지·인증·구간가·스펙·같은 브랜드 다른 제품 최대 8 |
| POST | `/v1/buyer/inquiries` | **5회/분/IP** | 문의 저장 + 운영팀 메일 |

- **G12**: 없는 slug/id 와 비공개·미완비·미승인은 **같은 404**(`brand not found` / `product not found`) — 비공개 행의 존재를 새지 않는다. 브랜드는 노출 제품이 1개 이상일 때만 존재한다.
- 카드 `priceUsdCents` = MOQ 구간 단가, `moq` = 둘째 행 시작 수량.
- 조회는 throttle 을 조이지 않는다 — klow_web 은 ISR(`revalidate: 60`)로 받는다(Vercel egress IP 공유).
- 프런트: klow_web `app/(buyer)/`(`/` 홈 · `/shop/brands/[slug]` · `/shop/products/[id]`) — 서버 컴포넌트가 `lib/buyer-space-server.ts` 로 `home`·`brands/:slug`·`products/:id` 를 받고, 카테고리 탭·검색(`products`)과 문의(`inquiries`)만 클라이언트 `api.buyerSpace` 다. sitemap 이 `products` 를 커서로 전부 훑어 노출 브랜드·제품을 싣는다.
- 서버 캐시 없음. 매 요청 노출 후보를 include 1회로 받아 메모리 판정(규모 수백 행).

### POST `/v1/buyer/inquiries`

Body `BuyerInquiryInput`: `{ kind: 'quote'|'brand_request', subject(1~200 · 디자인 "Brand or product"), needs?(≤2000), market?(≤200 · "Business & market"), email, brandSlug?, productId?, qty?, website? }` → `200 { ok: true }`.

- `brandSlug`·`productId` 는 **노출 중인 것만** 연결한다(아니면 null로 저장). 제품이 연결되면 그 브랜드도 연결된다.
- `website` 는 honeypot — 채워져 오면 200 을 주고 저장하지 않는다.
- `req.ip`(trust proxy 기준, `clientIp()`)를 저장한다.
- 메일은 **저장 후** 보내고, **실패는 삼키고 로그**한다(contact 와 반대 — 정본이 테이블이라서). 모든 입력은 `escapeHtml`(G7).

## 환경변수

| env | 기본값 | 비고 |
|---|---|---|
| `BUYER_INQUIRY_EMAIL` | (비움) | 문의 수신함. 비면 `CONTACT_INBOX_EMAIL` → `team@klow.kr` |
| `ADMIN_FRONTEND_URL` | (기존) | 메일의 "어드민에서 문의 보기" 링크(`/buyer/inquiries`) |
| `RESEND_API_KEY` | (기존) | 비면 `[DEV email] buyer inquiry …` 콘솔 로깅. ⚠️ dev 도 키가 있어 실발송 — 테스트는 `RESEND_API_KEY= npm run start` |
