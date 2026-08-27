#!/bin/bash
# LNMP 服务器部署脚本（阶段2：只拉镜像，不在服务器构建）
# 用法: bash deploy.sh   (可被 CI/CD 远程调用,也可手动在服务器上跑)
set -e
cd "$(dirname "$0")"

# ACR 必填校验，防止缺省时 compose 镜像地址变成空前缀坏值
ACR_REGISTRY=${ACR_REGISTRY:?必须设置 ACR_REGISTRY(如 registry.cn-hangzhou.aliyuncs.com)}
ACR_USERNAME=${ACR_USERNAME:?必须设置 ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD:?必须设置 ACR_PASSWORD}
IMAGE_TAG=${IMAGE_TAG:-latest}

echo "==> [1/3] 登录镜像仓库 ${ACR_REGISTRY}"
echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin

echo "==> [2/3] 拉取并启动容器 (${ACR_REGISTRY}/lnmp-php:${IMAGE_TAG})"
export ACR_REGISTRY IMAGE_TAG
docker compose up -d --pull always

echo "==> [3/3] 自检(带重试,等 MySQL 就绪)"
docker compose ps
for i in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost || true)
  echo "尝试 $i: HTTPS $code"
  if [ "$code" = "200" ]; then
    echo "✅ 部署完成: https://www.fchen.xyz (镜像 tag: $IMAGE_TAG)"
    exit 0
  fi
  sleep 3
done
echo "⚠️ 10 次尝试后仍非 200,查看日志: docker compose logs --tail 50"
exit 1
