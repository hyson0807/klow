# seeding-bulk-invoice — 구현 계획 (빌드 스펙 정본)

결정 요약은 [`README.md`](./README.md). 상태는 `docs/PROGRESS.md` `§7` 7·8행만 갖는다.

## 착수 게이트 (불변식)

1. **송장 캐리어는 국가 고정 캐리어 하나다.** 무게를 캐리어 판정에 쓰는 코드를 남기지 않는다 — 분기 값은 견적·비교 화면만 읽는다.
2. **엑셀 발급은 행 단위로 실패를 격리한다.** 한 행의 400 이 배치를 멈추지 않고, 이미 주문이 만들어진 행은 클라가 다시 보내지 않는다(송장 두 장).
3. **국가별 필수 필드의 정본은 서버 `assertEfsCountryFields`** 다. klow_brand 의 규칙은 화면용 1차 검사이고 서버에 없는 규칙은 `warn` 이다.
4. **reissue 와 bulk 는 발급 코어를 공유한다** — 링크+claim+주문+송장 생성 사본을 만들지 않는다.

### A행 — klow_server: 캐리어 고정화 + `POST /v1/brand/seeding/bulk-issue`

**A-1. 캐리어 = `productCarrier` 고정** (`src/modules/shipping/shipping.service.ts`)
- `pickCarrierForWeight`(:572) 를 무게 무관하게 `productCarrier` 만 반환하도록 바꾸거나(이름도 `pickCountryCarrier`) 제거 —
  호출부 `resolveCarrier`(:409, 시딩 claim·checkout·reissue·엑셀) 와 `resolveProductShipping`(:335, 일반 주문 견적·생성) 둘 다.
  `resolveCarrier` 의 `weightG` 파라미터 제거 → 시딩 호출 3곳(`seeding.service.ts:366·780·911`) 정리, reissue 의 "무게 승계 = 캐리어 때문" 주석 정정(규격 표시용 승계만 남음).
  일반 주문의 `carrierByBrand` 는 모양(JSON 스냅샷 `Order.shippingCarrierByBrand`) 유지, 값만 전 브랜드 동일. `brandChargeableWeights` 가 캐리어 외에 쓰이는지 확인 후 불필요하면 호출만 걷어낸다.
- **발급 가능국 정의** — 지금 `supportedCountries`(logistics-rate.service.ts:239) 와 어드민 목록(`seeding-cost/page.tsx:54`)은 "분기만 있어도(productCarrier null) 발급 가능"이다. 이제 **`productCarrier` 필수**로 바꾼다(운영 분기국 10개는 전부 설정돼 있어 무영향 — 실측). `isDirect`(:257) 도 `productCarrier === 'EFS'` 기준으로.
- EFS 제외구역 검사는 고정 캐리어 기준으로 그대로 동작.
- 분기 값을 읽는 곳은 **견적·비교 화면만** 남는다(`quoteByWeight`/비교표 등) — 표시 문구에 "예상" 명시.
- 기존 스펙 중 분기→캐리어를 기대하는 테스트 갱신.

**A-2. 엑셀 일괄 발급 엔드포인트**

1. **zod** `common/validation/seeding.ts` 에 `SeedingBulkIssueInput`:
   `{ campaignName?: max40, rows: SeedingBulkRow[] (1..20) }`,
   `SeedingBulkRow = { clientRowId, countryCode(ISO2), ...recipientAddressFields, email?: efsMaxBytes(email) 또는 빈값, instagram?, quantity, itemNames: SeedingItemNames }`
   + `itemNames.length === quantity` superRefine(reissue 와 같은 `ITEM_NAMES_QTY_MSG`). `.default([])` 금지 규칙 유지.
2. **공통 코어 추출** — `reissue` 의 "링크 생성(brand·brand·single·maxClaims 1·feeKrw 0) + `createFreeSeedingOrder` + `await shipments.createForOrderSystem`" 을
   private `issueDirect(brandUser, recipient, {iso2, quantity, itemNames, campaignName, box})` 로 뽑아 **reissue 와 bulk 가 공유**한다
   (사본 금지 — 2026-09-02 에 신고단가 사본 3벌을 합친 선례). reissue 는 box=소스 링크 승계, bulk 는 box=전부 null.
