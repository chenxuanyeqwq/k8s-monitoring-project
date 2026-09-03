#!/usr/bin/env bash
# 开机兜底：等 Docker 就绪后，把两个 compose 项目全量对齐拉起（幂等，不干扰已运行容器）。
# 背景：2026-09-03 重启后 cm-prometheus 未被 restart:unless-stopped 自动恢复，导致监控盲区。
#       Docker restart-on-boot 恢复不可靠，此脚本是独立于 Docker 语义的兜底。
LOG=/var/log/restore-docker-stack.log
echo "===== $(date '+%F %T') start =====" >>"$LOG"

# 等 Docker daemon 就绪（最多约 150s）
n=0
until docker info >/dev/null 2>&1; do
  n=$((n+1))
  if [ "$n" -ge 50 ]; then
    echo "docker daemon not ready after ~150s, abort" >>"$LOG"
    exit 1
  fi
  sleep 3
done
sleep 5

echo "--- LNMP project ---" >>"$LOG"
if cd /opt/k8s-project/01-lnmp; then
  # ACR_REGISTRY/IMAGE_TAG 只在 deploy 环境里有，cron 下为空会导致 compose 插值成
  # "/fchen/lnmp-php:latest"(invalid) 或把线上版本改成 latest。这里从当前运行的
  # lnmp-php 镜像 ref 反推，保证 restore 只启动原容器、不 pull 不 recreate 不换版本。
  PHPIMG=$(docker inspect --format '{{.Config.Image}}' lnmp-php 2>/dev/null)
  if [ -n "$PHPIMG" ]; then
    export ACR_REGISTRY="${PHPIMG%%/*}"
    export IMAGE_TAG="${PHPIMG##*:}"
    echo "pin php image: ACR_REGISTRY=$ACR_REGISTRY IMAGE_TAG=$IMAGE_TAG" >>"$LOG"
  else
    echo "lnmp-php container not found, skipping env pin" >>"$LOG"
  fi
  docker compose up -d >>"$LOG" 2>&1
else
  echo "no /opt/k8s-project/01-lnmp, skip" >>"$LOG"
fi

echo "--- cloud-monitoring project ---" >>"$LOG"
if cd /opt/k8s-project/07-cloud-monitoring; then
  docker compose -f docker-compose.monitoring.yml up -d >>"$LOG" 2>&1
else
  echo "no /opt/k8s-project/07-cloud-monitoring, skip" >>"$LOG"
fi

echo "===== $(date '+%F %T') done =====" >>"$LOG"
