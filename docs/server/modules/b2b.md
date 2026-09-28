# b2b — B2B 도매 (바이어 페이지 + 도매가/MOQ + 주문서)

- **모듈 경로**: `src/modules/b2b/`
- **관련 파일**: `b2b.service.ts`(브랜드측) · `b2b-public.service.ts`(바이어측) ·
  `b2b-sheet-ai.service.ts`(AI 원본 가격표 추출) · `b2b.mapper.ts`(행 → DTO) ·
  `b2b-order-email.ts`(주문 알림메일 본문) · `brand-b2b.controller.ts` · `public-b2b.controller.ts` ·
  검증 스키마 `common/validation/b2b.ts`
- **테이블**: `B2bSetting` · `B2bProductTerm` · `B2bPriceBreak` · `B2bDocument` · `B2bOrder` · `B2bOrderLine`
  (마이그레이션 `20260928100808_add_b2b_wholesale` — CREATE 만, 롤링 안전)
- **프론트**: klow_brand `/b2b`(대시보드) · klow_web `/{slug}/b2b`(바이어 페이지)
- **스펙**: [`docs/plan/b2b-wholesale/`](../../plan/b2b-wholesale/implementation-plan.md) (불변식 B1~B8)

해외 바이어가 링크 하나로 들어와 도매가·MOQ 를 보고 주문서를 넣는다. **브랜드관 위에 "도매가 + MOQ"
한 겹**을 얹는 구조라 브랜드관 쪽(메뉴·제품)은 읽기만 한다. 결제(PG)는 스코프 밖이다.

## 엔드포인트

### brand-b2b.controller.ts (`@Controller('v1/brand/b2b')`, `BrandGuard`)

| Method | Path | 기능 |
|--------|------|------|
| GET    | `/v1/brand/b2b/me` | 설정 + 제품별 조건(구간 포함, `productId → terms`) + 자료 + 주문 수(`{total, received}`) |
| PUT    | `/v1/brand/b2b/settings` | `published` · `orderEmail` · `hiddenMenuItemIds` 중 **보낸 칸만** 갱신(`patchOf`) |
| PUT    | `/v1/brand/b2b/products/:productId/terms` | 제품 하나의 조건을 **구간까지 통째 교체**. 남의/없는 제품은 404 |
| POST   | `/v1/brand/b2b/documents` | 자료(PDF) 메타 등록 — 파일은 먼저 `POST /v1/brand/upload` `kind:'doc'` 로 올린다. 브랜드당 20개 |
| PATCH  | `/v1/brand/b2b/documents/:id` | `lang` · `inMenu` · `menuLabel` (url·filename 은 못 고친다 — 교체는 새 문서로) |
| DELETE | `/v1/brand/b2b/documents/:id` | 삭제. R2 객체는 지우지 않는다 |
| GET    | `/v1/brand/b2b/orders` | 받은 주문 최신순(최대 500) |
| PATCH  | `/v1/brand/b2b/orders/:id` | 상태 전이 `received → confirmed → done` (`{status}`) |
| POST   | `/v1/brand/b2b/import/preview` | **AI 원본 가격표 추출 미리보기** (multipart `file` + 선택 `layout`). 10회/분 |

- ⚠️ `PUT /v1/brand/applications` 에 얹지 않았다(B1) — 거기선 한 칸의 zod 400 이 색·폰트·링크 저장까지 죽인다.
- ⚠️ 목업(`b2b-store.saveB2b`)은 레코드 통째 덮어쓰기였다. **필드별로 갈랐다** — 제품 하나의 저장이
  다른 제품의 도매가를 건드리지 않는다.
- `GET /me` 는 행이 없는 설정을 기본값(`published:false` · `orderEmail` = 계정 이메일)으로 **보여만** 준다.
  첫 `PUT /settings` 가 그 보이던 값 위에 보낸 칸을 얹어 행을 만든다(공개 토글만 켜도 알림 주소가 빈 값으로 굳지 않게).
- 조건 검증(`B2bTermsInput`): 금액 ≥0(0 = 미입력), **통화 소수 자릿수**(KRW·JPY 0 / 나머지 2), MOQ 0~999,999,
  구간 ≤5 · 구간 수량 > `max(MOQ,1)` · 중복 수량 금지 · 구간가 >0.

### public-b2b.controller.ts (`@Controller('v1/b2b')`, 인증 없음)

| Method | Path | 기능 |
|--------|------|------|
| GET    | `/v1/b2b/:slug?lang=` | 바이어 페이지 한 벌 — `{status:'open', brand, menuItems, documents, products}` 또는 `{status:'preparing', brand}` |
| GET    | `/v1/b2b/:slug/products/:productId` | 제품 상세 단건(고시·성분·상세컷 포함) |
| POST   | `/v1/b2b/:slug/orders` | 주문서 접수 → 알림메일. **5회/분/IP** |

- ⚠️⚠️ **`published` 는 서버가 보는 게이트다**(B4). 꺼져 있거나 브랜드가 서비스 불가(승인 취소·구독 끊김)면
  `status:'preparing'` + 브랜드 머리값만 준다 — **404 가 아니다.** 바이어에게 보낸 링크는 살아 있어야 한다.
  브랜드 자체가 없거나 공개 대상이 아니면(`isPublicBrand`) 그때만 404.
- 브랜드 머리값에 **`tagline` 원문을 싣지 않는다**(B5) — `tags`(파싱된 배열)만. `?lang=` 은 브랜드관과 같은
  `BrandTranslationService.localize` 를 탄다.
- `menuItems` 는 **브랜드관 메뉴 그대로**에서 `hidden` 줄과 `B2bSetting.hiddenMenuItemIds` 를 뺀 것이다(B6 —
  두 벌 들지 않는다). 빈 페이지·빈 링크 정리와 상점 칸 펼치기는 브랜드관과 같은 클라 로직이 한다.
