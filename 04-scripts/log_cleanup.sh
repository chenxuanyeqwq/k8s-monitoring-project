#!/bin/bash
# 日志清理脚本：删除指定目录下 N 天前的 .log 文件，防止磁盘被日志占满。
# 用法：./log_cleanup.sh [日志目录] [保留天数]
# 默认：目录 /var/log，保留 7 天
#
# 常见用法：
#   ./log_cleanup.sh                      # 清理 /var/log 下 7 天前的日志
#   ./log_cleanup.sh /app/logs 30         # 清理 /app/logs 下 30 天前的日志
#   crontab 定时（每天凌晨 2 点）：
#   0 2 * * * /opt/scripts/log_cleanup.sh /app/logs 7

LOG_DIR="${1:-/var/log}"
DAYS="${2:-7}"

# 目录不存在就报错退出
if [ ! -d "$LOG_DIR" ]; then
    echo "[ERROR] 目录不存在: $LOG_DIR" >&2
    exit 1
fi

echo "[INFO] 开始清理 $LOG_DIR 下超过 ${DAYS} 天的 .log 文件"
# -print 先打印被删文件，-delete 删除；-mtime +N 表示 N 天前修改过的
find "$LOG_DIR" -type f -name "*.log" -mtime +"$DAYS" -print -delete
echo "[INFO] 清理完成"
