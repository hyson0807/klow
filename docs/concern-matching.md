# 고민 키워드 매칭 & 추천 규칙

온보딩에서 사용자가 선택한 피부 고민 키워드가 샵탭 "추천 제품"과 "스킨트윈 크리에이터" 섹션에 어떻게 반영되는지 정리한 문서.

## 전체 흐름

```
온보딩 3단계 (칩 다중 선택, 최대 3개)
  ↓ Zustand persist: concernKeywords: string[]
useDiscoverQuery
  ↓ GET /v1/discover?skinType=건성&concerns=hydration,acne,pore
klow_server / DiscoverService.getRecommendations
  ↓ concernTags 결정 (아래 규칙 참고)
Prisma: Product.concerns / Creator.concerns hasSome concernTags  (OR 필터)
  ↓
scoreProduct / scoreCreator: overlap 개수 × 가중치로 정렬
  ↓
recommended[], skinTwinCreators[]
```

## 매칭 규칙

### 1. 필터 (후보 조회)
- Prisma `hasSome` = **OR**. 사용자의 `concernTags` 중 **하나라도** 겹치는 제품/크리에이터를 후보에 포함.
- `concernTags`가 비어 있으면 `skinType`만으로 매칭. 둘 다 없으면 fallback(인기 제품).

### 2. 랭킹 (정렬)
- **겹친 태그가 많을수록 상위**.
- 가중치:
  - 제품: `overlap × 14` (`scoreProduct`)
  - 크리에이터: `overlap × 8` (`scoreCreator`)
  - 피부 타입 매칭 제품 `+32`, 크리에이터 `+50`
  - 제품은 리뷰수 소셜 프루프 `+min(8, reviewCount/30)`
- 최종 점수 desc로 정렬 후 상위 N개를 반환.

### 3. Reason chip
- 겹친 태그 중 **상위 2개**를 `#수분 #모공` 형태로 join해서 표시.

## CONCERN_EXPANSION (자동 추가 규칙)

`klow_server/src/modules/discover/discover.service.ts`에 정의된 의미적 확장 테이블:

```ts
const CONCERN_EXPANSION: Record<string, string[]> = {
  hydration: ['hydration', 'soothing'],
  soothing: ['soothing', 'acne'],
  brightening: ['brightening', 'hydration'],
  'anti-aging': ['wrinkle', 'elasticity'],
  pore: ['pore', 'dead_skin', 'acne'],
  whitening: ['whitening', 'brightening'],
  antiaging: ['antiaging', 'wrinkle', 'elasticity'],
  glass_skin: ['glass_skin', 'brightening', 'hydration'],
};
```

### 언제 동작하는가

| 선택한 고민 개수 | 동작 |
|----------------|------|
| **0개** | fallback (인기 제품). concernTags = `[]` |
| **1개** | 확장 O. 테이블에 있으면 확장된 배열, 없으면 선택값 1개 그대로 |
| **2개 이상** | 확장 X. 사용자가 고른 키워드만 그대로 사용 |

### 동작 예시

- `['hydration']` 단일 선택 → `concernTags = ['hydration', 'soothing']`
  → 진정 태그만 있는 제품도 후보에 포함
- `['elasticity']` 단일 선택 → 테이블에 없음 → `concernTags = ['elasticity']`
- `['hydration', 'acne', 'pore']` 다중 선택 → `concernTags = ['hydration', 'acne', 'pore']`
  → 선택한 3개 태그에만 매칭. 임의 확장 없음.

### 왜 다중 선택에서는 껐는가

다중 선택에서도 확장을 하면 예를 들어 `[hydration, pore]` 2개 선택 시:
- `hydration → [hydration, soothing]`
- `pore → [pore, dead_skin, acne]`
- 합치면 `[hydration, soothing, pore, dead_skin, acne]` 5개

"내가 고른 고민"과 "서버가 자동으로 덧붙인 고민"이 섞여 사용자 의도와 다른 제품이 상위에 노출될 수 있다. 사용자가 이미 여러 개를 명시적으로 골랐다는 건 관심사를 충분히 표현했다는 의미이므로, 선택값을 그대로 존중한다.

단일 선택은 pool이 너무 좁아질 수 있어 의미적으로 가까운 태그 1~2개만 보조로 끌어온다.

## 관련 코드

| 위치 | 역할 |
|------|------|
| `klow_web/src/components/onboarding/OnboardingConcernStep.tsx` | 11개 고민 칩, 최대 3개 선택 UI |
| `klow_web/src/store/useAppStore.ts` | `concernKeywords: string[]` persist |
| `klow_web/src/hooks/useDiscoverQuery.ts` | 배열을 API로 전달 |
| `klow_web/src/lib/api.ts` | `?concerns=csv` 쿼리 파라미터 |
| `klow_web/src/lib/discoverLabels.ts` | `formatConcernList()` 제목 라벨 포맷 |
| `klow_server/src/modules/discover/public-discover.controller.ts` | `concerns` CSV + 레거시 `concern` 수용 |
| `klow_server/src/modules/discover/discover.service.ts` | `CONCERN_EXPANSION`, `scoreProduct`, `scoreCreator` |

## 고민 키워드 목록 (11종)

`klow_web/src/lib/concerns.ts` — `FEED_CONCERNS` 상수.

| ID | 한글 라벨 |
|----|----------|
| `hydration` | 수분 |
| `soothing` | 진정 |
| `elasticity` | 탄력 |
| `wrinkle` | 주름 |
| `acne` | 트러블 |
| `pore` | 모공 |
| `brightening` | 브라이트닝 |
| `dead_skin` | 각질 |
| `whitening` | 미백 |
| `antiaging` | 안티에이징 |
| `glass_skin` | 광채 (Glass-Skin) |
