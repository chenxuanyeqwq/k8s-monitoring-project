#!/bin/bash
# LNMP 一键回滚：拉取指定旧镜像并用它重启容器
# 用法: bash rollback.sh <镜像 short-sha>
# 查看可用版本: docker images | grep lnmp-php
set -e
cd "$(dirname "$0")"

if [ -z "$1" ]; then
  echo "用法: bash rollback.sh <镜像 short-sha>"
  echo "可用版本: docker images | grep lnmp-php"
  exit 1
fi

SHA="$1"
ACR_REGISTRY=${ACR_REGISTRY:?必须设置 ACR_REGISTRY(如 registry.cn-hangzhou.aliyuncs.com)}
ACR_USERNAME=${ACR_USERNAME:?必须设置 ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD:?必须设置 ACR_PASSWORD}

echo "==> 登录镜像仓库 ${ACR_REGISTRY}"
echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin

echo "==> 拉取旧镜像 ${ACR_REGISTRY}/fchen/lnmp-php:${SHA}"
docker pull "${ACR_REGISTRY}/fchen/lnmp-php:${SHA}"

echo "==> 用旧 tag 重启容器"
export ACR_REGISTRY
IMAGE_TAG="$SHA" docker compose up -d

echo "==> 自检"
for i in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost || true)
  echo "尝试 $i: HTTPS $code"
  if [ "$code" = "200" ]; then
    echo "✅ 回滚完成: 已回到 ${SHA}"
    exit 0
  fi
  sleep 3
done
echo "⚠️ 回滚自检失败,查看日志: docker compose logs --tail 50"
exit 1
