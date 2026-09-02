# CI/CD 标准流程优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CI/CD 流水线从"单 job 直发"升级为标准多阶段流程：质量门测到应用本身、多阶段流水线、生产审批门、部署后安全冒烟——全部在 GitHub 侧，服务器内存零占用。

**Architecture:** 6 个任务，每个独立可交付：① 从 index.php 抽纯函数到 lib.php 并写应用单测 → ② 流水线重构为 lint/test/build/deploy 多 job → ③ 质量门跑全部测试套件 → ④ CI 集成冒烟（真实镜像起 mysql+php，curl 读+写）→ ⑤ 生产审批门（environment 保护）→ ⑥ deploy.sh 加部署后安全冒烟。

**Tech Stack:** GitHub Actions · Docker Compose · PHP 8.2（无框架断言脚本）· Python unittest · shellcheck

## Global Constraints

- **不升级服务器、不迁移 k8s**：所有改动在 CI/GitHub 侧 + deploy.sh（经 CI scp 同步），服务器内存零新增。
- **index.php 行为必须保持不变**：重构后线上渲染与现在完全一致（集成冒烟测试验证读+写）。
- 测试套件运行方式（已确认可独立运行）：
  - `python -m unittest discover -s 06-blackbox -p "test_*.py"`
  - `python -m unittest test_feishu_send`（仓库根，导入 `feishu_send`）
  - `python -m unittest discover -s 07-cloud-monitoring -p "test_*.py"`（导入 `memory_report`，同目录）
- git push 需要 VPN + 代理 `git -c http.proxy=http://127.0.0.1:15490 push origin main`。
- 质量门不通过（任何 job 红）→ 不部署。

---

### Task 1: 抽取纯函数到 lib.php + 应用级 PHP 单测

把 index.php 里的纯逻辑（清洗、校验、转义、渲染、头像）抽到 `lib.php`，index.php 改为调用，并新增无框架断言脚本 `test_guestbook.php`。这是"质量门测到应用本身"的核心。

**Files:**
- Create: `01-lnmp/php/www/lib.php`
- Create: `01-lnmp/php/www/test_guestbook.php`
- Modify: `01-lnmp/php/www/index.php`（改用 lib.php 函数）

**Interfaces:**
- Produces:
  - `clean_input($value): string` — trim + null 安全
  - `is_valid_message(string $name, string $content): bool` — 两者非空
  - `escape($value): string` — `htmlspecialchars($value, ENT_QUOTES, 'UTF-8')` + null 安全
  - `render_content($content): string` — `nl2br(escape($content))`
  - `avatar_initial(string $name): string` — mb_substr 首字符（无 mbstring 时 substr）

- [ ] **Step 1: 创建 lib.php**

```php
<?php
/**
 * 留言板应用纯函数库（2026-09-02 CI/CD 优化抽出）
 * 职责：可被单测的纯函数，不依赖 $_POST / DB / 输出。
 * 使用：index.php require 本文件后调用。
 */

/** 清洗输入：trim；null 安全（空提交返回空串） */
function clean_input($value): string {
    if ($value === null) return '';
    return trim($value);
}

/** 留言是否有效：name 和 content 都非空 */
function is_valid_message(string $name, string $content): bool {
    return $name !== '' && $content !== '';
}

/** HTML 转义（XSS 防护）；null 安全 */
function escape($value): string {
    if ($value === null) return '';
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

/** 渲染内容：转义 + 换行转 <br /> */
function render_content($content): string {
    return nl2br(escape($content));
}

/** 头像首字符（优先 mb_substr 支持多字节） */
function avatar_initial(string $name): string {
    if ($name === '') return '';
    return function_exists('mb_substr') ? mb_substr($name, 0, 1, 'UTF-8') : substr($name, 0, 1);
}
```

- [ ] **Step 2: 创建 test_guestbook.php**

