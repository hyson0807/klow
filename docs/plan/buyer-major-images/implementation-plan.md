# buyer-major-images — 구현 계획 (정본)

결정·배경은 [`README.md`](./README.md). 상태는 `docs/PROGRESS.md §7` 만이 정본이다.

## 0. 현재 코드 전제 (2026-10-31 조사)

- 메이저 제품: `BuyerMajorProduct.images String[]`(R2 URL, 운영은 `https://cdn.klow.kr/brands/buyer/major/<uuid>.<ext>`) — `klow_server/prisma/schema.prisma`
- 어드민 메이저 API: `src/modules/buyer/admin-buyer-major.controller.ts`(AdminGuard, prefix `admin/buyer`) · 서비스 `buyer-major-admin.service.ts`
- 서버 의존성 이미 있음: `openai@^6`(다른 모듈이 `new OpenAI` 사용 — `src/common/sheet-ai.ts` 참고) · `sharp@^0.33`
- R2 업로드: `src/modules/upload/r2.service.ts` `uploadBytes({scope, folder, body, contentType, ext})` → `brands/<scope>/<folder>/<uuid>.<ext>`
- 어드민 화면: `klow_admin/src/app/(authed)/buyer/major/`(목록 · `[id]` 브랜드 편집 · `products/[id]`) · API 클라 `src/lib/api/` 배럴 · 토스트 `useToast()`(CLAUDE.md Admin UI Convention)
- 바이어 공간 이미지 칸: 카드 4:5(`.card__frame`) · 상세 썸네일 1:1 · 전부 `object-fit: cover` · `<img>` 원본 직접 로드
- ⚠️ **`§7` 53행(remove-buyer-sample)이 `BuyerMajorProduct.sampleable` 을 DROP** 했다(staging 적용됨, 운영 미배포). 이 트랙은 그 브랜치가 들어간 `staging` 위에서 시작한다. 같은 이유로 미추적 `klow_server/scripts/import-buyer-majors.ts` 의 `sampleable` 참조도 53행 운영 배포 전에 제거해야 한다(스킬 `oliveyoung-major-import` 사용 시 깨짐).

## 1. 게이트 (불변식)

- **G1 원본 보존** — 적용 전 `images` 를 백업한다. 되돌리기는 제품·브랜드 단위로 언제든 가능. 원본 R2 객체는 지우지 않는다.
- **G2 생성 ≠ 적용** — 생성 결과는 초안 테이블에만. `BuyerMajorProduct.images` 는 **적용 API** 에서만 바뀐다.
- **G3 출력 규격** — 4:5 · 1024×1280 · WebP · ≤ 250KB. 규격 밖이면 실패 처리(업로드 안 함).
- **G4 비용 가드** — 페이지 진입·목록 조회는 생성 0회. 생성은 명시적 버튼만. 브랜드 전체 생성은 확인창(제품 수 × 단가 표시). 같은 제품·같은 프롬프트 버전의 진행 중 초안이 있으면 중복 생성 안 함.
- **G5 실패 격리** — 한 장 실패(429·타임아웃·안전필터 거절)가 나머지를 멈추지 않는다. 429 는 지수 백오프 재시도(최대 3회), 그 외는 `failed` + 사유 저장 → 어드민 재시도 버튼.
- **G6 동시성 상한** — 서버 전체 동시 생성 N(기본 3, env). 서버 재시작 시 `running` 초안은 `queued` 로 되돌려 다시 집는다(유실 없음).
- **G7 키는 서버만** — `OPENAI_API_KEY` 는 클라로 안 나간다. 키 없으면 생성 API 503(화면은 안내).
- **G8 프롬프트 버전** — 초안에 `promptVersion` 저장. 프롬프트 원문은 서버 상수 파일 하나(`*.prompts.ts` — CLAUDE.md 접미사 규칙).

## 2. 설계

### 2-1. 스키마 (A 단계 · 마이그레이션 독립)

```prisma
model BuyerMajorImageDraft {
  id             String   @id @default(cuid())
  majorProductId String
  sourceUrl      String   @db.VarChar(500)    // 생성에 쓴 원본(images[0])
  resultUrl      String?  @db.VarChar(500)    // R2 WebP
  status         BuyerMajorImageDraftStatus @default(queued) // queued·running·done·failed·applied·discarded
  error          String?  @db.VarChar(500)
  promptVersion  String   @db.VarChar(20)
  isTest         Boolean  @default(false)
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  majorProduct   BuyerMajorProduct @relation(fields: [majorProductId], references: [id], onDelete: Cascade)
  @@index([majorProductId, status])
  @@index([status, createdAt])
}
// BuyerMajorProduct 에 추가: originalImages String[] @default([])  — 최초 적용 시 1회 백업(이후 덮어쓰지 않음)
```

