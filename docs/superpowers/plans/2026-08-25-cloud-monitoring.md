# 云服务器监控与告警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在阿里云 ECS(8.217.195.115)上部署 compose 版监控栈(node-exporter + Prometheus + Alertmanager + feishu-bridge + Grafana),加每日内存报告与黑盒常驻,达成"Grafana 看 CPU/磁盘 + 飞书预检(网站/CPU/每日内存)"。

**Architecture:** 新建 `07-cloud-monitoring/` 模块,一个 `docker-compose.monitoring.yml` 编排 5 个监控容器(node-exporter 用 `pid: host` + 挂载 /proc,/sys 采宿主机真实资源);Prometheus 抓 node-exporter 并跑告警规则,Alertmanager 去重路由到 feishu-bridge(复用 05 代码)转飞书;Grafana provisioning 自动配数据源与面板,仅 3000 对公网。宿主机 cron 跑 `service_probe.py`(黑盒,每 5 分钟)与 `memory_report.py`(每日内存)。

**Tech Stack:** Docker Compose、Prometheus 2.53、Grafana 11.2、Alertmanager、node-exporter、Python 3 标准库。

**Spec:** `docs/superpowers/specs/2026-08-25-cloud-monitoring-design.md`

## Global Constraints

- 新模块根目录:`07-cloud-monitoring/`,不动 `01-lnmp/` 现有业务
- 部署目标:阿里云 ECS `8.217.195.115`(Ubuntu 22.04 + Docker 29.7.2 + Compose v5.5.0)
- 公网只开 `3000`(Grafana)与已有的 `8080`;`9100/9090/9093/8080(bridge)` 全部内部互访,不映射公网
- 监控容器间用 compose 服务名互访(如 `node-exporter:9100`)
- feishu-bridge **复用** `05-feishu-bridge/bridge.py` + `Dockerfile`,监听 8080,`FEISHU_WEBHOOK` 从项目根 `.env` 读
- 飞书消息格式:`{"msg_type":"text","content":{"text":"..."}}`
- Grafana 默认密码必须改掉(不用 `admin/admin`),`GF_USERS_ALLOW_SIGN_UP: 'false'`
- 黑盒脚本在服务器上探 `http://localhost:8080`(本机业务),cron 每 5 分钟
- 每日内存报告 cron 每天 9:00

---

### Task 1: 监控栈配置文件(compose + prometheus + alertmanager + grafana provisioning)

**Files:**
- Create: `07-cloud-monitoring/docker-compose.monitoring.yml`
- Create: `07-cloud-monitoring/prometheus/prometheus.yml`
- Create: `07-cloud-monitoring/prometheus/rules.yml`
- Create: `07-cloud-monitoring/alertmanager/alertmanager.yml`
- Create: `07-cloud-monitoring/grafana/provisioning/datasources/datasource.yml`
- Create: `07-cloud-monitoring/grafana/provisioning/dashboards/node.json`

**Interfaces:**
- Produces: `docker-compose.monitoring.yml` 里服务名 `node-exporter` / `prometheus` / `alertmanager` / `feishu-bridge` / `grafana`,供 Task 2 的 bridge 构建、Task 3 的 cron 部署复用

- [ ] **Step 1: 创建 `07-cloud-monitoring/docker-compose.monitoring.yml`**

```yaml
# 云服务器监控栈 —— node-exporter + Prometheus + Alertmanager + feishu-bridge + Grafana
# 用法: docker compose -f docker-compose.monitoring.yml up -d --build
name: cloud-monitoring

services:
  node-exporter:
    image: prom/node-exporter:v1.8.2
    container_name: cm-node-exporter
    pid: host
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: cm-prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules.yml:/etc/prometheus/rules.yml:ro
      - prom_data:/prometheus
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: cm-alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    restart: unless-stopped

  feishu-bridge:
    build: ./feishu-bridge
    container_name: cm-feishu-bridge
    env_file: ../.env
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.2.0
    container_name: cm-grafana
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin123!}
      GF_USERS_ALLOW_SIGN_UP: 'false'
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - graf_data:/var/lib/grafana
    ports:
      - '3000:3000'
    restart: unless-stopped

volumes:
  prom_data:
  graf_data:
```

