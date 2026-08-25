#!/bin/bash
# LNMP 服务器部署脚本
# 作用:构建 php 镜像 → 启动/更新 compose 容器 → 自检
# 用法: bash deploy.sh   (可被 CI/CD 远程调用,也可手动在服务器上跑)
set -e
cd "$(dirname "$0")"

echo "==> [1/3] 构建 php 镜像(含 pdo_mysql)"
docker build -t lnmp-php ./php

echo "==> [2/3] 启动/更新容器"
docker compose up -d --build

echo "==> [3/3] 自检(带重试,等 MySQL 就绪)"
docker compose ps
for i in $(seq 1 10); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 || true)
  echo "尝试 $i: HTTP $code"
  if [ "$code" = "200" ]; then
    echo "✅ 部署完成: http://localhost:8080"
    exit 0
  fi
  sleep 3
done
echo "⚠️ 10 次尝试后仍非 200,查看日志: docker compose logs --tail 50"
exit 1
