# customer-reviews — 구현 계획 (빌드 스펙 정본)

결정 요약은 [`README.md`](./README.md), 설계 논거는 [`flow.md`](./flow.md).
상태는 [`../../PROGRESS.md`](../../PROGRESS.md) `§7` 만 갖는다.

## 착수 게이트 (불변식)

코드를 쓰기 전에 읽는다. 논거는 [`flow.md`](./flow.md) 의 같은 번호 절.

**G1. 트리거는 cron 의 DB 스캔이다 — `shipments.service.ts` 를 한 줄도 건드리지 않는다.**
배송완료 판정은 기존 단일 출처만 쓴다.
- `shipments/efs.client.ts` `EFS_DELIVERED_CODES = ['33','47','74']` · `isDeliveredTrackingCode()`
  — ⚠️ `'33'` 만 쓰지 말 것. settlement 이 그 버그로 47·74 건을 영영 정산하지 않았다
  ([`decisions/settlement.md 2026-09-04`](../../decisions/settlement.md#2026-09-04)).
- `'42'`(반송완료)는 `TERMINAL_TRACKING_CODES` 에만 있고 **배송완료가 아니다** → 대상 제외.
- `DOMESTIC`(국내 시딩 자체배송)은 EFS 추적이 영영 안 오므로 `brandConfirmedShippedAt != null`
  이 종착이다 — `shipments.service.ts` `isTerminalShipment()` 와 **같은 분기**.
- 주문 모집단은 `orders/contact-population.ts` `CONTACT_ORDER_WHERE`
  (`paymentStatus=paid` + `status != cancelled`)를 **그대로 import**. ⚠️ 송장 취소는
  `status=cancelled` 만 찍고 `paymentStatus` 는 `paid` 로 남기므로 두 조건이 다 필요하다.

**G2. 현장(onsite) 주문은 배송 축이 없다.** 송장 0장 + 결제 성공 즉시 `completed`(부스 직접
전달). 별도 트리거 **`paidAt + REVIEW_REQUEST_DELAY_DAYS`**. `onsite-brand.ts` 의 단일 브랜드
불변식이 서버에서 강제되므로 브랜드는 항상 1곳이다.
⚠️ onsite 의 `fullName`·`phone`·주소는 **빈 문자열**이고 `countryCode` 는 배송지가 아니라
**가격 기준국**이다 — locale 추정에는 쓰되 "배송지"로 읽지 말 것.

**G3. 이메일이 없는 주문이 있다.** `Order.email` 은 non-null 이지만 **빈 문자열일 수 있다** —
엑셀 일괄 시딩(`bulkIssue`)은 이메일을 선택 입력으로 받아 `email: row.email ?? ''` 로 저장하고
`reissue` 가 그 값을 승계한다. 스캔에 `email: { not: '' }` 가 없으면 Resend 가 매 주기 400 이다.

**G4. 토큰은 전용 시크릿으로 새로 만든다.** `signGuestOrderToken` 재사용 금지 — 그 값은 게스트
결제 쿠키(`klow_order`, 1시간) 값과 같은 문자열이고 이 링크는 수신함에 영구히 남는다.

**G5. 번역 소스가 `'ko'` 로 박혀 있다.** `Review.sourceLocale` 로 푼다.

**G6. cron 은 기본 off.** `REVIEW_REQUEST_CRON_ENABLED === 'true'` 일 때만 동작 —
다른 cron 의 `!== 'false'` 관례와 **의도적으로 반대**(이유를 파일 주석에 적는다).
메일이 가리키는 klow_web 페이지가 떠 있어야 켤 수 있다.

**G7. 시딩이 받은 제품은 판매 게이트를 통과하지 못할 수 있다.** 시딩 발급은 일부러
`PUBLIC_PRODUCT_WHERE` 를 걸지 않는다(`seeding.service.ts:205`). 게이트 미통과 제품은
`받으신 제품`·`다른 제품` **양쪽에서 다 뺀다**(리뷰를 받아도 노출될 곳이 없다).
받은 제품 이름 파생은 **반드시** `seeding/seeding-display-name.ts`
`SEEDING_ITEM_NAMES_SELECT` + `seedingItemNames(claim)` → `seeding-product-detail.ts`
`resolveProductsByLabel`. ⚠️ `SeedingClaim.selectedSkus` / `SeedingLink.itemNames` 직접 조회는
[`decisions/shipping-seeding.md 2026-09-14`](../../decisions/shipping-seeding.md#2026-09-14)
가 레포 전역 금지로 박은 패턴이다.
라인↔브랜드 귀속은 `orders/item-brands.ts` `itemBrandIdOf` / `brandOwnedItemWhere`.
⚠️ 브랜드 스코프 조회는 `items` 축과 `shipments.brandId` 축을 **둘 다** 본다
(`brand-crm.service.ts` 선례 — 제품이 하드 삭제돼도 송장의 동결 brandId 는 살아남는다).

**G8. 집계 우회 금지.** `Product.rating`/`reviewCount` 의 유일한 writer 는
`refreshProductAggregates(tx, productId)` 다. 고객 제출도 **같은 `$transaction` 안에서** 거친다.

---

## 데이터 모델

### 마이그레이션 1개 — `add_customer_reviews` (전부 롤링 안전 · 백필 0건)

`Review` 에 nullable ADD COLUMN 3개:

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `source` | `ReviewSource @default(proxy)` | `proxy`(어드민·브랜드 대행 입력 — 기존 전부) / `customer`(고객 직접) |
| `orderId` | `String?` + `Order?` 관계, `onDelete: SetNull` | 구매 확인 근거. 대행 입력은 null |
| `sourceLocale` | `String? @db.VarChar(5)` | 원문 언어. null = 한국어(기존 행) |

+ `enum ReviewSource { proxy customer }`
+ `Order.reviews Review[]` 역관계
+ `@@unique([orderId, productId])` — **한 주문에서 한 제품은 1건.** Postgres 는 NULL 을 서로
  구별하므로 `orderId=null` 인 대행 입력 행에는 제약이 걸리지 않는다(부분 인덱스가 필요 없다).

⚠️ `@default(proxy)` 라서 기존 행은 자동으로 `proxy` 다 — **백필 스크립트를 만들지 않는다.**

### 새 테이블 — `ReviewRequest` (발송 큐 겸 영수증)

`BrandCrmEmail` 을 본뜬다 — *"행을 먼저 적재하고 나중에 보낸다."*

```prisma
/// 리뷰 요청 메일 1통 = 1행 = (주문, 브랜드) 한 쌍. **행이 곧 영수증**이다.
/// ⚠️ `@@unique([orderId, brandId])` 가 "중복 발송 금지"의 정본이다 — BrandCrmEmail 은
/// 유니크가 없지만(같은 사람에게 여러 번 보내는 게 정상 기능) 이쪽은 1통이 요건이라
/// DB 제약으로 올린다. cron 주기가 겹쳐도 두 번째 insert 가 P2002 로 깨진다.
model ReviewRequest {
  id            String    @id @default(cuid())
  orderId       String
  brandId       String
  /// 발송 시점 수신 주소 스냅샷.
  toEmail       String    @db.VarChar(320)
  /// 메일 본문 언어(klow_web SUPPORTED_LOCALES). Order.countryCode 에서 파생한 스냅샷.
  locale        String    @db.VarChar(5)
  /// 'queued' | 'sent' | 'failed' | 'skipped'  (String — BrandCrmEmail 과 같은 선택)
  status        String    @db.VarChar(10)
  /// ⚠️ 네트워크 호출 **前에** 올린다 — 도중에 죽어도 같은 건을 무한히 다시 집지 않는다.
  attemptCount  Int       @default(0)
  nextAttemptAt DateTime?
  errorMsg      String?   @db.VarChar(500)
  createdAt     DateTime  @default(now())
  sentAt        DateTime?
  /// 고객이 이 요청으로 리뷰를 제출한 시각(최초 1회). 링크 재방문 시 '작성 완료' 표시 근거.
  submittedAt   DateTime?
  order         Order     @relation(fields: [orderId], references: [id], onDelete: Cascade)
  brand         Brand     @relation(fields: [brandId], references: [id], onDelete: Cascade)

  @@unique([orderId, brandId])
  @@index([status, nextAttemptAt])
  @@index([brandId])
}
```

---

## 서버 구성

`modules/reviews/` 는 평면 규칙(`CLAUDE.md` 코드 구조 규칙 4)을 지켜 파일을 더한다.

| 새 파일 | 역할 |
|---|---|
| `review-link-token.ts` | HMAC 서명/검증 (순수) |
| `review-request.service.ts` | `scanDue()` enqueue + `drain()` 발송 + `submittedAt` 마킹 |
| `review-request.cron.ts` | `@Cron('*/10 * * * *', { timeZone: 'Asia/Seoul', name: 'review-request-dispatch' })` + `private running` 재진입 가드 |
| `review-request-email.ts` | 8 locale 문구 테이블 → `{ subject, html }` |
| `__tests__/review-request.spec.ts` · `__tests__/review-submit.spec.ts` | |

`common/country-locale.ts` 신규 — `countryToLocale(iso2): Locale`.
⚠️ **klow_web `src/lib/locale.ts` `COUNTRY_TO_LOCALE` 의 의도적 미러**(klow_brand
`src/lib/i18n.ts` 가 이미 같은 미러다). 어긋나면 손해가 "그 손님이 영어 메일을 받는다"로
한정되므로 칼럼·마이그레이션을 만들지 않고, **키 집합을 잠그는 spec** 을 함께 둔다.
⚠️ `common/` 은 `modules/` 를 import 하지 않는다(`CLAUDE.md` 규칙 2) — locale 유니온을
`modules/products/product-translation.service.ts` 에서 당겨오지 말고 이 파일이 자체 정의한다.

`ReviewsModule` 에 `WebAuthModule` import 추가 → `EmailService` 주입(이미 export 돼 있다).
`EmailService.sendReviewRequest(mail)` 추가 — **트랜잭션 도메인(`EMAIL_FROM`)**,
CRM(`mail.klow.kr`)이 아니다. 본문 마크업·톤은 `buildOrderConfirmationHtml` 을 따른다
(CTA 버튼 1개 + 원문 링크 1줄). ⚠️ 브랜드명·수신자명에 `escapeHtml` 필수 — 둘 다 외부 입력.
⚠️ `BrandCrmOptOut`(brandId, email) 히트는 **보내지 않고 `status='skipped'`**.

### 토큰 — `review-link-token.ts`

`brand-crm/unsubscribe-token.ts` 와 **같은 모양**으로 쓴다.

```ts
// payload = `${orderId}:${brandId}` (둘 다 cuid 라 ':' 를 담지 않는다 → 첫 ':' 로 가른다)
// 값 = base64url(payload).hex(HMAC-SHA256)   ·   env REVIEW_LINK_SECRET
export function signReviewLinkToken(orderId: string, brandId: string): string;
export function verifyReviewLinkToken(token: string): { orderId: string; brandId: string } | null;
```

- **만료 없음** — 수신함에 영구히 남는 링크에 TTL 을 두면 만료 후 누른 사람에게 할 말이 없다.
- `timingSafeEqual` + **길이 선검사**(길이가 다르면 throw 한다).
- 위조·손상은 **전부 `null`** — 어느 단계에서 틀렸는지 구분해 알리지 않는다(열거 방지).
- `main.ts` 에 운영 부팅 가드 1개
  (`GUEST_ORDER_SECRET`·`CRM_UNSUBSCRIBE_SECRET` 와 같은 꼴, fail-closed).

### 엔드포인트 (전부 토큰 게이트 · Nest 가드 없음)

| Method | Path | 기능 |
|---|---|---|
| GET | `/v1/reviews/form?t=` | `{ brand{name,slug,logo}, locale, receivedProducts[], otherProducts[], written[], defaultUserName, submittedAt }`. `@Throttle` 20/분 |
| POST | `/v1/reviews/submit` | 1~20건 생성. `@Throttle` 5/분 |
| POST | `/v1/reviews/upload` | 토큰 게이트 presign — `UploadInput` 재사용(`kind:'image'` 만) + `scope: 'reviews/<orderId>'`. `@Throttle` 20/분 |

⚠️ **`public-reviews.controller.ts` 안에 넣고 `@Get(':id')` 보다 위에 선언한다** —
`form` 은 리터럴 라우트라 `:id` 가 먼저면 `id='form'` 으로 먹힌다(`translations` 가 이미
같은 이유로 위에 있다).

`common/validation/review.ts` 에 추가:

```ts
export const CustomerReviewItem = z.object({
  productId: z.string().min(1),
  rating: z.coerce.number().int().min(1).max(5),
  // ⚠️ 대행 입력(ReviewInput)엔 상한이 없다 — 공개 표면에는 둔다.
  content: z.string().trim().min(1).max(2000),
  images: z.array(z.string().url()).max(5).default([]),
});
export const CustomerReviewSubmitInput = z.object({
  t: z.string().min(1),
  userName: z.string().trim().min(1).max(40),
  sourceLocale: z.string().trim().max(5).optional(),
  items: z.array(CustomerReviewItem).min(1).max(20),
});
```

`ReviewsService.createFromCustomer(orderId, brandId, dto)`:

1. 전 `productId` 가 그 `brandId` 소유 + `PUBLIC_PRODUCT_WHERE` 통과인지 확인 —
   실패는 **400**(자기 주문 범위 안의 입력 오류라 404 로 숨길 이유가 없다. 브랜드 표면의
   `assertProductsOwned` 가 404 인 것은 *남의* 제품 id 열거를 막기 위한 것이고 여기는 다르다)
2. `$transaction`: `review.createMany`(`source:'customer'`, `orderId`, `sourceLocale`) →
   제품별 `refreshProductAggregates` → `ReviewRequest.submittedAt` 마킹 (G8)
3. `@@unique([orderId, productId])` P2002 → **409** "이미 작성하셨습니다"

### 브랜드·어드민 권한

- `updateForBrand` / `removeForBrand`: 대상이 `source='customer'` 면 **403**
  (`ForbiddenException`, "고객이 직접 작성한 리뷰는 수정·삭제할 수 없습니다").
  ⚠️ 이 한 군데는 404 관례의 **의도된 예외**다 — 브랜드가 그 제품을 실제로 소유하므로 숨길
  것이 없고, 403 이어야 화면이 "왜 안 되는지" 말할 수 있다.
- `BRAND_REVIEW_SELECT` 와 공개 `findAll` 응답에 `source` 추가(배지·버튼 분기의 입력).
- 어드민은 종전대로 전부 수정·삭제 가능 — 스팸·욕설 대응 경로다.

### 번역 (G5)

`review-translation.service.ts`:
- `sourceLocale === target` → 번역 호출 없이 원문, **캐시 행도 만들지 않는다**
- 그 외 → `translateBatch(texts, target, sourceLocale ?? 'ko')`
  (3번째 인자가 이미 `string | null` = 자동감지라 시그니처 변경 없음)

---

## 단계

마이그레이션은 보통 독립 단계지만 **백필이 0건**이고 nullable ADD COLUMN + CREATE TABLE
뿐이라 A행의 첫 순서로 흡수한다. 각 행의 `세션 안 순서`가 곧 **넘칠 때의 정지점**이다.

### A행 — klow_server ①: 스키마 + 토큰 + 조회/제출/업로드 API + 권한

- **읽을 것**: `server/modules/reviews.md` 전체 ·
  [`decisions/products.md#2026-08-18`](../../decisions/products.md#2026-08-18) ·
  [`decisions/shipping-seeding.md#2026-09-14`](../../decisions/shipping-seeding.md#2026-09-14) ·
  이 문서 G4·G5·G7·G8
- **건드리는 레포 · 배포 순서**: klow_server 단독(프론트가 없어 라우트만 떠 있으면 무해)
- **스키마·데이터 위험**: `add_customer_reviews` — nullable ADD COLUMN 3 +
  `CREATE TABLE ReviewRequest` + `CREATE TYPE ReviewSource` + unique 2개.
  **백필 없음 · 롤링 안전.** ⚠️ **git `feat/customer-reviews` + Neon DB 브랜치를 함께 판다.**
- **세션 안 순서**
  1. `schema.prisma` + `npx prisma migrate dev --name add_customer_reviews`
  2. `review-link-token.ts` + `main.ts` 부팅 가드 + `.env.example` 에 `REVIEW_LINK_SECRET`
  3. `validation/review.ts` 추가분 · `ReviewsService.createFromCustomer` ·
     `form` 조회(받은 제품 파생은 G7 의 기존 함수 재사용)
  4. `public-reviews.controller.ts` 에 3 라우트(`form` 을 `:id` 보다 위) + 스로틀
  5. 브랜드 403 가드 + `source` 를 brand/public select 에
  6. `review-translation.service.ts` 를 `sourceLocale` 인식으로 (G5)
  7. `__tests__/review-submit.spec.ts` — 토큰 위조 · 남의 브랜드 productId ·
     게이트 미통과 제품 · 중복 409 · 집계 갱신 · brand PATCH 403. 기존 리뷰 spec 무회귀
- **완료 기준**
  - `npm run typecheck`(tsconfig 2개) · 새 spec + 기존 jest · `npm run test:e2e` ·
    `npm run start` 라우트 수 **+3**
  - 로컬 `curl`: 유효 토큰 `form` 200 → `submit` 2건 → `GET /v1/reviews?productId=` 에 등장 ·
    `Product.rating` 재계산 확인 · 같은 제품 재제출 **409** · 토큰 1글자 변조 **404**
  - `PATCH /v1/brand/reviews/:id` 가 그 리뷰에 **403**

### B행 — klow_server ②: 요청 큐·cron·8개국어 메일 + klow_admin 출처 배지

- **읽을 것**: [`decisions/settlement.md#2026-09-04`](../../decisions/settlement.md#2026-09-04)
  (delivered 코드 단일 출처) · `server/modules/brand-crm.md`(큐 관용구) · 이 문서 G1·G2·G3·G6
- **건드리는 레포 · 배포 순서**: **klow_server → klow_admin**
  (어드민이 먼저면 `source` 없는 응답에 배지 분기가 걸려 전부 '대행'으로 보인다)
- **스키마·데이터 위험**: 없음 (A행에서 끝났다)
- **세션 안 순서**
  1. `common/country-locale.ts` + 키 잠금 spec
  2. `review-request-email.ts` — 8 locale 문구 테이블(`en` 원본 → 7개)
  3. `EmailService.sendReviewRequest`
  4. `review-request.service.ts`
     - `scanDue()` — ① **송장 축**: `status=submitted` +
       (`DOMESTIC` & `brandConfirmedShippedAt` | `latestStatusCode IN EFS_DELIVERED_CODES`) +
       그 시점이 `now - DELAY_DAYS` 이전 + `LOOKBACK_DAYS` 이내 +
       `order` 가 `CONTACT_ORDER_WHERE` + `order.email != ''`
       ② **현장 축**: `channel='onsite'` + `paidAt <= now - DELAY_DAYS` + 같은 조건
       → 기존 `ReviewRequest` 와 차집합 → `createMany({ skipDuplicates: true })`
     - `drain({ max, budgetMs })` — `attemptCount` 를 **호출 전에** 올리고, 성공/포기 시
       `nextAttemptAt = null`, 백오프 `[2m, 10m, 30m]`, `MAX_ATTEMPTS = 3`
       (`crm-email.service.ts` 와 같은 상수·같은 이유)
     - `BrandCrmOptOut` 히트 → `status='skipped'`
  5. `review-request.cron.ts` — `*/10 * * * *` · `private running` 가드 ·
     **`REVIEW_REQUEST_CRON_ENABLED === 'true'` 일 때만**(G6) ·
     ⚠️ `ReviewsModule` **providers 에 등록**(안 넣으면 조용히 안 돈다) ·
     `test/app.e2e-spec.ts` cron 기대 목록에 `review-request-dispatch` 추가
  6. klow_admin `/reviews`: 행에 `고객`/`대행` 배지 + 출처 필터(`sessionStorage` 유지 관례),
     고객 리뷰는 수정 버튼 숨기고 삭제만. `lib/api/reviews.ts` `ReviewDTO` 에 `source`
  7. `__tests__/review-request.spec.ts` — 47·74 도 대상 / 42 제외 / DOMESTIC 은
     `brandConfirmedShippedAt` / 빈 이메일 skip / 취소 주문 제외 / 멀티 브랜드 2행 /
     cron 2회 호출에 행 1개 / opt-out → skipped
- **완료 기준**
  - 검증 3층 + `npm run test:e2e` 의 **cron 개수 13개**
  - staging DB + 로컬 서버: `ALLOW_DEV_TRACKING_OVERRIDE=true` 로 테스트 송장에 `'33'` 주입 →
    `REVIEW_REQUEST_DELAY_DAYS=0` 으로 cron 1회 → `ReviewRequest` 1행 `sent` ·
    `RESEND_API_KEY` 를 비워 `[DEV email]` 로그의 링크 확인 → 그 링크가 A행 `form` 200
  - 멀티 브랜드 주문에서 한쪽 송장만 배송완료 → **1행만** 생긴다
  - klow_admin `npm run build` + 목록에 배지·필터

### C행 — klow_web 작성 페이지 + klow_brand 읽기 전용 + 문서·결정 기록

- **읽을 것**: `klow_web/docs/i18n.md` · klow_web `app/seed/[token]/page.tsx`(토큰 페이지
  관용구 + 수령국 locale) · `app/track/[id]/page.tsx`(`?t=` 관용구)
- **건드리는 레포 · 배포 순서**: **klow_brand → klow_web**, 그 **뒤에**
  `REVIEW_REQUEST_CRON_ENABLED=true` (G6 — 거꾸로면 손님이 404 를 본다)
- **스키마·데이터 위험**: 없음
- **세션 안 순서**
  1. klow_web `src/app/review/[orderId]/page.tsx` — `'use client'`, `?t=` 는
     `useSearchParams`, `useQuery` + `retry:false`. **locale 은 앱 전역이 아니라 서버가 돌려준
     값**을 쓴다(`/seed/[token]` 과 같은 이유 — 수신자는 앱 온보딩을 안 거쳤다).
     `_components/ReviewForm.tsx` — `받으신 제품` / `이 브랜드의 다른 제품` 2섹션, 체크 시
     별점·텍스트·사진 입력 펼침, 이미 쓴 제품은 `작성 완료` 로 비활성
  2. `src/lib/upload.ts` 신규(klow_web 에 없다) — `POST /v1/reviews/upload` presign → R2 PUT.
     최대 5장, `image/jpeg|png|webp` 만
  3. i18n: `src/i18n/locales/en/review.ts` + `en/index.ts` 등록 → `npm run i18n:fill`
     ⚠️ fill 은 `FILL_LOCALES` 전체를 다시 쓰므로 실행 후 **다른 locale 파일은
     `git checkout --`** 로 되돌리고 `git status` 로 확인한다(`labels.category` 큐레이션 값이
     되돌아간다)
  4. 프리뷰 토큰(`/review/preview`, `preview-seeding`, `preview-done`) — `/seed` 관례.
     `reference/preview-pages.md` 에 한 줄
  5. PDP: `components/product/ReviewCard.tsx` 에 `source==='customer'` → `구매 확인` 배지
     (`pdp` ns 키 추가)
  6. klow_brand: `ReviewListItem.tsx` 에 `고객 작성` 배지 + 수정·삭제 버튼 숨김
     (`api-types.ts` `ReviewDTO` 에 `source`)
  7. 문서 — `server/modules/reviews.md`(새 3 라우트 + 403 규칙 + `ReviewRequest`) ·
     `decisions/products.md` 에 항목 **1건** 추가 + `decisions/README.md` 표 +
     **`CLAUDE.md` 의 `## 결정 기록` 색인** 한 줄 + `CLAUDE.md` Where Things Live 한 줄
- **완료 기준**
  - klow_brand·klow_web `npm run build` + `npx eslint <바꾼 파일>` +
    klow_web `npm run type-check`(i18n 파리티)
  - 로컬 :3011 에서 B행이 찍은 실제 메일 링크로 진입 → 받은 제품 2개 + 다른 제품 1개 선택 →
    사진 1장 업로드 → 제출 → PDP 에 `구매 확인` 배지로 노출 · 평점 재계산 반영
  - 같은 링크 재방문 시 그 제품들이 `작성 완료` 로 비활성
  - klow_brand 리뷰 탭에서 그 리뷰에 수정·삭제 버튼이 **없다**
  - `/review/preview` 가 백엔드 없이 뜬다

---

## 재사용할 기존 코드 (새로 쓰지 말 것)

| 무엇 | 어디 |
|---|---|
| 배송완료 코드 판정 | `shipments/efs.client.ts` `EFS_DELIVERED_CODES` · `isDeliveredTrackingCode()` |
| 종착 판정 분기 | `shipments/shipments.service.ts` `isTerminalShipment()` (DOMESTIC vs EFS) |
| 주문 모집단 | `orders/contact-population.ts` `CONTACT_ORDER_WHERE` · `contactChannelOf` |
| 라인↔브랜드 귀속 | `orders/item-brands.ts` `itemBrandIdOf` · `brandOwnedItemWhere` |
| 시딩 실제 제품명 | `seeding/seeding-display-name.ts` `SEEDING_ITEM_NAMES_SELECT` · `seedingItemNames` |
| 라벨 → Product | `seeding/seeding-product-detail.ts` `resolveProductsByLabel` |
| 노출·판매 게이트 | `products/product-selects.ts` `PUBLIC_PRODUCT_WHERE` · `isPurchasable` |
| 집계 갱신 | `reviews/reviews.service.ts` `refreshProductAggregates` |
| HMAC 토큰 꼴 | `brand-crm/unsubscribe-token.ts` (만료 없음 · 열거 방지 · `timingSafeEqual`) |
| 큐·재시도 관용구 | `brand-crm/crm-email.service.ts` + `crm-email-dispatch.cron.ts` (`running` 가드) |
| 메일 발송·HTML 톤 | `web-auth/email.service.ts` `send()` · `buildOrderConfirmationHtml` · `common/html.ts` |
| presign | `upload/r2.service.ts` `getPresignedUploadUrl` · `validation/upload.ts` `UploadInput` |
| 토큰 공개 페이지 | klow_web `app/seed/[token]/page.tsx`(수령국 locale) · `app/track/[id]/page.tsx`(`?t=`) |
| 리뷰 카드 UI | klow_web `components/product/ReviewCard.tsx` · `ReviewImageLightbox.tsx` |
| 다중 이미지 업로드 UI | klow_brand `studio/_components/MultiImageUpload.tsx` (max 5 선례) |

## 새로 생기는 env (klow_server)

| 키 | 기본 | 비고 |
|---|---|---|
| `REVIEW_LINK_SECRET` | 없음 | 운영 미설정이면 **부팅 거부**(fail-closed) / dev 폴백 |
| `REVIEW_REQUEST_CRON_ENABLED` | **off** | `'true'` 일 때만 발송. ⚠️ 다른 cron 과 반대 관례(G6) |
| `REVIEW_REQUEST_DELAY_DAYS` | `3` | 배송완료·결제완료 후 대기 일수 |
| `REVIEW_REQUEST_LOOKBACK_DAYS` | `14` | 처음 켤 때 과거분이 한꺼번에 쏟아지는 것을 막는 창 |
