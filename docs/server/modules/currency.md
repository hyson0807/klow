# currency — 통화 환율 (표시용 현지통화 + 정산 정본 KRW)

- **모듈 경로**: `src/modules/currency/`
- **목적**: 국가별 현지통화 **표시 전용** 환율 관리. 가격 정본·청구(USD)와는 분리된 레이어다. 저장 단위는 국가가 아니라 **통화코드(ISO 4217)**이고, 국가→통화 매핑은 `ShippingCountry.currencyCode` 가 쥔다.
- **데이터 모델**: `CurrencyFxRate` (`code` PK) — 아래 표 참고
- **외부 API**: `https://open.er-api.com/v6/latest/USD` (키 불필요, 무료 공개. `{ result:'success', rates:{ USD:1, JPY:157.2, ... } }`). 타임아웃 10초(`AbortController`), 환경변수 없음.
- **관련 파일**: `currency.service.ts`, `admin-currency.controller.ts`, `public-currency.controller.ts`, `currency-refresh.cron.ts`, 검증 스키마 `common/validation/shop.ts` (`FxRatePatch`)

## CurrencyFxRate 모델

| 필드             | 타입        | 의미                                                                              |
|------------------|-------------|-----------------------------------------------------------------------------------|
| `code`           | `String @id`| ISO 4217 통화코드 (`JPY`, `EUR`, …). `USD` 자기 자신은 rate 1.0                    |
| `usdRate`        | `Float`     | **실효 환율** — 1 USD == N (해당 통화). 표시 환산·청구 환산이 읽는 값             |
| `autoRate`       | `Float?`    | cron 이 마지막으로 받은 자동값(그림자). `manualOverride` 와 무관하게 항상 기록 — 어드민이 "자동 제안값 vs 내가 덮은 값"을 비교하게. `null` = 자동 갱신된 적 없음 |
| `manualOverride` | `Boolean`   | `true` 면 cron 이 `usdRate` 를 덮지 않는다(수동 고정). `autoRate` 그림자만 갱신    |
| `source`         | `String`    | 기본 `"open.er-api.com"`, 수동 생성 시 `"manual"`                                 |
| `fetchedAt`      | `DateTime?` | 마지막 자동 갱신 성공 시각                                                        |
| `updatedAt`      | `DateTime`  | `@updatedAt`                                                                      |

> **`KRW` 행은 특별하다** — 표시용 통화가 아니라 **브랜드 정산 정본 환율(KRW per USD)** 이다. 같은 테이블에 있지만
> cron 이 절대 건드리지 않고(자동 갱신 대상에서 명시적 제외), 어드민 수동 보정 시에도 `manualOverride` 가 항상
> `true` 로 강제 핀된다(언핀 불가). 정산가 역산·주문 결제·`basePriceFxRate` 스냅샷이 이 값을 공유한다.

## admin-currency.controller.ts (`@Controller('admin/shop/fx-rates')`)

> 전체 라우트 `AdminGuard`. `@Throttle()` 없음(전역 기본 60회/분/IP). `/admin/*` 이라 non-GET 은 `AdminAuditInterceptor` 가 자동 기록.

| Method | Path                              | 기능                                                                          |
|--------|-----------------------------------|-------------------------------------------------------------------------------|
| GET    | `/admin/shop/fx-rates`            | 전체 통화 목록 (`code asc`). 실효 rate / 자동값 그림자 / 오버라이드 / 갱신시각 |
| POST   | `/admin/shop/fx-rates/refresh`    | 외부 API 즉시 갱신 트리거(cron 과 동일 경로). 어드민 "지금 갱신" 버튼. `{ updated, skipped }` 반환 |
| PATCH  | `/admin/shop/fx-rates/:code`      | 수동 보정 — `usdRate` / `manualOverride` 설정 (upsert)                        |

**PATCH body** — `FxRatePatch`: `{ usdRate?: number(>0, ≤100,000,000), manualOverride?: boolean }`. 둘 다 optional 이지만
`.refine` 으로 **최소 한 필드는 필수** (`at least one field is required`).

- `:code` 는 서버가 `toUpperCase()` 한다.
- `USD` → 400 `USD 는 정본 통화라 환율을 편집할 수 없습니다.`
- 기존 행이 없는데 `usdRate` 도 안 주면 → 400 `신규 통화는 usdRate 를 함께 지정해야 합니다.`
- `KRW` 는 편집은 되지만 `manualOverride` 가 요청값과 무관하게 **항상 `true`** 로 고정된다.
- 신규 생성 시 기본값: `usdRate = patch.usdRate ?? 1`, `manualOverride = patch.manualOverride ?? true`(KRW 는 무조건 true), `source = 'manual'`.

