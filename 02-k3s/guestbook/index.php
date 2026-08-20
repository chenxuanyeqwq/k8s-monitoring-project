<?php
/**
 * 留言板 - k8s 部署版（SQLite 存储）
 * 说明：k8s 演示用单容器 nginx+php-fpm，数据存 SQLite（挂载 /data 目录）。
 *      多副本时各副本数据独立，生产环境应改用 StatefulSet + PVC + 数据库。
 *      页面顶部显示镜像内嵌的 APP_VERSION，用于演示滚动更新（v1 -> v2 -> 回滚）。
 */

// SQLite 连接（/data 由 k8s emptyDir 挂载，entrypoint 里已 chmod 777）
$db = new PDO('sqlite:/data/guestbook.db');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->exec("CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");

// 提交留言（prepared statement 防注入）
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name    = trim($_POST['name'] ?? '');
    $content = trim($_POST['content'] ?? '');
    if ($name !== '' && $content !== '') {
        $stmt = $db->prepare("INSERT INTO messages (name, content) VALUES (?, ?)");
        $stmt->execute([$name, $content]);
    }
    header('Location: index.php');
    exit;
}

$version  = getenv('APP_VERSION') ?: 'dev';
$messages = $db->query("SELECT * FROM messages ORDER BY created_at DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>留言板 v<?= htmlspecialchars($version) ?></title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  form { background: #f6f8fa; padding: 1rem; border-radius: 8px; }
  input, textarea { width: 100%; padding: .5rem; margin: .25rem 0; box-sizing: border-box; }
  li { margin: 1rem 0; list-style: none; background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: .75rem; }
  .meta { color: #586069; font-size: .85rem; }
  .badge { display: inline-block; padding: .15rem .5rem; border-radius: 999px; font-size: .8rem; background: #e8f0fe; color: #1a73e8; }
</style>
</head>
<body>
<h1>📌 留言板 <span class="badge"><?= htmlspecialchars($version) ?></span></h1>
<p class="meta">k8s Deployment 部署 · 3 副本 · Nginx+PHP-FPM · SQLite</p>

<form method="post">
  <input name="name" placeholder="你的名字" required>
  <textarea name="content" placeholder="写点什么…" rows="3" required></textarea>
  <button type="submit">提交留言</button>
</form>

<ul>
<?php if (empty($messages)): ?>
  <li class="meta">还没有留言，来抢第一条吧。</li>
<?php else: foreach ($messages as $m): ?>
  <li>
    <div><strong><?= htmlspecialchars($m['name']) ?></strong></div>
    <div><?= nl2br(htmlspecialchars($m['content'])) ?></div>
    <div class="meta"><?= htmlspecialchars($m['created_at']) ?></div>
  </li>
<?php endforeach; endif; ?>
</ul>
</body>
</html>
