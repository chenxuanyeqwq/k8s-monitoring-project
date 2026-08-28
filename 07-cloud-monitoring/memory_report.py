#!/usr/bin/env python3
"""云服务器每日内存报告 —— 读 /proc/meminfo,把内存概况推送到飞书。
用法: python memory_report.py   (建议 cron 每天 9:13 调用,避开飞书整点限流高峰)
"""
import os
import sys
import time

# 复用项目根的 feishu_send 共享模块(带限流退避重试,统一检查业务 code)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feishu_send import load_webhook, send_feishu


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
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if not webhook:
        print("[%s] %s\n(未配置 FEISHU_WEBHOOK,仅打印)" % (now, text))
        return
    try:
        code = send_feishu(text, webhook)
        print("[%s] 已推送飞书 (code=%d)\n%s" % (now, code, text))
    except Exception as e:
        print("[%s] 飞书推送失败: %s\n%s" % (now, e, text))


if __name__ == "__main__":
    main()
