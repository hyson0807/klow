# klow_server: Railway → AWS ECS Fargate 이전

> 상태: [진행표 §7](../../PROGRESS.md#7-진행-기록) 참조.

AWS Activate 크레딧 신청에 맞춰 정리한 이전 계획이다. 1단계는 어느 플랫폼에서든 이득인 준비
작업이고, 2단계 이후는 크레딧 승인이 있어야 진행할 수 있다.

- 범위는 `klow_server`다. `klow_search_server`는 cron과 Playwright가 없어 같은 틀로 뒤따른다.
- 프론트 3개(Vercel)는 옮기지 않는다.

## 왜 단순한 "배포처 변경"이 아닌가

서버 자체는 옮기기 쉽다. `/health`가 있고, 로컬 디스크를 쓰지 않으며(`src/`에 `readFileSync`·`__dirname` 0건), 웹소켓이 없다. 어려운 건 코드가 **Railway 환경을 전제로 맞춰진 곳들**이다.

| 함정 | 잘못 옮기면 | 대응 |
|---|---|---|
| `TRUST_PROXY_HOPS=2`가 Railway 엣지에 맞춰 실측한 값 | Eximbay 웹훅 전부 403, rate limit이 서비스 전체 합산 (2026-09-04 사고 재현) | AWS에서 **재실측**. ALB 단독이면 1, CloudFront→ALB면 2일 가능성이 높다. 추측으로 넣지 말 것 |
| `@Cron` 10개가 인스턴스마다 돌고 분산 락 없음 | 전환 기간에 정기결제·결제 재확인·CRM 발송이 **양쪽에서 실행** | 1단계에서 `CRON_ENABLED` 추가 |
| DB가 Neon 싱가포르 | 서울 리전에 두면 쿼리마다 왕복 수십 ms 추가 (CRM처럼 왕복이 여러 번인 화면이 체감될 만큼 느려짐) | **ap-southeast-1**. Neon 싱가포르도 AWS 위라 같은 리전이면 지연이 거의 없다 |
| 레포에 빌드 설정 없음 | ECS에 올릴 이미지가 없음 | 1단계에서 Dockerfile 추가 |
| 고정 발신 IP | 벤더 콘솔에 IP를 등록해 둔 곳이 있으면 호출 거절 | 확인 필요: NicePay(`docs/brand-subscription.md`가 "고정 egress IP"를 운영 요건으로 적음)·Solapi·EFS. 필요하면 NAT Gateway + Elastic IP |
| 환경변수 약 74개 + `main.ts` 부팅 가드 | 하나만 빠져도 부팅 거부 | Secrets Manager/SSM으로 옮길 때 `.env.example` 대조 |
| ALB 기본 idle timeout 60초 | 소개서 AI 분석·요율표 AI 추출이 504 | idle timeout 상향 |
| 마이그레이션 적용 방식 | 레포 어디에도 자동 적용 설정이 없음 (런북은 Neon 스냅샷 → 수동 `migrate deploy`) | Railway 대시보드의 Pre-deploy Command 확인 후 ECS 일회성 태스크로 옮김 |

## 단계

```
0. 사전 확인 (코드 변경 없음)
   ├─ NicePay·Solapi·EFS 콘솔에 IP 등록 여부
   └─ Railway 배포 설정(Custom Start / Pre-deploy Command, Healthcheck, NODE_ENV)

1. 코드 준비 (플랫폼 무관)
   ├─ CRON_ENABLED 전체 스위치
   ├─ enableShutdownHooks + 종료 훅 순서
   └─ Dockerfile · docker-entrypoint.sh · .dockerignore

2. AWS 기반 구성 (ap-southeast-1)
   └─ VPC · ECR · Secrets Manager · ACM · ALB · CloudWatch Logs (Terraform/CDK로 코드화 권장)

3. 스테이징 이전
   ├─ ECS 스테이징 서비스 + 스테이징 DB 브랜치
   ├─ TRUST_PROXY_HOPS 실측  ← 결제 웹훅이 달려 있음
   ├─ Eximbay 샌드박스 결제·웹훅 1건
   └─ cron·업로드·메일·스크래퍼 확인

4. CI/CD
   └─ GitHub Actions → ECR push → 마이그레이션 태스크 → ECS 서비스 갱신

5. 운영 전환 (한 번에, 짧게)
   ├─ Cloudflare에서 api.klow.kr TTL 미리 낮추기
   ├─ ECS 운영을 CRON_ENABLED=false 로 기동
   ├─ api.klow.kr → ALB
   ├─ 운영 TRUST_PROXY_HOPS 실측 → 실결제 1건
   └─ Railway CRON_ENABLED=false → ECS CRON_ENABLED 해제   ← 순서 엄수

6. 1주 관찰 후 Railway 종료 (문제 시 DNS만 되돌리면 복구)
```

**`api.klow.kr`을 그대로 쓰는 것이 핵심이다.** Eximbay `return_url`·`status_url`과 프론트 3개의 API 주소가 모두 그 도메인을 가리킨다. DNS만 바꾸면 프론트와 외부 연동을 건드릴 필요가 없다.

## 1단계에서 한 일과 결정 근거

### `CRON_ENABLED` 전체 스위치

- **위치:** `klow_server/src/app.module.ts`의 `ScheduleModule.forRootAsync`
- **동작:** 값이 정확히 `'false'`일 때만 `@Cron`이 **하나도 등록되지 않는다.** 미설정이나 다른 값이면 켜짐이다(기존 cron별 플래그와 같은 규칙).
- **왜 등록 단계에서 끄나:** 핸들러마다 검사하면 새 cron을 추가할 때 검사를 빠뜨려 몰래 돈다. `cronJobs:false`면 `ScheduleExplorer`가 `addCron` 전에 return한다(`@nestjs/schedule` 6.1.3 소스 확인).
- **왜 `forRoot({ cronJobs: process.env… })`가 아닌가:** 데코레이터 평가 시점이라 `.env` 로드 순서에 기댄다. `forRootAsync` 팩토리는 DI 해석 시점에 `ConfigService`로 읽는다.
- **꺼져 있으면 경고 로그 1줄**이 남는다. ⚠️ 운영에서 켜는 것을 잊으면 결제 재확인·송장 재시도·정기결제가 조용히 멈춘다. **평상시에는 어느 환경에도 설정하지 않는다.**
- 기존 cron별 플래그 4개(`TRACKING_`/`SHIPMENT_RETRY_`/`CRM_EMAIL_`/`BRAND_DOMAIN_CRON_ENABLED`)는 그대로 둔다. 전체 스위치가 꺼져 있으면 그것들은 무의미하다.
- **회귀 잠금:** `test/app.e2e-spec.ts`. 미설정이면 10개 등록, `'false'`면 0개.

### 안전 종료

- `main.ts`에 `app.enableShutdownHooks()`를 넣었다. 예전에는 Railway가 재배포할 때 보내는 SIGTERM에 Node가 즉시 죽어 처리 중인 요청이 끊겼다.
- ⚠️ **종료 훅 순서가 함정이다.** `@nestjs/core` 11의 `close()`는 아래 순서로 돈다.
  ```
  onModuleDestroy → beforeApplicationShutdown(스케줄러 정지) → dispose(HTTP 서버 닫기) → onApplicationShutdown
  ```
  `PrismaService`와 `BrandScraperService`가 `onModuleDestroy`에서 정리하고 있어서, 훅만 켜면 **HTTP가 아직 요청을 받는 중에 DB와 브라우저를 먼저 닫는다.** 둘 다 `onApplicationShutdown`으로 옮겼다. (2026-09-15 에 Playwright 를 제거하면서 `BrandScraperService`의 종료 훅은 사라졌다 — 지금 이 훅을 쓰는 건 `PrismaService` 하나다.)
- **알려진 한계:** 스케줄러는 다음 틱을 멈출 뿐 실행 중인 핸들러를 기다리지 않는다. 종료 순간 돌던 cron은 끊길 수 있다(예전보다 나빠지지는 않는다).

### Dockerfile

`klow_server/Dockerfile` · `docker-entrypoint.sh` · `.dockerignore`

- **계보:** `~/hyson_works/hydo/hydo-api/Dockerfile`. Lightsail에서 운영 검증된 NestJS 11 + Prisma 6 + Neon 싱가포르 구성이다.
- ⚠️ **`npm prune` 뒤에 `prisma generate`를 한 번 더 돌린다.** prune이 생성된 client를 지운다. 빼면 부팅 시 `@prisma/client did not initialize`.
- **`node:20.18.0-alpine`:** `.nvmrc`와 같다. `argon2` 0.44는 musl prebuilt가 있다. `openssl`은 Prisma 엔진 탐지용으로 명시 설치한다. `schema.prisma`에 `binaryTargets`는 필요 없다(컨테이너 안에서 generate).
- **`NODE_ENV`를 이미지에 넣지 않는다.** `main.ts`의 production 부팅 가드가 이 값에 걸려 있어, 박으면 그 값을 쓰지 않던 환경이 부팅 거부될 수 있다. 환경변수의 정본은 플랫폼이다.
- **`RUN_MIGRATIONS=true`면 기동 직전 `prisma migrate deploy`.** 기본은 꺼짐이다. 롤링 비안전 마이그레이션이 있어 런북 순서를 대체하면 안 된다. 플랫폼에 pre-deploy 명령이 있으면 켜지 않는다(두 번 돈다).
- **Playwright 는 이제 레포에 없다** (2026-09-15 제거). 유일한 소비자였던 자사몰 URL 분석(`analyze-homepage`)이 프론트에서 이미 호출되지 않는 데드코드였고, chromium 설치 단계가 없어 SPA 폴백은 항상 503 이었다. 이미지에 브라우저를 넣을지 고민할 일 자체가 사라졌다 — 되살린다면 `docs/server/modules/brand-scraper.md` 의 경고(SSRF 가드 동반 복원)를 먼저 읽을 것.
- **`USER node`, exec 형식 엔트리포인트:** node가 PID 1로 SIGTERM을 직접 받는다.
- **`.dockerignore`에 `.env*` 필수.** 로컬 작업 트리에 `.env`·`.env.*.local`이 있어 빼지 않으면 이미지에 비밀번호가 들어간다.

### ⚠️ Railway가 루트 Dockerfile을 자동 감지한다

머지하는 순간 Railway 빌드가 자동 빌드에서 이 Dockerfile로 바뀐다. 이미지를 AWS 전에 운영에서 검증하는 효과가 있는 대신 아래를 지킨다.

**머지 전 Railway 대시보드 확인** — ⚠️ 아래 체크박스는 **이 절차를 실행하는 동안 손으로 찍는 임시
표시**이지 단계 상태의 근거가 아니다. 상태의 정본은 [진행표 §7](../../PROGRESS.md#7-진행-기록) 뿐이다.

- [ ] **Custom Start Command:** 비운다. 설정돼 있으면 엔트리포인트를 덮어쓰고, npm을 거치면 SIGTERM 전달이 불확실하다.
- [ ] **Pre-deploy Command:** `migrate deploy`가 있으면 그대로 동작한다(이미지에 CLI와 migrations 포함). 이 경우 `RUN_MIGRATIONS`는 켜지 않는다.
- [ ] **Healthcheck Path:** `/health`
- [ ] **`NODE_ENV`:** 환경별 기존 값을 유지한다(이미지가 기본값을 주지 않는다).

**배포 순서**
1. staging 먼저: 빌드 로그의 Dockerfile 감지 → 부팅 → `/health` → 결제 샌드박스 1건 → cron 등록 로그
2. 이상 없으면 production (트래픽 적은 시간)
3. 롤백: Railway에서 이전 배포 Redeploy, 또는 Dockerfile revert

## 로컬 이미지 검증 절차

```bash
cd klow_server
docker build -t klow-server:local .

# ⚠️ CRON_ENABLED=false 필수 — dev도 Resend 키가 켜져 있어 CRM 메일 cron이 실제 발송될 수 있다
docker run --rm -p 4000:4000 --env-file .env -e CRON_ENABLED=false --name klow-local klow-server:local
curl localhost:4000/health
docker stop klow-local                         # 정상 종료 확인 (137이면 SIGTERM 미전달)

docker run --rm --env-file .env --entrypoint npx klow-server:local prisma migrate status   # 읽기 전용
docker run --rm --entrypoint ls klow-server:local -la                                     # .env* 없어야 함
```

- `--env-file`은 따옴표를 벗기지 않는다. 값에 따옴표가 있으면 `-e`로 따로 넘긴다.
- **`RUN_MIGRATIONS=true`는 로컬에서 켜지 않는다.** `.env`가 가리키는 DB에 실제로 적용된다.
