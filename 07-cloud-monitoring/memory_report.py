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
