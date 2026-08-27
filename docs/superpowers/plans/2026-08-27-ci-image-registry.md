# 阶段2 CI/CD 镜像仓库化实现计划（2026-08-27）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 LNMP 的 php 镜像构建从云服务器挪到 GitHub Actions CI，经阿里云 ACR 镜像仓库版本化，服务器只拉镜像，支持一键回滚。

**Architecture:** CI（GitHub Actions）构建 php 镜像并打 `sha`+`latest` 双 tag 推送到 ACR；服务器 deploy.sh 只 `docker login + pull + compose up`，不再 build；rollback.sh 拉旧 sha 镜像一键回滚。compose 通过环境变量插值镜像地址，deploy/rollback 复用同一配置。

**Tech Stack:** GitHub Actions、阿里云 ACR 个人版、Docker Compose v2、bash

## Global Constraints

- 构建**只允许在 GitHub Actions** 发生，服务器严禁 `docker build`（8.27 OOM 事故教训）
- 镜像仓库：`registry.cn-hangzhou.aliyuncs.com/fchen/lnmp-php`
- GitHub Secrets 新增 `ACR_REGISTRY` / `ACR_USERNAME` / `ACR_PASSWORD`；保留 `SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD`
- 服务器 `/opt/k8s-project/01-lnmp/`；本地仓库 `E:\dev\k8s-project`；push 走代理 `HTTPS_PROXY=http://127.0.0.1:15490`
- 自检标准：`curl -sk https://localhost` 返回 200，重试 10 次
- 所有脚本保持 `set -e`

---

### Task 1: docker-compose.yml — php 镜像地址环境变量插值

**Files:**
- Modify: `01-lnmp/docker-compose.yml`（php 服务 `image: lnmp-php` 一行）

**Interfaces:**
- Consumes: 无
- Produces: 环境变量 `ACR_REGISTRY`（必填）、`IMAGE_TAG`（默认 `latest`）——Task 2/3 的脚本通过 export 这两个变量驱动 compose

- [ ] **Step 1: 修改镜像地址**

把 php 服务（`01-lnmp/docker-compose.yml:30`）的：
```yaml
    image: lnmp-php
```
改为：
```yaml
    image: ${ACR_REGISTRY}/lnmp-php:${IMAGE_TAG:-latest}
```

- [ ] **Step 2: 验证插值解析**

Run: `cd /e/dev/k8s-project && ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com IMAGE_TAG=abc123 docker compose -f 01-lnmp/docker-compose.yml config | grep -A1 "lnmp-php"`
Expected: 出现 `image: registry.cn-hangzhou.aliyuncs.com/lnmp-php:abc123`

- [ ] **Step 3: 提交**

```bash
cd /e/dev/k8s-project
git add 01-lnmp/docker-compose.yml
git commit -m "refactor: php 镜像地址改为 ACR 环境变量插值(阶段2)"
```

---

### Task 2: deploy.sh — 去 build，改 login + pull

**Files:**
- Modify: `01-lnmp/deploy.sh`（整体重写逻辑）

**Interfaces:**
- Consumes: 环境变量 `ACR_REGISTRY`(必填)/`ACR_USERNAME`/`ACR_PASSWORD`/`IMAGE_TAG`(默认 latest)；compose 的 `php.image` 插值（Task 1）
- Produces: 部署当前 `IMAGE_TAG` 镜像；自检结果；`docker compose logs --tail 50` 排障提示

- [ ] **Step 1: 重写 deploy.sh**

