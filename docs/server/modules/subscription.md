# subscription — 브랜드 멤버십 정기구독

- **모듈 경로**: `src/modules/subscription/`
- **주 클라이언트**: `klow_brand`(자체 가입 브랜드의 결제·해지·카드관리, `/v1/brand/subscription/*`) + `klow_admin`(구독 관찰·강제해지·환불·정책위반 reject·제품 단위 차단, `/admin/brand-subscriptions/*`).
- **데이터 모델**: `BrandSubscription`(brand 1:1, `status`/`planCode`/`billingInterval`/`currentPeriodStart`/`currentPeriodEnd`/`cancelAtPeriodEnd`/`canceledAt`/`billingKeyId`), `BillingKey`(`provider='nicepay'`, `pgBillingKey`=빌키 bid, `cardCompany`/`cardLast4`, `deletedAt` soft-delete, `isDefault`), `SubscriptionInvoice`(`status`/`amountKrw`/`pgProvider`/`pgTid`/`periodStart`/`periodEnd`/`paidAt`/`attemptCount`/`lastAttemptAt`/`failReason`). 게이트 플래그는 `Brand.pgCustomerKey`(null 이면 결제 준비 미완 + cron 청구 제외).
- **결제 방식 (NicePay 포스타트 빌링, 결제창 없음)**: 브랜드가 `CardEntryForm` 으로 입력한 카드정보(`cardNo`/`expYear`/`expMonth`/`idNo`/`cardPw`)를 서버로 보내면, 어댑터가 secretKey 로 AES-256-CBC(encMode `A2`) 암호화한 `encData` 로 `POST /v1/subscribe/regist`(빌키발급) → `POST /v1/subscribe/{bid}/payments`(자동결제) 를 호출한다. **카드 원문이 서버를 경유하지만(PCI) DB 에 저장하거나 로깅하지 않는다** — 저장하는 건 빌키(bid)/거래번호(tid)/카드사명/끝4자리뿐.
- **플랜 코드 (`planCode`)**:
  - `brand_standard` — 정기 유료 구독(기본값, env `SUBSCRIPTION_PLAN_CODE`). `billingKeyId` 있음 → cron 이 매 사이클 자동 청구.
  - `brand_comp` — 무료 구독권(어드민 수동 부여). `billingKeyId=null` → cron 청구 **제외**, 만료 시 cron 이 자동 `canceled`. 카드 변경 불가(유료 재가입으로 유도). invoice 안 남김.
  - `brand_cash` — 현금/계좌이체 수동 발급. `billingKeyId=null` → cron 청구 **제외**(만료 시 자동 `canceled`)이지만 받은 금액을 `pgProvider='cash'`/`pgTid=null` paid invoice 로 기록. 환불은 오프라인, 서버는 `refunded` 표시만(부분환불·PG 취소는 카드 전용).
- **금액·주기**: 신규 가입은 `billingInterval` = `semiannual` / `annual` 만 선택 가능(validation 차단). 6개월 기본 ₩330,000(env `SUBSCRIPTION_SEMIANNUAL_PRICE_KRW`, 월 환산 50,000), 연 기본 ₩528,000(env `SUBSCRIPTION_ANNUAL_PRICE_KRW`, 월 환산 40,000) — 둘 다 VAT 포함. env 미설정/0/비정상이면 경고 로그 + 기본값 폴백. 다음 결제일 = `semiannual`→+6개월 / `annual`→+12개월. **할부**: 구독 첫 결제만 `cardQuota`(0=일시불 / 3 / 6 / 12개월) 선택 가능(validation enum), 무이자는 카드사 이벤트 의존(`useShopInterest=false` 고정 — 상점분담 무이자 미지원). 정기 청구·카드변경 재개는 항상 일시불(`cardQuota=0`). 승인 응답 `card.cardQuota` 를 `SubscriptionInvoice.cardQuota`(Int?, null/0=일시불) 에 저장 → 브랜드 청구서 패널·어드민 구독 상세 표에 "N개월 할부/일시불" 로 노출. (마이그레이션 `add_invoice_card_quota`) **무이자 판정**: 할부(quota>0) 결제 직후 `GET /v1/card/interest-free`(빌링 `useAuth=false`) 로 카드사×개월×금액 무이자 이벤트표(기본+상점 merge 정본)를 받아 승인된 `card.cardcode`/개월/금액과 대조 → `SubscriptionInvoice.isInterestFree`(Boolean?, true=무이자/false=유이자·일시불/null=조회실패) 저장. 어댑터 `resolveInterestFree()`. 무이자면 UI 에 "무이자" 표기. (마이그레이션 `add_invoice_interest_free`) **결제 전 안내**: `GET /v1/brand/subscription/interest-free?interval=semiannual|annual`(BrandGuard) → 선택 주기 금액에 적용되는 카드사별 무이자 할부개월(`{amountKrw, cards:[{cardCode,cardName,months[]}]}`). 어댑터 `listInterestFree(amountKrw?)`(파싱 공유 `fetchInterestFreeTable()`). klow_brand 카드 입력 폼(`CardEntryForm`, `installment`)에서 조회해 "카드사별 무이자 할부 안내" 접이식 섹션으로 노출 → 브랜드가 자기 카드사 무이자 개월을 보고 할부 선택.
  - **legacy `monthly`(₩49,500 / +1개월, env `SUBSCRIPTION_MONTHLY_PRICE_KRW`)**: production 의 기존 월결제 구독 전용. 신규는 못 고르지만 저장값은 `normalizeInterval` 이 **그대로 보존**해 매월 계속 청구된다(정규화로 6개월으로 바뀌지 않음). interval 을 사용자 입력으로 덮어쓰는 곳은 `start`(신규/재가입)뿐 — `changeCard`/`resume`/cron `chargeOne` 은 저장 interval 을 보존한다.
