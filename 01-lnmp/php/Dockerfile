# PHP-FPM 运行时镜像
# 说明：代码不 COPY 进镜像，而是通过 docker-compose 从宿主机挂载。
#       这样改代码不用重新构建镜像，也更容易理解"镜像=运行时、挂载=代码"的分工。
FROM php:8.2-fpm-alpine

# 安装连接 MySQL 所需的 PHP 扩展（pdo_mysql）
# ⚠️ 排障点：官方镜像不含 gcc/make，docker-php-ext-install 要先 apk 装编译依赖，
#    而 Alpine 官方源在国内连不上会导致构建卡死。
#    解法：先用 sed 把 Alpine 源换成阿里云镜像，再装扩展。
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.aliyun.com|g' /etc/apk/repositories \
    && docker-php-ext-install pdo_mysql

WORKDIR /var/www/html

EXPOSE 9000