3. **`bulkIssue(brandUser, dto)`** — 행 단위로 실패를 격리하고 **throw 하지 않는다**:
   - 국가: `supportedCountries()` 에 있어야 함, `DOMESTIC`(KR) 행은 거절(국내는 링크 흐름 — IssuePanel 도 KR 을 뺀다)
   - `assertEfsCountryFields(iso2, row)` → `BadRequestException` 메시지를 그 행 `error` 로
   - `resolveCarrier(iso2, {city, postalCode})` (A-1 이후 고정 캐리어 — 제외구역·미설정 캐리어 400 도 행 에러)
   - 통과 행은 `issueDirect` 를 **순차** 실행(EFS 레이트 가드가 없어 병렬 금지, 청크 20행이면 최악 ~5분 → 클라가 10행씩 보냄)
   - 반환 `{ results: [{ clientRowId, ok, error?, linkId?, orderId?, shipmentStatus?: 'submitted'|'failed'|... }] }`
   - `reserveSlot()`/중복 422 는 타지 않는다(reissue 와 같음 — 발송대기 중복 **경고**는 뜬다)
4. **이메일 빈값 안전화** — `email=''` 로 저장되는 첫 경로다. 확인할 곳:
   `sendSeedingConfirmationSafe`(빈값이면 skip), `orders/recipient-match.ts` `recipientDedupeKeys`(**빈 이메일끼리 매칭되면 안 됨**),
   payload 33번(빈값 OK), 어드민/브랜드 목록 표시.
5. **알림** — 수령인 메일은 이메일 있을 때만. 브랜드 알림톡은 **보내지 않는다**(방금 본인이 N건을 누른 액션이라 N통 스팸 — reissue 의 opt-in 과 다르게 끈다. 결정 기록에 남김).
6. **컨트롤러** `brand-seeding.controller.ts` 에 `@Post('bulk-issue')` + 전용 스로틀 `THROTTLE_BULK_ISSUE`(예: 30회/분 — 100명 = 10요청).
7. **테스트** `seeding/__tests__/seeding-bulk-issue.spec.ts`: 국가별 필수(CN/MX 형식·US state·JP 영문) 행 에러 격리, KR 거절,
   itemNames/quantity 불일치 400, 이메일 빈값 저장 + 메일 skip, 빈 이메일 dedupe 비매칭, reissue 무회귀.
8. **문서** `docs/server/modules/seeding.md`·`shipping.md`(엔드포인트 + 캐리어 고정화) · `decisions/shipping-seeding.md` 새 항목 2건
   (캐리어 고정화 / 엑셀 일괄 발급) + `decisions/README.md` · `CLAUDE.md` 색인 + **CLAUDE.md Key Facts 의 "캐리어 무게 분기 … 시딩·일반주문 공용" 서술 정정**,
   `docs/reference/pricing-model.md` 의 같은 서술도.
9. 검증 3층 → klow_server `staging` 에 커밋(push 안 함). 

### B행 — klow_admin 문구 + klow_brand 목업 연결

**B-1. klow_admin** (`seeding-cost/[iso2]/page.tsx:30·63-67`, `seeding-cost/page.tsx:54·278`): 분기 표시를 "예상 배송비 비교용"으로 문구 변경,
무게별 캐리어 열은 "예상" 표기, 발급 가능 판정을 `productCarrier != null` 로. 분기국인데 고정 캐리어 미설정이면 경고 배지.
klow_brand 의 비교/견적 화면에 분기 캐리어를 "실제 캐리어"처럼 표시하는 곳이 있으면 같은 문구 정리.

**B-2. klow_brand**
1. `staging` 에서 `git cherry-pick ceba630`(taeyoung30 은 staging 기준 5커밋 뒤, 4파일 — 충돌 예상 없음).
2. **`bulk-invoice.ts` 규칙을 서버에 맞춘다**
   - `BULK_COLUMNS` 에 `nameEn`(영문 이름)·`address1En`(영문 주소) 추가 — need `'country'`, 별칭(영문이름·romaji·english name 등)
   - `COUNTRY_RULES` → 서버 4종만 `error`: CN taxId 18자리 · MX RFC(`/^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/`, 대문자 정규화) · US state · JP nameEn+address1En(영문·5자↑)
   - BR/TW/CA/AU state·우편번호 정규식 → **`warn`** 으로 강등(발급은 되고 확인만 권유). HK/MO 우편번호 빈칸 허용 삭제(서버 `min(2)`)
   - 비영문 이름/주소 전면 차단 **제거**(서버·EFS 가 현지어 허용, JP 는 영문 칸이 따로). 품명만 ASCII 유지(`brandItemsIssue` 재사용)
   - 전화번호: 공백·점 제거해 `^[+\-()0-9]+$` 로 정규화, 남는 문자 있으면 error. 이메일은 형식 틀리면 error(서버 zod 400 방지), 비면 OK
   - 가이드 시트·`COUNTRY_RULE_GUIDE` 문구를 위 4종으로 갱신
