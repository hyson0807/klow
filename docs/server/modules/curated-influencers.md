# curated-influencers — 큐레이티드 인플루언서 (어드민 큐레이션 → 브랜드 노출)

- **모듈 경로**: `src/modules/curated-influencers/`
- **주 클라이언트**: 어드민(`/admin/influencers` 인플루언서 탭) 이 큐레이션, `klow_brand`(`/v1/brand/creators` "크리에이터 찾기") 가 입점 시 매칭용으로 조회.
- **데이터 모델**: `CuratedInfluencer`(인스타 프로필 스냅샷 + `isPublished` 게이트) + `CuratedInfluencerPost`(대표 게시물, FK `onDelete: Cascade`).
- **⚠️ 검색은 이 모듈이 아니다**: 인플루언서 **검색**(Apify + OpenAI 하이브리드)은 별도 백엔드 `klow_search_server`(:4100, 자체 Neon + R2 `search` 버킷)에 있다. 이 모듈은 그 검색 결과를 **큐레이션해 저장(bulk upsert)하고 브랜드에 노출**하는 곳일 뿐이다 — 여기서 인스타/Apify 를 직접 호출하지 않는다. `searchInfluencerId` 가 search_server `Influencer.id` 추적용 링크, `profilePicUrl`/`displayUrl` 도 search R2·인스타 CDN URL 을 **그대로 미러(재업로드 X)**.
- **큐레이션 흐름**: 어드민이 search 탭에서 고른 인플루언서들을 `POST /admin/influencers/bulk` 로 보내면 `username` 기준 업서트(생성·수정 모두 `isPublished: true`) + 해당 인플루언서 게시물 전량 교체(`deleteMany` → `createMany`). 한 건 실패해도 나머지는 진행하는 **부분 성공**(`{ count, failed: username[] }`), 각 건은 `$transaction`. `curatedById`/`curatedAt` 에 마지막 큐레이션 admin·시각 기록.
- **공개 게이트 (`isPublished`)**: 기본 `true`. 브랜드 노출은 `isPublished: true` 만(어드민은 `isPublished` 필터로 둘 다 조회 가능). 토글 전용 라우트는 없고 — 노출은 bulk 재저장(항상 true)·`DELETE` 로 관리.
- **mapper (admin view vs brand view)**: 어드민 라우트는 Prisma 행을 **그대로**(전 필드 + `_count.posts`) 반환한다. 브랜드 라우트는 `curated-influencers.mapper.ts` 로 가공 — `toBrandCreatorCard`(카드: `handle/name/avatarUrl/followers/engagementRate/avgLikes/country/categories/language`, `platform:'instagram'` 고정) / `toBrandCreatorDetail`(카드 + `bio/isVerified/postsCount/avgComments/isKBeautyRelevant/posts[]`). 변환 규칙: `engagementRate` 는 DB 0~1 비율 → **×100(%)**, `name` 은 `fullName ?? username`, null 수치는 `0`·null 문자열은 `''` 로 폴백. `categories` 는 search 영문(`beauty/skincare/...`) → 한글 라벨(`스킨케어/메이크업/헤어/K뷰티/패션/라이프스타일/기타`) 매핑, 매칭 안 되면 드롭(`CATEGORY_KO`). `isPrivate/isForeign/externalUrl/searchInfluencerId` 등 내부 필드는 브랜드 DTO 에서 제외.
- **주요 `CuratedInfluencer` 필드**: `username`(@unique, 업서트 정본 키), `searchInfluencerId`(search_server 추적), `fullName`, `profilePicUrl`, `bio`, `externalUrl`, `isVerified`, `isPrivate`, `followersCount`/`followingCount`/`postsCount`, `avgLikes`/`avgComments`(Float), `engagementRate`(Float, **0~1 저장 — 상한 없음**), `categories`(String[], 영문 원본), `language`(ISO639-1), `country`(ISO3166 alpha-2), `isKBeautyRelevant`, `isForeign`, `isPublished`(default true), `curatedById`/`curatedAt`. `CuratedInfluencerPost`: `shortcode`/`caption`/`likesCount`/`commentsCount`/`displayUrl`/`postUrl`/`takenAt`.
- **관련 파일**: `curated-influencers.service.ts`(`bulkUpsert`/`listForAdmin`/`listSavedUsernames`/`remove`/`listForBrand`/`getForBrand`), `curated-influencers.mapper.ts`(brand DTO 변환), 2 개 컨트롤러(admin · brand), zod 스키마 `src/common/validation/creator.ts`(`CuratedInfluencerBulkInput`(items 1~100, 각 posts 최대 24) / `CuratedInfluencerAdminListQueryInput`).

## admin-curated-influencers.controller.ts (`@Controller('admin/influencers')`)

> 전체 라우트 `AdminGuard`. `bulk` 에 `@CurrentAdmin()` 주입(→ `curatedById`).

| Method | Path                              | 기능                                                                 |
|--------|-----------------------------------|----------------------------------------------------------------------|
| POST   | `/admin/influencers/bulk`         | username 기준 bulk upsert(+게시물 교체), 부분 성공 `{count, failed}`  |
| GET    | `/admin/influencers`              | 큐레이션 목록 — `q`(username/fullName)·`country`·`isPublished` 필터, `sort`(curatedAt/followers/engagementRate desc), `take`/`skip` 페이지, `_count.posts` 포함 → `{ data, total }` |
| GET    | `/admin/influencers/saved-usernames` | 저장된 username 집합(`string[]`) — search 탭에서 "이미 큐레이션됨" 체크 표시용 |
| DELETE | `/admin/influencers/:id`          | 큐레이션 삭제(게시물 cascade) — 없으면 404                            |

## brand-curated-influencers.controller.ts (`@Controller('v1/brand/creators')`)

> 전체 라우트 `BrandGuard`. **`isPublished: true` 만** 노출, mapper 로 브랜드 DTO 변환.

| Method | Path                       | 기능                                                                      |
|--------|----------------------------|---------------------------------------------------------------------------|
| GET    | `/v1/brand/creators`       | published 크리에이터 카드 목록 — `followersCount desc`, 최대 500, `toBrandCreatorCard` |
| GET    | `/v1/brand/creators/:id`   | published 크리에이터 상세(게시물 `takenAt desc` 포함) — 없으면 404, `toBrandCreatorDetail` |
