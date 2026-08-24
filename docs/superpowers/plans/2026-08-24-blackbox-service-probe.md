# 2.0 黑盒探测脚本（service_probe.py）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目新增 `04-scripts/service_probe.py` 黑盒探测脚本：从宿主机外网视角探测 LNMP(:8080) 与 k8s(:8081+Host头) 两个留言板入口，连续失败 3 次推飞书告警，恢复推"已恢复"。

**Architecture:** 纯标准库 Python 脚本，复用 `disk_alert.py` 的 `.env` + 飞书推送模式。核心状态机抽成纯函数 `apply_probe_result`（可单测），`main()` 负责探测→状态转移→消息推送→状态文件落盘。由 cron/Windows 任务计划定时调用（外部调度，脚本本身单次执行）。

**Tech Stack:** Python 3 标准库（`urllib.request` / `json` / `os` / `sys` / `time`），测试用标准库 `unittest`。零第三方依赖。

## Global Constraints

- 纯标准库，禁止第三方依赖（与 `disk_alert.py` 一致）。
- 消息文本**禁止 emoji**：Windows GBK 控制台 `print` 含 emoji 抛 `UnicodeEncodeError`（`disk_alert.py:76` 注释的已知坑）。
- 飞书 webhook 获取优先级：环境变量 `FEISHU_WEBHOOK` → 项目根 `.env`；未配置则只打印不推送。
- 判定规则：HTTP 200 = 可达；超时/连接拒绝/非 200 = 失败。连续失败达 `PROBE_FAIL_THRESHOLD`（默认 3）判定 `down` 并告警；`down` 后不再重复告警；恢复推一次"已恢复"。
- 状态文件 `service_probe_state.json` 位于脚本同目录，记录每个目标的 `fail_count` 与 `status`。
- 两个目标独立判断、独立告警。
- Windows 下用 `python` 命令（`python3` 是 Store 桩，见项目笔记坑 #9）。
- 实现完成后同步更新 `04-scripts/README.md`，并把 `service_probe_state.json` 加入 `.gitignore`。

---

### Task 1: TDD 实现状态机 + 完整脚本

**Files:**
- Create: `04-scripts/test_service_probe.py`
- Create: `04-scripts/service_probe.py`
- Modify: `.gitignore`（追加 `04-scripts/service_probe_state.json`）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces:
  - `apply_probe_result(rec: dict, ok: bool, reason: str, threshold: int) -> tuple[dict, str]` —— 纯函数状态机，返回 `(new_rec, event)`，`event ∈ {'ok','warn','alert','recover'}`。
  - `probe(url: str, headers: dict, timeout: int = 10) -> tuple[bool, str]`
  - `send_feishu(text: str, webhook: str) -> int` —— 原始推送（可抛异常，由 `push_feishu` 兜底）
  - `push_feishu(text: str, webhook: str) -> None` —— 安全推送封装：webhook 为空或失败都记日志继续，不崩脚本
  - `load_webhook() -> str`
  - `load_state() -> dict` / `save_state_safe(state: dict) -> None`
  - `main() -> None`

- [ ] **Step 1: 写失败的单元测试**

创建 `04-scripts/test_service_probe.py`：

```python
import unittest
from service_probe import apply_probe_result


class ApplyProbeResultTest(unittest.TestCase):
    def test_first_fail_is_warn(self):
        rec = {"fail_count": 0, "status": "up"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "warn")
        self.assertEqual(new["fail_count"], 1)

    def test_third_fail_triggers_alert(self):
        rec = {"fail_count": 2, "status": "up"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "alert")
        self.assertEqual(new["status"], "down")

    def test_down_does_not_repeat_alert(self):
        rec = {"fail_count": 3, "status": "down"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "warn")  # 已 down，只累加计数，不重复告警

    def test_success_resets_count(self):
        rec = {"fail_count": 2, "status": "up"}
        new, event = apply_probe_result(rec, True, "", 3)
        self.assertEqual(event, "ok")
        self.assertEqual(new["fail_count"], 0)

    def test_recover_from_down(self):
        rec = {"fail_count": 3, "status": "down"}
        new, event = apply_probe_result(rec, True, "", 3)
        self.assertEqual(event, "recover")
        self.assertEqual(new["status"], "up")
        self.assertEqual(new["fail_count"], 0)

    def test_below_threshold_stays_up(self):
        rec = {"fail_count": 1, "status": "up"}
        new, event = apply_probe_result(rec, False, "HTTP 500", 3)
        self.assertEqual(event, "warn")
        self.assertEqual(new["status"], "up")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /e/dev/k8s-project/04-scripts && python -m unittest test_service_probe -v
```
Expected: FAIL —— `ModuleNotFoundError: No module named 'service_probe'`。

