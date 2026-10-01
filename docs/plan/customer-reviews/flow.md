# customer-reviews — 흐름과 설계 논거

결정 요약은 [`README.md`](./README.md), 빌드 스펙은
[`implementation-plan.md`](./implementation-plan.md) 가 갖는다. 이 문서는 **"왜 이렇게 하나"** 만
다룬다.

## 1. 전체 흐름

```
[배송완료]                              [현장(onsite)]
 송장(Shipment) status=submitted          송장 0장
 + EFS 코드 33/47/74                      + Order.paidAt
 또는 DOMESTIC & brandConfirmedShippedAt
        │                                        │
        └──────────────┬─────────────────────────┘
                       ▼
        review-request.cron  (*/10, KST)   ← 훅이 아니라 **스캔**
                       │
            ① scanDue()  : 대상 - 이미 만든 ReviewRequest = 차집합
                           → createMany({ skipDuplicates: true })
                       │     @@unique([orderId, brandId]) 가 중복을 DB 에서 막는다
                       ▼
               ReviewRequest(status='queued')        ← 행이 곧 영수증
                       │
            ② drain()    : attemptCount++ (호출 前) → Resend
                           성공 sentAt / 실패 nextAttemptAt 백오프 / opt-out 'skipped'
                       ▼
   메일 (EMAIL_FROM · 주문 국가 locale 8종)
   CTA → https://klow.kr/review/<orderId>?t=<HMAC(orderId:brandId)>
                       │
                       ▼
   klow_web /review/[orderId]   (로그인 없음)
     GET /v1/reviews/form?t=    → 브랜드 · locale · 받은 제품 · 다른 제품 · 이미 쓴 제품
     POST /v1/reviews/upload    → 토큰 게이트 presign → R2 PUT (최대 5장)
     POST /v1/reviews/submit    → Review N건 (source='customer', orderId, sourceLocale)
                       │
                       ▼
   같은 $transaction 안에서 refreshProductAggregates → Product.rating/reviewCount
                       │
                       ▼
   klow_web PDP 즉시 노출 + `구매 확인` 배지
   klow_brand 리뷰 탭: `고객 작성` 배지 · 수정·삭제 버튼 없음(서버 403)
   klow_admin /reviews: 출처 배지 + 필터 · 삭제만 가능
```

## 2. 왜 cron 의 스캔이고 이벤트 훅이 아닌가 (G1)

`shipments.service.ts` 의 `refreshTracking()` 끝에 훅을 끼우는 길이 있었다. 안 쓴 이유:

1. 그 파일이 이미 **같은 종류의 사고를 주석으로 남겨 뒀다** — `isTerminalShipment()` 위에
   *"⚠️ 이 분기를 호출부마다 두지 말 것 — 국내용 완료 훅을 따로 만들었더니 **국내·EFS 송장이
   섞인 주문이 양쪽 어디에도 안 걸려** 영영 shipped 에 머물렀다"* 가 적혀 있다. 배송완료를
   읽는 지점을 또 늘리는 것이 바로 그 실수의 재발이다.
2. 종착으로 넘어가는 경로가 **셋**이다 — EFS 폴링(`refreshTracking`), dev 주입
   (`devSetTrackingStatus`), 국내 자체배송 발송처리. 훅은 세 곳에 달아야 하고 하나를 빠뜨리면
   그 유형의 주문만 조용히 메일을 못 받는다.
3. 스캔은 **배포 이전에 이미 배송완료된 주문도 소급해 잡는다.** 훅은 못 잡는다.
4. 발송은 어차피 큐가 필요하다(Resend 실패 재시도). 큐를 돌릴 cron 이 생기는데 거기서 스캔까지
   하면 새 코드가 **한 파일에 모인다.**

대가는 "배송완료 즉시"가 아니라 **최대 10분 + `REVIEW_REQUEST_DELAY_DAYS` 지연**이다.
어차피 받자마자 쓰라고 재촉할 메일이 아니므로 지연이 오히려 맞다.

## 3. 왜 주문 × 브랜드 단위인가

한 주문이 N개 브랜드 제품을 담으면 **EFS 송장도 N장**이고(한 브랜드 = 한 송장 = 한 박스),
박스가 따로 날아가므로 **배송완료 시점이 브랜드마다 다르다.** 주문 단위로 한 통만 보내면
먼저 도착한 브랜드의 리뷰가 늦은 브랜드를 기다린다.

브랜드 단위로 쪼개면 덤으로 화면이 단순해진다 — 링크를 열면 **그 브랜드 하나**의 제품만
보이므로 "브랜드 먼저 고르기" 단계가 없다. 요구사항의 *"해당 브랜드에서 자기가 받은 제품을
고르게"* 가 그대로 성립한다.

## 4. 왜 `ReviewRequest` 테이블인가 (플래그 컬럼이 아니라)

`Order.reviewRequestSentAt` 한 칼럼으로도 "한 번만"은 된다. 테이블로 올린 이유:

