# 2.0 黑盒探测脚本（service_probe.py）设计文档

- 日期：2026-08-24
- 状态：已由用户确认设计
- 目标模块：`04-scripts/`
- 关联：模块4 已有 `disk_alert.py`（白盒磁盘巡检，独立脚本直推飞书）

---

## 1. 目的

为项目补上**黑盒监控**能力：从宿主机外网视角，定时探测两个留言板入口是否"通"。
白盒（node_exporter→Prometheus）看资源指标，间接推断健康；黑盒从用户视角直接验证"服务能不能访问"。
探测失败 → 推飞书告警；恢复 → 推"已恢复"。补齐项目"服务可用性检测"的空白。

## 2. 架构 / 数据流

```
cron 每 5 分钟 → service_probe.py（Windows 宿主机，本机执行）
  ├─ 探① http://localhost:8080                                → LNMP 留言板（compose 栈）
  ├─ 探② http://localhost:8081 + Host: guestbook.local        → k8s 全链路（Ingress→Service→Pod）
  └─ 任一目标连续失败 3 次 → 推飞书 [服务探测] ❌ 不可达
     任一目标从"挂"恢复    → 推飞书 [服务探测] ✅ 已恢复
```

**探测目标说明**：
- 探① 直接探本机 LNMP 入口 `http://localhost:8080`，期望 HTTP 200。
- 探② 探 k3d 集群负载均衡入口 `http://localhost:8081`，携带 `Host: guestbook.local` 头，期望 HTTP 200。
  之所以从外部走 :8081+Host 头而非集群内直连 Service，是为了"黑盒"语义：站在用户角度走完整条链路
  （Traefik Ingress → guestbook-svc → 某个 Pod），任何一环断裂都能被探测出来。
- 两个目标**独立判断、独立告警**，互不影响。

## 3. 关键逻辑（用户已确认的设计决策）

| 决策 | 选择 | 理由 |
|---|---|---|
| 防抖 | 连续失败 **3 次**才判定"挂了"并告警 | 单次网络抖动不算故障，3 次确认避免误报 |
| 状态记忆 | 用本地文件（`service_probe_state.json`）记录每个目标的失败计数与当前状态 | 脚本每次执行是独立进程，不记文件无法实现"连续失败"计数与"恢复"判断 |
| 恢复通知 | 状态从"挂"→"好"时推"已恢复" | 与 feishu-bridge 的 `send_resolved` 行为一致，用户能确认故障闭环 |
| 正常静默 | 两目标均正常时不发任何消息 | 避免刷屏 |

**判定规则**：
- 一个目标的探活失败（超时 / 连接拒绝 / 非 200 响应）→ 失败计数 +1；成功 → 计数清零。
- 失败计数达到 3 → 状态置为 `down`，推告警；之后继续失败不再重复推（避免轰炸）。
- 状态为 `down` 时某次探活成功 → 状态置为 `up`，推"已恢复"。

## 4. 探测实现要点

- 纯标准库实现（`urllib.request` / `json` / `os` / `sys`），零第三方依赖，与 `disk_alert.py` 一致。
- 每个请求 `timeout=10` 秒。
- 探② 需设置请求头 `Host: guestbook.local`。
- 失败原因区分上报：`连接超时`、`连接拒绝`、`HTTP <code>`（如 500/502/404），便于排查是哪一环。
- 从项目根 `.env` 读取 `FEISHU_WEBHOOK`（复用模块4 的 `load_webhook` 模式）；未配置时只打日志不推送（便于先验逻辑）。

## 5. 飞书消息格式

沿用模块4/5 的统一格式：`{"msg_type":"text","content":{"text":"..."}}`

告警示例：
```
[服务探测] ❌ k8s留言板 不可达
目标: http://localhost:8081 (Host: guestbook.local)
失败原因: HTTP 502
连续失败: 3 次
时间: 2026-08-24 10:30:00
```

恢复示例：
```
[服务探测] ✅ k8s留言板 已恢复
目标: http://localhost:8081 (Host: guestbook.local)
时间: 2026-08-24 11:00:00
```

## 6. 错误处理

- 探活失败属于"业务判定"（推告警），不是异常。
- 飞书推送自身失败（网络/webhook 失效）→ `print` 日志并继续，**不让脚本崩溃**。
- 状态文件读写失败 → 打日志降级处理（按"无历史状态"对待，计数从当前次开始）。
- 脚本运行不依赖集群状态（本机执行），集群没起时探②会"连不上"→ 走失败逻辑，符合预期。

## 7. 测试方案（验收标准）

1. **正常态**：LNMP 与 k8s 两入口均可达 → 脚本静默，无飞书消息。
2. **LNMP 故障**：`docker compose -f 01-lnmp/docker-compose.yml stop lnmp-nginx`
   → 连续运行脚本 3 次 → 收到飞书 `[服务探测] ❌ LNMP留言板 不可达`。
3. **LNMP 恢复**：`docker compose -f 01-lnmp/docker-compose.yml start lnmp-nginx`
   → 运行脚本 → 收到 `[服务探测] ✅ LNMP留言板 已恢复`。
4. **k8s 故障**：`kubectl -n guestbook scale deployment guestbook --replicas=0`
   → 连续运行脚本 3 次 → 收到 `[服务探测] ❌ k8s留言板 不可达`（探② 应捕获非200/连不上）。
5. **恢复**：`kubectl -n guestbook scale deployment guestbook --replicas=3` → 收到已恢复。
6. **重复失败不轰炸**：持续失败期间只推一次告警，不重复推。

## 8. 产出文件

```
04-scripts/
├── disk_alert.py        (已有，不改)
├── log_cleanup.sh       (已有，不改)
├── service_probe.py     (新增，约 80~100 行，纯标准库)
└── README.md            (更新：加 service_probe.py 用法)
```

## 9. 范围外（YAGNI）

- 不做 blackbox-exporter 方案（不挂进 Prometheus/Grafana，不改集群监控栈）。
- 不做多级阈值 / 告警分级 / 卡片消息。
- 不做 HTTP 内容断言（不校验页面是否含"留言板"关键字，仅校验连通性与 200）。

## 10. 关联

- 模块4 脚本模式：复用 `disk_alert.py` 的 `.env` + 飞书推送 + cron 模式。
- 白盒 vs 黑盒：本功能补黑盒（服务可用性），Prometheus 规则已补白盒（资源指标）。
- 求职：作为"自研探测脚本"写入简历/面试，展示对白盒/黑盒监控边界的理解。