- [ ] **Step 3: 实现 `04-scripts/service_probe.py`**

```python
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
TARGETS = [
    {"name": "LNMP留言板", "url": "http://localhost:8080", "headers": {}},
    {"name": "k8s留言板", "url": "http://localhost:8081", "headers": {"Host": "guestbook.local"}},
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
    if new["fail_count"] >= threshold and rec.get("status") != "down":
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


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /e/dev/k8s-project/04-scripts && python -m unittest test_service_probe -v
```
Expected: 6 个测试全部 PASS。

- [ ] **Step 5: 更新 `.gitignore`**

在 `.gitignore` 末尾追加一行：

```
# 黑盒探测脚本的运行状态文件
04-scripts/service_probe_state.json
```

- [ ] **Step 6: 提交**

```bash
cd /e/dev/k8s-project && git add 04-scripts/service_probe.py 04-scripts/test_service_probe.py .gitignore && git commit -m "feat: 新增黑盒探测脚本 service_probe.py（含状态机单测）"
```

---

### Task 2: LNMP 黑盒链路集成验证（正常态 + 故障 + 恢复）

**Files:**
- 无新增文件（操作验证）。可能修改 `04-scripts/service_probe_state.json`（运行时状态，已 gitignore）。

**Interfaces:**
- Consumes: Task 1 的 `service_probe.py`。
- Produces: 对"LNMP 探测"的实机验证结论。

> 说明：本任务会短暂停掉 `lnmp-nginx`（约 1~2 分钟），期间 `:8080` 不可访问，属预期行为，测试完立即恢复。飞书群会收到测试告警，属预期。

- [ ] **Step 1: 清理状态文件，确认正常态静默**

```bash
rm -f /e/dev/k8s-project/04-scripts/service_probe_state.json
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```
Expected: 输出两行 `[INFO] LNMP留言板 正常 (HTTP 200)` 和 `[INFO] k8s留言板 正常 (HTTP 200)`；不推送飞书。

- [ ] **Step 2: 停掉 LNMP 前台，制造故障**

```bash
docker compose -f /e/dev/k8s-project/01-lnmp/docker-compose.yml stop lnmp-nginx
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```
Expected: `[WARN] LNMP留言板 第 1 次失败 (...)`，不推送（未达阈值）。

- [ ] **Step 3: 连续跑满 3 次，触发告警**

```bash
cd /e/dev/k8s-project/04-scripts && python service_probe.py && python service_probe.py
```
Expected: 第 2 次输出 `[WARN] ... 第 2 次失败`，第 3 次输出 `[ALERT] LNMP留言板 不可达` + `已推送飞书 (HTTP 200)`。**飞书群收到 `[服务探测][失败] LNMP留言板 不可达`**。

- [ ] **Step 4: 恢复 LNMP，触发"已恢复"**

```bash
docker compose -f /e/dev/k8s-project/01-lnmp/docker-compose.yml start lnmp-nginx
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```
Expected: 输出 `[RECOVER] LNMP留言板 已恢复` + `已推送飞书 (HTTP 200)`。**飞书群收到 `[服务探测][已恢复] LNMP留言板`**。

- [ ] **Step 5: 验证重复失败不轰炸**

再次执行 Step 2（停 nginx），连跑 4 次脚本：
```bash
docker compose -f /e/dev/k8s-project/01-lnmp/docker-compose.yml stop lnmp-nginx
cd /e/dev/k8s-project/04-scripts && python service_probe.py && python service_probe.py && python service_probe.py && python service_probe.py
```
Expected: 第 3 次触发一次 `[ALERT]`；**第 4 次只输出 `[WARN] ... 第 4 次失败`，不重复推送**。然后恢复：
```bash
docker compose -f /e/dev/k8s-project/01-lnmp/docker-compose.yml start lnmp-nginx
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```

- [ ] **Step 6: 提交**

```bash
cd /e/dev/k8s-project && git add -A && git commit -m "test: 黑盒探测 LNMP 链路实机验证（正常/故障/恢复/防轰炸）" || echo "无文件变更，跳过提交"
```

---

### Task 3: k8s 黑盒链路集成验证

**Files:**
- 无新增文件（操作验证）。

**Interfaces:**
- Consumes: Task 1 的 `service_probe.py`。
- Produces: 对"k8s 探测（:8081+Host头 走 Ingress 全链路）"的实机验证结论。

> 说明：本任务会短暂把 guestbook 缩到 0 副本（约 1~2 分钟），期间 `:8081` 返回非 200，属预期，测试完立即恢复。

