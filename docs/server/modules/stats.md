# stats — 어드민 대시보드 통계

- **모듈 경로**: `src/modules/stats/`
- **주 클라이언트**: `klow_admin` 메인 대시보드
- **관련 파일**: `admin-stats.controller.ts`

## admin-stats.controller.ts (`@Controller('admin/stats')`)

> `AdminGuard`.

| Method | Path                       | 기능                                                              |
|--------|----------------------------|-------------------------------------------------------------------|
| GET    | `/admin/stats`             | 카운트 묶음 — 상품·브랜드·크리에이터·비디오·리뷰·주문 등 (대시보드 카드용) |
| GET    | `/admin/stats/revenue`     | 수익(KPI) 집계 — 구독 + 무료시딩 (이번 달 + 누적, KRW)           |
