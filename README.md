# Docker + K8s 部署与监控

一个贯穿容器化 → 编排 → 监控 → 自动化的完整项目，5 个模块层层递进。

## 模块总览

| 模块 | 目录 | 内容 | 验证结果 |
|---|---|---|---|
| 1. LNMP 容器化 | `01-lnmp/` | 自写 PHP 留言板，docker compose 编排 Nginx+PHP-FPM+MySQL | ✅ 中文无乱码、删容器数据不丢 |
| 2. k3s 部署 | `02-k3s/` | k3d 建集群，留言板部署到 k8s，滚动更新/回滚演练 | ✅ v1→v2→回滚全通过 |
| 3. 监控告警 | `03-monitoring/` | node_exporter→Prometheus→Alertmanager→飞书，Grafana 面板 | ✅ CPU 打满告警真实触发 |
| 4. 运维脚本 | `04-scripts/` | 磁盘告警 + 日志清理脚本 | ✅ 本地实测通过 |
| 5. 飞书桥 | `05-feishu-bridge/` | Alertmanager 告警 → 飞书消息 的转换服务（k8s Deployment） | ✅ 压测告警端到端到桥 |

## 当前运行状态

```
LNMP 留言板（compose）    http://localhost:8080
k8s 留言板（Ingress）     curl -H "Host: guestbook.local" http://localhost:8081
Grafana                   curl -H "Host: grafana.local" http://localhost:8081  (admin/admin)
Prometheus                kubectl -n monitoring port-forward svc/prometheus 9090:9090
```

## 项目主线

> **自建小型生产环境**：Ubuntu → Docker 容器化 → k3s 多副本部署 → Prometheus/Grafana 监控 → Alertmanager 飞书告警 → 自动化脚本。

## 遇到的坑

1. Alpine 源连不上 → Dockerfile 构建卡死 → `sed` 换阿里云源
2. MySQL 导入中文乱码 → `SET NAMES utf8mb4;`
3. ghcr.io 被墙 → k3d 集群创建卡死 → DaoCloud ghcr 镜像 + `docker tag`
4. k3s containerd 不走 Docker 加速 → 挂 `registries.yaml` 指向 DaoCloud
5. kubeconfig host.docker.internal 连不上 → 改 127.0.0.1 + insecure-skip-tls-verify
6. containerd 拉镜像 DNS 抖动 → `k3d image import` 本地镜像（或用 `ctr -n k8s.io images import`）
7. **Alertmanager 原生 webhook 格式飞书不收**（`{"version":4,"alerts":[]}` vs 飞书要 `{"msg_type":...}`）→ 自建 `feishu-bridge` 转换层
8. **容器里 Python print 被块缓冲吞掉** → `kubectl logs` 看不到 → `sys.stdout.reconfigure(line_buffering=True)`

## 告警链路

```
CPU 压测 → node_exporter → Prometheus(规则 firing) → Alertmanager
    → feishu-bridge(转换格式) → 飞书群 webhook
```

- `03-monitoring/manifests/alertmanager.yaml` 的 receiver 固定指向 `http://feishu-bridge.monitoring.svc.cluster.local/alert`
- 真实飞书 webhook 统一填项目根 **`.env`**，`set_webhook.sh` 自动注入 bridge 的 ConfigMap
- 链路已端到端验证，**真实飞书推送实测通过（HTTP 200，飞书群已收到告警）** ✅

## 飞书 webhook 配置

webhook 统一填在项目根 **`.env`**（`FEISHU_WEBHOOK=` 后面），改完执行：

```bash
bash 03-monitoring/set_webhook.sh        # 注入 feishu-bridge 的 ConfigMap
kubectl -n monitoring apply -f 05-feishu-bridge/manifests/configmap.yaml
kubectl -n monitoring rollout restart deployment/feishu-bridge
```

`04-scripts/disk_alert.py`（直接发飞书）和 `05-feishu-bridge/bridge.py` 都会自动读 `.env`。

## 各模块 README

- [模块1：LNMP](01-lnmp/README.md)
- [模块2：k3s 部署](02-k3s/README.md)
- [模块3：监控告警](03-monitoring/README.md)
- [模块4：运维脚本](04-scripts/README.md)
- [模块5：飞书桥](05-feishu-bridge/README.md)