```php
<?php
/**
 * 留言板应用纯函数单元测试（无框架依赖，避免引入 composer/PHPUnit）
 * 运行: php test_guestbook.php   （失败 exit 1，供 CI 质量门使用）
 */
require __DIR__ . '/lib.php';

$failures = 0;

function check(string $name, bool $cond): void {
    global $failures;
    echo $cond ? "  ✅ $name\n" : "  ❌ $name\n";
    if (!$cond) $failures++;
}

echo "clean_input:\n";
check("trim 两侧空格", clean_input("  hello  ") === "hello");
check("空串", clean_input("") === "");
check("null 安全", clean_input(null) === "");

echo "is_valid_message:\n";
check("name+content 合法", is_valid_message("a", "b") === true);
check("name 空则非法", is_valid_message("", "b") === false);
check("content 空则非法", is_valid_message("a", "") === false);

echo "escape:\n";
check("XSS 标签转义", escape("<script>alert(1)</script>") === "&lt;script&gt;alert(1)&lt;/script&gt;");
check("null 安全", escape(null) === "");

echo "render_content:\n";
check("转义 + 换行转 <br />", render_content("<b>a\nb</b>") === "&lt;b&gt;a<br />\nb&lt;/b&gt;");

echo "avatar_initial:\n";
check("取首字符(多字节)", avatar_initial("张三") === "张");
check("空名返回空", avatar_initial("") === "");

if ($failures > 0) {
    echo "\n❌ $failures 个用例失败\n";
    exit(1);
}
echo "\n✅ 全部通过\n";
```

- [ ] **Step 3: 本地运行验证（Docker 里的 php:8.2-cli，无需本机装 PHP）**

Run: `docker run --rm -v "/e/dev/k8s-project/01-lnmp/php/www:/app" php:8.2-cli php /app/test_guestbook.php`
Expected: 输出含 "✅ 全部通过"，exit 0。
（若 avatar_initial 用例因缺 mbstring 失败，先 `php -m | grep mbstring` 确认；Docker 官方 php:8.2-cli 默认含 mbstring。）

- [ ] **Step 4: index.php 接入 lib.php（保持行为不变）**

在 `01-lnmp/php/www/index.php` 做以下精确替换：

1. 第 7 行 `date_default_timezone_set(...)` 之后插入：
```php
require __DIR__ . '/lib.php';
```
2. `die("数据库连接失败：" . htmlspecialchars($e->getMessage()));` → `die("数据库连接失败：" . escape($e->getMessage()));`
3. `$name    = trim($_POST['name'] ?? '');` → `$name    = clean_input($_POST['name'] ?? null);`
4. `$content = trim($_POST['content'] ?? '');` → `$content = clean_input($_POST['content'] ?? null);`
5. `if ($name !== '' && $content !== '') {` → `if (is_valid_message($name, $content)) {`
6. `$initial = function_exists('mb_substr') ? mb_substr($m['name'], 0, 1, 'UTF-8') : substr($m['name'], 0, 1);` → `$initial = avatar_initial($m['name']);`
7. `<?= htmlspecialchars($initial) ?>` → `<?= escape($initial) ?>`
8. `<?= htmlspecialchars($m['name']) ?>` → `<?= escape($m['name']) ?>`
9. `<?= htmlspecialchars($m['created_at']) ?>` → `<?= escape($m['created_at']) ?>`
10. `<?= nl2br(htmlspecialchars($m['content'])) ?>` → `<?= render_content($m['content']) ?>`

- [ ] **Step 5: 再跑一次单测确认重构没破坏函数**

Run: `docker run --rm -v "/e/dev/k8s-project/01-lnmp/php/www:/app" php:8.2-cli php /app/test_guestbook.php`
Expected: 仍 "✅ 全部通过"。

- [ ] **Step 6: Commit**

```bash
git add 01-lnmp/php/www/lib.php 01-lnmp/php/www/test_guestbook.php 01-lnmp/php/www/index.php
git -c http.proxy=http://127.0.0.1:15490 commit -m "feat(ci): 抽取 index.php 纯函数到 lib.php + 应用级 PHP 单测"
```

---

### Task 2: 流水线重构为多阶段（lint → test → build → deploy）

把 deploy.yml 从单 job 重构为 4 个 job（`needs` 串联 + concurrency 防旧覆盖）。此任务质量门保持现状（只跑 06-blackbox），下一任务再补全测试。

**Files:**
- Modify: `.github/workflows/deploy.yml`（整体重写）

**Interfaces:**
- Produces: jobs `lint` / `test` / `build` / `deploy`；deploy job 后续任务会加 `environment: production`。
- Consumes: secrets `SERVER_HOST/SERVER_USER/SERVER_PASSWORD/ACR_REGISTRY/ACR_USERNAME/ACR_PASSWORD`。

- [ ] **Step 1: 重写 deploy.yml 为多阶段**

`.github/workflows/deploy.yml` 全文替换为：

