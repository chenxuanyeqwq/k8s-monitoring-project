<?php
/**
 * LNMP 留言板 · 清爽 SaaS 版前端
 * 链路：Nginx -> PHP-FPM -> MySQL
 * 功能：展示留言 + 提交留言 + 友好时间 + 提交反馈 + 移动端适配
 */
date_default_timezone_set('Asia/Shanghai');   // 供 ISO 输出统一时区

$host = getenv('MYSQL_HOST') ?: 'db';
$user = getenv('MYSQL_USER') ?: 'guest';
$pass = getenv('MYSQL_PASSWORD') ?: 'guest123';
$db   = getenv('MYSQL_DATABASE') ?: 'guestbook';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    http_response_code(500);
    die("数据库连接失败：" . htmlspecialchars($e->getMessage()));
}

// 提交：prepared statement 防注入 + PRG 防重复提交
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name    = trim($_POST['name'] ?? '');
    $content = trim($_POST['content'] ?? '');
    if ($name !== '' && $content !== '') {
        $stmt = $pdo->prepare("INSERT INTO messages (name, content) VALUES (?, ?)");
        $stmt->execute([$name, $content]);
    }
    header('Location: index.php?posted=1');
    exit;
}

$showToast = isset($_GET['posted']);
$messages  = $pdo->query("SELECT * FROM messages ORDER BY created_at DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LNMP 留言板</title>
<style>
:root {
  --accent: #3b82f6; --accent-bg: #eff6ff; --accent-dark: #2563eb;
  --bg: #f6f8fa; --card: #ffffff; --text: #1f2937; --muted: #6b7280;
  --border: #e5e7eb; --radius: 12px;
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow-lg: 0 6px 16px rgba(0,0,0,.10);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh;
}
main { max-width: 640px; margin: 0 auto; padding: 2.5rem 1rem 3rem; }
header.site { margin-bottom: 1.5rem; }
header.site h1 { font-size: 1.5rem; font-weight: 700; display: flex; align-items: center; gap: .5rem; }
header.site p.meta { color: var(--muted); font-size: .85rem; margin-top: .25rem; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); }

form.card { padding: 1rem; margin-bottom: 1.5rem; }
input[type=text], textarea {
  width: 100%; padding: .6rem .75rem; margin: .3rem 0;
  border: 1px solid var(--border); border-radius: 8px; font-size: 1rem;
  font-family: inherit; color: var(--text); background: var(--card);
  transition: border-color .15s, box-shadow .15s;
}
input[type=text]:focus, textarea:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-bg);
}
textarea { resize: vertical; min-height: 72px; }
button[type=submit] {
  width: 100%; margin-top: .6rem; padding: .65rem;
  background: var(--accent); color: #fff; border: none; border-radius: 8px;
  font-size: 1rem; font-weight: 600; cursor: pointer; transition: background .15s;
}
button[type=submit]:hover { background: var(--accent-dark); }
button[type=submit]:active { transform: scale(.99); }

ul.messages { list-style: none; display: flex; flex-direction: column; gap: .75rem; }
li.msg { padding: .9rem 1rem; transition: transform .15s, box-shadow .15s; }
li.msg:hover { transform: translateY(-1px); box-shadow: var(--shadow-lg); }
.msg-head { display: flex; align-items: center; gap: .6rem; margin-bottom: .35rem; }
.avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: var(--accent-bg); color: var(--accent);
  display: flex; align-items: center; justify-content: center;
  font-size: .85rem; font-weight: 700; flex-shrink: 0;
}
.msg-name { font-weight: 600; font-size: .95rem; }
.msg-time { color: var(--muted); font-size: .8rem; margin-left: auto; }
.msg-body { overflow-wrap: anywhere; }

.empty { text-align: center; padding: 3rem 1rem; color: var(--muted); }
.empty .icon { font-size: 2.5rem; margin-bottom: .5rem; }
.empty .t1 { color: var(--text); font-weight: 600; margin-bottom: .2rem; }
.empty .t2 { font-size: .85rem; }

