# klow_server API 문서

NestJS 백엔드(`klow_server`, port 4000)의 **모듈별 엔드포인트** 한눈에 보기 문서입니다. 각 모듈 안의 컨트롤러는 URL prefix 로 역할이 나뉘어 있습니다.

## URL 표면(Surface) 컨벤션

| Prefix             | 클라이언트                | 인증 가드                    | 비고                                                    |
|--------------------|---------------------------|------------------------------|---------------------------------------------------------|
| `/admin/*`         | `klow_admin` (port 3000)  | `AdminGuard` (+SuperAdmin)   | 어드민 풀-CRUD. 모든 mutation 은 `AdminAuditLog` 기록.  |
| `/v1/*`            | `klow_web` (port 3001)    | `UserGuard` 또는 public      | 공개 surface. 로그인 필요시 `UserGuard`.                |
| `/v1/brand/*`      | `klow_brand` (port 3002)  | `BrandGuard` 또는 public     | 브랜드 셀프-서비스. 자기 브랜드 scope.                  |
| `/webhooks/*`      | 외부 (Eximbay 등)         | IP 화이트리스트              | 결제사 콜백 등.                                         |
| `/embed/*`         | 브랜드 자사몰(카페24) 등  | 없음 (공개)                  | 임베드 버튼. GET 전용·쿠키 없음·CORS `*`. ⚠️ preflight 유발 금지 — [embed](./modules/embed.md) 참고. |

## 인증 가드

| Guard              | 쿠키            | 용도                                                                  |
|--------------------|-----------------|-----------------------------------------------------------------------|
| `UserGuard`        | `klow_sid`      | 일반 유저 세션. `klow_web` 의 로그인 후 사용 영역.                    |
| `AdminGuard`       | `klow_admin_sid`| 어드민 세션. 60분 idle / 24h 절대만료(`ADMIN_IDLE_TIMEOUT_MINUTES` / `ADMIN_SESSION_TTL_HOURS`). |
| `SuperAdminGuard`  | (위와 동일)     | 어드민 중 `super` role 만 허용(`AdminRole` = `operator`\|`super`). `admins`, `audit-logs`, `efs-billing` 라우트. |
| `BrandGuard`       | `klow_brand_sid`| 브랜드 사용자 세션. 7일 만료, phone/email/google 가입 모두 호환.      |
| `AuthGuard('google')` 등 | (Passport)| Google OAuth callback 처리용.                                         |
| `public`           | -               | 누구나. 단, sensitive 라우트는 `Throttler` 적용.                       |

## 모듈 색인

> 32개 모듈, 약 200여 개 엔드포인트. 각 모듈 문서는 [`modules/`](./modules/) 폴더 참고.