```yaml
name: Deploy to Aliyun ECS

on:
  push:
    branches: [main]
    paths:
      - '01-lnmp/**'
      - '06-blackbox/**'
      - '.github/workflows/deploy.yml'
  workflow_dispatch: {}

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: PHP 语法检查
        uses: shivammathur/setup-php@v2
        with:
          php-version: '8.2'
      - name: php -l 全部 PHP 文件
        run: |
          php -l 01-lnmp/php/www/index.php
          php -l 01-lnmp/php/www/lib.php
          php -l 01-lnmp/php/www/test_guestbook.php
      - name: shellcheck 部署脚本
        run: |
          sudo apt-get update -q
          sudo apt-get install -y -q shellcheck
          shellcheck 01-lnmp/deploy.sh 01-lnmp/rollback.sh
      - name: Python 语法检查
        run: python -m py_compile test_feishu_send.py feishu_send.py 06-blackbox/service_probe.py 06-blackbox/test_service_probe.py

  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: 单元测试（service_probe 状态机）
        run: python -m unittest discover -s 06-blackbox -p "test_*.py"

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: 构建并推送镜像到 ACR
        env:
          ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
          ACR_USERNAME: ${{ secrets.ACR_USERNAME }}
          ACR_PASSWORD: ${{ secrets.ACR_PASSWORD }}
        run: |
          docker build --build-arg APP_BUILD=${GITHUB_SHA} \
            -t "${ACR_REGISTRY}/fchen/lnmp-php:${GITHUB_SHA}" \
            -t "${ACR_REGISTRY}/fchen/lnmp-php:latest" ./01-lnmp/php
          echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin
          docker push "${ACR_REGISTRY}/fchen/lnmp-php:${GITHUB_SHA}"
          docker push "${ACR_REGISTRY}/fchen/lnmp-php:latest"

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: 上传 01-lnmp 到服务器
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          password: ${{ secrets.SERVER_PASSWORD }}
          source: "01-lnmp"
          target: "/opt/k8s-project"
      - name: 远程执行部署
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

- [ ] **Step 2: 推送并确认 CI 全绿**

Run: `git -c http.proxy=http://127.0.0.1:15490 push origin main`，然后 `gh run list --workflow=deploy.yml --limit 1` 看运行。
Expected: lint/test/build/deploy 4 个 job 全绿；线上 `https://www.fchen.xyz` 仍 200。

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git -c http.proxy=http://127.0.0.1:15490 commit -m "ci: 流水线重构为多阶段 lint→test→build→deploy + 并发取消"
```

---

### Task 3: 质量门补齐全部测试套件

test job 从只跑 06-blackbox 扩展为三个 Python 套件 + PHP 应用测试。这就是"质量门测的是要部署的应用"的直接证据。

**Files:**
- Modify: `.github/workflows/deploy.yml`（test job）

**Interfaces:**
- Consumes: Task 1 的 `test_guestbook.php` + `lib.php`。
- Produces: test job 运行全部套件（lint → test 的 `needs` 不变）。

- [ ] **Step 1: 替换 test job 的步骤**

把 test job 的 steps 替换为：

```yaml
    steps:
      - uses: actions/checkout@v4
      - name: Python 单元测试（全部套件）
        run: |
          python -m unittest discover -s 06-blackbox -p "test_*.py"
          python -m unittest test_feishu_send
          python -m unittest discover -s 07-cloud-monitoring -p "test_*.py"
      - name: PHP 应用单元测试
        uses: shivammathur/setup-php@v2
        with:
          php-version: '8.2'
          extensions: mbstring
      - name: 运行 PHP 应用测试
        run: php 01-lnmp/php/www/test_guestbook.php
```

- [ ] **Step 2: 推送并确认 test job 全绿**

Run: push + `gh run watch <run-id> --exit-status`。
Expected: test job 绿（3 Python 套件 + PHP 单测全过）；若 test_feishu_send 或 test_memory_report 报错，修复导入路径后再推。

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git -c http.proxy=http://127.0.0.1:15490 commit -m "ci: 质量门跑全部测试套件（3×Python + PHP 应用单测）"
```

---

### Task 4: CI 集成冒烟测试（真实镜像 + MySQL，读/写验证）

build job 在构建后、推送前，用 `docker-compose.test.yml` 起 mysql + 刚构建的 php 镜像，curl 读页面 + POST 留言 + 确认落库。测的是**即将部署的那个镜像**。失败则 build 红、不推送、不部署。

**Files:**
- Create: `01-lnmp/docker-compose.test.yml`
- Modify: `.github/workflows/deploy.yml`（build job 加步骤 + 加 test 镜像 tag）