## public-currency.controller.ts (`@Controller('v1/shop')`)

| Method | Path                  | Guard  | 기능                                                        |
|--------|-----------------------|--------|-------------------------------------------------------------|
| GET    | `/v1/shop/currency`   | public | 국가→통화 맵 + 통화→환율 맵을 1콜로 반환                    |

응답: `{ countryCurrency: { [iso2]: currencyCode }, rates: [{ code, usdRate, updatedAt }] }`

- `countryCurrency` 는 **`ShippingCountry.enabled = true` 이고 `currencyCode` 가 있는 국가만** (공개 노출 대상).
- `rates` 는 **전체 통화 행** — 필터 없이 다 내려간다(KRW 정산 환율도 포함).
- web/brand 가 부팅 시 1콜로 받아 현지통화 표시/입력에 쓴다.

> `GET /v1/shop/fx-rate`(KRW per USD 단일값)는 이 모듈이 아니라 **shop 모듈** 소유다 — 같은 `CurrencyFxRate['KRW']`
> 행을 읽는 다른 라우트. [`shop.md`](./shop.md) 참고.

## currency-refresh.cron.ts

- `@Cron('0 4 * * *', { timeZone: 'Asia/Seoul', name: 'currency-rate-refresh' })` — **매일 KST 04:00**.
- `refreshFromApi()` 를 호출하고, 던져진 예외는 `catch` 해서 `currency fx refresh failed` 로 로깅만 한다(프로세스 영향 없음).

## `refreshFromApi()` 동작

1. `open.er-api.com` 에서 USD 기준 전통화 rate 를 1콜로 받는다. HTTP 실패나 `result !== 'success'` 면 **throw → 기존 값을 그대로 두고 에러만 로깅**(테이블 wipe 금지).
2. 갱신 대상 통화 = `ShippingCountry.currencyCode` 에 실제 매핑된 통화들(`distinct`) **+ `USD`(정본, 항상 rate 1) − `KRW`**. KRW 제외는 "미래에 KR 이 배송국이 돼도 정산 환율이 안 흔들리게" 하는 명시적 방어다.
3. 기존 행의 `manualOverride` 를 **한 번에 조회**해 루프 내 N+1 을 피한다.
4. 통화별 upsert:
   - `manualOverride = false` → `usdRate` + `autoRate` + `fetchedAt` 모두 갱신
   - `manualOverride = true` → `autoRate` + `fetchedAt` 만 갱신 (수동값 유지)
   - 신규 생성은 `manualOverride: false`
   - rate 가 없거나 유한하지 않거나 `<= 0` 이면 `skipped++` 하고 건너뜀
5. 모든 write 를 `prisma.$transaction(writes)` 로 **한 번의 배치 round-trip** 커밋 후 `{ updated, skipped }` 반환 (`updated` = 실제 write 개수).

## 사용처 (환율을 읽는 쪽)

`CurrencyModule` 이 `CurrencyService` 를 `exports` 하지만, **다른 모듈은 `CurrencyService` 를 주입하지 않고
`prisma.currencyFxRate` 를 직접 읽는다.** 실질 소비 지점은 세 곳이다.

| 읽는 곳                                                   | 무엇을                                                                                   |
|-----------------------------------------------------------|------------------------------------------------------------------------------------------|
| `pricing/fx.ts` `resolveFxRate(prisma)`                    | `KRW` 행의 `usdRate` = **정산 정본 환율**. 행이 없으면 `FX_RATE_FALLBACK`. 정산가 역산·주문 결제·`basePriceFxRate` 스냅샷이 공유 |
| `pricing/fx.ts` `resolveCurrencyUsdRate` / `…Strict` | 목적국 현지통화 환율(핀 현지가 `priceLocal` → USD 환산). 관대 버전은 미매핑/무효 시 `1`(USD) 폴백 + 경고 로깅, **strict 버전은 `null` 반환** → `orders.service` 가 그 핀 상품 라인을 차단한다(¥1500 → $1500 과청구 방지) |
| `shop/shop.service.ts` `getFxRate()`                      | `GET /v1/shop/fx-rate` 응답 — `{ usdKrwRate, updatedAt }`                                |
