# 3PL 풀필먼트(콜로세움) — 구현 계획

> 상태: [진행표](../../PROGRESS.md) 참조. 이 문서는 **스펙**만 갖는다.

브랜드가 **콜로세움 3PL 창고**에 재고를 미리 넣어두고, 그 재고로 출고하는 축을 만든다.
콜로세움은 EFS 와 달리 **API 가 없어서**, 운영자가 매일 주문서 엑셀을 콜로세움 대시보드에
**수작업으로 업로드**해야 한다(양식: 1시트 `양식`, 17열 — `쇼핑몰주문번호`·`주문서상품명`·`옵션명`·
`주문수량`·`상품금액`·`수취인명`·`수취인주소`·`수취인상세주소`·`수취인우편번호`·`수취인연락처`·
`수취인연락처2`·`배송메세지`·`주문자명`·`주문자전화번호`·`비고`·`택배사명`·`송장번호`).

## 0. v1 이 하는 일 (한 줄)

**어드민에서 브랜드별 재고를 입력 → 브랜드 재고 탭에 보임 → 브랜드가 출고신청(단건 + 엑셀 일괄)
→ 재고 자동 차감 → 어드민이 콜로세움 엑셀 다운로드.**

⚠️⚠️ **v1 에서 출고신청은 KLOW 주문에서 오지 않는다.** 브랜드가 수취인·제품을 직접 입력하는
**독립 엔티티**다. 일반주문·시딩의 자동 유입은 다음 트랙이고, 그래서 v1 은 `klow_server` 의
**EFS·`Shipment`·`ShippingCarrier`·라우팅 코드를 한 줄도 건드리지 않는다.**

이 범위 축소는 의도된 것이다 — 최종 목표("유럽 주문은 EFS 송장을 만들지 않고 콜로세움으로 라우팅")로
한 번에 가면 결제·송장·정산·청구 축이 전부 동시에 흔들린다. 뼈대를 먼저 세우고 유입을 나중에 붙인다.

## 1. 확정된 결정

| 항목 | 결정 |
|---|---|
| 배송지 | **국내·해외 둘 다**. 신청마다 국가를 고른다(기본 `KR`) |
| 신청 구성 | **수취인 1명 + 제품 N줄.** 엑셀에서는 같은 `쇼핑몰주문번호` 로 N행이 나간다 |
| 브랜드 일괄 업로드 | **KLOW 양식** — 다운로드→작성→업로드→미리보기→적용 4단계. 콜로세움 양식을 그대로 받지 않는다(제품명이 자유텍스트면 재고 차감 대상을 특정할 수 없다) |
| 재고 부족 | **신청 차단** — 400 + 남은 수량 안내 |
| 재고 차감 | **신청 시점** 자동 차감. 취소하면 반납(`exported` 전에만) |
| 중복 출고 방지 | **어드민 엑셀 내보내기 = `exported` 전이.** 다음 내보내기에서 자동 제외 |
| 어드민 재고 입력 위치 | **브랜드 상세 새 탭** (`/brands/[id]?tab=inventory`) |
| 모델 이름 | **벤더 중립**(`BrandInventoryItem` / `FulfillmentRequest`) — 3PL 이 바뀌어도 살아남고, 나중 라우팅 단계에서 벤더가 늘 수 있다 |

### 나중 단계에서 이미 정해진 것 (v1 범위 밖이지만 기록한다)

- **콜로세움 물류비는 KLOW 후청구**다 — 콜로세움이 KLOW 에 청구하고 어드민이 브랜드에 후청구.
  ⚠️ `efs-billing` 을 재사용할 수 없다: 그 모듈은 청구 후보를 `efsTrackingNumber != null` 로 거르므로
  콜로세움 건이 **구조적으로 제외**된다. **별도 축**이 필요하다.
- **송장번호·배송 추적 회신 방식은 콜로세움에 확인해야 한다.** 그때까지 v1 은 추적 없음이다.

