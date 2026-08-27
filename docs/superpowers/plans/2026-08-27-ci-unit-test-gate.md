# v4.1 测试进流水线实现计划（2026-08-27）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 service_probe 的 6 个单测接进 GitHub Actions，作为部署前的质量门。

**Architecture:** 在 deploy.yml 的 checkout 之后、CI 构建之前插入 `python -m unittest discover` 测试步；触发路径补 `06-blackbox/**`。测试跑在 GitHub runner（免费，不占服务器内存）。

**Tech Stack:** GitHub Actions、Python unittest（stdlib，无额外依赖）

## Global Constraints

- 只改 `.github/workflows/deploy.yml` 一个文件；服务器/compose/deploy.sh/rollback.sh/ACR 一律不碰
- 测试步必须排在构建步（② CI 构建并推送镜像到 ACR）之前
- 触发路径补 `06-blackbox/**`
- 测试命令：`python -m unittest discover -s 06-blackbox -p "test_*.py"`（本地已验 6 个 ok）
- push 走代理 `HTTPS_PROXY=http://127.0.0.1:15490`

---

### Task 1: deploy.yml 插入测试步 + 补触发路径

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `06-blackbox/test_service_probe.py`（已存在，纯 stdlib）
- Produces: 流水线新增"单元测试"步骤，在构建前运行；`06-blackbox/**` 改动可触发流水线

- [ ] **Step 1: 补触发路径**

把 `on.push.paths` 从：
```yaml
    paths:
      - '01-lnmp/**'               # 只有动了 LNMP 代码才触发
      - '.github/workflows/deploy.yml'
```
改为：
```yaml
    paths:
      - '01-lnmp/**'               # 动了 LNMP 代码才触发
      - '06-blackbox/**'           # v4.1：探测脚本改动也触发（跑测试+部署）
      - '.github/workflows/deploy.yml'
```

- [ ] **Step 2: 插入测试步**

在 checkout 步（`uses: actions/checkout@v4`）之后、`② CI 构建并推送镜像到 ACR` 之前插入：
```yaml
      # v4.1：部署前质量门——单元测试不过就不构建不部署
      - name: 单元测试（service_probe 状态机）
        run: python -m unittest discover -s 06-blackbox -p "test_*.py"
```

- [ ] **Step 3: YAML 校验**

Run: `cd /e/dev/k8s-project && npx --yes yaml-lint .github/workflows/deploy.yml 2>&1 | grep -v "npm notice"`
Expected: `√ YAML Lint successful.`

- [ ] **Step 4: 提交**

```bash
cd /e/dev/k8s-project
git add .github/workflows/deploy.yml
git commit -m "feat(v4.1): 单测进流水线作为部署前质量门"
```

---

### Task 2: 推送触发 CI，验证测试步

**Files:** 无

**Interfaces:**
- Consumes: Task 1 的 deploy.yml 改动
- Produces: 验证证据——测试步在构建前运行、6 个 ok

- [ ] **Step 1: 推送（走代理）**

```bash
cd /e/dev/k8s-project
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```

- [ ] **Step 2: 等待并确认 CI 全绿**

Run: `HTTPS_PROXY=http://127.0.0.1:15490 gh -R chenxuanyeqwq/k8s-monitoring-project run list --limit 1 --json databaseId,status,conclusion`
Expected: `conclusion: success`

- [ ] **Step 3: 确认测试步真的跑了且排在建构建前**

Run: `HTTPS_PROXY=http://127.0.0.1:15490 gh -R chenxuanyeqwq/k8s-monitoring-project run view <databaseId> --log` 里搜 `单元测试` 与 `Ran 6 tests`
Expected: 步骤名"单元测试"出现在"CI 构建并推送镜像到 ACR"之前，日志含 `Ran 6 tests ... OK`

- [ ] **Step 4: 验证线上无回归**

Run: `curl -sk -o /dev/null -w "%{http_code}\n" https://www.fchen.xyz`
Expected: `200`

---

### Task 3: 恶意改动验证质量门真能拦（可选但推荐）

**Files:**
- Modify: `06-blackbox/service_probe.py`（临时改坏，测完还原）

- [ ] **Step 1: 改坏一个逻辑**

把 `apply_probe_result` 里"连续失败 3 次告警"阈值临时改成 1（或让成功不重置计数），本地先确认测试红了：
Run: `python -m unittest discover -s 06-blackbox -p "test_*.py"`
Expected: 至少一个 FAIL

- [ ] **Step 2: push 验证 CI 拦在测试步**

```bash
cd /e/dev/k8s-project
HTTPS_PROXY=http://127.0.0.1:15490 git push origin main
```
Expected: 流水线红在"单元测试"步骤（构建/部署未执行）→ 证明坏代码到不了生产

- [ ] **Step 3: 还原并重新验证**

`git revert` 或恢复 service_probe.py → push → CI 恢复绿

---

### Task 4: Release v4.1 + 文档同步

**Files:**
- Modify: 桌面 `IT运维面试学习清单.md`、`Docker-K8s监控项目架构速查.md`（补 v4.1 质量门）
- 记忆文件 `docker-k8s-monitoring-project.md`

- [ ] **Step 1: 建 Release v4.1**

```bash
HTTPS_PROXY=http://127.0.0.1:15490 gh -R chenxuanyeqwq/k8s-monitoring-project release create v4.1 --title "v4.1 测试进流水线：部署前质量门" --target main --notes "..."
```

- [ ] **Step 2: 桌面文档同步**
  - 面试清单追问卡：30 秒自我介绍/一句话速记补"测试质量门"
  - 架构速查：CI/CD 段补测试步

- [ ] **Step 3: 记忆更新**
  在 `docker-k8s-monitoring-project.md` 的 v4.0 段后补 v4.1