- [ ] **Step 2: 创建 `07-cloud-monitoring/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s
rule_files:
  - /etc/prometheus/rules.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
scrape_configs:
  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']
```

- [ ] **Step 3: 创建 `07-cloud-monitoring/prometheus/rules.yml`**

```yaml
groups:
  - name: cloud-alerts
    rules:
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "云服务器 CPU 使用率过高"
          description: "实例 {{ $labels.instance }} CPU 使用率超过 80%"
      - alert: HighDiskUsage
        expr: (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 > 80
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "云服务器磁盘使用率过高"
          description: "根分区使用率超过 80%"
```

- [ ] **Step 4: 创建 `07-cloud-monitoring/alertmanager/alertmanager.yml`**

```yaml
route:
  receiver: feishu
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
receivers:
  - name: feishu
    webhook_configs:
      - url: 'http://feishu-bridge:8080/alert'
        send_resolved: true
```

- [ ] **Step 5: 创建 `07-cloud-monitoring/grafana/provisioning/datasources/datasource.yml`**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    uid: prometheus
```

- [ ] **Step 6: 创建 `07-cloud-monitoring/grafana/provisioning/dashboards/node.json`**

```json
{
  "annotations": {"list": []},
  "editable": true,
  "panels": [
    {
      "id": 1, "type": "timeseries", "title": "CPU 使用率",
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {"expr": "100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)", "legendFormat": "{{instance}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100}, "overrides": []}
    },
    {
      "id": 2, "type": "timeseries", "title": "内存使用率",
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {"expr": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100", "legendFormat": "{{instance}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100}, "overrides": []}
    },
    {
      "id": 3, "type": "timeseries", "title": "根分区磁盘使用率",
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {"expr": "(1 - node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"}) * 100", "legendFormat": "{{instance}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100}, "overrides": []}
    }
  ],
  "refresh": "10s",
  "schemaVersion": 39,
  "tags": ["cloud"],
  "time": {"from": "now-1h", "to": "now"},
  "timepicker": {},
  "timezone": "browser",
  "title": "云服务器监控",
  "uid": "cloud-node",
  "version": 1
}
```

- [ ] **Step 7: 验证 compose 配置合法(有 docker 时)**

Run: `docker compose -f 07-cloud-monitoring/docker-compose.monitoring.yml config`
Expected: 输出解析后的完整配置,无报错;`name: cloud-monitoring` 与 5 个服务均在
注:若报 `build context ... feishu-bridge 不存在`,属正常 —— 该目录由 Task 2 创建,等 Task 2 完成后再重跑本校验即可。

- [ ] **Step 8: 提交**

```bash
git add 07-cloud-monitoring/
git commit -m "feat: 云监控栈配置(compose+prometheus+alertmanager+grafana provisioning)"
```

---

### Task 2: feishu-bridge 复用进 07-cloud-monitoring

**Files:**
- Create: `07-cloud-monitoring/feishu-bridge/bridge.py`(复制自 `05-feishu-bridge/bridge.py`)
- Create: `07-cloud-monitoring/feishu-bridge/Dockerfile`(复制自 `05-feishu-bridge/Dockerfile`)

**Interfaces:**
- Consumes: Task 1 的 `docker-compose.monitoring.yml` 里 `feishu-bridge` 服务 `build: ./feishu-bridge`、`env_file: ../.env`
- Produces: 监听 `0.0.0.0:8080`,`POST /alert` 收 Alertmanager webhook → 转飞书 `{"msg_type":"text",...}` → 推 `FEISHU_WEBHOOK`

- [ ] **Step 1: 复制 bridge.py**

把 `E:\dev\k8s-project\05-feishu-bridge\bridge.py` 原样复制到 `07-cloud-monitoring/feishu-bridge/bridge.py`(内容不用改:监听 8080、读 `FEISHU_WEBHOOK` env)

- [ ] **Step 2: 复制 Dockerfile**

把 `E:\dev\k8s-project\05-feishu-bridge\Dockerfile` 原样复制到 `07-cloud-monitoring/feishu-bridge/Dockerfile`

- [ ] **Step 3: 验证能构建(有 docker 时)**

Run: `cd 07-cloud-monitoring && docker build -t cm-feishu-bridge ./feishu-bridge`
Expected: 构建成功,镜像名 `cm-feishu-bridge`

- [ ] **Step 4: 提交**

```bash
git add 07-cloud-monitoring/feishu-bridge/
git commit -m "feat: 复用 feishu-bridge 进云监控栈"
```

---

### Task 3: 每日内存报告 memory_report.py

**Files:**
- Create: `07-cloud-monitoring/memory_report.py`
- Create: `07-cloud-monitoring/test_memory_report.py`

**Interfaces:**
- Produces: `parse_meminfo(text) -> dict`、`mem_report(mem) -> dict{total_gb, used_gb, avail_gb, pct}`、`main()`(读 /proc/meminfo → 组飞书文本 → 推 webhook)

- [ ] **Step 1: 写失败测试**

```python
# test_memory_report.py
import unittest
from memory_report import parse_meminfo, mem_report