把 `01-lnmp/deploy.sh` 全部内容替换为：
```bash
#!/bin/bash
# LNMP 服务器部署脚本（阶段2：只拉镜像，不在服务器构建）
# 用法: bash deploy.sh   (可被 CI/CD 远程调用,也可手动在服务器上跑)
set -e
cd "$(dirname "$0")"

# ACR 必填校验，防止缺省时 compose 镜像地址变成空前缀坏值
ACR_REGISTRY=${ACR_REGISTRY:?必须设置 ACR_REGISTRY(如 registry.cn-hangzhou.aliyuncs.com)}
ACR_USERNAME=${ACR_USERNAME:?必须设置 ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD:?必须设置 ACR_PASSWORD}
IMAGE_TAG=${IMAGE_TAG:-latest}

echo "==> [1/3] 登录镜像仓库 ${ACR_REGISTRY}"
echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin

echo "==> [2/3] 拉取并启动容器 (${ACR_REGISTRY}/lnmp-php:${IMAGE_TAG})"
export ACR_REGISTRY IMAGE_TAG
docker compose up -d --pull always

echo "==> [3/3] 自检(带重试,等 MySQL 就绪)"
docker compose ps
for i in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost || true)
  echo "尝试 $i: HTTPS $code"
  if [ "$code" = "200" ]; then
    echo "✅ 部署完成: https://www.fchen.xyz (镜像 tag: $IMAGE_TAG)"
    exit 0
  fi
  sleep 3
done
echo "⚠️ 10 次尝试后仍非 200,查看日志: docker compose logs --tail 50"
exit 1
```

- [ ] **Step 2: 语法检查**

Run: `bash -n /e/dev/k8s-project/01-lnmp/deploy.sh`
Expected: 无输出（语法通过）

- [ ] **Step 3: 提交**

```bash
cd /e/dev/k8s-project
git add 01-lnmp/deploy.sh
git commit -m "refactor: deploy.sh 移除服务器构建,改为 ACR 登录+拉镜像部署(阶段2)"
```

---

### Task 3: rollback.sh — 新建一键回滚脚本

**Files:**
- Create: `01-lnmp/rollback.sh`

**Interfaces:**
- Consumes: 参数 `$1`（镜像 sha/tag）；环境变量 `ACR_REGISTRY`/`ACR_USERNAME`/`ACR_PASSWORD`；compose 插值（Task 1）
- Produces: 拉指定旧镜像并用其重启容器 + 自检

- [ ] **Step 1: 创建 rollback.sh**

```bash
#!/bin/bash
# LNMP 一键回滚：拉取指定旧镜像并用它重启容器
# 用法: bash rollback.sh <镜像 short-sha>
# 查看可用版本: docker images | grep lnmp-php
set -e
cd "$(dirname "$0")"

if [ -z "$1" ]; then
  echo "用法: bash rollback.sh <镜像 short-sha>"
  echo "可用版本: docker images | grep lnmp-php"
  exit 1
fi

SHA="$1"
ACR_REGISTRY=${ACR_REGISTRY:?必须设置 ACR_REGISTRY(如 registry.cn-hangzhou.aliyuncs.com)}
ACR_USERNAME=${ACR_USERNAME:?必须设置 ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD:?必须设置 ACR_PASSWORD}

echo "==> 登录镜像仓库 ${ACR_REGISTRY}"
echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin

echo "==> 拉取旧镜像 ${ACR_REGISTRY}/lnmp-php:${SHA}"
docker pull "${ACR_REGISTRY}/lnmp-php:${SHA}"

echo "==> 用旧 tag 重启容器"
export ACR_REGISTRY
IMAGE_TAG="$SHA" docker compose up -d

echo "==> 自检"
for i in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost || true)
  echo "尝试 $i: HTTPS $code"
  if [ "$code" = "200" ]; then
    echo "✅ 回滚完成: 已回到 ${SHA}"
    exit 0
  fi
  sleep 3
done
echo "⚠️ 回滚自检失败,查看日志: docker compose logs --tail 50"
exit 1
```

- [ ] **Step 2: 赋予执行权限 + 语法检查**

Run: `chmod +x /e/dev/k8s-project/01-lnmp/rollback.sh && bash -n /e/dev/k8s-project/01-lnmp/rollback.sh`
Expected: 无输出（语法通过）