- **start 흐름 (4 stage, `POST /start`)**: ① 사전조건(`assertEligibleForStart` — pending+구독없음(신규) 또는 (approved|pending)+canceled(재결제) 만 허용 / `assertOnboardingFieldsFilled` — 송화인·계좌 7필드 / `seedingAgreement` 서명 필수 — 미서명이면 `400 seeding_agreement_required`, 결제 퍼널이 결제 전에 시딩 계약서를 받으므로 프론트 우회 차단. 존재 여부만 검사) → ② NicePay 빌키발급 + 첫 결제(tx 밖) → ③ 단일 tx 로 `BillingKey` + `BrandSubscription`(active) + paid `SubscriptionInvoice` + `pgCustomerKey` 발급 커밋 → ④ tx 밖에서 `brandApps.approveApplication`(노출 활성화, 멱등). 결제 실패 시 DB row 미생성 + orphan 빌키 expire 정리, 네트워크 불확실 시 망취소(`netCancel`). orderId 는 매 시도 고유(reg=시각·첫결제=bid 기반)라 같은 달 재시도 가능.
- **invoice 생명주기**: 신규 갱신은 `pending` 으로 생성 → 결제 성공 `paid`(`pgTid`/`paidAt` 기록) / 실패 `failed`(`failReason`/`attemptCount`++/`lastAttemptAt`). 어드민 환불 시 paid → `refunded`. 재시도는 직전 `failed` invoice 를 재사용(신규 생성 안 함).
- **구독 상태 전이 (`BrandSubscription.status`)**: `active`(정상) ↔ `past_due`(결제 실패 후, dunning 재시도 대상) → `canceled`(만료/강제해지/환불). 사용자 해지는 `cancelAtPeriodEnd=true` 예약만 하고 `active` 유지 → cron 이 만료 시점에 `canceled` 전환. 해지/환불은 `brand.status` 를 건드리지 않아 재가입(`canceled`→`active`) 가능.
- **정기 청구 cron (`subscription-billing.cron.ts`)**: `@Cron('0 0 * * *', Asia/Seoul)` — KST 자정 일 1회 `runDueBilling()` 위임. 3+1 대상: ① **갱신**(active && `currentPeriodEnd<=now` && !cancelAtPeriodEnd → 청구) ② **종료**(active && 만료 && cancelAtPeriodEnd → canceled) ③ **dunning**(past_due && 최근 invoice failed && 재시도 시점 도래 → 청구) + **수동발급 만료**(billingKey 없는 comp/cash 만료 → `updateMany` 로 일괄 canceled). brand 별 처리는 `Promise.allSettled` 로 격리.
- **dunning 스케줄**: `retryGap(attemptCount)` = `[0, 1, 3, 7]` 일 — 직전 시도 후 0/1/3/7일 뒤 재시도. **4회 이상이면 재시도 없음 → `past_due` 확정**(별도 자동 해지 없음 — 운영자 force-cancel 또는 사용자 카드교체로 정리). 분류(permanent/transient/upstream)는 사용자 메시지용일 뿐, 재시도 여부는 `attemptCount` 만으로 결정.
- **카드 교체 (`POST /change-card`)**: 새 빌키 발급 + 기존 키 soft-delete + 이전 빌키 NicePay expire. `past_due` 였으면 즉시 1회 재청구해 `active` 복귀 시도. comp 플랜은 차단.
- **재개**: `POST /resume`(만료 전 해지예약 취소, `cancelAtPeriodEnd=false`) / `POST /resume-existing-card`(canceled 구독을 기존 빌키로 즉시 재결제해 active 복귀, 빌키 없으면 새 카드 흐름으로 유도) / `POST /cancel`(사이클 만료 후 해지 예약).
- **어드민 액션**: 정책위반 `reject` 는 `brandApps.rejectApplication`(brand.status=rejected) + `forceCancelIfActive`(활성 구독 즉시 해지, 환불 없음)를 함께 호출. `grant`(무료 N개월 + brand 승인 + pending 제품 승인), `grant-cash`(받은 금액 paid invoice 기록 + 동일 승인), `force-cancel`(즉시 해지, 환불 별도), invoice `refund`(NicePay 취소 호출 + invoice refunded + 구독 canceled, 부분환불 `cancelAmount` 지원·현금은 표시만), 제품 단위 `approve`/`reject`.
- **관련 파일**: `subscription.service.ts`(start/getMine/cancel·resume·resumeWithExistingCard/changeCard/runDueBilling·chargeOne/list·detail/forceCancel·forceCancelIfActive/grant·grantCash/refundInvoice), `nicepay-billing.adapter.ts`(registerBillingKey/chargeBilling/deleteBillingKey/cancelPayment/netCancel + resultCode 분류), `subscription-billing.cron.ts`, 2 개 컨트롤러(admin · brand).

