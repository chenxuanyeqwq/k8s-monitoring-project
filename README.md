# Docker + K8s 部署与监控

一个贯穿容器化 → 编排 → 监控 → 自动化的完整项目，现已**上云 + 全链路监控告警 + 日志采集 + 全站 HTTPS + 域名上线**。

> 📌 **当前版本 v4.5**：LNMP 上云公网可访问 + **标准多阶段 CI/CD（lint→测试→构建→审批→部署 + 应用级单测 + 集成冒烟 + 生产审批门 + 部署后安全冒烟）** + **云监控告警 + 应用层监控** + **日志采集(Loki+promtail)** + **全站 HTTPS(Let's Encrypt)** + **域名 fchen.xyz 上线** + **飞书推送加固(共享模块 + 限流重试)** + **公网扫描防护(nginx 加固 + fail2ban 自动封禁)** + **资源耗竭加固(停 snapd + LowMemory 内存预警)**。v4.4 = 资源耗竭加固;v4.3 = 公网扫描防护;v4.2 = 飞书推送加固;v4.1 = 单测质量门;v4.0 = 镜像仓库化;v3.6 = 全站HTTPS;v3.5 = 日志采集;v3.4 = 域名上线;v3.3 = 应用层监控;v3.2 = 云监控上云;v3.1 = 前端优化;v3.0 = 上云+CI/CD;v2.0 = 白盒+黑盒;v1.0 = 5 模块。

## 模块总览

| 模块 | 目录 | 内容 | 验证结果 |
|---|---|---|---|
| 1. LNMP 容器化 | `01-lnmp/` | 自写 PHP 留言板，docker compose 编排 Nginx+PHP-FPM+MySQL，**全站 HTTPS(Let's Encrypt)** | ✅ 中文无乱码、删容器数据不丢、HTTPS 200 |
| 2. k3s 部署 | `02-k3s/` | k3d 建集群，留言板部署到 k8s，滚动更新/回滚演练 | ✅ v1→v2→回滚全通过 |
| 3. 监控告警 | `03-monitoring/` | node_exporter→Prometheus→Alertmanager→飞书，Grafana 面板 | ✅ CPU 打满告警真实触发 |
| 4. 运维脚本 | `04-scripts/` | 磁盘告警 + 日志清理脚本 | ✅ 本地实测通过 |
| 5. 飞书桥 | `05-feishu-bridge/` | Alertmanager 告警 → 飞书消息 的转换服务（k8s Deployment） | ✅ 压测告警端到端到桥 |
| 6. 黑盒探测（**2.0**） | `06-blackbox/` | 从外网视角探测留言板入口，连续失败 3 次推飞书告警、恢复推已恢复（v3.2 起在云服务器常驻） | ✅ 停服实测告警+恢复 |
| 7. 云监控告警 + 日志（**v3.2-v3.5**） | `07-cloud-monitoring/` | 云服务器 compose 监控栈：node-exporter(机器) + nginx/mysql exporter(应用) → Prometheus→Alertmanager→飞书 + Grafana 7 面板 + 每日内存报告 + **Loki/promtail 日志采集(v3.5)** | ✅ 三层监控全 up,告警/恢复/内存报告/日志查询实测 |

## 当前运行状态

```
LNMP 留言板（compose·云端） https://www.fchen.xyz       ← 已上云，全站 HTTPS(v3.6)，公网可访问
云服务器 Grafana（v3.2/v3.5） http://8.217.195.115:3000     ← 面板看 CPU/内存/磁盘；Explore 查容器日志(Loki)
LNMP 留言板（compose·本地）  http://localhost:8080 (会自动跳 HTTPS)
k8s 留言板（Ingress）     curl -H "Host: guestbook.local" http://localhost:8081
本地 Grafana               curl -H "Host: grafana.local" http://localhost:8081  (admin/admin)
Prometheus(本地)           kubectl -n monitoring port-forward svc/prometheus 9090:9090
```

## 项目主线

> **自建小型生产环境**：Ubuntu → Docker 容器化 → k3s 多副本部署 → Prometheus/Grafana 监控 → Alertmanager 飞书告警 → 自动化脚本 → **上云 + CI/CD + 云监控告警**。

## 遇到的坑

1. Alpine 源连不上 → Dockerfile 构建卡死 → `sed` 换阿里云源
2. MySQL 导入中文乱码 → `SET NAMES utf8mb4;`
3. ghcr.io 被墙 → k3d 集群创建卡死 → DaoCloud ghcr 镜像 + `docker tag`
4. k3s containerd 不走 Docker 加速 → 挂 `registries.yaml` 指向 DaoCloud
5. kubeconfig host.docker.internal 连不上 → 改 127.0.0.1 + insecure-skip-tls-verify
6. containerd 拉镜像 DNS 抖动 → `k3d image import` 本地镜像（或用 `ctr -n k8s.io images import`）
7. **Alertmanager 原生 webhook 格式飞书不收**（`{"version":4,"alerts":[]}` vs 飞书要 `{"msg_type":...}`）→ 自建 `feishu-bridge` 转换层
8. **容器里 Python print 被块缓冲吞掉** → `kubectl logs` 看不到 → `sys.stdout.reconfigure(line_buffering=True)`
9. **NI Application WebServer 抢占 8080 端口（Windows）** → 8080 的所有 IPv4 地址被劫持（返回 `Embedthis-http` 404），nginx 只在 IPv6 `::1` 通，表现为"curl 通但 Python urllib 404" → `net stop NIApplicationWebServer` 释放端口
10. **Grafana provisioning 面板不加载**（v3.2）→ scp 上传文件 root 权限、容器非 root 读不了 → `chmod -R a+rX` + 重启 Grafana
11. **飞书 webhook 成功响应字段是 `StatusCode`**（非小写 `code`）→ 判断成功要兼容两个字段，否则成功被误判为失败
12. **Loki 容器只绑 IPv6**（v3.5）→ 组件间 gRPC 走 IPv4 `127.0.0.1` 超时、`/ready` 503 + ratestore 报错 → 配置显式 `http_listen_address: 0.0.0.0` + `grpc_listen_address: 0.0.0.0`
13. **2G 内存上 Loki 前必须先加 swap**（v3.5）→ `fallocate -l 2G /swapfile` + 写 fstab，否则内存紧张 OOM
14. **acme.sh 默认用 ZeroSSL 签发失败**（v3.6）→ ZeroSSL API 返回 502 Bad Gateway、白等 6 分钟 → `--set-default-ca --server letsencrypt` 切 Let's Encrypt 秒签
15. **CI/CD 自检失效**（v3.6）→ nginx 改 HTTPS 后 `curl localhost:8080` 返回 301 非 200 → 自检改 `curl -sk https://localhost`
16. **飞书 webhook 整点限流静默丢消息**（v4.2）→ 每日内存报告 cron 09:00 整点撞飞书**租户级限流** `code=11232 frequency limited`，且脚本无重试 → 消息静默丢失。修复：项目根新增共享模块 `feishu_send.py`（统一发送 + 指数退避重试 0.5/1/2s），cron 挪到 **09:13** 避开整点高峰
17. **公网扫描器打爆请求率+MySQL 查询率**（v4.3）→ GCP 台北 VM `34.80.5.60` 25 分钟打 8726 次，路径全是凭据泄露/SSRF 探测（`/.env`、`/.git/config`、`/actuator`、`169.254.169.254`），UA 伪装成 Perplexity/ChatGPT/Claude。**放大器**：nginx `try_files $uri $uri/ /index.php` 让任意未知路径都落 index.php 查 MySQL，扫描器每请求都放大成一次查询。**关键坑**：Docker 端口流量走 **FORWARD/DOCKER-USER 链、不过 INPUT 链**，封 INPUT 不生效，必须 `chain=DOCKER-USER`。修复：nginx 敏感路径 444 + 未知路径 `=404` 关放大器 + `limit_req` 限流 + **fail2ban 自动封禁**
18. **服务器资源耗竭级联崩溃**（v4.4）→ 1.6Gi 内存跑 LNMP + 12 容器监控栈长期仅剩 ~300-400MiB 可用，snapd 死循环重启 523 次持续吃 CPU → swap thrash → 监控/MySQL/sshd/云助手**逐个被饿死**（**非经典 OOM**，无 oom-kill 记录）。**关键坑**：① mem_limit 只能防单容器 OOM，**防不住宿主级 swap thrash** ② 告警规则没有内存项 → 监控自己先死都没人知道。修复：停用 snapd（`systemctl disable --now snapd snapd.socket`）+ 新增 **LowMemory** 告警（可用内存 <300MiB 持续 10min → 飞书）
19. **nginx 444 不是 HTTP 状态码**（v4.5）→ 部署后安全冒烟想用 curl 验证敏感路径返回 444，但 nginx `return 444` = **不发响应直接关连接**，curl 收到空响应报 `http_code=000`（empty reply / "server closed abruptly"）而非 444。**关键坑**：`return 444` 在 curl 眼里是 000，判断 `!= 444` 会误判加固失效。修复：冒烟判定接受 **444 或 000** 两者视为加固生效（未知路径仍校验 404）

## 告警链路（三层监控 → 飞书）

```
机器层  CPU/磁盘/内存    → node-exporter      ┐
应用层  Nginx 请求/5xx   → nginx-exporter      ├→ Prometheus(规则 firing)
        MySQL 查询/连接  → mysqld-exporter     ┘      → Alertmanager
可用性  黑盒探活         → service_probe.py(直推)     → feishu-bridge → 飞书群
```

- 告警规则：`HighCPUUsage` / `HighDiskUsage` / `High5xxRate` / `MySQLDown` / **`LowMemory`（v4.4，可用内存 <300MiB）**
- 云服务器(compose)链路见 `07-cloud-monitoring/`；本地(k8s)链路见 `03-monitoring/manifests/` + `05-feishu-bridge/manifests/`
- 真实飞书 webhook 统一填项目根 **`.env`**，**两端链路均已实测：飞书群真实收到告警** ✅

## v2.0 新增：黑盒监控（服务可用性探测）

白盒（Prometheus）看的是**资源指标**，黑盒直接回答"**服务通不通**"。`06-blackbox/service_probe.py` 从外网视角探测留言板入口：

```
cron 每 5 分钟 → service_probe.py
  └─ http://8.217.195.115:8080（云端公网入口，v3.2 起在云服务器常驻）
  └─ 连续失败 3 次 → 飞书告警；恢复 → 飞书"已恢复"；正常静默
```

- 核心是纯函数状态机 `apply_probe_result`，配 6 个 unittest（`python -m unittest test_service_probe`）
- 连续失败 3 次才告警（防误报）、`down` 后不重复轰炸、状态存 `service_probe_state.json`（已 gitignore）
- 失败原因区分上报：`连接拒绝` / `HTTP 503` / `HTTP 404`
- **实测**：停 nginx → 飞书收到失败告警；恢复 → "已恢复"

## v3.0 新增：上云 + CI/CD 自动部署

LNMP 留言板已部署到 **阿里云 ECS（Ubuntu 22.04，香港）**，公网可访问；接入 **GitHub Actions 流水线**，代码 push 到 main 自动构建并部署。

```
GitHub push → Actions(拉代码) → CI 构建镜像 → push ACR(sha+latest 双 tag) → scp 01-lnmp → SSH deploy.sh(服务器只拉镜像) → 上线
```

- **公网地址**：`https://www.fchen.xyz`（留言板，v3.4 起域名访问、v3.6 起全站 HTTPS；旧 `http://www.fchen.xyz:8080` 自动 301 跳转 HTTPS）
- **关键文件**：`.github/workflows/deploy.yml`（CI/CD）、`01-lnmp/deploy.sh`（拉镜像+部署+自检）、`01-lnmp/rollback.sh`（一键回滚）、`docs/云服务器部署手册.md`
- **安全**：服务器密码存 GitHub Secrets（不落库）；`.env` 由 gitignore 保护不入库

## v3.1–v3.5 新增：前端优化 → 云监控告警 → 应用层监控 → 域名上线 → 日志采集

### v3.1 前端清爽 SaaS 版
留言板前端整体重写（单文件 `01-lnmp/php/www/index.php`）：CSS 设计令牌、友好时间（PHP ISO + JS 相对时间）、提交 Toast（PRG 防重复提交）、精致空状态、移动端适配。安全防护（prepare + htmlspecialchars + PRG）全程保持。

### v3.2 云监控告警（compose 版监控栈上云）
在云服务器部署 `07-cloud-monitoring/`（与 LNMP 同机，compose 编排五件套）：

```
node-exporter → Prometheus(规则) → Alertmanager → feishu-bridge → 飞书
                └─→ Grafana(:3000) 可视化
```

- **Grafana**：`http://8.217.195.115:3000`，看云服务器 CPU/内存/磁盘三块面板
- **CPU 告警**：`HighCPUUsage`（5min 平均 >80% 持续 1min）→ 飞书；实测压测触发 + 恢复均收到 ✅
- **黑盒**：`06-blackbox` 挪到云服务器 cron 每 5 分钟探公网入口
- **每日内存报告**：`memory_report.py` cron 每天 **9:13** 推飞书（v4.2 起避开整点限流高峰；实测 code=0 推送成功）
- **安全**：安全组仅放行 8080/3000；Grafana 改默认密码（fail-fast 必填）；监控内部端口不暴露公网
- 部署手册：`docs/云服务器监控部署手册.md`

### v3.3 应用层监控（网站本身）
在三层监控的**机器层**之上补**应用层**，看网站内部指标：
```
┌─ 机器层  node-exporter        → CPU/内存/磁盘
├─ 应用层  nginx-exporter:9113  → Nginx 请求率/5xx/连接  ← v3.3
│         mysqld-exporter:9104 → MySQL 查询/连接
└─ 可用性  黑盒探活            → 每 5 分钟探公网
```
- nginx 开 `stub_status`（`allow 172.16.0.0/12`）；MySQL 建只读账号 `exporter`
- exporter 接入 `01-lnmp_default` 外部网络，按服务名访问 `nginx`/`db`（跨 compose）
- **Grafana 7 块面板**（新增 Nginx 请求率/5xx、MySQL 查询/连接），实测有数据
- **新增告警**：`High5xxRate`（>5% 1min）+ `MySQLDown`，走飞书链路
- 坑：mysqld-exporter 用 **v0.14.0**（v0.15 有 .my.cnf 解析坑）；改 prometheus.yml 要 `docker restart cm-prometheus`；scp 更新文件后 `chmod -R a+rX grafana/` + 重启 Grafana

### v3.4 域名上线（fchen.xyz）
绑定阿里云域名 **fchen.xyz**（香港服务器**免备案**），配置 A 记录 `@` + `www` → `8.217.195.115`，公网主入口升级为域名：

```
http://www.fchen.xyz:8080    ← 留言板（主入口，域名）
http://8.217.195.115:3000    ← Grafana（监控面板，保持 IP）
```

- 实名认证已通过 → ServerHold 解除 → 解析生效（curl 实测 `http://www.fchen.xyz:8080` HTTP 200）
- DNS：权威 NS `dns21/dns22.hichina.com`，A 记录已发布；全球解析传播约数小时收敛
- 待办（可选扩展）：HTTPS（Let's Encrypt + 自动续期）

### v3.5 日志采集（Loki + promtail）
四路监控闭环的最后一块——**日志**。`07-cloud-monitoring` 新增 **Loki**(存储) + **promtail**(采集)，promtail 读 docker.sock 自动发现所有容器，收 stdout/stderr 日志推 Loki，接入 Grafana Explore：

```
容器日志(nginx/php/mysql/prometheus...) → promtail(docker_sd 自动发现) → Loki → Grafana Explore 查询
```

- **实测**：curl 访问网站 → nginx access log（`GET / HTTP/1.1 200`）自动进 Loki 秒查 ✅；所有容器日志自动采集 ✅
- **查询入口**：Grafana(:3000) → **Explore** → Loki → `{container="lnmp-nginx"}` 看网站访问日志
- **保留 7 天**；自动打标 `container`/`stream`/`service_name`
- 坑：Loki 只绑 IPv6 → 显式绑 `0.0.0.0`；2G 内存先加 swap（2G）兜底

### v3.6 全站 HTTPS（Let's Encrypt）
给留言板上了免费 TLS 证书，全站加密，HTTP 自动 301 到 HTTPS：

```
https://www.fchen.xyz           ← 主入口（443，TLS 加密）
http://www.fchen.xyz            ← 自动 301 跳转 HTTPS
http://www.fchen.xyz:8080       ← 旧入口，自动 301（过渡保留）
```

- **证书**：Let's Encrypt（acme.sh 签发，ECC，90 天自动续期 + 续期后自动 reload nginx）
- **配置**：`01-lnmp/nginx/nginx.conf` 监听 443 + HTTP 301；证书文件 `01-lnmp/nginx/ssl/`（gitignore 不入库）
- **验证**：`https://www.fchen.xyz` HTTP 200；证书有效期 2026-08-26 ~ 11-24
- 坑：acme.sh 默认 ZeroSSL 签发 502 → 切 Let's Encrypt；CI/CD 自检同步改 HTTPS

### v4.0 生产级 CI/CD：镜像仓库化 + 一键回滚（2026-08-27）

镜像构建从服务器挪到 CI，经阿里云 ACR 镜像仓库版本化，服务器只拉镜像部署——8.27 OOM 事故的根治项：

```
GitHub push → CI 构建 php 镜像 → push ACR(commit sha + latest 双 tag) → scp 01-lnmp → 服务器 docker login + 拉镜像 + compose up → 自检
```

- **镜像地址**：`crpi-fcwx65scr1zcwwy2.cn-hongkong.personal.cr.aliyuncs.com/fchen/lnmp-php:<tag>`（香港个人版专属域名，命名空间 fchen）
- **回滚**：`bash rollback.sh <commit sha>` 一条命令拉旧镜像重启，实测三版本切换通过
- **版本可追溯**：镜像内烘焙 `APP_BUILD=commit sha`，`docker exec lnmp-php printenv APP_BUILD` 验证当前线上版本
- **内存收益**：构建峰值从 2G 服务器消失（OOM 根治），服务器只做 pull
- **相关**：`docs/2026-08-27-LNMP-OOM事故记录.md`、`docs/superpowers/specs/2026-08-27-ci-image-registry-design.md`

### v4.1 测试进流水线：部署前质量门（2026-08-27）

单元测试接入 GitHub Actions，push 先跑测试，不过不构建不部署：

- **流水线**：push → checkout → **单元测试(6 个单测)** → CI 构建 → ACR → 服务器只拉 → 自检
- **测试**：`python -m unittest discover -s 06-blackbox -p "test_*.py"`，跑在 GitHub runner（不占服务器内存）
- **触发**：`06-blackbox/**` 改动也触发（探测脚本逻辑变更会被测试把关）
- **实测**：临时改坏阈值 → CI **红在测试步**，构建/部署未执行 → 线上不受影响 → 还原恢复绿

### v4.2 飞书推送加固：共享发送模块 + 限流重试（2026-08-28）

每日内存报告在 **09:00 整点**撞飞书**租户级限流**（`code=11232 frequency limited`），消息被静默丢弃——根因是 cron 卡整点（所有租户定时任务集中触发）+ 发送脚本无重试。本次修复：

- **新增共享模块** `feishu_send.py`（项目根）：统一 `load_webhook` + `send_feishu`，带**指数退避重试**（0.5s→1s→2s），对限流类错误（`11232`/`230020`/`230006`/HTTP 429/5xx/网络错误）自动重试，成功才返回
- **三脚本去重**：`memory_report.py` / `service_probe.py` / `disk_alert.py` 删除各自重复的发送实现（**净减 90 行**），统一走共享模块
- **顺手修复隐藏 bug**：probe/disk 脚本之前**只看 HTTP 状态码、不查飞书业务 code**——限流恰恰是 HTTP 200 + body `code=11232`，等于一直"假装发送成功"，消息实际丢失
- **cron 挪出整点**：每日内存报告 `09:00 → 09:13`，避开租户级定时任务的集中触发高峰
- **日志加时间戳**：`memory_report.log` 每次运行带 `[YYYY-MM-DD HH:MM:SS]`，日后排查不再靠猜
- **测试**：新增 `test_feishu_send.py`（**10 用例**，覆盖 11232 重试成功/重试耗尽抛错/不可重试立即抛/HTTP 429/5xx/网络错误）；原 `test_memory_report.py` 保持通过
- **线上验证**：手动执行 `memory_report.py` → `code=0` 飞书实收 ✅；cron 已同步改 09:13

### v4.3 公网扫描防护：nginx 加固 + fail2ban 自动封禁（2026-08-31）

公网 IP 被自动化扫描器盯上——GCP 台北 VM `34.80.5.60` 25 分钟打 8726 次，路径全是凭据泄露/SSRF 探测（`/.env`、`/.git/config`、`/.aws/credentials`、`/actuator`、`/webhook?url=169.254.169.254/...`、wp-config 系列），UA 伪装成 Perplexity/ChatGPT/Claude/Applebot。更麻烦的是 nginx 的 **"放大器"** 让扫描请求放大成 MySQL 查询，请求率与查询率同步飙升。本次纵深防御加固：

- **① 手动封禁**：`iptables -I DOCKER-USER -s <IP>/32 -j DROP`。⚠️ **关键坑**：Docker 端口流量走 FORWARD→DOCKER-USER 链、**不过 INPUT 链**（`-P FORWARD DROP`），封 INPUT 不生效，必须用 DOCKER-USER 链
- **② nginx 关放大器**：`location /` 的 `try_files ... /index.php` 改为 `try_files $uri $uri/ =404`——未知路径不再落 index.php，扫描器刷 N 次只产生 N 个空 404，不再放大成 PHP+MySQL
- **③ nginx 敏感路径屏蔽**：`/.env`、`/.git`、`/.aws`、`/.ssh`、wp-config*、`/actuator`、`*.swp/*.old/*.bak`、`169.254.169.254`(SSRF) → `return 444` 断连（比 404 更省带宽，仍计入 access_log）
- **④ nginx 单 IP 限流**：`limit_req_zone` 10r/s + burst（php 路径收紧 burst 5），兜底扫描器刷爆
- **⑤ fail2ban 自动封禁**：filter `nginx-probe`（按请求路径特征匹配，与状态码 301/404/444 无关）+ jail（60s 内 6 次命中封 1h）+ `action=iptables-multiport[chain=DOCKER-USER]`；读 nginx bind mount 出的真实 access.log（**stdout 双写保住 Loki**），配 systemd 内存护栏（MemoryMax=128M，实测 RSS 15MB）+ logrotate
- **验证**：加固后 `/.env`→444、`/random/nonexistent`→404（不再 200）、`/`→200、POST→302 全对；Loki 仍收日志；fail2ban-regex 离线自检 4/4 命中；CI/CD 部署后加固不被覆盖
- **相关**：`docs/2026-08-31-公网扫描防护记录.md`

## 飞书 webhook 配置

webhook 统一填在项目根 **`.env`**（`FEISHU_WEBHOOK=` 后面）：

- 本地(k8s)链路：`bash 03-monitoring/set_webhook.sh` 注入 bridge 的 ConfigMap
- 云服务器(compose)链路：把 `.env` 放到服务器 `/opt/k8s-project/.env`，`07-cloud-monitoring/docker-compose.monitoring.yml` 的 feishu-bridge 自动读取
- 三个直连飞书的脚本（`04-scripts/disk_alert.py`、`06-blackbox/service_probe.py`、`07-cloud-monitoring/memory_report.py`）统一复用项目根 **`feishu_send.py`**（自带限流退避重试）读取 `.env`

## 各模块 README

- [模块1：LNMP](01-lnmp/README.md)
- [模块2：k3s 部署](02-k3s/README.md)
- [模块3：监控告警](03-monitoring/README.md)
- [模块4：运维脚本](04-scripts/README.md)
- [模块5：飞书桥](05-feishu-bridge/README.md)
- [模块6：黑盒探测（2.0）](06-blackbox/README.md)
- [模块7：云监控告警 + 日志（v3.5）](07-cloud-monitoring/README.md)
