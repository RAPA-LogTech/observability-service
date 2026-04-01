#!/bin/bash
# observability-service 빌드 & Docker Hub 푸시 + 서버 배포 자동화 스크립트

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

IMAGE="gurururu/observability-service:latest"
SERVER_IP="3.34.169.89"
SERVER="ubuntu@3.34.169.89"
SSH_KEY="$HOME/keys/log-platform-key-v5.pem"

# 1. 빌드 + 푸시 동시에
echo "[1/4] Docker 이미지 빌드 및 푸시 (linux/amd64)..."
cd "$DEPLOY_DIR"
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t $IMAGE .

# 2. 서버에서 pull
echo "[2/4] 서버에서 최신 이미지 pull..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER "sudo docker pull $IMAGE"

echo "[3/4] 서버로 docker-compose.yml 업로드 후 observability-compose.yml로 배치..."
scp -i $SSH_KEY -o StrictHostKeyChecking=no \
  "$DEPLOY_DIR/docker-compose.yml" \
    $SERVER:/tmp/observability-compose.yml

ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER "
  sudo install -o ubuntu -g ubuntu -m 644 /tmp/observability-compose.yml /home/ubuntu/observability-compose.yml
"

# 3. 서버에서 재시작
echo "[4/4] 서버에서 컨테이너 재시작..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER "
  cd /home/ubuntu && \
  sudo docker stop observability-service 2>/dev/null || true && \
  sudo docker rm -f observability-service 2>/dev/null || true && \
  sudo docker compose -f observability-compose.yml up -d observability-service
"

echo "✅ 배포 완료! http://$SERVER_IP:8081"