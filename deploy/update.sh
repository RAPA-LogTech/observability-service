#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".env.prod" ]]; then
  echo "[ERROR] deploy/.env.prod 파일이 없습니다."
  echo "        cp .env.prod.example .env.prod 후 값 설정하세요."
  exit 1
fi

# Optional: first argument overrides IMAGE_TAG
if [[ $# -ge 1 ]]; then
  export IMAGE_TAG="$1"
fi

COMPOSE_FILE="docker-compose.prod.yml"
SERVICE_NAME="observability-service"

echo "[INFO] Pull image: ${IMAGE_NAME:-rapa-logtech/observability-service}:${IMAGE_TAG:-latest}"
docker compose --env-file .env.prod -f "$COMPOSE_FILE" pull "$SERVICE_NAME"

echo "[INFO] Recreate container"
docker compose --env-file .env.prod -f "$COMPOSE_FILE" up -d --no-deps --force-recreate "$SERVICE_NAME"

echo "[INFO] Service status"
docker compose --env-file .env.prod -f "$COMPOSE_FILE" ps "$SERVICE_NAME"

echo "[INFO] Recent logs"
docker compose --env-file .env.prod -f "$COMPOSE_FILE" logs --tail=50 "$SERVICE_NAME"
