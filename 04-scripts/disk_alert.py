#!/usr/bin/env python3
"""
磁盘空间告警脚本
用途：检查挂载点使用率，超阈值向飞书 webhook 推送告警。
用法：
  python3 disk_alert.py                    # 检查根分区
  python3 disk_alert.py / /data            # 检查多个挂载点
环境变量：
  DISK_THRESHOLD  告警阈值(%)，默认 80
  FEISHU_WEBHOOK  飞书机器人 webhook URL（不配则不推送，只打印）
webhook 获取优先级：环境变量 FEISHU_WEBHOOK → 项目根 .env（04-scripts/ 的上一级）
依赖：Python 3 标准库（shutil / urllib），无需第三方库。
"""
import os
import sys
import shutil

# 复用项目根的 feishu_send 共享模块(带限流退避重试,统一检查业务 code)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feishu_send import load_webhook, send_feishu


def get_usage_pct(path: str) -> float:
    """返回挂载点使用率百分比"""
    usage = shutil.disk_usage(path)
    return usage.used / usage.total * 100


def main() -> None:
    threshold = float(os.getenv("DISK_THRESHOLD", "80"))
    webhook = load_webhook()
    paths = sys.argv[1:] or ["/"]  # 没传参数就检查根分区

    for path in paths:
        try:
            pct = get_usage_pct(path)
            print(f"[INFO] {path} 使用率 {pct:.1f}% (阈值 {threshold:.0f}%)")

            if pct <= threshold:
                continue

            # 注意：别用 emoji，Windows GBK 控制台打印会报错（Linux 无此问题）
            alert_text = f"[磁盘告警] {path} 使用率 {pct:.1f}% 超过阈值 {threshold:.0f}%"
            if webhook:
                try:
                    code = send_feishu(alert_text, webhook)
                    print(f"[ALERT] 已推送飞书: {alert_text} (code={code})")
                except Exception as e:
                    print(f"[ALERT] 飞书推送失败(不中断检查): {e}")
            else:
                print(f"[ALERT] {alert_text}（未配置 FEISHU_WEBHOOK，跳过推送）")
        except Exception as e:
            print(f"[ERROR] {path}: {e}")


if __name__ == "__main__":
    main()
