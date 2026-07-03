# upload — R2 presigned URL 발급

- **모듈 경로**: `src/modules/upload/`
- **스토리지**: Cloudflare R2 버킷 `klow`
- **공개 base URL**: `https://pub-cac46f90807b402a9079c58c5e8287bb.r2.dev`
- **R2 quirk 처리**: `r2.service.ts` 에서 `requestChecksumCalculation: 'WHEN_REQUIRED'` 설정 (AWS SDK v3.729+ CRC32 checksum 회피)
- **관련 파일**: `r2.service.ts`, `upload.controller.ts`, `brand-upload.controller.ts`

## upload.controller.ts (`@Controller('admin/upload')`)

| Method | Path                    | Guard         | 기능                                                                |
|--------|-------------------------|---------------|---------------------------------------------------------------------|
| POST   | `/admin/upload`         | `AdminGuard`  | presigned PUT URL 발급 (어드민 scope; 자유로운 prefix)              |

## brand-upload.controller.ts (`@Controller('v1/brand/upload')`)

| Method | Path                       | Guard          | 기능                                                                |
|--------|----------------------------|----------------|---------------------------------------------------------------------|
| POST   | `/v1/brand/upload`         | `BrandGuard`   | presigned PUT URL 발급 (`brandId/...` 또는 `userId/...` prefix 강제) |

## 참고

- 클라이언트에서 받은 presigned URL 로 직접 R2 에 PUT 후, 공개 URL 을 DB 에 저장하는 방식.
- 만약 presigned upload 가 503/400 으로 깨지면 가장 먼저 `requestChecksumCalculation` 설정을 확인할 것 (CLAUDE.md 의 R2 quirk 노트).
