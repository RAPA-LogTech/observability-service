# observability-service

FastAPI backend for logs, metrics, and traces. 기본 포트: **8081**

---

## AWS 배포

Terraform을 통해 Dashboard EC2에 Docker Compose로 자동 배포됩니다.

### 배포 명령어

```bash
cd aws-observability-platform
terraform apply
```

### 배포 구조

```
Terraform → Dashboard EC2 생성 → user_data_dashboard.sh →
  ├─ observability-service (Docker, 8081포트)
  └─ dashboard 프론트엔드 (Docker, 3000포트)
```

### 자동 설정 환경변수

| 변수 | 값 | 설명 |
|------|-----|------|
| `OPENSEARCH_URL` | `${opensearch_endpoint}` | OpenSearch 엔드포인트 |
| `OPENSEARCH_USERNAME` | `${opensearch_master_user}` | OpenSearch 마스터 유저 |
| `OPENSEARCH_PASSWORD` | `${opensearch_master_password}` | OpenSearch 비밀번호 |
| `AMP_ENDPOINT` | `${amp_remote_write_url}` | AMP Remote Write URL |
| `ALLOWED_ORIGINS` | `${public_dashboard_url}` | CORS 허용 도메인 |
| `AWS_REGION` | `${aws_region}` | AWS 리전 |

### Docker 설정

- 이미지: `gurururu/observability-service:latest`
- 네트워크: `host` 모드
- 재시작: `unless-stopped`

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

## 배포 상태 확인

```bash
# EC2 접속 후
docker ps
docker logs -f observability-service
```

---

## 이미지 최신화

서버에 이미 배포된 상태에서 코드를 수정하고 이미지를 최신화할 때 사용합니다.

### 빌드 & 푸시 & 서버 배포

```bash
# deploy.sh 실행 (이미지 빌드 → Docker Hub 푸시 → 서버 pull 및 재시작)
./deploy.sh
```

### 수동 배포

```bash
# 1. 이미지 빌드 및 푸시
docker buildx build --platform linux/amd64 --push -t gurururu/observability-service:latest .

# 2. 서버 접속
ssh -i ~/.ssh/your-key.pem ubuntu@<server-ip>

# 3. 이미지 pull 및 컨테이너 재시작
sudo docker pull gurururu/observability-service:latest
sudo docker stop observability-service && sudo docker rm -f observability-service
sudo docker compose -f /home/ubuntu/observability-compose.yml up -d observability-service
```
