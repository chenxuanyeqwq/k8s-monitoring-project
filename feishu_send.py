#!/usr/bin/env python3
"""飞书 webhook 统一发送模块 —— 带限流退避重试。

集中管理各脚本的 FEISHU_WEBHOOK 加载与发送，统一检查飞书业务 code，
避免 load_webhook / send_feishu 在 memory_report / service_probe / disk_alert
三处重复实现（此前已三份复制，且后两个只看 HTTP 状态、漏检飞书业务 code）。

背景（2026-08-28）：每日内存报告 09:00 整点撞飞书租户级限流(code=11232)，
消息静默丢失。11232 属于可重试错误 → 这里统一做指数退避重试。

用法（各脚本顶部）：
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from feishu_send import load_webhook, send_feishu
"""
import json
import os
import time
import urllib.request
from urllib.error import HTTPError, URLError

# 可重试的飞书业务错误码（限流/频控类，重试后大概率成功）
RETRYABLE_CODES = {11232, 230020, 230006}
# 可重试的 HTTP 状态码（网关抖动 / 服务端繁忙）
RETRYABLE_HTTP = {429, 500, 502, 503, 504}

MAX_ATTEMPTS = 3
BASE_DELAY = 0.5   # 首次重试前等待秒数，指数退避：0.5s → 1s → 2s


def load_webhook(env_dir=None):
    """返回飞书 webhook：环境变量 FEISHU_WEBHOOK 优先，其次读项目根 .env。

    env_dir 仅供单测注入临时目录；默认取模块所在目录（本模块放在项目根，.env 就在旁边）。
    """
    hook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if hook:
        return hook
    here = env_dir or os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, ".env"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("FEISHU_WEBHOOK="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
    except OSError:
        pass
    return ""


def send_feishu(text, webhook, max_attempts=MAX_ATTEMPTS, base_delay=BASE_DELAY):
    """推文本消息到飞书。成功返回业务 code 0。

    - 限流/频控类业务错误与可重试 HTTP 状态、网络错误 → 指数退避重试
    - 不可重试业务错误 → 立即抛 RuntimeError
    - 重试耗尽仍失败 → 抛最后一次异常
    """
    payload = {"msg_type": "text", "content": {"text": text}}
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)
            code = data.get("StatusCode", data.get("code"))
            if code == 0:
                return 0
            err = RuntimeError("飞书业务错误: code=%s, msg=%s" % (code, data.get("msg", "")))
            if code not in RETRYABLE_CODES:
                raise err          # 不可重试，直接抛给调用方
            last_err = err         # 可重试，记下来继续循环
        except HTTPError as e:
            if e.code not in RETRYABLE_HTTP:
                raise
            last_err = e
        except (URLError, TimeoutError, ValueError) as e:
            # ValueError 覆盖 json 解析失败（网关返回非 JSON 页面）；网络类都当可重试
            last_err = e
        if attempt < max_attempts:
            time.sleep(base_delay * (2 ** (attempt - 1)))
    raise last_err


if __name__ == "__main__":
    # 手动自检：python feishu_send.py 直接推送一条测试消息
    import sys
    hook = load_webhook()
    if not hook:
        print("未配置 FEISHU_WEBHOOK（环境变量或项目根 .env），无法自检")
        sys.exit(1)
    try:
        code = send_feishu("[feishu_send] 自检消息：模块 + 重试链路可用 (code=%d)" % 0, hook)
        print("自检成功 code=%s" % code)
    except Exception as e:
        print("自检失败: %s" % e)
        sys.exit(1)