**Interfaces:**
- Consumes: build job 刚构建的本地镜像（tag `test-${GITHUB_SHA}`）。
- Produces: 集成冒烟通过后，才 `docker push`。

- [ ] **Step 1: 创建 docker-compose.test.yml**

`01-lnmp/docker-compose.test.yml`：

```yaml
# CI 集成冒烟测试专用（2026-09-02 新增）
# 只在 GitHub Actions runner 上跑，不碰服务器。
# 用真实 mysql:8.0 + 刚构建的 php 镜像，验证读/写全链路。
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: guestbook
      MYSQL_USER: guest
      MYSQL_PASSWORD: guest123
    volumes:
      - ./mysql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-proot123"]
      interval: 2s
      timeout: 3s
      retries: 30

  php:
    image: ${TEST_IMAGE}
    command: php -S 0.0.0.0:8080 -t /var/www/html
    environment:
      MYSQL_HOST: db
      MYSQL_DATABASE: guestbook
      MYSQL_USER: guest
      MYSQL_PASSWORD: guest123
    volumes:
      - ./php/www:/var/www/html
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8080:8080"
```

- [ ] **Step 2: 改 build job——构建加 test tag、构建后跑集成冒烟、通过才推送**

build job 的 run 替换为：

```yaml
      - name: 构建镜像
        env:
          ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
        run: |
          docker build --build-arg APP_BUILD=${GITHUB_SHA} \
            -t "${ACR_REGISTRY}/fchen/lnmp-php:${GITHUB_SHA}" \
            -t "${ACR_REGISTRY}/fchen/lnmp-php:test-${GITHUB_SHA}" \
            -t "${ACR_REGISTRY}/fchen/lnmp-php:latest" ./01-lnmp/php
      - name: 集成冒烟测试（起真实镜像，curl 读+写）
        env:
          TEST_IMAGE: ${{ secrets.ACR_REGISTRY }}/fchen/lnmp-php:test-${{ github.sha }}
        run: |
          cd 01-lnmp
          docker compose -f docker-compose.test.yml up -d
          # 等待应用就绪（db healthy + php 起来，最多 80s）
          code=""
          for i in $(seq 1 40); do
            code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ || true)
            [ "$code" = "200" ] && break
            sleep 2
          done
          [ "$code" = "200" ] || { echo "❌ 应用未就绪 code=$code"; docker compose -f docker-compose.test.yml logs php; exit 1; }
          # 读：页面渲染出表单
          curl -s http://localhost:8080/ | grep -q "写点什么" || { echo "❌ 读失败：页面未渲染"; exit 1; }
          # 写：POST 一条留言
          curl -s -X POST -d "name=ci&content=ci-smoke-$(date +%s)" http://localhost:8080/ -o /dev/null
          # 再读：确认留言落库
          curl -s http://localhost:8080/ | grep -q "ci-smoke" || { echo "❌ 写失败：留言未落库"; exit 1; }
          echo "✅ 集成冒烟通过（读 + 写）"
          docker compose -f docker-compose.test.yml down -v
      - name: 推送镜像到 ACR
        env:
          ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
          ACR_USERNAME: ${{ secrets.ACR_USERNAME }}
          ACR_PASSWORD: ${{ secrets.ACR_PASSWORD }}
        run: |
          echo "$ACR_PASSWORD" | docker login "$ACR_REGISTRY" -u "$ACR_USERNAME" --password-stdin
          docker push "${ACR_REGISTRY}/fchen/lnmp-php:${GITHUB_SHA}"
          docker push "${ACR_REGISTRY}/fchen/lnmp-php:latest"
```

> 注意：集成冒烟在 **push 之前**，失败则本步红、后续"推送镜像"不执行、deploy 因 needs: build 不触发。

- [ ] **Step 3: 推送并确认集成冒烟通过**

Run: push + watch CI。
Expected: build job 三步全绿（构建 → 集成冒烟 → 推送）；线上 200。

- [ ] **Step 4: Commit**

```bash
git add 01-lnmp/docker-compose.test.yml .github/workflows/deploy.yml
git -c http.proxy=http://127.0.0.1:15490 commit -m "ci: 集成冒烟测试（真实镜像起 mysql+php，curl 读+写）"
```

---

### Task 5: 生产审批门（environment 保护）

deploy job 加 `environment: production`，并用 gh api 配置 required reviewers（审批人为用户本人）。push 后 CI 自动跑到 build，**部署前暂停等人点 Approve**。

