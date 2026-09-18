# brand-notices — 브랜드관 공지 팝업

- **모듈 경로**: `src/modules/brand-notices/`
- **관련 파일**: `notice-window.ts`(게시 기간 판정 단일 출처), `brand-notices.service.ts`,
  `notice-translation.service.ts`, `brand-notices.controller.ts`,
  `public-brand-notices.controller.ts`, 검증 스키마 `common/validation/brand-notice.ts`
- **프론트**: klow_brand 설정 > 공지사항(`settings/_components/NoticeSection.tsx`),
  klow_web `components/brand/BrandNoticeModal.tsx` + `lib/notice-dismiss.ts`

브랜드가 **기간을 정해** 올린 안내를 손님이 브랜드관에 들어올 때 **팝업**으로 한 번 띄운다.
손님은 "오늘 하루 보지 않기"로 닫는다. 추석 연휴 배송 공지 요청에서 나왔다.

노출은 **팝업만**이다 — 닫으면 그날은 흔적을 남기지 않는다(상단 배너 없음). 기간이 겹치는 공지가
여럿이면 한 팝업 안에 세로로 나열된다.

## 왜 Json 이 아니라 테이블인가

`Brand.story` 는 Json 인데 공지는 테이블이다. 이유는 **번역**이다. `BrandTranslation` 은
`tagline`/`description` **스칼라 컬럼** 모델이라 Json 배열을 담지 못하고, 그래서 story 는 애초에
번역 대상에서 빠져 있다. 공지는 원문이 한국어인데 브랜드관 손님 다수가 해외라 자동 번역이
요구사항이므로, **짧은 스칼라 텍스트 + 1:N 캐시**라야 기존 파이프라인(`ReviewTranslation`)에 붙는다.

## ⚠️⚠️ 시계가 둘이고 의도적으로 다르다

| 축 | 기준 | 소유 |
|---|---|---|
| 게시 기간(`startAt`/`endAt`) | **KST** — 브랜드의 달력 | 서버 `notice-window.ts` |
| "오늘 하루 보지 않기" 만료 | **뷰어 로컬 자정** | klow_web `lib/notice-dismiss.ts` |

브랜드가 "9/29~10/3"이라 쓸 때 그건 한국 추석이다. 반면 팝업을 보는 사람은 해외 손님이라
KST 자정은 베트남 22:00·UAE 전날 19:00·미국 동부 전날 오전이다 — **KST 로 통일하면 손님이
오후에 닫은 팝업이 같은 날 저녁에 다시 뜬다.** 한쪽에 맞추려 들지 말 것.

회귀 잠금은 `klow_web` 의 `npm run check:notice-dismiss` 다. ⚠️ 이 검사는 `TZ` 환경변수에
반응한다 — KST 하드코딩 구현을 잡는 **유일한** 방법이다(`TZ=Asia/Ho_Chi_Minh` 로 돌리면 실패한다).

## 엔드포인트

### brand-notices.controller.ts (`@Controller('v1/brand/notices')`, `BrandGuard`)

| Method | Path | 기능 |
|--------|------|------|
| GET    | `/v1/brand/notices`      | 전체(만료·꺼짐 포함) — 편집 화면용. 행마다 `state` 동봉 |
| POST   | `/v1/brand/notices`      | 생성. 브랜드당 `MAX_BRAND_NOTICES`(20) 초과 시 400 |
| PATCH  | `/v1/brand/notices/:id`  | 수정 |
| DELETE | `/v1/brand/notices/:id`  | 삭제 |

- ⚠️ **경로에 brandId 가 없다** — 세션(`requireBrandId`)에서 꺼내므로 남의 브랜드를 가리킬 방법이
  구조적으로 없다(`brand-storefront-translations` 와 같은 판단).
- ⚠️ 소유권은 `where: { id, brandId }` 로만 좁히고 실패는 `Forbidden` 이 아니라 **`NotFound`** 다
  — id 를 넣어 보며 남의 공지 존재를 열거하지 못하게(`brand-reviews` 와 같은 방침).
