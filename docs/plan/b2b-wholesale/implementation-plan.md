# b2b-wholesale — 구현 계획 (빌드 스펙 정본)

결정 요약은 [`README.md`](./README.md), 설계 논거는 [`flow.md`](./flow.md).
상태는 [`../../PROGRESS.md`](../../PROGRESS.md).

⚠️⚠️ **선행 게이트: 트랙 [`brand-menu-schema`](../brand-menu-schema/implementation-plan.md) 완료.**

---

## §1 착수 게이트 — 불변식

- **B1. `PUT /v1/brand/applications` 에 얹지 않는다.** 전용 컨트롤러로 간다(`brand-notices` 선례).
- **B2. 금액은 `Decimal(14,2)`. `Float` 금지.**
- **B3. 주문은 금액 스냅샷을 자기 안에 든다.** `B2bOrderLine.productId` 는 **nullable +
  `onDelete: SetNull`** — 제품을 지워도 주문 이력이 남아야 한다.
- **B4. `published` 는 서버가 검증하는 게이트다.** 목업에서는 클라이언트 boolean 이었다.
  끄면 "준비 중"만 보이고 **링크는 살아 있다**(404 아님).
- **B5. 태그는 파싱해서 내려보낸다.** `tagline` 원문을 실으면 바이어 화면에
  `__klow_brand_tags_v1__:` 내부 키가 찍힌다.
- **B6. 메뉴를 두 벌 들지 않는다.** B2B 가 저장하는 것은 "안 보일 줄의 id 목록" 하나다.
- **B7. 없는 기능에 서버를 만들지 않는다.** `wholesaleUsd`·`wholesaleDiscountPct`·`lowestTierPrice`·
  `tierSavingPct` 는 호출처 0건이고 환율 훅도 B2B 에서 안 쓴다(README 참고).
- **B8. 목업 고지를 저장 경로와 함께 지운다.** "이 브라우저에만 저장돼요" 문구만 지우고 localStorage
  경로를 남기면 로컬분이 서버값을 덮는다(재고 탭 `DEMO_STOCK` 선례: 칩만 지우면 예시가 실데이터로
  읽힌다).

---

## §2 스키마 (1단계)

`CREATE TABLE` 6개 + enum 3개. **DROP 0건 · 백필 없음 → 롤링 안전.**

| 모델 | 키 | 비고 |
|---|---|---|
| `B2bSetting` | `brandId @unique` | `published` · `orderEmail` |
| `B2bProductTerm` | `productId @unique` | `visible` · `price Decimal(14,2)` · `currency` · `moq`. 기본 도매가가 **곧 첫 구간**이라 여기 있다 |
| `B2bPriceBreak` | `@@unique([termId, minQty])` | `minQty` · `price Decimal(14,2)`. **통화는 두지 않는다** — 제품 통화를 따른다(칸마다 갈리면 "많이 살수록 싸진다"를 비교할 수 없다). 상한 5는 zod 가 막는다 |
| `B2bDocument` | `brandId` (N) | `url` · `filename` · `lang` · `inMenu` · `menuLabel` · `uploadedAt` |
| `B2bOrder` | `brandId` (N) | `status` · 바이어 5필드(`company`·`contact`·`email`·`countryCode`·`note`) · `currency` · `total Decimal` · `notifyEmail` · `notifiedAt` |
| `B2bOrderLine` | `orderId` (N) | `productId String?` + `onDelete: SetNull` · `name` · `image` · `qty` · `unitPrice` · `lineTotal` |

enum: `B2bCurrency`(USD KRW EUR JPY CNY) · `B2bDocLang`(en zh ja es etc) ·
`B2bOrderStatus`(received confirmed done).

⚠️ `B2bProductTerm` 의 기본값은 **`visible: true` · `price: 0`** 이다(목업 `defaultTerms()`). 노출이
기본이고 가격이 0이면 바이어 화면에 안 걸린다 — `isSellable = visible && price > 0`.

---

## §3 단계

⚠️⚠️ **이 트랙 전체가 대화 세션 하나다**(`PROGRESS.md` `§7` 6행) — **셋 중 가장 크다**
(테이블 6벌 + 컨트롤러 2벌 + 3레포 화면). 아래 1~6은 세션 안의 순서이자 정지점이다.
⚠️ 마이그레이션(1번)이 첫 순서다. 넘치면 `3번까지`(서버) / `4번부터`(화면) 경계에서 끊는다 —
그 선이 배포 경계와도 같다.


### 1. 스키마 + 마이그레이션

