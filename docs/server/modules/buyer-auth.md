# buyer-auth — 바이어 계정 (klow.kr/ 바이어 공간 로그인·가입 · 어드민 검수)

- **모듈 경로**: `src/modules/buyer-auth/`
- **목적**: 바이어 공간(`klow.kr/`, [buyer](./buyer.md))의 **바이어 계정**. 이메일+비밀번호 로그인, 3단계 가입(마지막에 이메일 OTP · 사업자등록증/매장 사진 업로드), 비밀번호 찾기, 그리고 어드민이 가입 바이어를 보고 검수 상태(“Verified buyer” 배지)를 정하는 API.
- **설계 정본**: [`docs/plan/buyer-auth/`](../../plan/buyer-auth/README.md) — 불변식 G1~G7 은 `implementation-plan.md §1`.
- **관련 파일**: `buyer-auth.service.ts` · `public-buyer-auth.controller.ts` · `admin-buyer-accounts.controller.ts` · `buyer.guard.ts` + `current-buyer.decorator.ts` · `buyer-session.ts`(쿠키 인스턴스 · TTL) · `buyer-document-key.ts`(서류 R2 키 생성·검증 — 순수) · 검증 `common/validation/buyer-auth.ts` · OTP `web-auth/email-verification.service.ts`(`buyer-` purpose 분기) · 메일 `web-auth/email.service.ts#sendBuyerSignupCode`/`sendBuyerPasswordResetCode`(영어) · R2 `upload/r2.service.ts#getPresignedPrivateUploadUrl`/`headObject`/`getBytes`
- **마이그레이션**: `20261008050340_add_buyer_auth` — 신규 테이블 3(`BuyerUser`·`BuyerSession`·`BuyerUserDocument`) + enum 2(`BuyerUserStatus`·`BuyerDocumentKind`). 전부 `CREATE` 라 롤링 안전, 백필 없음.
- **env**: `BUYER_SESSION_COOKIE_NAME`(기본 `klow_buyer_sid`) · `BUYER_SESSION_TTL_DAYS`(기본 30). cron 없음.

⚠️⚠️ **소비자 로그인과 완전히 분리한다(G1).** `User`·`Session`·`klow_sid`·`/v1/auth/*` 를 읽지도 쓰지도 않는다. 같은 이메일이 소비자 계정과 바이어 계정을 둘 다 가져도 서로 모르는 별개 계정이다. 재사용은 `EmailVerificationService`(OTP 테이블 `EmailVerification`, purpose 로 분리)·`common/password`·`common/cookies` 배관까지만.

## 데이터 모델

| 모델 | 역할 |
|---|---|
| `BuyerUser` | 계정 + 가입 프로필(이름·전화 `dial`+`phone`·국가·회사·업종·통화·판매 채널·웹사이트·관심 브랜드 slug·추천 코드). `email` 은 `trim().toLowerCase()`(G6). `status` = `pending`(기본) / `verified` / `rejected` + 어드민 메모(`statusNote` — 바이어에게 안 보임)·변경 시각·변경 어드민 id. `lastSeenAt` = 계정 레벨 마지막 접속 |
| `BuyerSession` | `BrandSession` 과 같은 모양 + **`persistent`**(“Keep me signed in” — false 면 쿠키에 maxAge 없음). 만료 세션은 조회 시 하드 삭제 |
| `BuyerUserDocument` | 가입 서류. `kind` = `business_license` / `store_photo`, **R2 키만** 저장(`buyer-docs/<uuid>/<128bit hex>.<ext>`), 원본 파일명·MIME·크기(R2 실측) |

`interestedBrands` 는 `Brand.slug` 문자열 배열 — FK 아님(브랜드가 사라져도 가입 기록은 남는다). 어드민 상세가 이름을 조인하고, 사라진 slug 는 `name: null`.

## 세션

- 쿠키 `klow_buyer_sid`, 서버 TTL **30일**. **슬라이딩**: 세션 검증(가드·`GET me`) 때 남은 기간이 **TTL 절반(15일) 아래**면 `expiresAt = now + 30일` 로 갱신하고, **영속 쿠키였을 때만** 쿠키를 다시 내린다(세션 쿠키가 영속 쿠키로 바뀌지 않게). 한 달에 한 번이라도 들어오면 로그아웃되지 않는다.
- `keepSignedIn: false`(로그인·가입) → 같은 서버 TTL + **maxAge 없는 브라우저 세션 쿠키**.
- `lastSeenAt` 은 5분 스로틀(fire-and-forget) + 세션 생성 시 한 번.
- 비밀번호 재설정 confirm 은 그 계정의 **전 세션을 삭제**하고 새 세션 하나만 발급한다.
- `makeCookieHelpers().set(res, value, { persistent })` 의 세 번째 인자는 이 모듈을 위해 추가했다(기본 true — 기존 소비자 무변경).

## public-buyer-auth.controller.ts (`@Controller('v1/buyer/auth')`)

바이어 화면이 영어라 에러는 `{ code, message }`(영어)로 낸다. 스로틀 TIGHT = 5회/분, LOOSE = 10회/분(IP).

