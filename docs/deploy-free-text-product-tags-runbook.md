# 배포 런북 — 제품 태그 자유 텍스트 전환 + 고정 키워드 폐지 (2026-07-30)

제품의 **주요 고민 / 추천 피부 타입**을 고정 enum(11개 concern 키 + 4개 한국어 피부타입)에서
**자유 텍스트 태그**(영문 저장 → 로케일별 MT 노출)로 바꾸고, 같은 enum 을 쓰던 개인화·필터 기능을
전부 제거하는 릴리스의 프로덕션 배포 절차.

관련: [`architecture.md`](./architecture.md) · [`server/modules/translation.md`](./server/modules/translation.md) ·
[이전 DROP COLUMN 릴리스](./deploy-drop-logistics-markup-runbook.md)

## 왜 순서가 중요한가

두 가지가 걸려 있다.

1. **DROP COLUMN 8개**(`User.skinType/concerns`, `Creator.skinType/concerns`,
   `Video.concerns/forSkinTypes`, `Review.userSkinType`, `ShopSettings.todaysPickConcern`).
   구 코드는 이 컬럼들을 `SELECT` 하므로 마이그레이션과 **공존할 수 없다** → 롤링 배포 불가,
   **단일 레플리카 컷오버**가 필요하다. (`country_free_shipping` 과 같은 종류의 위험.)
2. **백필은 코드 배포 *후***. 백필이 `hydration`→`Hydration` 으로 값을 바꾸는데, 구 코드의
   concern 칩·ConcernPicks·TodaysPick 은 enum 키로 조회하므로 배포 전에 돌리면 그 화면들이
   조용히 빈 목록이 된다. 반대로 신 코드의 태그 입력은 `initial.concerns` 를 값 그대로 칩으로
   띄우는 **값 무관(value-agnostic)** 구조라, 백필 전에 브랜드가 제품을 저장해도 미백필 값을
   덮어쓰지 않는다.

| 순서 | 그 구간 증상 |
|---|---|
| **마이그레이션 → 코드 → 백필** ✅ | 1~2분간 PDP 에 `hydration`/`건성` 원문 노출(읽을 수는 있음) |
| 백필 → 코드 ❌ | 구 프론트의 고민 칩·오늘의 픽이 전부 빈 목록 |
| 롤링 배포 ❌ | 구 레플리카가 없는 컬럼을 SELECT → 500 |

## 순서

```bash
# ── 0) 사전 확인: 4개 레포가 전부 빌드되는지 (DB 마이그레이션 후 타입 에러는 최악)
cd klow_server && npm run build
cd ../klow_web   && npx tsc --noEmit && npx next build
cd ../klow_admin && npx tsc --noEmit && npx next build
cd ../klow_brand && npx tsc --noEmit && npx next build

# ── 1) 백필 dry-run (읽기 전용) — 다운타임 전에 매핑 집계 + 미매핑 목록을 눈으로 확인
cd ../klow_server     # ⚠️ DATABASE_URL 이 prod 를 가리키는지 먼저 확인
npm run backfill:product-tags-english
#   확인 사항:
#   - 값별 변환 집계가 `SELECT unnest(concerns), count(*) FROM "Product" GROUP BY 1` 과 일치
#   - "⚠ 미매핑" 목록 (어드민이 자유 입력해둔 한글 등) — 지워지지 않고 그대로 남는다

# ── 2) 유지보수 모드 / 레플리카 0
#    (DROP COLUMN 과 구 코드는 공존 불가)

# ── 3) Neon 브랜치/스냅샷 확보 → 마이그레이션
#    ⚠️ 코드 롤백만으로는 복구 불가(컬럼이 사라진다). 스냅샷이 유일한 롤백 경로다.
npx prisma migrate deploy
#   내용: 컬럼 8개 DROP + ProductTranslation.concerns/recommendedFor (Json?, nullable) ADD

# ── 4) 코드 배포 — klow_server 먼저, 그 다음 web/admin/brand
#    서버 먼저인 이유: 신 프론트는 제거된 필드를 아예 보내지 않고, 브라우저에 캐시된 구 프론트는
#    기능만 잃고 500 은 나지 않는다.

# ── 5) 백필 반영 (코드 배포 후!)
npm run backfill:product-tags-english -- --apply
#   `prisma.product.update`(단건)로 쓰므로 @updatedAt 이 올라가고,
#   ProductTranslation.sourceUpdatedAt < updatedAt 이 되어 전 로케일 MT 캐시가 무효화된다.
#   ✓ 멱등하다 — 재실행하면 "0건 반영" 이고 updatedAt 도 안 움직인다(정의역/치역이 서로소).

# ── 6) 유지보수 해제
#    5단계의 updatedAt bump + `t.concerns === null` self-heal 이 (제품×로케일)당 1회
#    재번역을 강제한다. 트래픽이 자연히 채우고, 급하면 인기 제품 PDP 를 ?lang=ja 로 한 번 긁는다.
```

## 배포 후 검증

- `GET /v1/products/<id>?lang=en` → `concerns: ["Hydration", ...]`, `recommendedFor: ["Dry skin", ...]`
- `GET /v1/products/<id>?lang=ja` 2회 → 1회차 느림/2회차 즉시, 둘 다 일본어.
  `SELECT concerns, recommendedFor FROM "ProductTranslation" WHERE locale='ja'` 의
  **원소 개수가 원문과 같은지** 확인 — 가변 길이 재조립의 off-by-one 이 가장 나기 쉬운 지점이다.
- `GET /v1/products?sort=popular&take=10` → 평점 desc, 리뷰수 desc
- 404 여야 하는 것: `/v1/discover`, `/v1/discover/recommendations`, `/v1/shop/today`,
  `/admin/shop/settings`
- klow_brand `/studio`: 주요 고민에 `수분` + Enter → 칩이 **`Hydration`** 으로 치환
- klow_web `/product/<id>`: KEY BENEFITS · GOOD FOR 가 뷰어 국가 언어로 노출
- klow_admin: 크리에이터 생성/수정 저장 성공 (서버 `creator.skinType` required 제거를 빠뜨렸으면
  여기서 400 이 난다)

## 롤백

3단계 이후에는 **코드 롤백만으로 복구되지 않는다** — 3단계 직전에 잡은 Neon 브랜치/스냅샷으로
복원한 뒤 구 코드를 배포한다. 4단계 직후(백필 전)라면 코드만 되돌려도 데이터는 온전하다.
