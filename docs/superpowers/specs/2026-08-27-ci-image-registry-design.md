# 阶段2 CI/CD 镜像仓库化设计（2026-08-27）

## 背景与目标

- **背景**：2026-08-27 OOM 事故暴露部署架构脆弱点——镜像在服务器上现场 `docker build`（内存峰值主凶，2G 服务器扛不住），且部署不可追溯、不可回滚。
- **目标**：构建与运行分离 —— CI 构建 → 镜像仓库版本化 → 服务器只拉镜像 → 一键回滚。让"修复事故的方式"对齐企业生产级 CI/CD 标准。

## 现状（改造前数据流）

```
git push → Actions checkout → scp 01-lnmp → SSH 执行 deploy.sh
  deploy.sh: docker build -t lnmp-php ./php   # 🚨 在服务器上构建，内存峰值
             → docker compose up -d --build   # 每次构建再起容器
             → curl 自检 HTTP 200
compose php 服务 image: lnmp-php              # 本地镜像，无版本、无回滚
```

## 目标架构（改造后数据流）

```
git push → Actions checkout
         → CI: docker build ./01-lnmp/php → tag <short-sha> + latest → docker login ACR → docker push
         → scp 01-lnmp（配置/nginx/证书不涉及）
         → SSH 执行 deploy.sh（带 ACR 凭据 + IMAGE_TAG）
            deploy.sh: docker login → docker compose up -d --pull always → 自检
服务器 只拉镜像不构建：build 峰值从服务器消失
回滚：rollback.sh <sha> → 拉旧镜像 → 旧 tag 起容器 → 自检
```

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 镜像仓库 | **阿里云 ACR 个人版**（免费）| 用户已有阿里云账号；HK 服务器拉国内镜像稳，规避 ghcr.io/Docker Hub 被墙的坑 |
| Tag 策略 | **commit 短SHA + latest 双 tag** | SHA 可追溯，latest 部署便捷；回滚用 SHA |
| 回滚 | **rollback.sh 脚本** | 一键回滚，简历叙事点"部署可追溯 + 可回滚" |

## 文件改动清单

### 1. `.github/workflows/deploy.yml`
在 checkout 之后、scp 之前插入 **build+push 步骤**：
- `docker build ./01-lnmp/php` → tag `<registry>/lnmp-php:${{ github.sha }}` 与 `:latest`
- `docker login <registry>`（用 ACR_USERNAME/ACR_PASSWORD secret）
- `docker push` 两个 tag
- ssh-action 增加 `envs: ACR_REGISTRY,ACR_USERNAME,ACR_PASSWORD,IMAGE_TAG` 把凭据传给远程 deploy.sh
- IMAGE_TAG 默认取 `${{ github.sha }}`（本次部署的就是刚构建的版本）

### 2. `01-lnmp/docker-compose.yml`
php 服务镜像改为**环境变量插值**（deploy.sh 和 rollback.sh 复用同一 compose，不维护两份配置）：
```yaml
image: ${ACR_REGISTRY}/lnmp-php:${IMAGE_TAG:-latest}
```
`${IMAGE_TAG:-latest}` 保证缺省时也能本地手动起（兼容老用法）。

### 3. `01-lnmp/deploy.sh`
- 删除 `docker build -t lnmp-php ./php`（构建已挪到 CI）
- `ACR_REGISTRY=${ACR_REGISTRY:?必须设置}` 强制要求（防止缺省时 compose 镜像地址变成 `/lnmp-php` 空前缀坏值）；`IMAGE_TAG=${IMAGE_TAG:-latest}`
- `docker login` 用 ACR_USERNAME/ACR_PASSWORD，失败即停（set -e）
- `docker compose up -d --pull always`（强制拉最新镜像）
- 保留 10 次重试自检；增加打印当前部署的镜像 tag（可追溯）

### 4. `01-lnmp/rollback.sh`（新建）
- 用法：`bash rollback.sh <short-sha>`
- 流程：`docker pull <registry>/lnmp-php:<sha>` → `IMAGE_TAG=<sha> docker compose up -d` → 自检（复用 deploy.sh 的自检逻辑）

## 阿里云 ACR 前置准备（用户操作，控制台）

1. 开通「容器镜像服务 ACR」个人版（免费）
2. 建命名空间 `fchen` + 镜像仓库 `lnmp-php`
3. 「访问凭证」设置固定登录密码 → 得到 `ACR_USERNAME` / `ACR_PASSWORD`
4. 仓库地址：`crpi-fcwx65scr1zcwwy2.cn-hongkong.personal.cr.aliyuncs.com/fchen/lnmp-php`（实测：ACR 个人版使用 `crpi-<实例id>.cn-hongkong.personal.cr.aliyuncs.com` 专属域名，**不是** `registry.cn-hangzhou.aliyuncs.com`；用户名是访问凭证页显示的 `fchen_xy`，不是账户中文全名）

## GitHub Secrets 清单（Settings → Secrets and variables → Actions）

新增（实测值）：
- `ACR_REGISTRY` = `crpi-fcwx65scr1zcwwy2.cn-hongkong.personal.cr.aliyuncs.com`
- `ACR_USERNAME` = `fchen_xy`
- `ACR_PASSWORD` = 访问凭证设置的固定密码

保留：`SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD`

## 回滚流程

```bash
# 服务器上，/opt/k8s-project/01-lnmp 下
bash rollback.sh <old-short-sha>
# 1) docker pull <registry>/lnmp-php:<old-sha>
# 2) IMAGE_TAG=<old-sha> docker compose up -d
# 3) 自检 10 次 HTTP 200，失败标红提示看日志
```

## 验证方式

1. 改一处可观察的页面文案 → push → 观察 Actions 日志：**build 步骤在 GitHub runner 上完成**（服务器无 build）
2. 服务器 `docker images` 出现 `<registry>/lnmp-php:<sha>` 与 `:latest`
3. 服务器 `free -h`：部署过程无内存峰值（对比改造前）
4. 网站 HTTPS 200，页面显示新文案
5. 执行 `rollback.sh <上一个sha>` → 页面回旧文案 → 验证一键回滚闭环

## 范围外（YAGNI）

- `07-cloud-monitoring` 不改（静态配置，手动 scp 已覆盖）
- k3s 栈（02-k3s）不进本次范围（阶段5 再做 K8s 版 CI/CD）

## 错误处理

- CI 任一环节失败 → 整个 workflow 标红（action 默认 fail-fast）
- 服务器 pull 失败 / compose up 失败 → 自检不通过 → workflow 标红
- 回滚失败 → 自检拦截并提示 `docker compose logs --tail 50`
- docker login 失败 → 立即失败（`set -e`），避免用错凭据还继续部署