- **브랜드 축이 필요하다.** 주문×브랜드 단위라 칼럼 하나로는 담을 수 없다.
- **행이 곧 영수증이다.** `BrandCrmEmail` 의 주석이 그 이유를 이미 적었다 —
  *"⚠️ 행을 먼저 적재하고 나중에 보낸다 — fire-and-forget 으로 보내면 실패가 흔적 없이
  사라진다(2026-08-17 결제 확정이 정확히 그 병이었다)."*
- **재시도가 필요하다.** `attemptCount` / `nextAttemptAt` / `errorMsg` 없이는 Resend 일시
  장애가 그 고객의 리뷰 요청을 영구히 날린다.
- **`submittedAt` 이 같은 행에 붙는다.** 링크 재방문 시 "이미 쓰셨습니다"를 보여줄 근거가
  리뷰 테이블 조회 없이 한 행에서 나온다.

⚠️ `BrandCrmEmail` 과 한 가지가 다르다 — **거기엔 유니크가 없고 여기엔 있다.** CRM 은 같은
사람에게 여러 번 보내는 게 정상 기능이지만, 이 메일은 *"중복으로 보내지면 안 된다"* 가
요건이다. 행동(claim-before-send)만으로 막으면 cron 주기가 겹칠 때 두 통이 나간다.
DB 제약으로 올리면 두 번째 insert 가 P2002 로 깨진다 — **코드가 틀려도 메일은 안 겹친다.**

## 5. 왜 전용 토큰 시크릿인가 (G4)

주문확인 메일이 이미 `/track/<orderId>?t=<signGuestOrderToken(orderId)>` 를 싣고 있어 그걸
그대로 쓰면 코드가 0줄이다. 안 쓴 이유: 그 토큰 값은 **게스트 결제 쿠키(`klow_order`)의 값과
같은 문자열**이고, 그 쿠키는 `payment/prepare` · `report-failure` 의 소유권 게이트다.

- 리뷰 링크는 **받은편지함에 영구히 남는다**(수명 무한).
- 결제 쿠키는 **1시간**짜리 결제 1사이클 자격이다.

수명과 권한이 전혀 다른 두 자격을 같은 서명으로 묶지 않는다. 실제 피해 범위가 지금은 좁아도
(이미 결제된 주문엔 prepare 가 안 먹는다) 그건 다른 코드의 우연한 성질이고, 경계는 우연에
기대지 않는다.

모양은 `brand-crm/unsubscribe-token.ts` 를 그대로 따른다 — **만료 없음**(만료된 링크를 누른
수신자에게 "다시 신청하세요"라고 할 방법이 없다. 그건 곧 스팸 신고다) · `timingSafeEqual` +
길이 선검사 · 위조·손상은 **전부 `null`** 로 어느 단계에서 틀렸는지 알리지 않는다(열거 방지).
payload 에 `brandId` 까지 넣어 **토큰 하나가 (주문, 브랜드) 한 쌍에만 유효**하게 한다.

## 6. 왜 `Review.source` 컬럼을 새로 만드는가

