# 바이어 공간 — 디자인 전면 일치(목업)와 실제 구현 목록

2026-10-05 사용자 결정: **klow.kr 바이어 공간은 디자인 `KLOWBUYER/` 와 모든 게 같아야 한다 — 동작하지 않는 목업이어도.**
README 의 결정 4("행동 버튼은 문의 폼 하나")·"스코프 밖" 을 뒤집었다. 화면은 지금 전부 있고, **동작은 아래 표대로 나중에** 붙인다
(진행표 `§7` 24·25행). 이 문서는 "지금 무엇이 가짜이고, 진짜로 만들려면 무엇이 필요한가" 의 정본이다.

## 원칙

- **화면·문구·마크업·클래스는 디자인 그대로**(`components/buyer-space/Kb*` 가 디자인 컴포넌트 1:1). 바뀐 것은 세 가지뿐 —
  ① mock 카탈로그 조회 → 실데이터 **스냅샷**(클라에 카탈로그가 없어 샘플박스는 담을 때 카드 값을 저장한다)
  ② 디자인 경로 → **`/shop/*`**(`/signup`·`/checkout` 이 소비자 라우트와 겹친다 — `shop` 은 이미 예약어·KLOW_ONLY)
  ③ localStorage 키 `klow.*` → **`kb.*`**(같은 도메인의 소비자 앱과 분리)
- ⚠️ **계정(로그인·가입·비번 찾기·서류·검수 배지)은 2026-10-08 에 [`../buyer-auth/`](../buyer-auth/README.md) 트랙으로 떼었다** — 아래 "행" 칸의 `buyer-auth` 가 그것이다.
- 상태는 전부 **이 브라우저 localStorage** 에만 산다(`kb.samples` · `kb.buyer` · `kb.orders` · `kb.checkout` · `kb.ask.*`). 서버 저장 없음.
- **실제로 운영팀에 닿는 것은 기존 문의 API 하나**(`POST /v1/buyer/inquiries` → `BuyerInquiry` + 운영팀 메일)다.
  Request 드로어 외에 **목업 결제 완료**와 **채팅 이메일 이관**이 같은 API 로 요청을 보낸다 — "our Seoul team will contact you"
  안내를 참으로 만들기 위해서다. ⚠️ 카드 정보는 어떤 형태로도 보내지 않는다(마스킹 문자열 포함).
- 가짜 데이터를 진짜처럼 보이게 하지 않는다 — **리뷰는 빈 상태**, 데모 주문·데모 회사("Lumen Beauty Co.")를 심지 않는다,
  결제·완료 화면은 "청구했다" 대신 "아직 청구 안 됨 — 메일로 확인" 문구.
- 목업 페이지는 전부 `robots: noindex` · sitemap 미포함(검색 노출은 홈·브랜드·제품만 — README 결정 10).

## 화면별 — 지금 / 실제 구현에 필요한 것

