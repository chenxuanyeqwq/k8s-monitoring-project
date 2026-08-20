#!/bin/sh
# 单容器同时跑 php-fpm 和 nginx（演示用；生产建议拆容器由编排管理）
# /data 是 k8s 挂的 emptyDir，默认 root 属主，SQLite 要写它，先放开权限
mkdir -p /data && chmod 777 /data

# 启动 php-fpm（后台），再以前台方式启动 nginx 保持容器存活
php-fpm -D
nginx -g 'daemon off;'
