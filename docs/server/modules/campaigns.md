# campaigns — 인플루언서 캠페인 단축링크·유입 추적

- **모듈 경로**: `src/modules/campaigns/`
- **주 클라이언트**: `klow_brand`(자기 캠페인 CRUD·인플루언서 링크 발급·유입 차트, `/v1/brand/campaigns/*`) + `klow_admin`(전 브랜드 캠페인 관찰·강제 On/Off·삭제, `/admin/campaigns/*`) + 공개 트래픽(인플루언서가 SNS 에 게시한 `/r/{code}` 단축링크 클릭).
- **데이터 모델**: `Campaign`(brand 소유, `name`/`description`/`startDate`/`endDate`(표시용 자유 텍스트 문자열, 무손실 저장)/`status`), `CampaignLink`(인플루언서별 발급 링크 — `influencerName`/`platform`/`handle`/`memo`/`code`(@unique 6자 영숫자)/`clickCount`(누적)/`enabled`, `brandId` 는 스코핑/집계 편의용 denormalize=`campaign.brandId`), `CampaignLinkDailyStat`(링크×날(KST) 1행, `date`(YYYY-MM-DD)/`clicks` — "기간별 유입 추이" 차트용). 삭제는 `onDelete: Cascade` 로 링크·일별통계 함께 제거.
- **상태 enum**: `CampaignStatus` = `active` | `ended`. `CampaignPlatform` = `IG` | `YT` | `TT`.
- **캠페인이란**: 브랜드가 캠페인을 만들고 인플루언서마다 단축링크(`/r/{code}`)를 발급하면, 인플루언서가 자기 SNS 에 그 링크를 게시한다. 유저가 클릭하면 서버가 클릭 1 을 기록하고 브랜드관(klow_web `/{brand.slug}`)으로 302 리다이렉트한다. 브랜드는 링크별 누적 클릭·일자별 유입 시계열을 대시보드에서 본다.
- **단축링크 코드**: 혼동 문자(0/O, 1/I) 제외한 32자 알파벳에서 6자 랜덤(32^6 ≈ 10억). 발급 시 `@unique` 충돌(P2002)이면 최대 5회 재시도.
- **클릭 집계 규칙 (`resolveAndCount`)**: code 없음(만료/오타) → 증가 없이 웹 홈 폴백. 링크 `enabled=false` 또는 캠페인 `status!=='active'` → 증가 없이 웹 홈 폴백(미집계). 정상이면 `clickCount +1`(단일 update) + 오늘(KST) 일별 버킷 `clicks +1`(fire-and-forget upsert, 동시 첫클릭 P2002 은 update 폴백 후 실패 무시) + 브랜드 slug 있으면 `/{slug}`, 없으면 웹 홈으로 302. 컨트롤러는 항상 유효 URL 을 받으므로 그대로 302.
- **링크 베이스 env**: 공유 링크 베이스는 `CAMPAIGN_LINK_BASE`(기본 `http://localhost:4000`, 응답 `url` 에 `/r/{code}` 로 노출 — 운영 klow.kr/r/* 는 배포 rewrite), 리다이렉트 대상 웹 베이스는 시딩과 공용 `FRONTEND_URL`(기본 `http://localhost:3001`).
- **스코핑**: 브랜드 라우트는 전부 `BrandGuard` + `requireBrandId` 로 본인 브랜드에 스코핑(캠페인·링크 mutation 은 `where { id, brandId }` / `updateMany`·`deleteMany` 로 소유 검증). 어드민 라우트는 `AdminGuard` 로 brandId 스코핑 없이 전 브랜드 개입, mutation 은 글로벌 `AdminAuditInterceptor` 가 자동 기록.
- **관련 파일**: `campaigns.service.ts`(브랜드 CRUD·링크 발급·공개 리다이렉트·일별 통계), 컨트롤러 3개(brand·admin·public-redirect), `campaigns.module.ts`(`BrandAuthModule` import — BrandGuard 의존).
- **교차링크**: [brands](./brands.md)(brand.slug 리다이렉트 대상), [seeding](./seeding.md)(FRONTEND_URL 공용).

## brand-campaigns.controller.ts (`@Controller('v1/brand/campaigns')`)

> 전체 라우트 `BrandGuard` + `requireBrandId`(본인 브랜드 스코핑). body/query 는 `ZodValidationPipe` 검증.

| Method | Path                                            | 기능                                                                    |
|--------|-------------------------------------------------|-------------------------------------------------------------------------|
| GET    | `/v1/brand/campaigns`                           | 내 캠페인 목록 + 상단 KPI(activeCampaigns/totalLinks/totalClicks)       |
| POST   | `/v1/brand/campaigns`                           | 캠페인 생성(`name`/`description?`/`startDate?`/`endDate?`)              |
| GET    | `/v1/brand/campaigns/:id`                       | 캠페인 상세(+ 발급 링크 전체, url·clickCount 포함)                      |
| PATCH  | `/v1/brand/campaigns/:id`                       | 기간 수정 + 중지/재개(`startDate?`/`endDate?`/`status?`, 최소 1필드)    |
| DELETE | `/v1/brand/campaigns/:id`                       | 캠페인 삭제(링크·통계 cascade)                                          |
| POST   | `/v1/brand/campaigns/:id/links`                 | 인플루언서 링크 발급(`influencerName`/`platform`/`handle`/`memo?`, code 랜덤) |
| PATCH  | `/v1/brand/campaigns/:id/links/:linkId`         | 인플루언서 링크 On/Off 토글(`enabled`)                                  |
| DELETE | `/v1/brand/campaigns/:id/links/:linkId`         | 인플루언서 링크 1건 삭제                                                |
| GET    | `/v1/brand/campaigns/:id/links/:linkId/stats`   | 링크 일자별 유입 시계열(`days=1~90`, 기본 30, dense 제로필)             |

## admin-campaigns.controller.ts (`@Controller('admin/campaigns')`)

> 전체 라우트 `AdminGuard`(brandId 스코핑 없음 — 전 브랜드 관찰·강제개입). mutation 은 `AdminAuditInterceptor` 자동 기록.

| Method | Path                                       | 기능                                                                |
|--------|--------------------------------------------|---------------------------------------------------------------------|
| GET    | `/admin/campaigns`                         | 전체 캠페인 목록(`q`=캠페인명/브랜드명 검색, `status`, `take`/`skip`) |
| GET    | `/admin/campaigns/:id`                     | 캠페인 상세(브랜드 정보 + 링크 전체 + totalClicks)                   |
| PATCH  | `/admin/campaigns/:id`                     | 캠페인 On/Off 강제 토글(`status`=active\|ended, 필수)               |
| DELETE | `/admin/campaigns/:id`                     | 캠페인 삭제(cascade)                                                 |
| PATCH  | `/admin/campaigns/:id/links/:linkId`       | 인플루언서 링크 On/Off 강제 토글(`enabled`)                         |
| DELETE | `/admin/campaigns/:id/links/:linkId`       | 인플루언서 링크 1건 삭제                                             |

## public-campaigns.controller.ts (`@Controller('r')`)

> 가드 없음 — 공개 트래픽. 인플루언서가 SNS 에 게시한 단축링크.

| Method | Path        | 기능                                                                        |
|--------|-------------|-----------------------------------------------------------------------------|
| GET    | `/r/:code`  | 클릭 1 기록 후 브랜드관(klow_web `/{slug}`)으로 302. 무효/Off 는 미집계·홈 폴백 |
