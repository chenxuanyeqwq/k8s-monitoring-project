-- 首次启动自动执行（仅当 MySQL 数据卷为空时跑一次）
-- 说明：数据库 guestbook 由 docker-compose 的 MYSQL_DATABASE 自动创建，
--       这里只负责建表 + 插入示例数据。

-- ⚠️ 排障点：mysql 镜像导入 .sql 时客户端连接可能默认 latin1，
--    中文会被双重转码成乱码。SET NAMES utf8mb4 强制连接用 UTF-8。
SET NAMES utf8mb4;

USE guestbook;

CREATE TABLE IF NOT EXISTS messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始示例数据，用于启动后立刻能看见内容
INSERT INTO messages (name, content) VALUES
  ('范城铭', '第一条留言：LNMP 容器化部署成功！'),
  ('运维小助手', '试试往数据库里写一条，然后 docker compose down 再 up，数据还在吗？');