[`decisions/products.md 2026-08-18`](../../decisions/products.md#2026-08-18) 은 *"브랜드가 자기
제품의 **모든** 리뷰를 수정·삭제할 수 있고, 그래서 `Review` 에 status·출처 컬럼이 없고
스키마 변경이 0건이다"* 를 명시적 설계로 적었다. 고객 리뷰가 같은 테이블에 들어오면 그
전제가 깨진다 — **브랜드가 불리한 실고객 리뷰를 조용히 지울 수 있다.**

그래서 컬럼 하나를 더해 그 경로만 닫는다. 대안을 둘 다 버렸다:

- *컬럼 없이 그냥 쌓기* — 브랜드가 실고객 리뷰를 지울 수 있고, 어드민·브랜드가 쓴 것과
  구분할 수단이 영구히 없어진다(사후 복구 불가).
- *별 테이블* — PDP 조회·번역 캐시·`refreshProductAggregates` 가 전부 두 벌이 된다.

`@default(proxy)` 라서 **백필이 0건**이고 기존 행은 자동으로 `proxy` 다.

## 7. 왜 번역 소스를 컬럼으로 빼는가 (G5)

`review-translation.service.ts` 는 `translateBatch(texts, locale, 'ko')` — **원문이 한국어라고
못박혀 있다.** 그게 맞았던 이유는 지금까지 리뷰를 한국인(어드민·브랜드)이 썼기 때문이다.
고객은 영어·일본어로 쓴다. 영어 문장에 ko→en 번역을 걸면 결과가 망가진다.

`Review.sourceLocale String?`(null = 한국어 = 기존 행) 을 더하고,
`sourceLocale === target` 이면 번역을 **호출하지 않고 원문**(캐시 행도 안 만든다),
아니면 `translateBatch(…, target, sourceLocale ?? 'ko')`. `translateBatch` 의 3번째 인자가
이미 `string | null`(null = 자동감지)이라 시그니처는 그대로다.

## 8. 왜 메일은 트랜잭션 도메인인가

`brand-crm/email-sender.ts` 가 발신 도메인을 일부러 갈라 뒀다 — *"브랜드 마케팅 메일을
`EMAIL_FROM` 으로 보내면 한 브랜드의 스팸 신고가 **OTP·주문확인 메일의 도달률까지**
끌어내린다"*. 리뷰 요청은 **브랜드가 쓰는 임의 본문이 아니라 KLOW 가 주문 생애주기에 보내는
고정 템플릿**이라 `sendOrderConfirmation` 과 같은 축이다 → `EmailService` / `EMAIL_FROM`.

⚠️ 그래도 **`BrandCrmOptOut`(brandId, email) 은 존중한다.** 그 브랜드의 수신거부를 눌러 둔
사람에게 그 브랜드 제품 리뷰를 권하는 것은 거부 의사를 무시하는 것이다. 걸리면 보내지 않고
`status='skipped'` 로 적어 "왜 안 갔는지"를 남긴다. 별도 수신거부 테이블은 만들지 않는다.

## 9. 왜 메일 locale 을 서버 미러로 푸는가

서버에는 **국가 → locale 표가 없다.** klow_web `src/lib/locale.ts` 의 `COUNTRY_TO_LOCALE` 와
klow_brand `src/lib/i18n.ts` 에만 있다(이미 2중 미러). `Order` 에도 `User` 에도 locale 칼럼이
없고, 유일한 단서는 `Order.countryCode` 다.

- `ShippingCountry.locale` 칼럼을 새로 만들면 드리프트가 사라지지만 마이그레이션 + 어드민 UI +
  백필 + 운영팀 유지보수가 붙는다.
- 서버에 세 번째 미러(`common/country-locale.ts`)를 두면 어긋날 수 있지만 **손해가
  "그 손님이 영어 메일을 받는다"로 한정**된다(en 폴백).

손해가 작고 비용 차이가 커서 미러를 고른다. 어긋남을 알아채도록 **키 집합을 잠그는 spec** 을
함께 둔다. 비용이 커지면(예: 메일이 여러 종류로 늘면) 그때 칼럼으로 올린다.

## 10. 왜 cron 을 기본 off 로 두는가 (G6)

배포 순서가 `klow_server → klow_admin → klow_brand → klow_web` 인데, **메일을 보내는 코드가
klow_server 에 있고 메일이 가리키는 페이지는 klow_web 에 있다.** 기본 on 이면 서버가 나가는
순간 손님에게 404 로 가는 링크가 발송된다 — 되돌릴 수 없다.

그래서 `REVIEW_REQUEST_CRON_ENABLED` 는 **`'true'` 일 때만 동작**한다. ⚠️ 다른 cron 의
`!== 'false'`(미설정이면 on) 관례와 **의도적으로 반대**이고, 그 이유를 cron 파일 주석에 적는다.

켜는 순간 과거 배송완료분이 한꺼번에 대상이 되므로 `REVIEW_REQUEST_LOOKBACK_DAYS`(기본 14)로
창을 막고, 첫 실행은 건수를 로그로 먼저 본다.

## 11. 받은 제품을 어떻게 아는가 (G7)

| 주문 유형 | `OrderItem.productId` | 실제 제품명 |
|---|---|---|
| 일반 · 현장 | 실 `Product.id` | `Product` 그대로 |
| 시딩 `selectionMode=customer` | **null** | `SeedingClaim.selectedSkus` (자유 텍스트 라벨) |
| 시딩 `selectionMode=brand` | **null** | `SeedingLink.itemNames` (자유 텍스트, 2026-08-18 이전 발급은 `[]`) |

시딩은 `OrderItem.productName` 이 **제품명이 아니라 EFS 통관 영문 품명**이고
`productImage` 는 항상 빈 문자열이다(실측 446/446). 그래서:

- 이름 파생은 **반드시** `seeding/seeding-display-name.ts` 의
  `SEEDING_ITEM_NAMES_SELECT` + `seedingItemNames(claim)` 를 쓴다.
  ⚠️ `selectedSkus` / `itemNames` 를 직접 고르면
  [`decisions/shipping-seeding.md 2026-09-14`](../../decisions/shipping-seeding.md#2026-09-14)
  가 레포 전역 금지로 박은 패턴이다(바코드 라벨 제품명 누락 사고가 정확히 그것이었다).
- 라벨 → `Product` 는 `seeding-product-detail.ts` `resolveProductsByLabel` 의
  best-effort `(brandId, name)` 조인이다. 못 찾으면 그냥 `받으신 제품`에 안 들어간다 —
  **아래 "다른 제품" 목록에서 고르면 되므로 기능이 깨지지 않는다.** 이게 "자유 선택"으로
  설계한 두 번째 이유다.
- ⚠️ 시딩 발급은 카탈로그를 읽을 때 **일부러 판매 게이트를 걸지 않는다**(샘플은 승인 전이거나
  판매가가 없는 경우가 흔하다 — `seeding.service.ts:205`). 그래서 받은 제품이 게이트 미통과일
  수 있다. **그건 양쪽 목록에서 다 뺀다** — 리뷰를 받아도 그 제품 상세가 손님에게 노출되지
  않아 리뷰가 아무 데도 안 보인다.
