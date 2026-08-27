# 커스텀 도메인 대행 구매 (P6) — KLOW 가 사서 연결하고 연 이용료를 받는다

> **현재 상태: ✅ 구현 완료 (2026-08-26) — §19 의 A · B · C · D · E · F 전부 끝났다. 남은 것은 코드가 아니라 배포·약관·§0 실측이다.**
> 이 문서가 이 기능의 **정본**이다.
>
> ---
>
> ## 🚦 다음 세션이 여기부터 읽는다 — 진행 상황 (2026-08-26 갱신)
>
> **작업 위치**: 워크트리 `/Users/hyson/welkit/klow-domain/klow_server`,
> 브랜치 `feat/domain-purchase` (staging 기준). 새로 만들지 말 것.
> 머지는 전부 끝난 뒤 `cd /Users/hyson/welkit/klow/klow_server && git checkout staging &&
> git merge --no-ff feat/domain-purchase`, 정리는 `git worktree remove`.
>
> ### 끝난 것 — 커밋 9개 (**klow_server 는 전부 끝났다**)
>
> | PR | 커밋 | 내용 |
> |---|---|---|
> | **A** | `7a5dcb7` | Prisma 모델 2 + enum 3 + 역방향 relation 2줄 (마이그레이션 `20260826024609_add_brand_domain_purchase` 적용) · `src/pricing/domain-price.ts` + 배럴 + 스펙 |
> | **B** | `aedd709` | registrar 확장(`checkDomains`·`createRegistration`·`getRegistrationStatus`·`setAutoRenew` + `CloudflareRegistrationIndeterminateError`) · `cloudflare-dns.client.ts` · `domain-dns.ts` + 스펙 18개 · §6 "전제 5곳" 전부 갱신 |
> | **C-1** | `1e7cb0f` | `subscription/dunning.ts`(`retryGap`·`throwAsHttp`) · `subscription/billing-key-select.ts` · `orderIdFrom` static 승격 · **`findPaymentByOrderId` 신규** · `SubscriptionModule.exports = [NicepayBillingAdapter]` |
> | **C-2** | `6274dc2` | `domain-purchase.service.ts` · `registration-status.ts` · `brand-domain-purchase.controller.ts` · `brand-domain-registrations.cron.ts` · `attachPurchasedDomain` · `DELETE` 조건부 차단 · e2e cron 9→10 · env 2개 |
> | **C-3** | `2b1fb36` | 스펙 3종(구매 24 · 폴링 19 · 상한/서킷 15) + harness 구매 축 확장 |
> | **D-1** | `c39c4cd` | `domain-dns.service.ts` 신설 · `removeDomainPair` 추출 · `cleanupOrphans` DNS 정리 · `releaseDomain`(§18-1a 4단계) · `reviveReleasedRegistration` · 어드민 라우트 7개 · `domain-release.spec.ts` 17개 |
> | **D-2** | `b770ae4` | `domain-revenue.ts` 분리 + `GET /admin/stats/kpi` 의 `domainRevenue`(§16-6) + kpi 스펙 2개 |
> | **E-1** | `8c7e7c6` | `KakaoService.sendTemplate` · `domain-notify.service.ts`(알림 4종) · **`markActionRequired` 초크포인트** · `domain-notify.spec.ts` 4개 · env 4개 |
> | **E-2** | `ea62df4` | `domain-renewal.service.ts` + `brand-domain-renewal` cron(사전 고지·청구·dunning·**만료일 전진 확인**·만료 정리) · e2e cron 10→11 · `domain-renewal.spec.ts` 17개 |
>
> **실측값**: 라우트 **315 → 325**, cron **9 → 11**, 유닛 **794 → 892개**(61스위트).
> 검증 3층은 매 커밋마다 통과시켰다(typecheck 2개 tsconfig · `test:e2e` · `PORT=4001 npm run start`).
> ⚠️ 포트 4000 은 메인 체크아웃 dev 서버가 점유 중일 수 있어 **4001** 을 쓴다.
>
> ### 프론트 2개도 끝났다 (2026-08-26)
>
> | PR | 레포 · 브랜치 | 커밋 | 내용 |
> |---|---|---|---|
> | **D(화면)** | `klow_admin` · `feat/domain-purchase` (워크트리 `/Users/hyson/welkit/klow-domain/klow_admin`) | `b75a365` | §16 도메인 탭 — 탭 배열 1줄 + `BrandDomainPanel` + 다이얼로그 3종 + `lib/api/brand-domains.ts` + `lib/domain-status.ts` + KPI '도메인 매출' 타일 |
> | **F(서버)** | `klow_server` · 같은 브랜치 | `c243964` | §12 — `/me` 가 `customDomain`·`domainPending` 을 파생해 내린다 + 스펙 5케이스 |
> | **F(화면)** | `klow_brand` · `feat/domain-purchase` (워크트리 `/Users/hyson/welkit/klow-domain/klow_brand`) | `2e3b7b9` | §13~§15 — `/settings/domain` 신설 · 스튜디오 말풍선 · `DomainSection` 삭제 |
>
> **실측값**: 라우트 **325 유지**(§12 는 라우트를 안 늘린다) · cron **11** · 서버 유닛 **897개**(62스위트).
> 세 레포 모두 typecheck · lint · build(프론트) / test:e2e · start(서버) 통과.
>
> ### 남은 것 — 코드가 아니다
>
> 1. **머지** — 세 레포의 `feat/domain-purchase` 를 각각 staging 으로(§19 배포 순서는 그대로).
> 2. **도메인 구매 약관**(§18-1, 법무) — 배포 5단계를 막는다. 구매 다이얼로그에 고지 문구는
>    이미 있고 `/legal` 링크 자리만 `TODO` 로 비어 있다.
> 3. **§0 실측 + 스테이징 리허설 1건**(환불 불가라 유일한 실전 검증).
> 4. 알림톡 템플릿 4개(배포를 막지 않는다 — 미승인이면 SMS 폴백).
>
> ### ⚠️ 프론트에서 문서와 다르게 간 곳 3가지 (2026-08-26 · 되돌리지 말 것)
>
> 1. ⚠️⚠️ **§12 가 지목한 `APPLICATION_INCLUDE` 는 틀린 자리다.** 그건 **어드민 목록 전용**이고
>    (`brand-applications.service.ts:44`, 소비자는 `:818` 하나), 스튜디오가 부르는
>    `GET /v1/brand/applications/me` → `getMyApplication()` 은 **자체 인라인 include**
>    (products + subscription)를 쓴다. 거기 넣지 않으면 말풍선이 영원히 안 뜬다.
> 2. ⚠️⚠️ **자동저장이 캐시의 brand 를 통째로 갈아치우고 있었다.** `updateApplication` 은
>    include 없이 **bare Brand** 를 돌려주는데 `useBrandAutoSave.onSuccess` 가
>    `setQueryData(qk.brandApplication, { brand: result })` 로 **교체**한다 → 첫 자동저장
>    이후 `products`·`subscription`(그리고 이번에 추가한 두 필드)이 다음 invalidate 까지
>    사라져, §13 의 말풍선 조건(`subscription?.status === 'active'`)이 **영구히 false** 가 된다.
>    → `setQueryData` 를 **병합**으로 바꿨다(`{ brand: { ...prev?.brand, ...result } }`).
>    result 에 있는 키는 전부 result 가 이기므로 안전하고, 잠재 버그를 함께 고친 것이다.
>    ⚠️ 대안(=`updateApplication` 에 include 추가)은 800ms 마다 나가는 응답을 무겁게 만든다.
> 3. ⚠️ **§15 의 "`api.domains.remove` 제거"는 3차 점검과 모순이라 따르지 않았다.** §11 이
>    브랜드 `DELETE` 를 전면 제거가 아니라 **조건부 차단**으로 바꿨고, §20 수동 E2E 10번이
>    "어드민이 붙인 `.co.kr` 을 브랜드가 스스로 해제할 수 있는지"를 검증 항목으로 못박았다.
>    → **`create` 만 제거하고 `remove` 는 남겼다.** 구매 도메인 카드에는 삭제 버튼 대신
>    "연결 해제 문의" 안내를 띄워 409 를 미리 피한다.
>
> 그리고 문서에 없던 판단 둘:
> - **DNS 안내는 브랜드 소유 도메인에만 그린다.** §14 는 `DomainStatusPanel` 에 "DNS 안내 없음"
>   이라고만 적었는데, 그건 **구매 도메인에만** 참이다(우리가 Cloudflare 에서 직접 심는다).
>   어드민이 붙여 준 브랜드 소유 도메인은 브랜드가 자기 등록기관에 직접 넣어야 하고 **그 값을
>   알려 주는 화면이 여기 말고 없다** — 지우면 그 경로가 통째로 막힌다.
> - **구매 확인 다이얼로그는 가격을 다시 묻는다.** 목록 견적은 서버 5분 캐시라 그대로
>   `expectedAmountKrw` 로 보내면 409 를 자초한다. 그 409 의 재계산가를 읽으려고 klow_brand
>   `ApiError` 에 **`payload`**(파싱된 본문 원본)를 추가했다.
>
> ### ⚠️ 서버 구현이 문서와 다른 곳 6가지 (전부 코드 주석에 이유가 박혀 있다. 되돌리지 말 것)
>
> 1. **`ceilToUnitKrw()` 를 분리하고 부동소수 가드(`toPrecision(12)`)를 넣었다**(§5).
>    `10000 * 1.1 === 11000.000000000002` 이라 순진한 `Math.ceil` 이 ₩11,000 을 ₩12,000 으로
>    만든다(공급가 200만 이하 115건). **공식 자체는 문서 그대로**다.
> 2. **`planDnsConvergence(apexHost, desired, existing)`** — 문서 §6 서명에 `apexHost` 를 더했다.
>    없으면 `desired = []`(연결 해제)일 때 관리 대상 이름·타입을 몰라 **아무것도 못 지운다**
>    → §20 의 "`desired=[]` → 우리 레코드만 전부 remove" 가 성립하지 않는다.
> 3. **`hasUnknownRecordValue()` 를 추가로 export 했다**(`domain-dns.ts`). `desiredRecordsFor` 가
>    빈 `recordValue` 를 빼고 나면 **"값을 모른다"와 "연결 해제"가 둘 다 `[]` 로 보인다** —
>    전자를 후자로 오독하면 §7-3 c 가 우리 레코드를 지운다. 호출부는 이걸 먼저 봐야 한다.
> 4. **`billing-key-select.ts` 는 기존 세 호출부를 정본으로 갈아끼우지 않았다**(§10).
>    셋 다 동작이 바뀌기 때문이다 — 특히 정기청구(`chargeReady`·`chargeOne`)에 `deletedAt` 을
>    넣으면 청구 실패가 dunning 이 아니라 **"행이 아예 안 잡힘"** 이 되어 구독이 `active` 인 채
>    만료일을 지나 **무료로 계속 서빙**된다. 일회성은 "잘못된 카드에 긁는 것"이, 정기청구는
>    "안 긁고 침묵하는 것"이 최악이라 방향이 반대다. 그래서 `RECURRING_CHARGEABLE_WHERE` 로
>    갈래를 **의도로 명시**했다(이 파일의 목적은 "통일"이 아니라 "갈라진 것을 사고가 아니라
>    의도로 만드는 것"). ⚠️ §10 표의 `resumeWithExistingCard` 행도 부정확했다 — 거긴
>    `pgCustomerKey` 가 없으면 **그 자리에서 발급**하므로 정본과 애초에 다르다.
>
> 5. **`releaseDnsFor` 의 소유자를 `domain-dns.service.ts`(신규 제공자)로 내렸다**(§18-2 b).
>    문서대로 `domain-purchase.service.ts` 에 두면 **DI 순환**이다 — 부르는 쪽이 둘인데
>    (어드민 연결 해제 · `cleanupOrphans`) 후자가 `BrandDomainsService` 이고
>    `DomainPurchaseService → BrandDomainsService` 의존이 이미 있다(forwardRef 가 필요해진다).
>    문서가 지키려던 것은 이름이 아니라 **"Cloudflare 호출을 brand-domains 로직 안에 쓰지
>    않는다"** 이므로 훅을 더 아래 계층으로 내려 규칙을 지키면서 순환을 없앴다.
>    (`CloudflareDnsClient` 를 그 서비스에 직접 주입하는 선택지는 정확히 그 규칙을 어긴다.)
> 6. **`action_required` 전이를 `markActionRequired` 한 곳으로 모았다**(§9-2 4번).
>    문서엔 알림 발화 지점이 안 적혀 있었는데, 전이가 다섯 곳에 흩어져 있어 각 자리에 알림을
>    붙이면 **여섯 번째 지점이 생기는 날 무음으로 멈춘 건**이 생긴다.
>
> ### ⚠️⚠️ §0 미실측이라 보수적으로 짜고 `TODO` 로 남긴 두 분기
>
> 실측이 끝나면 **이 둘만** 손보면 된다. 코드에 `TODO(§0-6)` / `TODO(§0)` 로 표시돼 있다.
>
> | 위치 | 지금 동작 | 실측 후 |
> |---|---|---|
> | `submitRegistration` 의 `privacyMode` | **무조건 `'redaction'`.** 거절하는 TLD 면 4xx 분기로 떨어져 **전액 환불**된다(손실 0, 다만 브랜드는 이유를 모른다) | §0 6번 → (a) 구매 가능 TLD 화이트리스트 또는 (b) 그 TLD 만 `'off'` 로 1회 재시도. ⚠️ (b)는 재시도 **전에** 우리 계정 등록 여부를 먼저 확인할 것 |
> | `advanceRegistering` 의 `action_required` | **전부 사람 큐**(fail-closed). 자동 환불 0건 | fee acknowledgement 필드명을 실측해 §7-4 첫 두 칸(프리미엄·미지원 TLD)만 즉시 환불로 내린다 |
>
> 그리고 **`findPaymentByOrderId`** — 존재하지 않는 orderId 에 NicePay 가 404 를 주는지
> 200 + 비-0000 resultCode 를 주는지 미실측이다. 지금은 **404 만** "거래 없음" 으로 확정하고
> 나머지는 던진다(= `charge=pending` 이 안전한 쪽으로 고착). ⚠️ 실측 없이 임의의 코드를
> "거래 없음" 으로 매핑하지 말 것 — 승인된 결제를 미승인으로 확정하면 돈만 받고 도메인을 못 준다.
>
> ### 배포를 막는 코드 밖 항목
>
> - ⚠️⚠️ **도메인 구매 약관**(§18-1, 법무 검토) — **외부 리드타임**이고 구매 다이얼로그가
>   링크해야 하므로 §19 배포 5단계를 막는다. 지금 착수할 것.
> - **§0 실측** — 스테이징 자격증명으로 값싼 도메인 1개 실제 구매(환불 불가).
> - 알림톡 템플릿 4개는 **배포를 막지 않는다**(미승인이면 SMS 폴백).
>
> ---
>
> 착수 전 [§0 실측 항목](#0-착수-첫날-실측--여기서-답이-갈리면-7-3-이-바뀐다)을 볼 것 —
> 거기서 답이 갈리면 §7-3 의 연결 절차가 바뀐다.
>
> 🔎 **검토 반영분(2026-08-25)** — 초안을 코드와 대조해 고친 것들. 되돌리지 말 것:
> **사실 오류 3** ① `DEFAULT_BILLING_KEY_WHERE` 는 **존재하지 않는다**(§10 — "추출"이 아니라 신설)
> ② `throwAsHttp` 도 모듈 로컬 미export 라 §10 목록에 추가 ③ `pendingGiveUpWhere` 논거는 사실이
> 아니라 §4 에서 교체(결론은 유지).
> **돈이 걸린 공백 4** ④ 동시 구매를 막는 장치가 실제로 없었다 → **`FOR UPDATE` 행 잠금**(§7-1-D)
> ⑤ `netCancel` 은 실패해도 throw 하지 않는다 → charge 를 **`pending` 유지**(§7-1-E)
> ⑥ `brandId` FK 기본값 `Restrict` 가 어드민 브랜드 삭제를 깨뜨린다 → **nullable + SetNull**(§4)
> ⑦ 구매 후 구독이 끊기면 연결이 403 → **환불 말고 `registered` 유지**(§7-3).
>
> 📌 **제품 결정 반영분(2026-08-25)** — §2 요구사항 표에 4줄이 늘었다:
> **소유권 이전 안 함**(§18-1, 약관 필요) · **2년차 가격 병기 + 청구 7일 전 고지**(§9-1) ·
> **브랜드 알림 4종: 알림톡 정본 + SMS 폴백**(§9-2, 템플릿 승인 필요) ·
> **프리미엄·미지원 TLD 는 즉시 환불 + 직접 구매 안내**(§7-4).
> 함께 채운 빈칸: **DNS·zone 정리 경로**(§18-2 — §1 의 약속에 코드 경로가 없었다) ·
> **우리 카드 실패 서킷브레이커**(§18-3) · **구매 상한**(§18-4) · **API 응답 shape**(§11).
> ⚠️ 약관·알림톡 템플릿은 **외부 리드타임**이라 §19 4.5 단계로 앞당겨 착수한다.
>
> 🔁 **2차 전수 점검(2026-08-26)** — 위 결정을 반영한 뒤 문서 전체를 다시 훑어 찾은 것들:
> ⓐ ⚠️⚠️ **연결 해제가 `setAutoRenew(false)` 를 안 불러 만료일에 우리 카드가 긁혔다**(§18-1a)
> ⓑ registration 에 **`released` 상태가 없어** `active` 의 정의가 거짓이 됐다(§4)
> ⓒ §7-1-E 가 부르는 **NicePay 거래 조회 메서드가 어댑터에 존재하지 않는다**(§10 · `findPaymentByOrderId`)
> ⓓ §0 이 "둘 다 스냅샷"이라 했는데 **`renewalCostUsdCents` 컬럼이 없었다**(§4 · §9-1)
> ⓔ §5 는 "env 오버라이드 없음"인데 §11 env 목록에 `DOMAIN_MARGIN_RATE` 가 남아 모순(§11)
> ⓕ 만료 정리가 **`removeForBrand`(brandId 필수·소유검증)** 를 부르는데 brandId 가 nullable 이 됐다(§9)
> ⓖ `registered` 재시도에 **백오프·상한이 없어** 1년 내내 2분마다 Vercel 을 친다(§7-3)
> ⓗ `privacy_mode`·`years`·`goodsName` 미결정(§7 6·4단계). → **전부 확정(2026-08-27)**: §0 3번 표(필드 타입) + §7 4단계(바이트 상한).
> 그 밖에 상호참조 5건(§0→§9 · §6→§7-1 · §7 흐름10→§7-3 · §7-2→§7-4 · §3→§7-4/§18-1)과
> env 6개 누락을 고쳤다.
>
> 🔁🔁 **3차 전수 점검(2026-08-26)** — 남은 결함 13건. 앞의 두 점검이 **구매 순간**에 집중한 반면
> 이번에 걸린 것은 대부분 **"구매 이후의 수명"** 이다. 되돌리지 말 것:
> **치명 4** ①⚠️⚠️ **갱신 성공 후 `expiresAt` 을 전진시키는 경로가 없어** 정상 갱신된 도메인의
> 연결이 만료일에 끊긴다(§9-3) ② §7 흐름 8이 **`createRegistration` 재호출을 빠뜨려** 카운터만
> 올리고 환불한다(§7 흐름 8) ③ `charge=pending` 보정 조건이 **`lastAttemptAt` null 을 못 집어**
> `charging` 영구 고착 + 재구매 영구 차단(§7 흐름 11) ④ 락이 Brand 단위라 **같은 host 동시 구매**가
> §7-4 fail-closed 와 충돌해 손실 0인 건이 환불되지 않는다(§7-1-F).
> **중대 6** ⑤ 서킷브레이커의 **저장소·리셋 경로 미정의**(§18-3) ⑥ 브랜드 `DELETE` 전면 제거는
> 과잉 — 어드민 수동 연결 도메인은 브랜드 소유다(§11 · §18-1a) ⑦ `GET registration` 이 단수형인데
> 행은 N개(§11) ⑧ 말풍선이 **구매 진행 중에도** 떠 막다른 길(§13) ⑨ 구매 상한이 `charging` 을
> 안 세어 동시 요청을 못 막는다(§18-4) ⑩ `released` 재연결이 `MAX_DOMAINS_PER_BRAND` 에 걸린다(§18-1a).
> **빈칸 3** ⑪ `privacy_mode:true` 를 금지 TLD 에 무조건 보낸다(§7 6단계 · §0) ⑫ §0 에 **zone 활성화
> 관찰**이 없다 ⑬ 도메인 매출이 **어느 리포트에도 안 잡힌다**(§16).
>
> 🔧 **env 정리(2026-08-26) — 12개 → 3개 + 외부 식별자 4개.** 되돌리지 말 것(근거는 §11 env 절):
> 구매 상한 2개는 **코드 상수**로 내렸고(이 레포엔 env 수치 상한이 0건 · `=0` 오타가 전 브랜드
> 구매를 조용히 막는다), `BRAND_DOMAIN_RENEWAL_CRON_ENABLED` 는 **삭제**해
> `DOMAIN_PURCHASE_ENABLED` 마스터 게이트에 흡수했다("돈 나가는 cron 은 opt-in" 은 레포 관례가
> 아니고 — cron 9개 중 switch 3개, 정작 `brand-subscription-billing` 에는 없다 — 그 스위치는 위험을
> 줄이는 게 아니라 **"1년 뒤 켜기를 잊으면 도메인이 만료된다"로 옮긴다**). 알림톡 템플릿 4개는
> 튜너블이 아니라 카카오 발급 식별자라 남기되 **전부 선택**이라 배포를 막지 않는다.
>
> ✅ **구현 착수 가능성 최종 점검(2026-08-26)** — "새 세션이 이 문서만 보고 짤 수 있는가" 기준으로
> 훑어 **빈칸 6개**를 메웠다(전부 2·3차 점검이 새로 만든 것들이다):
> ㉠ §9-3 이 참조하던 `renewalConfirmPending` 이 **컬럼으로 존재하지 않았다** → 플래그를 만들지 않고
> **`periodEnd` 를 nullable 로 바꿔 그 null 이 "확인 대기" 마커**가 되게 했다(§4 · §9-3)
> ㉡ 그 `periodEnd` 는 **non-null 로 선언돼 있어** §9-3 의 "청구 시점에 확정하지 말라"와 정면 충돌했다(§4)
> ㉢ §18-3 이 **"새 테이블·컬럼 금지"와 "`resetAt` 저장"을 동시에 요구**했다 → **쿨다운 half-open**
> 으로 바꿔 저장을 0으로 만들고 **리셋 라우트를 없앴다**(§18-3 · §11)
> ㉣ `expiresAtIsEstimated` 행이 "어드민 알림만" 이라 **방치되면 우리 카드가 긁혔다**(§18-1a 재발)
> → 2단계 + `ESTIMATED_GIVE_UP_DAYS`(§9)
> ㉤ Prisma **역방향 relation 2줄이 빠져 `generate` 가 통과하지 않았다**(§4 — 이름이 §12 와의 계약)
> ㉥ `ACTIVE_REGISTRATION_STATUSES` 의 **소유 파일이 미정**이었다(§12).
>
> ⚠️ 이 문서의 `file:line` 은 **2026-08-25 스냅샷**이다. 구현 시점엔 밀려 있을 수 있으니
> **심볼명(함수/상수)으로 재확인**한 뒤 편집할 것(형제 문서 두 개와 같은 관례).
>
> 선행 문서: [`README.md`](./README.md) → [`flow.md`](./flow.md) →
> [`implementation-plan.md`](./implementation-plan.md) (P0~P5). 이 문서는 그 다음 단계다.

---

## 1. 왜 이걸 하는가

P0~P4 로 만든 커스텀 도메인은 **브랜드가 자기 도메인을 이미 갖고 있다**는 전제 위에 서 있다.
설정에서 호스트를 입력하면 서버가 Vercel 에 등록하고 A/CNAME 을 안내하고, **브랜드가 자기
등록기관(가비아 등)에 가서 DNS 를 손으로 넣는다.** 그 왕복이 이 기능의 실질 진입 장벽이다.

2026-08-24~25 에 `/start`(가입 직후 브랜드 주소를 정하는 화면)에 **도메인 검색 + 찜하기**가 붙었다.
브랜드명을 치는 동안 Cloudflare Registrar `domain-search` 로 구매 가능한 도메인을 2열로 보여주고,
하트를 누르면 `BrandDomainWish` 에 저장된다. 그런데 **그 찜을 다시 볼 화면이 없다** — `/start` 를
지나 스튜디오로 들어가면 접근 경로가 0이고, 설정 > 도메인 연결은 찜을 읽지도 않는다. 찜 커밋이
스스로 *"최종 목표는 스튜디오에서 찜한 도메인을 바로 사는 것이고, 이 커밋은 그 데이터가 쌓이기
시작하는 데까지"* 라고 적어 둔 그 다음 작업이 이것이다.

### 핵심은 DNS 왕복을 없애는 것이다

우리 Cloudflare 계정으로 사면 **그 도메인의 네임서버가 곧 Cloudflare** 라(Registrar 로 등록한
도메인은 Cloudflare 네임서버에 남아야 한다) A/CNAME 을 **우리가 API 로 직접 꽂을 수 있다**.
브랜드는 결제 버튼 하나만 누르고, 등록 → DNS 주입 → Vercel 연결 → 검증은 전부 서버가 한다.

```
[종전]  브랜드가 도메인 보유 → 설정에 host 입력 → 우리가 A/CNAME 안내
        → 브랜드가 가비아에 로그인해 DNS 입력 → 몇 시간~며칠 → active

[이번]  브랜드가 찜/검색 → 결제 버튼 1회
        → (서버) 카드 청구 → Cloudflare 등록 → zone DNS 주입 → Vercel 연결 → active
```

도메인은 **KLOW 소유**이고 브랜드에게는 **연 단위 이용료**를 받는다.

### 부수 효과 — `brand-domains.md` 의 알려진 갭 2건이 **구매 경로에서** 닫힌다

| 갭 | 구매 경로에서 왜 닫히나 |
|---|---|
| **댕글링 DNS → 브랜드 간 도메인 인계** | DNS 를 우리가 소유하므로 브랜드 A의 연결을 끊을 때 레코드도 우리가 지운다. 남의 도메인이 Vercel 을 계속 가리키는 상태 자체가 성립하지 않는다 |
| **미검증 도메인 스쿼팅이 영구적** | 호스트 직접 입력이 브랜드 화면에서 사라진다. 자기 것이 아닌 호스트를 잡아 두는 경로가 없다 |

⚠️ **두 갭이 사라지는 것이 아니다 — 우리가 산 도메인에서만 닫힌다.** §3 때문에 어드민 수동 연결이
필수로 남고, `brand.co.kr` 을 이미 가진 한국 브랜드는 **다수가 그 경로**로 들어온다. 그쪽 도메인은
DNS 가 여전히 브랜드 소유라 댕글링 인계도, 행이 남아 `domain_taken` 409 가 영구화되는 스쿼팅도
종전 그대로다. **`brand-domains.md` 의 「알려진 갭」 항목을 지우지 말 것.**

---

## 2. 확정 요구사항 (2026-08-25)

| 항목 | 결정 |
|---|---|
| 진입 | 스튜디오 폰 목업 위 링크바에 **"커스텀 도메인 만들기" 말풍선**(미연결 + 구독 active) |
| 페이지 | **`/settings/domain`**. 설정 허브에는 진입 카드 |
| 도메인 소스 | 찜 목록 + 그 자리 검색 |
| 소유 | **KLOW 소유** (우리 Cloudflare 계정 등록) |
| 가격 | 원가(USD) × `resolveFxRate` × **1.3 = 공급가** → ×1.1 VAT → **1,000원 올림** = 청구가 |
| 결제 | **기존 구독 `BillingKey` 즉시 청구**(카드 재입력 없음) |
| 수작업 DNS | **브랜드 화면에서 완전 제거** · 어드민에만 수동 연결 유지 |
| 개수 | 브랜드당 **1개** (+`www` 자동) — ⚠️ 상수가 아니라 §7 0단계 게이트로 강제 |
| 갱신 미납 | 0/1/3/7 dunning → **`auto_renew=false`** → 만료 |
| 어드민 | `/brands/[id]` **도메인 탭** + 수동 연결 |
| **소유권 이전** | **하지 않는다.** 도메인은 KLOW 보유 · 만료까지 서빙 후 소멸 (§18-1) |
| **갱신가 고지** | 구매 화면에 **2년차 가격 병기** + **청구 7일 전(만료 37일 전) 사전 고지** (§9-1) |
| **브랜드 알림** | **알림톡(Solapi) 정본 · SMS 폴백** — 4종 (§9-2) |
| **자동 실패 건** | 프리미엄·미지원 TLD 는 **즉시 환불 + 직접 구매 안내** (§7-4) |

⚠️⚠️ **"1개" 를 `MAX_DOMAINS_PER_BRAND` 로 구현하지 말 것.** 그 상수(`domain-host.ts:15`)는 지금 **3**
이고 primary + www redirect 를 **합쳐서** 센다. 1로 낮추면 ① `domain-host.spec.ts:131` 의
`expect(MAX_DOMAINS_PER_BRAND).toBeGreaterThanOrEqual(3)` 이 깨지고 ② `createForBrand` 의
`used + 2 > MAX` 분기가 발동해 **www 페어가 통째로 생략**된다(apex 를 사도 `www` 가 안 붙는다).
개수 제한은 §7 0단계 게이트("primary `BrandDomain` 0개")가 전담한다 — §20 의 "기존 스펙 무변경
통과"는 **이 상수를 안 건드릴 때만** 참이다.

### 마진 30% 의 기준 — 공급가다

| 단계 | `.shop` 예시 |
|---|---|
| Cloudflare `registration_cost` | `$32.98` |
| × `resolveFxRate` (1,400) | `₩46,172` |
| **× 1.3 (마진 30%)** | **`₩60,024`** ← 공급가 |
| × 1.1 (VAT) | `₩66,026` |
| **1,000원 올림** | **`₩67,000` / 년 (VAT 포함)** |

실마진 `₩13,852` = 원가 대비 정확히 **30.0%**. ⚠️ 원가×1.3 을 *최종 청구가*(VAT 포함)로 잡으면
공급가가 원가×1.18 이 되어 **실마진이 20% 로 내려간다** — 구독료(396,000·660,000)가 전부 VAT
포함 실청구액이라 무심코 같은 기준을 쓰기 쉽다. `SubscriptionInvoice.amountKrw` 와 같은 기준으로
**최종 청구가**를 저장하되, 계산의 마진 곱은 **공급가 단계**에서 일어난다.

---

## 3. ⚠️ 확인된 커버리지 한계 — `.kr`·`.co.kr` 미지원

**Cloudflare Registrar 는 `.kr`·`.co.kr` 을 지원하지 않는다.** `.jp`·`.de`·`.cn` 도 없다. 지원되는
ccTLD 는 `.uk`(`.co.uk`) · `.co` · `.mx` · `.nz` · `.ca` 정도이고 나머지는 gTLD(`.com`·`.shop`·
`.store`·`.dev`·`.app`·`.xyz` …)다.

즉 **한국 브랜드가 흔히 보유한 `brand.co.kr` 은 구매 경로로 영영 못 붙인다.** 그래서 어드민 수동
연결이 선택이 아니라 **필수**다 — 이게 없으면 "이미 가진 도메인을 연결하는 방법"이 세상에서
사라진다(브랜드 화면에서는 제거하고 운영팀 경로만 남기는 이유).

그 밖의 벤더 제약:

- **프리미엄 도메인**은 explicit fee acknowledgement 가 필요하다 → 자동 승인하지 않는다.
  처리는 **§7-4**(과금 전이므로 **즉시 환불 + 직접 구매 안내**).
- `reason: extension_not_supported_via_api` — 대시보드는 되는데 API 는 안 되는 TLD 가 있다. 같은 §7-4.
- **transfer API 없음**(beta). ℹ️ 그런데 **우리는 애초에 이전을 하지 않기로 했다(§18-1)** 이므로
  이 제약은 정책의 근거가 아니라 각주일 뿐이다 — 정책이 바뀌면 그때 대시보드 수동 작업이 된다.

---

## 0. 착수 첫날 실측 — 여기서 답이 갈리면 §7-3 이 바뀐다

스테이징 자격증명으로 **값싼 도메인 1개를 실제로 사서** 확인한다. **환불이 안 되므로 이것이 유일한
실전 검증**이고, 문서로 대체할 수 없다.

1. **등록 시 Cloudflare zone 이 자동 생성되는가.** 공식 문서에 언급이 없다(Registrar 로 산 도메인은
   "Cloudflare 네임서버에 남아야 한다"고만 돼 있다). → 코드는 `GET /zones?name=` 조회 후 없으면
   `POST /zones` 하는 **멱등 경로**로 짜서 양쪽 결과를 모두 커버한다.
   1-a. ⚠️ **zone 이 `pending`(NS 미확인) 인 동안 DNS 레코드 API 가 먹는가, 그리고 `active` 까지
   얼마나 걸리는가.** §7-3 은 `createZone` **직후** 레코드를 주입하는데, 새 zone 이 pending 이면
   레코드가 만들어져도 응답하지 않을 수 있다. 이 값이 **c 단계 재시도 주기의 유일한 근거**다 —
   측정하지 않으면 "레코드는 심었는데 `refreshOne` 이 계속 `misconfigured`" 를 버그로 오진한다.
2. `registration-status` 응답에 **만료일이 실려 오는가** — `expiresAtIsEstimated` 컬럼의 존재 이유다.
   ✅ **실측 완료(2026-08-27): 안 온다. 이 엔드포인트는 `expires_at` 을 절대 싣지 않는다**
   (대시보드엔 만료일이 보이는데 응답은 계속 null 이었다). 만료일의 정본은 **다른 엔드포인트**인
   `GET .../registrar/registrations/{domain}` 이고 거기엔 `expires_at`·`auto_renew`·`status`·
   `locked` 가 있다(문서: *"Present when the registration is ready; may be null only while
   status is registration_pending"*).
   ⚠️⚠️ 이걸 모르고 `registration-status` 에서 만료일을 읽던 동안 **두 곳이 조용히 망가져 있었다**:
   ① 모든 구매가 `expiresAtIsEstimated:true` 로 시작 → §9 갱신 고지·청구가 그 필터에 걸려
   통째로 건너뛰어지고 만료 7일 전 자동갱신이 꺼진다(= **1년 뒤 도메인 소멸**)
   ② §9-3 의 만료일 전진 비교가 **영원히 거짓** → 정상 갱신까지 전부 `action_required` 로 떨어져,
   "우리 계정 카드 사망 탐지기" 가 오경보만 내는 장치가 된다.
   ⚠️ **`registration-status` 를 이걸로 대체하지 말 것** — 우리 상태 머신은 `failed`·
   `action_required`·`blocked` 로 갈리는데 이쪽 `status` 에는 그 값들이 없다. 역할이 다르다:
   진행 판정은 `registration-status`, 레지스트리 사실은 `registrations/{domain}`.
3. **토큰 스코프.** 지금 `CLOUDFLARE_REGISTRAR_TOKEN` 은 `.env.example` 이 *"가능하면 읽기 전용으로
   — write 토큰은 도메인을 등록해 돈을 쓸 수 있다"* 라 안내해 발급됐을 가능성이 높다.
   **Registrar Write** 가 필요하고, **Zone DNS:Edit 는 별도 토큰**(`CLOUDFLARE_DNS_TOKEN`, §6)이다.
   ⚠️ 스테이징·운영 토큰을 **반드시 분리**한다 — §11 의 `DOMAIN_PURCHASE_ENABLED` opt-in 이 있어도
   토큰이 같으면 실수 한 번이 실제 돈이다.
4. 계정 **default registrant contact** 설정 여부(없으면 `registrations` 가 거절된다).
   ✅ **실측 완료(2026-08-27)** — 없으면 `400 No registrant contact provided and no default address
   book entry found for this account.` 로 확정 거절된다. 해결은 코드가 아니라 대시보드
   **Domains → Registrations → Create default contact**(주소록 기본 항목)다. ⚠️ 등록자는 전 브랜드
   공통 **KLOW 법인 정보**여야 한다(도메인은 KLOW 자산 · 소유권 이전 없음 — §18-1a). ⚠️⚠️ 이메일은
   개인 주소가 아니라 **팀 공용 주소**로 — ICANN 규정상 등록자 이메일로 연례 검증 메일이 오고
   기한 내 미응답이면 **도메인이 정지된다**(WHOIS privacy 를 켜도 이 메일은 실제 주소로 온다).
5. `registrations` 가 동기로 `succeeded` 를 주는 비율과 `in_progress` 의 실제 소요 — 폴링 주기의 근거.
6. ⚠️ **`privacy_mode: 'redaction'` 을 거절하는 TLD 가 있는가.** `.us` 처럼 레지스트리가 WHOIS privacy 를
   **금지**하는 TLD 가 있고, 그런 곳에 무조건 true 를 보내면 §7 6단계에서 **4xx 확정 거절 → 환불**로
   떨어져 브랜드는 이유를 모른 채 실패를 본다(§7 6단계). 거절 응답의 모양을 확인하고, 판별이
   불가능하면 **구매 가능 TLD 화이트리스트**를 두는 편이 낫다.
7. ⚠️⚠️ **`auto_renew` 로 실제 갱신이 일어난 뒤 `registrations/{domain}` 의 만료일이 언제 전진하는가.**
   갱신 API 가 없어(위) 이 전진값이 **"갱신이 실제로 됐다"는 유일한 신호**다. 관측 시점(만료일
   당일인지 며칠 전후인지)이 §9-2a 유예창의 근거이므로, 첫 구매 도메인 1개는 **만료까지 살려 두고
   1년 뒤에 이 항목만 다시 측정**한다(§19 배포 6단계와 같은 캘린더에 등록).

### 벤더 계약 (2026-08-25 확인)

- `POST /accounts/{id}/registrar/domain-check` — ≤20개/요청, 레지스트리 직조회.
  `{name, registrable, tier, pricing:{currency, registration_cost, renewal_cost}, reason?}`
- `POST /accounts/{id}/registrar/registrations` — `{domain_name, years?, auto_renew?, privacy_mode?}`.
  ✅ **필드 타입 확정(2026-08-27, 공식 API 문서)**: `domain_name` string · `years` **number**(1~10) ·
  `auto_renew` **boolean**(기본 `false`) · `privacy_mode` **문자열 enum `'off' | 'redaction'`**(기본
  `'redaction'`). ⚠️⚠️ `privacy_mode` 만 불리언이 아니다 — `true` 를 보내면
  `400 value at /privacy_mode is not a string` 으로 **확정 거절**된다(실측으로 전 구매가 막혔다).
  `auto_renew`·`years` 는 지금 값이 맞으니 **같이 문자열로 바꾸지 말 것**. 그 밖에 `contacts` ·
  `contact_extensions`(`.us` nexus 등) · `acknowledgements` 가 선택 필드로 있다.
  **201/202** + `state: in_progress|succeeded|failed|action_required|blocked`.
  ⚠️ **계정 기본 결제수단에 즉시 청구되고 환불이 안 된다.**
  ⚠️ **`auto_renew` 기본이 `false`** — 명시하지 않으면 1년 뒤 도메인이 소멸한다(문서는 false,
  블로그는 true 로 갈려 있어 **반드시 명시 전달**).
- `GET .../registrations/{domain}/registration-status` — ⚠️ **`action_required`·`failed` 에서는
  폴링을 멈추고 사람에게 넘긴다**(문서 명시).
- **갱신 API 없음**(beta). 실제 갱신은 `auto_renew` 로 **만료일에** 일어난다 → §9 리드타임의 근거.
- `renewal_cost ≠ registration_cost` 인 TLD 가 많다(첫해 할인) → **둘 다 스냅샷**한다.

---

# 서버 (klow_server)

## 4. 스키마 — 신규 모델 2 · enum 3

### ⚠️⚠️ `BrandDomainStatus` 는 한 글자도 건드리지 않는다

세 가지 이유로 기존 enum 에 못 얹는다:

1. **행이 존재할 수 없는 시점에 상태가 필요하다.** `BrandDomain` 은 Vercel `addProjectDomain`
   성공 **이후에만** insert 된다(`registerDomain`). 그런데 "카드 청구 성공, 등록 대기"는 그
   도메인이 세상에 존재하기도 전이다.
2. **`decideDomainStatus` 가 표현할 수 없는 값이 된다.** 그건 Vercel 두 응답(`verified` ·
   `misconfigured` · `verification`)의 **순수 함수**이고 반환이 3분기다. 결제·레지스트라 축은
   입력이 아예 다르므로, enum 에만 값을 늘리면 반환 타입과 실제 값의 범위가 갈린다.
3. **읽는 쪽이 넷이다.** `refreshOriginSnapshot`(`status:'active'`) · `resolveHost` ·
   `verifyDue`(`status: { in: ['pending','verifying'] }`) · `cleanupOrphans` 가 전부 이 컬럼을 본다.
   값을 늘리면 **넷 전부가 재검토 대상**이고, 하나라도 놓치면 서빙·CORS 오리진 스냅샷이 샌다.

> ℹ️ 초안에는 근거로 *"`pendingGiveUpWhere` 가 7일 지난 행을 `error` 로 덮는다"* 가 있었으나
> **사실이 아니라 지웠다** — 그 술어는 `{ status: 'pending', createdAt: { lt: … } }` 로
> **`pending` 정확 일치**이고 기준 컬럼도 `updatedAt` 이 아니라 `createdAt` 이라, 신규 enum 값은
> 애초에 걸리지 않는다(`domain-status.ts:42`). **결론(별도 enum)은 그대로 유효하다** — 위 셋이
> 단독으로 지탱하고, 특히 1번은 그것 하나로 충분하다.

이 분리 덕에 `verified-origin` · `resolve-host` · `domain-status` · `domain-host` 스펙이 **0줄
수정**이다. **그것들이 수정돼야 한다면 설계가 샌 것이다.**

```prisma
/// KLOW 가 브랜드 대신 Cloudflare Registrar 에서 직접 구매해 **소유하는** 도메인 1개 = 1행.
/// BrandDomain(Vercel 연결·DNS 검증 축)과 분리한 이유는 수명과 실패 모드가 다르기 때문이다:
/// 이 행은 **카드 청구가 성공한 순간부터** 존재하고(그때 BrandDomain 은 만들 수 없다),
/// 브랜드가 탈퇴해도 **우리가 1년치 원가를 이미 냈으므로** 남아야 한다.
model BrandDomainRegistration {
  id      String @id @default(cuid())
  /// ⚠️⚠️ **nullable + SetNull 이다(기본값 Restrict 를 쓰면 안 된다).** `brands.service.ts:146` 에
  ///    어드민 하드 삭제(`DELETE /admin/brands/:id` → `tx.brand.delete`)가 **실재한다**.
  ///    Restrict 로 두면 도메인을 한 번 산 브랜드는 영영 삭제할 수 없고(FK 위반 500),
  ///    Cascade 로 두면 회계가 증발한다 — 이 모델을 분리한 근거와 정면 충돌이다.
  ///    (탈퇴는 status='withdrawn' 이라 행 삭제가 아니다. 문제는 어드민 하드 삭제 하나뿐이다.)
  brandId String?
  /// brandId 가 null 이 된 뒤에도 어드민 회계 화면이 "누구 것이었나"를 잃지 않게 하는 스냅샷.
  /// host 만으로는 추적이 안 된다.
  brandNameSnapshot String? @db.VarChar(120)
  /// 소문자 punycode apex. 정규화는 modules/brand-domains/domain-host.ts 가 소유한다.
  /// ⚠️ @unique 를 걸지 않는다 — 실패·만료 후 재구매를 영구히 막는다
  ///    (BrandDomain 이 @@unique([brandId, role]) 를 안 건 것과 같은 근거 — Prisma partial unique 미지원).
  /// ⚠️⚠️ 그래서 "브랜드당 진행중 1건" 을 **DB 가 잡아 주지 않는다.** 강제는 §7 3단계의
  ///    `SELECT id FROM "Brand" … FOR UPDATE` **행 잠금**이 한다(§7-1-D).
  ///    `BrandDomain.host @unique` 를 최종 방어선으로 믿으면 안 된다 — 서로 **다른** 호스트를
  ///    동시에 사는 경우를 못 막고, 발화 시점도 Cloudflare 청구가 끝난 뒤다.
  host    String @db.VarChar(253)

  status  BrandDomainRegistrationStatus @default(charging)

  /// Cloudflare 원문 state. ⚠️ 재가공하지 않는다(beta 라 값이 늘 수 있다).
  cfState        String?  @db.VarChar(32)
  /// DNS 주입의 유일한 키.
  cfZoneId       String?  @db.VarChar(64)
  /// 등록 요청이 접수조차 안 된 경우의 재시도 횟수. 3회 소진 시 환불.
  /// ⚠️ 단 우리 계정에서 그 도메인이 한 번이라도 보였다면 환불하지 않고 action_required (§7 흐름 8번).
  submitAttempts Int      @default(0)

  /// 레지스트리 만료일. 정본은 Cloudflare `GET registrar/registrations/{domain}` 의 `expires_at`
  /// (⚠️ `registration-status` 가 **아니다** — 거긴 안 실려 온다. §0 2번 실측).
  expiresAt DateTime?
  /// ⚠️ true = Cloudflare 가 만료일을 안 줘서 paidAt+1년으로 **근사**한 값.
  ///    근사값으로 자동 갱신 청구를 걸면 안 된다 — cron 이 어드민 알림만 남기고 건너뛴다.
  expiresAtIsEstimated Boolean @default(false)
  autoRenew Boolean @default(true)

  /// 연결된 BrandDomain(primary). ⚠️ Cascade 가 아니라 **SetNull** 이다 — 브랜드가 탈퇴해
  ///    BrandDomain 이 사라져도 우리는 여전히 그 도메인을 소유하고 돈을 냈다. Cascade 면 회계가 증발한다.
  brandDomainId String?      @unique
  brandDomain   BrandDomain? @relation(fields: [brandDomainId], references: [id], onDelete: SetNull)

  lastError String?  @db.VarChar(300)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
  brand     Brand?   @relation(fields: [brandId], references: [id], onDelete: SetNull)
  charges   BrandDomainCharge[]

  @@index([brandId])
  @@index([status, updatedAt])     // 등록 폴링 cron 전용
  @@index([autoRenew, expiresAt])  // 갱신 청구 cron 전용
}

/// 도메인 1건에 대한 **돈 한 번**(최초 구매 + 매년 갱신).
/// SubscriptionInvoice 의 형제 — 컬럼 이름·의미를 의도적으로 미러링해 dunning 이 같은 모양이 되게 했다.
model BrandDomainCharge {
  id             String @id @default(cuid())
  registrationId String
  kind   BrandDomainChargeKind   @default(registration)
  status BrandDomainChargeStatus @default(pending)

  /// ⚠️ SubscriptionInvoice.amountKrw 와 같은 기준 — **VAT 포함 실청구액 KRW 정수**.
  amountKrw       Int
  /// 감사·마진 리포트용 스냅샷. 청구 시점 값을 그대로 얼린다. **이 청구의 원가**다
  /// (registration 이면 registration_cost, renewal 이면 renewal_cost).
  costUsdCents    Int
  /// ⚠️ **다음 해 갱신 원가**(같은 domain-check 응답의 renewal_cost). §0 의 "둘 다 스냅샷한다"가
  ///    이 컬럼이다 — 없으면 §9-1 이 브랜드에게 안내한 "2년차 예상가"가 **아무 데도 안 남아**
  ///    갱신 청구 때 "작년에 얼마라고 했었나"를 대조할 수 없다(RENEWAL_PRICE_SPIKE_MAX 는
  ///    직전 *청구액* 대비라 안내값과는 다른 축이다). nullable — 벤더가 안 줄 수도 있다.
  renewalCostUsdCents Int?
  fxRateKrwPerUsd Float
  marginRate      Float
  supplyKrw       Int

  pgProvider    String?
  pgTid         String?  @unique   // ⚠️ 같은 승인이 두 행에 들어가면 회계가 갈린다
  attemptCount  Int      @default(0)
  lastAttemptAt DateTime?
  paidAt        DateTime?
  /// ⚠️ **전액 환불만 지원한다.** SubscriptionInvoice 를 미러하느라 refundedAmountKrw 가 없는데,
  ///    그건 그쪽의 알려진 결함(부분환불이 흔적을 안 남긴다)이다. 여기서는 부분환불이 의미가
  ///    없으므로(도메인 1개 = 1년 = 값 하나) **부분환불 경로를 만들지 않는 것으로 확정**한다.
  ///    어드민 refund 도 cancelAmount 를 받지 않는다(§11).
  refundedAt    DateTime?
  failReason    String?  @db.VarChar(500)
  /// 이 청구가 덮는 등록 기간.
  periodStart   DateTime
  /// ⚠️⚠️ **nullable 이고, 그 null 이 §9-3 의 "갱신 전진 확인 대기" 마커다.**
  ///    갱신은 우리가 부르는 API 가 아니라 Cloudflare `auto_renew` 가 **만료일에** 하므로,
  ///    청구가 성공한 시점에는 새 만료일을 모른다. 여기서 `expiresAt+1년` 을 미리 박으면
  ///    갱신이 실제로 안 됐을 때 **장부에만 1년이 늘어난다**.
  ///    → `kind='renewal' AND status='paid' AND periodEnd IS NULL` = **전진 확인 대기**.
  ///    이 파생 하나로 `renewalConfirmPending` 같은 별도 플래그 컬럼이 필요 없다.
  ///    registration(최초 구매)은 등록 성공 시점에 만료일을 받으므로 그때 바로 채운다.
  periodEnd     DateTime?
  createdAt     DateTime @default(now())
  registration  BrandDomainRegistration @relation(fields: [registrationId], references: [id])

  @@index([registrationId])
  @@index([status])
}

enum BrandDomainRegistrationStatus {
  charging         /// 카드 청구 진행 중. 돈이 아직 안 나갔을 수 있다.
  paid             /// ★ 돈은 받았고 등록 요청 결과가 불확실하다. cron 이 진실을 확인한다.
  registering      /// Cloudflare 접수됨(in_progress). 폴링 대상.
  registered       /// 레지스트리 등록 완료. DNS·Vercel 연결 전.
  active           /// DNS 주입 + Vercel 연결 완료. BrandDomain 이 함께 존재한다.
  released         /// ★ 연결만 해제됨. 도메인은 KLOW 가 계속 보유하지만 BrandDomain 은 없고
                   ///   auto_renew=false 다(§18-1). active 를 재사용하면 그 값의 정의
                   ///   ("BrandDomain 이 함께 존재한다")가 거짓이 되고, 갱신 cron 이
                   ///   "연결된 도메인"과 "버려진 도메인"을 구분하지 못한다.
  action_required  /// Cloudflare 가 사람 개입 요구. ⚠️ 자동 환불 여부는 **원인에 따라 갈린다** — §7-4.
  failed           /// 등록 실패 + 환불 완료.
  expired          /// 갱신 미납 확정 또는 released 도메인의 만료일 경과 → 소멸.
}
enum BrandDomainChargeKind   { registration renewal }
enum BrandDomainChargeStatus { pending paid failed refunded }
```

⚠️⚠️ **기존 두 모델에 역방향 relation 필드를 1줄씩 넣어야 `prisma generate` 가 통과한다.**
Prisma 는 양방향 선언을 요구하므로 위 스니펫만으로는 컴파일되지 않는다. **이름이 곧 계약이다** —
§12 의 `APPLICATION_INCLUDE` 가 `domainRegistrations` 를 이름으로 직접 쓰므로 바꾸면 그쪽이 깨진다:

```prisma
model Brand {
  // …기존 필드…
  domainRegistrations BrandDomainRegistration[]      // ← §12 가 이 이름을 쓴다
}

model BrandDomain {
  // …기존 필드…
  purchaseRegistration BrandDomainRegistration?      // brandDomainId @unique 의 역방향
}
```

⚠️ `BrandDomain` 쪽은 **1:1(옵셔널)** 이다 — `BrandDomainRegistration.brandDomainId` 가 `@unique`
이기 때문이고, 배열로 쓰면 `prisma generate` 가 거절한다. 그리고 이 두 줄은 **컬럼을 만들지 않는다**
(순수 relation 선언) → §4 의 "순수 expand · 롤링 배포 안전" 결론은 그대로다.

**두 모델로 나눈 이유**: 만료일·auto_renew·zone·상태는 **도메인당 1행(영속)**, 원가·판매가·환율·
PG·dunning 은 **연 1행(이력)**. 합치면 갱신 이력이 최신값에 덮이거나 `expiresAt`/`autoRenew` 를 매
행에 중복해야 한다. 어드민 요구("**구매 내역**(복수) · 원가/판매가 · 만료일 · auto_renew · **직전
청구 상태**")가 1:N 을 직접 요구한다.

**마이그레이션**은 **순수 expand**(`CREATE TYPE ×3 + CREATE TABLE ×2`). `BrandDomain` 은 컬럼 하나도
안 바뀌어 뜨거운 경로(`resolveHost` · 오리진 스냅샷 · `verifyDue` · `cleanupOrphans`)의 select 와
쿼리 플랜이 전혀 안 바뀐다 → **롤링 배포 안전 · 백필 없음**(`20260821052240_add_brand_domains` 와
같은 성격).
⚠️ 생성은 `npx prisma migrate dev --name add_brand_domain_purchase` 로만(CLAUDE.md).
interactive 프롬프트가 막히면 사용자에게 직접 실행을 요청한다.

## 5. 가격 커널 — `src/pricing/domain-price.ts` (신규)

CLAUDE.md 규칙 6("가격 계산은 `src/pricing/`")에 따라 **모듈이 아니라 커널**에 둔다.
배럴 `src/pricing/index.ts` 에 `export * from './domain-price'`.

⚠️ **`subscription-price.ts` 의 "형제"라고 부르지 말 것 — 물려받을 패턴이 없다.** 그쪽은 VAT 포함
정액 상수 3개를 들고 있을 뿐이고, **`src/pricing/` 전체에 마진·VAT 계산이 하나도 없다**
(`PAYMENT_FEE_RATE = 0.05` 는 역산용, `VAT_DIVISOR = 1.1` 은 `payment.service.ts:140` 에 산다).
`domain-price.ts` 는 **가격 커널 최초의 `×마진 ×VAT` 계산**이다.

```ts
export const DOMAIN_MARGIN_RATE = 1.3;   // ⚠️ env 오버라이드를 두지 않는다 — 아래 주석 5번
export const DOMAIN_VAT_RATE    = 1.1;
export const DOMAIN_ROUND_UNIT  = 1_000;
/// 환율 오입력 방어대. 이 밖이면 quote 를 만들지 않고 던진다.
export const DOMAIN_FX_MIN = 800;
export const DOMAIN_FX_MAX = 3_000;

export type DomainPriceQuote = {
  costUsdCents: number; fxRateKrwPerUsd: number; marginRate: number;
  supplyKrw: number;   // = round(costUsd × fx × margin)
  amountKrw: number;   // = ceil(supply × 1.1 / 1000) × 1000  ← 최종 청구가(VAT 포함)
};
export function quoteDomainPriceKrw(costUsdCents, fxRateKrwPerUsd, marginRate?): DomainPriceQuote;

/// Cloudflare `pricing.registration_cost` / `renewal_cost` 파서. 문자열("10.44")·숫자를
/// **여기 한 곳에서만** 해석한다. 파싱 실패·0 이하는 던진다 — 0원 청구로 도메인을 무료로
/// 파는 사고를 원천 차단한다.
export function parseRegistrarCostUsdCents(raw: unknown): number;
```

파일 주석에 반드시 박을 것:

1. ⚠️⚠️ **환율은 `resolveFxRate(prisma)`**(정산 정본 = `CurrencyFxRate['KRW'].usdRate`).
   `resolveCurrencyUsdRate`(표시용, **1 폴백**)를 쓰면 **$10 도메인이 10원에 팔린다**.
   `src/pricing/fx.ts` 상단이 이미 *"폴백 의미가 정반대"* 를 경고하고 있으니 그 문장을 재인용할 것.
2. `resolveFxRate` 는 행이 없으면 `FX_RATE_FALLBACK`(1380)을 주는 **비-strict** 함수다 → 청구
   경로에서는 `DOMAIN_FX_MIN/MAX` 범위 가드가 **유일한 안전망**이다. 밖이면
   `503 domain_price_unavailable`.
3. **견적과 청구가 같은 함수를 탄다.** 화면 금액 ≠ 청구 금액이면 분쟁이고, 환불 불가 상품에서는
   회복이 불가능하다.
4. ⚠️ **범위 가드는 오설정만 잡고 노후화는 못 잡는다.** `CurrencyFxRate['KRW']` 행은 **cron 이
   갱신하지 않는 수동 고정값**이다(`fx.ts:13-16` — admin 만 갱신). 몇 달 묵어 실환율과 벌어진 값은
   800~3,000 범위를 태연히 통과하며 **마진만 조용히 깎인다**(스냅샷 1,380 인데 실제가 1,480 이면
   마진 30% 가 약 21% 가 된다). 그래서 (a) `fxRateKrwPerUsd` 를 charge 행에 스냅샷하고
   (b) 어드민 도메인 탭에 **환율 갱신일(`CurrencyFxRate.updatedAt`)을 함께 노출**한다.
5. ⚠️ **마진율에 env 오버라이드를 두지 않는다.** 형제 `resolveSubscriptionPriceKrw` 는 env 를 받되
   `usedFallback`/`rawEnv` 를 돌려주고 **호출부가 반드시 warn 을 찍는다**
   (`subscription.service.ts:91-92`: *"이 warn 을 지우지 말 것 — 의도치 않은 기본가 청구를 운영이
   인지할 유일한 신호"*). 환불 불가 상품에서 **오설정된 마진율은 상수보다 훨씬 나쁘다** — 조용히
   원가 이하로 팔 수 있다. 변경이 코드 리뷰를 거치도록 상수로 못박고, 굳이 env 를 연다면
   `usedFallback` 모양을 **그대로 미러**해 청구 경로에서 warn 을 찍을 것.
   (`marginRate?` 인자는 남긴다 — 스펙이 경계값을 넣기 위한 순수 함수 접점이다.)

## 6. Cloudflare 클라이언트 — 파일 2개 + 순수 헬퍼 1개

### `cloudflare-registrar.client.ts` 확장

추가: `checkDomains(names[≤20])` · `createRegistration` · `getRegistrationStatus` · `setAutoRenew`.

- ⚠️ **파일 상단의 설계 전제 주석을 지우지 말고 갱신한다.** 지금 이렇게 적혀 있다:
  > `POST /registrar/domain-check` 와 `POST /registrar/registrations` 는 이 파일에 존재하지 않는다
  > — 후자는 계정 기본 결제수단에 **즉시 청구되고 환불이 안 된다**. "과금이 가능한 코드 경로를
  > 만들지 않는다"가 이 클라이언트의 설계 전제다. 등록 기능을 붙일 사람은 그 전제를 먼저 다시
  > 검토할 것.

  전제가 바뀐 **사실**과 **무엇으로 대체했는지**(§10 `DOMAIN_PURCHASE_ENABLED` opt-in 게이트 +
  §7-1 의 5가지 규칙)를 그 자리에 쓴다. 지우기만 하면 다음 사람이 안전장치의 존재를 모른다.
- ⚠️⚠️ **같은 전제가 5곳에 흩어져 있다 — 전부 갱신해야 한다.** 상단 주석만 고치면 나머지 넷이
  서로 모순된 채 남는다:

  | # | 위치 | 지금 적힌 것 |
  |---|---|---|
  | 1 | `cloudflare-registrar.client.ts` 상단 블록 | "search 만 부른다 · 과금 가능한 경로를 만들지 않는다" |
  | 2 | 같은 파일 `CloudflareEnvelope` 타입 주석 | "`pricing`·`tier` 를 **일부러** 넣지 않는다 — **가격 미표시가 확정 요구사항**" |
  | 3 | `domain-search.ts` `DomainSuggestion` 주석 | "`pricing` 을 더하면 벤더 가격 스키마에 묶인다" |
  | 4 | `domain-wishes.service.ts` 헤더 | "구매 기능을 붙일 사람이 `domain-check` 를 함께 가져오고 `registrations` 전제를 재검토할 것" |
  | 5 | `.env.example` Cloudflare 블록 | "**가능하면 읽기 전용으로** — write 토큰은 도메인을 등록해 돈을 쓸 수 있다" |

  ⚠️ **2·3 번은 "삭제"가 아니라 "정정"이다.** 가격은 §11 `POST quotes`(`domain-check`)가 전담하고
  **`domain-search` 응답에는 계속 안 싣는다** — `DomainSuggestion = { name }` 과
  `domain-search.spec.ts` 의 "never ships pricing/tier" 단언은 **무변경으로 통과해야 한다**.
  두 주석은 "검색 응답에는 여전히 안 싣는다 · 가격은 quotes 가 낸다"로 고쳐 쓴다.
- `createRegistration` 타임아웃 **30s**(검색은 10s — 사람이 타이핑하며 기다리는 축이지만, 이쪽은
  돈이 걸린 축이다).
- ⚠️ `auto_renew: true` **명시 전달**.
- ⚠️⚠️ `AbortError`·5xx 는 **`CloudflareRegistrationIndeterminateError`** 로 던진다 — §7-1 (A) 를
  타입으로 강제하기 위한 전용 예외다.
- 프리미엄 fee acknowledgement 요구 응답은 **자동 승인하지 않는다** → `action_required`.
  ⚠️ 그 뒤 처리는 §7-4 다(프리미엄은 **아직 과금 전**이라 즉시 환불이 안전하다).
  ⚠️ **fee acknowledgement 요구 필드를 원문 그대로 보존**해 `cfState` 와 별개로 판정에 쓴다 — §7-4 가
  `state` 문자열이 아니라 그 필드로 분기하기 때문이다.

### `cloudflare-dns.client.ts` (신규)

`getZoneIdByName` · `createZone` · `listDnsRecords` · `createDnsRecord` · `updateDnsRecord` ·
`deleteDnsRecord`.

⚠️ **파일을 나누는 이유는 다른 API 표면 + 다른 토큰 스코프**다(Account→Registrar vs Zone→DNS:Edit).
한 파일에 두면 "토큰 하나면 되는 줄" 알고 스코프를 좁혀 조용히 깨진다. env 도 나눈다:
**`CLOUDFLARE_DNS_TOKEN`, registrar 토큰 폴백 금지** — registrar 클라이언트가 `R2_ACCOUNT_ID`
폴백을 거부한 것과 **같은 논리**다.

### `domain-dns.ts` (신규 순수 헬퍼 — 접미사 없는 명사, 규칙 4)

```ts
export const DNS_PROXIED = false as const;   // ★ 스펙이 이 값을 잠근다
export type DesiredDnsRecord = { type: 'A' | 'CNAME'; name: string; content: string };
export function desiredRecordsFor(apex, apexRec, wwwRec): DesiredDnsRecord[];
export function planDnsConvergence(desired, existing): { create; update; remove; skip };
```

- ⚠️⚠️ **`proxied: false`(DNS only) 필수.** true 면 Cloudflare 오렌지 클라우드가 오리진을 감싸
  Vercel `getDomainConfig` 가 `misconfigured: true` 를 **영원히** 반환하고 인증서도 안 나온다.
- 값의 정본은 **`VercelClient.recommendedRecord(domain, config)`** — 이미 rank:1 을 소유한다.
  하드코딩(`76.76.21.21` / `cname.vercel-dns.com`) 금지는 `BrandDomain.recordValue` 스키마 주석에
  이미 있는 규칙(F3)이고 여기서도 같다.
- ⚠️ **`recordValue` 가 빈 문자열이면 주입하지 않는다.** `recommendedRecord` 는 "모른다"를 빈
  문자열로 표현한다(폴백을 옛 값으로 위장하지 않으려고). 그 상태에서 심으면 브랜드 도메인이
  엉뚱한 곳을 가리킨다 → 다음 cron 사이클로 미룬다.
- **멱등**: "생성"이 아니라 **"원하는 상태로 수렴"** 이다. 반복 호출로 레코드가 쌓이면 안 되고,
  등록 직후 zone 에 기본 레코드가 이미 있을 수도 있다.
- ⚠️⚠️ **`remove` 는 "우리가 심은 것"만 대상으로 한다.** `desiredRecordsFor()` 가 관리하는
  **이름·타입 조합**(apex A / `www` CNAME)에 한정하고 그 밖은 절대 건드리지 않는다 — 브랜드가
  그 zone 에 MX·TXT 를 넣어 뒀을 수 있고, **메일을 죽이면 도메인 값보다 비싼 사고**다.
  `desired` 가 빈 배열이면 곧 "연결 해제"이고, 그때 `remove` 가 §18-2 의 정리 경로가 된다.

## 7. 구매 오케스트레이션 — `domain-purchase.service.ts` (신규)

`brand-domains.service.ts`(719줄)에 넣지 않는다. **순서와 보상이 이 파일의 전부**다.

```
[요청 안에서]
0 게이트   DOMAIN_PURCHASE_ENABLED · 구독 active · 서킷 open 아님(§18-3)
           · primary BrandDomain 0개 · 진행중 registration 0건(§2 — 상태 집합은
             ACTIVE_REGISTRATION_STATUSES §12) · 구매 상한 미초과(§18-4)
           ⚠️ 뒤 셋은 여기서 **먼저 걸러 벤더 호출을 아끼는 것**이고, 진짜 판정은
              3단계 락 안의 재검사다(락 밖 검사는 경합 창이 그대로 열려 있다)
1 재확인   domain-check 단건(★ quotes 5분 캐시 우회) → registrable !== true 면 409 domain_unavailable
2 재견적   quoteDomainPriceKrw() → 클라 expectedAmountKrw 대조, 불일치 → 409 domain_price_changed
3 DB      ★★ 트랜잭션: Brand 행 FOR UPDATE → primary BrandDomain 0개 · 진행중 registration 0건을
           **락 안에서 재검사** → Registration(charging) + Charge(pending) insert → 커밋
           (락 구간은 이 세 문장뿐. PG·Cloudflare 왕복은 **반드시 락 밖**이다 — §7-1-D)
4 청구     chargeBilling({ bid, amountKrw, orderId: orderIdFrom(charge.id), goodsName })
           ⚠️⚠️ goodsName 은 **40바이트 상한**(매뉴얼 확인. buyerName 30 · buyerTel 20 ·
           buyerEmail 60 · orderId 64, 전부 **문자 수가 아니라 UTF-8 바이트**다). 호스트가
           최대 253자라 길이가 외부 입력에 달려 있어 **어댑터가 잘라 준다** — 안 자르면
           "긴 도메인을 산 브랜드만 결제가 안 되는" 재현 어려운 실패가 된다.
           ⚠️ goodsName 에 **도메인명을 넣는다**(예: `KLOW 도메인 shop.example.com`) — 카드 명세서에
              그대로 찍히고, 구독료와 구분이 안 되면 그 자체가 문의·이의제기 사유다
           ├ NicepayBillingError → charge=failed / reg=failed → throwAsHttp(400). 돈 안 나감.
           └ 타임아웃·네트워크 → netCancel(orderId) → ★ charge 는 **pending 유지**(failed 아님)
             + lastError + Sentry → 502. cron 이 진실을 확인한다 (§7-1-E)
5 DB      charge=paid(pgTid) / reg=paid        ← ★ "돈은 받았고 등록은 아직" 의 정본 상태
6 등록     createRegistration({ domain_name, years:1, auto_renew:true, privacy_mode:'redaction' })
           ⚠️⚠️ **privacy_mode 는 불리언이 아니라 문자열 enum 이다**('off' | 'redaction').
           ⚠️ **명시 전달한다** — 등록자가 KLOW 라 끄면 우리 회사 연락처가 WHOIS 에
              공개되어 스팸·피싱 표적이 된다. Cloudflare 는 무료 제공이고, 기본값을 믿지 말 것
              (auto_renew 가 기본 false 인 것과 같은 이유 — beta 문서가 갈려 있다)
           ⚠️ years 는 **1 고정**이다. 다년 구매는 지원하지 않는다 — 연 이용료 모델이라 2년을 사면
              브랜드가 1년 뒤 이탈했을 때 미회수 원가가 두 배가 된다
           ⚠️⚠️ **privacy_mode 를 거절하는 TLD 가 있다**(`.us` 등 레지스트리가 WHOIS privacy 금지).
              그 4xx 는 "도메인을 못 산다"가 아니라 **"이 옵션을 못 쓴다"** 인데, 아래 분기가
              무조건 환불로 접으면 브랜드는 살 수 있는 도메인을 이유도 모른 채 못 산다.
              → §0 6번 실측 결과에 따라 (a) 구매 가능 TLD 화이트리스트로 **애초에 못 고르게** 하거나
              (b) privacy 거절이 판별 가능하면 그 TLD 만 `privacy_mode:'off'` 로 1회 재시도한다.
              ⚠️ (b) 를 택하면 **재시도 전에 우리 계정 등록 여부를 먼저 확인**할 것 — 첫 요청이
                 이미 등록을 만들었다면 재시도가 두 번째 과금이다(§7-1 A 와 같은 축)
           ├ 201/202 → reg=registering (cfState 저장)
           ├ 4xx 확정 거절 → cancelPayment(tid) → charge=refunded / reg=failed → 400
           └ 타임아웃·5xx → ★★ 취소하지 않는다. reg=paid 로 두고 cron 이 진실을 조회
7 응답     { registration }   (화면은 폴링)

[cron 이 하는 것 — §8]
8  reg=paid        → registration-status 조회
                     ├ 존재 → registering 으로 승격 (6번 타임아웃의 회복 경로)
                     └ 404  → 접수 자체가 안 됐다 →
                        ★ submitAttempts++ **후 createRegistration 을 다시 부른다**(6단계와 같은 인자)
                        ⚠️⚠️ **재호출이 이 분기의 본체다.** 초안은 `submitAttempts++ , 3회 소진 시 환불`
                           만 적어 두었는데 그대로 구현하면 **카운터만 세 번 올리고 환불**한다 —
                           등록은 한 번도 재시도되지 않고, `submitAttempts` 주석(§4)이 말하는
                           "접수조차 안 된 경우의 재시도"가 코드에 존재하지 않게 된다
                        └ 3회 소진 → cancelPayment → failed
                        ⚠️ 단 **그 도메인이 우리 계정에 이미 등록돼 있으면 절대 환불하지 않는다**
                           (§7-1 A 의 연장 — 환불했는데 등록이 살아 있으면 순손실 2배).
                           그때는 action_required 로 사람에게 넘긴다
                        ⚠️⚠️ **"계정에 보인다" 를 그대로 판정에 쓰면 안 된다 — §7-1-F 를 볼 것.**
                           다른 브랜드가 먼저 산 도메인도 우리 계정에 보이므로, 그 규칙을 글자대로
                           적용하면 **손실 0 인 건이 자동 환불되지 못하고** 사람 큐에 쌓인다.
                           판정은 "우리 계정에 있는가"가 아니라 **"이 registration 행의 요청으로
                           생긴 등록인가"**(우리 DB 의 소유 행 대조)여야 한다
9  reg=registering → succeeded → registered(+expiresAt) / failed → 환불 / action_required|blocked → 정지
10 reg=registered  → §7-3 connectDomain
11 charge=pending  → 4단계 netCancel 불확정 건 **+ 3~4단계 사이에 죽은 건**.
                     ★ 기준은 **COALESCE(lastAttemptAt, createdAt) < now−10분** → NicePay 재조회
                     ├ 승인됨   → charge=paid(pgTid) + reg=paid 로 승격 (정상 등록 경로에 합류)
                     ├ 미승인   → charge=failed + reg=failed
                     └ 금액 불일치 → ★ 자동 확정하지 않는다. action_required (payment.service 의 mismatch 선례)
                     ⚠️⚠️ **`lastAttemptAt` 은 null 일 수 있고, SQL 에서 `null < x` 는 false 다.**
                        charge(pending) 는 3단계에서 insert 되고 청구는 4단계라, 그 사이에 프로세스가
                        죽으면(롤링 배포·크래시) `lastAttemptAt` 이 채워지지 않는다. 조건을 그대로
                        쓰면 **이 cron 이 그 행을 영원히 못 집고** registration 은 `charging` 에
                        갇히며, §7 0단계 게이트("진행중 registration 0건")가 그 브랜드의
                        **재구매를 영구 차단**한다. COALESCE 가 이 흐름의 유일한 방어다
                     ℹ️ 흐름 8~10 은 registration 축(paid/registering/registered)만 집는다 —
                        **`reg=charging` 을 직접 다루는 칸은 없고**, 오직 이 11번이 charge 축으로
                        덮는다. 그래서 위 COALESCE 가 빠지면 `charging` 을 구제할 경로가 0이 된다
```

### 7-1. 반드시 지킬 5가지

| # | 규칙 | 안 지키면 |
|---|---|---|
| **A** | ⚠️⚠️ **타임아웃 ≠ 실패.** `registrations` 타임아웃·5xx 에 `cancelPayment` 를 **부르지 않는다** | Cloudflare 는 등록했는데(환불 불가) 브랜드 돈은 돌려줌 → **순손실 2배**. 전용 예외 타입 `CloudflareRegistrationIndeterminateError` 로 이 분기를 타입으로 강제 |
| **B** | charge 행을 청구 **전에** 만들고 `orderId = orderIdFrom(charge.id)` | 구독 정기청구가 `invoice.id` 를 seed 로 쓰는 것과 같은 근거 — 재시도가 같은 orderId 를 못 쓰면 **이중 승인** |
| **B'** | ⚠️⚠️ **취소(환불) 축은 정반대다 — seed 에 난수를 섞어 매번 다른 orderId 를 쓴다** | 매뉴얼이 *"결제된 orderId 로는 재호출이 불가"* 라고 못박아, 취소에 같은 주문번호를 재사용하면 **첫 시도가 실패한 뒤 재시도가 영구히 막힌다**(= 브랜드가 돈을 못 돌려받는다). 취소의 이중 실행은 NicePay 가 tid 상태로 이미 막으므로 멱등이 필요 없다. ⚠️ `Date.now()` 로는 부족하다 — 같은 밀리초 안의 두 번째 시도가 충돌한다(스펙이 실제로 잡았다) |
| **C** | `pgTid @unique` (SubscriptionInvoice 미러) | 같은 승인이 두 행에 들어가면 회계가 갈린다 |
| **D** | ⚠️⚠️ 동시성은 **`SELECT id FROM "Brand" WHERE id = $1 FOR UPDATE` 행 잠금**으로 막는다. `@Throttle({limit:3, ttl:60_000})` 은 보조일 뿐 **직렬화를 하지 않는다** | 연타 = **환불 불가 도메인 2개 구매.** 아래 §7-1-D |
| **E** | ⚠️⚠️ **`netCancel` 은 실패해도 throw 하지 않는다**(`nicepay-billing.adapter.ts:506` — `logger.warn` 만 남기고 리턴). 그 분기의 charge 는 `failed` 가 아니라 **`pending` 유지** | netCancel 이 실패하면 **카드는 승인된 채 장부만 실패**가 되고 아무도 모른다. 구독은 다음날 재청구가 자연 복구책이지만 **도메인은 일회성이라 복구 경로가 없다.** 아래 §7-1-E |
| **F** | ⚠️⚠️ "**우리 계정에 그 도메인이 보이는가**" 를 환불 금지 판정에 **그대로 쓰지 않는다.** 판정 단위는 계정이 아니라 **이 registration 행** 이다 | Brand 행 잠금은 **host 단위 직렬화를 하지 않는다** — 다른 브랜드가 먼저 산 도메인도 계정에 보이므로, 손실 0 인 건이 자동 환불되지 못하고 사람 큐에 쌓인다. 아래 §7-1-F |

#### 7-1-D. 왜 `@Throttle` 로는 못 막는가

- `@Throttle` 은 **속도 제한**이지 상호배제가 아니다. 1분 3회 안에서 **동시 인플라이트 2건**은 통과한다.
- `BrandDomainRegistration.host` 에 `@unique` 를 **일부러 안 걸었다**(실패·만료 후 재구매를 막지
  않으려고 — 옳은 판단이다). 그래서 DB 가 중복을 안 잡는다.
- "최종 방어선 `BrandDomain.host @unique`" 는 **두 가지를 못 한다**: ① 서로 **다른** 호스트 2개를
  동시에 사는 경우를 전혀 막지 못하고 ② 발화 시점이 §7-3 connect 라 **Cloudflare 청구가 이미 끝난 뒤**다.

**선례가 이 레포에 둘 있다** — `seeding.service.ts:1055`(정원 게이트, `SeedingLink` 행 잠금) ·
`brand-auth.service.ts:717`(`BrandUser` 행 잠금). CLAUDE.md 가 수동 SQL 마이그레이션을 금지하므로
partial unique index(`WHERE status IN (…)`)는 애초에 선택지가 아니다 — **행 잠금이 정답**이다.

⚠️ 락 구간은 §7 3단계의 세 문장(잠금 → 재검사 → insert)뿐이다. **PG·Cloudflare 왕복을 락 안에
넣으면** 동시 요청이 수십 초씩 직렬 대기하고 Prisma 기본 트랜잭션 타임아웃(5초)에 걸린다
(시딩 `SEEDING_TX_OPTS` 가 같은 이유로 존재하지만, 여기서는 **락을 짧게 하는 쪽**이 맞다).

#### 7-1-E. netCancel 불확정 건의 회수 경로

`payment-reconcile.cron.ts` 가 존재하는 이유가 정확히 이 병(`pending` 고착)이다. 같은 모양을 쓴다 —
등록 폴링 cron 이 `charge.status='pending' AND lastAttemptAt < now−10분` 행을 함께 집어(§7 흐름 11번)
NicePay 를 조회하고, 승인돼 있으면 `charge=paid` + `reg=paid` 로 **정상 등록 경로에 합류**시킨다.

⚠️⚠️ **"거래가 조회된다" 를 "승인됐다" 로 읽으면 안 된다.** 이 분기는 바로 앞에서 `netCancel` 을
불렀으므로, 되조회에서 **가장 흔하게 만나는 상태가 오히려 취소된 거래**다. `status` 를 안 보고
확정하면 브랜드는 한 푼도 안 냈는데 우리는 환불 불가능한 도메인 원가를 지불한다(초안 구현이
정확히 그랬다 — 이 문장의 "승인돼 있으면" 을 느슨하게 읽은 결과다). 판정 정본은
`classifyNicepayPaymentStatus`(subscription 어댑터)이고 **`approved` 일 때만** 확정한다:
`void`(취소·만료·거절)는 돈이 안 나갔으므로 `failed` 확정, **모르는 값과 부분취소는
`action_required`**(fail-closed — 모르는 값을 `void` 로 폴백하면 NicePay 가 상태를 추가하는 날
승인된 결제를 미승인으로 확정한다).

⚠️ **금액 불일치는 자동 확정하지 않는다** — 사람이 판단한다. ⚠️⚠️ **금액을 못 읽은 것(`null`)도
같은 칸이다** — "확인 불가"를 "확인 통과"로 흘려보내면 금액 검증이 통째로 사라진다
(Eximbay 의 `parseFloat("132,000")===132` 선례).

⚠️⚠️ **그 "재조회"를 할 메서드가 지금 없다.** `NicepayBillingAdapter` 의 public 표면은
`registerBillingKey` · `chargeBilling` · `resolveInterestFree` · `listInterestFree` ·
`deleteBillingKey` · `cancelPayment` · `netCancel` **일곱 개뿐이고 거래 조회가 하나도 없다**
(구독은 조회가 필요 없었다 — 다음날 재청구가 자연 복구책이라서다). **어댑터에 조회를 추가해야
한다**(§10 표):

```ts
/// 주문번호로 거래 조회. 타임아웃 건은 tid 를 모르므로 orderId 로만 찾을 수 있다.
/// 없으면 null(= 승인 안 됨). 기존 private getJson 을 그대로 쓴다.
async findPaymentByOrderId(orderId: string): Promise<{ tid; amountKrw; status } | null>
```

⚠️ **`tid` 로 조회하는 메서드로 대체할 수 없다** — 이 분기는 애초에 `chargeBilling` 응답을 못 받아
`tid` 가 없는 상황이다. **`orderId` 조회가 유일한 경로**이고, `orderIdFrom(charge.id)` 가 결정적
(deterministic)이라 그게 성립한다(§7-1 B 가 여기서 두 번째로 값을 한다).
⚠️ Eximbay `payment-reconcile` 이 `key_field='order_id'` 를 쓴 것과 **같은 이유·같은 모양**이다 —
그쪽 주석을 참고하되 **PG 가 다르므로 코드를 재사용하지는 않는다.**

#### 7-1-F. 같은 host 를 두 브랜드가 동시에 사면 fail-closed 규칙이 **거꾸로 작동한다**

§7-1-D 의 락은 **`Brand` 행 단위**라 브랜드가 다르면 직렬화가 전혀 없고,
`BrandDomainRegistration.host` 에는 §4 가 **일부러 `@unique` 를 안 걸었다**(실패·만료 후 재구매를
막지 않으려고). 그래서 두 브랜드가 같은 `shop.example.com` 을 동시에 살 수 있다:

```
브랜드 A: domain-check ok → 청구 → registrations 성공
브랜드 B: domain-check ok(같은 순간) → 청구 → registrations 거절(이미 등록됨)
```

B 는 **Cloudflare 가 과금하지 않은** 건이라 §7-2 기준으로 **즉시 전액 환불이 정답**이다. 그런데
§7 흐름 8·§7-4 의 규칙을 글자대로 적용하면 그 순간 **우리 계정에 그 도메인이 보인다**(A 것이다)
→ "보이면 환불하지 않는다" 에 걸려 **자동 환불이 막히고 `action_required` 로 사람에게 넘어간다.**
fail-closed 가 지키려던 것(순손실 2배)과 무관한 건이 사람 큐에 쌓이는 것이고, B 브랜드는 돈이
묶인 채 기다린다.

**판정을 계정 축에서 registration 축으로 좁힌다** — "우리 계정에 있는가" 가 아니라
**"이 registration 행의 요청이 만든 등록인가"**:

- 우리 DB 에 **같은 host 로 이미 `registered`/`active` 인 다른 registration 행이 있으면** → 그건
  남의 것이므로 **환불 대상**(손실 0).
- 그런 행이 없는데 계정에는 보인다 → **우리 것일 수 있다** → 종전대로 fail-closed(환불 금지).
- ⚠️ 이 순서를 뒤집지 말 것. "계정에 보임" 을 먼저 보면 위 첫 칸이 영원히 도달하지 않는다.

⚠️ 같은 상황이 §7-3 b 에서 `domain_taken`(Vercel/`BrandDomain.host @unique`)으로도 나타난다 —
그쪽도 **B 의 등록이 애초에 없었으므로 환불**이고, `registered` 유지 재시도(구독 끊김 케이스)와는
다른 분기다. 두 `domain_taken` 을 한 칸에 묶지 말 것.

ℹ️ host 단위 advisory lock(`pg_advisory_xact_lock(hashtext(host))`)으로 애초에 직렬화하는 선택지도
있으나, **채택하지 않는다** — 락 두 개(Brand + host)를 서로 다른 순서로 잡는 코드가 하나라도
생기면 데드락이고, 위 판정 하나로 손실이 0 이 되기 때문이다. 채택한다면 **획득 순서를 문서에
못박을 것**.

### 7-2. 환불 불가의 **주체**를 혼동하지 말 것

- **Cloudflare → 우리**: 환불 불가. 등록이 `succeeded` 면 그 돈은 나갔다.
- **우리 → 브랜드**: NicePay `cancelPayment` 로 언제든 취소 가능.

그래서 6번 4xx / 폴링 `failed` 는 **Cloudflare 가 아직 과금하지 않은** 케이스라 손실 0이고,
`action_required` 는 **원인에 따라 갈린다** — 프리미엄·API 미지원은 과금 전이라 즉시 환불, 그 밖은
손실 가능성이 있어 자동 환불을 막는다. 판정표는 **§7-4** 다.

⚠️ 브랜드 UI 의 "환불 불가" 고지는 **등록 성공 후**에 대한 것이다. 서버가
`agreedNonRefundable: true` 를 받지 않으면 400(전자상거래법).

### 7-3. `connectDomain(registration)` — 등록 완료 후 연결 (멱등)

```
a. zone 확보: cfZoneId ?? getZoneIdByName(host) ?? createZone(host)   → registration.cfZoneId 저장
b. BrandDomainsService.attachPurchasedDomain(brandId, host)
     내부는 기존 createForBrand 경로 재사용 → 여기서 recordType/recordValue 가 확정된다
     ├ ok:false, reason='subscription_required' → ★ registered 유지 + 재시도 (아래 ⚠️⚠️)
     └ ok:true → c
c. dns 수렴(zoneId, { type, name, content: recordValue, proxied: false })
     ⚠️ recordValue 가 '' 면 이번 사이클은 건너뛴다 — 그리고 **다음 사이클엔 attach 가 돌려준 값이
        아니라 BrandDomain 행을 다시 읽는다**(아래 ⚠️)
d. apex 면 www 페어도 같은 방식
e. refreshOne → active → registration.active
```

⚠️ **b 가 c 보다 먼저다** — 무슨 레코드를 꽂을지는 Vercel 응답(`recommendedRecord`)이 알려준다.

⚠️⚠️ **b 가 403 이면 환불하지 않는다.** `createForBrand` 는 `assertSubscribed`
(`brand-domains.service.ts:683`)를 타므로, 구매(§7 4단계)와 연결(cron 경유라 수 분~수 시간 뒤) 사이에
구독이 `past_due` 로 떨어지면 **403 `subscription_required`** 가 난다. 그때 `failed`(환불)로 접으면
**우리는 1년치 원가를 냈는데 도메인이 아무 데도 안 붙은 채 버려진다.** `registered` 를 유지하고 계속
재시도하며(도메인은 이미 우리 것이다) 어드민에 **"연결 대기"** 로 노출한다 — 구독이 복구되는 순간
다음 사이클에 자동으로 붙는다.

⚠️ **다만 무한 2분 폴링으로 두면 안 된다.** 구독이 영영 안 돌아오면 그 행이 **1년 내내** 2분마다
Vercel 을 친다. `registered` 재시도는 **`lastError` 갱신 + 백오프**(2분 → 실패가 쌓이면 1시간)로
누르고, **7일 넘게 `registered` 면 어드민 SMS 로 한 번 올린다**(그 뒤엔 조용히 1시간 간격 유지).
⚠️ 이건 `submitAttempts` 와 **다른 축**이라 그 카운터를 재사용하지 말 것 — 그쪽은 "환불까지 3회"라
여기에 쓰면 **연결이 3번 실패했다고 도메인을 환불**해 버린다.

⚠️ **빈 `recordValue` 를 채우는 건 `refreshOne` 이다.** `recommendedRecord` 는 rank:1 권장값이 없으면
의도적으로 **빈 문자열**을 돌려주고(`vercel.client.ts:217-238`), `registerPair` 실패 행도
`status='error'` + `recordValue: ''` 로 남는다(`brand-domains.service.ts:391`). 그 값을 나중에
채우는 유일한 코드가 `refreshOne`(`:582` — `:609` 에서 `recommendedRecord` 재계산)이고, 그건
**기존 `brand-domain-verify` cron 이 5분마다** `pending`/`verifying` 행에 돌린다. 따라서 등록 cron 은
attach 시점에 받은 DTO 를 캐싱하지 말고 **매 사이클 `BrandDomain` 행을 다시 조회**해야 한다.

⚠️ **`createForBrand` 를 개명하지 않는다.** 그 함수가 하는 일(구독 재확인 · `domain_taken` 선검사 ·
Vercel 추가 → insert → 실패 시 보상 제거 · apex 판정 → `registerPair` · `refreshOriginSnapshot`)이
구매 경로에 100% 필요하고, **`domain-pairing.spec.ts` 가 그 이름을 직접 부른다** — 그 스펙이
"서브도메인 → apex 자동 등록 금지"(F28)를 잠그는 유일한 장치다. 개명은 회귀 위험 대비 얻는 게 0.
cron 이 부를 얇은 진입점만 추가한다:

```ts
/// 구매 완료 도메인을 Vercel 에 붙인다. createForBrand 와 같은 경로를 타되,
/// 호출자가 브랜드가 아니라 cron 이라 예외가 아니라 결과 객체를 돌려준다.
async attachPurchasedDomain(brandId, apexHost): Promise<{ok:true; …} | {ok:false; reason:string}>
```

### 7-4. 자동으로 못 끝내는 건 — 즉시 환불 + 직접 구매 안내

⚠️⚠️ **이 절은 §7-1 A(자동 환불 금지)와 충돌하는 것처럼 보이지만 아니다. 두 상황이 다르다.**
가르는 기준은 하나 — **Cloudflare 가 우리에게 이미 과금했는가**.

| 상황 | Cloudflare 과금 | 처리 |
|---|---|---|
| **프리미엄 fee acknowledgement 요구** | **아직 안 됨**(그 승인이 곧 과금 트리거다) | ★ **즉시 환불** + "이 도메인은 직접 구매 후 어드민에 연결 요청" 안내. 손실 0 |
| `reason: extension_not_supported_via_api` 등 **API 미지원 TLD** | 안 됨(요청이 거절됐다) | ★ 즉시 환불 + 같은 안내. 손실 0 |
| 그 밖의 `action_required` / `blocked` | **알 수 없다** | ⚠️ **자동 환불 금지.** 어드민이 Cloudflare 계정에서 그 도메인의 실재를 눈으로 확인한 뒤에만 환불한다(§7 흐름 8번과 같은 규칙 — **계정에 보이면 환불하지 않는다**) |

⚠️⚠️ **셋째 칸의 "계정에서 눈으로 확인" 은 §7-1-F 의 좁힌 판정을 먼저 적용한 뒤**다 — 우리 DB 에
같은 host 로 다른 브랜드의 `registered`/`active` 행이 있으면 그 도메인은 **남의 것이므로 손실 0**,
사람 확인 없이 환불한다. 그 선검사를 빼면 동시 구매 경합이 전부 이 칸으로 쏟아진다.

⚠️ **`cfState` 원문만 보고 분기하지 말 것.** 프리미엄 판정은 **응답의 fee acknowledgement 요구
필드**로 하고, 그게 없으면 무조건 아래 칸(사람 판단)으로 떨어뜨린다 — beta API 라 `state` 값이
늘 수 있고, **모르는 값을 "환불해도 되는 쪽"으로 폴백하면 순손실 2배가 난다.** fail-closed 다.

⚠️ 안내 문구는 "직접 구매하시면 어드민이 연결해 드립니다"까지 가야 한다 — §11 에서 브랜드
화면의 호스트 직접 입력을 없앴으므로, **브랜드가 스스로 붙일 방법이 없다.**

## 8. cron — 신규 2개, 파일 1개

`src/modules/brand-domains/brand-domain-registrations.cron.ts`.
규칙 5는 "`@Cron` 은 `*.cron.ts` 파일에"이지 "파일당 하나"가 아니다.

```ts
@Cron('*/2 * * * *', { timeZone: 'Asia/Seoul', name: 'brand-domain-registration' })
// paid → registering → registered → active (§7 흐름 8~10).
// ⚠️ **charge=pending 보정(§7 흐름 11 · §7-1-E)도 이 cron 이 맡는다** — netCancel 불확정 건을
//    NicePay 재조회로 확정한다. 별도 cron 으로 빼지 않는 이유: 같은 registration 행을 만지므로
//    재진입 가드를 공유해야 하고, 보정 결과가 곧바로 8번(등록 접수) 입력이 된다.
// 재진입 가드 running(기존 cron 선례).
// kill switch: BRAND_DOMAIN_REGISTRATION_CRON_ENABLED === 'false' 일 때만 off (기존 관례)

@Cron('30 0 * * *', { timeZone: 'Asia/Seoul', name: 'brand-domain-renewal' })
// 갱신 청구 + dunning + 만료일 전진 확인(§9-3).
// ⚠️ 00:00 의 brand-subscription-billing 과 30분 띄운다(NicePay 동시 부하).
// ⚠️⚠️ **전용 kill switch 를 두지 않는다 — 게이트는 DOMAIN_PURCHASE_ENABLED 하나다**(§11).
//    초안은 "돈 나가는 cron 은 opt-in" 이라며 BRAND_DOMAIN_RENEWAL_CRON_ENABLED 를 반대
//    폴라리티로 뒀으나, ① 그건 레포 관례가 아니고(cron 9개 중 switch 3개, 정작 돈이 나가는
//    brand-subscription-billing 에는 없다) ② **위험을 줄이는 게 아니라 옮긴다** — 갱신은
//    첫 구매 후 11개월간 due 행이 0이라 켜 두어도 무해한 반면, "1년 뒤에 켠다"를 사람 기억에
//    맡기면 잊는 순간 도메인이 만료된다. 자세한 논거는 §11 env 절.
```

⚠️ kill switch 는 `process.env` 가 아니라 **`ConfigService`(`this.config.get(...)`)** 로 읽는다 —
기존 `brand-domains.cron.ts:31` 과 같은 관례이고, 그래야 스펙이 env 를 주입할 수 있다.

### 기존 cron 에 얹지 않는 이유

| 후보 | 기각 사유 |
|---|---|
| `brand-domain-verify` (5분) | 그 cron 은 **Vercel 만 태우고 돈을 만지지 않는다.** 결제 재시도·환불을 얹으면 재진입 가드 하나가 두 종류의 부작용을 덮고, `BRAND_DOMAIN_CRON_ENABLED=false` 를 내리는 순간 **미완료 결제 복구까지 멈춘다.** 사고 시 한쪽만 끌 수 있어야 한다 |
| `brand-subscription-billing` (일 1회) | 등록 폴링은 **분 단위**여야 한다(브랜드가 화면에서 기다린다). 게다가 `SubscriptionModule → BrandDomainsModule` **순환**이 생긴다 |

### ⚠️ `test/app.e2e-spec.ts` — cron 9개 → **11개**

⚠️ **두 번에 나눠 는다**: PR C 에서 `brand-domain-registration` 이 붙어 **9 → 10**(✅ 반영됨),
PR E 에서 `brand-domain-renewal` 이 붙어 **10 → 11**. E 를 할 때 제목 문자열도 같이 고칠 것.

**테스트 제목 문자열(`'cron N개가 …'`)과 `expect` 배열을 둘 다** 고친다(제목만 두면 다음 사람이
헷갈린다). 알파벳 정렬이므로 `registration` < `renewal` < `verify`:

```ts
expect(registered).toEqual([
  'brand-domain-registration',   // ← 신규
  'brand-domain-renewal',        // ← 신규
  'brand-domain-verify',
  'brand-subscription-billing',
  'brand-withdrawal-process-due',
  'currency-rate-refresh',
  'efs-shipment-retry',
  'efs-tracking-refresh',
  'instagram-token-refresh',
  'payment-reconcile',
  'storefront-visitor-day-prune',
]);
```

## 9. 갱신

- **`RENEWAL_LEAD_DAYS = 30`.** ⚠️⚠️ **줄이면 안 된다.** 근거는 *"dunning 0/1/3/7 = 최대 11일 +
  여유 19일"* 이다. Cloudflare beta 에 갱신 API 가 없어 실제 갱신은 `auto_renew` 로 **만료일에**
  일어나므로, 만료 19일 전에 결론이 나야 `setAutoRenew(false)` 로 **우리 카드가 먼저 긁히는 것을**
  막을 수 있다. 이 문장을 상수 주석에 그대로 박을 것.
- 갱신가는 청구 시점 `domain-check` 재조회 → `renewal_cost` + **그날의** `resolveFxRate` 로 재계산
  (가격 인상·환율 변동 자동 반영).
- ⚠️ **직전 청구 대비 `RENEWAL_PRICE_SPIKE_MAX`(2배) 초과면 청구하지 않고 `action_required`** +
  어드민 알림(레지스트리 프리미엄 갱신가 폭등 방어).
- ⚠️ `expiresAtIsEstimated = true` 인 행은 **자동 청구하지 않는다**(근사 만료일로 돈을 받을 수 없다).
  ⚠️⚠️ **그런데 "어드민 알림만" 으로 끝내면 안 된다 — 그건 §18-1a 와 똑같은 사고로 이어진다.**
  청구를 안 해도 **Cloudflare `auto_renew` 는 여전히 `true`** 이므로 만료일이 오면 **브랜드에겐 안
  받고 우리 카드만 긁힌다.** 그래서 이 행은 **두 단계**다:
  ① 만료 `RENEWAL_LEAD_DAYS`(30) 전 → `action_required` + 어드민 알림(사람이 실제 만료일을
     Cloudflare 대시보드에서 확인해 `expiresAt` 을 채우면 정상 갱신 흐름으로 합류한다)
  ② ⚠️ **만료 7일 전까지 사람이 안 고치면 `setAutoRenew(false)`** — 근사값이라도 그 시점엔
     "곧 만료"가 확실하고, **모르는 채로 우리 카드가 긁히는 것보다 도메인을 잃는 편이 낫다**
     (되돌릴 수 있다: 사람이 늦게라도 고치면 `setAutoRenew(true)` 로 복구).
  ⚠️ ②의 7일은 `RENEWAL_NOTICE_LEAD_DAYS − RENEWAL_LEAD_DAYS` 와 **우연히 같은 7이지만 다른
  축**이다. 상수를 공유하지 말 것(`ESTIMATED_GIVE_UP_DAYS = 7`).
- dunning 실패 확정(`retryGap(attemptCount) === null`) → `setAutoRenew(false)` + `expired` 예약.
  ⚠️ **`BrandDomain` 을 즉시 지우지 않는다** — 만료일까지는 정상 서빙된다. 만료 후 정리는
  `cleanupOrphans` 가 아니라 이 cron 이 `expiresAt < now` 로 처리한다.
  ⚠️⚠️ **그 정리에 `removeForBrand(brandId, id)` 를 쓰지 말 것.** 두 가지가 안 맞는다 —
  ① 그 함수는 `findFirst({id, brandId})` 로 **브랜드 소유를 검증**하는 사용자 경로이고
  ② `registration.brandId` 는 이제 **nullable** 이라(§4) 어드민이 브랜드를 지운 뒤엔 null 이다.
  cron 은 **`registration.brandDomainId` 로 직접** 지우는 별도 경로를 쓴다(pair 삭제·Vercel 제거·
  `refreshOriginSnapshot` 은 `removeForBrand` 내부 로직을 추출해 공유). `released` 행도 만료일이
  지나면 같은 경로로 zone 까지 정리한다(§18-2 c).
  ⚠️⚠️ **그 `expiresAt < now` 정리는 `autoRenew=false` 인 행에만 걸어야 한다 — §9-3 을 읽지 않고
  구현하면 정상 갱신된 도메인을 이 줄이 죽인다.**

### 9-1. 갱신가 사전 고지 — `RENEWAL_NOTICE_LEAD_DAYS = 37`

⚠️⚠️ **`RENEWAL_LEAD_DAYS`(30)를 고지에 재사용하면 안 된다 — 그날이 첫 청구일이다.** 그대로 쓰면
"사전 고지"가 청구와 **같은 날**에 나가 고지가 아니게 된다. 그래서 상수를 하나 더 둔다:
**만료 37일 전 = 청구 7일 전**에 알림톡 1회(정기결제 사전 고지 관행이 결제 7일 전이다).
⚠️ 두 상수의 **차(7일)가 고지 리드타임**이라는 사실을 주석에 박을 것 — `RENEWAL_LEAD_DAYS` 를
나중에 손대는 사람이 이쪽도 같이 움직여야 함을 알아야 한다.

**첫해 할인 TLD 대응** — `.shop` 류는 `renewal_cost` 가 `registration_cost` 의 2~3배다. 그래서:

- 구매 화면(§14 `PurchaseDialog`)에 **"1년차 ₩X · 2년차부터 약 ₩Y(환율·레지스트리 가격에 따라
  변동)"** 를 **병기**한다. ⚠️ 근사치임을 반드시 함께 쓴다 — 1년 뒤 환율·원가를 지금 확정할 수 없고,
  확정한 것처럼 보이면 그 자체가 분쟁거리다.
- 그 값의 출처는 §11 `quotes` 응답이다. `domain-check` 가 `registration_cost` 와 `renewal_cost` 를
  **한 응답에 함께** 주므로 **벤더 호출이 늘지 않는다**. `quoteDomainPriceKrw()` 를 두 번 태워
  `amountKrw`(1년차)와 `renewalAmountKrw`(추정)를 같이 내린다.
- ⚠️ **안내한 2년차 예상가를 남기려면 컬럼이 하나 더 필요하다** — `costUsdCents` 는 *그 청구의*
  원가(1년차면 `registration_cost`)라 2년차 값이 아니다. 그래서 §4 에 **`renewalCostUsdCents`** 를
  뒀다. 이게 없으면 갱신 청구 때 "작년에 얼마라고 안내했나"를 대조할 방법이 없다
  (`RENEWAL_PRICE_SPIKE_MAX` 는 **직전 청구액** 대비라 안내값과는 다른 축이다).

### 9-2. 브랜드 알림 4종 — 알림톡 정본 · SMS 폴백

지금 **구독은 브랜드에게 아무 알림도 보내지 않는다**(`subscription/` 에 `EmailService`·`SmsService`
참조 0건). 도메인은 **자동갱신 + 환불 불가**라 같은 방식을 따르면 안 된다.

| # | 계기 | 내용 |
|---|---|---|
| 1 | 구매 완료(`registration.active`) | 연결된 호스트 · 만료일 · **자동갱신 예정 금액** |
| 2 | 갱신 사전 고지(만료 37일 전, §9-1) | 갱신 예정일 · **금액** · 해지하려면 어디로 |
| 3 | 갱신 결제 실패(dunning 각 시도) | 재시도 일정 · 카드 변경 링크 · **미납 확정 시 도메인이 만료된다**는 경고 |
| 4 | 수동 대응 필요(`action_required` · §7-4 환불) | 무슨 일이 있었는지 + 다음 행동 |

⚠️⚠️ **알림톡은 템플릿마다 사전 승인이 필요하다.** `KakaoService`(`modules/web-auth/kakao.service.ts`)
는 지금 **템플릿 id 를 env 한 개**(`SOLAPI_KAKAO_TEMPLATE_ORDER_PAID`)로 들고 있어, 위 4종은
**승인 템플릿 4개 + env 4개**가 새로 필요하다. 그리고 그 파일 주석이 밝히듯 **카카오 채널 심사·
발신프로필·템플릿 승인이 하나라도 안 끝나면 실발송 없이 콘솔 로그로 떨어진다.**

→ 그래서 **정본은 알림톡, 폴백은 SMS** 다. `KakaoService.ready` 가 false 이거나 발송이 실패하면
**`SmsService.sendText` 로 같은 내용을 보낸다**(`shipment-alert.service.ts` 가 이미 쓰는 경로이고
SMS 는 템플릿 승인이 필요 없다). ⚠️ **폴백을 안 두면 "갱신 결제 실패"가 조용히 사라지고**, 그건
이 기능이 만들 수 있는 최악의 무음 실패다(브랜드는 도메인이 만료된 뒤에야 안다).

⚠️ 수신번호는 `Brand.senderPhone ?? BrandUser.phone`(알림톡 기존 규칙과 동일). **둘 다 없으면
발송을 건너뛰되 `logger.warn` + Sentry** — 조용히 지나가면 안 된다.
⚠️ 두 모듈 다 `WebAuthModule` 이 export 하므로 `BrandDomainsModule → WebAuthModule` import 만
추가하면 된다(순환 없음 — `ShipmentsModule` 선례).
⚠️ `.env.example` 의 Solapi 블록에 새 템플릿 4개를 추가한다. ⚠️⚠️ **네 개 전부 선택(optional)이고
배포를 막지 않는다** — 미설정이면 위 폴백이 SMS 로 내보내므로 기능이 온전히 동작하고, 승인되는
대로 한 줄씩 채우면 그 종류만 알림톡으로 승격된다(§11 · §19 4.5단계). 심사는 착수해 두되 **기다리며
배포를 미루지 말 것.** 이 네 값은 튜너블이 아니라 **카카오가 발급하는 외부 식별자**라 상수화가
불가능하고(계정·환경마다 다르다), 그래서 env 가 유일한 방법이다 —
기존 `SOLAPI_KAKAO_TEMPLATE_ORDER_PAID` 와 같은 계열이다.

### 9-3. ⚠️⚠️ 갱신 성공 후 **만료일 전진 확인** — 없으면 정상 갱신된 도메인이 만료일에 끊긴다

초안 §9 에는 **브랜드에게 돈을 받는 절차만** 있고 **`expiresAt` 을 앞으로 미는 절차가 없었다.**
그런데 Cloudflare 는 갱신 API 가 없어(§0) 실제 갱신이 **`auto_renew` 로 만료일 당일**에 일어난다.
그래서 30일 전 청구가 성공해도 `registration.expiresAt` 은 **옛 값 그대로**이고, 만료일이 지나는
순간 §9 의 정리 절(`expiresAt < now`)이 **돈을 낸 브랜드의 `BrandDomain` 을 지운다.**

반대편이 더 나쁘다. §18-3 처럼 **우리 계정 카드가 죽어 Cloudflare 실갱신이 실패**하면 브랜드 돈만
받고 도메인은 소멸하는데, **그걸 감지하는 코드가 하나도 없다** — 만료일 전진 여부가 유일한
신호인데 아무도 그 값을 다시 읽지 않기 때문이다. 둘 다 "조용히" 일어난다.

**갱신 charge 가 `paid` 가 된 뒤에도 그 registration 은 끝난 것이 아니다.** 갱신 cron 이 다음을 맡는다:

```
갱신 청구 성공(charge=paid, kind=renewal, periodEnd=null)   ← ★ 이 null 이 "확인 대기" 마커다
  → 만료일 D-1 부터 registrations/{domain} 재폴링 (하루 1회면 충분 — 벤더 갱신은 당일 이벤트다)
      ├ 만료일이 전진했다 → registration.expiresAt 갱신 · charge.periodEnd = 새 만료일 · 확인 완료
      └ D+GRACE 까지 전진 없음 → ★ registration.action_required + 어드민 SMS.
                                  ⚠️ BrandDomain 은 **지우지 않는다**(브랜드는 돈을 냈다)
```

**확인 대기 집합은 컬럼이 아니라 쿼리다** — 새 플래그를 만들지 않는다:

```ts
// 갱신 cron 이 매일 집는 두 번째 집합
where: { kind: 'renewal', status: 'paid', periodEnd: null,
         registration: { expiresAt: { lte: addDays(now, 1) } } }
```

- ⚠️⚠️ **정리 절(`expiresAt < now` → `BrandDomain` 삭제)은 `autoRenew=false` 인 행에만 건다.**
  `autoRenew=true` 인데 만료일이 지난 행은 "만료"가 아니라 **"갱신 확인이 안 끝난 상태"** 다.
  이 한 줄이 없으면 위 첫 번째 사고가 그대로 난다.
- `GRACE` 는 §0 7번 실측값으로 정한다(전진이 만료일 당일인지 며칠 뒤인지 모르는 채로 정하면
  멀쩡한 갱신을 사고로 올린다). 실측 전 기본값은 **7일** — 레지스트리 redemption 기간보다 짧다.
- ⚠️ `expiresAtIsEstimated=true` 인 행은 애초에 자동 청구를 안 하므로(§9) 이 흐름에 들어오지 않는다.
- ⚠️ **`periodEnd` 를 청구 시점에 `expiresAt+1년` 으로 확정해 두지 말 것** — 갱신이 실제로 안 됐을 때
  장부에만 1년이 늘어난다. 전진 확인 후에 쓴다(그래서 §4 에서 nullable 이다).
- ⚠️⚠️ **`expiresAtIsEstimated=true` 인 행은 여기서 새는 것이 아니라 §9-1a 로 빠진다.** 그 행은
  자동 청구를 안 하는데(§9) **Cloudflare `auto_renew` 는 여전히 `true`** 라, 방치하면 만료일에
  **브랜드에겐 안 받고 우리 카드만 긁힌다** — §18-1a 와 정확히 같은 사고다.
  처리(2단계 + `ESTIMATED_GIVE_UP_DAYS`)는 **§9 의 `expiresAtIsEstimated` 항목**에 있다.

ℹ️ 이 절이 §18-3(우리 카드 사망)의 **탐지기**이기도 하다. 서킷브레이커는 *구매* 경로만 막는데,
**갱신은 우리가 아무 API 도 부르지 않아 실패를 볼 기회가 여기밖에 없다.**

## 10. 모듈 배선 — `SubscriptionModule` exports 개방

순환 없음(확인 완료):

```
BrandDomainsModule → [BrandAuthModule, SubscriptionModule(신규)]
SubscriptionModule → [BrandAuthModule, BrandApplicationsModule]
BrandApplicationsModule → [BrandAuthModule, TranslationModule, ProductsModule]
```

`BrandDomainsModule` 을 import 하는 곳은 `app.module.ts` 하나뿐(`main.ts` 는 `app.get()` 으로 꺼낸다)
→ **순환 0**.

```ts
// subscription.module.ts
exports: [NicepayBillingAdapter],
// ⚠️ SubscriptionService 를 열지 않는 것은 의도다. 도메인 구매가 필요한 건 카드 승인/취소
//    (chargeBilling·cancelPayment·netCancel)뿐이고, 1160줄짜리 구독 상태 머신을 열면
//    다음 사람이 거기서 grantSubscription 을 부른다.
// ⚠️⚠️ 역방향(SubscriptionModule → BrandDomainsModule)은 순환이다. 갱신 미납 시 도메인을
//    끄는 로직은 반드시 brand-domains 가 소유한다.
```

DI 없이 공유할 조각 4개(전부 순수 파일 → 순환 위험 0):

| 조각 | 어디로 | 왜 |
|---|---|---|
| `retryGap` (dunning 0/1/3/7) | **`subscription/dunning.ts`** 신규 | 지금 `subscription.service.ts:1138` 의 **비-export 모듈 로컬 함수**다. 두 벌이 되면 반드시 갈린다. ⚠️ `common/` 으로 올리지 않는다 — dunning 은 배관이 아니라 **정책**이라 소유 모듈이 갖는 게 규칙 3 휴리스틱에 맞다(`common/cookies.ts` vs `modules/web-auth/session.ts` 선례) |
| `throwAsHttp` | `retryGap` 과 같은 파일(또는 `NicepayBillingAdapter`) | ⚠️ **이것도 `subscription.service.ts:68-77` 의 비-export 모듈 로컬 함수다.** §7 4단계가 쓰는데 목록에 없으면 구현자가 말없이 복제하고, 그러면 `NicepayErrorClass` → HTTP 매핑이 두 벌이 된다. (`NicepayBillingError`·`classifyNicepayError` 는 `nicepay-billing.adapter.ts:80,69` 에서 **이미 export** 되어 있으니 그쪽은 손댈 것이 없다) |
| **"정본 빌링키" 술어** | **`subscription/billing-key-select.ts`** 신규 | ⚠️⚠️ **초안이 `DEFAULT_BILLING_KEY_WHERE` 를 "추출"하라고 적었으나 그런 상수는 존재하지 않는다**(레포 grep 0건). 실제로는 세 곳에 손으로 쓰였고 **이미 갈려 있다**: `chargeReady`(`:669-672`, `deletedAt` **안 봄**) · `resumeWithExistingCard`(`:466-471`, **봄**) · `chargeOne`(`:757-762`, 안 봄). 그래서 이 작업은 "추출"이 아니라 **"신설 + 정본 결정"** 이다. 정본은 `billingKeyId != null && !billingKey.deletedAt && brand.pgCustomerKey != null` — ⚠️ 도메인 구매는 **일회성·환불 불가·즉시 청구**라 `deletedAt` 검사가 **필수**다(사용자가 이미 바꾼 카드에 청구되는 것이 최악이다). 규칙이 두 벌이 되면 안 되는 근거는 `brands/brand-selects.ts` 선례 그대로 |
| `orderIdFrom` | `NicepayBillingAdapter` 의 static 으로 승격 | NicePay orderId 규칙은 결제 배관이라 어댑터가 소유하는 게 맞다 |
| **`findPaymentByOrderId` (신규 메서드)** | `NicepayBillingAdapter` | ⚠️⚠️ **어댑터에 거래 조회가 아예 없다**(public 7개 전부 승인/취소/조회불가). §7-1-E 의 "NicePay 재조회"가 부를 대상이 없으므로 **반드시 추가**한다. 구독은 조회가 필요 없었다(다음날 재청구가 복구책) — 일회성 결제라 새로 필요해진 것이다 |

## 11. 라우트 · zod · env

| 라우트 | 처분 |
|---|---|
| `GET /v1/brand/domains` | 유지 |
| `POST /v1/brand/domains` (host 직접) | **브랜드에서 제거 → 어드민으로 이관** |
| `POST /v1/brand/domains/:id/check` | 유지(구매 도메인도 DNS 수렴이 늦으면 "지금 확인"이 자연스럽다) |
| `DELETE /v1/brand/domains/:id` | **조건부 차단**(전면 제거 아님 — 아래 ⚠️⚠️) — `BrandDomainRegistration` 이 걸린 행이면 409 `domain_purchased`("연결 해제 문의" 안내), 걸리지 않은 행(어드민이 붙여 준 **브랜드 소유** 도메인)은 **종전대로 브랜드가 삭제**한다 |
| `GET /v1/brand/domains/search` · `/v1/brand/domain-wishes/*` | 유지(찜이 1급 소비자가 된다) |

⚠️⚠️ **`DELETE` 를 전면 제거하면 안 된다.** 제거 근거("우리가 산 도메인이라 브랜드가 지우면
원가를 우리가 문다")는 **registration 이 걸린 행에만 참**인데, §3 때문에 `.co.kr` 을 비롯한
**브랜드 소유 도메인은 어드민 수동 연결로 계속 들어온다**. 전면 제거하면 그 브랜드는 **자기
도메인인데도** 연결 해제를 매번 운영팀에 문의해야 하고(종전엔 스스로 됐다), §3 이 "어드민 수동
연결은 선택이 아니라 필수" 라고 못박은 그 경로의 UX 만 골라 나빠진다.
⚠️ 판정은 `registration` **행의 존재**로만 한다 — 호스트 문자열·TLD 로 넘겨짚지 말 것.

**신규(브랜드)** — `brand-domain-purchase.controller.ts`, `@Controller('v1/brand/domain-purchase')`

⚠️ **파일 분리 근거를 `requireBrandId` 로 적지 말 것.** 구매 컨트롤러는 `brand-domains.controller.ts`
와 **불변식이 같다**(둘 다 `requireBrandId` 가 필요하다). 그 불변식이 반대인 건 search·wishes
둘뿐이고, 잘못된 근거를 남기면 다음 사람이 search 컨트롤러에 `requireBrandId` 를 넣어 `/start` 를
죽인다. 분리 이유는 **관심사·크기**다.

⚠️⚠️ **경로를 `v1/brand/domains` 밑에 두지 않는 이유**: 그 컨트롤러엔 이미 `POST /:id/check` ·
`DELETE /:id` 가 있고, `brand-domain-wishes.controller.ts` 는 **정확히 이 그림자 문제 때문에**
`v1/brand/domain-wishes` 로 빠졌다고 주석에 적어 뒀다(같은 계열 선례: `shipping-countries/export`,
`shipments` alert 라우트). 지금은 `GET /:id` 가 없어 우연히 안전할 뿐이고, **순서에 기대는 안전은
다음 사람이 라우트를 추가하는 날 깨진다.** 굳이 같은 prefix 를 쓴다면 리터럴 경로를 `:id` 라우트보다
**먼저** 등록할 것.

- `POST /v1/brand/domain-purchase/quotes` `{hosts[≤20]}` → 찜 목록에 가용성 + 가격을 붙인다.
  `domain-check` 가 20개/요청이라 **배치가 맞다**(`MAX_DOMAIN_WISHES = 20` 과도 맞아떨어진다).
  `DomainSearchService` 와 같은 **5분 캐시**(찜 20개 × 유료 호출).
  ⚠️ **`@Throttle` 을 반드시 건다** — 이웃이 search 20/분 · wishes 30/분 · check **6/분**인데 이건
  **가장 비싼 벤더 호출**이다(check 와 같은 급 권장). 안 걸면 전역 60/분만 적용된다.
  ⚠️ 화면 흐름상 **검색이 2왕복이 된다**: `GET domains/search`(`{name}` 만 10건) → `POST quotes`
  (`domain-check` 10건). `domain-search` 응답에 가격을 얹어 1왕복으로 줄이고 싶어지겠지만
  **하지 말 것** — `DomainSuggestion = { name }` 과 `domain-search.spec.ts` 의 "never ships
  pricing/tier" 단언을 무변경으로 통과시키는 편이 싸다(§6 표 2·3번).
- `POST /v1/brand/domain-purchase/purchase` `{host, expectedAmountKrw, agreedNonRefundable}` · `@Throttle 3/분`
  ⚠️⚠️ **여기서 부르는 `domain-check` 는 quotes 의 5분 캐시를 우회한다.** 같은 캐시를 타면
  ① 5분 묵은 `registrable` 을 믿고 사고 ② 견적과 청구가 같은 캐시 값을 보므로
  **`expectedAmountKrw` 불일치 409 가 영원히 발화하지 않는다**(§7 2단계가 통째로 무의미해진다).
- `GET /v1/brand/domain-purchase/registration` — 진행 상태(화면 3초 폴링)
  ⚠️⚠️ **단수형 라우트인데 registration 은 브랜드당 N행이 된다**(실패·환불·`released`·재구매).
  어느 행을 돌려줄지 규칙이 없으면 화면이 **옛 `failed` 행을 물고 폴링**해, 진행 중인 구매가
  영영 안 보인다. 선택 규칙을 못박는다:
  **① `status ∈ {charging, paid, registering, registered, active}` 중 `createdAt` 최신 1건**
  **② 없으면 그 브랜드의 `createdAt` 최신 1건**(방금 실패한 건을 화면이 보여줘야 하므로)
  **③ 그것도 없으면 `null`**. ⚠️ `released`/`expired` 는 ①에 넣지 않는다 — 그건 종료된 자산이라
  "진행 상태" 폴링의 대상이 아니고, §14 `PurchaseProgressPanel` 이 영원히 열린다.

**응답 shape (초안엔 없었다 — 화면이 뭘 받는지 미정이었다)**

```ts
// POST quotes → 찜/검색 목록에 붙일 값. domain-check 한 응답에서 둘 다 나오므로 벤더 호출 +0.
type DomainQuote = {
  host: string;
  available: boolean;          // registrable === true
  reason?: string;             // 우리가 아는 사유만 매핑 — 벤더 원문 그대로 흘리지 않는다
  amountKrw?: number;          // 1년차 실청구가 (available 일 때만)
  renewalAmountKrw?: number;   // ★ 2년차 추정가 (§9-1) — renewal_cost 기반
};

// GET registration → 폴링 화면용. ⚠️ 원문 벤더 필드를 담지 않는다(아래).
type RegistrationProgress = {
  host: string;
  phase: 'charging' | 'paid' | 'registering' | 'registered' | 'active'
       | 'action_required' | 'failed' | 'expired';
  message: string;             // 사람이 읽을 우리 문구 (phase → 문구 매핑, 벤더 원문 아님)
  expiresAt?: string; autoRenew?: boolean;
};
```

⚠️⚠️ **`cfState`·`lastError` 원문을 브랜드에게 내리지 않는다.** `BrandDomain.lastError` 스키마
주석이 이미 *"브랜드 UI 에 **그대로** 노출되므로 민감정보·토큰을 담지 않는다"* 는 규칙을 세워
뒀는데, Cloudflare/NicePay 원문 에러엔 **계정 id·내부 식별자**가 섞일 수 있다. 두 값은
**어드민 탭 전용**(§16)이고, 브랜드 화면은 `phase → message` 매핑만 본다.
⚠️ 같은 이유로 `quotes.reason` 도 **우리가 아는 코드만 매핑**하고 모르는 값은 일반 문구로 접는다.

**신규(어드민)** — `admin-brand-domains.controller.ts` (`admin/brands/:id/domains`, `AdminGuard`)

- `GET /` · `POST /` **수동 연결**(→ `createForBrand` 그대로) · `DELETE /:domainId`
- `PATCH /registrations/:id/auto-renew` · `POST /registrations/:id/retry`(없으면 운영이 DB 를
  손으로 만진다) · `PATCH /charges/:id/refund`(구독 `refundInvoice` 미러 — ⚠️ **`cancelAmount` 는 받지 않는다**, 전액 환불만. §4)
- ⚠️ **`GET /admin/domain-purchase/circuit`**(§18-3) — streak · 잔여 쿨다운 · 최근 실패 사유.
  브랜드 축이 아니라 **계정 축**이라 `admin/brands/:id/domains` 밑이 아니다.
  ⚠️⚠️ **쓰기(리셋) 라우트는 만들지 않는다** — 서킷이 쿨다운 기반 half-open 이라 스스로 풀린다(§18-3).
  리셋을 두면 저장할 `resetAt` 이 필요해지고, 그걸 담을 자리가 이 스키마에 없어 싱글턴 테이블이
  하나 생긴다. **없어서 못 만든 게 아니라 안 만든 것이니 나중에 "빠졌네" 하고 추가하지 말 것.**

> ℹ️ 브랜드 라우트를 지워도 `domain_taken` · `domain_already_in_use` · `mapVercelError` ·
> `registerPair` · `pairErrorMessage` · `refreshOne` 재추가 분기는 **전부 산다** — 어드민 수동
> 연결과 구매 경로가 같은 `createForBrand` 를 타기 때문이다. 특히 `refreshOne` 의 재추가는
> **더 중요해진다**: 운영자가 Vercel 대시보드에서 실수로 지웠을 때 구매 도메인은 브랜드가 스스로
> 재등록할 방법이 아예 없다.

**zod** (`common/validation/brand-domain.ts`, **`.default()` 금지** 관례)

```ts
export const BrandDomainQuotesInput = z.object({
  hosts: z.array(BrandDomainHostField).min(1).max(20),   // domain-check 상한과 같은 값
});
export const BrandDomainPurchaseInput = z.object({
  host: BrandDomainHostField,
  // 화면이 보여준 금액. 서버 재계산과 다르면 409 — 환불 불가 상품이라 필수.
  expectedAmountKrw: z.number().int().positive(),
  // 전자상거래법 고지 동의. literal(true) 라 false 는 400 이다.
  agreedNonRefundable: z.literal(true),
});
```
정규화·거부는 여전히 `modules/brand-domains/domain-host.ts` 소유(규칙 2 — `common/` 은 `modules/`
를 import 못 한다).

**env**

```
CLOUDFLARE_DNS_TOKEN=              # 신규 (Zone > DNS:Edit). ⚠️ registrar 토큰 폴백 금지
DOMAIN_PURCHASE_ENABLED=           # ⚠️⚠️ 마스터 게이트 — === 'true' 일 때만 "돈을 움직인다"
                                   #    (구매 + 갱신 청구 둘 다. 아래 ⚠️⚠️⚠️)
BRAND_DOMAIN_REGISTRATION_CRON_ENABLED=    # === 'false' 일 때만 off (기존 cron 관례)
# 알림톡 템플릿 4종 (§9-2) — **전부 선택**이다. 미설정이면 KakaoService 가 콘솔 로그로
# 떨어지고 **SMS 폴백이 대신 나가므로**(무음 아님) 승인 전에도 기능이 온전히 동작한다.
# 승인되는 대로 한 줄씩 채우면 그 종류만 알림톡으로 승격된다.
SOLAPI_KAKAO_TEMPLATE_DOMAIN_PURCHASED=
SOLAPI_KAKAO_TEMPLATE_DOMAIN_RENEWAL_NOTICE=
SOLAPI_KAKAO_TEMPLATE_DOMAIN_PAYMENT_FAILED=
SOLAPI_KAKAO_TEMPLATE_DOMAIN_ACTION_REQUIRED=
```

⚠️⚠️ **env 는 3개 + 외부 식별자 4개다. 여기에 수치·튜너블을 더 얹지 말 것**(2026-08-26 정리):

- **구매 상한 2개(`DOMAIN_MAX_REGISTRATIONS_PER_*`)를 env 에서 뺐다 → §18-4 의 코드 상수다.**
  근거 둘. ① **이 레포에는 env 로 읽는 수치 상한이 0건**이다 — `MAX_DOMAINS_PER_BRAND`(3) ·
  `MAX_DOMAIN_WISHES`(20) · 시딩 정원(2~500) · 리뷰 bulk(200) 전부 상수이고, 여기서 예외를 만들면
  이 파일이 그 선례가 된다. ② **§5 주석 5번의 논거가 그대로 적용된다** — 환불 불가 상품에서
  오설정된 값은 상수보다 나쁘다. `=0` 오타 하나면 **전 브랜드 구매가 조용히 막히고**, 반대로
  큰 값이면 비용 폭주 방어가 사라진다. 값을 바꿀 일이 생기면 **코드 리뷰를 거치는 편이 맞다**.
- ⚠️⚠️⚠️ **`BRAND_DOMAIN_RENEWAL_CRON_ENABLED` 를 없애고 `DOMAIN_PURCHASE_ENABLED` 에 흡수했다.**
  초안은 "돈이 나가는 cron 은 opt-in 이어야 한다"며 **반대 방향 폴라리티**를 뒀는데, 그건
  **레포 관례가 아니다** — cron 9개 중 kill switch 는 3개뿐이고 **정작 돈이 나가는
  `brand-subscription-billing` 에는 없다**. 그리고 그 스위치는 **위험을 줄이는 게 아니라 옮긴다**:
  갱신은 첫 구매 후 11개월간 due 행이 0이라 켜 두어도 아무 일도 하지 않는 반면, "1년 뒤에 켠다"를
  캘린더에 맡기면 **잊는 순간 도메인이 만료된다**(§19 배포 6단계가 그 리마인더였다).
  마스터 게이트 하나가 스테이징 오청구를 막는 목적을 그대로 달성하면서 그 망각 위험을 없앤다.
- ⚠️ 대신 **`BRAND_DOMAIN_REGISTRATION_CRON_ENABLED` 는 마스터 게이트와 독립**이어야 한다.
  사고 대응은 "신규 유입만 막고 in-flight 는 끝낸다" 이므로, `DOMAIN_PURCHASE_ENABLED=false` 가
  이 cron 을 멈추면 **`paid` 로 묶인 돈이 영영 등록되지 않는다**(§7 흐름 8~11 이 통째로 정지).

⚠️ **`DOMAIN_MARGIN_RATE` 는 일부러 없다** — §5 주석 5번에서 **env 오버라이드를 두지 않기로**
확정했다(오설정된 마진율은 상수보다 나쁘다). 초안 env 목록에 남아 있던 줄을 지웠으니
다시 넣지 말 것.

⚠️⚠️ **[`implementation-plan.md`](./implementation-plan.md) §2-8 의 "부팅 fail-closed 가드를 붙이지
않는다"는 이 기능에 그대로 적용되지 않는다.** 그 문장의 근거는 *"도메인은 미설정 시 브랜드가 즉시
에러를 보므로 조용히 깨지지 않는다"* 였는데 **구매 경로는 정확히 그 반대**다 — 스테이징 서버가
운영 Cloudflare 토큰을 들고 있으면 테스트 클릭 한 번이 **되돌릴 수 없는 실제 돈**이 된다
(`VERCEL_PROJECT_ID` 오지정 경고와 같은 축이되, 이쪽은 회수가 불가능하다). 그래서
`DOMAIN_PURCHASE_ENABLED` 를 **명시 opt-in** 으로 두고 미설정 시 `503 domain_purchase_unavailable`.

⚠️ `.env.example` Cloudflare 블록의 *"가능하면 읽기 전용으로 — write 토큰은 도메인을 등록해 돈을
쓸 수 있다"* 주석도 **write 필요로 정정**해야 한다.

---

# 프론트

## 12. klow_brand — `BrandDTO.customDomain` (말풍선의 데이터 소스)

말풍선 조건("커스텀 도메인 미연결")을 알려면 스튜디오가 도메인 상태를 알아야 한다. **새 쿼리를
쏘지 않고** `brand-applications.service.ts:43` 의 `APPLICATION_INCLUDE` 에 한 줄을 더한다:

```ts
domains: { where: { role: 'primary', status: 'active' }, select: { host: true }, take: 1 },
```

→ `BrandDTO.customDomain: string | null` 로 파생. **HTTP 왕복 0 증가**(Prisma relation 이라 DB
쿼리 +1). ⚠️ **`Brand` 에 컬럼을 추가하지 않는다** — `BrandDomain` 이 정본이고 서버 DTO 파생으로만.

⚠️ **같은 자리에서 `domainPending` 도 함께 뽑는다**(§13) — 말풍선이 구매 진행 중에 막다른 길이
되지 않으려면 필요한데, 별도 쿼리를 쏘면 §13 의 "추가 쿼리 없음" 이 깨진다:

```ts
domainRegistrations: {
  where: { status: { in: ['charging','paid','registering','registered','active'] } },
  select: { status: true }, orderBy: { createdAt: 'desc' }, take: 1,
},
```
⚠️ 이 `in` 목록은 §11 `GET registration` ①과 **같은 집합이어야 한다** — 갈리면 말풍선과 진행
화면이 서로 다른 사실을 말한다. 상수 하나로 두고 양쪽이 import 할 것 — 자리는 **`modules/brand-domains/registration-status.ts`**(접미사 없는 명사 = 순수 헬퍼, 규칙 4). ⚠️ `common/` 에 두지 않는다(규칙 3 — 도메인 값이다). `brand-applications.service.ts` 가 이 파일을 import 하는 것은 **DI 가 아니라 순수 파일 import** 라 모듈 순환이 아니다(§10 의 배선표는 그대로다).

> **부수 이득**: 지금 링크바가 `storefrontLabel(previewBrand?.slug)` 로 `customDomain` 을 **안 넘겨**
> 도메인이 붙어도 `klow.kr/{slug}` 를 보여주는 **기존 버그가 함께 고쳐진다**.
>
> ⚠️ **단, 같은 40px 바 안의 QR 버튼·공유 버튼은 여전히 `klow.kr` 을 낸다.** `storefront.ts` 주석이
> *"지금 이 인자를 넘기는 곳은 설정 > 도메인 연결 하나뿐이고 ShareModal·QR·인스타 답글·프로모션
> 링크의 도메인화는 계획 §6-2 로 미뤄져 있다"* 고 적어 뒀다. 라벨만 고치면 **한 바 안에서 주소가
> 갈린다** — 셋을 함께 고치거나(권장), 미룬다면 이 비대칭을 `studio/page.tsx` 주석에 남길 것.
> (`productLinkUrl(slug, productId)` 은 `customDomain` 인자가 **아예 없다** — 같은 §6-2 범위다.)

## 13. klow_brand — 스튜디오 말풍선

**위치**: `studio/page.tsx` 링크바(**362~390행**, 좌측 컬럼 wrapper 는 362행)의 **바로 아래 형제**
— 드리프트 경고 배너(**393~405행**)와 같은 자리. (2026-08-25 실측. 초안의 354~381/382 는 스냅샷이
밀린 값이었다.)

```
<div className="flex flex-col items-center gap-3 lg:-mt-5">
  ├ 링크바 (w-full max-w-[380px] h-[40px])
  ├ ★ 도메인 말풍선   ← 여기 (in-flow, mb-2)
  ├ 드리프트 경고 배너
  └ <PhoneFrame>
```

- ⚠️ **링크바 위에 두지 말 것** — `lg:-mt-5` 컬럼이라 위로 밀면 헤더와 겹친다.
- ⚠️ **`absolute` 로 띄우지 말 것.** `StudioSkeleton.tsx:32~37` 이 링크바 치수(`max-w-[380px]
  h-[40px]`)를 미러링하는데, 절대배치면 높이를 예약할 수 없어 로드 직후 레이아웃이 튄다 →
  드리프트 배너와 **같은 in-flow 패턴**을 쓴다.
- ⚠️ **스켈레톤은 말풍선 자리를 예약하지 않는다** — 조건부라 항상 뜨는 게 아니고, 예약하면 이미
  연결한 브랜드에서 빈칸이 남는다. 이 비대칭(링크바는 미러링 / 말풍선은 미러링 안 함)을 두 파일
  주석에 남길 것.
- **조건**: `brand?.slug && !brand.customDomain && brand.subscription?.status === 'active'`.
  미구독에 띄우면 눌러도 서버가 403 이라 막다른 길이다.
  ⚠️⚠️ **`!brand.customDomain` 만으로는 부족하다.** 그 값은 `status='active'` 인 `BrandDomain` 파생
  (§12)이라 **구매가 `charging`~`registered` 인 동안 계속 참**이다 → 말풍선이 그대로 떠 있고,
  눌러 들어가 다시 사면 §7 0단계 게이트가 **409 로 막는 막다른 길**이 된다(§14 가
  `PurchaseProgressPanel` 로 피하려던 바로 그 상황). **진행 중이면 문구를 "도메인 연결 진행 중"
  으로 바꿔 `/settings/domain` 으로 보낸다.**
  ⚠️ 그 판정에 **추가 쿼리를 쓰지 말 것** — `APPLICATION_INCLUDE`(§12)에서 `customDomain` 을 뽑을 때
  **진행중 registration 유무도 같이 파생**해 `BrandDTO.domainPending: boolean` 으로 내린다
  (선택 규칙은 §11 `GET registration` ①과 같은 집합). HTTP 왕복 0 증가는 그대로 유지된다.
  ⚠️ `previewBrand` 가 아니라 **`brand`**(자동저장 draft 가 얹히지 않은 서버 사실).
  ℹ️ `BrandDTO.subscription` 이 이미 있어(`studio/page.tsx:319` 가 쓴다) **추가 쿼리가 없다**.
- 닫기 버튼 없음(연결하면 자동으로 사라진다). 전용 Tooltip 컴포넌트가 프로젝트에 없으므로
  (`components/ui/Popover.tsx` 는 바깥클릭·ESC 를 갖춘 상호작용 팝오버라 과하다) **이 자리 전용 마크업**.

## 14. klow_brand — `/settings/domain` (신규)

middleware matcher **무변경**(`/settings/:path*` 가 이미 있다). `settings/subscription/` 구조를 미러
(`StudioPillHeader` + 패널 분할).

| 컴포넌트 | 역할 |
|---|---|
| `DomainStatusPanel` | 연결됨: 호스트 · 만료일 · 자동갱신 · "브랜드관 열기". **DNS 안내 없음** |
| `PurchaseProgressPanel` | `charging\|paid\|registering` → 3초 폴링. ⚠️ **`registered` 도 폴링 대상**이다 — 등록은 끝났는데 연결이 아직인 구간이고, 구독이 끊겼으면 **여기서 오래 머문다**(§7-3). 그때는 "구독이 확인되면 자동으로 연결됩니다" 안내(막다른 길처럼 보이면 안 된다). `action_required` → 운영팀 연락 안내. ⚠️⚠️ **`failed` 는 이 패널이 담당하지 않는다** — 환불까지 끝난 종료 상태라 브랜드가 **다시 사야** 하는데, 여기서 그리면 검색 패널이 닫혀 화면에서 할 수 있는 일이 하나도 없어진다(초안이 그랬다). 서버도 같은 판단이다 — `ACTIVE_REGISTRATION_STATUSES` 가 `failed` 를 일부러 뺐다. 검색 패널 **위 한 줄 안내**(`PurchaseFailedNotice`)로만 남기고, "담당자가 확인하고 있어요" 를 쓰지 않는다(아무도 안 보고 있는 상태다 — 그렇게 안내하면 브랜드가 연락을 기다리며 재시도를 안 한다). 구매 차단 판정의 단일 출처는 `blocksNewPurchase` 다 |
| `WishListPanel` | `domainWishes.list()` + `POST quotes` 병합. 팔린 도메인은 회색 + "이미 판매됨" + 찜 해제 |
| `DomainSearchPanel` | 찜이 없거나 다 팔렸을 때 직접 검색 |
| `PurchaseDialog` | 공급가/VAT/합계 + **2년차 예상가 병기**(§9-1) + `****1234` + **환불 불가 · 이전 불가 고지 체크박스**(§18-1 — 두 고지를 **같은 칸**에). ⚠️ `BillingKey.cardLast4` 는 **null 일 수 있다**(`nicepay-billing.adapter.ts:303` — 빌키 발급 응답엔 카드번호가 없어 **첫 결제 응답에서** 채운다) → `카드 정보 확인 중` 폴백 |
| `DomainLinkCard` (settings/_components) | 허브 진입 카드 — `SubscriptionLinkCard.tsx` 를 그대로 미러 |

- ⚠️⚠️ **`DomainSuggestions.tsx` 의 모듈 레벨 `searchUnavailable` 래치를 재사용하지 말 것.**
  모듈 레벨이라 `/start` 에서 한 번 503 을 받으면 **세션 내내 전염**되어 `/settings/domain` 의
  검색이 죽은 채로 뜬다. 두 화면의 실패 정책은 **정반대**다 — `/start` 는 "부가 기능이라 조용히
  사라진다", `/settings/domain` 은 "검색이 본업이라 에러 배너를 띄운다". **컴포넌트를 공유하지
  않고** `qk.domainSearch` 캐시만 공유한다. 이 비대칭을 두 파일 주석에 남길 것.
- ⚠️ 찜은 **`brandUserId` 스코프**다(`/start` 엔 Brand 가 없어 그렇게 잡혔다). `BrandUser.brandId`
  는 unique 가 아니라 한 브랜드에 계정이 여럿일 수 있어 **A가 찜한 것이 B에게 안 보인다.** 이번엔
  그대로 둔다(검색으로 다시 찾으면 된다) — `brandId` 로 옮기면 `/start` 사용자(brandId=null)가
  못 쓰게 된다.
- `HandoffNotice`(둘러보기·담기는 커스텀 도메인 / 로그인·결제·주문조회는 klow.kr)는 **그대로
  가져온다** — 경계는 구매 방식과 무관하게 유효하다.
- ⚠️ **`lib/onsite.ts` 의 `onsiteStoreUrl()` 에는 customDomain 을 절대 넘기지 않는다**(미들웨어가
  `?mode=onsite` 를 떼어 내 부스 QR 이 에러 없이 조용히 일반 모드로 떨어진다).

## 15. klow_brand — 제거

`settings/_components/DomainSection.tsx` **삭제**(578줄 — `AddDomainForm`·`DnsGuide`·`DnsRecordBox`·
`PairLine`·`groupDomains`·`toVerificationRecord` 동반). `settings/page.tsx:319` → `DomainLinkCard`.
`api.domains.create`/`remove` 제거.

⚠️ `src/lib/domain.ts` 의 `checkDomainInput` 은 **삭제하지 않는다**(`canonicalHost`·`wwwPairHost` 도
`/settings/domain` 이 계속 쓴다). 파일 상단의 *"서버 `domain-host.ts` 의 의도된 크로스레포 미러"*
주석에 **소비자 목록**을 갱신할 것.

⚠️⚠️ **klow_admin 에는 이 미러가 없다.** `lib/domain.ts` 는 **klow_brand 에만** 존재하므로, 어드민
수동 연결 폼에 같은 실시간 검증을 붙이려면 **미러가 3벌**(server / brand / admin)이 된다 — 이
레포가 크로스 레포 미러로 이미 여러 번 데인 축이다(`skin-type-presets`·`category-presets`·
`tax-id`·`constants`).
**권고: 어드민엔 미러를 만들지 않는다.** 근거 — ① 사용자가 **운영팀 소수**라 즉시 피드백의 값이
낮고 ② 최종 판정은 어차피 서버 `normalizeHost`(400 `domain_invalid`)이며 ③ `BLOCKED_EXACT`/
`BLOCKED_SUFFIXES` 는 klow_brand 에서도 **export 되지 않는 모듈 private** 이라 그대로 복사해야 한다.
어드민 폼은 **서버 400 을 토스트로 띄우는 것으로 갈음**한다(CLAUDE.md 어드민 토스트 규약).
⚠️ 그래도 미러를 만들기로 한다면 **거부 문구까지 문자 그대로 복사**할 것 — 그게 지금 두 벌이
안 갈리는 유일한 이유다.

## 16. klow_admin — `/brands/[id]` 도메인 탭

1. `brands/_components/brand-detail-tab.ts` 의 `BRAND_DETAIL_TABS` 에 `'domain'` **한 줄**
   (딥링크 화이트리스트가 여기서 파생되므로 다른 곳은 안 고쳐도 된다)
   ⚠️⚠️ **그 파일에 `'use client'` 를 붙이지 말 것** — 서버 컴포넌트 `[id]/page.tsx` 가
   `isBrandDetailTab` 을 부르는데, client 모듈의 함수 export 는 client reference proxy 가 되어
   런타임에 `is not a function` 으로 죽는다(주석에 실제로 한 번 배포된 이력이 적혀 있다)
2. `BrandDetailTabs.tsx` — `domainMounted` + 탭 버튼. ⚠️ 초기값을 `initialTab === 'domain'` 에서
   파생시킬 것(`false` 고정이면 딥링크 진입에 빈 화면)
3. `components/brand-domain/BrandDomainPanel.tsx` + `ManualAttachDialog` · `AutoRenewToggle` ·
   `RefundChargeDialog` · `RetryRegistrationDialog` — `brand-subscription/` 5파일 구조를 미러
4. 표시: 호스트 · registration status · Cloudflare `cfState` 원문 · 만료일(+근사 배지) ·
   `auto_renew` · **원가(USD/KRW)/판매가/마진** · 청구 이력(attemptCount·failReason) · 연결된
   `BrandDomain` 행 상태
5. `lib/api/brand-domains.ts` + 배럴. **CLAUDE.md "Admin UI Convention — Toast Feedback (required)"** 준수
6. ⚠️⚠️ **도메인 매출이 지금 어느 리포트에도 안 잡힌다.** `BrandDomainCharge` 는
   `SubscriptionInvoice` 의 형제로 설계했지만(§4), 어드민 대시보드 홈의 **브랜드 구독매출**
   (`revenueTotalKrw`)과 정산 화면은 **`SubscriptionInvoice` 만 읽는다.** 그대로 두면 새 상품의
   매출·원가·마진이 회사 지표에서 **통째로 사라지고**, §5 가 charge 행에 `fxRateKrwPerUsd`·
   `marginRate`·`supplyKrw` 를 스냅샷해 둔 이유가 무의미해진다.
   → **도메인 탭에 그 브랜드 합계**(누적 청구액·원가·실마진)를 내고, 전사 합계는
   `GET /admin/stats` 계열에 **별도 항목으로 추가**한다. ⚠️ **`revenueTotalKrw` 에 합산하지 말 것** —
   그 라벨은 2026-08 개편에서 "건당 ₩1,500 시딩 이익이 섞여 있던" 것을 걷어내고 **구독매출만**
   가리키도록 정정한 값이다(CLAUDE.md). 같은 실수를 반복하게 된다.

## 17. klow_web — 변경 없음

구매한 도메인도 결국 **같은 `BrandDomain` row(`status='active'`)** 를 만들고, `resolveHost` ·
`middleware.ts` · 핸드오프는 그 행만 본다. **서빙 경로가 통째로 무변경**이다.

> ℹ️ 새 POST 지만 `common/origin-policy.ts` 의 `BRAND_STATE_CHANGE_PATHS` 와는 **무관**하다 — 그
> 목록은 *커스텀 도메인 오리진*(손님 브라우저)에서 오는 상태변경을 좁히는 것이고, 구매는 브랜드
> 콘솔(`brand.klow.kr`, `klow` 클래스)에서 부른다. `origin-policy.spec.ts` 는 **무변경 통과**해야 한다.

---

## 18. 종료 경로 3가지

셋 다 **환불이 없다**(원가가 이미 나갔다). 화면 문구가 이걸 미리 말해야 CS 가 생기지 않는다.

| 계기 | registration | Cloudflare `auto_renew` | DNS 레코드 | zone | 브랜드관 |
|---|---|---|---|---|---|
| **연결 해제**(어드민 경유) | ★ `released` | ★★ **즉시 `false`**(§18-1a) | ★ 즉시 삭제(§18-2) | 남긴다 | 즉시 `klow.kr/{slug}` 폴백 |
| **구독 해지·past_due** | `active` 유지 | **`true` 유지** — 갱신 청구는 계속한다(별도 상품이다) | ★ `cleanupOrphans` 가 Vercel 을 지울 때 함께 삭제 | 남긴다 | 60일 유예 후 Vercel 제거. 서빙은 `resolveHost` 가 즉시 차단 |
| **갱신 미납 확정** | `expired` 예약 | `false`(§9) | 만료 시 무의미 | ★ 만료 확정 시 삭제(§18-2 c) | 만료일까지 정상, 이후 `BrandDomain` 삭제 |

⚠️ `cleanupOrphans` 가 `BrandDomain` 행을 지울 때 **`BrandDomainRegistration` 은 지우지 않는다** —
회계·자산 기록이고 재구독 시 재연결의 근거다. FK 를 `SetNull` 로 둔 이유가 이것이다.

### 18-1. 소유권 이전은 하지 않는다 (2026-08-25 확정)

브랜드가 이탈하며 "그 도메인 넘겨달라"고 해도 **이전하지 않는다.** 도메인은 KLOW 자산이고,
만료까지 보유한 뒤 소멸시킨다. (Cloudflare 는 transfer API 가 없어 어느 쪽이든 대시보드 수동
작업이었을 것이다 — §3.)

⚠️⚠️ **이건 CS 마찰이 가장 큰 선택지이므로 "사후 통보"가 되면 안 된다.** 세 곳에 미리 쓴다:
1. **구매 확인 다이얼로그**(§14 `PurchaseDialog`) — 환불 불가 고지와 **같은 칸**에.
   *"이 도메인은 KLOW 명의로 등록·보유되며, 연결 해제 시 이전되지 않습니다."*
2. **도메인 구매 약관**(`/legal/*`) — 신규 문서가 필요하다. ⚠️ 지금 klow_brand `/legal` 에 도메인
   조항이 없다. **§19 배포 5단계 전에 준비할 것**(법무 검토 리드타임이 있다).
3. **`/settings/domain` 연결 해제 안내** — "연결 해제 문의" 문구 옆.

ℹ️ 이 정책 때문에 §1 의 "댕글링 갭이 닫힌다"가 **더 강해진다** — 도메인이 영영 남의 손에
넘어가지 않으므로 인계 창구 자체가 없다.

### 18-1a. ⚠️⚠️ 연결 해제는 **반드시 `setAutoRenew(false)` 를 부른다** — 안 하면 우리 카드가 긁힌다

초안의 표는 *"다음 갱신 청구 안 함"* 이라고만 적었는데, 그건 **브랜드에게 청구하지 않는다**는
뜻이었다. 그런데 **Cloudflare 쪽 `auto_renew` 는 그대로 `true`** 라, 만료일이 오면
**계정 기본 결제수단(= 우리 카드)이 자동으로 긁힌다.** 브랜드에게는 안 받고 우리만 낸다 —
쓰지도 않는 도메인에 매년 원가를 무는 것이고, **아무도 알아채지 못한다**(청구서가 브랜드
장부에 안 남으므로 어드민 화면에도 안 보인다).

§9 의 `RENEWAL_LEAD_DAYS` 설계가 정확히 이 사고를 막으려고 있지만, **그 cron 은 `autoRenew=true`
인 행만 돌므로 연결 해제 경로를 대신 막아 주지 않는다.** 그래서 해제 시점에 **동기로** 부른다:

```
연결 해제 = ① setAutoRenew(host, false)  ← ★ 실패하면 해제를 중단하고 어드민에 에러
            ② registration.autoRenew=false · status='released' · brandDomainId=null
            ③ releaseDnsFor(host)         (§18-2 — 실패해도 진행)
            ④ BrandDomain 삭제(pair 포함)
```

⚠️ **①이 실패하면 ②~④를 진행하지 않는다** — DNS·Vercel 만 걷어내고 `auto_renew` 가 살아 있으면
정확히 위 사고다. ③과 대칭이 아닌 이유가 이것이다(③은 실패해도 돈이 안 나간다).
⚠️ `released` 도메인은 만료일까지 우리 자산이므로 **재연결이 가능**하다 — 어드민 수동 연결이
같은 host 로 들어오면 `registration` 을 재사용하고 `setAutoRenew(true)` 를 되돌린다.

⚠️⚠️ **이 4단계는 `registration` 이 걸린 도메인 전용이다.** 어드민 수동 연결로 붙은 **브랜드 소유**
도메인(§3 — `.co.kr` 등)에는 registration 이 없고, 거기에 `setAutoRenew` 를 부르면 **우리가 사지도
않은 도메인을 Cloudflare 에 조회**하는 것이라 404 로 죽거나(①이 실패하면 ②~④를 안 하기로 했으므로)
**해제 자체가 막힌다**. 분기는 `registration` 행의 존재로 한다 — 없으면 ①을 건너뛰고 ③④만 한다
(그 도메인의 DNS 는 애초에 우리 zone 이 아니므로 ③도 no-op 이다).

⚠️⚠️ **`released` 재연결이 `MAX_DOMAINS_PER_BRAND`(3)에 걸릴 수 있다.** §7 0단계 게이트는
"진행중 registration 0건" 인데 `released` 는 진행중이 아니므로, released 도메인을 가진 브랜드가
**새 도메인을 살 수 있다**(primary + www = 2). 그 뒤 어드민이 released 를 재연결하면 4개가 되어
`createForBrand` 가 상한으로 거절하고, 위 "재연결이 가능하다"가 **조용히 거짓**이 된다.
→ 재연결 전에 어드민 화면이 **기존 연결을 먼저 해제하도록 안내**한다(상한을 올려 해결하지 말 것 —
§2 가 `MAX_DOMAINS_PER_BRAND` 를 손대지 않는 것을 §20 "무변경 통과" 의 조건으로 걸어 뒀다).

### 18-2. ⚠️⚠️ DNS·zone 정리 경로 — §1 의 약속을 실제로 지키는 코드

§1 이 *"브랜드 A의 연결을 끊을 때 레코드도 우리가 지운다"* 고 약속했는데, **초안엔 그 호출 지점이
어디에도 없었다**(`deleteDnsRecord` 는 §6 메서드 목록에만 있었고 `planDnsConvergence` 반환에도
`delete` 가 없었다). 약속이 코드 없이 떠 있으면 갭은 그대로 열려 있다.

**(a) `planDnsConvergence` 반환에 `remove` 를 추가한다** — `{ create, update, remove, skip }`.
⚠️ **우리가 심은 레코드만** 지운다: `desiredRecordsFor()` 가 관리하는 **이름·타입 조합**
(apex A / `www` CNAME)에 한정하고, **그 밖의 레코드는 절대 건드리지 않는다**(브랜드가 그 zone 에
MX·TXT 를 넣어 뒀을 수 있고, 메일을 죽이면 도메인 값보다 비싼 사고다).

**(b) 삭제를 부르는 지점은 정확히 둘이다.** 지금 그 둘은 **`BrandDomainsService` 소유**인데
DNS 는 `brand-domains` 가 아니라 **구매 축**의 관심사다 → `removeForBrand` / `cleanupOrphans` 안에
Cloudflare 호출을 넣지 말고, **`domain-purchase.service.ts` 가 노출하는 훅**(`releaseDnsFor(host)`)을
부른다. ⚠️ **DNS 삭제가 실패해도 `BrandDomain` 삭제는 진행한다** — `removeForBrand` 가 Vercel 제거
실패를 `logger` + `Sentry` 로 남기고 DB 삭제를 계속하는 것과 **같은 규칙**이다(정리 작업이 서로를
막으면 고아가 양쪽에 쌓인다).

**(c) zone 은 연결 해제로 지우지 않는다.** 도메인을 우리가 계속 보유하고 갱신·재연결 가능성이
있기 때문이다. **`expired` 확정 시에만** zone 을 지운다(§9 의 만료 정리 cron) — 안 그러면
Cloudflare 계정에 zone 이 **무한 누적**된다. ⚠️ zone 삭제는 `registration.cfZoneId` 를 `null` 로
되돌리는 것과 **한 트랜잭션**이어야 재구매 시 §7-3 a 의 멱등 경로가 다시 성립한다.

### 18-3. ⚠️ 우리 카드가 죽으면 전 브랜드 구매가 동시에 실패한다

`registrations` 는 **Cloudflare 계정 기본 결제수단**에 청구한다. 그게 만료·한도초과로 실패하면
**모든 브랜드의 구매가 동시에 6단계에서 실패**하고, 각 브랜드는 이미 우리 카드로 승인된 돈을
환불받는다(손실은 없지만 전면 장애다). 초안엔 이 축이 통째로 없었다.

- 결제수단 관련 실패는 **개별 도메인 문제가 아니므로 `failed` 로 접고 끝내면 안 된다** —
  `DOMAIN_PURCHASE_ENABLED` 를 런타임에 끌 수 없으니, **연속 실패 N건(예: 3건)이면 구매를
  자동 차단**하는 서킷브레이커를 서비스에 둔다(§18-4 의 카운터를 재사용).
- 발화 시 **어드민 SMS**(`shipment-alert.service.ts` 와 같은 경로) — 브랜드 알림이 아니다.
- ⚠️⚠️ **상태를 메모리에 두지 않는다.** 인메모리 카운터는 ① 인스턴스가 여럿이면 각자 세어
  차단이 안 걸리고 ② 재배포 한 번에 리셋되어 **카드가 죽은 채로 다시 열린다**. 판정 소스는
  §18-4 와 같은 **`BrandDomainCharge`/`BrandDomainRegistration` 행**이다 —
  "최근 N건의 registration 시도가 **전부** 결제수단 사유로 실패" 를 매 요청 시 조회한다(행 수가
  작아 비용이 무의미하다). 상태를 저장하는 새 테이블·컬럼을 만들지 말 것.
- ⚠️⚠️ **차단은 영구가 아니라 쿨다운이다(half-open).** 카드를 교체해도 과거 실패 행은 그대로
  남으므로, "최근 N건" 만 보면 **차단이 영원히 안 풀린다** — 장애를 막는 대신 장애를 하나 더
  만든다. 그렇다고 리셋 기준시각(`resetAt`)을 저장하려 하면 **그걸 담을 자리가 이 스키마에 없다**
  (싱글턴 테이블을 새로 파야 한다). 그래서 **표준 half-open 패턴**을 쓴다 — 판정에 필요한
  타임스탬프가 이미 실패 행에 있으므로 **저장이 0** 이다:

  ```
  streak = 시간 역순으로 연속된 "결제수단 사유 실패" registration 수
  open   = streak >= N(3) AND now − 가장 최근 실패 < CIRCUIT_COOLDOWN(30분)
  ```

  쿨다운이 지나면 **다음 1건이 그냥 통과한다**(half-open). 카드가 아직 죽었으면 그 1건이 실패하며
  타임스탬프가 갱신돼 다시 닫히고, 살아났으면 성공해 streak 이 끊긴다.
  ⚠️ 그 1건은 **돈을 잃지 않는다** — 결제수단 사유 실패는 정의상 §7 6단계의 확정 거절이라
  Cloudflare 가 과금하기 전이고 브랜드 카드는 즉시 환불된다(§7-2). **리셋 라우트가 필요 없는
  이유가 이것이다.**
  ⚠️ 어드민은 `GET /admin/domain-purchase/circuit`(§11)으로 streak·잔여 쿨다운·최근 실패 사유를
  본다 — **조회 전용**이고 쓰기 라우트는 없다.
- ⚠️ 차단 중 응답은 **503**(브랜드 잘못이 아니다) + "일시적으로 도메인 구매를 받을 수 없습니다".
  `DOMAIN_PURCHASE_ENABLED` 미설정과 **같은 코드(`domain_purchase_unavailable`)를 쓰지 말 것** —
  어드민이 로그에서 두 원인을 구분해야 한다.

### 18-4. ⚠️ 구매 상한 — 비용 폭주 방어

`DOMAIN_PURCHASE_ENABLED` 는 on/off 뿐이라, 버그·악용·재시도 루프가 **환불 불가 원가**를 그대로
태울 수 있다. 상한 두 개를 둔다 — ⚠️ **둘 다 `domain-purchase.service.ts` 의 코드 상수이고
env 가 아니다**(2026-08-26 정리. 근거는 §11 env 절 — 이 레포엔 env 수치 상한이 0건이고,
`=0` 오타 하나가 전 브랜드 구매를 조용히 막는다):

| 상한 | 기본 | 넘으면 |
|---|---|---|
| **계정 전체 일일 등록 건수** | 20 | 503 + 어드민 SMS. 정상 운영에선 절대 안 닿는다 |
| **브랜드당 연간 등록 건수** | 3 | 400. 실패 후 재구매는 허용하되 무한 반복은 막는다 |

⚠️ 카운트 소스는 **`BrandDomainCharge`(kind=registration, status in [paid, refunded])** 다 —
`BrandDomainRegistration.status` 로 세면 환불된 건이 빠져 **실패 루프가 상한을 우회한다.**

⚠️⚠️ **그 집합은 `pending` 을 포함하지 않아 동시 요청을 못 막는다.** charge 는 §7 3단계에 `pending`
으로 태어나 4단계에서야 `paid` 가 되므로, 그 사이에 도착한 요청들은 **서로를 보지 못한다** —
일일 상한 20 에 동시 30건이 통째로 통과할 수 있고, 상한이 막으려던 "버그·재시도 루프의 비용 폭주"
가 정확히 그 모양이다. 두 가지를 함께 지킨다:

1. **카운트에 `pending` 도 넣는다** — 집합은 `status in [pending, paid, refunded]`.
   ⚠️ 그러면 §7 흐름 11 이 `failed` 로 확정한 건은 자연히 빠져(=`failed` 는 안 센다) "실패 후
   재구매 허용" 과도 어긋나지 않는다.
2. **검사 위치는 §7 0단계가 아니라 3단계의 `FOR UPDATE` 락 안**이다. 락 밖에서 세면 세는 순간과
   insert 하는 순간 사이가 그대로 경합 창이다. ⚠️ 단 **일일 계정 상한은 브랜드 락으로 직렬화되지
   않는다**(브랜드가 다르면 락도 다르다) — 그쪽은 근사 방어로 받아들이고(20 은 정상 운영에서
   절대 안 닿는 값이다), 정밀 차단이 필요해지면 §7-1-F 각주의 advisory lock 을 그때 도입한다.

---

## 19. 구현 순서 (PR 분할) · 배포

| PR | 범위 | 배포 안전성 |
|---|---|---|
| **A** ✅ `7a5dcb7` | Prisma 모델 2 + enum 3 + `pricing/domain-price.ts` + 스펙 | 읽는 코드가 없다 |
| **B** ✅ `aedd709` | registrar 확장 + `cloudflare-dns.client.ts` + `domain-dns.ts` + 스펙 | 호출부가 없다 |
| **C** ✅ `1e7cb0f`·`6274dc2`·`2b1fb36` | `SubscriptionModule.exports` 개방 + `dunning.ts`(`retryGap`·`throwAsHttp` **추출**) + `billing-key-select.ts`(**신설** — §10) + **`findPaymentByOrderId` 어댑터 메서드**(§7-1-E) + 구매 서비스·라우트(**`FOR UPDATE` 락 · 상한 §18-4 · 서킷브레이커 §18-3** 포함) + 등록/보정 cron + e2e cron 목록 + 스펙 3종 | `DOMAIN_PURCHASE_ENABLED` opt-in |
| | ⚠️ **C 는 한 PR 에 안 들어가 셋으로 쪼갰다**: C-1(§10 추출·배선) → C-2(서비스·라우트·cron) → C-3(스펙 3종 + harness 확장). 다음에 비슷한 규모를 다룰 때 같은 축으로 자르면 된다 | |
| **D** ✅(서버) `c39c4cd`·`b770ae4` | 어드민 라우트 + klow_admin 도메인 탭(수동 연결 · **연결 해제 = §18-1a 4단계** · **서킷 조회**(§18-3, 조회 전용 — 리셋 라우트 없음)) + **DNS/zone 정리**(§18-2) + **매출 합계 노출**(§16 6번) | 운영이 먼저 눈을 갖는다. ⚠️ 연결 해제 UI 를 열기 전에 `setAutoRenew(false)` 가 반드시 배선돼 있어야 한다. ⚠️ 서킷은 쿨다운으로 스스로 풀리므로(§18-3) **어드민 화면이 늦어도 장애가 되지 않는다** |
| **E** ✅ `8c7e7c6`·`ea62df4` | 갱신 cron + dunning + auto_renew off + **만료일 전진 확인**(§9-3) + **알림 4종**(§9-2, 알림톡+SMS 폴백) + **사전 고지**(§9-1) | opt-in cron. ⚠️ 알림은 갱신보다 **먼저** 살아 있어야 의미가 있다 — 구매 완료 알림(1번)은 C 로 당겨도 된다. ⚠️⚠️ **`expiresAt < now` 정리 절과 §9-3 전진 확인은 반드시 같은 PR 이다** — 정리만 먼저 나가면 첫 갱신일에 돈 낸 브랜드의 도메인이 끊긴다 |
| **F** | klow_brand: `/settings/domain` + 말풍선 + `DomainSection` 제거 | **마지막** |

**배포 순서**

| # | 대상 | 확인 |
|---|---|---|
| 1 | `prisma migrate deploy` | expand only. 구버전 인스턴스가 새 테이블을 읽지 않는다 |
| 2 | **klow_server** | `DOMAIN_PURCHASE_ENABLED` 미설정 → 구매 503, 갱신 cron off. **아무 일도 안 일어난다** |
| 3 | **klow_admin** | 운영이 먼저 상태를 볼 수 있게. 수동 연결 경로가 여기서 열린다 |
| 4 | env 주입 + **스테이징 실전 리허설 1건** | 환불 불가라 **이것이 유일한 실전 검증**이다(§0) |
| 4.5 | ⚠️ **선행 리드타임** — 도메인 구매 **약관**(§18-1, 법무 검토)**만 5단계를 막는다.** 알림톡 **템플릿 4개 승인**(§9-2)은 **막지 않는다** | 약관은 구매 다이얼로그가 링크해야 하므로 **1단계와 같이 착수**. 템플릿은 env 가 전부 선택이라(§11) 미승인 상태에선 **SMS 폴백이 대신 나가고**, 승인되는 대로 한 줄씩 채우면 그 종류만 알림톡으로 승격된다 — 카카오 심사를 기다리며 배포를 미루지 말 것 |
| 5 | **klow_brand** (마지막) | ⚠️ 2보다 먼저 나가면 `/settings/domain` 이 없는 라우트를 친다 |
| 6 | ~~`BRAND_DOMAIN_RENEWAL_CRON_ENABLED=true`~~ **없어졌다**(§11 — 마스터 게이트에 흡수). 대신 **§0 7번(만료일 전진 관측)** 을 운영 캘린더에 건다 | 갱신 cron 은 2단계부터 이미 돌고 있고 11개월간 due 행이 0이라 **켤 일이 없다**(잊어서 만료되는 경로가 사라졌다). 캘린더에 남는 건 실측 하나뿐 — §9-3 의 `GRACE` 를 정하는 유일한 기회이고, 놓치면 1년을 더 기다려야 한다 |

⚠️⚠️ **`POST /v1/brand/domains` 제거를 2단계에 넣지 말 것.**
구 `DomainSection`(그걸 호출한다)은 5단계에서야 사라지므로 그 사이 창 전체가 404 이고, **"서버
먼저" 원칙이 이 라우트에서만 거꾸로 뒤집힌다.**
(⚠️ `DELETE /v1/brand/domains/:id` 는 3차 점검에서 **제거가 아니라 조건부 차단**으로 바뀌었으므로
(§11) 이 문제에서 빠진다 — registration 이 없는 도메인에는 종전 동작 그대로다.) 이 레포 관례(`?campaign=` 레거시 별칭을 klow_web
배포까지 살려 둔 선례)대로 **한 릴리스 남겼다가 5단계 이후 제거**하거나, 라우트 제거를 PR **F 의 서버
동반 PR** 로 옮긴다. (운영 미배포 기능이라 실사용자는 0이지만, 스테이징에 수작업으로 붙여 둔 도메인이
있으면 4단계에서 어드민 탭으로 관리 가능함을 먼저 확인할 것.)

⚠️ **롤백**: 4 이후에 롤백하면 이미 구매된 registration 행을 구버전 서버가 읽지 않아 **cron 이
멈춘 채 등록만 진행된다.** 롤백 시엔 반드시 어드민에서 `action_required` 목록을 눈으로 확인.

---

## 20. 검증

### 신규 스펙

| 파일 | 잠그는 것 |
|---|---|
| ✅ `src/pricing/__tests__/domain-price.spec.ts` | 마진 1.3 · VAT 1.1 · **1,000원 올림 경계**(…999→1000, 1000→1000, 1001→2000) · `DOMAIN_FX_MIN/MAX` 밖이면 throw · `parseRegistrarCostUsdCents` 실패 시 throw(**0원 청구 금지**) |
| ✅ `brand-domains/__tests__/domain-purchase.spec.ts` (24개) | ⭐ 결제 실패 → **Cloudflare 호출 0회** · ⭐⭐ 4xx → `cancelPayment` **1회** + charge=refunded · ⭐⭐ **타임아웃 → `cancelPayment` 0회** + reg=paid 유지 · ⭐⭐ **netCancel 분기에서 charge 가 `failed` 가 아니라 `pending`**(§7-1 E) · ⭐⭐ **동시 2요청 → registration 1건**(§7-1 D 행 잠금) · 삭제된 카드(`deletedAt`) → **청구 시도 0회** · 진행중 1건 → 409 · `expectedAmountKrw` 불일치 → 409 · 구매 시점 `domain-check` 가 **quotes 캐시를 안 탄다** |
| ✅ `.../domain-registration-poll.spec.ts` (19개) | `paid`+404 → 3회 재시도 후 환불 · ⭐⭐ **그 재시도가 `createRegistration` 을 실제로 다시 부른다**(§7 흐름 8 — 카운터만 올리고 환불하면 실패) · **단 그 등록이 우리 것이면 환불 안 함**(§7 흐름 8번) · ⭐⭐ **같은 host 로 다른 브랜드의 `registered` 행이 있으면 → 환불한다**(§7-1-F — "계정에 보임" 으로 판정하면 이 케이스가 사람 큐로 샌다) · `in_progress→succeeded→registered` · `failed→환불` · **`action_required` 자동 환불 안 함** · `charge=pending` 10분 경과 → NicePay 재조회 후 승격/실패 확정, **금액 불일치는 비전이** · ⭐⭐ **`lastAttemptAt` 이 null 인 `charging`+`pending` 건도 `createdAt` 기준으로 집힌다**(§7 흐름 11 — 빠지면 재구매 영구 차단) · 연결 403(`subscription_required`) → **환불하지 않고 `registered` 유지** |
| ✅ `.../domain-dns.spec.ts` (18개) | **`proxied:false` 고정** · apex=A / www=CNAME · rank1 값 사용(하드코딩 아님) · **빈 recordValue 면 주입 스킵** · **멱등**(같은 값 → create 0회 / 다른 값 → update) · ⭐⭐ **`remove` 가 우리 이름·타입만 고른다**(zone 의 MX·TXT·무관 A 레코드는 **건드리지 않음** — §18-2) · `desired=[]` → 우리 레코드만 전부 remove |
| ✅ `.../domain-purchase-limits.spec.ts` (15개) | ⭐ 일일 계정 상한 초과 → 503 + **Cloudflare 호출 0회** · 브랜드당 연간 상한 초과 → 400 · ⭐⭐ **환불된 건도 카운트에 들어간다**(`BrandDomainCharge` 기준 — `registration.status` 로 세면 실패 루프가 상한을 우회한다) · ⭐⭐ **`pending` 도 카운트에 들어간다**(§18-4 — 빠지면 동시 요청이 상한을 통째로 통과) · ⭐ **상한 검사가 `FOR UPDATE` 락 안에서 일어난다** · 연속 실패 N건 → 서킷브레이커 차단(§18-3) · ⭐⭐ **쿨다운(30분) 경과 후 다음 1건은 통과한다**(§18-3 half-open — 이 단언이 없으면 차단이 영구화된다) · ⭐ **결제수단 사유가 아닌 실패는 streak 을 쌓지 않는다** |
| `.../domain-notify.spec.ts` (신규) | ⭐⭐ **알림톡 미설정/실패 → SMS 폴백이 실제로 발송**된다(§9-2 — 폴백이 없으면 갱신 실패가 무음) · 수신번호 없음 → 발송 스킵 + warn · 사전 고지는 **만료 37일 전 1회**(중복 발송 없음) |
| `.../domain-release.spec.ts` (신규) | ⭐⭐ **연결 해제가 `setAutoRenew(false)` 를 1회 부른다**(§18-1a — 안 부르면 만료일에 우리 카드가 긁힌다) · ⭐⭐ **그 호출이 실패하면 `BrandDomain` 을 지우지 않는다**(부분 해제 금지) · `status='released'` + `brandDomainId=null` · DNS 삭제 실패해도 해제는 완료 · `released` 도메인 재연결 시 `setAutoRenew(true)` 복구 · ⭐⭐ **registration 이 없는(브랜드 소유) 도메인 해제는 `setAutoRenew` 를 0회 부른다**(§18-1a — 부르면 안 산 도메인을 조회해 해제가 통째로 막힌다) · ⭐ **브랜드 `DELETE` 는 registration 이 걸린 행에만 409, 그 밖은 종전대로 삭제**(§11) |
| `.../domain-renewal.spec.ts` | 리드타임 30일 · **고지 리드타임 37일이 청구보다 앞선다**(§9-1 — 두 상수가 같아지면 실패) · dunning 0/1/3/7 · 4회 소진 → `setAutoRenew(false)` · 갱신가 2배 초과 → 청구 안 함 · `expiresAtIsEstimated` → 청구 안 함 · **만료 전까지 Vercel 연결 유지** · `expired` 확정 시 **zone 삭제 + `cfZoneId=null`**(§18-2 c) · ⭐⭐ **갱신 charge=paid 후 만료일이 전진하면 `expiresAt` 이 갱신된다**(§9-3) · ⭐⭐ **`autoRenew=true` 인데 `expiresAt < now` 면 `BrandDomain` 을 지우지 않는다**(§9-3 — 이 단언이 없으면 돈 낸 브랜드의 브랜드관이 만료일에 죽는다) · ⭐ **D+GRACE 까지 전진 없음 → `action_required` + 어드민 알림, 연결은 유지** |
| ✅ `__tests__/harness.ts` **확장**(PR C-3 에서 구매 축까지) | `brandDomainRegistration`·`brandDomainCharge`·`billingKey` 인메모리 + Nicepay/Cloudflare 스텁. ⚠️ 기존 원칙대로 **스텁이 진짜보다 관대하면 스펙이 아무것도 못 잡는다** — `pgTid @unique` 와 `host @unique` 를 반드시 던지게 할 것. ⚠️⚠️ **`netCancel` 스텁은 실패해도 절대 throw 하지 않아야 한다**(진짜가 그렇다 — throw 하는 스텁을 쓰면 §7-1 E 테스트가 아무것도 못 잡은 채 통과한다). ⚠️ 동시성 테스트를 위해 `$queryRaw … FOR UPDATE` 를 **실제로 직렬화**하는 스텁이 필요하다(no-op 으로 두면 §7-1 D 가 통과해도 의미가 없다 — 차라리 락 획득 호출 여부를 단언할 것) |

> 🧰 **D·E 를 쓰는 사람에게 — harness 에 이미 있는 것**(PR C-3, 다시 만들지 말 것):
> `seedRegistration()` · `seedCharge()` · `purchaseService()` 팩토리 ·
> prisma 스텁(`brandDomainRegistration`·`brandDomainCharge`·`currencyFxRate`·`$transaction`·
> `$queryRaw`) · 벤더 스텁 4종(`registrar()`·`dnsClient()`·`nicepay()`·`config()`) ·
> 호출 기록 배열(`registrarCalls`·`nicepayCalls`·`dnsCalls`·`lockCalls`) ·
> 시나리오 스위치(`checkRows`·`registrarError`·`registrationStatus`·`chargeError`·
> `payments`·`paymentLookupFails`·`fxRate`).
> D 는 여기에 **`setAutoRenew` 호출 카운트 단언**만 얹으면 되고(스텁은 이미 기록한다),
> E 는 `brandDomainCharge` 에 `kind='renewal'` 행을 심으면 된다.
>
> ⚠️ **`brand DELETE` 조건부 차단(§11)은 C-2 에서 이미 구현했다** — 스펙만 D 의
> `domain-release.spec.ts` 에 남아 있다. 구현을 다시 하지 말 것.

### 무변경으로 통과해야 하는 것 (통과 안 하면 설계가 샌 것)

`domain-pairing` · `verified-origin` · `resolve-host` · `domain-status` · `domain-host` ·
**`domain-search`**(가격 미노출 단언) · `domain-wishes` · `origin-policy` · `origin-exempt`.
**수정이 필요한 기존 파일은 `test/app.e2e-spec.ts`(cron 9→11) 하나뿐**이다.

> ✅ **PR C 시점 실측(2026-08-26)**: 9종 전부 **스펙 파일 무변경으로 통과**한다.
> ⚠️ 다만 PR C-2 에서 `domain-pairing`·`verified-origin` 이 **3건 빨간불이 났다** — 원인은
> 설계 누수가 아니라 **`removeForBrand` 의 조건부 차단(§11)이 추가한 registration 조회를
> harness 스텁이 몰라서**였다. 아래 "harness.ts 확장" 행이 예고한 그 작업이고, **스펙 파일은
> 한 줄도 고치지 않고** 스텁에 모델을 더해 복구했다. 같은 증상이 D·E 에서 또 나면
> **먼저 harness 를 의심할 것** — 스펙 파일을 고치는 순간이 설계가 샌 순간이다.

⚠️ 이 무변경이 성립하는 **조건이 둘** 있다 — ① `MAX_DOMAINS_PER_BRAND` 를 **3 그대로** 둔다
(`domain-host.spec.ts:131` 이 `>= 3` 을 단언한다 — §2) ② `domain-search` 응답에 가격을 얹지
않는다(§6·§11). 둘 중 하나라도 어기면 "무변경 통과"가 깨지고, **그건 설계가 샜다는 신호**다.

### 검증 3층 (CLAUDE.md)

1. `npm run typecheck` — **`tsconfig.json` 과 `tsconfig.scripts.json` 둘 다**
   (`npx tsc --noEmit` 만 쓰면 `src/` 밖을 구조적으로 못 본다)
2. `npm run test:e2e` — cron **11개** + DI 그래프(`SubscriptionModule.exports`)
3. `npm run start` — env 가드 + 라우트 매핑. ✅ **PR C 시점 실측 318**(315 + 구매 3개:
   `POST quotes` · `POST purchase` · `GET registration`). D 가 어드민 라우트를 더하면 또 는다 —
   **마지막 PR 에서 워크스페이스 `CLAUDE.md` 의 라우트 수를 실측값으로 갱신할 것.**
   ⚠️ 포트 4000 은 메인 체크아웃 dev 서버가 점유 중일 수 있다 → `PORT=4001 npm run start`
4. `npx eslint <바꾼 파일>` 로 좁혀 쓸 것(`npm run lint` 는 `--fix` 를 물고 있어 무관한 파일의
   포맷 부채까지 건드린다)

### 수동 E2E (스테이징) — 환불 불가라 이것이 유일한 실전 검증

1. `/start` 찜 → 스튜디오 말풍선 → `/settings/domain`
2. 견적 금액이 `원가 × fx × 1.3 × 1.1` 올림과 일치하는지 계산기로 대조
3. 값싼 `.shop`/`.xyz` 구매 → NicePay 승인 → 등록 → **Cloudflare 대시보드에서 zone·레코드·
   `proxied:off`·만료일을 눈으로 확인**
4. `active` → 그 도메인으로 브랜드관이 뜨는지, `www` 가 307 하는지
5. 어드민 탭에 원가/판매가/만료일, **수동 연결로 `.co.kr` 이 붙는지**
6. 실패 경로: 이미 팔린 도메인 → 409, 결제 실패 카드 → **Cloudflare 호출이 없었는지 로그 확인**
7. 구매 다이얼로그에 **2년차 예상가 · 환불 불가 · 이전 불가** 세 고지가 다 보이는지
8. 구매 완료 알림톡(또는 SMS 폴백)이 실제로 도착하는지 — ⚠️ 템플릿 미승인 상태에서 **SMS 로
   떨어지는지**까지 확인해야 §9-2 의 폴백이 검증된다
9. ⭐ **연결 해제 → Cloudflare 대시보드에서 A/CNAME 이 사라졌는지 · zone 과 무관한 TXT 를 하나
   미리 넣어 두고 그게 남아 있는지**(§18-2 a 의 핵심 안전장치)
10. ⭐ **어드민 수동 연결로 붙인 `.co.kr` 을 브랜드가 스스로 해제할 수 있는지**(§11 조건부 `DELETE`)
    — 그리고 **구매 도메인은 409** 로 막히는지. 이 두 가지가 한 화면에서 갈린다.
11. ⭐⭐ **만료 리허설은 실측으로 대체할 수 없다 → 스텁으로 잠근다.** §9-3 은 1년 뒤에야 실물이
    나오므로 수동 E2E 대상이 아니고, `domain-renewal.spec.ts` 의 두 ⭐⭐ 단언이 **유일한 방어**다.
    배포 전에 그 스펙이 실제로 실패하는지(단언을 일부러 깨 보고) 확인할 것.

### 문서 갱신 (구현과 같은 PR 에서)

- `docs/server/modules/brand-domains.md` — 신규 라우트·모델·cron, 소비자 목록 갱신, 특히
  **"타임아웃에는 결제를 취소하지 않는다"는 규칙과 그 이유**(Cloudflare 축 §7-1 A · NicePay 축 §7-1 E).
  ⚠️ **「알려진 갭」 2건은 지우지 말 것** — 어드민 수동 연결 도메인에서는 그대로 유효하다(§1)
- [`implementation-plan.md`](./implementation-plan.md) §9 불변식 표 — 새 F-번호 **5개** 후보:
  **"구매는 `FOR UPDATE` 로 직렬화한다"** · **"`netCancel` 불확정 건을 `failed` 로 접지 않는다"** ·
  **"연결이 실패해도 등록된 도메인은 환불하지 않는다"** ·
  ★ **"`autoRenew=true` 인 행은 `expiresAt` 이 지나도 정리하지 않는다"**(§9-3) ·
  ★ **"환불 금지 판정은 계정이 아니라 registration 행 단위다"**(§7-1-F).
  다섯 다 "어기면 돈을 잃거나 서빙이 끊긴다" 급이다
- `docs/server/modules/subscription.md` — `exports: [NicepayBillingAdapter]` 개방과 그 경계
- 이 문서 — 상태 블록을 실제 진행에 맞춰 갱신
- 워크스페이스 `CLAUDE.md` — 라우트 수 + Key Facts 항목