| 메서드 · 경로 | 가드 · 스로틀 | 동작 |
|---|---|---|
| `POST send-code` `{email}` | TIGHT | 가입 OTP 발송(purpose `buyer-signup-otp`). 이미 바이어 계정이 있으면 409 `email_taken` |
| `POST verify-code` `{email, code}` | LOOSE | → `{token}`(15분, purpose `buyer-signup-token`). 오답·만료·시도 초과는 400 `invalid_code` 하나 |
| `POST documents/presign` `{token, email, kind, fileName, contentType, size}` | TIGHT | 토큰 **검증만**(소비 안 함 — 파일이 2개). pdf/jpeg/png/webp · ≤10MB. → `{uploadUrl, key}` — **publicUrl 없음(G2)**. 토큰 무효 400 `verification_expired` |
| `POST signup` | TIGHT | 서류 키 형식(`buyer-document-key.ts`) → 이메일 중복 → R2 `HEAD` 로 업로드 확인·크기 실측 → **토큰 1회 소비** → 계정 + 서류 행 → 세션 + 쿠키 → `{user}`. 서류는 0~2개, 종류당 1개(사업자등록증도 선택 — 디자인 그대로) |
| `POST login` `{email, password, keepSignedIn?}` | LOOSE | 없는 이메일·틀린 비번 모두 **401 `invalid_credentials`**(가입 여부 비공개) |
| `POST logout` | — | 세션 행 삭제 + 쿠키 지움 |
| `GET me` | 쿠키 직접(가드 없음) | `{user}` — 비로그인 401. 슬라이딩 연장 시 쿠키 재발급 |
| `PATCH me` | `BuyerGuard` | 이름·전화·회사·업종·통화·채널·웹사이트(`""`/null = 지움)·관심 브랜드. 이메일·상태는 못 바꾼다(보내도 버려진다) |
| `POST password-reset/send-otp` `{email}` | TIGHT | **없는 이메일도 200**(가입 여부 비공개 — 브랜드와 다르다). 있으면 OTP(purpose `buyer-password-reset-otp`) |
| `POST password-reset/verify-otp` `{email, code}` | LOOSE | → `{token}` |
| `POST password-reset/confirm` `{email, token, password}` | LOOSE | 비번 갱신 + 전 세션 삭제(트랜잭션) → 새 영속 세션 + 쿠키 → `{user}` |

`user` 모양(`PublicBuyer`): `id · email · name · dial · phone · country · company · businessType · currency · channels · website · interestedBrands · referral · status · createdAt · documents[{id, kind, fileName}]`. ⚠️ 서류 키·URL 과 `statusNote` 는 싣지 않는다.

비밀번호: 8~128자(디자인 그대로 — 브랜드처럼 영문+숫자 강제 없음).

⚠️ **OTP 메일은 영어(G7).** `EmailVerificationService.issueOtp` 는 purpose 접두로 템플릿을 고르고, 모르는 접두는 한국어 소비자 가입 메일로 떨어진다. 그래서 `buyer-password-reset*` → `buyer-*` 분기가 **맨 앞**에 있다. 새 바이어 purpose 도 `buyer-` 로 시작할 것.

## admin-buyer-accounts.controller.ts (`@Controller('admin/buyer/accounts')`, AdminGuard — 모든 어드민)

mutation 은 `AdminAuditInterceptor` 가 자동 기록한다. 화면은 klow_admin **바이어 공간 > 바이어 계정**(`(authed)/buyer/accounts/` — 서류는 인증 fetch → Blob 으로 미리보기).

| 메서드 · 경로 | 동작 |
|---|---|
| `GET /admin/buyer/accounts?q=&status=&page=` | 이메일·이름·회사 부분일치 검색, 상태 필터, 최신 가입순 50개/쪽 → `{items[{id,email,name,company,country,businessType,status,createdAt,lastSeenAt,documentCount}], total, page, pageSize, statusCounts{pending,verified,rejected}}` |
| `GET /admin/buyer/accounts/:id` | 가입 정보 전부(비번 해시 제외) + `interestedBrands[{slug, name}]` + `statusChangedBy{email,name}` + 서류 메타 `[{id, kind, fileName, contentType, size, createdAt}]` |
| `PATCH /admin/buyer/accounts/:id/status` `{status, note?}` | 상태 + 변경 시각·어드민 기록. `note` 생략 = 메모 유지, `""` = 지움 → 상세 모양 반환 |
| `GET /admin/buyer/accounts/:id/documents/:docId` | 서류 원본을 **서버가 중계**(`R2Service.getBytes`) — `Content-Type` 원본 · `Content-Disposition: inline; filename*=` · `X-Content-Type-Options: nosniff` · `Content-Security-Policy: sandbox` · `Cache-Control: private, no-store` |

## 서류 비공개(G2)

R2 버킷(`klow`/`klow-staging`)은 **공개 버킷**이라 키를 알면 누구나 읽는다. 그래서 —

- 키는 서버가 만들고 추측 불가(`randomUUID` + `randomBytes(16)`), 원본 파일명은 키에 넣지 않는다.
- presign 응답·DB·바이어 응답·어드민 응답 어디에도 공개 URL 이 없다. 어드민은 위 프록시로만 받는다.
- `signup` 은 클라가 돌려준 키가 이 형식이고 확장자가 선언 MIME 과 맞는지, 그리고 실제로 업로드됐는지(`HEAD`)를 본다 — 다른 경로의 오브젝트를 서류로 붙이지 못하게.
- ⚠️ 클라(klow_web)가 R2 에 직접 PUT 하므로 버킷 CORS 에 klow_web 오리진이 있어야 한다(고객 리뷰 사진과 같은 조건 — `decisions/products.md#2026-10-01`).

## 스코프 밖 (트랙 README)

샘플 주문·결제 · 문의를 계정에 연결 · **서버측 구간가 은닉**(블러는 여전히 화면 가림) · 탈퇴 · 로그인 실패 잠금(스로틀로 대신) · 이메일 변경 · 2FA · 소셜.
