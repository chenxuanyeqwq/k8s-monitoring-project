# 留言板 k8s 部署版镜像（单容器：nginx + php-fpm）
# 说明：k8s 演示用单容器即可；数据用 SQLite(emptyDir 挂载)，生产应改 StatefulSet+PVC。
# 构建：
#   docker build -t guestbook:v1 --build-arg APP_VERSION=v1 .
#   docker build -t guestbook:v2 --build-arg APP_VERSION=v2 .

FROM php:8.2-fpm-alpine

# 排障点：和模块1一样，apk 装 nginx 需要先把 Alpine 源换成阿里云
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.aliyun.com|g' /etc/apk/repositories \
    && apk add --no-cache nginx

# 版本号打进镜像（滚动更新演示时，v1/v2 页面显示不同版本）
ARG APP_VERSION=v1
ENV APP_VERSION=$APP_VERSION

# 整份替换主配置；删掉 Alpine 自带的 conf.d 里的默认 server 避免冲突
COPY nginx.conf /etc/nginx/nginx.conf
RUN rm -f /etc/nginx/conf.d/default.conf
COPY index.php /var/www/html/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /var/www/html
EXPOSE 80
ENTRYPOINT ["entrypoint.sh"]
