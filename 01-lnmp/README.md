# 模块1：LNMP 留言板容器化

自写 PHP 留言板，用 docker compose 一键编排 **Nginx + PHP-FPM + MySQL** 三容器，验证"容器销毁、数据不丢"。

> **v3.0+ 更新**：本模块已部署到**阿里云 ECS**（`http://8.217.195.115:8080` 公网可访问），由 GitHub Actions 自动部署（`git push` 即上线）；前端升级为清爽 SaaS 版（友好时间 / 提交 Toast / 空状态 / 移动端适配）。服务器部署手册见 `docs/云服务器部署手册.md`。

## 架构

```
浏览器
  │  :8080
  ▼
Nginx (lnmp-nginx, 容器80)
  │  转发 .php
  ▼
PHP-FPM (lnmp-php, 容器9000) ──pdo_mysql──► MySQL (lnmp-mysql, 容器3306)
                                            │
                                        named volume: 01-lnmp_mysql_data
```

## 启动

```bash
# 1. 构建 php 镜像（含 pdo_mysql 扩展）
docker build -t lnmp-php ./php

# 2. 启动三容器
docker compose up -d

# 3. 访问
http://localhost:8080
```

## 目录结构

```
01-lnmp/
├── docker-compose.yml   # 三容器编排 + named volume
├── php/
│   ├── Dockerfile       # php-fpm 运行时 + pdo_mysql 扩展
│   └── www/index.php    # 留言板应用（挂载进容器，改代码不用重建镜像）
├── nginx/nginx.conf     # 转发 .php 请求到 php-fpm
└── mysql/init.sql       # 首次启动自动建表 + 种子数据
```

## 验证结果 （2026-08-19）

- [x] 留言板可访问、可写留言，**中文 UTF-8 全程无乱码**（hex 校验：范=E88C83）
- [x] 持久化：`docker compose down`（删容器）→ `up` → **4 条留言全在**
- [x] MySQL healthcheck 通过后才启动 php，避免连库竞态

## 两个排障点

1. **Alpine 源连不上导致构建卡死**：php 官方镜像不含 gcc/make，`docker-php-ext-install pdo_mysql` 会先 `apk add` 编译依赖，而 Alpine 官方源在国内连不上 → 构建卡 9 分钟。解法：`sed` 把 `/etc/apk/repositories` 换成阿里云源再装扩展。
2. **init.sql 导入中文乱码**：mysql 镜像导入 `.sql` 时客户端连接默认 latin1，UTF-8 中文被双重转码。解法：文件头加 `SET NAMES utf8mb4;`。
