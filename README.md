# Docker + K8s 部署与监控

一个贯穿容器化 → 编排 → 监控 → 自动化的完整项目，现已**上云 + 全链路监控告警**。

> 📌 **当前版本 v3.2**：LNMP 上云公网可访问 + CI/CD 自动部署 + **云监控告警**（Grafana 看云服务器资源 + 飞书 CPU/网站/每日内存预检）+ 前端清爽版。v3.1 = 前端优化;v3.0 = 上云+CI/CD;v2.0 = 白盒+黑盒;v1.0 = 5 模块全链路。

## 模块总览

| 模块 | 目录 | 内容 | 验证结果 |
|---|---|---|---|
| 1. LNMP 容器化 | `01-lnmp/` | 自写 PHP 留言板，docker compose 编排 Nginx+PHP-FPM+MySQL | ✅ 中文无乱码、删容器数据不丢 |
| 2. k3s 部署 | `02-k3s/` | k3d 建集群，留言板部署到 k8s，滚动更新/回滚演练 | ✅ v1→v2→回滚全通过 |
| 3. 监控告警 | `03-monitoring/` | node_exporter→Prometheus→Alertmanager→飞书，Grafana 面板 | ✅ CPU 打满告警真实触发 |
| 4. 运维脚本 | `04-scripts/` | 磁盘告警 + 日志清理脚本 | ✅ 本地实测通过 |
| 5. 飞书桥 | `05-feishu-bridge/` | Alertmanager 告警 → 飞书消息 的转换服务（k8s Deployment） | ✅ 压测告警端到端到桥 |
| 6. 黑盒探测（**2.0**） | `06-blackbox/` | 从外网视角探测留言板入口，连续失败 3 次推飞书告警、恢复推已恢复（v3.2 起在云服务器常驻） | ✅ 停服实测告警+恢复 |
| 7. 云监控告警（**v3.2**） | `07-cloud-monitoring/` | 云服务器 compose 监控栈：node-exporter→Prometheus→Alertmanager→feishu-bridge→飞书 + Grafana 面板 + 每日内存报告 | ✅ 压测实测告警+恢复+内存报告推送 |

## 当前运行状态

```
LNMP 留言板（compose·云端） http://8.217.195.115:8080   ← 已上云，公网可访问
云服务器 Grafana（v3.2）     http://8.217.195.115:3000     ← 看云服务器 CPU/内存/磁盘
LNMP 留言板（compose·本地）  http://localhost:8080
k8s 留言板（Ingress）     curl -H "Host: guestbook.local" http://localhost:8081
本地 Grafana               curl -H "Host: grafana.local" http://localhost:8081  (admin/admin)
Prometheus(本地)           kubectl -n monitoring port-forward svc/prometheus 9090:9090
```

## 项目主线

> **自建小型生产环境**：Ubuntu → Docker 容器化 → k3s 多副本部署 → Prometheus/Grafana 监控 → Alertmanager 飞书告警 → 自动化脚本 → **上云 + CI/CD + 云监控告警**。

## 遇到的坑

1. Alpine 源连不上 → Dockerfile 构建卡死 → `sed` 换阿里云源
2. MySQL 导入中文乱码 → `SET NAMES utf8mb4;`
3. ghcr.io 被墙 → k3d 集群创建卡死 → DaoCloud ghcr 镜像 + `docker tag`
4. k3s containerd 不走 Docker 加速 → 挂 `registries.yaml` 指向 DaoCloud
5. kubeconfig host.docker.internal 连不上 → 改 127.0.0.1 + insecure-skip-tls-verify
6. containerd 拉镜像 DNS 抖动 → `k3d image import` 本地镜像（或用 `ctr -n k8s.io images import`）
7. **Alertmanager 原生 webhook 格式飞书不收**（`{"version":4,"alerts":[]}` vs 飞书要 `{"msg_type":...}`）→ 自建 `feishu-bridge` 转换层
8. **容器里 Python print 被块缓冲吞掉** → `kubectl logs` 看不到 → `sys.stdout.reconfigure(line_buffering=True)`
9. **NI Application WebServer 抢占 8080 端口（Windows）** → 8080 的所有 IPv4 地址被劫持（返回 `Embedthis-http` 404），nginx 只在 IPv6 `::1` 通，表现为"curl 通但 Python urllib 404" → `net stop NIApplicationWebServer` 释放端口
10. **Grafana provisioning 面板不加载**（v3.2）→ scp 上传文件 root 权限、容器非 root 读不了 → `chmod -R a+rX` + 重启 Grafana
11. **飞书 webhook 成功响应字段是 `StatusCode`**（非小写 `code`）→ 判断成功要兼容两个字段，否则成功被误判为失败

## 告警链路