## 2. 착수 전 콜로세움에 확인할 것 (미확정)

⚠️ **추측해서 구현하지 않는다.** 정해지기 전에는 아래 잠정 처리로 두고, 정해지면 그 단계에서 채운다.

| # | 항목 | 잠정 처리 |
|---|---|---|
| A | **해외 주소를 어느 칸에 넣나** — 양식에 **국가 열이 없다**(주소/상세주소/우편번호 3칸뿐) | 국가명을 `수취인주소` 접두로 붙인다. 국내(KR)는 종전 그대로. **해외 출고를 실제로 쓰기 전에 반드시 확인** |
| B | **상품 식별** — 콜로세움이 자체 상품코드를 쓰나, `주문서상품명` 문자열로 찾나 | KLOW 제품명을 그대로 쓴다. 코드가 필요하면 재고 모델에 **nullable `vendorSku` ADD COLUMN**(롤링 안전)으로 뒤에 붙인다 |
| C | `상품금액` 열의 용도 (통관가? 정산? 통화?) | 빈칸 |
| D | `택배사명`·`송장번호` 를 우리가 채우나 콜로세움이 회신하나 | 빈칸(회신 전제) |

## 3. 실측으로 확정된 전제

구현 중 이 전제를 그대로 쓴다. 코드 위치는 심볼명으로 재확인한 뒤 편집한다.

- ⚠️⚠️ **`Product.stockLeft` 를 재사용하지 말 것.** 이미 존재하지만 klow_web PDP 의 희소성 문구
  (`Only {n} left in stock`, 8개 로케일)를 띄우는 **어드민 수기 표시값**이고, 주문이 들어와도
  차감하는 코드가 **어디에도 없다**. 3PL 재고를 여기 넣으면 창고 수량을 고칠 때마다 고객 상품
  페이지에 "N개 남음"이 뜬다.
  (소비자: `klow_admin/src/components/forms/ProductForm.tsx` · `klow_web/src/app/product/[id]/page.tsx`)
- **KLOW 에는 옵션/변형(SKU) 개념이 없다** — `Product` 하나가 곧 SKU다. 엑셀 `옵션명` 열은 빈칸.
- **탭 복원 기준점**: 커밋 `724a5cd`(2026-09-19, "홈화면 수정(정산)")가 재고 탭을 지우고 그 자리에
  정산 탭을 넣었다. 건드린 파일은 정확히 5개 — `IdlePanel.tsx`·`StudioSkeleton.tsx`·
  `InventoryTab.tsx`(삭제, 277줄)·`SettlementTab.tsx`(추가)·`StudioPillHeader.tsx`.
  원본 복원: `git show '724a5cd^:src/app/(authed)/studio/_components/tabs/InventoryTab.tsx'`
- **헤더 필 되살리기는 주석 해제 한 블록**이다 — `klow_brand/src/components/StudioPillHeader.tsx` 의
  `settlement` 블록이 `{/* */}` 로 감싸져 있고, 머리말이 *"되살릴 때 이 블록만 주석 해제하면 된다 —
  `Wallet` import 는 손대지 않았다"* 라고 지침을 남겨 뒀다.
- **`/settlement` 독립 페이지는 자립적이다** — `StudioShell active="settlement"` + 탭과 **같은**
  `SettlementDashboard` 를 쓰므로 탭 컴포넌트만 지우면 된다. `middleware.ts` matcher 에 이미
  `'/settlement/:path*'` 가 있어 **무수정**.
- **어드민 브랜드 상세 탭 추가는 배열 한 줄**이다 —
  `klow_admin/src/app/(authed)/brands/_components/brand-detail-tab.ts` 의
  `BRAND_DETAIL_TABS = ['brand','subscription','stats','settlement']`.
  ⚠️ 그 파일에 `'use client'` 를 붙이면 서버 컴포넌트가 `isBrandDetailTab` 을 호출할 때
  `is not a function` 런타임 에러가 난다(타입체크·빌드는 통과한다 — 파일 주석이 경고하고, 실제로 한 번 났다).
  ⚠️ `BrandDetailTabs.tsx` 의 lazy-mount 초기값을 `initialTab === 'inventory'` 로 **파생**시켜야
  딥링크로 들어온 화면이 비지 않는다.
