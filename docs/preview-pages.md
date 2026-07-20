# klow_web 디자인 프리뷰 화면

실제 데이터(주문·송장·PG 왕복·세션)를 만들지 않고, **결제 완료·배송추적·시딩 화면의 모든 케이스를
mock 으로 렌더**하는 개발/디자인 전용 페이지 모음이다. 백엔드 없이 접속만 하면 각 상태를 볼 수 있어
디자인/QA 시 유용하다.

## 공통 원칙

- **프리뷰는 순수 뷰만 렌더한다.** 카트 정리, PG verify, sessionStorage 플래그 clear 같은 부수효과는
  호출하지 않는다 → 안전하게 아무 상태에서나 열어볼 수 있다.
- **실물과 같은 컴포넌트를 그린다.** 화면(presentational) 부분을 공유 컴포넌트로 추출해 실제 페이지와
  프리뷰가 같은 것을 렌더한다. 그래서 **디자인을 공유 컴포넌트에서 고치면 실물·프리뷰에 동시 반영**된다.
- **프리뷰 컨트롤 바/토큰은 프리뷰 전용**이며 실제 화면에는 존재하지 않는다.
- 모두 klow_web(포트 3001) 라우트다. 운영 배포본에도 존재하지만 실제 데이터가 없어 mock 만 보인다.

---

## 1. 결제 완료 프리뷰 — `/checkout/preview`

결제 케이스별 **완료·실패 화면**을 상단 스위처로 전환하며 본다.

| 시나리오 | 실제 경로 | 분기 근거(실물) |
|---|---|---|
| 일반결제 완료 (회원) | `/checkout/success` | `useSession().authed` |
| 일반결제 완료 (비회원) | `/checkout/success` | guest |
| 현장결제 완료 (부스) | `/checkout/success` onsite 분기 | `isOnsiteCheckout()` sessionStorage |
| 결제 실패 (회원) | `/checkout/failed` | 세션 회원 |
| 결제 실패 (비회원) | `/checkout/failed` | `isGuestCheckout()` |

- **공유 컴포넌트:** `klow_web/src/app/checkout/_components/SuccessView.tsx`(일반/현장 분기),
  `FailedView.tsx`. props 만으로 렌더하는 순수 뷰.
- **실물 페이지는 얇은 래퍼:** `checkout/success/page.tsx`·`checkout/failed/page.tsx` 가
  `useSearchParams`·`useSession`·sessionStorage 를 읽어 부수효과(현장 모드 해제, guest 플래그 정리)를
  처리한 뒤 계산값을 뷰에 넘긴다.
- 스위처 바 하단에 **시딩 프리뷰(아래 3번)로 가는 링크 그룹**이 함께 있다(시딩은 별도 라우트).
- i18n 은 `useT('checkout')`(`src/i18n/locales/en/checkout.ts` 의 `success.*`/`onsite.*`/`failed.*`).

---

## 2. 배송추적 프리뷰 — `/track/preview`

실제 주문/송장 없이 배송추적 화면의 모든 상태를 mock 으로 렌더한다. 상단 시나리오 스위처로 전환.

| 시나리오 | 라벨 | 내용 |
|---|---|---|
| `all` | All statuses | 5개 브랜드 그룹(각 상태) 한 화면에 |
| `preparing` | Preparing | 송장 발급 전 |
| `submitted` | Ready to ship | 송장 발급됨(발송 전) |
| `in_transit` | In transit | 통관/운송 중 (이벤트 타임라인) |
| `delivered` | Delivered | 배송 완료 |
| `cancelled` | Cancelled | 송장 발급 후 취소 |
| `loading` | Loading | 로딩 스켈레톤 |
| `error` | Not found | 조회 실패/미존재 |

- **공유 컴포넌트:** `klow_web/src/app/track/_components/TrackingView.tsx`. 실제 페이지
  `track/[id]/page.tsx` 와 이 프리뷰가 같은 컴포넌트를 렌더한다.
- 이벤트명은 실제 EFS Tracking Status Table 의 status name 만 사용(`tracking-status.ts`).
  서버는 오름차순(과거→최신) 저장, `TrackingView` 가 reverse 로 최신을 위로 올린다.
- mock 주문번호 `KLW-2026-0620-AB12CD`, `paymentStatus: 'paid'`.

---

## 3. 시딩 프리뷰 — `/seed/{preview토큰}`

무가/유가 시딩(크리에이터 발송 신청) 화면을 백엔드 없이 본다. 운영 토큰은 영숫자라
`preview*` 와 절대 겹치지 않는다. 프리뷰 토큰은 `enabled: !preview` 로 API 를 타지 않고 mock 을 쓴다.

시딩은 **결제주체(paymentBy) × 선택주체(selectionMode)** 2×2 매트릭스다.

### 신청 폼 (토큰별)

| 경로 | 케이스 |
|---|---|
| `/seed/preview` | Case1 · 브랜드 결제 + 브랜드 지정 (주소만, 결제 없음) |
| `/seed/preview-cn` | Case1 · 중국(CN) — 신분증 입력란 노출 |
| `/seed/preview-select` | Case2 · 브랜드 결제 + 고객 선택 (제품 선택, 결제 없음) |
| `/seed/preview-pay` | Case4 · 고객 결제 + 브랜드 지정 (선택 없음, 결제) |
| `/seed/preview-paysel` | Case3 · 고객 결제 + 고객 선택 (제품 선택 + 결제) |

### 신청 결과 화면 (`?state=` 쿼리)

폼은 실제 제출을 해야만 결과 화면으로 넘어가므로, 프리뷰 토큰에 한해 쿼리로 결과 상태를 강제한다.
(실제 운영 토큰에는 `state` 쿼리가 무시된다 — `preview` 일 때만 동작.)

| 경로 | 화면 |
|---|---|
| `/seed/preview?state=success` | **신청 완료** — 바이어가 주소 입력을 완료했을 때 나오는 성공 카드(`seed.success`) |
| `/seed/preview?state=claimed` | **이미 신청됨** — 링크가 이미 사용된 상태(`seed.claimed`) |

- **위치:** `klow_web/src/app/seed/[token]/page.tsx`
  (`PREVIEW_TOKENS`, `previewLink()`, `previewState`).
- 시딩은 화면 로직이 한 페이지에 응축돼 있어 별도 컴포넌트로 추출하지 않고 페이지 자체에 프리뷰 훅을 둔다.
- 결제(고객 결제 케이스)는 프리뷰에서 Eximbay 를 실제로 호출하지 않는다.

---

## 유지보수 메모

- checkout/tracking 은 **공유 뷰 컴포넌트**를 고치면 실물·프리뷰가 함께 바뀐다. 시딩은 페이지 자체를
  수정한다.
- 새 결제/배송/시딩 상태가 생기면 해당 프리뷰 스위처(또는 `state` 값)에 케이스를 추가한다.
- klow_web 은 독립 저장소다. 관련 코드 변경/커밋은 `cd klow_web` 후 진행한다.
