#!/bin/bash
# observability-service 빌드 & Docker Hub 푸시 + 서버 배포 자동화 스크립트

set -e

IMAGE="gurururu/observability-service:latest"
SERVER="ubuntu@3.37.198.240"
SSH_KEY="~/keys/log-platform-key-v5.pem"

# 1. 빌드 + 푸시 동시에
echo "[1/3] Docker 이미지 빌드 및 푸시 (linux/amd64)..."
cd /Users/mac/Projects/logtech/observability-service
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t $IMAGE .

# 2. 서버에서 pull
echo "[2/3] 서버에서 최신 이미지 pull..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER "sudo docker pull $IMAGE"

echo "[2.5/3] 서버로 docker-compose.yml 파일 복사..."
scp -i $SSH_KEY -o StrictHostKeyChecking=no \
    /Users/mac/Projects/logtech/observability-service/docker-compose.yml \
    $SERVER:/home/ubuntu/docker-compose.yml

# 3. 서버에서 재시작
echo "[3/3] 서버에서 컨테이너 재시작..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER "
  cd /home/ubuntu && \
  sudo docker stop observability-service 2>/dev/null || true && \
  sudo docker rm -f observability-service 2>/dev/null || true && \
  sudo docker compose up -d observability-service
"

echo "✅ 배포 완료!"