- **인라인 숫자 편집은 기존 프리미티브 재사용** — `klow_admin/src/components/NumericInputCell.tsx`
  (`{ value: number | null, onSave: (v) => void, className? }`, Enter/blur 에만 저장, 빈 값 = `null`).
- **엑셀**
  - 스타일 없는 내부 문서 → **SheetJS**. ExcelJS 는 브랜드 대면 문서(청구서·정산내역) 전용이다.
  - 서버 응답 헤더는 `common/xlsx-download.ts` 의 `sendXlsx(res, buffer, { asciiName, displayName })`.
    클라는 `klow_admin/src/lib/api/client.ts` 의 `downloadFile(url, fallbackName, init?)`.
  - ⚠️⚠️ **`common/xlsx-sheet-names.ts` 의 `EXPORT_SHEET_NAMES` 에 새 시트명을 반드시 등재한다.**
    빠뜨리면 그 파일이 배송비용·비교요율 탭 업로드에서 **첫 시트 폴백으로 조용히 먹혀 그 국가
    요율표를 덮는다**(미매칭 0건으로 미리보기가 완벽해 보이는 채로).
  - **라이터와 파서를 한 파일에 둔다** — `shipping/seeding-declared-xlsx.ts` 선례. "내보낸 포맷 ==
    파서가 읽는 포맷"이 왕복의 전부라, 헤더 문자열을 한쪽에서만 고치면 조용히 깨진다.
  - ⚠️ 날짜는 `common/kst-time.ts` 의 `kstDateStr()` — `toISOString().slice(0,10)` 은 KST 00~09시 건을
    **하루 전 날짜**로 내보낸다.
- **재고 차감 동시성 선례**: `seeding.service.ts` 의 `reserveSlot()` — `SELECT … FOR UPDATE` 행 잠금,
  락 구간 3왕복 상한, Prisma 기본 5초 대신 20초 트랜잭션 옵션.
- **정적 라우트는 `@Get(':id')` 앞에** 선언한다(`shipping-countries/export` 선례).
- **권한**: 돈·대량 PII 반출은 `SuperAdminGuard`, 일반 운영은 `AdminGuard`.
  출고신청 엑셀에는 수취인 이름·주소가 들어가므로 **`POST` + `SuperAdminGuard`** 다
  (`admin-contacts` export 선례 — GET 은 `AdminAuditInterceptor` 가 기록하지 않아 **누가 뽑았는지
  흔적이 남지 않는다**).
- 착수 시점 기준선: 라우트 **349**(부팅 로그가 정본) · cron **10** · Nest 모듈 **34**.

## 4. 단계 분할

레포 경계와 마이그레이션이 분할선이고, 배포 순서와도 일치한다. **한 단계 = 한 세션.**

| # | 단계 | 레포 |
|---|---|---|
| 1 | 스튜디오 탭 스왑 — 정산→헤더 필 / 재고 탭 복원 | klow_brand |
| 2 | 스키마 + 마이그레이션 + 모듈 스캐폴딩 | klow_server |
| 3 | 재고 API — 어드민 쓰기 · 브랜드 읽기 | klow_server |
| 4 | 출고신청 API — 생성·취소 + 재고 차감 트랜잭션 | klow_server |
| 5 | 엑셀 — 브랜드 업로드 파서 + 어드민 콜로세움 내보내기 | klow_server |
| 6 | 어드민 화면 — 브랜드 재고 탭 + 출고신청 내역 | klow_admin |
| 7 | 브랜드 화면 — 재고현황 + 출고신청(단건 + 엑셀) | klow_brand |