SAMPLE = "MemTotal:       2048000 kB\nMemFree:        102400 kB\nMemAvailable:    819200 kB\n"

class TestMem(unittest.TestCase):
    def test_parse_meminfo(self):
        m = parse_meminfo(SAMPLE)
        self.assertEqual(m["MemTotal"], 2048000 * 1024)
        self.assertEqual(m["MemAvailable"], 819200 * 1024)

    def test_mem_report_pct(self):
        r = mem_report(parse_meminfo(SAMPLE))
        # used = total - avail = (2048-819.2)MB = 1228.8MB
        self.assertAlmostEqual(r["used_gb"], 1.2, delta=0.01)
        self.assertAlmostEqual(r["pct"], 60.0, delta=0.1)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd 07-cloud-monitoring && python -m unittest test_memory_report -v`
Expected: FAIL(ImportError: memory_report not defined)

- [ ] **Step 3: 写实现**

```python
#!/usr/bin/env python3
"""云服务器每日内存报告 —— 读 /proc/meminfo,把内存概况推送到飞书。
用法: python memory_report.py   (建议 cron 每天 9:00 调用)
"""
import json
import os
import urllib.request


def parse_meminfo(text):
    """解析 /proc/meminfo 文本,返回 {键: 字节数}。值单位 kB 时换算成 bytes。"""
    result = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, rest = line.split(':', 1)
        parts = rest.strip().split()
        if not parts:
            continue
        value = int(parts[0])
        if len(parts) > 1 and parts[1] == 'kB':
            value *= 1024
        result[key] = value
    return result


def mem_report(mem):
    """由 parse_meminfo 的结果计算内存概况。"""
    total = mem['MemTotal']
    avail = mem.get('MemAvailable', mem.get('MemFree', 0))
    used = total - avail
    pct = used / total * 100
    return {
        "total_gb": round(total / 1024 ** 3, 2),
        "used_gb": round(used / 1024 ** 3, 2),
        "avail_gb": round(avail / 1024 ** 3, 2),
        "pct": round(pct, 1),
    }


def load_webhook():
    hook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if hook:
        return hook
    here = os.path.dirname(os.path.abspath(__file__))
    for env_path in (os.path.join(here, "..", ".env"), os.path.join(here, ".env")):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FEISHU_WEBHOOK="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
        except OSError:
            continue
    return ""


def send_feishu(text, webhook):
    payload = {"msg_type": "text", "content": {"text": text}}
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def main():
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            mem = parse_meminfo(f.read())
    except OSError:
        print("无法读取 /proc/meminfo(非 Linux?)")
        return
    r = mem_report(mem)
    text = "【云服务器每日内存报告】\n总量: {} GB\n已用: {} GB\n可用: {} GB\n使用率: {}%".format(
        r["total_gb"], r["used_gb"], r["avail_gb"], r["pct"])
    webhook = load_webhook()
    if not webhook:
        print(text)
        print("(未配置 FEISHU_WEBHOOK,仅打印)")
        return
    code = send_feishu(text, webhook)
    print("已推送飞书 (HTTP %d)\n%s" % (code, text))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd 07-cloud-monitoring && python -m unittest test_memory_report -v`
Expected: 2 tests OK

- [ ] **Step 5: 提交**

```bash
git add 07-cloud-monitoring/memory_report.py 07-cloud-monitoring/test_memory_report.py
git commit -m "feat: 云服务器每日内存报告脚本(含单测)"
```

---

### Task 4: 部署手册

**Files:**
- Create: `docs/云服务器监控部署手册.md`

**Interfaces:**
- Consumes: Task 1/2/3 的全部文件;复用 `06-blackbox/service_probe.py`;依赖 `01-lnmp` 已在服务器运行、`.env` 在服务器 `/opt/k8s-project/.env`

- [ ] **Step 1: 写手册(内容如下,写入文件)**

```markdown
# 云服务器监控部署手册(compose 版监控栈 + 飞书预检)