## admin-subscription.controller.ts (`@Controller('admin/brand-subscriptions')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                                                       | 기능                                                                    |
|--------|------------------------------------------------------------|-------------------------------------------------------------------------|
| GET    | `/admin/brand-subscriptions`                               | 구독 목록 (status 필터: active/past_due/canceled/none/rejected)         |
| GET    | `/admin/brand-subscriptions/:id`                           | brand 구독 상세 (+ 빌링키·invoice 전체·제품, `monthlyPriceKrw` 포함)    |
| PATCH  | `/admin/brand-subscriptions/:id/reject`                    | 정책위반 차단 — brand reject + 활성 구독 강제 해지(환불 없음)           |
| PATCH  | `/admin/brand-subscriptions/:id/grant`                     | 무료 구독권 부여 — 결제 없이 N개월 active + brand 승인 + 제품 승인       |
| PATCH  | `/admin/brand-subscriptions/:id/grant-cash`                | 현금결제 구독 발급 — 받은 금액 paid invoice 기록 + N개월 active          |
| PATCH  | `/admin/brand-subscriptions/:id/force-cancel`              | 즉시 해지 (환불은 별도, 재가입 가능)                                    |
| PATCH  | `/admin/brand-subscriptions/:id/invoices/:invoiceId/refund`| invoice 환불 — NicePay 취소(부분환불 가능) + invoice refunded + 구독 해지|
| PATCH  | `/admin/brand-subscriptions/:id/products/:productId/approve`| 제품 단위 승인                                                          |
| PATCH  | `/admin/brand-subscriptions/:id/products/:productId/reject` | 제품 단위 차단(reject)                                                  |

## brand-subscription.controller.ts (`@Controller('v1/brand/subscription')`)

> 전체 라우트 `BrandGuard` (caller 자신의 brand 로 스코프).

| Method | Path                                       | 기능                                                          |
|--------|--------------------------------------------|---------------------------------------------------------------|
| GET    | `/v1/brand/subscription`                   | 내 구독 + 빌링키 + 최근 invoice 12건                          |
| POST   | `/v1/brand/subscription/start`             | 빌키발급 + 첫 결제 + brand 승인 (신규/재가입 결제 진입)        |
| POST   | `/v1/brand/subscription/cancel`            | 사이클 만료 후 해지 예약 (`cancelAtPeriodEnd=true`)           |
| POST   | `/v1/brand/subscription/resume`            | 해지 예약 취소 (만료 전, 다음 사이클 자동 갱신 복구)          |
| POST   | `/v1/brand/subscription/resume-existing-card`| canceled 구독을 기존 빌키로 즉시 재결제해 active 복귀         |
| POST   | `/v1/brand/subscription/change-card`       | 카드 교체 (past_due 면 즉시 1회 재청구)                        |

## 관련 문서

- 브랜드 입점/심사 워크플로우는 [brand-applications](./brand-applications.md) — 구독은 그 위의 결제 게이트.
- 구독 매출 정산은 [settlement](./settlement.md).
- 전체 결제 흐름·NicePay 교체 배경·Stage 분리 설계는 워크스페이스 문서 [`../../../docs/brand-subscription.md`](../../../docs/brand-subscription.md).