- 제품 게이트는 브랜드관(`PUBLIC_PRODUCT_WHERE`)과 **다르다** — `approved` + 대표사진만 본다. 브랜드관에서 가린
  제품(`hidden`)도, D2C 판매가가 없는 제품도 도매로는 걸 수 있다. 노출은 `B2bProductTerm.visible && price > 0`.
- 목록은 카드 필드만(`d2cUsdCents` = `defaultListUsd` — 국가 핀과 무관한 기본 판매가, 취소선 기준). 상세 필드는 단건으로.
- ⚠️ 조회에는 스로틀을 따로 걸지 않는다(전역 기본) — 부스·사무실 NAT 뒤 여러 바이어가 한 IP 로 연다.

#### 주문 접수 규칙

- **금액은 받지 않는다.** 바디는 `{buyer:{company,contact,email,country,note}, lines:[{productId, qty}]}` 뿐이고,
  서버가 **지금의 거래 조건**으로 단가(구간 적용)를 다시 계산해 스냅샷으로 굳힌다(B3). 계산은 최소단위 정수.
- 400: `b2b_product_unavailable`(없음·숨김·가격 0) · `b2b_mixed_currency`(한 주문서 = 한 통화) ·
  `b2b_invalid_qty`(MOQ 미만 — 배수 조건은 없다. 바이어 화면 `clampQty` 와 같은 규칙) · `b2b_duplicate_line`.
  409: `b2b_not_published`.
- 알림메일은 **저장 뒤에** 보낸다(`EmailService.sendB2bOrderNotice`, replyTo = 바이어). 실패해도 주문은 남고
  `notifiedAt` 이 null 로 남아 대시보드가 그대로 고지한다. `orderEmail` 이 빈 값이면 보내지 않는다.
  ⚠️ dev 에서 `RESEND_API_KEY` 가 켜져 있으면 **실제로 발송된다** — 테스트는 `RESEND_API_KEY= npm run start`
  (그때는 콘솔 로그로 대체되고 `notifiedAt` 이 찍힌다).
- 바이어 응답에는 브랜드 알림 주소를 싣지 않는다.

## AI 원본 가격표 추출 (`b2b-sheet-ai.service.ts`)

브랜드가 거래처에 보내던 엑셀을 그대로 올리면 제품별 도매가·MOQ·구간을 뽑는다. **미리보기만** 하고
저장하지 않는다 — 적용은 확정한 줄마다 `PUT products/:id/terms` 를 탄다(검증 한 벌).

- ⚠️⚠️ **AI 는 레이아웃(시트·열 번호)만, 금액·수량은 서버가 원본 셀에서 읽는다**(B7-1) —
  `shipping/rate-sheet-ai.service.ts` 와 같은 2단계. 그 파일을 일반화하지 않고 따로 뒀다(축·상한이 다르다).
- 응답: `{layout, sheets, columns[{index,header,numericCount,textCount}], rows[{index, sourceName, productId|null,
  matchScore, currency, price, priceText, moq, tiers, warnings}], skipped[{index,name,price,reason}], warnings}`.
  `priceText` 는 원본 셀 표기 그대로다(대조용).
- `layout` 을 같이 보내면 **AI 재호출 없이** 재추출한다(열 바꿔 고르기).
- ⚠️⚠️ **MOQ 열은 서버가 헤더로 정한다**(AI 경로): 명시적 MOQ 열(`MOQ_HEADER_RE`) → 없으면 **`U/B`·박스당 입수 열 = MOQ**
  (`PACK_HEADER_RE`, 1박스가 최소 주문 — 경고 한 줄로 알린다) → 없으면 0. AI 가 짚은 열은 믿지 않는다(notes 와 모순된 답을 낸 적이 있다).
  브랜드가 `layout` 으로 직접 고른 값(-1 = 없음 포함)은 그대로 따른다. ⚠️ 계획서 B7-2("U/B 는 MOQ 가 아니다")는 2026-09-28 사용자 결정으로 뒤집혔다.
- ⚠️ 헤더 줄은 AI 의 `dataStartIndex` 로 정하지 않는다 — **단가 열의 첫 숫자 행 바로 위 5줄 중 채워진 칸이
  가장 많은 줄**(`findHeaderRow`). AI 가 헤더 줄 자체를 시작으로 준 호출에서 타이틀 줄이 헤더로 읽혀
  열 판정이 통째로 틀린 적이 있다(스펙이 그 모양을 잠근다).
- 구간 열의 `minQty` 는 **헤더에서 서버가 다시 읽는다**(`100+`·`500~999`·`1,000 pcs`). MOQ 이하 구간·
  6번째 이후 구간은 떨구고 줄 `warnings` 에 적는다 — 저장 스키마가 400 을 낼 줄을 미리보기에 내지 않는다.
- 단가 칸이 빈 줄(라인 구분행)·헤더 반복 줄은 조용히 건너뛰고, 숫자가 아닌 단가(`문의`)는 `skipped` 에 사유와 함께 낸다.
- 제품 매칭은 **후보만** 댄다(B7-3) — `Product` 에 SKU·바코드가 없다. 이름 토큰 유사도(브랜드 괄호·기호 무시)
  0.5 이상을 점수 높은 쌍부터 1:1 로 묶는다. 확정은 사람이 미리보기에서 한다.
- 통화는 `USD·KRW·EUR·JPY·CNY` 만. 밖이면 400. 파일 상한 15MB(사진 시트를 품는 가격표가 흔하다).
- 스펙: `src/modules/b2b/__tests__/b2b-sheet-extract.spec.ts`.
