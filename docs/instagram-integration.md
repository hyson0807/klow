# Instagram 연동 — Meta 앱 셋업 & 운영 가이드

브랜드가 자기 Instagram 계정을 연동해 포스팅 댓글에 브랜드관 링크 DM 을 보내는 기능(klow_brand **인스타그램** 탭)의 **운영 준비** 문서. 코드 구현은 [`docs/server/modules/instagram.md`](./server/modules/instagram.md) 참고.

> ⚠️ **App Review 승인 전엔 실제 브랜드가 쓸 수 없다.** 아래 5의 App Review + Business Verification 이 통과해야 "내 앱에 role 없는 브랜드 계정"에 대해 댓글 조회/DM 발송이 동작한다. 승인 전에는 **앱에 tester role 을 부여한 테스트 IG 계정**으로만 전체 흐름을 검증할 수 있다(코드는 승인 여부와 무관하게 동일).

## 1. Meta 앱 생성

1. [Meta for Developers](https://developers.facebook.com/) → **My Apps** → **Create App**.
2. Use case 는 **Instagram** 계열(비즈니스). 앱 생성 후 대시보드에서 **Instagram** 제품(**Instagram API with Instagram Login**)을 추가한다. *Facebook Login / Facebook Page 는 불필요* — 셀프 온보딩 마찰을 줄이기 위해 Instagram Login 을 쓴다.

## 2. 자격증명 & OAuth 설정

- **App ID / App Secret** 확보 → 서버 env `META_APP_ID` / `META_APP_SECRET`.
- Instagram 앱 설정의 **OAuth redirect URIs** 에 콜백을 등록:
  - 로컬: `http://localhost:4000/v1/brand/instagram/callback`
  - 운영: `https://api.klow.kr/v1/brand/instagram/callback`
  - 이 값은 서버 env `META_BRAND_CALLBACK_URL` 과 **정확히 일치**해야 한다(불일치 시 Meta 가 거부).

## 3. 요청 권한(scope)

동의 화면에서 요청하는 scope (코드 `instagram.client.ts INSTAGRAM_SCOPES`):

| scope | 용도 |
|-------|------|
| `instagram_business_basic` | 기본 프로필/미디어 조회 + 토큰 refresh 필수 |
| `instagram_business_manage_comments` | 댓글 조회 + **private reply 발송** |
| `instagram_business_manage_messages` | 표준 메시징(후속 DM 대비 함께 요청) |

## 4. 테스트 계정 (승인 전 검증용)

- 앱 대시보드 → **Roles / Instagram testers** 에 검증용 **IG 비즈니스/크리에이터 계정**을 tester 로 추가하고, 그 계정에서 초대를 수락한다.
- 이 계정으로 연동 → 포스팅/댓글 조회 → 다른 계정으로 댓글을 달고 → 일괄 발송까지 전 흐름을 Standard Access 로 검증할 수 있다.

## 5. Business Verification + App Review (프로덕션 게이트, 최장 리드타임)

실제 브랜드(내 앱에 role 없는 계정)에 쓰려면 **Advanced Access** 가 필요하고, 이는 아래를 요구한다:

1. **Business Verification** — KLOW 사업자 실체 인증(사업자등록 등 서류).
2. **App Review** — scope 별 제출. 특히 messaging/comments 는 심사가 깐깐하므로 여러 번의 반려를 감안한다. 제출물:
   - 명확한 use-case 설명(브랜드가 자기 계정 연동 → 자기 포스팅 댓글 작성자에게 답장).
   - **스크린캐스트**: 브랜드 로그인 → 인스타그램 탭 → 계정 연동(OAuth 동의) → 포스팅 선택 → 댓글 다중선택 → 템플릿 선택 → DM 발송 → 수신 확인.
   - 개인정보 처리방침 URL, 데이터 사용 설명.
3. 승인 후 각 scope 를 **Advanced Access** 로 승격하면 실제 브랜드에 동작.

> 최소 scope 재검증: private reply 는 문서상 `instagram_business_manage_comments` 만으로 가능하다고 되어 있으나 후속 DM 을 위해 `instagram_business_manage_messages` 도 함께 신청한다. App Review 제출 시 실제 필요한 최소 scope 를 재확인할 것.

## 6. 서버 환경변수

```bash
META_APP_ID=...
META_APP_SECRET=...
META_BRAND_CALLBACK_URL=https://api.klow.kr/v1/brand/instagram/callback   # 로컬: http://localhost:4000/...
META_GRAPH_VERSION=v21.0
META_TOKEN_ENCRYPTION_KEY=<base64 of 32 random bytes>                     # openssl rand -base64 32
```

- `META_TOKEN_ENCRYPTION_KEY` 는 장기토큰 암호화 키(AES-256-GCM). **회전 금지**(회전하면 기존 연동 토큰 복호화 불가 → 전 브랜드 재연동 필요).
- 브랜드관 링크 base 는 결제와 동일한 `FRONTEND_URL`(klow_web origin)을 재사용한다.

## 7. 마이그레이션

스키마에 `InstagramConnection` / `InstagramTemplate` / `InstagramReply` 3개 모델이 추가된다. **CLAUDE.md 규칙에 따라 직접 실행**:

```bash
cd klow_server && npx prisma migrate dev --name add_instagram_integration
```

## 7-1. ⚠️ 개발 모드 → 라이브 전환 (댓글 읽기 필수 조건)

**개발(Development) 모드에서는 `GET /{media-id}/comments` 가 항상 빈 배열을 반환한다** (`comments_count` 는 정상인데 `data:[]`). 실제 검증 중 확인된 Meta 동작으로, 우리 코드 문제가 아니다. 해결:

1. **기본 설정**에 실제 URL 채우기: 개인정보처리방침 `https://brand.klow.kr/legal/privacy`, 서비스 약관 `https://brand.klow.kr/legal/terms`, 데이터 삭제 안내 URL(콜백 아님)도 privacy 페이지로.
2. 대시보드에서 앱을 **라이브(Live)** 로 전환("게시").
3. **본인 소유 비즈니스 계정(테스터로 등록된 그 계정)의 댓글 읽기는 App Review/비즈니스 인증 없이** 라이브 전환만으로 동작한다. App Review 는 "다른 사람 계정" 데이터를 쓸 때만 필요.

## 7-2. 댓글 작성자 username 제약 → `{username}` 폴백

표준 액세스(App Review 전)에서는 **타인이 단 댓글의 `username` 필드를 Instagram 이 내려주지 않는다**(본인 계정 댓글만 제공). 그래서 `{username}` 이 빈 값이 되어 "@님"처럼 깨질 수 있어, 서버 `renderTemplate` 이 **선행 `@` 까지 흡수해 `고객` 으로 폴백**한다(`instagram.service.ts` `USERNAME_FALLBACK`). 실제 작성자 핸들(`@pibugom` 등)은 **Advanced Access(App Review 승인) 이후** 채워질 것으로 기대된다.

## 8. 운영 상 유의

- **레이트리밋 750/hr/계정** — 대량 일괄 발송 시 서버가 순차 처리하고 초과분은 `skipped`/`failed` 로 리포트. 배치 상한은 요청당 100개(zod).
- **7일 규칙** — 댓글 후 7일 지난 건 발송 불가(UI 비활성 + 서버 재검증).
- **중복 방지** — `InstagramReply.commentId @unique` 로 한 댓글에 두 번 발송 불가.
- **영구 연동** — refresh cron 이 매일 토큰을 갱신하므로 브랜드는 재연동 불필요. cron 이 오래 멈춰 토큰이 만료되면 `connection` 응답의 `needsReconnect=true` 로 UI 가 재연동을 안내한다.