- [ ] **Step 3: 提交**

```bash
cd /e/dev/k8s-project
git add 01-lnmp/rollback.sh
git commit -m "feat: 新增 rollback.sh 一键回滚(拉旧sha镜像重启)"
```

---

### Task 4: deploy.yml — CI 构建 + 推送 + 传凭据

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: GitHub Secrets `ACR_REGISTRY`/`ACR_USERNAME`/`ACR_PASSWORD`（Task 5 用户配置）；`01-lnmp/php/Dockerfile`（构建上下文）
- Produces: ACR 上 `lnmp-php:<GITHUB_SHA>` 与 `lnmp-php:latest` 两个 tag；远程执行 deploy.sh 时注入 ACR 凭据环境变量

- [ ] **Step 1: 在 checkout 后插入 CI 构建步骤**

修改 `.github/workflows/deploy.yml`：在第 27 行 `actions/checkout@v4` 之后、`② 上传 01-lnmp` 之前，插入：
```yaml
      # 阶段2(8.27 OOM 后)：构建挪到 CI，服务器只拉镜像
      - name: ② CI 构建并推送镜像到 ACR
        env:
          ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
          ACR_USERNAME: ${{ secrets.ACR_USERNAME }}
          ACR_PASSWORD: ${{ secrets.ACR_PASSWORD }}
        run: |
          docker build -t "${ACR_REGISTRY}/lnmp-php:${GITHUB_SHA}" -t "${ACR_REGISTRY}/lnmp-php:latest" ./01-lnmp/php
          echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin
          docker push "${ACR_REGISTRY}/lnmp-php:${GITHUB_SHA}"
          docker push "${ACR_REGISTRY}/lnmp-php:latest"
```

- [ ] **Step 2: 把原 ②③ 步骤重编号并给 ssh-action 传凭据**

把原 `② 上传 01-lnmp` 改为 `③ 上传 01-lnmp 到服务器`（内容不变）；原 `③ 远程执行部署` 改为 `④ 远程执行部署`，并加上 `env:` 与 `envs:`（把 ACR 凭据传给远程 deploy.sh）：
```yaml
      - name: ④ 远程执行部署
        uses: appleboy/ssh-action@v1.0.3
        env:
          ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
          ACR_USERNAME: ${{ secrets.ACR_USERNAME }}
          ACR_PASSWORD: ${{ secrets.ACR_PASSWORD }}
        with:
          envs: ACR_REGISTRY,ACR_USERNAME,ACR_PASSWORD
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          password: ${{ secrets.SERVER_PASSWORD }}
          script: |
            bash /opt/k8s-project/01-lnmp/deploy.sh
```

- [ ] **Step 3: 更新文件头注释（描述新流程）**

把 `deploy.yml:2-5` 的注释改为：
```yaml
# CI/CD 流水线:代码 push 到 main → CI 构建镜像推 ACR → 服务器只拉镜像部署
# 工作原理:
#   1. checkout 拉取代码
#   2. CI 构建 php 镜像 → 打 <sha>+latest 双 tag → 推送阿里云 ACR
#   3. scp 把 01-lnmp 目录上传到服务器 /opt/k8s-project
#   4. ssh 在服务器上执行 01-lnmp/deploy.sh(登录ACR + 拉镜像 + compose up + 自检)
#
# 前置配置(GitHub 仓库 Settings → Secrets and variables → Actions):
#   SERVER_HOST       = 服务器公网 IP,如 8.217.195.115
#   SERVER_USER       = SSH 用户名,如 root
#   SERVER_PASSWORD   = SSH 密码(root 密码)
#   ACR_REGISTRY      = registry.cn-hangzhou.aliyuncs.com
#   ACR_USERNAME      = ACR 访问凭证用户名
#   ACR_PASSWORD      = ACR 访问凭证固定密码
```

