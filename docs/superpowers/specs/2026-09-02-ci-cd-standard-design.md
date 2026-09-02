# CI/CD 标准流程优化设计（2026-09-02）

> 触发：面试官质疑"不是完整 CI/CD，只是 git webhook 上云镜像部署"。
> 目标：让流水线具备**标准 CI/CD 要素**，且每项改动都能一句话讲清楚（面试可解释）。
> 约束：**不升级服务器、不迁移 k8s**——所有改动都在 CI/GitHub 侧，服务器内存零占用。

## 一、现状与问题

当前流水线（`deploy.yml`）：

```
push(main) → 单job: unittest(仅06-blackbox) → docker build → push ACR → scp → ssh deploy.sh → 自检200
```

暴露的问题（面试官所指"不完整"的实锤）：

| 问题 | 说明 |
|---|---|
| 质量门没测应用 | 3 个测试套件只跑 1 个；没有任何测试在测 index.php / MySQL 逻辑 |
| 无静态检查 | 无 lint（PHP 语法、Shell 脚本） |
| 无部署治理 | 无审批门、无 environment 隔离，push 即上线 |
| 部署隐患 | scp 可能冲掉服务器加固配置，且无部署后安全校验 |

## 二、设计主线（三阶段，按面试性价比排序）

### 阶段 1：质量门补齐 —— "我测的是要部署的那个应用"

**目标话术**：*"我的流水线有质量门，测的是要部署的应用本身（单测 + 集成冒烟），坏代码到不了生产。"*

**1.1 全部测试进质量门**
- 现在 CI 只跑 `discover -s 06-blackbox`。补上另外两个已有套件：
  - `test_feishu_send.py`（10 用例，仓库根）
  - `07-cloud-monitoring/test_memory_report.py`
- deploy.yml 测试步骤改为依次运行三个套件。

**1.2 应用级 PHP 单测**
- 从 `01-lnmp/php/www/index.php` 抽**纯函数**到新文件 `01-lnmp/php/www/lib.php`：
  - `sanitize_message(string $raw): string` —— XSS 转义 + trim + 长度校验
  - （可再抽 1-2 个纯函数：友好时间格式化、空消息判断）
- `index.php` include `lib.php`，行为不变（重构需保证线上一致）。
- 新增 `01-lnmp/php/www/test_guestbook.php`：**无框架依赖**的断言脚本（避免 composer/PHPUnit 引入，面试讲"PHP 单元测试"即可），失败 `exit 1`。
- CI 用 `shivammathur/setup-php@v2` 装 PHP，跑 `php test_guestbook.php`。

**1.3 CI 集成冒烟测试（测"将要部署的镜像"）**
- 新增 `01-lnmp/docker-compose.test.yml`：在 CI runner 上起 `mysql:8.0` + **刚构建的 php 镜像**（复用正式 compose 的 `db`/`php` 服务名与 DB 初始化）。
- CI 步骤（build 之后、push 之前）：
  1. `docker compose -f docker-compose.test.yml up -d`
  2. 轮询等待就绪
  3. curl 应用断言 200 + 页面含预期内容（读）
  4. POST 一条留言 → 再查页面确认落库（写）
  5. `down -v` 清理
- 验证的是"即将部署的那个 artifact"，不是别的。

### 阶段 2：流程标准化 —— "标准 CI/CD 流程 + 生产部署有审批"

**目标话术**：*"流水线是多阶段的：lint → 测试 → 构建 → 审批 → 部署，生产部署受保护。"*

**2.1 多阶段流水线（重构 deploy.yml 为多 job）**

```
jobs:
  lint:    php -l 全部 php 文件 + shellcheck deploy.sh/rollback.sh
  test:    needs lint → python 三套件 + php 应用测试
  build:   needs test → docker build + push ACR（sha+latest 双 tag）
  deploy:  needs build → scp + ssh deploy.sh → environment: production
```

- `concurrency: cancel-in-progress`：旧提交的部署被新提交取代，避免串跑。
- 各阶段独立失败即停，坏代码进不了下一阶段。