**1·2단계만 아래에 정밀하게 쓴다.** 3~7은 제목과 범위 한 줄만 남긴다 — 뒤 단계의 전제는 앞 단계가
끝나야 확정되므로 미리 쓰면 착수 시점엔 틀려 있다. **틀린 명세는 없는 명세보다 나쁘다.**

---

### 1. 스튜디오 탭 스왑 — 정산을 헤더로, 그 자리에 재고

- **읽을 것**: 이 문서 §3, 커밋 `724a5cd` diff
- **건드리는 레포 · 배포 순서**: klow_brand 단독. **배포 순서 제약 없음**(서버 계약 변경 0)
- **스키마·데이터 위험**: **없음**
- **할 일**
  1. `src/components/StudioPillHeader.tsx` — `settlement` 블록 주석 해제.
     파일 상단 요약 주석과 블록 주석의 *"홈 탭으로 이전했다"* 산문을 **함께 뒤집는다**
     (`Wallet` import 는 이미 남아 있어 컴파일이 통과한다)
  2. `src/app/(authed)/studio/_components/IdlePanel.tsx`
     - `StudioTab` 유니온 `'settlement'` → `'inventory'`
     - `TABS` 항목 교체: `{ key: 'inventory', label: '재고', icon: <Package className="w-4 h-4" /> }`
       (`Wallet` → `Package` import 스왑)
     - 본문 분기를 `InventoryTab` 으로
     - "구 '재고' 자리" 주석과 `showAutoSaveStatus` 주석의 `'settlement'` 문자열 수정
  3. `src/app/(authed)/studio/_components/tabs/InventoryTab.tsx` 복원 (위 `git show` 로 원문 그대로).
     ⚠️ `DEMO_STOCK` 과 `연동 준비 중 · 예시` 칩을 **둘 다 유지**한다 — 7단계에서 **함께** 지운다.
     칩만 지우면 예시 숫자가 실재고로 읽히고, 상수만 지우면 실데이터에 "예시" 딱지가 붙는다
  4. `src/app/(authed)/studio/_components/tabs/SettlementTab.tsx` **삭제**(`/settlement` 페이지는 자립)
  5. `src/app/(authed)/studio/_components/StudioSkeleton.tsx` 라벨 주석 수정 (**칸 수는 4 그대로**)
  6. `src/app/(authed)/studio/page.tsx` — `?tab=` pin 이 `'orders'` 만 받으므로 무변경 확인
- **완료 기준**
  - `npm run build` 통과
  - 헤더 필에 `정산` 이 보이고 `/settlement` 가 그대로 열린다
  - 스튜디오 홈 상위 탭이 `통계 / 디자인 / 주문 / 재고` 4칸이고, 재고 탭이 목업 + `예시` 칩을 그린다
  - `?tab=orders` 딥링크(시딩 '배송현황 보러가기')가 여전히 주문 탭을 연다
  - 모바일 375px·데스크탑 둘 다에서 4칸 스트립이 안 깨진다
- ⚠️ **`middleware.ts` 는 수정하지 않는다** — `/settlement/:path*` 가 이미 등록돼 있다
- ⚠️ 이 단계가 끝나면 **`CLAUDE.md` 의 2026-09-18 항목이 다시 참이 된다**(그 항목은 `724a5cd` 이후
  스테일이었다). 2026-09-19 스왑과 이번 되돌림을 한 줄로 반영한다

### 2. 스키마 + 마이그레이션 + 모듈 스캐폴딩

- **읽을 것**: 이 문서 §1·§2·§3, `../../server/README.md` 모듈 색인,
  `klow_server/prisma/schema.prisma` 의 `Product`·`Brand` 관계부
- **건드리는 레포 · 배포 순서**: klow_server 단독. **마이그레이션 → 코드** 순
- **스키마·데이터 위험**: 마이그레이션 `add_3pl_fulfillment` — **`CREATE TABLE` ×3 + `CREATE TYPE` ×1
  뿐이라 롤링 배포 안전 · 백필 없음**.
  ⚠️ **git 브랜치 + Neon DB 브랜치를 함께 판다.** 드리프트를 리셋으로 풀지 않는다 — 그 DB 의
  데이터가 전부 지워진다