- [ ] **Step 4: 校验 YAML 语法**

Run: `python -c "import yaml,sys; yaml.safe_load(open(r'E:\dev\k8s-project\.github\workflows\deploy.yml', encoding='utf-8')); print('YAML OK')"`
Expected: `YAML OK`（若本机无 pyyaml，用 `npx yaml-lint` 或直接人工对照）

- [ ] **Step 5: 提交**

```bash
cd /e/dev/k8s-project
git add .github/workflows/deploy.yml
git commit -m "feat: CI 构建推送 ACR + 部署步骤传凭据(阶段2)"
```

---

### Task 5: 用户前置 — 开通 ACR + 配置 GitHub Secrets（GATE）

**Files:** 无（GitHub 仓库 Settings + 阿里云控制台）

**Interfaces:**
- Consumes: 无
- Produces: Secrets `ACR_REGISTRY`/`ACR_USERNAME`/`ACR_PASSWORD`（Task 4 与 Task 6 依赖）

- [ ] **Step 1: 开通 ACR 个人版（用户，阿里云控制台）**
  1. 控制台搜「容器镜像服务」→ 开通**个人版**（免费）
  2. 创建命名空间 `fchen`
  3. 创建镜像仓库 `lnmp-php`（命名空间 fchen 下，仓库类型「本地仓库」）
  4. 「访问凭证」→ 设置固定登录密码，记下 `ACR_USERNAME`（通常为阿里云账号全名）与固定密码

- [ ] **Step 2: 添加 GitHub Secrets（用户）**
  GitHub 仓库 `chenxuanyeqwq/k8s-monitoring-project` → Settings → Secrets and variables → Actions → New repository secret：
  - `ACR_REGISTRY` = `registry.cn-hangzhou.aliyuncs.com`
  - `ACR_USERNAME` = （上一步的用户名）
  - `ACR_PASSWORD` = （上一步的固定密码）

- [ ] **Step 3: 验证 Secrets 已配（可选核对）**

Run（需 gh 已登录，走代理）: `HTTPS_PROXY=http://127.0.0.1:15490 gh -R chenxuanyeqwq/k8s-monitoring-project secret list`
Expected: 输出包含 `ACR_REGISTRY`/`ACR_USERNAME`/`ACR_PASSWORD`（名称）与 `SERVER_*`

---

### Task 6: 端到端验证（CI 构建 + 服务器只拉镜像）

**Files:** 无新增（用 `workflow_dispatch` 手动触发首次冒烟，避免伪造提交）

**Interfaces:**
- Consumes: Task 1-5 全部产物 + Secrets
- Produces: 验证证据——build 在 Actions、服务器无 build、镜像双 tag、网站 200、内存无峰值

- [ ] **Step 1: push 前面 4 个 commit 到 main（走代理）**

```bash
cd /e/dev/k8s-project
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```
Expected: 推送成功。注意：此次 push 会立即触发 workflow，若 Secrets 未配好 build 步骤会失败（无害，重配后手动触发即可）。

- [ ] **Step 2: 手动触发一次 workflow_dispatch**

GitHub 仓库 → Actions → "Deploy to Aliyun ECS" → Run workflow（选 main）
Expected: 4 步全绿。日志第 ② 步可见 `docker build` + `docker push`（构建发生在 GitHub runner）。

- [ ] **Step 3: 验证镜像已到 ACR + 服务器只有拉取**

Run: `ssh -o BatchMode=yes root@8.217.195.115 'docker images | grep lnmp-php; echo ---; docker ps --format "{{.Names}}\t{{.Status}}"; echo ---; free -h | head -2'`
Expected: `docker images` 出现 `registry.cn-hangzhou.aliyuncs.com/lnmp-php:<sha>` 和 `:latest`；12 容器全 Up；可用内存无明显骤降（无 build 峰值）

- [ ] **Step 4: 网站自检**

