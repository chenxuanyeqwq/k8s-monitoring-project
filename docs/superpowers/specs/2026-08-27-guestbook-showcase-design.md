# 留言板项目展示重构设计（2026-08-27）

## 背景与目标

- **背景**：用户把 `https://www.fchen.xyz` 写进 BOSS 打招呼语，HR 点进来应 10 秒内看懂"这人做了什么"（Docker/K8s/监控/CI-CD），从而产生兴趣。
- **目标**：把留言板改造成"留言功能 + 项目展示"一体——信息卡摆出技术栈/可观测性/CI-CD，附版本记录、Grafana 静态截图、监控状态点。不破坏留言板 UX 与安全基线。

## 设计决策

| 决策点 | 选择 |
|--------|------|
| 展示强度 | 信息卡（中等），不喧宾夺主 |
| 版本展示 | 当前 `v4.1` + `<details>` 可折叠版本记录（v1.0→v4.1）|
| Grafana 展示 | **静态截图** `grafana.png`（用户自己截图，零内存负担，绕开吃内存的渲染器）|
| 访客访问实时看板 | 不在公网页面写账号；"联系索取只读 Viewer 访客账号"（BOSS 对话里给）|
| 监控状态 | 标题旁"● 在线监控中"状态点（纯 CSS 动效）|

## 页面结构（改动后）

```
header:  LNMP 留言板 [● 在线监控中]
         运行于阿里云 · Docker+K8s · Prometheus · CI/CD
项目信息卡: 📦 项目信息 [v4.1]
          架构 / 部署 / 可观测性 / CI-CD 四行
          ▾ 版本记录 v1.0→v4.1（可折叠）
Grafana 截图: <img grafana.png> + 说明（联系索取只读访客账号）
留言表单:（原样保留）
留言列表:（原样保留）
footer:  Powered by Docker+K8s+Prometheus · GitHub · v4.1
```

## 文件改动

- **Modify**: `01-lnmp/php/www/index.php`（加 CSS + 信息卡 + 截图 + footer）
- **Add**: `01-lnmp/php/www/grafana.png`（静态截图，243KB）

## 明确不碰

- 留言提交/展示逻辑、安全基线（prepare / htmlspecialchars / PRG）
- 数据库结构、compose、监控栈
- 移动端适配保持（新元素纳入现有响应式）

## 验证方式

1. push → CI/CD 部署 → `https://www.fchen.xyz` 200
2. 页面含信息卡/版本记录/截图，截图正常加载（`curl` 到 `https://www.fchen.xyz/grafana.png` 200）
3. 移动端不破版（窄屏检查）
4. 顺手清理测试留言（`DELETE FROM messages WHERE ...`）

## 范围外（YAGNI）

- Grafana 实时 iframe 嵌入（v4.2，需 nginx 反代 + 匿名访问，本次不做）
- Viewer 访客账号创建（用户在 Grafana 后台自建，或按需配匿名只读）
