# contact — 랜딩 상담 문의

- **모듈 경로**: `src/modules/contact/`
- **목적**: klow_brand 랜딩(`/`) 최종 CTA "상담 문의" 모달이 보내는 공개 폼을 받아 **운영팀 문의함으로 메일만 보낸다**.
- **데이터 모델**: **없다.** Prisma 테이블·마이그레이션 없이 Resend 발송만 한다 — 접수 이력은 문의함(메일)이 정본이다.
- **관련 파일**: `contact.service.ts`, `public-contact.controller.ts`, `contact.module.ts`, 검증 스키마 `common/validation/contact.ts`, 메일 템플릿 `modules/web-auth/email.service.ts` (`sendBrandContactInquiry` / `buildContactInquiryHtml`)

## public-contact.controller.ts (`@Controller('v1/contact-inquiries')`)

| Method | Path                     | Guard  | Throttle            | 기능                       |
|--------|--------------------------|--------|---------------------|----------------------------|
| POST   | `/v1/contact-inquiries`  | public | 5회 / 분 / IP        | 상담 문의 접수 → 메일 발송 |

- Body — `ContactInquiryInput`: `{ brandName, contact, email, message? }`. 길이 제한 `brandName` 100 / `contact` 50 / `email` 200 / `message` 2000, 전부 `.trim()` 후 검사.
  - `contact` 는 전화·카톡ID 등 **자유 텍스트**로 형식을 강제하지 않는다(문의 문턱을 낮추는 게 우선).
  - `email` 은 회신 주소 — 메일의 `replyTo` 에 실려 문의함에서 "회신" 한 번으로 답장이 간다.
  - **`message` 만 선택**(`.default('')`) — 연락처만 남기고 "연락 주세요" 로 끝내는 문의를 막지 않는다. 미전송·빈 문자열·공백 모두 `''` 로 들어오고, 메일 템플릿이 그 경우 "(작성된 내용 없음 …)" 을 대신 렌더한다. 나머지 3개는 필수라 빠지면 400.
- 응답 `200 { ok: true }`.
- 완전 공개 쓰기 경로라 `@Throttle(THROTTLE_TIGHT)` 가 붙어 있다. **떼면 메일 폭주 통로가 된다**(전역 기본은 60회/분).
- 메일 발송 실패는 **삼키지 않고 그대로 500** 으로 올린다 — 저장을 안 하므로 조용히 성공을 반환하면 문의가 소리 없이 유실된다. 프론트는 토스트로 재시도를 유도한다.

## 수신함 / 환경변수

| env                    | 기본값          | 비고                                        |
|------------------------|-----------------|---------------------------------------------|
| `CONTACT_INBOX_EMAIL`  | `team@klow.kr`  | 문의 수신 주소. 선택값이라 `main.ts` fail-closed 가드에는 없다. |
| `RESEND_API_KEY`       | (기존)          | 비면 발송 대신 `[DEV email] contact inquiry from …` 콘솔 로깅 |
| `EMAIL_FROM`           | (기존)          | 발신 주소. 문의 메일도 같은 발신 도메인을 쓴다 |

## 메일 템플릿

`buildContactInquiryHtml()` — 기존 어드민 초대/주문 확인 메일과 동일한 인라인 스타일 카드(`max-width:480px`, `#FAFAFA`). 필드 3개는 라벨/값 테이블, 문의 내용은 별도 블록.

⚠️ **네 필드 전부 미인증 공개 입력이다.** 모든 값이 모듈 로컬 `escapeHtml()` 을 거치고, 줄바꿈 `\n → <br>` 치환은 **이스케이프 후**에 한다. 새 필드를 추가할 때 이 순서를 지키지 않으면 메일 본문에 HTML 이 그대로 주입된다.

`message` 가 비면 빈 블록 대신 회색 안내문("(작성된 내용 없음 — 연락처로 먼저 연락해 주세요)")을 렌더한다.

## 프론트 연결 (klow_brand)

- 모달: `src/components/ContactModal.tsx` (공용 `Modal` 셸 `size="lg"` + `Field` + `.form-input`)
- 진입 두 경로:
  1. 랜딩 하단 CTA — `_landing_new/DarkSheet.tsx` 의 `data-contact-cta` 앵커 → `LandingNew.tsx` 위임 클릭 핸들러
  2. **딥링크 `?contact=1`** — 블로그·SNS 글에 `https://brand.klow.kr/?contact=1` 을 붙이면 랜딩이 뜨면서 모달이 자동으로 열린다 (`?login=1` / `?signup=guide` 와 동일 규약)
- ⚠️ 로그인된 브랜드는 랜딩에서 `/studio` 로 자동 리다이렉트되는데, `?contact=1` 일 때는 **그 리다이렉트를 건너뛴다** — 안 그러면 블로그 링크를 눌러도 모달을 보기 전에 튕긴다.
- API 클라이언트: `klow_brand/src/lib/api.ts` 의 `api.contact.create(...)`
