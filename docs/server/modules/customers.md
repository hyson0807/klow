# customers — 고객(유저) 어드민 관리

- **모듈 경로**: `src/modules/customers/`
- **데이터 모델**: `User` (auth 모듈 소유)
- **주 클라이언트**: `klow_admin`
- **관련 파일**: `customers.service.ts`, `admin-customers.controller.ts`

## admin-customers.controller.ts (`@Controller('admin/customers')`)

> 전체 라우트 `AdminGuard`.

| Method | Path                       | 기능                                                                  |
|--------|----------------------------|-----------------------------------------------------------------------|
| GET    | `/admin/customers`         | 고객 목록 (아래 쿼리 필터 + 페이지네이션) → `{ data, total }`         |
| GET    | `/admin/customers/:id`     | 고객 상세 (주문·카트·리뷰·세션 include). 없으면 404 `customer not found` |
| PATCH  | `/admin/customers/:id`     | 고객 프로필 수정 (CS 응대용) → 상세와 동일 형태 반환                  |

### GET `/admin/customers` 쿼리 (`CustomerListQueryInput`)

`q`(이메일·닉네임 부분일치, insensitive) · `country` · `provider`(`email` | `google` — `googleId` 유무로 판정) ·
`since` / `until`(가입일 범위, `createdAt`) · `hasOrders`(boolean) · `take`(1~200, 기본 50) · `skip`(기본 0).
정렬은 `createdAt desc` 고정.

- 목록 항목: `{ id, email, nickname, country, provider, emailVerifiedAt, createdAt, lastSeenAt(최근 세션 생성시각),
  orderCount, reviewCount, totalSpent }`. **`totalSpent` 는 USD 센트 합계**(취소 주문 제외).
- 상세는 위에 더해 `updatedAt` + `orders`(최근 50) · `cart`(전체, `unitPriceUsd = Product.basePriceUsd`) ·
  `reviews`(최근 30) · `sessions`(최근 20, `userAgent`/`ip`/`expiresAt` 포함).

### PATCH `/admin/customers/:id` 바디 (`CustomerProfilePatchInput`)

**`nickname`(1~50) 과 `country`(≤64, `null` 허용) 두 필드뿐**이다 — 서비스가 명시적 화이트리스트로 복사하므로
`email` / `passwordHash` / `googleId` 는 어떤 경우에도 수정되지 않는다. 없는 id 면 404 `customer not found`.
