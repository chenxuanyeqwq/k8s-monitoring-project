# 云服务器监控与告警 设计文档

> 日期：2026-08-25 ｜ 状态：待审阅 ｜ 部署目标：阿里云 ECS 8.217.195.115（Ubuntu + Docker Compose）

## 目标与范围

给已上云的 LNMP 留言板补上**监控与告警**,达成三个最终交付：

| # | 最终态 | 状态 |
|---|--------|------|
| 1 | 网站可留言（`http://8.217.195.115:8080`） | ✅ 已完成 |
| 2 | Grafana 看服务器 CPU/磁盘/内存（`http://8.217.195.115:3000`） | ⬅️ 本设计 |
| 3 | 飞书预检：网站可用性 + CPU 告警 + 每日内存报告 | ⬅️ 本设计 |

**部署形态**：云服务器 **Docker Compose**（与 LNMP 同机，非 k8s）。
**明确不做（后续扩展）**：应用层 exporter（nginx/mysql）、日志采集、HTTPS。

## 架构总览

```
云服务器 8.217.195.115
├─ 业务(已有)      compose LNMP  :8080 公网
├─ 监控(新增 compose)   docker-compose.monitoring.yml
│   ├─ node-exporter   :9100  内部   采集机器 CPU/内存/磁盘/网络
│   ├─ prometheus      :9090  内部   抓 node-exporter + 告警规则
│   ├─ alertmanager    :9093  内部   告警去重路由
│   ├─ feishu-bridge   :8080  内部   转飞书格式（复用 05 代码）
│   └─ grafana         :3000  公网   可视化（改默认密码）
└─ 宿主机 cron（新增）
    ├─ service_probe.py   每 5 分钟  探 :8080 可用性 → 飞书（从本地挪来）
    └─ memory_report.py   每天 9:00  读内存 → 飞书每日报告
```

## 端口与安全

| 端口 | 服务 | 公网 | 说明 |
|------|------|------|------|
| 8080 | LNMP | ✅ 已开 | 留言板 |
| **3000** | Grafana | ✅ 新增开 | 可视化入口 |
| 9100/9090/9093/8080 | 监控各服务 | ❌ 不开 | 仅 compose 内部互访 |

- **安全组只新增放行 3000**
- Grafana 默认密码 `admin/admin` → 改为环境变量注入的强密码
- 监控服务间用 compose 服务名互访，不暴露公网

## 组件设计

### node-exporter（采集机器资源）
- 镜像 `prom/node-exporter`
- `pid: host` + 挂载宿主机 `/proc`、`/sys` → 采集**云服务器真实** CPU/内存/磁盘/网络
- compose 网络内 `node-exporter:9100`，Prometheus 抓取

### prometheus（存储 + 告警规则）
- 镜像 `prom/prometheus`，配置挂载
- scrape：`node-exporter:9100`
- **告警规则**（rules.yml）：
  - `HighCPUUsage`：`100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80`，`for: 1m`
  - `HighDiskUsage`：`node_filesystem_avail_bytes / node_filesystem_size_bytes` 换算使用率 > 80%
- alertmanager 目标：`alertmanager:9093`

### alertmanager（告警去重路由）
- 镜像 `prom/alertmanager`
- route → receiver `feishu`，webhook 指向 `http://feishu-bridge:8080/alert`，`send_resolved: true`
- `group_by: ['alertname']`、`repeat_interval: 1h` 防轰炸

### feishu-bridge（格式转换，复用 05 代码）
- **复用 `05-feishu-bridge/bridge.py` + Dockerfile**，打成 compose 服务
- 作用：Alertmanager 原生 webhook 格式飞书不收 → 转成 `{"msg_type":"text",...}` 再推飞书
- 环境变量 `FEISHU_WEBHOOK` 从 `.env` 读取
- compose 网络内 `feishu-bridge:8080`，仅 Alertmanager 访问

### grafana（可视化）
- 镜像 `grafana/grafana`，provisioning 自动配
- datasource → `http://prometheus:9090`
- dashboard → 预置 JSON：CPU 使用率、内存使用率、磁盘使用率 三块面板
- 环境变量：`GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`（改掉默认）

## 宿主机 cron 脚本

### service_probe.py（黑盒，从本地挪到服务器常驻）
- 复用 `06-blackbox/service_probe.py`，目标改为 `http://localhost:8080`（服务器上探本地业务）
- 服务器上配 cron：`*/5 * * * * python3 /opt/k8s-project/.../service_probe.py`
- 好处：不再依赖本地电脑开关机，服务器常开 = 监控常开

### memory_report.py（每日内存报告，新增）
- 读取 `/proc/meminfo`（MemTotal/MemAvailable）→ 算已用/总量/使用率 → 推飞书
- cron：`0 9 * * * python3 /opt/k8s-project/.../memory_report.py`
- 复用 `.env` 的 `FEISHU_WEBHOOK`

## 交付物（文件清单）

```
07-cloud-monitoring/
├── docker-compose.monitoring.yml
├── prometheus/
│   ├── prometheus.yml
│   └── rules.yml
├── alertmanager/
│   └── alertmanager.yml
├── feishu-bridge/          (复用 05-feishu-bridge 代码)
├── grafana/
│   └── provisioning/
│       ├── datasources/datasource.yml
│       └── dashboards/node.json
├── memory_report.py
└── README.md
docs/云服务器监控部署手册.md
```

**部署方式**：监控栈配置进仓库；首次手动部署（scp + `docker compose -f docker-compose.monitoring.yml up -d`）；cron 一次性配置。CI/CD 对监控栈的接管列为后续优化。

## 验收标准

1. 公网打开 `http://8.217.195.115:3000`（新密码）→ 看到 CPU/内存/磁盘 三块面板、数据在动
2. 提交留言正常（业务不回归）
3. `stress` 压测 CPU → 约 5-6 分钟后飞书收到 `HighCPUUsage` 告警；回落收"已恢复"
4. 停 nginx → 黑盒 3 次探测 → 飞书告警；恢复 → 已恢复
5. 每天 9:00 收到内存报告
6. `docker ps` 看到 5 个监控容器 Running；安全组仅 3000/8080 公网

## 面试话术

> "我把监控也做上云了：node-exporter 采集云服务器 CPU/磁盘，Prometheus 存指标并跑告警规则（CPU>80% 持续1分钟），Alertmanager 去重路由，经自建 feishu-bridge 转格式推飞书；黑盒脚本放服务器每 5 分钟探网站可用性；再加一个 cron 每天 9 点推内存报告。Grafana 改默认密码、公网只开 3000。三层监控（机器/可用性）+ 定时报告，全链路真实跑通。"