目标:在 8.217.195.115 上搭 Grafana(:3000 看 CPU/磁盘)+ 飞书告警(CPU/网站)+ 每日内存报告。

## 0. 前置(已完成)
- LNMP 留言板已运行(:8080),`/opt/k8s-project/` 已有项目代码
- 服务器 `/opt/k8s-project/.env` 已有 `FEISHU_WEBHOOK`

## 1. 上传监控模块
本地 PowerShell:
```powershell
scp -r E:\dev\k8s-project\07-cloud-monitoring root@8.217.195.115:/opt/k8s-project/
```

## 2. 配置 Grafana 密码(改默认)
服务器上编辑 `/opt/k8s-project/07-cloud-monitoring/docker-compose.monitoring.yml`:
把 `GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin123!}` 里的默认值改成你自己的强密码(或用环境变量覆盖)。

## 3. 启动监控栈
```bash
cd /opt/k8s-project/07-cloud-monitoring
docker compose -f docker-compose.monitoring.yml up -d --build
docker compose -f docker-compose.monitoring.yml ps   # 5 个容器 Running
```

## 4. 安全组放行 3000
阿里云控制台 → ECS 安全组 → 入方向 → 添加 TCP 3000(0.0.0.0/0)

## 5. 验证 Grafana
浏览器打开 `http://8.217.195.115:3000`,用你设的密码登录 → 看到"云服务器监控"面板(CPU/内存/磁盘三块)。

## 6. 黑盒脚本常驻(网站可用性)
上传 `06-blackbox` 到服务器(若未传):
```powershell
scp -r E:\dev\k8s-project\06-blackbox root@8.217.195.115:/opt/k8s-project/
```
服务器上配 cron(编辑 `service_probe.py` 目标已为 localhost:8080 或改公网 IP):
```bash
crontab -e
# 加一行:
*/5 * * * * cd /opt/k8s-project/06-blackbox && python3 service_probe.py >> /var/log/service_probe.log 2>&1
```

## 7. 每日内存报告
```bash
cd /opt/k8s-project/07-cloud-monitoring
crontab -e
# 加一行:
0 9 * * * cd /opt/k8s-project/07-cloud-monitoring && python3 memory_report.py >> /var/log/memory_report.log 2>&1
```

## 8. 验收
- Grafana 打开,三块面板数据在动
- `stress` 压 CPU → 5-6 分钟后飞书收到 HighCPUUsage
- 停 nginx → 黑盒 3 次 → 飞书告警
- 次日 9 点收到内存报告

## 常见问题
| 症状 | 处理 |
|------|------|
| Grafana 打不开 | 安全组 3000 没开 / 容器没起来(`docker compose ps`) |
| 飞书没告警 | 检查 `.env` 的 webhook、`docker logs cm-feishu-bridge` |
| 面板无数据 | `docker logs cm-prometheus` 看是否抓 node-exporter:9100 |
```

- [ ] **Step 2: 提交**

```bash
git add docs/云服务器监控部署手册.md
git commit -m "docs: 云服务器监控部署手册"
```

---

### Task 5: 部署到云服务器并验收(需用户在服务器上执行)

**Files:** 无新增;执行 Task 1-4 产物的部署

- [ ] **Step 1: 上传并启动**(服务器执行,见手册 1-3 节)
- [ ] **Step 2: 放行安全组 3000**(阿里云控制台,见手册 4 节)
- [ ] **Step 3: 验证 Grafana**(见手册 5 节;把登录后看到的画面/报错发回)
- [ ] **Step 4: 配 cron**(黑盒 + 每日内存,见手册 6-7 节)
- [ ] **Step 5: 端到端验收**(见手册 8 节;压测 CPU 触发告警,飞书实收)
