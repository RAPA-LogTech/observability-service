# observability-service

FastAPI backend for logs, metrics, and traces. Runs on port **8081**.

---

## EC2 배포 (처음부터)

EC2 인스턴스에 서비스를 **완전히 새로 설치**할 때 이 섹션을 따라 진행하세요.

### 1. 패키지 설치

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip git
```

### 2. 코드 클론

```bash
cd ~
git clone https://github.com/RAPA-LogTech/observability-service.git backend
cd ~/backend
```

### 3. 가상환경 생성 및 의존성 설치

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. `.env` 파일 생성

아래 명령어를 그대로 복사해서 실행하면 `.env`가 생성됩니다:

```bash
cat > ~/backend/.env << 'EOF'
SERVICE_NAME=observability-service
ENVIRONMENT=production
DATA_SOURCE_MODE=real_only

ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

OPENSEARCH_URL=https://vpc-log-platform-dev-berciu3s6yeeq6getvwavbebz4.ap-northeast-2.es.amazonaws.com
OPENSEARCH_LOGS_INDEX=logs-*
OPENSEARCH_TRACES_INDEX=traces-*
OPENSEARCH_TIMEOUT_SECONDS=8
OPENSEARCH_VERIFY_TLS=true
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=Fkvk1234!

AMP_ENDPOINT=https://aps-workspaces.ap-northeast-2.amazonaws.com/workspaces/ws-438cd95b-8a3a-4106-b8e9-9b7c8af4f5f8/api/v1/remote_write
AMP_TIMEOUT_SECONDS=8
AMP_STEP_SECONDS=60
EOF
```

생성 확인:

```bash
cat ~/backend/.env
```

### 5. 서버 백그라운드 실행

```bash
mkdir -p ~/backend/logs
cd ~/backend
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8081 > ~/backend/logs/app.log 2>&1 &
echo $! > ~/backend/logs/app.pid
echo "Started. PID: $(cat ~/backend/logs/app.pid)"
```

### 6. 동작 확인

```bash
# 헬스 체크
curl -s http://localhost:8081/health

# 로그 조회 테스트
curl -s "http://localhost:8081/v1/logs?limit=3"

# 실시간 로그 확인
tail -f ~/backend/logs/app.log
```

---

## 코드 업데이트 절차

코드가 변경됐을 때 EC2에서 반영하는 방법:

```bash
cd ~/backend
git pull
source .venv/bin/activate
pip install -r requirements.txt   # requirements 변경 시만 필요

# 서버 재시작
kill $(cat logs/app.pid) 2>/dev/null || pkill -f "uvicorn main:app"
sleep 1
nohup uvicorn main:app --host 0.0.0.0 --port 8081 > logs/app.log 2>&1 &
echo $! > logs/app.pid
echo "Restarted. PID: $(cat logs/app.pid)"
```

---

## 로컬 개발 (macOS)

### 0. 사전 요구사항

```bash
# macOS (Homebrew)
brew install python@3.11 git
```

### 1. 의존성 설치

```bash
cd observability-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

개발 도구까지 포함:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

### 2. `.env` 생성

```bash
cp .env.example .env
# OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD 입력
```

### 3. 서버 실행

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8081
```

---

## API Endpoints

| Method | Path | 설명 |
|--------|------|------|
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

## 트러블슈팅

### 서버 PID 확인 / 수동 종료

```bash
cat ~/backend/logs/app.pid      # 저장된 PID 확인
ps aux | grep uvicorn           # 실행 중인 프로세스 확인
pkill -f "uvicorn main:app"     # 강제 종료
```

### OpenSearch 401 오류

자격증명 직접 테스트:

```bash
curl -i -s --max-time 8 -u 'admin:Fkvk1234!' \
  'https://vpc-log-platform-dev-berciu3s6yeeq6getvwavbebz4.ap-northeast-2.es.amazonaws.com'
```

200이 뜨면 서버가 `.env`를 읽지 못한 것 → 서버 재시작 필요:

```bash
kill $(cat ~/backend/logs/app.pid) 2>/dev/null || pkill -f "uvicorn main:app"
sleep 1
cd ~/backend && source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8081 > logs/app.log 2>&1 &
echo $! > logs/app.pid
```

### `ModuleNotFoundError`

venv가 활성화되지 않은 경우:

```bash
source ~/backend/.venv/bin/activate
pip install -r requirements.txt
```

### `python3.11: command not found`

```bash
# 설치된 Python으로 대체
python3 -m venv .venv
```
