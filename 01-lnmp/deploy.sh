#!/bin/bash
# LNMP 服务器部署脚本（阶段2：只拉镜像，不在服务器构建）
# 用法: bash deploy.sh   (可被 CI/CD 远程调用,也可手动在服务器上跑)
set -e
cd "$(dirname "$0")"

# ACR 仓库必填校验，防止缺省时 compose 镜像地址变成空前缀坏值
ACR_REGISTRY=${ACR_REGISTRY:?必须设置 ACR_REGISTRY(如 crpi-xxx.cn-hongkong.personal.cr.aliyuncs.com)}
IMAGE_TAG=${IMAGE_TAG:-latest}

# 有提供凭据就显式登录；否则用本机已保存的 ACR 凭据（CI 部署时会 docker login 落盘）
if [ -n "${ACR_USERNAME:-}" ] && [ -n "${ACR_PASSWORD:-}" ]; then
  echo "==> [1/3] 登录镜像仓库 ${ACR_REGISTRY}"
  echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin
else
  echo "==> [1/3] 使用本机已保存的 ACR 凭据"
fi

echo "==> [2/3] 拉取并启动容器 (${ACR_REGISTRY}/fchen/lnmp-php:${IMAGE_TAG})"
export ACR_REGISTRY IMAGE_TAG
docker compose up -d --pull always

echo "==> [3/3] 自检(带重试,等 MySQL 就绪)"
docker compose ps
SELF_CHECK_OK=0
for i in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost || true)
  echo "尝试 $i: HTTPS $code"
  if [ "$code" = "200" ]; then
    echo "✅ 部署完成: https://www.fchen.xyz (镜像 tag: $IMAGE_TAG)"
    SELF_CHECK_OK=1
    break
  fi
  sleep 3
done
if [ "$SELF_CHECK_OK" != "1" ]; then
  echo "⚠️ 10 次尝试后仍非 200,查看日志: docker compose logs --tail 50"
  exit 1
fi

echo "==> [4/4] 安全冒烟（加固回归校验）"
for path in "/.env" "/actuator"; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost$path" || true)
  echo "  $path -> $code (期望 444)"
  if [ "$code" != "444" ]; then
    echo "❌ 安全冒烟失败: $path 返回 $code，加固可能被冲掉"
    exit 1
  fi
done
code=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost/definitely-not-a-real-path-xyz" || true)
echo "  未知路径 -> $code (期望 404)"
if [ "$code" != "404" ]; then
  echo "❌ 安全冒烟失败: 未知路径返回 $code"
  exit 1
fi
echo "✅ 安全冒烟通过: 加固未被冲掉"