- [ ] **Step 1: 确认正常态**

```bash
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```
Expected: `[INFO] k8s留言板 正常 (HTTP 200)`。

- [ ] **Step 2: 缩容制造故障**

```bash
kubectl -n guestbook scale deployment guestbook --replicas=0
cd /e/dev/k8s-project/04-scripts && python service_probe.py && python service_probe.py && python service_probe.py
```
Expected: 第 3 次输出 `[ALERT] k8s留言板 不可达 (HTTP 502 或 连接失败)` + `已推送飞书 (HTTP 200)`。**飞书群收到 `[服务探测][失败] k8s留言板 不可达`**。

- [ ] **Step 3: 恢复副本，触发"已恢复"**

```bash
kubectl -n guestbook scale deployment guestbook --replicas=3
# 等 Pod 就绪
kubectl -n guestbook rollout status deployment/guestbook
cd /e/dev/k8s-project/04-scripts && python service_probe.py
```
Expected: `[RECOVER] k8s留言板 已恢复` + `已推送飞书 (HTTP 200)`。**飞书群收到 `[服务探测][已恢复] k8s留言板`**。

- [ ] **Step 4: 提交**

```bash
cd /e/dev/k8s-project && git add -A && git commit -m "test: 黑盒探测 k8s 链路实机验证（缩容/恢复/告警推送）" || echo "无文件变更，跳过提交"
```

---

### Task 4: 更新 README 与收尾

**Files:**
- Modify: `04-scripts/README.md`（追加 service_probe.py 一节）。
- Modify: 桌面教学笔记 `C:\Users\chenxuanye\Desktop\DockerK8s监控项目_形象化教学笔记.md`（把"没做黑盒"改为"已补黑盒"）。

**Interfaces:**
- Consumes: Task 1 的 `service_probe.py` 最终行为。
- Produces: 面向使用者/复习者的文档。

- [ ] **Step 1: 在 `04-scripts/README.md` 追加一节**

在 `log_cleanup.sh` 一节之后、`## 面试一句话` 之前插入：

```markdown
## service_probe.py — 服务可用性黑盒探测

从宿主机外网视角探测两个留言板入口是否"通"（黑盒监控，补 Prometheus 白盒的盲区）：
连续失败 3 次判定"挂了"推飞书告警，恢复推"已恢复"。

```bash
# 手动跑一次
python service_probe.py

# 连续失败阈值可配
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
```

- [ ] **Step 2: 更新桌面教学笔记的黑盒描述**

编辑 `C:\Users\chenxuanye\Desktop\DockerK8s监控项目_形象化教学笔记.md`：
- 第八节「白盒 vs 黑盒」表中，本项目列从 `❌ 没做` 改为 `✅ 已补（service_probe.py 独立探测脚本）`。
- 六节「三个指标档案」后的坑点 2 附近，加一句：`2026-08-24 新增：黑盒探测脚本 service_probe.py，从外网视角探 :8080 与 :8081+Host头，挂了推飞书。`

- [ ] **Step 3: 提交**

```bash
cd /e/dev/k8s-project && git add -A && git commit -m "docs: README 补充黑盒探测脚本说明"
```

---

### Task 5: 收尾验收（对照 spec 测试方案逐条过）

**Files:**
- 无新增文件。

**Interfaces:**
- Consumes: 全部任务的产物。
- Produces: 交付确认。

- [ ] **Step 1: 对照 spec 第 7 节验收清单逐条核对**

| spec 测试项 | 通过标准 | 状态 |
|---|---|---|
| 正常态静默 | 两目标 200，无飞书 | 见 Task2 S1 |
| LNMP 故障 → 3 次 → 告警 | 飞书收到 `[服务探测][失败] LNMP留言板` | 见 Task2 S3 |
| LNMP 恢复 → "已恢复" | 飞书收到 `[服务探测][已恢复] LNMP留言板` | 见 Task2 S4 |
| k8s 缩容 → 告警 | 飞书收到 `[服务探测][失败] k8s留言板` | 见 Task3 S2 |
| k8s 恢复 → "已恢复" | 飞书收到 `[服务探测][已恢复] k8s留言板` | 见 Task3 S3 |
| 重复失败不轰炸 | down 后不再重复推 | 见 Task2 S5 |

- [ ] **Step 2: 确认最终文件清单**

```bash
git -C /e/dev/k8s-project log --oneline -6
git -C /e/dev/k8s-project status
```
Expected: 新增 `service_probe.py`、`test_service_probe.py`，修改 `.gitignore`、`04-scripts/README.md`；工作区干净。