```
CPU 压测 → node_exporter → Prometheus(规则 firing) → Alertmanager
    → feishu-bridge(转换格式) → 飞书群 webhook
```

- 本地(k8s)链路见 `03-monitoring/manifests/` + `05-feishu-bridge/manifests/`
- 云服务器(compose)链路见 `07-cloud-monitoring/`
- 真实飞书 webhook 统一填项目根 **`.env`**，**两端链路均已实测：飞书群真实收到告警** ✅

## v2.0 新增：黑盒监控（服务可用性探测）

白盒（Prometheus）看的是**资源指标**，黑盒直接回答"**服务通不通**"。`06-blackbox/service_probe.py` 从外网视角探测留言板入口：

```
cron 每 5 分钟 → service_probe.py
  └─ http://8.217.195.115:8080（云端公网入口，v3.2 起在云服务器常驻）
  └─ 连续失败 3 次 → 飞书告警；恢复 → 飞书"已恢复"；正常静默
```

- 核心是纯函数状态机 `apply_probe_result`，配 6 个 unittest（`python -m unittest test_service_probe`）
- 连续失败 3 次才告警（防误报）、`down` 后不重复轰炸、状态存 `service_probe_state.json`（已 gitignore）
- 失败原因区分上报：`连接拒绝` / `HTTP 503` / `HTTP 404`
- **实测**：停 nginx → 飞书收到失败告警；恢复 → "已恢复"

## v3.0 新增：上云 + CI/CD 自动部署

LNMP 留言板已部署到 **阿里云 ECS（Ubuntu 22.04，香港）**，公网可访问；接入 **GitHub Actions 流水线**，代码 push 到 main 自动构建并部署。

```
GitHub push → Actions(拉代码) → scp 上传 01-lnmp → SSH 执行 deploy.sh → 上线
```

- **公网地址**：`http://8.217.195.115:8080`（留言板）
- **关键文件**：`.github/workflows/deploy.yml`（CI/CD）、`01-lnmp/deploy.sh`（构建+部署+带重试自检）、`docs/云服务器部署手册.md`
- **安全**：服务器密码存 GitHub Secrets（不落库）；`.env` 由 gitignore 保护不入库

## v3.1/v3.2 新增：前端优化 + 云监控告警

### v3.1 前端清爽 SaaS 版
留言板前端整体重写（单文件 `01-lnmp/php/www/index.php`）：CSS 设计令牌、友好时间（PHP ISO + JS 相对时间）、提交 Toast（PRG 防重复提交）、精致空状态、移动端适配。安全防护（prepare + htmlspecialchars + PRG）全程保持。

### v3.2 云监控告警（compose 版监控栈上云）
在云服务器部署 `07-cloud-monitoring/`（与 LNMP 同机，compose 编排五件套）：

```
node-exporter → Prometheus(规则) → Alertmanager → feishu-bridge → 飞书
                └─→ Grafana(:3000) 可视化
```

- **Grafana**：`http://8.217.195.115:3000`，看云服务器 CPU/内存/磁盘三块面板
- **CPU 告警**：`HighCPUUsage`（5min 平均 >80% 持续 1min）→ 飞书；实测压测触发 + 恢复均收到 ✅
- **黑盒**：`06-blackbox` 挪到云服务器 cron 每 5 分钟探公网入口
- **每日内存报告**：`memory_report.py` cron 每天 9 点推飞书（实测 code=0 推送成功）
- **安全**：安全组仅放行 8080/3000；Grafana 改默认密码（fail-fast 必填）；监控内部端口不暴露公网
- 部署手册：`docs/云服务器监控部署手册.md`

## 飞书 webhook 配置

webhook 统一填在项目根 **`.env`**（`FEISHU_WEBHOOK=` 后面）：

- 本地(k8s)链路：`bash 03-monitoring/set_webhook.sh` 注入 bridge 的 ConfigMap
- 云服务器(compose)链路：把 `.env` 放到服务器 `/opt/k8s-project/.env`，`07-cloud-monitoring/docker-compose.monitoring.yml` 的 feishu-bridge 自动读取
- `04-scripts/disk_alert.py`、`06-blackbox/service_probe.py`、`07-cloud-monitoring/memory_report.py` 都会自动读 `.env`

## 各模块 README

- [模块1：LNMP](01-lnmp/README.md)
- [模块2：k3s 部署](02-k3s/README.md)
- [模块3：监控告警](03-monitoring/README.md)
- [模块4：运维脚本](04-scripts/README.md)
- [模块5：飞书桥](05-feishu-bridge/README.md)
- [模块6：黑盒探测（2.0）](06-blackbox/README.md)
- [模块7：云监控告警（v3.2）](07-cloud-monitoring/README.md)
