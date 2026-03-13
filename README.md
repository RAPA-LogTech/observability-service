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
git clone https://github.com/RAPA-LogTech/observability-service.git
cd ~/observability-service
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
cat > ~/observability-service/.env << 'EOF'
SERVICE_NAME=observability-service
ENVIRONMENT=production
DATA_SOURCE_MODE=real_only

ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

OPENSEARCH_URL=https://vpc-logtech-dev-an3ndw6k4k7nzlvnrounfxfn3q.ap-northeast-2.es.amazonaws.com
OPENSEARCH_LOGS_INDEX=logs-*
OPENSEARCH_TRACES_INDEX=traces-*
OPENSEARCH_TIMEOUT_SECONDS=8
OPENSEARCH_VERIFY_TLS=true
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=SDdfgDG1234!

AMP_ENDPOINT=https://aps-workspaces.ap-northeast-2.amazonaws.com/workspaces/ws-aafbc09f-d82d-4e8b-bb9c-46def73576e2/api/v1/query
AMP_TIMEOUT_SECONDS=8
AMP_STEP_SECONDS=60
EOF
```

생성 확인:

```bash
cat ~/observability-service/.env
```

### 5. 서버 포어그라운드 실행

```bash
cd ~/observability-service
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8081
```

### 6. 동작 확인

```bash
# 헬스 체크
curl -s http://localhost:8081/health

# 로그 조회 테스트
curl -s "http://localhost:8081/v1/logs?limit=3"

# 실시간 로그는 위 uvicorn 실행 터미널에서 바로 출력됨
```

---

## 코드 업데이트 절차

코드가 변경됐을 때 EC2에서 반영하는 방법:

```bash
cd ~/observability-service
git pull
source .venv/bin/activate
pip install -r requirements.txt   # requirements 변경 시만 필요

# 서버 재시작
pkill -f "uvicorn main:app" || true
sleep 1
uvicorn main:app --host 0.0.0.0 --port 8081
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

### 포어그라운드 실행 중 종료

```bash
# 현재 터미널에서 실행 중이면 Ctrl+C

# 다른 터미널에서 떠 있는 uvicorn 정리
pkill -f "uvicorn main:app"
ps aux | grep uvicorn
```

### OpenSearch 401 오류

자격증명 직접 테스트:

```bash
curl -i -s --max-time 8 -u 'admin:SDdfgDG1234!' \
  'https://vpc-logtech-dev-an3ndw6k4k7nzlvnrounfxfn3q.ap-northeast-2.es.amazonaws.com'
```

200이 뜨면 서버가 `.env`를 읽지 못한 것 → 서버 재시작 필요:

```bash
pkill -f "uvicorn main:app" || true
sleep 1
cd ~/observability-service && source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8081
```

### `ModuleNotFoundError`

venv가 활성화되지 않은 경우:

```bash
source ~/observability-service/.venv/bin/activate
pip install -r requirements.txt
```

### `python3.11: command not found`

```bash
# 설치된 Python으로 대체
python3 -m venv .venv
```

---

## `git pull` 이후 어디부터 다시 실행하나요?

아래 순서대로 하면 됩니다.

### EC2 (포어그라운드 실행 기준)

```bash
cd ~/observability-service
git pull
source .venv/bin/activate

# requirements 변경이 있을 때만 실행
pip install -r requirements.txt

# 기존 서버 종료 (실행 중이면)
pkill -f "uvicorn main:app" || true
sleep 1

# 서버 다시 실행
uvicorn main:app --host 0.0.0.0 --port 8081
```

체크 포인트:

- 터미널에 `Application startup complete.`가 보이면 정상 실행
- 다른 터미널에서 `curl -s http://localhost:8081/health` 확인

### 로컬(macOS)

```bash
cd observability-service
git pull
source .venv/bin/activate

# requirements 변경이 있을 때만 실행
pip install -r requirements.txt

# 개발 모드 실행
uvicorn main:app --reload --host 0.0.0.0 --port 8081
```
