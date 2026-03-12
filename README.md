# observability-service

FastAPI backend for logs/metrics/traces.

## Where to put environment variables

Create a local `.env` file in this folder.

1. Copy `.env.example` to `.env`
2. Edit values in `.env`
3. Run app (settings are loaded automatically)

```bash
cp .env.example .env
uvicorn main:app --reload --port 8001
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
    main.py
  main.py
  .env.example
  requirements.txt
```

## Endpoints

- `GET /health`
- `GET /v1/logs`
- `GET /v1/metrics`
- `GET /v1/traces`
- `GET /v1/traces/{trace_id}`

## Pre-commit with pylint

Install dev tools and register git hooks:

```bash
pip3 install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

Run once manually:

```bash
pre-commit run --all-files
```

After installation, `pylint` runs automatically before each commit.