.toast {
  position: fixed; top: 1rem; left: 50%; transform: translateX(-50%);
  background: #10b981; color: #fff; padding: .6rem 1.2rem; border-radius: 999px;
  font-size: .9rem; box-shadow: var(--shadow-lg); z-index: 50;
  animation: toast-in .3s ease;
}
.toast.hide { opacity: 0; transform: translateX(-50%) translateY(-8px); transition: opacity .3s, transform .3s; }
@keyframes toast-in { from { opacity: 0; transform: translateX(-50%) translateY(-8px); } to { opacity: 1; transform: translateX(-50%); } }

@media (max-width: 480px) {
  main { padding: 1.5rem .75rem 2.5rem; }
  header.site h1 { font-size: 1.3rem; }
  li.msg { padding: .8rem .85rem; }
  input[type=text], textarea, button[type=submit] { min-height: 44px; }
}
</style>
</head>
<body>
<?php if ($showToast): ?>
<div class="toast" id="toast">✓ 留言已发布</div>
<?php endif; ?>
<main>
  <header class="site">
    <h1>📌 LNMP 留言板</h1>
    <p class="meta">Nginx → PHP-FPM → MySQL · 数据存 MySQL,删容器不丢</p>
  </header>

  <form class="card" method="post">
    <input type="text" name="name" placeholder="你的名字" required>
    <textarea name="content" placeholder="写点什么…" rows="3" required></textarea>
    <button type="submit">✏️ 发布留言</button>
  </form>

  <?php if (empty($messages)): ?>
  <div class="card empty">
    <div class="icon">✨</div>
    <div class="t1">还没有留言</div>
    <div class="t2">来抢第一条吧,在上面写下你的第一句话</div>
  </div>
  <?php else: ?>
  <ul class="messages">
    <?php foreach ($messages as $m): ?>
    <li class="msg card">
      <div class="msg-head">
        <?php $initial = function_exists('mb_substr') ? mb_substr($m['name'], 0, 1, 'UTF-8') : substr($m['name'], 0, 1); ?>
        <span class="avatar"><?= htmlspecialchars($initial) ?></span>
        <span class="msg-name"><?= htmlspecialchars($m['name']) ?></span>
        <span class="msg-time" data-time="<?= date('c', strtotime($m['created_at'] . ' UTC')) ?>"><?= htmlspecialchars($m['created_at']) ?></span>
      </div>
      <div class="msg-body"><?= nl2br(htmlspecialchars($m['content'])) ?></div>
    </li>
    <?php endforeach; ?>
  </ul>
  <?php endif; ?>
</main>

<script>
// 友好时间：把 data-time(ISO) 转成"刚刚/x 分钟前/昨天"等
document.querySelectorAll('.msg-time').forEach(function (el) {
  var iso = el.getAttribute('data-time');
  if (!iso) return;
  var t = new Date(iso).getTime();
  if (isNaN(t)) return;
  var diff = (Date.now() - t) / 1000;
  var text;
  if (diff < 60) text = '刚刚';
  else if (diff < 3600) text = Math.floor(diff / 60) + ' 分钟前';
  else if (diff < 86400) text = Math.floor(diff / 3600) + ' 小时前';
  else if (diff < 604800) {
    var days = Math.floor(diff / 86400);
    text = days === 1 ? '昨天' : days + ' 天前';
  } else {
    var d = new Date(t);
    function p(n) { return n < 10 ? '0' + n : n; }
    text = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  el.textContent = text;
});

// Toast 3 秒后淡出并移除
var toast = document.getElementById('toast');
if (toast) {
  setTimeout(function () {
    toast.classList.add('hide');
    setTimeout(function () { toast.remove(); }, 400);
  }, 3000);
}
</script>
</body>
</html>
