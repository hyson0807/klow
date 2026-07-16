# instagram 모듈

브랜드가 자기 **Instagram 비즈니스/크리에이터 계정**을 연동하고, 자기 포스팅에 달린 댓글에 **브랜드관 링크(klow.kr/{slug})가 담긴 DM(private reply)** 을 일괄 발송하는 모듈. 목적은 댓글 단 사람을 브랜드관으로 유입시켜 구매로 잇는 것.

- 소스: `klow_server/src/modules/instagram/`
- 프론트: `klow_brand` **인스타그램** 탭 (`src/app/(authed)/instagram/`)
- 사전 준비/운영 가이드: [`docs/instagram-integration.md`](../../instagram-integration.md)

## 핵심 제약 (Meta Instagram Platform API)

- **제품**: "Instagram API with **Instagram Login**" — Facebook 페이지 불필요. OAuth 는 instagram.com / graph.instagram.com.
- **DM 은 private reply 만 가능**: 댓글 작성자는 브랜드에게 먼저 DM 한 적이 없으므로 일반 DM(24h 윈도우) 불가. `recipient:{comment_id}` 로 보내는 private reply 가 유일한 합법 경로. **댓글 1개당 평생 1회**, **댓글 후 7일 이내**, **750 calls/hour/계정** 레이트리밋.
- **공동작업 게시물**: 실제 publish 한 계정만 댓글/DM API 접근 가능 → 브랜드가 collaborator 로만 초대된 포스팅은 댓글이 비어 보임(정상).
- **App Review 게이트**: `instagram_business_manage_comments` / `instagram_business_manage_messages` 는 내 앱에 role 없는 실제 브랜드 계정에 쓰려면 **Advanced Access(App Review + Business Verification)** 필요. 승인 전엔 앱에 tester role 부여한 테스트 계정만 동작.

## 토큰 & 영구 연동

- 연동 시 단기토큰 → **60일 장기토큰** 교환 후 AES-256-GCM 암호문(`InstagramConnection.accessTokenEnc`)으로 저장. 평문 토큰은 저장/로깅하지 않는다. (`instagram-crypto.ts`, env `META_TOKEN_ENCRYPTION_KEY`)
- **`InstagramRefreshCron`** 이 매일 KST 03:00 실행 — 만료 10일 이내 연동을 `refresh_access_token` 로 롤포워드. 브랜드는 재인증 없이 **영구 연동** 유지. 브랜드 로그인 세션(`klow_brand_sid`)과 무관.

## 데이터 모델

- `InstagramConnection` — brand당 1개(`brandId @unique`). `igUserId`/`igUsername`/`accessTokenEnc`/`tokenExpiresAt`/`lastRefreshedAt`.
- `InstagramTemplate` — brand당 N개. `name`/`body`(토큰 `{link}`·`{username}`).
- `InstagramReply` — 발송 이력 겸 멱등성 방어선. `commentId @unique`(평생 1회 강제), `status`(pending/sent).

## 엔드포인트

### 연동 OAuth (`InstagramConnectController`)

| Method | Path | 가드 | 설명 |
|--------|------|------|------|
| GET | `/v1/brand/instagram/connect?returnTo=` | `BrandGuard` | state/brandId/returnTo 쿠키 세팅 후 Meta 동의 화면으로 302 |
| GET | `/v1/brand/instagram/callback` | (없음) | Meta IdP 호출. state 검증 → code 교환 → 장기토큰 → getMe → 연동 저장 → `BRAND_FRONTEND_URL/instagram?ig_connected=1` 로 302. 실패 시 `?ig_error=<reason>`. CSRF Origin 체크 예외(main.ts). |

### 리소스 (`InstagramController`, 모두 `@UseGuards(BrandGuard)` + `requireBrandId`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/v1/brand/instagram/connection` | 연동 상태. `{connected:false}` 또는 `{connected:true, igUsername, connectedAt, needsReconnect}` |
| DELETE | `/v1/brand/instagram/connection` | 연동 해제 |
| GET | `/v1/brand/instagram/media?cursor=` | 포스팅 목록(최신순, 커서 페이지네이션) — 서버가 저장 토큰 복호화해 Graph API 프록시 |
| GET | `/v1/brand/instagram/media/unreplied-counts?mediaIds=a,b,c` | 그리드 뱃지용 — 여러 포스팅의 "답장 가능(미DM·7일 이내)" 댓글 수. `{counts:{[mediaId]:number}}`. mediaIds 최대 30개, 미디어당 최대 3페이지(150댓글) 조회·동시성 5. 개별 조회 실패한 미디어는 맵에서 생략(뱃지 미표시). 그리드 로드를 막지 않도록 프론트가 미디어 목록 수신 후 지연 호출 |
| GET | `/v1/brand/instagram/media/:mediaId/comments?cursor=` | 댓글 목록(50/page). 각 댓글에 `alreadyReplied`/`tooOld`/`replyable` 파생 플래그 부착 |
| GET | `/v1/brand/instagram/templates` | 템플릿 목록 |
| POST | `/v1/brand/instagram/templates` | 템플릿 생성 `{name, body}` |
| PATCH | `/v1/brand/instagram/templates/:id` | 템플릿 수정 |
| DELETE | `/v1/brand/instagram/templates/:id` | 템플릿 삭제 |
| POST | `/v1/brand/instagram/replies/bulk` | 일괄 발송 `{mediaId, templateId, commentIds[]}`. 응답 `{sent, skipped[], failed[]}` |

### 일괄 발송(`replies/bulk`) 처리 순서

1. 템플릿 로드 + 브랜드 slug 로드.
2. 요청 댓글의 username/timestamp 를 **실제 미디어 댓글에서 재해석**(never trust client, 최대 5페이지).
3. 각 댓글: 7일 초과면 skip(`too_old`), 미해석이면 skip(`not_found`).
4. `InstagramReply` 를 status=`pending` 으로 **선-예약**(commentId @unique → 동시요청/중복발송 원천 차단). 예약 실패 = `already_replied` skip.
5. 템플릿 렌더(`{link}`→`storefrontUrl(slug)`, `{username}`→댓글 작성자) 후 `sendPrivateReply` 호출.
6. 성공 → status=`sent`. 실패 → 예약 삭제(재시도 가능) 후 `failed[]` 에 기록.

## 환경변수

`META_APP_ID`, `META_APP_SECRET`, `META_BRAND_CALLBACK_URL`(기본 `http://localhost:4000/v1/brand/instagram/callback`), `META_GRAPH_VERSION`(기본 `v21.0`), `META_TOKEN_ENCRYPTION_KEY`(base64 32B). 브랜드관 링크 base 는 결제와 동일한 `FRONTEND_URL`.