| 화면 (경로 · 컴포넌트) | 지금(목업) | 실제 구현에 필요한 것 | 행 |
|---|---|---|---|
| 헤더 Sign in · 아바타 (`KbHeader`) | `kb.buyer` 가 있으면 이니셜 아바타 | 서버 바이어 세션(쿠키) | buyer-auth 27~29 |
| 로그인 `/shop/signin` (`KbSignup`) | 아무 비밀번호나 통과. 이 브라우저에서 가입한 이메일이면 그 프로필, 아니면 이메일만 가진 빈 프로필 | `BuyerUser` + 비밀번호(argon2) 또는 이메일 OTP, 세션 테이블, 비밀번호 찾기 | buyer-auth 27~29 |
| 가입 3단계 `/shop/signup` | 이메일 인증 코드는 아무 6자리(디자인 문구 "For this mock-up, any 6 digits work" 그대로). 업로드는 파일명만 | 이메일 OTP 발송(Resend), 사업자등록증·매장사진 R2 업로드, 어드민 검수("Verified buyer" 배지 부여), 관심 브랜드 저장 | buyer-auth 27~29 |
| 계정 `/shop/account`(+`?tab=`) · 요청 상세 `/shop/account/requests/[id]` (`KbAccount`·`KbRequestDetail`) | 이 브라우저 프로필·목업 주문만. 상태는 항상 `requested`, 영수증·Korea Post 추적 버튼은 동작 없음. "Message the Seoul team" 만 Request 드로어 | 바이어 주문 테이블·상태 전이(브랜드 재고 확인 → 포장 → 발송 → 배송완료), 송장·추적(EFS 연동 재사용 검토), 알림 설정 저장, 탈퇴 — **프로필·상태 배지·로그아웃은 buyer-auth 28**, 나머지 24 | 24 |
| 샘플박스 바·드로어 (`KbSampleBox`) · 카드 "Sample 1 unit" · 브랜드 "Sample the range" · PDP "Add N samples" | `kb.samples` 에 카드 스냅샷 + **수량(`qty`)**. 가격 = **샘플 가격**(구간표 1행 단가, 서버 카드 `sampleUsdCents`). **샘플 구간 = 1 ~ (MOQ−1)개**(MOQ 10 이면 9개까지 샘플가) — PDP 수량 계산기로 고르고, 카드 호버·브랜드 일괄은 1개. 소계 = Σ 단가×수량, 무료배송 기준은 여전히 SKU 수. 카드 가격 표시 = **샘플가 + MSRP**(로그인 무관 — 2026-10-08) | 서버 장바구니(로그인 후 승격), 재고·품절 | 24 |
| PDP 구간가 로그인 게이트 (`KbPricing`, 2026-10-08) | 로그인 전(목업 `kb.buyer` 없음)엔 샘플 행만 가격 공개, MOQ 이상 행은 **자리표시 `$00.00` 블러**(KLOWBUYER `login` 브랜치 방식). 그 행 클릭 · 수량을 MOQ 이상으로 올리면 `/shop/signin?next=<상세>` | ⚠️ **화면 가림뿐이다** — `GET /v1/buyer/products/:id` 가 전 구간을 공개로 내려 RSC 페이로드에 실린다. 서버 바이어 인증이 생기면 **서버가 비로그인 응답에서 MOQ 이상 구간을 잘라야** 진짜로 가려진다 — 게이트를 실세션으로 잇는 것은 buyer-auth 28, 서버측 은닉은 그 트랙도 스코프 밖(별도 결정) | buyer-auth 28 |
| 체크아웃 `/shop/checkout` → 결제 `/shop/checkout/pay` → 완료 `/shop/checkout/complete` (`KbCheckout`·`KbPayment`·`KbComplete`) | Eximbay 결제창 **목업**(아무 16자리). "Payments aren't live yet" 안내. Pay 시 목업 주문 저장 + **샘플 목록·합계·배송국가·바이어를 문의 API 로 운영팀에 전송** | Eximbay 실결제(USD — 소비자 결제 흐름 `payment` 모듈 재사용 검토: prepare/verify/webhook), 동의 4종 저장, 배송지 전체 주소, 5 SKU 무료배송·$18 정책의 정본, 브랜드별 출고(3PL·EFS) | 24 |
| Concierge `/shop/match` (`KbConcierge`) | 질문 5개 디자인 그대로. 점수는 디자인 규칙을 **가진 필드로만** 계산(`lib/buyer-space-mock#matchBrands`) — 라인은 `icons`/`gems` 만 tier 로, 판매채널은 가중치 0 | `BuyerBrand` 에 **취급 라인(`lines`)·적합 채널(`channels`)** 컬럼 + 어드민 입력, (선택) 답변 저장해 운영팀 리드로 | 25 |
| 제품 채팅 (`KbAskProduct`) | 즉답 3개는 실데이터(브랜드 도시·리드타임·서류 지역·인증·구간가). 이관 카드에 **이메일**을 남기면 그 질문을 문의 API 로 전송, WhatsApp 만 남기면 이 브라우저에만(서버 문의가 이메일 필수) | 실시간 채팅 또는 브랜드 담당자 이관 큐, WhatsApp 채널, 스레드 서버 저장, `BuyerInquiry` 에 연락 채널 컬럼 | 25 |
| 리뷰 (PDP `#reviews`, `KbReviews`) | **그 제품에 이미 등록된 리뷰**(브랜드 등록 + 고객 작성, `/v1/reviews?productId=`)를 영어 번역으로 노출(2026-10-06). 리뷰 개수는 표시하지 않는다(평균 별점만). 바이어 주문 리뷰가 아니라서 "verified buyers" 문구는 뺐다. 0건이면 빈 문구 | 바이어 주문 기반 리뷰 수집(검증된 주문만), 사진 업로드, 번역 메뉴(디자인 Translate — 7개 언어) | 25 |

## 디자인과 의도적으로 다른 곳 (전부)

- **밴드 필터**(선반 안 "공급률·소매가" 버튼) — 선반이 어드민 수동 큐레이션이라 규칙이 없다(README 결정 3).
- `.page` 좌우 여백 — 디자인 CSS 는 `.page { padding: … 0 … }` 가 `.wrap` 의 좌우 여백을 0 으로 덮어 목업 페이지 본문이 화면 끝에 붙는다. `padding-block` 으로 세로만 덮었다.
- 결제·완료·요청 상세의 "charged / paid" 문구 → 아직 청구 안 됨(위 원칙).
- 빈 데이터 칸 숨김(브랜드 사실 행·태그라인·claims·"on market since") — 실데이터가 비어 있을 수 있다(22행부터의 규칙).
- **로고월은 이미지 로고를 쓰지 않고 항상 브랜드 이름 텍스트**다(2026-10-05 사용자 결정) — 디자인은 로고 이미지가 있으면 그림, 선택 칸에선 `invert(1)` 로 반전했는데, 브랜드 로고 형태(컬러·사진·흰 배경)가 제각각이라 칸이 들쭉날쭉하고 선택 칸에서 네거티브로 보였다. 어드민 브랜드 상세의 로고 교체는 이제 **브랜드 페이지 링크 공유 미리보기(OG 이미지)에만** 쓰인다.
- 버튼 화살표 글리프 길이 — 디자인은 Google Fonts 의 Geist Mono, 우리는 `geist` 패키지(Next 14.2 의 `next/font/google` 에 Geist 가 없다). 글리프 모양만 다르다.