신규 테이블 + nullable/default 컬럼뿐 → **롤링 안전 · 백필 없음**.

### 2-2. 서버 (klow_server `src/modules/buyer/` — 평면 파일, 접미사 규칙)

- `buyer-major-image.prompts.ts` — 프롬프트 원문(§4) + `PROMPT_VERSION`
- `buyer-major-image.service.ts` — 큐 적재·상태 조회·적용·되돌리기
- `buyer-major-image.worker.ts`(또는 서비스 내부) — `onModuleInit` 에서 `running→queued` 복구, 인메모리 동시성 N 으로 `queued` 를 집어 처리:
  1. 원본 fetch(허용 호스트 = R2 공개 도메인만 — SSRF 방지)
  2. `openai.images.edit({ model, image, prompt, size: '1024x1536', quality, output_format: 'webp' })`
  3. `sharp` → 1024×1280 크림색(프롬프트 배경과 같은 색) 패딩/중앙 크롭 → WebP q80, 크기 검사(G3)
  4. `r2.uploadBytes({ scope:'buyer', folder:'major-gen', ... })` → `done`
- 컨트롤러는 기존 `admin-buyer-major.controller.ts` 에 추가(AdminGuard):

| Method | Path | 동작 |
|---|---|---|
| POST | `admin/buyer/major-brands/:id/image-drafts/test` | body `{productId?}`(없으면 첫 제품) — 1장 적재(`isTest`) |
| POST | `admin/buyer/major-brands/:id/image-drafts` | 브랜드 전 제품 적재(이미 `done`·진행 중인 제품 제외 옵션) |
| GET | `admin/buyer/major-brands/:id/image-drafts` | 제품별 최신 초안 + 원본 대표 이미지 + 진행 요약 |
| POST | `admin/buyer/image-drafts/:draftId/retry` · `/discard` | 개별 재시도·버리기 |
| POST | `admin/buyer/major-brands/:id/image-drafts/apply` | body `{draftIds[]}` — `done` 만 적용(G2·G1) |
| POST | `admin/buyer/major-brands/:id/image-drafts/revert` | body `{productIds[]}` — `originalImages` 로 복원 |

- ⚠️ 감사 로그: admin mutation 은 `AdminAuditInterceptor` 가 자동 기록(추가 작업 없음).
- 적용 규칙(착수 시 사용자 확인 1번에 따라): 기본 (a) `images = [resultUrl, ...originalImages]`(최대 `BUYER_MAX_IMAGES`).

### 2-3. 어드민 (klow_admin)

- 새 화면 `(authed)/buyer/major/images/page.tsx`(메이저 목록 상단 링크 또는 탭):
  1. 브랜드 셀렉트(메이저 브랜드 목록 재사용)
  2. **테스트** 버튼 — 제품 1개 선택(기본 첫 제품) → 원본 | 결과 나란히(4:5 프레임) → 재생성/버리기
  3. **브랜드 전체 생성** — 확인창(제품 수 × 예상 단가) → 진행 그리드(제품 카드: 원본·결과·상태 배지, 3~5초 폴링, 전부 끝나면 폴링 중지)
  4. 카드별 체크(기본: `done` 전부 체크) → **선택 적용** · 적용된 제품은 **되돌리기**
- 모든 생성·적용·실패는 토스트(Admin UI Convention). 폴링은 탭이 숨겨지면 멈춤.

## 3. 단계

### A. klow_server — 스키마 + 생성 워커 + 어드민 API  (`§7` 55행)

