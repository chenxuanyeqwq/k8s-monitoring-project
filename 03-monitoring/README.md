# 模块3：Prometheus + Grafana 监控与告警（03-monitoring）

在 k3s 上自建完整监控告警栈：**node_exporter → Prometheus → Alertmanager → 飞书**。

## 数据流

```
node_exporter (DaemonSet, 每节点 :9100)
      │  抓取指标
      ▼
Prometheus (:9090) ── 规则评估(CPU>80%持续1min) ──► Alertmanager (:9093)
      │                                                  │ webhook
      ▼                                                  ▼
   Grafana (:3000) 可视化大屏              feishu-bridge (转格式) → 飞书群
```

## 快速复现

```bash
# 1. 导入镜像（本地已拉好，含 quay.io 的 node_exporter）
k3d image import prom/prometheus:v2.53.0 prom/alertmanager:v0.27.0 \
  grafana/grafana:11.2.0 quay.io/prometheus/node-exporter:v1.8.2 -c k8s-project

# 2. 部署
kubectl apply -f manifests/namespace.yaml
kubectl apply -f manifests/

# 3. 访问
curl -H "Host: grafana.local" http://localhost:8081   # Grafana, admin/admin

# 4. 触发告警（打满CPU）
kubectl -n guestbook run stress --image=guestbook:v1 --restart=Never --command \
  -- sh -c 'for i in $(seq 1 $(kubectl get nodes -o jsonpath="{.items[0].status.capacity.cpu}")); do (while :; do :; done) & done; sleep 600'

# 5. 查看告警
kubectl -n monitoring exec deploy/prometheus -- wget -qO- 'http://localhost:9090/api/v1/alerts'
kubectl -n monitoring exec deploy/alertmanager -- wget -qO- 'http://localhost:9093/api/v2/alerts'
```

## 目录结构

```
03-monitoring/manifests/
├── namespace.yaml        # monitoring 命名空间
├── node-exporter.yaml    # DaemonSet: 采集节点指标(hostNetwork+hostPID)
├── prometheus.yaml       # ConfigMap(抓取+规则) + Deployment + Service
├── alertmanager.yaml     # ConfigMap(飞书webhook) + Deployment + Service
└── grafana.yaml          # 数据源+面板 provisioning + Deployment + Service + Ingress
```

## 验证结果（2026-08-19）

- [x] Prometheus 抓取 2 个目标全 up（prometheus 自身 + node_exporter），node_cpu 采集 160 条
- [x] 告警规则 HighCPUUsage 加载，表达式 CPU 使用率实时计算正常
- [x] CPU 压测打满（kubectl top 106%）→ 表达式 99.996% → **告警 firing**
- [x] Alertmanager 将告警路由到 feishu 接收端
- [x] Grafana 自动 provisioning 数据源 + Node 监控面板（CPU/内存），页面可访问

## ⚠️ 待办：飞书 webhook

> **架构更新（2026-08-20）**：Alertmanager 原生 webhook 格式飞书不收，receiver 已改为指向
> `feishu-bridge` 服务（见 `../05-feishu-bridge/`）。链路：`Alertmanager → feishu-bridge → 飞书群`。
> 告警从 Prometheus 触发到 bridge 的端到端已验证，只差 bridge 里填真实 URL。

webhook URL 统一填在**项目根 `.env`**（`FEISHU_WEBHOOK=` 后面），然后注入 bridge 的 ConfigMap：

```bash
bash set_webhook.sh
kubectl -n monitoring apply -f ../05-feishu-bridge/manifests/configmap.yaml
kubectl -n monitoring rollout restart deployment/feishu-bridge
```

也可以直接传 URL：`bash set_webhook.sh https://open.feishu.cn/...`。

## 面试一句话

> "我在 k3s 上自建了 Prometheus + Grafana + Alertmanager 监控栈：node_exporter 采节点指标，Prometheus 写告警规则（CPU>80% 持续1分钟），Alertmanager 通过 webhook 对接飞书机器人。实测用压测脚本打满 CPU，确认告警真实触发并路由到飞书接收端，同时配好了 Grafana 自动注入的监控面板。"