3. **`api.ts`** `seeding.bulkIssue({campaignName, rows})` + `api-types.ts` 결과 타입.
4. **`BulkInvoiceModal.tsx`**
   - `onMockUpload` 제거(버튼이 실제 파일 선택)
   - `issue()` → 통과 행을 **10행 청크로 순차 호출**, 진행바는 실제 완료 수. 행 매핑: `rowItems` → `quantity`=합, `itemNames`=`brandItemNames` 평탄화(`seeding-link.utils.ts:236`), 공통 제품(`settleRows`) 반영
   - 서버 `ok:false` 행 → 서버 메시지를 이슈로 달아 **수정 대기**로(기존 `saveBulkPending` 경로). `ok:true` 는 송장 상태가 failed 여도 대기로 되돌리지 **않는다**(주문이 이미 있어 재발송하면 두 장 — 어드민 재시도 경로에 맡기고 완료 화면에 "발급 실패 N건 · 자동 재시도 중" 표시)
   - 완료 시 `qk.seedingLinks`·`qk.shipments('pending')` invalidate
   - 청크 도중 네트워크 오류 → 남은 행은 명단에 그대로, 이미 된 행만 제거(중복 발급 방지)
5. **이용계약서 게이트** — 링크 발급과 같은 `useSeedingAgreement` 서명 확인을 모달 진입 전에 태운다(서버는 강제 안 함).
6. `npm run build` + `npx eslint <바꾼 파일>`.
7. 레포별 `staging` 커밋(push 안 함) · `§7`/`§9`/`§0` 갱신 · 사용자에게 **push 순서 klow_server → klow_admin → klow_brand** 안내
   (brand 가 먼저면 새 버튼이 404). 

## 재사용할 기존 코드

- `seeding.service.ts` `reissue`(:306) · `createFreeSeedingOrder`(:1336) · `SEEDING_TX_OPTS` · `randomDeclaredCents`/`seedingDeclaredTotalCents`
- `common/efs-recipient.ts` `assertEfsCountryFields` · `validation/shared.ts` `recipientAddressFields`/`TAX_ID_RULES`/`efsMaxBytes`
- `validation/seeding.ts` `SeedingItemNames`/`ITEM_NAMES_QTY_MSG`/`SeedingReissueInput`(형태 참고)
- `shipping.service.ts` `resolveCarrier` · `shipments.service.ts` `createForOrderSystem`(throw 안 함)
- klow_brand `seeding-link.utils.ts` `brandItemNames`/`brandItemsIssue` · `useFileDrop` · `xlsx-js-style`(이미 의존성)

## 검증

- **A행 캐리어**: 분기국(예: 운영 분기국 중 하나를 staging 에서 확인)에 무거운 무게로 `POST /v1/orders/quote`·시딩 claim → 캐리어가 `productCarrier` 그대로인지. 브랜드 발급 화면 견적은 여전히 무게별 예상 요금이 뜨는지.
- **A행**: `npm run typecheck`(두 tsconfig) · 새 spec + 기존 jest · `npm run test:e2e`(DI) · `npm run start` 라우트 수 +1.
  로컬 서버 + staging DB 로 `curl` 3행(US 정상 / CN 신분증 누락 / JP 영문 누락) → 결과 배열 확인.
  ⚠️ **실 EFS 발급이 일어나므로** 실행 전 `.env` 의 EFS 가 테스트 계정인지 확인하고, 아니면 정상 행 1건만 보내고 어드민에서 송장 취소.
- **B행**: klow_admin·klow_brand `npm run build` · 로컬 klow_brand(:3002) → 양식 다운로드 → JP/CN/MX/US 섞은 엑셀 업로드 → 규칙 오류 표시 → 수정 → 발급 →
  발송대기 탭에 행 등장·바코드 인쇄 가능 · 서버 거절 행이 수정 대기로 이동 · 모달 닫았다 열어도 대기 명단 유지.
