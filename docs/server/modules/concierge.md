# concierge — 컨시어지 문의

- **모듈 경로**: `src/modules/concierge/`
- **목적**: 공개 페이지에서 "원하는 상품 찾아주기" 같은 문의 폼을 받아 어드민이 처리.
- **데이터 모델**: `ConciergeRequest` (`id`, `imageUrl?`, `product?`, `brand?`, `note?`, `status`, `createdAt`, `updatedAt`) — **작성자 식별 필드가 없다**(유저 연결·이메일·연락처 컬럼 없음). 익명 제보 폼에 가깝다.
- **상태 enum**: `ConciergeStatus` = `pending`(기본) | `replied` | `completed`
- **관련 파일**: `concierge.service.ts`, `admin-concierge.controller.ts`, `public-concierge.controller.ts`, 검증 스키마 `common/validation/concierge.ts`

## admin-concierge.controller.ts (`@Controller('admin/concierge-requests')`)

> 전체 라우트 `AdminGuard`. `@Throttle()` 없음(전역 기본 60회/분/IP).

| Method | Path                                       | 기능                                                |
|--------|--------------------------------------------|-----------------------------------------------------|
| GET    | `/admin/concierge-requests`                | 요청 목록. `?status=` 필터, `createdAt desc`, **최대 200건**(페이지네이션 없음) |
| GET    | `/admin/concierge-requests/:id`            | 요청 상세. 없으면 404 `concierge request not found` |
| PATCH  | `/admin/concierge-requests/:id`            | **상태 전이 전용** (`{ status }` 하나뿐 — 메모/답변 필드 없음) |
| DELETE | `/admin/concierge-requests/:id`            | 요청 삭제. `{ ok: true }` 반환                      |

- `PATCH` body — `ConciergeRequestPatch`: `{ status: 'pending' | 'replied' | 'completed' }`. `status` 는 **필수**이고 그 외 필드는 받지 않는다.
- `PATCH` / `DELETE` 는 `orNotFound` 로 감싸여 대상이 없으면 404 (`concierge request`).
- ⚠️ 목록의 `?status=` 는 zod 를 안 거치고 `ConciergeStatus` 로 캐스팅만 된다 — enum 밖 문자열이 오면 Prisma 단에서 터진다(어드민 UI 는 정해진 값만 보냄).

## public-concierge.controller.ts (`@Controller('v1/concierge-requests')`)

| Method | Path                              | Guard      | 기능                                                |
|--------|-----------------------------------|------------|-----------------------------------------------------|
| POST   | `/v1/concierge-requests`          | public     | 공개 문의 폼 제출 (찾는 제품 이미지/이름)           |

- Body — `ConciergeRequestInput`: `{ imageUrl?, product?, brand?, note? }` (전부 `string` optional).
- `.refine` 로 **`imageUrl` 또는 공백 아닌 `product` 중 최소 하나** 필요 — 아니면 400 `imageUrl 또는 product 중 하나 이상 필요합니다`.
- 이미지는 이 라우트가 받지 않는다 — 클라가 업로드 후 얻은 URL 문자열을 `imageUrl` 로 넣는다.
- 가드도 `@Throttle()` 도 없다(전역 기본 60회/분/IP만 적용) — 공개 쓰기 경로임에 유의.
- 생성된 `ConciergeRequest` 행 전체를 그대로 반환한다.
