# 模块4：运维自动化脚本（04-scripts）

两个可上生产的小脚本，演示"把重复运维工作写成脚本"的能力。

## disk_alert.py — 磁盘空间告警

检查挂载点使用率，超阈值向飞书 webhook 推送告警。

```bash
# 检查根分区
python3 disk_alert.py

# 检查多个挂载点
python3 disk_alert.py / /data

# 自定义阈值 + 配置飞书 webhook
DISK_THRESHOLD=85 FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/你的KEY python3 disk_alert.py /
```

**crontab 定时（每天 9 点检查一次）：**
```
0 9 * * * cd /opt/scripts && DISK_THRESHOLD=85 FEISHU_WEBHOOK=xxx python3 disk_alert.py / >> /var/log/disk_alert.log 2>&1
```

## log_cleanup.sh — 日志清理

删除指定目录下 N 天前的 `.log` 文件，防止磁盘被日志占满。

```bash
./log_cleanup.sh                 # 清 /var/log 下 7 天前日志
./log_cleanup.sh /app/logs 30    # 清 /app/logs 下 30 天前日志
```

**crontab 定时（每天凌晨 2 点）：**
```
0 2 * * * /opt/scripts/log_cleanup.sh /app/logs 7
```

## service_probe.py — 服务可用性黑盒探测

从宿主机外网视角探测两个留言板入口是否"通"（黑盒监控，补 Prometheus 白盒资源监控的盲区）：
连续失败 3 次判定"挂了"推飞书告警，恢复推"已恢复"，正常静默不刷屏。

```bash
# 手动跑一次
python service_probe.py

# 连续失败阈值可配（默认 3）
PROBE_FAIL_THRESHOLD=3 python service_probe.py
```

**crontab 定时（每 5 分钟一次）：**
```
*/5 * * * * cd /e/dev/k8s-project/04-scripts && python service_probe.py >> /var/log/service_probe.log 2>&1
```

探测目标：
- `http://localhost:8080` → LNMP 留言板
- `http://localhost:8081` + `Host: guestbook.local` → k8s 留言板（Ingress→Service→Pod 全链路）

状态记录在脚本同目录 `service_probe_state.json`（已 gitignore），实现"连续失败计数 + 恢复判断"。

## 面试一句话

> "我写了三个运维脚本：磁盘告警脚本用 Python 标准库检查挂载点使用率、超阈值通过飞书 webhook 推送告警；日志清理脚本用 find 定时清理过期日志；还有个黑盒探测脚本，从外网视角定时探测留言板两个入口通不通，挂了推飞书、恢复推已恢复。都配好了 crontab 定时任务。"
