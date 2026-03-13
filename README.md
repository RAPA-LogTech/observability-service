# observability-service

FastAPI backend for logs, metrics, and traces.

## Quick Start (from clone to run)

### 0. Prerequisites

- Python 3.11
- pip (bundled with Python)
- git

Check versions:

```bash
python3.11 --version
git --version
```

Optional (if Python 3.11 is not installed):

```bash
# macOS (Homebrew)
brew install python@3.11

# Ubuntu/Debian
# sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip
```

### 1. Clone the repository

If you are cloning this service as part of the LogTech workspace:

```bash
git clone https://github.com/RAPA-LogTech/observability-service.git
cd observability-service
```

If this service lives inside a monorepo, clone that repository and move into this folder:

```bash
git clone <your-monorepo-url>
cd <your-monorepo>/observability-service
```

### 2. Create and activate virtual environment (venv)

Create venv in the service root:

```bash
python3.11 -m venv .venv
```

Activate venv:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
# .venv\Scripts\Activate.ps1
```

When activated, your shell prompt usually shows `(.venv)`.

### 3. Install dependencies

Install all required Python packages for app + development tools in one shot:

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

If you only need runtime dependencies (without lint/format tools):

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create `.env` from example:

```bash
cp .env.example .env
```

Open `.env` and fill values for your environment.

Minimum commonly used settings:

```env
SERVICE_NAME=observability-service
ENVIRONMENT=local
DATA_SOURCE_MODE=real_only

ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

OPENSEARCH_URL=https://vpc-log-platform-dev-berciu3s6yeeq6getvwavbebz4.ap-northeast-2.es.amazonaws.com
OPENSEARCH_LOGS_INDEX=logs-*
OPENSEARCH_TRACES_INDEX=traces-*
OPENSEARCH_TIMEOUT_SECONDS=8
OPENSEARCH_VERIFY_TLS=true

OPENSEARCH_USERNAME=<your-username>
OPENSEARCH_PASSWORD=<your-password>
# or use API key instead
# OPENSEARCH_API_KEY=<your-api-key>
```

### 5. Run the server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8081
```

Server URL:

- `http://localhost:8081`

### 6. Verify API is working

```bash
curl -s http://localhost:8081/health
curl -s "http://localhost:8081/v1/logs?limit=3"
curl -s "http://localhost:8081/v1/metrics?minutes=15"
curl -s "http://localhost:8081/v1/traces?limit=3"
```

### 7. Stop / deactivate

Stop server with `Ctrl+C`, then:

```bash
deactivate
```

## API Endpoints

- `GET /health` - health check
- `GET /v1/logs` - query logs from OpenSearch
- `GET /v1/logs/backlog` - paginated backlog for stream recovery
- `GET /v1/logs/stream` - SSE stream for real-time logs
- `GET /v1/metrics` - query metrics (AMP)
- `GET /v1/metrics/backlog` - paginated metrics backlog
- `GET /v1/metrics/stream` - SSE stream for real-time metrics
- `GET /v1/traces` - query traces from OpenSearch
- `GET /v1/traces/{trace_id}` - trace detail
- `GET /v1/traces/backlog` - paginated traces backlog
- `GET /v1/traces/stream` - SSE stream for real-time traces

## Development Utilities

Install development tools separately (optional):

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

Run checks manually:

```bash
pre-commit run --all-files
```

## Troubleshooting

### `python3.11: command not found`

Use installed Python path:

```bash
python3 -m venv .venv
```

### `ModuleNotFoundError` after install

Usually venv is not activated. Re-activate and reinstall:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### OpenSearch timeout or auth error

- Verify `OPENSEARCH_URL`, credentials/API key, TLS option
- Confirm network access/security group/VPC routing
- Test with `curl` directly to OpenSearch endpoint
