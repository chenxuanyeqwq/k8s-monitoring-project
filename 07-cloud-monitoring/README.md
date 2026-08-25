# 模块7：云监控告警（v3.2）—— compose 版监控栈上云

> 在阿里云 ECS（8.217.195.115）上给 LNMP 留言板补上的**机器级监控 + 飞书告警**。
> 与本地 k8s 版监控（03-monitoring）同源思路，但部署形态是 **Docker Compose**（五件套）。

## 架构

```
云服务器 8.217.195.115
├─ 业务：compose LNMP 留言板 :8080（已有）
└─ 监控（本模块，docker-compose.monitoring.yml）
    ├─ node-exporter   :9100  内部  采集云服务器 CPU/内存/磁盘/网络（pid:host + 挂载 /proc /sys）
    ├─ prometheus      :9090  内部  抓 node-exporter + 告警规则（HighCPUUsage / HighDiskUsage）
    ├─ alertmanager    :9093  内部  去重路由 → feishu-bridge
    ├─ feishu-bridge   :8080  内部  复用 05 代码，Alertmanager 格式 → 飞书格式
    └─ grafana         :3000  公网  可视化（CPU/内存/磁盘三块面板，provisioning 自动配）
└─ 宿主机 cron
    ├─ service_probe.py   每 5 分钟  黑盒探公网入口（06-blackbox，挪来常驻）
    └─ memory_report.py   每天 9:00  读 /proc/meminfo 推飞书每日内存报告
```

## 启动（云服务器上）

```bash
# 1. 上传本目录 + 确保项目根有 .env（含 FEISHU_WEBHOOK）
scp -r 07-cloud-monitoring root@<服务器>:/opt/k8s-project/

# 2. 设置 Grafana 密码（必填，fail-fast）
echo 'GRAFANA_ADMIN_PASSWORD=你的强密码' > /opt/k8s-project/07-cloud-monitoring/.env

# 3. 启动
cd /opt/k8s-project/07-cloud-monitoring
docker compose -f docker-compose.monitoring.yml up -d --build
docker compose -f docker-compose.monitoring.yml ps
```

## 访问与验证

| 入口 | 说明 |
|------|------|
| `http://8.217.195.115:3000` | Grafana，看云服务器 CPU/内存/磁盘面板 |
| 飞书 | CPU 告警（HighCPUUsage >80% 持续1min）、黑盒失败告警、每日内存报告 |

**全链路实测（2026-08-25）：**
- `stress --cpu 2` 压测 → Prometheus HighCPUUsage firing → Alertmanager → feishu-bridge → **飞书实收告警 + 恢复** ✅
- 黑盒探公网入口 → HTTP 200 正常
- 每日内存报告 → 飞书 code=0 推送成功 ✅

## 关键点

- **两个 `.env` 别混**：`/opt/k8s-project/.env`（FEISHU_WEBHOOK，feishu-bridge 用）+ `07-cloud-monitoring/.env`（GRAFANA_ADMIN_PASSWORD，compose 插值用）
- **权限坑**：scp 上传后 Grafana 面板不加载 → `chmod -R a+rX grafana/` + 重启 cm-grafana
- **飞书响应字段**：成功响应可能用 `StatusCode` 或 `code`，代码已兼容两者
- **告警规则**：`prometheus/rules.yml`（CPU>80% / 根分区磁盘>80%，均 `for: 1m` 防抖动）

## 测试

```bash
cd 07-cloud-monitoring && python -m unittest test_memory_report -v   # 内存报告纯函数 2 例
```
