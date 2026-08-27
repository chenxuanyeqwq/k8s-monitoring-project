# v4.1 测试进流水线设计（2026-08-27）

## 背景与目标

- **背景**：v4.0 流水线是「CI 构建 → ACR → 服务器只拉 → 自检」，但缺 **CI 段的代码测试**——`service_probe.py` 的 6 个单测只在本机手动跑（`python -m unittest`），改坏逻辑会静默上线（网站照样 200，流水线照样绿）。
- **目标**：让单元测试成为流水线**质量门**——push 先跑测试，不过不构建、不部署。

## 现状 vs 目标

```
现状:  push → checkout → CI构建 → ACR → 服务器拉取 → 自检(200)
目标:  push → checkout → 跑单测(6个) → 全过才继续构建部署 → 自检(200)
```

核心区别：现在的 200 自检是**部署后验证**（CD 段），只证明"网站活着"，证明不了"逻辑写对了"。单测是**部署前质量门**（CI 段），坏逻辑到不了生产。

## 改动清单（只动 1 个文件）

### `.github/workflows/deploy.yml`
1. 触发路径补 `06-blackbox/**`（探测脚本改动也触发流水线 + 测试）
2. checkout 之后、构建之前加一步：
```yaml
- name: 单元测试（service_probe 状态机）
  run: python -m unittest discover -s 06-blackbox -p "test_*.py"
```

### 明确不碰
服务器、compose、deploy.sh、rollback.sh、镜像、A C R 凭据——全部不动。

## 设计决策（面试可讲）

- **测试跑在 GitHub runner**（免费，不占 2G 服务器内存）——测试与构建同机，服务器零负担
- **测试在构建之前** = "坏代码到不了生产"的质量门
- **单管道**：01-lnmp 与 06-blackbox 共用一条流水线，改动探测脚本也会跑测试+部署。个人项目可接受；面试可补一句"项目大了会拆成 test-only 与 deploy 两个 workflow"

## 验证方式

1. 本地 `python -m unittest discover -s 06-blackbox -p "test_*.py"` → 6 个 ok（已跑通）
2. push 触发 CI → 日志可见"单元测试"步骤 6 个 ok，且排在构建之前
3. 恶意改动：临时把 `apply_probe_result` 改坏一个逻辑 → push → 流水线红在测试步（验证门真的拦得住），测完还原

## 范围外（YAGNI）

- 不引入测试框架（unittest 足够）
- 不测 PHP 应用（无测试框架，非本项目核心）
- 监控栈（07-cloud-monitoring）不进流水线