- ⚠️⚠️ **이 GET 은 번역 서비스를 부르지 않는다.** 부르면 브랜드가 설정 카드를 펼칠 때마다
  Google 번역 과금 + 캐시 write 가 난다(`brand-translation.service.ts` 의 같은 경고).
- ⚠️ `state`(`live|scheduled|ended|off`)를 **서버가 계산해 내려준다.** klow_brand 가 날짜에서
  직접 파생하면 판정 사본이 둘이 되어 "배지는 게시 중인데 손님에겐 안 보임"이 조용히 난다.

### public-brand-notices.controller.ts (`@Controller('v1/brands')`, 공개)

| Method | Path | 기능 |
|--------|------|------|
| GET | `/v1/brands/:brandId/notices?lang=` | 지금 게시 중인 공지만, 요청 locale 로 번역 |

**왜 브랜드 상세(`by-slug`)에 얹지 않았나** — 셋 다 결정적이다:

1. `PUBLIC_BRAND_DETAIL_SELECT` 는 모듈 최상위 `as const` **상수**인데 공지는 `now` 가 필요하다.
   상수에 넣으면 기간이 **모듈 로드 시각에 얼어붙는다**(`brand-selects.ts` 의
   `brandUnserviceableSinceWhere` 가 같은 이유로 함수다).
2. 번역은 캐시 미스 시 Google 왕복이다. 얹으면 브랜드관 **모든** 첫 렌더가 그 왕복을 기다린다.
   팝업은 지연 가능한 표면이다.
3. 선례가 같다 — `GET /v1/reviews/translations` 도 "원문이 한국어라 en 도 번역 대상"이라는
   같은 이유로 전용 라우트다.

- ⚠️ `v1/brands` 프리픽스를 `public-brands.controller.ts` 와 공유하지만 세그먼트 깊이가 달라
  (`:id` vs `:brandId/notices`) 충돌하지 않는다.
- ⚠️ **브랜드 공개 게이트(`PUBLIC_BRAND_WHERE`)를 반드시 통과**한다 — 탈퇴·거절 브랜드의 공지가
  새면 안 된다. 술어를 새로 쓰지 말고 `brand-selects.ts` 것을 가져다 쓴다.
- ⚠️ 없는/비공개 브랜드는 404 가 아니라 **빈 배열**이다. 팝업은 부가 표면이라 실패가 브랜드관
  렌더를 막으면 안 된다(fail-soft).
- ⚠️ **응답은 공개 투영**(`{id,title,body,imageUrl}`)이다. `startAt`/`endAt`/`enabled` 를 내리면
  누군가 클라에서 기간 판정을 재구현하고 그 판정은 서버의 KST 경계와 갈린다.

## ⚠️⚠️ en 번역 트랩

공지 원문은 브랜드가 쓴 **한국어**다. 그런데 klow_web `lib/api.ts` 의 `addLang()` 은
`lang === 'en'` 이면 쿼리를 **안 붙인다**(제품·브랜드는 원문이 영어라 맞는 최적화다).
그대로 두면 **US/SG 손님 + `COUNTRY_TO_LOCALE` 미매핑 국가 + 국가를 아직 안 고른 게스트**가
한국어 공지를 본다 — QR·인플루언서 링크로 들어온 첫 화면이 정확히 그 상태다.

막는 곳이 **둘**이다(한쪽만 두면 조용히 샌다):
1. 클라 — `api.brands.notices()` 가 `addLang` 을 **쓰지 않고** locale 을 항상 붙인다.
2. 서버 — `normalizeNoticeLocale(lang)` 이 부재·미지원을 **`en` 으로 떨어뜨린다**.
   리뷰(`normalizeReviewLocale`)가 미지원에 한국어 원문을 돌려주는 것과 **의도적으로 다르다** —
   klow_web `SUPPORTED_LOCALES` 에 `ko` 가 없어 **한국어 원문이 정답인 locale 이 하나도 없다**.
   이건 동시에 **과금 누수 가드**이기도 하다(화이트리스트 밖 문자열이 Google 로 가면 값마다 캐시 미스).

