

# observability-service

FastAPI backend for logs, metrics, and traces. 기본 포트: **8081**

---

## Docker Compose 단일 파일 배포 (환경변수 파일 없이)


### 1. docker-compose.yaml을 리눅스에서 바로 저장하는 명령어 예시

```bash
cat > docker-compose.yaml <<'EOF'
services:
  observability-service:
    build:
      context: ./observability-service
      dockerfile: Dockerfile
    ports:
      - "8081:8081"
    environment:
      - ALLOWED_ORIGINS=http://localhost:3000
      - OPENSEARCH_URL=https://vpc-log-platform-dev-emru3vfn6thqsybe5qc7nndgga.ap-northeast-2.es.amazonaws.com
      - OPENSEARCH_USERNAME=admin
      - OPENSEARCH_PASSWORD=your_password
      - AMP_ENDPOINT=https://aps-workspaces.ap-northeast-2.amazonaws.com/workspaces/ws-xxxx/api/v1/query
    restart: unless-stopped
EOF
```

위 명령어를 복사해서 붙여넣으면 docker-compose.yaml 파일이 바로 생성됩니다.

### 2. 컨테이너 실행/업데이트

```bash
docker compose up -d
```

### 3. 상태/로그 확인

```bash
docker compose ps
docker compose logs --tail=100 observability-service
```

### 4. 기타

- 환경변수는 docker-compose.yml의 environment: 섹션에서 직접 관리합니다.
- 별도의 .env 파일이나 export 없이 바로 적용됩니다.
- 기존 venv/python 수동 실행 방식은 더 이상 사용하지 않습니다.

---

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

git pull
git clone https://github.com/RAPA-LogTech/observability-service.git
git pull
