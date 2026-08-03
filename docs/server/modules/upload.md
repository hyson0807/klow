# upload — R2 presigned URL 발급

- **모듈 경로**: `src/modules/upload/`
- **스토리지**: Cloudflare R2 버킷 — 버킷명·공개 base 는 env(`R2_BUCKET` / `R2_PUBLIC_BASE`), 그 외 `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`. 운영값은 버킷 `klow`, 공개 base `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk 처리**: `r2.service.ts` 의 `S3Client` 가 `requestChecksumCalculation: 'WHEN_REQUIRED'` + `responseChecksumValidation: 'WHEN_REQUIRED'` 설정 (AWS SDK v3.729+ CRC32 checksum 회피)
- **관련 파일**: `r2.service.ts`, `admin-upload.controller.ts`, `brand-upload.controller.ts`, 검증 스키마 `common/validation/upload.ts`

## admin-upload.controller.ts (`@Controller('admin/upload')`)

| Method | Path                    | Guard         | 기능                                                                |
|--------|-------------------------|---------------|---------------------------------------------------------------------|
| POST   | `/admin/upload`         | `AdminGuard`  | presigned PUT URL 발급. scope 없음 → 키가 `images/...` / `videos/...` 루트에 생성 |

## brand-upload.controller.ts (`@Controller('v1/brand/upload')`)

| Method | Path                       | Guard          | 기능                                                                |
|--------|----------------------------|----------------|---------------------------------------------------------------------|
| POST   | `/v1/brand/upload`         | `BrandGuard`   | presigned PUT URL 발급. scope = `user.brandId ?? user.id` 를 서버가 강제 → 키가 `brands/<scope>/...` 로 격리 |

> 브랜드 scope 는 **세션에서 뽑으므로 클라가 지정할 수 없다.** 아직 브랜드가 붙기 전(신청 전) 단계면
> `brandUserId` 로 prefix 되고, 승인 후에는 `brandId` 로 묶인다. 어느 쪽이든 본인 외엔 그 prefix 를 쓸 수 없다.

## 요청 / 응답 (두 컨트롤러 공통)

두 라우트 모두 `ZodValidationPipe(UploadInput)` 를 거치고, `@Throttle()` 은 붙어있지 않다(전역 기본 60회/분/IP).

**Body** — `common/validation/upload.ts` `UploadInput`

| 필드          | 타입                     | 규칙                                                                 |
|---------------|--------------------------|----------------------------------------------------------------------|
| `filename`    | `string`                 | 1~255자                                                              |
| `contentType` | `string`                 | 1자 이상 + 아래 `kind` 별 화이트리스트에 있어야 함                   |
| `kind`        | `'image' \| 'video'`     | 저장 폴더(`images` / `videos`) 와 허용 MIME 을 동시에 가른다          |

- 허용 MIME — image: `image/webp`, `image/jpeg`, `image/png`, `image/gif` / video: `video/mp4`, `video/quicktime`, `video/webm`.
- **SVG 는 의도적으로 제외** — R2 공개 URL 로 서빙되면 스크립트 삽입(XSS) 위험이 있어서다.
- `kind` 와 `contentType` 이 안 맞으면 `.refine` 이 `contentType` path 로 `unsupported content-type for kind` 400.

**Response** — `{ uploadUrl, publicUrl, key }`

- `uploadUrl`: `PutObjectCommand` presign, **TTL 600초**. `ContentType` 이 서명에 포함되므로 PUT 시 동일 헤더로 보내야 한다.
- `key`: `<base>/<uuid>-<sanitized filename>` (`base` = `images`/`videos`, 브랜드는 `brands/<scope>/images|videos`). 파일명은 `[^a-zA-Z0-9._-]` 를 `_` 로 치환하고 앞에 `randomUUID()` 를 붙여 충돌·경로조작을 막는다.
- `publicUrl`: `${R2_PUBLIC_BASE}/${key}`.

## R2Service 서버측 헬퍼 (라우트 없음)

`UploadModule` 이 `R2Service` 를 `exports` 하므로 다른 모듈이 프리사인 없이 직접 R2 를 다룰 수 있다.

| 메서드                                                               | 용도                                                                                     |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| `uploadBytes({ scope, folder, body, contentType, ext })`             | 서버가 바이트를 직접 PUT. 키는 `brands/<scope>/<folder>/<uuid>.<ext>`. 시딩 계약서 서명 PNG 처럼 서버가 디코드/검증한 작은 아티팩트용. `{ publicUrl, key }` 반환 |
| `getBytes(key)`                                                      | 오브젝트를 `Buffer` 로 되읽는다. 동결된 청구서 xlsx 를 `BrandGuard` 뒤에서 재스트리밍(원 R2 public URL 비노출)하기 위함 |

## 참고

- 클라이언트에서 받은 presigned URL 로 직접 R2 에 PUT 후, 공개 URL 을 DB 에 저장하는 방식.
- 만약 presigned upload 가 503/400 으로 깨지면 가장 먼저 `requestChecksumCalculation` 설정을 확인할 것 (CLAUDE.md 의 R2 quirk 노트).
