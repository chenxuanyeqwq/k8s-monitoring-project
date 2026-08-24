# 模块6：黑盒探测（06-blackbox）

**v2.0 新增**：服务可用性黑盒监控，补 Prometheus 白盒资源监控的盲区——白盒看"机器指标"，黑盒直接回答"**服务通不通**"。

## service_probe.py — 服务可用性探测

从宿主机外网视角探测两个留言板入口，连续失败 3 次判定"挂了"推飞书告警，恢复推"已恢复"，正常静默不刷屏。

```bash
# 手动跑一次
python service_probe.py

# 连续失败阈值可配（默认 3）
PROBE_FAIL_THRESHOLD=3 python service_probe.py
```

**crontab 定时（每 5 分钟一次）：**
```
*/5 * * * * cd /e/dev/k8s-project/06-blackbox && python service_probe.py >> /var/log/service_probe.log 2>&1
```

**探测目标：**
- `http://localhost:8080` → LNMP 留言板
- `http://localhost:8081` + `Host: guestbook.local` → k8s 留言板（Ingress→Service→Pod 全链路）

## 实现要点

- 核心是纯函数状态机 `apply_probe_result`（正常/告警/恢复/防轰炸），配 6 个 unittest：
  `python -m unittest test_service_probe -v`
- 连续失败 3 次才告警（防误报）；`down` 后不重复轰炸；状态存同目录 `service_probe_state.json`（已 gitignore）
- 失败原因区分上报：`连接拒绝` / `HTTP 503`（Ingress 无可用 Pod）/ `HTTP 404`
- 飞书 webhook 从项目根 `.env` 读取（复用模块4 模式）；未配置只打日志不推送

## 实测验证

- 停 nginx → 3 次探测 → 飞书收到 `[服务探测][失败]`（HTTP 200）
- 恢复 nginx → 飞书收到 `[服务探测][已恢复]`
- k8s 缩容到 0 → 捕获 `HTTP 503` → 飞书告警；恢复 3 副本 → 已恢复

## 面试一句话

> "我用一个纯标准库脚本做了黑盒监控：从外网视角定时探测两个留言板入口通不通，连续失败 3 次推飞书告警、恢复推已恢复、防轰炸。核心状态机抽成纯函数配了单测。这让我的监控从白盒（资源指标）补上了黑盒（服务可用性）这一层。"
