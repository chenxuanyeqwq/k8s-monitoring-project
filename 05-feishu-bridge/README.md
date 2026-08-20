# 模块5：feishu-bridge · Alertmanager → 飞书 转换桥（05-feishu-bridge）

**解决的问题**：Alertmanager 的 webhook 直接 POST 的是它自己的告警 JSON
（`{"version":"4","alerts":[...]}`），飞书自定义机器人只认飞书消息格式
（`{"msg_type":"text",...}`）。两者格式不兼容，所以需要这个转换层。

## 链路

```
Prometheus(规则触发) → Alertmanager → feishu-bridge → 飞书群 webhook
                                   (本模块, 转格式+推送)
```

## 功能

- `POST /alert` 接收 Alertmanager webhook，转成飞书文本消息后推送飞书
- `GET  /healthz` 健康检查
- 飞书 webhook 从环境变量 `FEISHU_WEBHOOK` 读（k8s 里来自 ConfigMap `feishu-config`），
  未配置时只打印日志——便于先验证上游链路、再单独填 URL

## 部署（已实测通过 ✅ 2026-08-20）

```bash
# 1. 构建 + 导入镜像到 k3s（k3d 不在 PATH 时直接用 ctr）
docker build -t feishu-bridge:1.0 .
docker save feishu-bridge:1.0 -o /tmp/fb.tar
docker cp /tmp/fb.tar k3d-k8s-project-server-0:/fb.tar
docker exec k3d-k8s-project-server-0 sh -c 'ctr -n k8s.io images import /fb.tar'

# 2. 部署
kubectl apply -f manifests/

# 3. 填真实飞书 URL（唯一待办）
bash ../03-monitoring/set_webhook.sh          # 读根目录 .env
kubectl -n monitoring apply -f manifests/configmap.yaml
kubectl -n monitoring rollout restart deployment/feishu-bridge

# 4. 验证
kubectl -n monitoring logs deploy/feishu-bridge --tail=20
```

## 本地单测

```bash
python bridge.py --port 18099
# 另开终端 POST 一条样例告警：
curl -X POST http://127.0.0.1:18099/alert -H 'Content-Type: application/json' -d '{"status":"firing","alerts":[{"labels":{"alertname":"Demo"},"annotations":{"summary":"测试"}}]}'
```

## 验证结果（2026-08-20）

- [x] 本地 mock：firing / resolved 两种状态均正确转换
- [x] 集群内直连：port-forward → POST → HTTP 200
- [x] 端到端：CPU 压测 → Prometheus `HighCPUUsage` firing → Alertmanager → bridge 日志收到真实告警
- [x] `send_resolved`：状态 `resolved` → 输出「已恢复」消息

## 目录结构

```
05-feishu-bridge/
├── bridge.py         # 转换服务（纯标准库 http.server）
├── Dockerfile        # DaoCloud python:3.12-slim
├── manifests/
│   ├── configmap.yaml   # FEISHU_WEBHOOK（set_webhook.sh 注入）
│   ├── deployment.yaml  # Deployment feishu-bridge :8080
│   └── service.yaml     # ClusterIP :80 → 8080
└── README.md
```
