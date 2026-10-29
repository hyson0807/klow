# dampenerlab — 댐프너랩 커스텀 댐프너 단독 판매 사이트 (dampenerlab.klow.kr)

- **모듈 경로**: `src/modules/dampenerlab/`
- **목적**: 아이템샵 대표님의 **댐프너랩 커스텀 댐프너**(원본 itemshop.com/products/129696696)를 해외 고객에게 판다. 프론트는 별도 레포 `klow_dampenerlab`(Next.js, 영어) — 원본 상품 페이지 + Konva 편집기 클론. 결제는 KLOW Eximbay(USD), 발송은 KLOW EFS 송장(댐프너랩 = KLOW `Brand`).
- **설계 정본**: [`docs/plan/dampenerlab/`](../../plan/dampenerlab/README.md)
- **관련 파일**: `dampenerlab.service.ts` · `public-dampenerlab.controller.ts` · 검증 `common/validation/dampenerlab.ts` · 결제 return 분기 `payment/shop-sites.ts` + `payment.service.ts#resultRedirectUrl` · 주문 생성 `orders.service.ts#create`(선택 인자 `CreateOrderOptions`)
- **마이그레이션**: `20261029050441_add_shop_site_and_item_customization` — `Order.shopSite VARCHAR(30)` + `OrderItem.customization JSONB`. 둘 다 nullable ADD → **롤링 안전 · 백필 없음**.
- **env**: `DAMPENERLAB_BRAND_ID`(없으면 이 모듈 전 엔드포인트 503) · `DAMPENERLAB_FRONTEND_URL`(결제 return 303 목적지 — 없으면 klow.kr 로 폴백) · `CORS_ORIGIN` 에 사이트 origin 추가(안 하면 POST 가 403 origin not allowed).

⚠️⚠️ **주문은 소비자 주문 그대로다**(`kind = consumer`, `channel = web`). 가격(`priceLine`)·배송비(요율표 500g / 브랜드 지정)·브랜드당 5개 한도·EFS 송장·정산·주문 확인 메일·브랜드 알림톡이 klow_web 주문과 똑같이 돈다. 다른 점은 `shopSite = 'dampenerlab'` 과 라인별 `customization` 뿐이다.

⚠️ **결제 return 목적지는 서버 env 고정 맵**(`shop-sites.ts` `SHOP_SITE_ENV`)으로만 정한다 — 요청값 URL 로 303 하면 오픈 리다이렉트다. 사이트를 추가하면 그 표 한 줄 + env + `CORS_ORIGIN`.

## 공개 API (`@Controller('v1/dampenerlab')`)

| 메서드 · 경로 | 동작 |
|---|---|
| `GET products` | `{brandId, products:[{id, name}]}` — 이 브랜드 제품 id(가격·이미지는 기존 `GET /v1/products/:id` 가 정본) |
| `POST uploads/presign` `{contentType: png·jpeg·webp, size ≤ 15MB}` | 디자인 이미지(손님 사진·면별 인쇄/미리보기 PNG) presign. 키는 서버가 정한다 `dampenerlab/designs/<uuid>.<ext>`, **크기를 서명에 넣어** 선언과 다른 PUT 은 R2 가 거절. → `{uploadUrl, key, publicUrl}`. 30회/분 |
| `POST orders` `{order, designs}` | `order` = klow_web `POST /v1/orders` 와 같은 본문(배송지·국가 규칙·동의 3종). `designs[{productId, customization}]` 1~5개, 제품당 1개. 검사: 주문 제품이 전부 이 브랜드 · 디자인 제품이 주문에 있음 · 모든 디자인 키가 R2 에 실제로 있음(`headObject`). 게스트면 `klow_order` 쿠키 → 이후 `POST /v1/payment/prepare` 그대로. → `{id}`. 10회/분 |

`customization` (`DampenerCustomization`, `kind` 판별 유니온):

- `dampener` — `shape: square|round` · `color: white|yellow|pink|orange|red|skyblue|green|darkgreen|navy|black`(원본 목업 이미지 파일명 slug) · `sides: same|different` · `front` · `back`(different 일 때만, 필수)
- `case` — `color: silver` · `front`(뚜껑 한 면)
- 면(`front`/`back`) = `{printKey, previewKey, design?}` — 키는 `dampenerlab/designs/` 접두만 통과, `design`(편집기 노드 트리)은 해석하지 않고 200,000자 상한만.

케이스처럼 디자인 없이 사는 제품은 `order.items` 에만 넣는다(디자인 줄은 최소 1개).

## 결제 흐름

klow_dampenerlab → `POST /v1/dampenerlab/orders` → `POST /v1/payment/prepare`(Eximbay 상품 링크 = 사이트 홈) → Eximbay → `/payment/return`(서버 확정) → **303 `${DAMPENERLAB_FRONTEND_URL}/checkout/redirect?…&klow_verified=1`** — klow_web `/checkout/redirect` 와 같은 querystring 계약.