- **읽을 것**: 이 문서 §0~§2 · `README.md` 착수 시 확인 3가지 · `docs/server/modules/buyer.md#메이저-브랜드` · 결정 storefront 2026-10-22·2026-10-29
- **선행**: `§7` 53행 브랜치가 들어간 `staging`. 사용자 확인 3가지(README) 답 받기
- **건드리는 레포 · 배포 순서**: klow_server 단독(B 보다 먼저 — 어드민은 새 API 없으면 화면만 실패)
- **스키마·데이터 위험**: `add_buyer_major_image_drafts`(CREATE 1 + ADD COLUMN default 1 · 롤링 안전 · 백필 없음). ⚠️ git `feat/buyer-major-images` + **Neon DB 브랜치**(CLAUDE.md 규칙)
- **세션 안 순서(정지점)**: ① 마이그레이션 ② 프롬프트·서비스·워커(로컬에서 실제 1장 생성 — 키 필요, 약 $0.3) ③ 컨트롤러 + zod ④ `docs/server/modules/buyer.md` ⑤ 검증 3층(e2e 의 DI 그래프 — 워커 provider 등록 확인)
- **완료 기준**: 로컬 DB 브랜치에서 테스트 API 1회 → 1~2분 내 `done` + R2 WebP 1024×1280 ≤250KB · 같은 제품 재요청 시 중복 적재 안 됨 · 적용 → `images[0]` 교체 + `originalImages` 백업 · 되돌리기 → 원복 · 서버 재시작 중 `running` → 재처리됨 · 키 없을 때 503

### B. klow_admin — 제작 페이지 + 배포  (`§7` 56행)

- **읽을 것**: A 의 인계 메모 · 이 문서 §2-3 · `klow_admin/src/app/(authed)/buyer/major/` · CLAUDE.md Admin UI Convention
- **건드리는 레포 · 배포 순서**: klow_admin → (마무리) staging: DB migrate → server → admin · 운영: 같은 순서
- **스키마·데이터 위험**: 없음(A 의 마이그레이션 배포만)
- **세션 안 순서(정지점)**: ① 화면·API 클라 ② 로컬 왕복(브랜드 1개 테스트 → 전체 → 적용 → 되돌리기) ③ staging 배포 + staging 에서 소브랜드 1개 실생성 ④ 운영 배포(사용자 확인 후) — 운영 시범 브랜드 1개는 사용자가 화면으로
- **완료 기준**: 어드민에서 브랜드 선택 → 테스트 결과 확인 → 전체 생성 진행 그리드 → 선택 적용 → klow.kr 브랜드 페이지에 4:5 새 이미지 노출 → 되돌리기 원복

## 4. 프롬프트 원문 (사용자 제공, 2026-10-31 — `PROMPT_VERSION = 'v1'`)

```
IMAGE FORMAT: 4:5 portrait aspect ratio (width:height). This is mandatory.

[PRODUCT FOCUS & TEXT REMOVAL]
Extract ONLY the physical main product item(s) from the reference image. Completely REMOVE and ERASE all text elements, badges, stickers, graphic overlays, promotional icons, floating water droplets, and background marketing text (e.g., Korean/English description badges, promotional slogans, text bubbles). Do NOT render any text that is not physically printed directly on the product's actual container label.

[STRICT PROPORTION & DIMENSION PRESERVATION]
CRITICAL: Maintain the EXACT original height-to-width ratio (aspect ratio) and geometric proportions of every product as seen in the reference image. Do NOT stretch, elongate, compress, or deform the products vertically or horizontally. Keep the original bottle shape, cap-to-body proportion, and contour lines 100% authentic and unskewed.

[PHOTO PRESERVATION]
Keep the physical product container, cap, label artwork, and packaging design pixel-perfect identical to the reference image. Do NOT alter, redesign, or modify the brand logo, container material, transparent textures, or colors of the physical bottle.

[PRODUCT COUNT]
Use EXACTLY the same number of physical product items as shown in the reference image. Do NOT add extra boxes, bottles, vials, or secondary objects.

[3D POSITIONING & DISPLAY]
Transform the main product into a realistic three-dimensional standing studio display. The product should stand upright on a clean flat surface showing front face, subtle side edge, and top cap with natural perspective and realistic depth, without altering its natural vertical dimensions.

[COMPOSITION]
The primary product takes up 65-75% of the frame. Prominently displayed, centered, clearly visible, and perfectly in sharp focus. NO promotional badges, NO floating graphics, NO syringes, NO extra props.

[LIGHTING & BACKGROUND]
Solid, clean, warm off-white soft cream background tone — matte finish, completely free of any text, graphics, or patterns. Soft diffused studio lighting from upper left with realistic gentle shadows beneath the base of the product. Clean, minimal, high-end commercial product photography, sharp focus, 8K quality.
```

⚠️ 모델은 4:5 를 직접 못 낸다 — 2:3 로 받고 서버가 4:5 로 맞춘다(D2). 프롬프트의 4:5 문구는 구도 지시로만 작동한다.
