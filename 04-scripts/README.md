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
``
