# observability-service

FastAPI backend for logs, metrics, and traces. Runs on port **8081**.

---

## 배포 기준

운영 배포는 아래 `Docker 배포 운영 (env/yaml 기반)` 섹션만 사용합니다.

기존 venv 수동 실행 방식은 더 이상 사용하지 않습니다.

---

## API Endpoints

| Method | Path | 설명 |
| ------ | ---- | ---- |
| GET | `/health` | 헬스 체크 |
| GET | `/v1/logs` | 로그 조회 (OpenSearch) |
| GET | `/v1/logs/stream` | 실시간 로그 스트림 (SSE) |
| GET | `/v1/logs/backlog` | 로그 페이징 |
| GET | `/v1/metrics` | 메트릭 조회 (AMP) |
| GET | `/v1/metrics/stream` | 실시간 메트릭 스트림 (SSE) |
| GET | `/v1/metrics/backlog` | 메트릭 페이징 |
| GET | `/v1/traces` | 트레이스 조회 (OpenSearch) |
| GET | `/v1/traces/{trace_id}` | 트레이스 상세 |
| GET | `/v1/traces/stream` | 실시간 트레이스 스트림 (SSE) |
| GET | `/v1/traces/backlog` | 트레이스 페이징 |

---

## 트러블슈팅 (Docker 기준)

### OpenSearch 401 오류

```bash
curl -i -s --max-time 8 -u 'admin:<실제_비밀번호>' \
  'https://vpc-logtech-dev-an3ndw6k4k7nzlvnrounfxfn3q.ap-northeast-2.es.amazonaws.com'
```

### git pull 이후 재배포

```bash
cd ~/observability-service
git pull
cd ~/observability-service/deploy
./update.sh
```

### 컨테이너 상태/로그 확인

```bash
cd ~/observability-service/deploy
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=100 observability-service
```

---

## Docker 배포 운영 (env/yaml 기반)

`deploy` 폴더 기준으로 운영하면 됩니다.

생성된 파일:

- `deploy/docker-compose.prod.yml`
- `deploy/.env.prod.example`
- `deploy/update.sh`

### 1) 최초 1회 설정

```bash
cd ~/observability-service/deploy
cp .env.prod.example .env.prod
# .env.prod에서 IMAGE_NAME, IMAGE_TAG, OPENSEARCH/AMP 값 수정
```

### 2) 컨테이너 최초 기동

```bash
cd ~/observability-service/deploy
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

### 3) `latest` 이미지로 업데이트

```bash
cd ~/observability-service/deploy
./update.sh
```

동작 내용:

- 최신 이미지 pull
- `observability-service` 컨테이너만 recreate
- 상태/최근 로그 출력

### 4) 특정 태그로 업데이트/롤백

```bash
cd ~/observability-service/deploy
./update.sh 2026.03.19-1
```

또는 `.env.prod`의 `IMAGE_TAG` 변경 후 다시:

```bash
./update.sh
```

---

## 서버에 올리는 방법 + 환경변수 사용법

아래 순서로 하면 EC2 서버에서 Docker 기반으로 운영할 수 있습니다.

### 1) 서버에 코드 올리기 (최초)

```bash
cd ~
git clone https://github.com/RAPA-LogTech/observability-service.git
cd ~/observability-service/deploy
```

### 2) 서버에서 코드 갱신 (이후 반복)

```bash
cd ~/observability-service
git pull
cd ~/observability-service/deploy
```

### 3) 환경변수 파일 생성

```bash
cd ~/observability-service/deploy
cp .env.prod.example .env.prod
```

`.env.prod`에서 최소 아래 항목은 반드시 채우세요.

```env
IMAGE_NAME=rapa-logtech/observability-service
IMAGE_TAG=latest

ENVIRONMENT=production
DATA_SOURCE_MODE=real_only
ALLOWED_ORIGINS=http://13.209.190.231:3000

OPENSEARCH_URL=https://vpc-logtech-dev-an3ndw6k4k7nzlvnrounfxfn3q.ap-northeast-2.es.amazonaws.com
OPENSEARCH_LOGS_INDEX=logs-*
OPENSEARCH_TRACES_INDEX=traces-*
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=<실제_비밀번호>

AMP_ENDPOINT=https://aps-workspaces.ap-northeast-2.amazonaws.com/workspaces/ws-aafbc09f-d82d-4e8b-bb9c-46def73576e2/api/v1/query
```

주의:

- `.env.prod`는 서버 전용 파일입니다. Git에 커밋하지 마세요.
- 비밀번호에 `!` 같은 특수문자가 있어도 `.env.prod`에는 그대로 넣으면 됩니다.

### 4) 컨테이너 실행

```bash
cd ~/observability-service/deploy
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

### 5) 이미지 업데이트 (latest 운영)

```bash
cd ~/observability-service/deploy
./update.sh
```

### 6) 상태 확인

```bash
cd ~/observability-service/deploy
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=100 observability-service
curl -s http://localhost:8081/health
```