- **할 일**
  1. `prisma/schema.prisma` — 신규 모델 3개 + enum 1개
     - **`BrandInventoryItem`** — `@@unique([brandId, productId])`, `quantity Int @default(0)`.
       ⚠️ 주석에 **"`Product.stockLeft` 와 다른 축이다 — 절대 재사용 금지"** 와 그 이유(§3)를 박는다
     - **`FulfillmentRequest`** — 수취인 1명(`countryCode` 기본 `KR` · 이름 · 주소 2칸 · 우편번호 ·
       연락처 2개 · 배송메모 · 주문자 2칸 · 비고) + `externalOrderNo String?`(브랜드가 붙이는
       자기 주문번호) + `status` + `exportedAt DateTime?`
     - **`FulfillmentRequestItem`** — `productId` + **`productName` 스냅샷** + `quantity`.
       ⚠️ 이름을 스냅샷하는 이유는 제품명을 나중에 고쳐도 **이미 내보낸 건이 안 바뀌게** 하기 위함이다
     - `enum FulfillmentRequestStatus { requested exported cancelled }`
  2. `npx prisma migrate dev --name add_3pl_fulfillment` — **interactive 라 사용자에게 실행을 요청**한다
  3. `src/modules/fulfillment/` 스캐폴딩 — `fulfillment.module.ts` 를 `app.module.ts` 에 import.
     파일은 평면 + 접미사 규칙(`.service` / `.controller`), 컨트롤러는 URL surface 접두(`admin-` / `brand-`)
  4. `src/common/validation/fulfillment.ts` 신규 + `index.ts` 배럴에 re-export
     (⚠️ `.default()` 금지 — 구 클라가 안 보낸 필드를 서버가 조용히 덮어쓰는 사고 선례가 여럿이다)
- **완료 기준**
  - `npm run typecheck` — **tsconfig 2개**를 돈다(`npx tsc --noEmit` 만 쓰면 `src/` 밖이 조용히 깨진다)
  - `npm run test:e2e` — DI 그래프 통과 + **cron 10개 불변**(새 cron 없음)
  - `npm run start` — 부팅 + **라우트 349 불변**(아직 컨트롤러 라우트가 0개다)
  - `npx prisma migrate status` clean
- ⚠️ 이 단계는 라우트를 만들지 않는다 — 배포해도 **아무 동작이 달라지지 않는다**(안전한 착지점)

### 3~7 (제목과 범위만)

3. **재고 API** — 어드민 `GET`/`PUT /admin/brands/:id/inventory`(`AdminGuard`, 브랜드 제품 목록 조인
   + 수량 upsert), 브랜드 `GET /v1/brand/inventory`(`BrandGuard`).
   ⚠️ `admin-brands.controller.ts` 에 `@Get(':id')` 가 있으므로 **별도 컨트롤러**로 뺀다.
4. **출고신청 API** — 브랜드 생성·목록·취소. **생성·취소가 재고 차감/반납과 한 트랜잭션**이고
   `SELECT … FOR UPDATE` 행 잠금을 쓴다(`reserveSlot()` 선례). 재고 부족은 400 + 남은 수량.
   취소는 `exported` 전에만.
5. **엑셀 2종** — ① 브랜드 업로드(KLOW 양식, 라이터+파서 한 파일, 다운로드→미리보기→적용)
   ② 어드민 콜로세움 내보내기(`POST` + `SuperAdminGuard`, 17열 매핑, 내보내기 = `exported` 전이).
   **`EXPORT_SHEET_NAMES` 등재 필수.** 회귀 스펙 `__tests__/fulfillment-xlsx.spec.ts`.