## 번역 캐시

`ReviewTranslationService` 와 같은 구조다. `NOTICE_TRANSLATABLE_LOCALES = ['en', ...TRANSLATABLE_LOCALES]`
이고 비-en 멤버는 **파생**한다(동기화 지점 1개 — 회귀 스펙이 일치를 단언해, 제품에 로케일이 늘 때
공지만 조용히 빠지는 걸 막는다).

- ⚠️⚠️ **`translateBatch(texts, locale, 'ko')` — 3번째 인자가 필수다.** 그 함수의 `source`
  기본값이 `'en'` 이라 빠뜨리면 한국어를 영어라고 선언해 번역이 조용히 망가지고 **타입이 못 잡는다**.
- ⚠️ 제목·본문을 한 배열로 이어 붙여 1회 배치로 보내므로, 재조립은 `stale.length` 오프셋으로
  **명시적 인덱싱**한다. 공유 커서(`out[i++]`)를 쓰면 off-by-N 이 난다.
- ⚠️ 실패는 **원문 폴백 + 캐시 미기록**(다음 요청이 재시도할 수 있게) + **`Logger.warn`**.
  리뷰 쪽의 완전 침묵 `catch {}` 는 베끼지 않는다 — 전 손님이 한국어 공지를 보는 상태가
  아무 흔적 없이 지속된다.
- 스테일 판정이 `sourceUpdatedAt < BrandNotice.updatedAt` 이라 **`enabled` 토글 하나에 전 로케일이
  재번역된다**(제품·브랜드·리뷰가 전부 같은 방식이라 수용한다). 그래서 raw SQL·`updateMany` 로
  본문만 바꾸면 `@updatedAt` 이 안 올라 옛 번역이 영원히 서빙된다.

## 게시 기간

판정의 단일 출처는 `notice-window.ts` 다 — Prisma where(`liveNoticeWhere`)·JS 짝(`isNoticeLive`)·
배지(`noticeStateOf`)를 **한 블록**에 둔다(`brand-selects.ts` 의 `*_WHERE` / `is*()` 관례).

```
enabled && (startAt == null || startAt <= now) && (endAt == null || endAt > now)
```

- ⚠️ **종료는 반열림(`endAt > now`)** 이고 `endAt` 에는 종료일 **다음날** 00:00 KST 가 들어 있다.
  `lte: 그날 23:59:59` 로 바꾸면 마지막 1초 미만이 잘린다(`kst-time.ts` 의 `kstYmdRange` 가 같은
  이유로 반열림으로 통일돼 있다).
- ⚠️ `liveNoticeWhere` 가 **팩토리 함수**인 것이 중요하다. 모듈 최상위 상수면 `now` 가 프로세스
  부팅 시각에 얼어붙어 오래 뜬 서버에서 기간이 영영 안 바뀐다.
- 와이어 포맷은 **`'YYYYMMDD'`**(하이픈 없음) — 기존 `parseKstYmd` 가 그 형식을 받고 존재하지
  않는 날짜(`20260931`)를 롤오버 없이 거부해 **신규 공용 날짜 코드가 0줄**이다. klow_brand 의
  `DateRangePicker` 는 `'YYYY-MM-DD'` 를 내므로 클라가 하이픈을 벗겨 보낸다.
- ⚠️ `new Date('2026-09-29')` 금지 — UTC 자정이라 KST 로 9/28 09:00 이 되어 공지가 하루 일찍 뜬다.

## 그 밖의 ⚠️

- **사진**은 기존 `POST /v1/brand/upload`(presigned R2)를 그대로 쓴다 — 신규 업로드 라우트 없음.
  zod 는 `BrandStorySchema` 의 `StoryImageUrl` 과 같은 모양(`''` → `null` transform)이다.
  `z.string().url().optional()` 로 두면 **첨부한 사진을 지울 방법이 없다**(undefined = 미변경).
