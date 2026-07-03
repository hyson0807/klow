# klow_server API 문서

NestJS 백엔드(`klow_server`, port 4000)의 **모듈별 엔드포인트** 한눈에 보기 문서입니다. 각 모듈 안의 컨트롤러는 URL prefix 로 역할이 나뉘어 있습니다.

## URL 표면(Surface) 컨벤션

| Prefix             | 클라이언트                | 인증 가드                    | 비고                                                    |
|--------------------|---------------------------|------------------------------|---------------------------------------------------------|
| `/admin/*`         | `klow_admin` (port 3000)  | `AdminGuard` (+SuperAdmin)   | 어드민 풀-CRUD. 모든 mutation 은 `AdminAuditLog` 기록.  |
| `/v1/*`            | `klow_web` (port 3001)    | `UserGuard` 또는 public      | 공개 surface. 로그인 필요시 `UserGuard`.                |
| `/v1/brand/*`      | `klow_brand` (port 3002)  | `BrandGuard` 또는 public     | 브랜드 셀프-서비스. 자기 브랜드 scope.                  |
| `/webhooks/*`      | 외부 (Eximbay 등)         | IP 화이트리스트              | 결제사 콜백 등.                                         |

## 인증 가드

| Guard              | 쿠키            | 용도                                                                  |
|--------------------|-----------------|-----------------------------------------------------------------------|
| `UserGuard`        | `klow_sid`      | 일반 유저 세션. `klow_web` 의 로그인 후 사용 영역.                    |
| `AdminGuard`       | `klow_admin_sid`| 어드민 세션. 60분 idle / 24h 절대만료.                                |
| `SuperAdminGuard`  | (위와 동일)     | 어드민 중 `SUPER` role 만 허용. `admins`, `audit-logs` 라우트.        |
| `BrandGuard`       | `klow_brand_sid`| 브랜드 사용자 세션. 7일 만료, phone/email/google 가입 모두 호환.      |
| `AuthGuard('google')` 등 | (Passport)| Google OAuth callback 처리용.                                         |
| `public`           | -               | 누구나. 단, sensitive 라우트는 `Throttler` 적용.                       |

## 모듈 색인

> 28개 모듈, 약 200여 개 엔드포인트. 각 모듈 문서는 [`modules/`](./modules/) 폴더 참고.

| 카테고리   | 모듈                                                                  | 주요 책임                                                |
|------------|-----------------------------------------------------------------------|----------------------------------------------------------|
| **인증**   | [auth](./modules/auth.md)                                             | 일반 유저 가입/로그인 (email OTP + Google OAuth)         |
|            | [admin-auth](./modules/admin-auth.md)                                 | 어드민 로그인 (TOTP 2FA), 초대, admins 관리              |
|            | [brand-auth](./modules/brand-auth.md)                                 | 브랜드 가입/로그인 (phone OTP 메인 + email + Google)     |
| **감사**   | [audit-logs](./modules/audit-logs.md)                                 | `AdminAuditLog` 조회 (super-admin 전용)                  |
| **상품**   | [products](./modules/products.md)                                     | 상품 CRUD + 공개 카탈로그 (`PUBLIC_PRODUCT_WHERE` 필터)  |
|            | [brands](./modules/brands.md)                                         | 브랜드 CRUD + 공개 조회 (slug/id)                        |
|            | [creators](./modules/creators.md)                                     | 크리에이터 CRUD + 공개 조회 (상품 연관 포함)             |
|            | [videos](./modules/videos.md)                                         | 비디오 CRUD + 공개 조회 (creatorId/productId 필터)       |
|            | [reviews](./modules/reviews.md)                                       | 리뷰 CRUD + 공개 조회                                    |
|            | [discover](./modules/discover.md)                                     | 피부/관심사 기반 상품 추천 피드                          |
|            | [shop](./modules/shop.md)                                             | 오늘의 추천(Today's Pick), 환율, 쇼핑 설정, 가격 미리보기 |
|            | [curated-influencers](./modules/curated-influencers.md)               | 큐레이티드 인플루언서 (입점 시 크리에이터 매칭용)        |
| **주문**   | [cart](./modules/cart.md)                                             | 유저 장바구니 (merge 포함)                               |
|            | [orders](./modules/orders.md)                                         | 주문 생성/조회/취소/환불 (USD, 약관동의 + IP, 게스트 흐름) |
|            | [payment](./modules/payment.md)                                       | Eximbay 결제 prepare/verify, webhook                     |
| **배송**   | [shipping](./modules/shipping.md)                                     | 국가별 배송설정(물류비/캐리어), EFS 제외지역             |
|            | [shipments](./modules/shipments.md)                                   | 브랜드별 EFS 송장 발급 + 배송추적                        |
|            | [seeding](./modules/seeding.md)                                       | 크리에이터 시딩(샘플) 링크 + 시딩 배송요율              |
| **브랜드 자체 서비스** | [brand-applications](./modules/brand-applications.md)     | 브랜드 입점 신청 + 자체 상품 등록 (셀프-서비스)          |
|            | [subscription](./modules/subscription.md)                             | 브랜드 멤버십 정기구독 (NicePay 빌링) + 승인 게이트      |
|            | [brand-scraper](./modules/brand-scraper.md)                           | 자사몰 URL → AI 자동 데이터 추출                         |
| **고객**   | [customers](./modules/customers.md)                                   | 어드민이 보는 유저 목록/상세                             |
| **컨시어지**| [concierge](./modules/concierge.md)                                  | 공개 폼 제출 + 어드민 검토                               |
| **마케팅** | [campaigns](./modules/campaigns.md)                                  | 인플루언서 캠페인 단축링크(`/r/{code}`) + 유입 추적      |
| **운영**   | [stats](./modules/stats.md)                                           | 어드민 대시보드 카운트 + 수익(KPI)                       |
|            | [settlement](./modules/settlement.md)                                 | 브랜드 매출 정산 (delivered 송장 집계)                   |
|            | [upload](./modules/upload.md)                                         | R2 presigned URL 발급 (admin / brand scope)              |
|            | [translation](./modules/translation.md)                              | Google 번역 v2 래퍼 (DB 콘텐츠 다국어, 내부 서비스)     |

## 공통 미들웨어

- **Throttler** — sensitive 엔드포인트(`login`, `signup`, `send-verification`, scraper)에 `@Throttle()` 적용.
  - `THROTTLE_TIGHT`: 5회 / 분 / IP
  - `THROTTLE_LOOSE`: 10회 / 분 / IP
- **AdminAuditInterceptor** — `/admin/*` 의 모든 non-GET 응답을 `AdminAuditLog` 에 자동 기록 (password/code/token 류 redact).
- **ZodValidationPipe** — `src/common/validation.ts` 의 zod 스키마로 body/query 검증.
- **PUBLIC_PRODUCT_WHERE** — 공개 surface 에서 `Brand.status=approved` & `Product.status=approved` 만 노출. 추가로 **구독 게이트**: 가입 brand(`submittedById != null`)는 `BrandSubscription.status='active'` 동안만 노출/판매되고, 어드민이 직접 만든 brand(`submittedById = null`) 와 legacy(`brandId = null`) 제품은 면제. ([subscription](./modules/subscription.md), `product-selects.ts`.)

## 변경 이력

- 이 문서는 `npm run start:dev` 시점의 컨트롤러 라우팅을 기준으로 작성됨.
- 컨트롤러를 추가/수정하면 해당 모듈 문서를 함께 업데이트할 것.
