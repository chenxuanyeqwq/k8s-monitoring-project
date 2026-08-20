#!/usr/bin/env bash
# 把飞书 webhook 注入 feishu-bridge 的 ConfigMap，让告警真推到飞书群。
#
# 用法：
#   bash set_webhook.sh                      # 读项目根 .env 里的 FEISHU_WEBHOOK
#   bash set_webhook.sh https://open.feishu.cn/open-apis/bot/v2/hook/xxx   # 或直接传 URL
#
# 链路：Prometheus → Alertmanager → feishu-bridge → 飞书群
# Alertmanager 的 receiver 已固定指向 feishu-bridge 服务，这里只需给 bridge 填真实 URL。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_CFG="$SCRIPT_DIR/../05-feishu-bridge/manifests/configmap.yaml"
ENV_FILE="$SCRIPT_DIR/../.env"

WEBHOOK="${1:-}"
if [[ -z "$WEBHOOK" && -f "$ENV_FILE" ]]; then
  WEBHOOK="$(grep -E '^FEISHU_WEBHOOK=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '[:space:]' || true)"
  # 去掉可选的外层引号（用户可能写成 "https://..." 或 'https://...'）
  WEBHOOK="${WEBHOOK%\"}"; WEBHOOK="${WEBHOOK#\"}"
  WEBHOOK="${WEBHOOK%\'}"; WEBHOOK="${WEBHOOK#\'}"
fi

if [[ -z "$WEBHOOK" ]]; then
  echo "❌ 没找到有效 webhook。先填 $ENV_FILE（FEISHU_WEBHOOK=你的URL），或直接传 URL：bash set_webhook.sh https://open.feishu.cn/..."
  exit 1
fi

sed -i "s|FEISHU_WEBHOOK: \"\"|FEISHU_WEBHOOK: \"$WEBHOOK\"|" "$BRIDGE_CFG"
echo "✅ 已注入 webhook 到 $BRIDGE_CFG"
echo "下一步执行："
echo "  kubectl -n monitoring apply -f ../05-feishu-bridge/manifests/configmap.yaml"
echo "  kubectl -n monitoring rollout restart deployment/feishu-bridge"
