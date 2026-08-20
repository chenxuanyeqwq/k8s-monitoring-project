#!/usr/bin/env python3
"""
feishu-bridge：Alertmanager 告警 → 飞书消息 的转换桥。

问题背景：Alertmanager 的 webhook 直接 POST 的是它自己的告警 JSON
（{"version":"4","alerts":[...]}），而飞书自定义机器人只认飞书消息格式
（{"msg_type":"text","content":{...}}），两者不兼容，所以需要一个转换层。

功能：
- POST /alert      接收 Alertmanager webhook，转成飞书文本消息后推给飞书
- GET  /healthz    健康检查
- 飞书 webhook 从环境变量 FEISHU_WEBHOOK 读；没配时只打印日志，方便先验证链路

用法：
  python bridge.py           # 监听 0.0.0.0:8080
  python bridge.py --port 9099
依赖：Python 3 标准库，无需第三方包。
"""
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8080


def load_webhook() -> str:
    """获取飞书 webhook：环境变量优先，其次项目根 .env（本文件在 05-feishu-bridge/ 下，根在上一级）。"""
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


def build_feishu_text(data: dict) -> str:
    """把 Alertmanager webhook payload 转成飞书文本消息。"""
    status = data.get("status", "unknown")
    alerts = data.get("alerts", [])
    state = "【告警中】" if status == "firing" else "【已恢复】"
    lines = [f"{state} 收到 {len(alerts)} 条告警"]
    for a in alerts:
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        name = labels.get("alertname", "unknown")
        lines.append(f"  - {name}")
        if ann.get("summary"):
            lines.append(f"      摘要: {ann['summary']}")
        if ann.get("description"):
            lines.append(f"      详情: {ann['description']}")
        for k in ("severity", "instance", "node"):
            if k in labels:
                lines.append(f"      {k}: {labels[k]}")
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/alert":
            self._reply(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON 解析失败: {e}")
            self._reply(400, "bad json")
            return

        text = build_feishu_text(data)
        webhook = load_webhook()
        log_prefix = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {len(data.get('alerts', []))}条告警 状态={data.get('status')}"

        if webhook:
            payload = {"msg_type": "text", "content": {"text": text}}
            try:
                req = urllib.request.Request(
                    webhook,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    print(f"{log_prefix} → 已推送飞书 (HTTP {resp.status})")
            except Exception as e:
                print(f"{log_prefix} → 飞书推送失败: {e}")
                self._reply(500, "feishu push failed")
                return
        else:
            # 未配置 webhook：只记录，用于先验证 Prometheus→Alertmanager→bridge 链路
            print(f"{log_prefix} → 未配置 FEISHU_WEBHOOK，仅记录：\n{text}")

        self._reply(200, "ok")

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(200, "ok")
        else:
            self._reply(404, "not found")

    def _reply(self, code: int, msg: str):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> None:
    # 容器里 stdout 是管道，默认块缓冲会把日志吞掉，改成行缓冲方便 kubectl logs 实时看
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    port = DEFAULT_PORT
    if len(sys.argv) >= 3 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    webhook = load_webhook()
    print(f"feishu-bridge 监听 :{port}  (webhook={'已配置' if webhook else '未配置，仅记录日志'})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