**2.2 生产审批门**
- `deploy` job 加 `environment: production`。
- 用 `gh api` 配置该 environment 的 **required reviewers**（审批人为用户本人）。
- 效果：push → CI 自动验证 → 停在 deploy → 用户在 GitHub 点 **Approve** → 才部署生产。
- 风险与回退：若 GitHub Free 公共仓库不支持 required reviewers（需验证），回退方案为 deploy 改为 `workflow_dispatch`（手动触发），同样构成"人工 gate"，面试照讲。

### 阶段 3：部署可靠性 —— "部署不会悄悄破坏配置"

**目标话术**：*"我部署后会做安全冒烟，如果部署把加固冲掉了，CI 会标红。"*

**3.1 部署后安全冒烟（防 scp 冲掉加固）**
- `deploy.sh` 末尾（现有 HTTP 200 自检之后）追加安全冒烟：
  - `/.env` → 期望 444（敏感路径）
  - `/actuator` → 期望 444
  - 未知路径 → 期望 404
- 任一失败 → `exit 1`，部署标记失败，人工介入。
- 意义：v4.3 的加固如果被旧配置冲掉，部署立刻红，而不是线上裸奔没人知道。

## 交付策略

- 三阶段**各自独立可交付、可停止**：做完阶段 1 就已解决面试官"没测应用"的核心质疑；阶段 2 补流程外观；阶段 3 补工程细节。
- 每个阶段完成即推 GitHub 触发 CI 验证，全绿后才进入下一阶段。

## 三、数据流（新流水线）

```
push(main)
  │
  ├─ job lint ────── php -l / shellcheck ──────────── 失败即停
  ├─ job test ────── python×3套件 + php应用单测 ────── 失败即停
  ├─ job build ───── 构建镜像 → push ACR(sha+latest) ─ 失败即停（线上无影响）
  ├─ environment: production ── 人工 Approve ───────── 未批不部署
  └─ job deploy ──── scp + deploy.sh(拉镜像+自检+安全冒烟) → 上线
```

## 四、错误处理与回滚

| 场景 | 行为 |
|---|---|
| lint/test/build 任一失败 | 流水线红，不进入下一阶段；线上不受影响 |
| 审批未通过 | deploy 不执行 |
| 部署自检 200 失败 | deploy.sh exit 1（现有逻辑），可 `rollback.sh <sha>` |
| 部署后安全冒烟失败 | deploy.sh exit 1，人工介入（**新增**） |
| 并发 push | concurrency 取消旧 run，避免旧覆盖新 |

## 五、测试策略

- 阶段 1 本身就是写测试：应用单测 + 集成冒烟。
- 验收标准 = CI 全绿 + 线上功能正常（curl 读/写验证）。
- 阶段 3 的安全冒烟是部署后的"回归测试"。

## 六、面试讲法（配合每阶段，一页纸）

**主话术（30 秒）**：
> "我的 CI/CD 是标准的多阶段流水线：lint → 测试 → 构建 → 审批 → 部署。质量门测的是要部署的应用——有 PHP 单元测试和集成冒烟测试，坏代码到不了生产。生产部署有审批门保护，部署后有自检和安全冒烟。整个流程产物带 commit sha 可追溯，可一键回滚。"

**追问应对**：
| 追问 | 答 |
|---|---|
| 测的是什么？ | 应用本身的单测（消息校验纯函数）+ 集成冒烟（起 mysql+php 真实镜像 curl 读/写） |
| staging 呢？ | CI 的集成测试就是预发布验证；因个人项目成本，未拆独立 staging 环境，生产前有审批兜底 |
| 为什么用 compose 不用 k8s？ | 2G 单机成本约束；云原生部署形态在 02-k3s 模块有验证（Deployment/Ingress/滚动） |
| 审批门怎么实现？ | GitHub Actions environment 保护规则，required reviewers |

## 七、不做（YAGNI）

- ❌ 独立 staging 环境（服务器约束，不新增容器）
- ❌ k8s 迁移（服务器约束，暂缓）
- ❌ PHPUnit 框架（轻量断言脚本够用；面试讲"PHP 单元测试"即可，后续可选升级）
- ❌ 依赖缓存优化（性价比低，不影响面试）
- ❌ 测试覆盖率报告（过度工程）