| 카테고리   | 모듈                                                                  | 주요 책임                                                |
|------------|-----------------------------------------------------------------------|----------------------------------------------------------|
| **인증**   | [web-auth](./modules/web-auth.md)                                             | 일반 유저 가입/로그인 (email OTP + Google OAuth)         |
|            | [admin-auth](./modules/admin-auth.md)                                 | 어드민 로그인 (TOTP 2FA), 초대, admins 관리              |
|            | [brand-auth](./modules/brand-auth.md)                                 | 브랜드 가입/로그인 (phone OTP 메인 + email + Google)     |
| **감사**   | [audit-logs](./modules/audit-logs.md)                                 | `AdminAuditLog` 조회 (super-admin 전용)                  |
| **상품**   | [products](./modules/products.md)                                     | 상품 CRUD + 공개 카탈로그 (`PUBLIC_PRODUCT_WHERE` 필터)  |
|            | [brands](./modules/brands.md)                                         | 브랜드 CRUD + 공개 조회 (slug/id)                        |
|            | [reviews](./modules/reviews.md)                                       | 리뷰 CRUD + 공개 조회                                    |
|            | [shop](./modules/shop.md)                                             | 운영 환율 조회(`/v1/shop/fx-rate`) — Today's Pick·쇼핑 설정은 2026-07-30 제거 |
|            | [currency](./modules/currency.md)                                     | 통화 환율 — 표시용 현지통화 + 정산 정본 KRW (cron 자동 갱신 + 어드민 수동 보정) |
|            | [curated-influencers](./modules/curated-influencers.md)               | 큐레이티드 인플루언서 (입점 시 크리에이터 매칭용)        |
| **주문**   | [cart](./modules/cart.md)                                             | 유저 장바구니 (merge 포함)                               |
|            | [orders](./modules/orders.md)                                         | 주문 생성/견적/조회/취소/환불 (USD, 약관동의 + IP, 게스트 흐름, 현장 QR 주문) |
|            | [payment](./modules/payment.md)                                       | Eximbay 결제 prepare/verify, webhook                     |
| **배송**   | [shipping](./modules/shipping.md)                                     | 국가×무게 요율표(시딩·일반주문 공용), 캐리어·EFS 제외지역, 국가 설정 |
|            | [shipments](./modules/shipments.md)                                   | 브랜드별 EFS 송장 발급·취소 + 배송추적                   |
|            | [seeding](./modules/seeding.md)                                       | 크리에이터 시딩(샘플) 링크 + EMS/DHL 비교요율            |
| **브랜드 자체 서비스** | [brand-applications](./modules/brand-applications.md)     | 브랜드 입점 신청 + 자체 상품 등록 (셀프-서비스)          |
|            | [subscription](./modules/subscription.md)                             | 브랜드 멤버십 정기구독 (NicePay 빌링) + 승인 게이트      |
|            | [brand-scraper](./modules/brand-scraper.md)                           | 자사몰 URL → AI 자동 데이터 추출                         |
| **고객**   | [customers](./modules/customers.md)                                   | 어드민이 보는 유저 목록/상세                             |
|            | [contact](./modules/contact.md)                                       | 랜딩 "상담 문의" 폼 → 운영팀 문의함 메일 (저장 없음)     |
| **마케팅** | [promotions](./modules/promotions.md)                                  | 인플루언서 할인가 브랜드관 링크(제품×국가 세일가) + 유입 추적 |
|            | [embed](./modules/embed.md)                                          | 브랜드 자사몰(카페24)에 다는 KLOW 해외구매 버튼 (`/embed/*`, 공개·CORS `*`) |
|            | [instagram](./modules/instagram.md)                                  | 브랜드 IG 계정 연동 → 포스팅 댓글에 브랜드관 링크 DM(private reply) |
| **운영**   | [stats](./modules/stats.md)                                           | 어드민 대시보드 카운트 + 수익(KPI) + 주간 수출 물량      |
|            | [settlement](./modules/settlement.md)                                 | 브랜드 매출 정산 (delivered 송장 + 현장결제 주문 집계)   |
|            | [efs-billing](./modules/efs-billing.md)                               | EFS 배송비 브랜드 후청구 (시딩+일반, 정산표 업로드·청구서) |
|            | [upload](./modules/upload.md)                                         | R2 presigned URL 발급 (admin / brand scope)              |
|            | [translation](./modules/translation.md)                              | Google 번역 v2 래퍼 (DB 콘텐츠 다국어, 내부 서비스)     |

## 공통 미들웨어

- **Throttler** — sensitive 엔드포인트(`login`, `signup`, `send-verification`, OTP 발송, `payment/verify`, 시딩 claim/checkout, scraper 등)에 `@Throttle()` 적용. 미지정 라우트는 전역 기본(60회 / 분 / IP).
  - `THROTTLE_TIGHT`: 5회 / 분 / IP
  - `THROTTLE_LOOSE`: 10회 / 분 / IP
  - 개별 지정: `POST /v1/brand/translate` 20회 / 분, scraper `analyze-homepage`·`analyze-deck` 3회 / 분, `analyze-product` 6회 / 분 (전부 유료 외부 API 호출)
- **AdminAuditInterceptor** — `/admin/*` 의 모든 non-GET 응답을 `AdminAuditLog` 에 자동 기록 (password/code/token 류 redact).
- **ZodValidationPipe** — `src/common/validation/`(도메인별 분할, index 배럴) 의 zod 스키마로 body/query 검증.
- **PUBLIC_PRODUCT_WHERE** (= `PURCHASABLE_PRODUCT_WHERE`, 노출 == 구매 가능) — 공개 surface 에서 `Brand.status=approved` & `Product.status=approved` + 대표사진 + 판매가 완성도(`hasSellablePrice`) + `Product.hidden=false` 를 모두 만족해야 노출/판매된다. 추가로 **구독 게이트**: 가입 brand(`submittedById != null`)는 `BrandSubscription.status='active'` 동안만 노출/판매되고, 어드민이 직접 만든 brand(`submittedById = null`) 와 legacy(`brandId = null`) 제품은 면제. ([subscription](./modules/subscription.md), `product-selects.ts`.) ⚠️ 브랜드관 자체의 공개 필터(`PUBLIC_BRAND_WHERE`)는 이보다 느슨하다 — [brands](./modules/brands.md) 참고.

## 변경 이력

- 이 문서는 `npm run start:dev` 시점의 컨트롤러 라우팅을 기준으로 작성됨.
- 컨트롤러를 추가/수정하면 해당 모듈 문서를 함께 업데이트할 것.