- **읽을 것**: 이 문서 `§1`·`§2`, `klow_brand/src/lib/b2b.ts` 의 타입 정의 전문
- **건드리는 레포 · 배포 순서**: klow_server 단독
- **스키마·데이터 위험**: `CREATE TABLE` 6 + enum 3 → **DROP 0건 · 백필 없음 · 롤링 안전.**
  `npx prisma migrate dev --name add_b2b_wholesale`. DB 브랜치 `ep-solitary-morning-a1rygrkh`.
  ⚠️ **마이그레이션 단독 세션**(PROGRESS `§4`)
- **완료 기준**: 검증 3층 · `prisma studio` 로 6테이블 확인 · ⚠️ cron 기대 목록 불변

### 2. 서버 — 브랜드측 API + PDF 업로드 확장

- **읽을 것**: 이 문서 `§1`, `klow_server/src/modules/brand-notices/`(전용 컨트롤러 선례),
  `klow_server/src/common/validation/upload.ts`, `klow_server/src/modules/upload/r2.service.ts`
- **건드리는 레포 · 배포 순서**: klow_server 단독
- **스키마·데이터 위험**: 없음
- **할 일**
  - `src/modules/b2b/` 신규 — `b2b.module.ts` · `b2b.service.ts` ·
    `brand-b2b.controller.ts`(`@Controller('v1/brand/b2b')` · BrandGuard)
    - `GET /me` — 설정 + 제품조건(구간 포함) + 자료를 한 번에
    - `PUT /settings` · `PUT /products/:productId/terms`(구간까지 일괄 교체) ·
      `POST /documents` · `PATCH /documents/:id` · `DELETE /documents/:id`
    - ⚠️ 목업 `saveB2b` 는 **전체 통째 덮어쓰기**였다. 정규화하면서 **필드별로 가른다** —
      제품 하나 저장이 다른 제품을 건드리지 않게
  - `src/common/validation/b2b.ts` — 구간 ≤5 · `moq` ≥0 · 금액 양수 · `orderEmail` 형식
  - **PDF 업로드**: `validation/upload.ts` 의 `kind` 에 `'doc'` 추가 + `application/pdf` 허용 +
    `r2.service.ts` `buildKey()` 에 `docs` 폴더. ⚠️ **SVG 는 계속 막는다**(XSS)
    - ⚠️ 호출부도 고친다 — `B2bDocsCard` 가 `uploadFile(file)` 을 `kind` 기본값 `'image'` 로 부르면서
      `contentType: application/pdf` 를 넣어 **현재 조합은 400 이다**(README 참고)
  - ⚠️ 새 모듈이라 `test/app.e2e-spec.ts` 의 **모듈 수 기대치가 35 → 36**
  - `docs/server/modules/b2b.md` 신규 + `docs/server/README.md` 색인(**필수**)
- **완료 기준**: curl 로 설정·도매가·자료 왕복 · PDF presign 200 · 검증 3층 · 라우트 수 증가 확인

### 3. 서버 — 공개 API + 주문 접수 + 알림메일

*(착수 세션에서 정밀화. 아래는 골격.)*

- **할 일 (골격)**
  - `public-b2b.controller.ts` — `GET /v1/b2b/:slug` · `POST /v1/b2b/:slug/orders`
  - 공개 투영: 브랜드 표시값 + **파싱된 태그**(B5) + 메뉴 + 도매 조건 + 자료.
    ⚠️ **제품 상세 필드를 목록에 다 싣지 않는다** — 목록은 카드용, 상세는 단건으로
    ([`flow.md`](./flow.md) §2)
  - 주문 접수 → Resend 로 `orderEmail` 발송 → `notifiedAt` 기록
  - ⚠️ 주문 POST 는 메일 발송을 동반하므로 `THROTTLE_TIGHT` 급. **조회는 과하게 조이지 않는다**
    (부스·NAT 선례 — [`flow.md`](./flow.md) §5)
  - ⚠️ dev 에서 `RESEND_API_KEY` 가 켜져 있어 **실제로 메일이 나간다** —
    테스트는 `RESEND_API_KEY= npm run start`
- **완료 기준**: `published:false` 면 "준비 중" 응답(404 아님) · 주문 1건 → 메일 수신 → `notifiedAt` 기록

### 4. klow_brand `/b2b` 대시보드 실연결

*(착수 세션에서 정밀화.)*

