<?php
/**
 * LNMP 留言板
 * 链路：Nginx -> PHP-FPM -> MySQL
 * 功能：展示历史留言 + 提交新留言
 *
 * 环境变量在 docker-compose.yml 里通过 environment 注入（MYSQL_HOST 等），
 * 好处：数据库地址/账号不写死在代码里，换个环境不用改代码。
 */

$host = getenv('MYSQL_HOST') ?: 'db';
$user = getenv('MYSQL_USER') ?: 'guest';
$pass = getenv('MYSQL_PASSWORD') ?: 'guest123';
$db   = getenv('MYSQL_DATABASE') ?: 'guestbook';

// PDO 连接 MySQL；charset 用 utf8mb4 避免中文乱码
try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    http_response_code(500);
    die("数据库连接失败：" . htmlspecialchars($e->getMessage()));
}

// 处理提交：用 prepared statement + htmlspecialchars 防 SQL 注入和 XSS
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name    = trim($_POST['name'] ?? '');
    $content = trim($_POST['content'] ?? '');
    if ($name !== '' && $content !== '') {
        $stmt = $pdo->prepare("INSERT INTO messages (name, content) VALUES (?, ?)");
        $stmt->execute([$name, $content]);
    }
    header('Location: index.php'); // 提交后重定向，避免刷新重复提交
    exit;
}

// 读取最近 50 条留言
$messages = $pdo->query("SELECT * FROM messages ORDER BY created_at DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LNMP 留言板</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  form { background: #f6f8fa; padding: 1rem; border-radius: 8px; }
  input, textarea { width: 100%; padding: .5rem; margin: .25rem 0; box-sizing: border-box; }
  li { margin: 1rem 0; list-style: none; background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: .75rem; }
  .meta { color: #586069; font-size: .85rem; }
</style>
</head>
<body>
<h1>📌 LNMP 留言板</h1>
<p class="meta">Nginx → PHP-FPM → MySQL 三容器 · 数据存 MySQL，删容器不丢</p>

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
