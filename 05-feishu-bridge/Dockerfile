# 用 DaoCloud 镜像源避免 Docker Hub 拉取慢/失败（本项目惯用做法）
FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app
COPY bridge.py /app/

EXPOSE 8080
CMD ["python", "bridge.py"]