**Files:**
- Modify: `.github/workflows/deploy.yml`（deploy job 加一行）
- 配置：GitHub 仓库环境保护（gh api）

**Interfaces:**
- Consumes: build 成功产物（ACR 镜像）。
- Produces: deploy 受审批保护。

- [ ] **Step 1: deploy job 加 environment**

在 deploy job 中加一行（`runs-on` 之后）：

```yaml
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
```

- [ ] **Step 2: 创建 environment 并配置审批人**

```bash
# 创建 environment（若已存在则跳过）
gh api -X PUT repos/chenxuanyeqwq/k8s-monitoring-project/environments/production --silent || true
# 拿当前用户 id
UID=$(gh api user --jq .id)
# 配置 required reviewers（审批人 = 用户本人）
gh api -X POST repos/chenxuanyeqwq/k8s-monitoring-project/environments/production/protection-rules \
  -f type=required_reviewers \
  -F "reviewers[][type]=User" -F "reviewers[][id]=$UID" --silent && echo "审批门配置完成"
```

- [ ] **Step 3: 推送并验证"停在审批"**

Run: push + `gh run list --workflow=deploy.yml --limit 1`。
Expected: lint/test/build 全绿，deploy job 显示 **Waiting for approval**（不自动执行）。
然后点 GitHub 上 Approve，deploy 完成，线上 200。
（若 GitHub Free 公共仓库不支持 required_reviewers（报错 422），**回退方案**：deploy 触发方式改 `workflow_dispatch` 手动触发，同样构成人工 gate，面试照讲"生产部署需人工确认"。）

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml
git -c http.proxy=http://127.0.0.1:15490 commit -m "ci: 生产部署加审批门（environment: production + required reviewers）"
```

---

### Task 6: 部署后安全冒烟（防 scp 冲掉加固）

deploy.sh 在 HTTP 200 自检之后追加安全冒烟：敏感路径应 444、未知路径应 404。任一失败则部署标红，防止 v4.3 加固被旧配置冲掉却无人察觉。

**Files:**
- Modify: `01-lnmp/deploy.sh`（末尾追加）

**Interfaces:**
- Consumes: deploy.sh 现有 `[3/3] 自检` 逻辑。
- Produces: 部署后的安全回归校验。

- [ ] **Step 1: deploy.sh 追加安全冒烟**

在 deploy.sh 现有自检逻辑之后追加：

```bash
echo "==> [4/4] 安全冒烟（加固回归校验）"
for path in "/.env" "/actuator"; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost$path" || true)
  echo "  $path -> $code (期望 444)"
  if [ "$code" != "444" ]; then
    echo "❌ 安全冒烟失败: $path 返回 $code，加固可能被冲掉"
    exit 1
  fi
done
code=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost/definitely-not-a-real-path-xyz" || true)
echo "  未知路径 -> $code (期望 404)"
if [ "$code" != "404" ]; then
  echo "❌ 安全冒烟失败: 未知路径返回 $code"
  exit 1
fi
echo "✅ 安全冒烟通过: 加固未被冲掉"
```

> 依据（v4.3 加固）：nginx 对 `/.env`、`/actuator` 等敏感路径返回 444，未知路径 `=404`。

- [ ] **Step 2: 推送触发一次部署，确认安全冒烟通过**

Run: push + watch CI deploy job。
Expected: deploy job 绿，deploy.sh 输出含 "✅ 安全冒烟通过"。

- [ ] **Step 3: 在服务器确认新 deploy.sh 已同步**

Run: `ssh root@8.217.195.115 'grep -n "安全冒烟" /opt/k8s-project/01-lnmp/deploy.sh'`
Expected: 输出含 `[4/4] 安全冒烟`。

- [ ] **Step 4: Commit**

```bash
git add 01-lnmp/deploy.sh
git -c http.proxy=http://127.0.0.1:15490 commit -m "ci: deploy.sh 追加部署后安全冒烟（敏感路径444/未知路径404）"
```

---

## 收尾

- [ ] 全部 6 任务完成后，跑一次完整验证：`curl -sk https://www.fchen.xyz` 200；`gh run list` 历史全绿。
- [ ] 更新 `docs/2026-09-02-资源耗竭事故记录.md` 或 README 版本记录（可选，v4.5 版本号待定）。
- [ ] 面试讲法已含在设计文档 `docs/superpowers/specs/2026-09-02-ci-cd-standard-design.md` 第六节。
