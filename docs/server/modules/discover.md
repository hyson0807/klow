# discover — 추천 피드

- **모듈 경로**: `src/modules/discover/`
- **목적**: 유저 입력 (피부타입 / concerns / categoryKey) 기반 상품 추천 노출.
- **공개 필터**: `PUBLIC_PRODUCT_WHERE` 적용.
- **관련 파일**: `discover.service.ts`, `public-discover.controller.ts`

## public-discover.controller.ts (`@Controller('v1/discover')`)

> 전체 라우트 public.

| Method | Path                              | 기능                                                                            |
|--------|-----------------------------------|---------------------------------------------------------------------------------|
| GET    | `/v1/discover`                    | `skinType`, `concerns[]`, `categoryKey` 기반 상품 그룹 반환                     |
| GET    | `/v1/discover/recommendations`    | 추천 상품 단일 리스트 (`?take=` 최대 200)                                       |