- **klow_web 렌더**: 사진은 `w-full h-auto` 다. 공지 사진은 십중팔구 **글자가 든 세로 카드**라
  고정 비율 + `object-cover` 는 그 글자를 잘라낸다. 본문은 `whitespace-pre-wrap` 평문이고
  **`dangerouslySetInnerHTML` 금지**(브랜드 자유 텍스트).
- **모달 충돌**: 팝업 게이트는 `sessionReady && (authed || country != null)` 로 **원인**을 본다.
  `useUiStore.onboardingOpen === false` 로 막으면 레이스다 — 그 초기값이 `false` 라 국가 선택
  모달이 effect 에서 열리기 전 프레임에 두 시트가 같이 마운트되고, 겹치면 `body.overflow`
  저장/복원이 서로를 덮어 **스크롤이 영구 잠긴다**.
- **현장(부스 QR)은 제외**한다 — 배송이 없어 배송 공지가 무의미하고 결제 직전 손님 폰에 모달이
  뜨는 건 마찰이다. 되돌리려면 `!isOnsite` 한 줄만 빼면 된다.
- **할인 링크 랜딩**(`/{slug}/{influencer}`)도 같은 `BrandStorefront` 를 렌더하므로 자동으로 함께 커버된다.
- **dismiss 키는 `noticeId` 만**이다. `${id}:${updatedAt}` 로 잡으면 브랜드가 게시 기간을 하루
  연장하거나 노출 토글만 껐다 켜도 `@updatedAt` 이 올라 닫았던 **전 손님에게 다시 뜬다**.
- **i18n 키를 1개만 추가했다**(`brand.notice.hideToday`, 닫기는 기존 `common.close`). ⚠️ 그 1개도
  `npm run i18n:fill` 없이 **8개 파일에 손으로** 넣었다 — fill 은 en 과 값이 같은 leaf 를 미번역으로
  보고 재번역해 `labels.category` 큐레이션 값(`id.mist`·`vi.toner`·`vi.serum`)을 갈아엎는다.
- **klow_admin 은 무변경**이다(어드민에 공지 편집 UI 없음).
- 브랜드 하드삭제는 `onDelete: Cascade` 가 처리한다 — `brands.service.remove()` 변경 없음.

## 마이그레이션

`20260918081103_add_brand_notices` — `CREATE TABLE` ×2 + 인덱스 + FK 뿐 →
**롤링 배포 안전 · 백필 없음 · cron 10개 불변**(e2e 기대 목록 무수정). 라우트 **+5**.

## 회귀 잠금

- `brand-notices/__tests__/notice-window.spec.ts` — 종료일 당일 23:59 포함(off-by-one)·
  KST 새벽 날짜 밀림·롤오버 거부·`stateOf` ↔ 노출 술어 일치·`liveNoticeWhere` 가 호출 시각을 쓴다
- `notice-translation.spec.ts` — 캐시 히트 시 `translateBatch` 0회·**source 가 `'ko'`**·
  제목/본문 인덱스 짝·실패 시 캐시 미기록·`lang` 없음 → `en`·locale 목록이 제품과 일치
- `notice-scope.spec.ts` — 소유권 where·남의 공지는 **404**·상한 400·공개 게이트·
  **브랜드 편집 목록이 번역을 안 탄다**
- klow_web `npm run check:notice-dismiss` — ⚠️ **`TZ` 에 반응한다**(KST 하드코딩을 잡는 유일한 방법)

## 배포 순서

**klow_server → klow_brand → klow_web**

- klow_brand 를 먼저 내면 편집 화면이 404
- klow_web 을 먼저 내면 공지 조회가 404 → 팝업만 안 뜨고 브랜드관은 정상(fail-soft)

⚠️ **배포만으로는 아무것도 달라지지 않는다** — 브랜드가 공지를 작성해야 손님에게 뜬다.