- **할 일 (골격)**
  - `src/lib/b2b-store.ts` 를 서버 호출로 갈아끼운다 — 그 파일 주석이 이미 교체 계약을 명시한다
    (`loadB2b → api.b2b.me()` · `saveB2b → api.b2b.save()` · `submitB2bOrder → POST`)
  - `src/lib/api.ts` 에 `api.b2b.*` 신설(현재 b2b 관련 함수가 **0개**다)
  - ⚠️ **동기 전제를 비동기로 바꾼다** — `BuyerStorefront` 의 `loadPublicB2b` 와 `B2bBoard` 의
    `useState(() => loadB2bOrders(slug))` 가 동기 함수 전제라 로딩·에러 상태가 없다
  - ⚠️ `notifyB2bOrder(order)` 는 지금 인자를 `_order` 로 무시하고 `return false` 다 — 교체 지점
  - PDF 업로드를 `uploadFile(file, 'doc')` 로
  - 상단 "이 브라우저에만 저장돼요 · 서버 연결 준비 중" 문구와 localStorage 경로를 **함께** 제거(B8)
  - ⚠️ 가격표 임포트(512줄)는 **클라이언트 그대로** — 서버 작업 없음(B7 과 같은 정신)
- **완료 기준**: **다른 기기에서 같은 도매가** · 주문 1건 → 알림메일 수신 → 상태 3단 전이

### 5. klow_web 바이어 페이지 (모바일 + PC)

*(착수 세션에서 정밀화.)*

- **할 일 (골격)**
  - b2bpc 의 `klow_brand/src/app/[slug]/b2b` + `src/components/b2b/` 8파일을
    **klow_web `[brandSlug]/b2b`** 로 이관(README 결정 4)
  - klow_web `middleware.ts` 의 **`STOREFRONT_SEGMENTS` 에 `'b2b'` 등록** — 커스텀 도메인에서 열리게
  - 전역 `Footer` 숨김 규칙을 klow_web 쪽으로. `noindex` 유지
  - ⚠️⚠️ **`Promotion.slug` 예약 가드를 여기서 넣는다.** 정적 세그먼트 `b2b` 가
    `[brandSlug]/[influencer]` 를 이기므로 **이름이 "b2b" 인 할인 링크가 조용히 죽는다.**
    슬러그 자동 생성에 예약어 검사를 추가하고, **기존 `Promotion` 중 `slug='b2b'` 가 있는지 먼저
    SELECT** 한다. 있으면 보고하고 멈춘다(마이그레이션이 아니라 데이터 문제다)
  - ⚠️ `RESERVED_BRAND_SLUGS` 는 **최상위** 세그먼트 목록이라 `b2b` 를 넣을 필요가 없다 —
    `/{slug}/b2b` 는 2번째 세그먼트다. 두 축을 섞으면 기존 브랜드 슬러그 검증이 바뀌고, 그 목록은
    klow_server·klow_web **양쪽 미러**라 한쪽만 고치면 클라이언트 라우팅이 깨진다
  - ⚠️ 바이어 페이지는 로그인이 없다 — `/v1/brand/*` 를 부르지 않고 3단계의 공개 엔드포인트만 쓴다
- **완료 기준**: `klow.kr/{slug}/b2b` **와 커스텀 도메인 `{domain}/{slug}/b2b` 양쪽에서 열림** ·
  모바일·PC 둘 다 · 장바구니 → 주문서 → 접수 한 바퀴 · **기존 `/{slug}/{할인링크}` 무회귀**

### 6. 운영 배포

- **배포 순서**: klow_server → klow_brand → klow_web · 마이그레이션 먼저(staging → 운영)
- ⚠️ **운영 마이그레이션 큐** — 운영은 164개로 dev(167)보다 3개 적다. 이 트랙의 것은 3PL·카페24
  뒤에 줄을 선다
- **완료 기준**: 스테이징 왕복 통과 후 운영. 실브랜드 1곳으로 도매가·자료·주문 한 바퀴

---

## §4 위험 목록 (R)

| # | 위험 | 대응 |
|---|---|---|
| R1 | `b2b` 세그먼트가 이름이 "b2b" 인 할인 링크를 죽인다 | 5단계 예약 가드 + 기존 데이터 선조회 |
| R2 | PDF 업로드가 `kind:'image'` + pdf mime 조합으로 400 | 2단계에서 `kind:'doc'` 추가 + 호출부 수정 |
| R3 | 공개 응답에 제품 고시 전문이 다 실려 비대해진다 | 3단계에서 목록/상세 분리 |
| R4 | 목업 고지만 지우고 localStorage 경로가 남아 서버값을 덮는다 | B8 |
| R5 | 브랜드가 도매가를 올리면 과거 주문 금액이 따라 움직인다 | B3 금액 스냅샷 |
| R6 | 제품 삭제가 과거 주문 줄을 통째로 지운다 | B3 `onDelete: SetNull` |
| R7 | 바이어 트래픽이 브랜드관 D2C 퍼널에 섞인다 | 집계하지 않는다([`flow.md`](./flow.md) §6) |
| R8 | dev 에서 알림메일이 실제로 발송된다 | `RESEND_API_KEY=` 로 비워 실행 |
