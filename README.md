# observability-service

FastAPI backend for logs/metrics/traces.

## Local Development Setup

### 1. Create Virtual Environment

```bash
cd observability-service
python3.11 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or on Windows:
# .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your OpenSearch/AMP credentials
nano .env
```

### 4. Run Application

```bash
uvicorn main:app --reload --port 8001
```

Server will start at `http://localhost:8001`

- Health check: `GET http://localhost:8001/health`
- Logs: `GET http://localhost:8001/v1/logs`
- Metrics: `GET http://localhost:8001/v1/metrics`
- Traces: `GET http://localhost:8001/v1/traces`

### 5. Deactivate Virtual Environment

```bash
deactivate
```

## Environment Variables

Create `.env` file in project root:

```bash
cp .env.example .env
```

Edit with your OpenSearch/AMP endpoint and credentials:

```
DATA_SOURCE_MODE=real_only
OPENSEARCH_URL=https://vpc-log-platform-dev-xxx.ap-northeast-2.es.amazonaws.com
OPENSEARCH_LOGS_INDEX=logs-*
OPENSEARCH_TRACES_INDEX=ss4o_traces-*
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=your_password
ALLOWED_ORIGINS=*
```

## Project structure

```text
observability-service/
  app/
    api/
      health.py
      logs.py
      metrics.py
      traces.py
    core/
      config.py
    data/
      mock_data.py
    services/
      observability_service.py
      streaming_service.py
    main.py
  main.py
  .env.example
  requirements.txt
  requirements-dev.txt
```

## API Endpoints

- `GET /health` - Health check
- `GET /v1/logs` - Query logs from OpenSearch
- `GET /v1/logs/backlog` - Get paginated log backlog (for pagination)
- `GET /v1/logs/stream` - SSE (Server-Sent Events) for real-time log streaming
- `GET /v1/metrics` - Query metrics from AMP
- `GET /v1/metrics/backlog` - Get paginated metrics backlog
- `GET /v1/metrics/stream` - SSE for real-time metrics streaming
- `GET /v1/traces` - Query traces from OpenSearch
- `GET /v1/traces/{trace_id}` - Get specific trace detail
- `GET /v1/traces/backlog` - Get paginated traces backlog
- `GET /v1/traces/stream` - SSE for real-time traces streaming

## Development Tools

### Pre-commit with pylint

Install dev dependencies:

```bash
# Activate venv first
source .venv/bin/activate

pip install -r requirements-dev.txt
pre-commit install
```

Run linting manually:

```bash
pre-commit run --all-files
```

After installation, `pylint` runs automatically before each commit.