6. **어드민 화면** — 브랜드 상세 `재고` 탭(`NumericInputCell`) + 사이드바 `배송` 그룹에 출고신청 내역 탭.
   ⚠️ `Sidebar.tsx` 의 `NAV` **와** `components/tabs/routeLabels.ts` 의 `ROUTE_LABELS` **둘 다** 갱신한다 —
   후자를 빠뜨리면 탭 제목이 영문 슬러그로 뜬다(현재 6개 탭이 이미 그 상태다).
   선택·일괄 처리는 `shipments/_components/FailedTable.tsx` 패턴(목록 변경 시 죽은 id 정리 포함).
7. **브랜드 화면** — 재고 탭 목업을 실데이터로 교체(`DEMO_STOCK` + `예시` 칩 **함께 제거**),
   서브탭 2개 추가(`재고현황` / `출고신청`). 서브탭 UI 는 `shipping/ui.tsx` 의 `Segmented` 2칸 변형.
   ⚠️ 기간별 해외/국내 **출고량은 디자인만**이다 — 목업 상수 + `예시` 표시를 남긴다.

## 5. 다음 트랙 후보 (v1 이 일부러 하지 않는 것)

착수 결정이 나면 그때 진행표에 행이 된다. 지금은 백로그다.

- **유럽 국가 EFS→콜로세움 라우팅** — `ShippingCarrier` enum 값 추가 · `pickCarrierForWeight` 최우선
  반환 · `executeCreate` EFS 스킵 분기 · 배송비용 탭(`/seeding-cost`)의 캐리어 select.
  ⚠️ `DOMESTIC`(국내 자체배송)이 **완성된 템플릿**이다 — enum 주석이 새 캐리어가 답해야 할 질문
  5개(발급·추적·청구·정산·어드민 노출)를 그대로 열거한다. 조사도 끝나 있다:
  `payload-builder` 의 `Record<Exclude<ShippingCarrier,'DOMESTIC'>, …>` 가 컴파일로 누락을 잡고,
  정산 축은 2026-09 전환(인식 시점 = `paidAt`)으로 캐리어를 전혀 안 봐서 **무손질 통과**한다.
  ⚠️ 다만 `resolveProductShipping` 의 "국내는 일반주문 대상 아님" throw 는 **복사하면 안 된다**
  (유럽은 일반주문이 주 대상이다).
- **일반주문·시딩의 출고신청 탭 자동 유입** — 유입이 생기면 같은 주문이 주문 탭 '발송 대기'와
  출고신청에 **이중 노출**된다. 주문 탭에는 "EFS 인천 GDC 로 박스를 보내세요" 안내가 붙어 있어
  그대로 두면 브랜드가 박스를 엉뚱한 곳으로 보낸다(국내 자체배송에서 같은 이유로 이미 숨기고 있다).
  → 유럽 건은 `listPendingForBrand` 에서 뺀다.
- **콜로세움 물류비 KLOW→브랜드 후청구** — `efs-billing` 재사용 불가(§1 참고). 콜로세움이 우리에게
  청구한 실비를 받는 경로(아마 또 엑셀)가 함께 필요하다.
- **송장번호·배송 추적·고객 `/track` 연동** — 회신 방식 확인이 선행(§2 D).
  붙일 자리는 `shipments/local-tracking.ts` 의 `localTrackingLink()` 와
  `orders.service.ts` 의 `shipmentTrackingStatus()`, 그리고 **`isTerminalShipment()` 한 곳**이다.
  ⚠️ 종착 판정 분기를 호출부마다 두지 말 것 — 국내배송 때 전용 완료 훅을 따로 만들었다가
  **국내·EFS 송장이 섞인 주문이 양쪽 어디에도 안 걸려** 영영 `shipped` 에 머문 선례가 있다.
- **제품 노출 게이트 변경은 불필요** — 재고 0이 판매를 막지 않기로 했으므로
  `PURCHASABLE_PRODUCT_WHERE` 를 건드릴 이유가 없다.