Run: `curl -sk --max-time 15 -o /dev/null -w "HTTPS %{http_code} (%{time_total}s)\n" https://www.fchen.xyz`
Expected: `HTTPS 200`

- [ ] **Step 5: 记录当前 sha（回滚测试用）**

Run: `ssh -o BatchMode=yes root@8.217.195.115 'docker inspect lnmp-php --format "{{.Config.Image}}"'`
Expected: 输出形如 `registry.cn-hangzhou.aliyuncs.com/lnmp-php:abc123`，冒号后的 `abc123` 即为回滚用的 sha-A（若输出为镜像 ID sha256:… 则改用 `docker images --format "{{.Repository}}:{{.Tag}}" | grep lnmp-php | grep latest` 取 tag）

---

### Task 7: 回滚验证（真实两版本回滚）

**Files:** 修改 `01-lnmp/php/www/index.php`（加一处可见文案，用于观察回滚效果）

**Interfaces:**
- Consumes: Task 3 的 rollback.sh；Task 6 记录的旧 sha
- Produces: 回滚功能真实验证

- [ ] **Step 1: 加可见文案并 push（部署新版本 = sha-B）**

在 `01-lnmp/php/www/index.php` 页面底部加一行 `<div style="position:fixed;bottom:8px;right:12px;color:#bbb;font-size:12px">build-<时间戳></div>`（时间戳为当前日期），提交并推送：
```bash
cd /e/dev/k8s-project
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```
Expected: Actions 全绿；浏览器/curl 页面出现该行 → 记为 **sha-B**

- [ ] **Step 2: 执行 rollback.sh 回到 sha-A**

```bash
ssh -o BatchMode=yes root@8.217.195.115 'cd /opt/k8s-project/01-lnmp && \
  ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com ACR_USERNAME=<user> ACR_PASSWORD=<pass> \
  bash rollback.sh <sha-A>'
```
Expected: 输出 `✅ 回滚完成: 已回到 <sha-A>`；页面该行文案消失（回到 sha-A 版本）

- [ ] **Step 3: 验证回滚后网站仍 200**

Run: `curl -sk -o /dev/null -w "%{http_code}\n" https://www.fchen.xyz`
Expected: `200`

- [ ] **Step 4: 恢复部署最新版（再 push 一次让 CI 重新部署）**

```bash
cd /e/dev/k8s-project
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```
Expected: Actions 全绿；页面文案再次出现（服务器回到 sha-B+ 的最新版）

---

### Task 8: 文档同步 + 收尾

**Files:**
- Modify: `docs/云服务器部署手册.md`（CI/CD 章节改为"CI 构建 + ACR + 服务器只拉镜像"）
- Modify: `docs/2026-08-27-LNMP-OOM事故记录.md`（待办里勾掉 CI/CD 阶段2）
- Modify: `README.md`（若有 CI/CD 流程描述，同步）

**Interfaces:**
- Consumes: Task 1-7 的全部最终状态
- Produces: 文档与代码一致

- [ ] **Step 1: 更新部署手册 CI/CD 章节**

把「CI/CD」章节从"scp → 服务器 build → compose up"改为"CI 构建推 ACR → 服务器拉镜像 compose up"，并补充 `rollback.sh` 用法与 Secrets 清单（ACR 三项）。

- [ ] **Step 2: 更新 OOM 事故记录待办**

把 `docs/2026-08-27-LNMP-OOM事故记录.md` 的「待办」里勾掉：
```markdown
- [x] CI/CD 阶段 2：构建挪出服务器（deploy.sh 的 `docker build` 挪到 GitHub Actions + 镜像仓库）
```

- [ ] **Step 3: 提交并推送**

```bash
cd /e/dev/k8s-project
git add docs/01-lnmp/php/www/index.php
git commit -m "docs: 同步阶段2 CI/CD 部署手册/事故记录"
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```
Expected: Actions 全绿；文档与线上一致
