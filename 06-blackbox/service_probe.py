#!/usr/bin/env python3
"""
服务可用性探测脚本（黑盒监控）
用途：从宿主机外网视角探测两个留言板入口是否"通"。挂了推飞书告警，恢复推"已恢复"。
用法：
  python service_probe.py      # 跑一次探测（建议 cron / Windows 任务计划每 5 分钟调用）
环境变量：
  PROBE_FAIL_THRESHOLD   连续失败多少次判定"挂了"，默认 3
  FEISHU_WEBHOOK         飞书机器人 webhook URL（不配则不推送，只打印）
状态文件：
  脚本同目录下 service_probe_state.json —— 记录每个目标的失败计数与当前状态（up/down）
依赖：Python 3 标准库（urllib / json / os / sys / time），无需第三方库。
"""
import os
import json
import time
import urllib.request
from urllib.error import HTTPError, URLError


# 探测目标：每个目标独立判断、独立告警
# v3.6：主目标为云端 HTTPS 入口(阿里云 ECS)，从外部视角探测服务可用性
TARGETS = [
    {"name": "云端LNMP留言板", "url": "https://www.fchen.xyz", "headers": {}},
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_probe_state.json")


def probe(url, headers, timeout=10):
    """探测 URL。HTTP 200 视为可达。返回 (ok: bool, reason: str)。"""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True, ""
            return False, "HTTP %s" % resp.status
    except HTTPError as e:
        return False, "HTTP %s" % e.code
    except URLError as e:
        return False, "连接失败: %s" % getattr(e, "reason", e)
    except Exception as e:
        return False, "异常: %s" % e


def apply_probe_result(rec, ok, reason, threshold):
    """状态机核心（纯函数，可单测）。
    rec: {fail_count:int, status:'up'|'down'}
    返回 (new_rec, event)，event ∈ {'ok','warn','alert','recover'}。
    """
    new = dict(rec)
    if ok:
        if rec.get("status") == "down":
            new["status"] = "up"
            new["fail_count"] = 0
            return new, "recover"
        new["fail_count"] = 0
        return new, "ok"
    new["fail_count"] = rec.get("fail_count", 0) + 1
    if new["fail_count"] > threshold and rec.get("status") != "down":  # 临时改坏:>= 变 >,测试应红
        new["status"] = "down"
        return new, "alert"
    return new, "warn"


def send_feishu(text, webhook):
    """推飞书文本消息，返回 HTTP 状态码。"""
    payload = {"msg_type": "text", "content": {"text": text}}
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def load_webhook():
    """环境变量优先，其次读项目根 .env（复用 disk_alert.py 逻辑）。"""
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


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    threshold = int(os.getenv("PROBE_FAIL_THRESHOLD", "3"))
    webhook = load_webhook()
    state = load_state()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    for t in TARGETS:
        name = t["name"]
        ok, reason = probe(t["url"], t["headers"])
        rec = state.get(name, {"fail_count": 0, "status": "up"})
        new_rec, event = apply_probe_result(rec, ok, reason, threshold)
        state[name] = new_rec

        if event == "ok":
            print("[INFO] %s 正常 (HTTP 200)" % name)
        elif event == "warn":
            print("[WARN] %s 第 %d 次失败 (%s)" % (name, new_rec["fail_count"], reason))
        elif event == "alert":
            text = "[服务探测][失败] %s 不可达\n目标: %s\n失败原因: %s\n连续失败: %d 次\n时间: %s" % (
                name, t["url"], reason, new_rec["fail_count"], now)
            print("[ALERT] %s 不可达 (%s)" % (name, reason))
            push_feishu(text, webhook)
        elif event == "recover":
            text = "[服务探测][已恢复] %s\n目标: %s\n时间: %s" % (name, t["url"], now)
            print("[RECOVER] %s 已恢复" % name)
            push_feishu(text, webhook)

    save_state_safe(state)


def push_feishu(text, webhook):
    """推送飞书；webhook 为空或推送失败都不崩脚本（记日志继续）。"""
    if not webhook:
        print("  (未配置 FEISHU_WEBHOOK，跳过推送)")
        return
    try:
        status = send_feishu(text, webhook)
        print("  已推送飞书 (HTTP %d)" % status)
    except Exception as e:
        print("  [ERROR] 飞书推送失败（不影响探测）：%s" % e)


def save_state_safe(state):
    """写状态文件；失败只记日志，不让脚本崩溃。"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("[ERROR] 状态文件写入失败：%s" % e)


if __name__ == "__main__":
    main()
