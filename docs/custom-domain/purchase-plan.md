# 커스텀 도메인 대행 구매 (P6) — KLOW 가 사서 연결하고 연 이용료를 받는다

> **현재 상태: 📝 계획 수립 완료 (2026-08-25) · 코드 미착수.**
> 이 문서가 이 기능의 **정본**이다. 착수 전 [§0 실측 항목](#0-착수-첫날-실측--여기서-답이-갈리면-7-3-이-바뀐다)
> 을 먼저 끝낼 것 — 거기서 답이 갈리면 §7-3 의 연결 절차가 바뀐다.
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

### 부수 효과 — `brand-domains.md` 의 알려진 갭 2건이 닫힌다

| 갭 | 왜 닫히나 |
|---|---|
| **댕글링 DNS → 브랜드 간 도메인 인계** | DNS 를 우리가 소유하므로 브랜드 A의 연결을 끊을 때 레코드도 우리가 지운다. 남의 도메인이 Vercel 을 계속 가리키는 상태 자체가 성립하지 않는다 |
| **미검증 도메인 스쿼팅이 영구적** | 호스트 직접 입력이 브랜드 화면에서 사라진다. 자기 것이 아닌 호스트를 잡아 두는 경로가 없다 |

---

## 2. 확정 요구사항 (2026-08-25)

| 항목 | 결정 |
|---|---|
| 진입 | 스튜디오 폰 목업 위 링크바에 **"커스텀 도메인 연결하기" 말풍선**(미연결 + 구독 active) |
| 페이지 | **`/settings/domain`**. 설정 허브에는 진입 카드 |
| 도메인 소스 | 찜 목록 + 그 자리 검색 |
| 소유 | **KLOW 소유** (우리 Cloudflare 계정 등록) |
| 가격 | 원가(USD) × `resolveFxRate` × **1.3 = 공급가** → ×1.1 VAT → **1,000원 올림** = 청구가 |
| 결제 | **기존 구독 `BillingKey` 즉시 청구**(카드 재입력 없음) |
| 수작업 DNS | **브랜드 화면에서 완전 제거** · 어드민에만 수동 연결 유지 |
| 개수 | 브랜드당 **1개** (+`www` 자동) |
| 갱신 미납 | 0/1/3/7 dunning → **`auto_renew=false`** → 만료 |
| 어드민 | `/brands/[id]` **도메인 탭** + 수동 연결 |

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

- **프리미엄 도메인**은 explicit fee acknowledgement 가 필요하다 → 자동 승인하지 않고 사람에게 넘긴다.
- `reason: extension_not_supported_via_api` — 대시보드는 되는데 API 는 안 되는 TLD 가 있다.
- **transfer API 없음**(beta). 브랜드가 "우리 도메인 넘겨달라"고 하면 Cloudflare 대시보드 수동 작업이다.

---

## 0. 착수 첫날 실측 — 여기서 답이 갈리면 §7-3 이 바뀐다

스테이징 자격증명으로 **값싼 도메인 1개를 실제로 사서** 확인한다. **환불이 안 되므로 이것이 유일한
실전 검증**이고, 문서로 대체할 수 없다.

1. **등록 시 Cloudflare zone 이 자동 생성되는가.** 공식 문서에 언급이 없다(Registrar 로 산 도메인은
   "Cloudflare 네임서버에 남아야 한다"고만 돼 있다). → 코드는 `GET /zones?name=` 조회 후 없으면
   `POST /zones` 하는 **멱등 경로**로 짜서 양쪽 결과를 모두 커버한다.
2. `registration-status` 응답에 **만료일이 실려 오는가** — `expiresAtIsEstimated` 컬럼의 존재 이유다.
3. **토큰 스코프.** 지금 `CLOUDFLARE_REGISTRAR_TOKEN` 은 `.env.example` 이 *"가능하면 읽기 전용으로"*
   라 안내해 발급됐을 수 있다. **Registrar Write + Zone DNS:Edit** 가 필요하다.
4. 계정 **default registrant contact** 설정 여부(없으면 `registrations` 가 거절된다).
5. `registrations` 가 동기로 `succeeded` 를 주는 비율과 `in_progress` 의 실제 소요 — 폴링 주기의 근거.

### 벤더 계약 (2026-08-25 확인)

- `POST /accounts/{id}/registrar/domain-check` — ≤20개/요청, 레지스트리 직조회.
  `{name, registrable, tier, pricing:{currency, registration_cost, renewal_cost}, reason?}`
- `POST /accounts/{id}/registrar/registrations` — `{domain_name, years?, auto_renew?, privacy_mode?}`.
  **201/202** + `state: in_progress|succeeded|failed|action_required|blocked`.
  ⚠️ **계정 기본 결제수단에 즉시 청구되고 환불이 안 된다.**
  ⚠️ **`auto_renew` 기본이 `false`** — 명시하지 않으면 1년 뒤 도메인이 소멸한다(문서는 false,
  블로그는 true 로 갈려 있어 **반드시 명시 전달**).
- `GET .../registrations/{domain}/registration-status` — ⚠️ **`action_required`·`failed` 에서는
  폴링을 멈추고 사람에게 넘긴다**(문서 명시).
- **갱신 API 없음**(beta). 실제 갱신은 `auto_renew` 로 **만료일에** 일어난다 → §7 리드타임의 근거.
- `renewal_cost ≠ registration_cost` 인 TLD 가 많다(첫해 할인) → **둘 다 스냅샷**한다.

---

# 서버 (klow_server)

## 4. 스키마 — 신규 모델 2 · enum 3

### ⚠️⚠️ `BrandDomainStatus` 는 한 글자도 건드리지 않는다

세 가지 이유로 기존 enum 에 못 얹는다:

1. **행이 존재할 수 없는 시점에 상태가 필요하다.** `BrandDomain` 은 Vercel `addProjectDomain`
   성공 **이후에만** insert 된다(`registerDomain`). 그런데 "카드 청구 성공, 등록 대기"는 그
   도메인이 세상에 존재하기도 전이다.
2. **`pendingGiveUpWhere` 가 죽인다.** 7일 지난 `pending` 을 `updateMany` 로 `error` 처리하는데,
   등록 대기 행이 거기 걸리면 **결제 기록이 조용히 error 로 덮인다**.
3. **`decideDomainStatus` 는 Vercel 두 응답의 순수 함수**다. 결제·레지스트라 축은 입력이 아예 다르다.

이 분리 덕에 `verified-origin` · `resolve-host` · `domain-status` · `domain-host` 스펙이 **0줄
수정**이다. **그것들이 수정돼야 한다면 설계가 샌 것이다.**

```prisma
/// KLOW 가 브랜드 대신 Cloudflare Registrar 에서 직접 구매해 **소유하는** 도메인 1개 = 1행.
/// BrandDomain(Vercel 연결·DNS 검증 축)과 분리한 이유는 수명과 실패 모드가 다르기 때문이다:
/// 이 행은 **카드 청구가 성공한 순간부터** 존재하고(그때 BrandDomain 은 만들 수 없다),
/// 브랜드가 탈퇴해도 **우리가 1년치 원가를 이미 냈으므로** 남아야 한다.
model BrandDomainRegistration {
  id      String @id @default(cuid())
  brandId String
  /// 소문자 punycode apex. 정규화는 modules/brand-domains/domain-host.ts 가 소유한다.
  /// ⚠️ @unique 를 걸지 않는다 — 실패·만료 후 재구매를 영구히 막는다. "진행중 1건" 은 서비스
  ///    트랜잭션이 강제하고 최종 방어선은 BrandDomain.host @unique 다
  ///    (BrandDomain 이 @@unique([brandId, role]) 를 안 건 것과 같은 근거 — Prisma partial unique 미지원).
  host    String @db.VarChar(253)

  status  BrandDomainRegistrationStatus @default(charging)

  /// Cloudflare 원문 state. ⚠️ 재가공하지 않는다(beta 라 값이 늘 수 있다).
  cfState        String?  @db.VarChar(32)
  /// DNS 주입의 유일한 키.
  cfZoneId       String?  @db.VarChar(64)
  /// 등록 요청이 접수조차 안 된 경우의 재시도 횟수. 3회 소진 시 환불.
  submitAttempts Int      @default(0)

  /// 레지스트리 만료일. 정본은 Cloudflare registration-status 응답.
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
  brand     Brand    @relation(fields: [brandId], references: [id])
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
  /// 감사·마진 리포트용 스냅샷. 청구 시점 값을 그대로 얼린다.
  costUsdCents    Int
  fxRateKrwPerUsd Float
  marginRate      Float
  supplyKrw       Int

  pgProvider    String?
  pgTid         String?  @unique   // ⚠️ 같은 승인이 두 행에 들어가면 회계가 갈린다
  attemptCount  Int      @default(0)
  lastAttemptAt DateTime?
  paidAt        DateTime?
  refundedAt    DateTime?
  failReason    String?  @db.VarChar(500)
  /// 이 청구가 덮는 등록 기간.
  periodStart   DateTime
  periodEnd     DateTime
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
  action_required  /// Cloudflare 가 사람 개입 요구. **자동 환불 금지.**
  failed           /// 등록 실패 + 환불 완료.
  expired          /// 갱신 미납 확정 → 만료.
}
enum BrandDomainChargeKind   { registration renewal }
enum BrandDomainChargeStatus { pending paid failed refunded }
```

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
`subscription-price.ts` 의 형제이고 배럴 `src/pricing/index.ts` 에 `export * from './domain-price'`.

```ts
export const DOMAIN_MARGIN_RATE = 1.3;   // env DOMAIN_MARGIN_RATE 로 덮을 수 있다(subscription-price 관례)
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

## 6. Cloudflare 클라이언트 — 파일 2개 + 순수 헬퍼 1개

### `cloudflare-registrar.client.ts` 확장

추가: `checkDomains(names[≤20])` · `createRegistration` · `getRegistrationStatus` · `setAutoRenew`.

- ⚠️ **파일 상단의 설계 전제 주석을 지우지 말고 갱신한다.** 지금 이렇게 적혀 있다:
  > `POST /registrar/domain-check` 와 `POST /registrar/registrations` 는 이 파일에 존재하지 않는다
  > — 후자는 계정 기본 결제수단에 **즉시 청구되고 환불이 안 된다**. "과금이 가능한 코드 경로를
  > 만들지 않는다"가 이 클라이언트의 설계 전제다. 등록 기능을 붙일 사람은 그 전제를 먼저 다시
  > 검토할 것.

  전제가 바뀐 **사실**과 **무엇으로 대체했는지**(§10 `DOMAIN_PURCHASE_ENABLED` opt-in 게이트 +
  §8 의 4가지 규칙)를 그 자리에 쓴다. 지우기만 하면 다음 사람이 안전장치의 존재를 모른다.
- `createRegistration` 타임아웃 **30s**(검색은 10s — 사람이 타이핑하며 기다리는 축이지만, 이쪽은
  돈이 걸린 축이다).
- ⚠️ `auto_renew: true` **명시 전달**.
- ⚠️⚠️ `AbortError`·5xx 는 **`CloudflareRegistrationIndeterminateError`** 로 던진다 — §8 (A) 를
  타입으로 강제하기 위한 전용 예외다.
- 프리미엄 fee acknowledgement 요구 응답은 **자동 승인하지 않는다** → `action_required`.

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
export function planDnsConvergence(desired, existing): { create; update; skip };
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

## 7. 구매 오케스트레이션 — `domain-purchase.service.ts` (신규)

`brand-domains.service.ts`(719줄)에 넣지 않는다. **순서와 보상이 이 파일의 전부**다.

```
[요청 안에서]
0 게이트   구독 active · primary BrandDomain 0개 · 진행중 registration 0건 · DOMAIN_PURCHASE_ENABLED
1 재확인   domain-check 단건 → registrable !== true 면 409 domain_unavailable  (찜은 오래된 스냅샷이다)
2 재견적   quoteDomainPriceKrw() → 클라 expectedAmountKrw 대조, 불일치 → 409 domain_price_changed
3 DB      Registration(charging) + Charge(pending) 한 트랜잭션
4 청구     chargeBilling({ bid, amountKrw, orderId: orderIdFrom(charge.id), goodsName })
           ├ NicepayBillingError → charge=failed / reg=failed → throwAsHttp(400). 돈 안 나감.
           └ 타임아웃·네트워크 → netCancel(orderId) → 동일 처리
5 DB      charge=paid(pgTid) / reg=paid        ← ★ "돈은 받았고 등록은 아직" 의 정본 상태
6 등록     createRegistration({ domain_name, years:1, auto_renew:true })
           ├ 201/202 → reg=registering (cfState 저장)
           ├ 4xx 확정 거절 → cancelPayment(tid) → charge=refunded / reg=failed → 400
           └ 타임아웃·5xx → ★★ 취소하지 않는다. reg=paid 로 두고 cron 이 진실을 조회
7 응답     { registration }   (화면은 폴링)

[cron 이 하는 것 — §9]
8  reg=paid        → registration-status 조회
                     ├ 존재 → registering 으로 승격 (6번 타임아웃의 회복 경로)
                     └ 404  → 접수 자체가 안 됐다 → submitAttempts++ , 3회 소진 시 cancelPayment → failed
9  reg=registering → succeeded → registered(+expiresAt) / failed → 환불 / action_required|blocked → 정지
10 reg=registered  → §7-2 connectDomain
```

### 7-1. 반드시 지킬 4가지

| # | 규칙 | 안 지키면 |
|---|---|---|
| **A** | ⚠️⚠️ **타임아웃 ≠ 실패.** `registrations` 타임아웃·5xx 에 `cancelPayment` 를 **부르지 않는다** | Cloudflare 는 등록했는데(환불 불가) 브랜드 돈은 돌려줌 → **순손실 2배**. 전용 예외 타입 `CloudflareRegistrationIndeterminateError` 로 이 분기를 타입으로 강제 |
| **B** | charge 행을 청구 **전에** 만들고 `orderId = orderIdFrom(charge.id)` | 구독 정기청구가 `invoice.id` 를 seed 로 쓰는 것과 같은 근거 — 재시도가 같은 orderId 를 못 쓰면 **이중 승인** |
| **C** | `pgTid @unique` (SubscriptionInvoice 미러) | 같은 승인이 두 행에 들어가면 회계가 갈린다 |
| **D** | **진행중 1건 락** + 컨트롤러 `@Throttle({limit:3, ttl:60_000})` | 연타 = **두 번 구매**(환불 불가) |

### 7-2. 환불 불가의 **주체**를 혼동하지 말 것

- **Cloudflare → 우리**: 환불 불가. 등록이 `succeeded` 면 그 돈은 나갔다.
- **우리 → 브랜드**: NicePay `cancelPayment` 로 언제든 취소 가능.

그래서 6번 4xx / 폴링 `failed` 는 **Cloudflare 가 아직 과금하지 않은** 케이스라 손실 0이고,
`action_required` 는 손실 가능성이 있어 **자동 환불을 막는다**(사람이 판단).

⚠️ 브랜드 UI 의 "환불 불가" 고지는 **등록 성공 후**에 대한 것이다. 서버가
`agreedNonRefundable: true` 를 받지 않으면 400(전자상거래법).

### 7-3. `connectDomain(registration)` — 등록 완료 후 연결 (멱등)

```
a. zone 확보: cfZoneId ?? getZoneIdByName(host) ?? createZone(host)   → registration.cfZoneId 저장
b. BrandDomainsService.attachPurchasedDomain(brandId, host)
     내부는 기존 createForBrand 경로 재사용 → 여기서 recordType/recordValue 가 확정된다
c. dns 수렴(zoneId, { type, name, content: recordValue, proxied: false })
d. apex 면 www 페어도 같은 방식
e. refreshOne → active → registration.active
```

⚠️ **b 가 c 보다 먼저다** — 무슨 레코드를 꽂을지는 Vercel 응답(`recommendedRecord`)이 알려준다.

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

## 8. cron — 신규 2개, 파일 1개

`src/modules/brand-domains/brand-domain-registrations.cron.ts`.
규칙 5는 "`@Cron` 은 `*.cron.ts` 파일에"이지 "파일당 하나"가 아니다.

```ts
@Cron('*/2 * * * *', { timeZone: 'Asia/Seoul', name: 'brand-domain-registration' })
// paid → registering → registered → active. 재진입 가드 running(기존 cron 선례).
// kill switch: BRAND_DOMAIN_REGISTRATION_CRON_ENABLED === 'false' 일 때만 off (기존 관례)

@Cron('30 0 * * *', { timeZone: 'Asia/Seoul', name: 'brand-domain-renewal' })
// 갱신 청구 + dunning. ⚠️ 00:00 의 brand-subscription-billing 과 30분 띄운다(NicePay 동시 부하).
// ⚠️⚠️ kill switch 방향이 **반대다**: BRAND_DOMAIN_RENEWAL_CRON_ENABLED !== 'true' 면 off.
//    돈이 나가는 cron 은 opt-in 이어야 한다 — 운영 배포 전 실수로 도는 것을 막는다.
//    이 비대칭은 의도이고, 형제 cron 과 다른 이유를 여기 적어 둔다.
```

### 기존 cron 에 얹지 않는 이유

| 후보 | 기각 사유 |
|---|---|
| `brand-domain-verify` (5분) | 그 cron 은 **Vercel 만 태우고 돈을 만지지 않는다.** 결제 재시도·환불을 얹으면 재진입 가드 하나가 두 종류의 부작용을 덮고, `BRAND_DOMAIN_CRON_ENABLED=false` 를 내리는 순간 **미완료 결제 복구까지 멈춘다.** 사고 시 한쪽만 끌 수 있어야 한다 |
| `brand-subscription-billing` (일 1회) | 등록 폴링은 **분 단위**여야 한다(브랜드가 화면에서 기다린다). 게다가 `SubscriptionModule → BrandDomainsModule` **순환**이 생긴다 |

### ⚠️ `test/app.e2e-spec.ts` — cron 9개 → **11개**

**테스트 제목 문자열(`'cron 9개가 …'`)과 `expect` 배열을 둘 다** 고친다(제목만 두면 다음 사람이
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
- ⚠️ `expiresAtIsEstimated = true` 인 행은 **자동 청구하지 않는다** — 어드민 알림만.
- dunning 실패 확정(`retryGap(attemptCount) === null`) → `setAutoRenew(false)` + `expired` 예약.
  ⚠️ **`BrandDomain` 을 즉시 지우지 않는다** — 만료일까지는 정상 서빙된다. 만료 후 정리는
  `cleanupOrphans` 가 아니라 이 cron 이 `expiresAt < now` 로 `removeForBrand` 를 태운다.

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

DI 없이 공유할 조각 3개(전부 순수 파일 → 순환 위험 0):

| 조각 | 어디로 | 왜 |
|---|---|---|
| `retryGap` (dunning 0/1/3/7) | **`subscription/dunning.ts`** 신규 | 지금 `subscription.service.ts:1138` 의 **비-export 모듈 로컬 함수**다. 두 벌이 되면 반드시 갈린다. ⚠️ `common/` 으로 올리지 않는다 — dunning 은 배관이 아니라 **정책**이라 소유 모듈이 갖는 게 규칙 3 휴리스틱에 맞다(`common/cookies.ts` vs `modules/web-auth/session.ts` 선례) |
| `DEFAULT_BILLING_KEY_WHERE` | **`subscription/billing-key-select.ts`** 신규 | "어느 키가 정본인가"가 두 벌이 되면 안 된다(`brands/brand-selects.ts` 선례) |
| `orderIdFrom` | `NicepayBillingAdapter` 의 static 으로 승격 | NicePay orderId 규칙은 결제 배관이라 어댑터가 소유하는 게 맞다 |

## 11. 라우트 · zod · env

| 라우트 | 처분 |
|---|---|
| `GET /v1/brand/domains` | 유지 |
| `POST /v1/brand/domains` (host 직접) | **브랜드에서 제거 → 어드민으로 이관** |
| `POST /v1/brand/domains/:id/check` | 유지(구매 도메인도 DNS 수렴이 늦으면 "지금 확인"이 자연스럽다) |
| `DELETE /v1/brand/domains/:id` | **제거** — ⚠️ 우리가 산 도메인을 브랜드가 지우면 Vercel 에서만 빠지고 **우리는 1년치 원가를 그대로 물고** registration 이 고아가 된다. 화면은 "연결 해제 문의" 안내 |
| `GET /v1/brand/domains/search` · `/v1/brand/domain-wishes/*` | 유지(찜이 1급 소비자가 된다) |

**신규(브랜드)** — `brand-domain-purchase.controller.ts`
(형제 3개와 같은 관례로 **파일 분리** — `requireBrandId` 불변식이 파일마다 다르다)

- `POST /v1/brand/domains/quotes` `{hosts[≤20]}` → 찜 목록에 가용성 + 가격을 붙인다.
  `domain-check` 가 20개/요청이라 **배치가 맞다**. `DomainSearchService` 와 같은 **5분 캐시**
  (찜 20개 × 유료 호출).
- `POST /v1/brand/domains/purchase` `{host, expectedAmountKrw, agreedNonRefundable}` · `@Throttle 3/분`
- `GET /v1/brand/domains/registration` — 진행 상태(화면 3초 폴링)

**신규(어드민)** — `admin-brand-domains.controller.ts` (`admin/brands/:id/domains`, `AdminGuard`)

- `GET /` · `POST /` **수동 연결**(→ `createForBrand` 그대로) · `DELETE /:domainId`
- `PATCH /registrations/:id/auto-renew` · `POST /registrations/:id/retry`(없으면 운영이 DB 를
  손으로 만진다) · `PATCH /charges/:id/refund`(구독 `refundInvoice` 미러)

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
DOMAIN_PURCHASE_ENABLED=           # ⚠️⚠️ === 'true' 일 때만 구매 허용 (opt-in)
DOMAIN_MARGIN_RATE=1.3             # 선택 (미설정 시 상수)
BRAND_DOMAIN_REGISTRATION_CRON_ENABLED=    # === 'false' 일 때만 off
BRAND_DOMAIN_RENEWAL_CRON_ENABLED=         # ⚠️ !== 'true' 면 off (반대 방향, 의도)
```

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

> **부수 이득**: 지금 링크바가 `storefrontLabel(previewBrand?.slug)` 로 `customDomain` 을 **안 넘겨**
> 도메인이 붙어도 `klow.kr/{slug}` 를 보여주는 **기존 버그가 함께 고쳐진다**.

## 13. klow_brand — 스튜디오 말풍선

**위치**: `studio/page.tsx` 354~381행 링크바의 **바로 아래 형제** — 드리프트 경고 배너(382행~)와
같은 자리.

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
| `PurchaseProgressPanel` | `charging\|paid\|registering` → 3초 폴링. `action_required` → 운영팀 연락 안내 |
| `WishListPanel` | `domainWishes.list()` + `POST quotes` 병합. 팔린 도메인은 회색 + "이미 판매됨" + 찜 해제 |
| `DomainSearchPanel` | 찜이 없거나 다 팔렸을 때 직접 검색 |
| `PurchaseDialog` | 공급가/VAT/합계 + `****1234` + **환불 불가 고지 체크박스** |
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

⚠️ `src/lib/domain.ts` 의 `checkDomainInput`·`BLOCKED_*` 는 **삭제하지 않는다** — 소비자가
klow_admin 수동 연결 폼으로 옮겨간다. 파일 상단의 *"서버 `domain-host.ts` 의 의도된 크로스레포
미러"* 주석에 **새 소비자가 어디인지** 갱신할 것.

## 16. klow_admin — `/brands/[id]` 도메인 탭

1. `brands/_components/brand-detail-tab.ts` 의 `BRAND_DETAIL_TABS` 에 `'domain'` **한 줄**
   (딥링크 화이트리스트가 여기서 파생되므로 다른 곳은 안 고쳐도 된다)
2. `BrandDetailTabs.tsx` — `domainMounted` + 탭 버튼. ⚠️ 초기값을 `initialTab === 'domain'` 에서
   파생시킬 것(`false` 고정이면 딥링크 진입에 빈 화면)
3. `components/brand-domain/BrandDomainPanel.tsx` + `ManualAttachDialog` · `AutoRenewToggle` ·
   `RefundChargeDialog` · `RetryRegistrationDialog` — `brand-subscription/` 5파일 구조를 미러
4. 표시: 호스트 · registration status · Cloudflare `cfState` 원문 · 만료일(+근사 배지) ·
   `auto_renew` · **원가(USD/KRW)/판매가/마진** · 청구 이력(attemptCount·failReason) · 연결된
   `BrandDomain` 행 상태
5. `lib/api/brand-domains.ts` + 배럴. **CLAUDE.md "Admin UI Convention — Toast Feedback (required)"** 준수

## 17. klow_web — 변경 없음

구매한 도메인도 결국 **같은 `BrandDomain` row(`status='active'`)** 를 만들고, `resolveHost` ·
`middleware.ts` · 핸드오프는 그 행만 본다. **서빙 경로가 통째로 무변경**이다.

> ℹ️ 새 POST 지만 `common/origin-policy.ts` 의 `BRAND_STATE_CHANGE_PATHS` 와는 **무관**하다 — 그
> 목록은 *커스텀 도메인 오리진*(손님 브라우저)에서 오는 상태변경을 좁히는 것이고, 구매는 브랜드
> 콘솔(`brand.klow.kr`, `klow` 클래스)에서 부른다. `origin-policy.spec.ts` 는 **무변경 통과**해야 한다.

---

## 18. 종료 경로 3가지

셋 다 **환불이 없다**(원가가 이미 나갔다). 화면 문구가 이걸 미리 말해야 CS 가 생기지 않는다.

| 계기 | 도메인 | 브랜드관 |
|---|---|---|
| **연결 해제**(어드민 경유) | KLOW 보유 유지, 다음 갱신 청구 안 함 → 만료 | 즉시 `klow.kr/{slug}` 폴백 |
| **구독 해지·past_due** | 그대로 보유, 갱신 청구는 계속(별도 상품이다) | `cleanupOrphans` 60일 유예 후 Vercel 제거. 서빙은 `resolveHost` 가 즉시 차단 |
| **갱신 미납 확정** | `auto_renew=false` → 만료일에 소멸 | 만료일까지 정상, 이후 `BrandDomain` 삭제 |

⚠️ `cleanupOrphans` 가 `BrandDomain` 행을 지울 때 **`BrandDomainRegistration` 은 지우지 않는다** —
회계·자산 기록이고 재구독 시 재연결의 근거다. FK 를 `SetNull` 로 둔 이유가 이것이다.

---

## 19. 구현 순서 (PR 분할) · 배포

| PR | 범위 | 배포 안전성 |
|---|---|---|
| **A** | Prisma 모델 2 + enum 3 + `pricing/domain-price.ts` + 스펙 | 읽는 코드가 없다 |
| **B** | registrar 확장 + `cloudflare-dns.client.ts` + `domain-dns.ts` + 스펙 | 호출부가 없다 |
| **C** | `SubscriptionModule.exports` + `dunning.ts`/`billing-key-select.ts` 추출 + 구매 서비스·라우트 + 등록 cron + e2e cron 목록 | `DOMAIN_PURCHASE_ENABLED` opt-in |
| **D** | 어드민 라우트 + klow_admin 도메인 탭(수동 연결 포함) | 운영이 먼저 눈을 갖는다 |
| **E** | 갱신 cron + dunning + auto_renew off | opt-in cron |
| **F** | klow_brand: `/settings/domain` + 말풍선 + `DomainSection` 제거 | **마지막** |

**배포 순서**

| # | 대상 | 확인 |
|---|---|---|
| 1 | `prisma migrate deploy` | expand only. 구버전 인스턴스가 새 테이블을 읽지 않는다 |
| 2 | **klow_server** | `DOMAIN_PURCHASE_ENABLED` 미설정 → 구매 503, 갱신 cron off. **아무 일도 안 일어난다** |
| 3 | **klow_admin** | 운영이 먼저 상태를 볼 수 있게. 수동 연결 경로가 여기서 열린다 |
| 4 | env 주입 + **스테이징 실전 리허설 1건** | 환불 불가라 **이것이 유일한 실전 검증**이다(§0) |
| 5 | **klow_brand** (마지막) | ⚠️ 2보다 먼저 나가면 `/settings/domain` 이 없는 라우트를 친다 |
| 6 | `BRAND_DOMAIN_RENEWAL_CRON_ENABLED=true` | 첫 구매 + 11개월 뒤에나 필요. **잊지 않도록 운영 캘린더에 등록** |

⚠️ 서버가 브랜드 라우트를 지운 창 동안 구 `DomainSection` 의 연결이 404 다(운영 미배포 기능이라
실사용자 0이지만, 스테이징에 수작업으로 붙여 둔 도메인이 있으면 4단계에서 어드민 탭으로 관리
가능함을 먼저 확인할 것).

⚠️ **롤백**: 4 이후에 롤백하면 이미 구매된 registration 행을 구버전 서버가 읽지 않아 **cron 이
멈춘 채 등록만 진행된다.** 롤백 시엔 반드시 어드민에서 `action_required` 목록을 눈으로 확인.

---

## 20. 검증

### 신규 스펙

| 파일 | 잠그는 것 |
|---|---|
| `src/pricing/__tests__/domain-price.spec.ts` | 마진 1.3 · VAT 1.1 · **1,000원 올림 경계**(…999→1000, 1000→1000, 1001→2000) · `DOMAIN_FX_MIN/MAX` 밖이면 throw · `parseRegistrarCostUsdCents` 실패 시 throw(**0원 청구 금지**) |
| `brand-domains/__tests__/domain-purchase.spec.ts` | ⭐ 결제 실패 → **Cloudflare 호출 0회** · ⭐⭐ 4xx → `cancelPayment` **1회** + charge=refunded · ⭐⭐ **타임아웃 → `cancelPayment` 0회** + reg=paid 유지 · 진행중 1건 → 409 · `expectedAmountKrw` 불일치 → 409 |
| `.../domain-registration-poll.spec.ts` | `paid`+404 → 3회 재시도 후 환불 · `in_progress→succeeded→registered` · `failed→환불` · **`action_required` 자동 환불 안 함** |
| `.../domain-dns.spec.ts` | **`proxied:false` 고정** · apex=A / www=CNAME · rank1 값 사용(하드코딩 아님) · **빈 recordValue 면 주입 스킵** · **멱등**(같은 값 → create 0회 / 다른 값 → update) |
| `.../domain-renewal.spec.ts` | 리드타임 30일 · dunning 0/1/3/7 · 4회 소진 → `setAutoRenew(false)` · 갱신가 2배 초과 → 청구 안 함 · `expiresAtIsEstimated` → 청구 안 함 · **만료 전까지 Vercel 연결 유지** |
| `__tests__/harness.ts` **확장** | `brandDomainRegistration`·`brandDomainCharge`·`billingKey` 인메모리 + Nicepay/Cloudflare 스텁. ⚠️ 기존 원칙대로 **스텁이 진짜보다 관대하면 스펙이 아무것도 못 잡는다** — `pgTid @unique` 와 `host @unique` 를 반드시 던지게 할 것 |

### 무변경으로 통과해야 하는 것 (통과 안 하면 설계가 샌 것)

`domain-pairing` · `verified-origin` · `resolve-host` · `domain-status` · `domain-host` ·
`origin-policy` · `origin-exempt`.
**수정이 필요한 기존 파일은 `test/app.e2e-spec.ts`(cron 9→11) 하나뿐**이다.

### 검증 3층 (CLAUDE.md)

1. `npm run typecheck` — **`tsconfig.json` 과 `tsconfig.scripts.json` 둘 다**
   (`npx tsc --noEmit` 만 쓰면 `src/` 밖을 구조적으로 못 본다)
2. `npm run test:e2e` — cron **11개** + DI 그래프(`SubscriptionModule.exports`)
3. `npm run start` — env 가드 + 라우트 매핑(311 → 실측값으로 CLAUDE.md 갱신)
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

### 문서 갱신 (구현과 같은 PR 에서)

- `docs/server/modules/brand-domains.md` — 신규 라우트·모델·cron, 소비자 목록 갱신, 특히
  **"타임아웃에는 결제를 취소하지 않는다"는 규칙과 그 이유**
- `docs/server/modules/subscription.md` — `exports: [NicepayBillingAdapter]` 개방과 그 경계
- 이 문서 — 상태 블록을 실제 진행에 맞춰 갱신
- 워크스페이스 `CLAUDE.md` — 라우트 수 + Key Facts 항목
