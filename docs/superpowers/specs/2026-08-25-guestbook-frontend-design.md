# 留言板前端优化 · 设计文档

> 日期：2026-08-25 ｜ 状态：已评审 ｜ 源码：`E:\dev\k8s-project\01-lnmp\php\www\index.php`

## 目标与范围

对已上云、全链路打通的 LNMP 留言板做**前端视觉升级 + 轻交互**,不改后端。

- **范围**：视觉升级(清爽现代 SaaS 风)+ 四个轻交互(友好时间 / 提交提示 / 精致空状态 / 移动端适配)
- **实现方式**：**方案 A——单文件内联改造**,全部改动集中在 `index.php`,CI/CD 自动部署
- **明确不做**：不引入框架/CDN、不新增数据库字段、不改 `docker-compose.yml`、不动后端查询逻辑
- **成功标准**：`http://8.217.195.115:8080` 刷新后看到新设计;提交留言有反馈;手机上排版正常;时间显示友好

## 视觉设计系统

### 设计令牌(CSS 变量,全部样式由此派生)

```css
:root {
  --accent:   #3b82f6;   /* 主强调色 · 蓝 */
  --accent-bg:#eff6ff;   /* 强调色浅底 */
  --bg:       #f6f8fa;   /* 页面背景 */
  --card:     #ffffff;   /* 卡片白 */
  --text:     #1f2937;   /* 主文字 */
  --muted:    #6b7280;   /* 次要文字(时间/说明) */
  --border:   #e5e7eb;   /* 细边框 */
  --radius:   12px;      /* 统一圆角 */
  --shadow:   0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow-lg:0 6px 16px rgba(0,0,0,.10);   /* hover 加深阴影 */
}
```

### 字体排印
- 字体栈:`system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`
- 标题 `1.5rem/700` ｜ 说明 `0.85rem/--muted` ｜ 正文 `1rem/行高1.6` ｜ 时间 `0.8rem/--muted`

### 组件语言
| 组件 | 设计 |
|------|------|
| 页面容器 | `max-width:640px` 水平居中,`padding:2rem 1rem` |
| 表单卡片 | 白底圆角 12px + 细边框 + 轻阴影;输入框聚焦 `--accent` 光圈 |
| 留言卡片 | 白底圆角;hover 上浮 + `--shadow-lg` |
| 头像 | 名字首字母 + 蓝底白字圆形(纯 CSS) |
| 提交按钮 | `--accent` 底白字圆角,hover 变深;移动端全宽 |
| Toast | 顶部固定居中,绿底白字,上滑淡入,3s 自动淡出 |
| 空状态 | 居中大 emoji `✨` + 两行引导文案 |

## 页面结构与交互

### index.php 内部组织(单文件)
```
PHP 顶部
 ├─ 处理 POST → 插入留言 → header('Location: index.php?posted=1')(PRG,防重复提交)
 ├─ $showToast = isset($_GET['posted'])
 ├─ 输出时间时:date('c', strtotime($t . ' UTC')) → ISO 带时区(供 JS)
 └─ 查询最近 50 条留言
HTML
 ├─ <head> 内联 CSS(设计系统)
 ├─ <body>
 │   ├─ Toast(有 posted 才渲染)
 │   ├─ <main> 容器:header / form 卡片 / 留言列表或空状态
 └─ <script>:toast 自动淡出 + 时间相对化
```

### 交互① 提交提示(PRG + Toast)
- 提交成功 → 重定向 `?posted=1`(现状已是 PRG,保留)
- 页面检测到 `posted=1` → 渲染绿色 toast「✓ 留言已发布」→ CSS 上滑淡入 → JS `setTimeout` 3s 加 `.hide` 淡出

### 交互② 友好时间(纯前端方案)
- **时区坑**：容器默认 UTC,与国内差 8 小时;直接 `strtotime` 相对时间会偏 8h
- **解法**：PHP 输出 `<time datetime="ISO">`,ISO 由 `date('c', strtotime($t.' UTC'))` 生成(把存储的 UTC 串按 UTC 解析再转 ISO);JS 用 `new Date(datetime)` 在**浏览器本地时区**计算相对时间
- 显示规则：`<60s` 刚刚 / `<1h` x 分钟前 / `<24h` x 小时前 / `<7d` 昨天或 x 天前 / 更早 `Y-m-d H:i`

### 交互③ 精致空状态
- `if (empty($messages))`:居中 `✨` + 「还没有留言,来抢第一条吧」 + 小字「在上面的表单写下第一句话」

### 交互④ 移动端适配
- 保留 `<meta name="viewport">`(已存在)
- `@media (max-width:480px)`:容器 padding 收窄、输入框与按钮全宽、卡片间距收紧、触控目标 ≥ 44px

## 边界情况与错误处理
- **时区**：以 JS 本地时区为准,服务器 UTC 不影响显示;如需改回服务端渲染,后续可给 mysql 容器加 `TZ=Asia/Shanghai`
- **重复提交**：PRG 已防;toast 只在 `?posted=1` 时出现一次,刷新后消失
- **XSS/SQL 注入**：沿用现有 `prepare` + `htmlspecialchars`,新代码不引入未经转义输出
- **兼容**：仅依赖现代浏览器基础能力(变量、flex、transition),无外部依赖

## 测试与验收
1. 本地 `docker compose up -d --build` 后访问 `localhost:8080` 目检:布局、配色、空状态
2. 提交一条留言 → 看到绿色 toast → 列表出现新留言 + 相对时间
3. 改 `<480px` 窗口宽度 → 表单全宽、不拥挤
4. 断网/清空留言(临时)验证空状态文案
5. 验证通过后 `git push` → GitHub Actions 自动部署 → 刷新 `http://8.217.195.115:8080` 公网复核

## 交付物
- 仅修改 `01-lnmp/php/www/index.php`(约 250~300 行)
- 无新增文件、无新增依赖、无数据库改动
