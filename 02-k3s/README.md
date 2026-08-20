# 模块2：k3s 部署 + 滚动更新回滚演练

把留言板容器化部署到本地 k3s 集群，实现 **Deployment 滚动更新 / 回滚 / Service / Ingress** 完整链路。

## 架构

```
宿主机 :8081
  │  curl -H "Host: guestbook.local"
  ▼
Traefik Ingress (k3d loadbalancer, 容器80)
  │  guestbook.local → guestbook-svc
  ▼
Service guestbook-svc (ClusterIP, 负载均衡)
  │  ├──► Pod guestbook:v1 (10.42.0.21)
  │  ├──► Pod guestbook:v1 (10.42.0.22)
  │  └──► Pod guestbook:v1 (10.42.0.23)
  每个Pod = 单容器 nginx+php-fpm 留言板(SQLite, emptyDir)
```

## 快速复现

```bash
# 0. 建集群（带 containerd 镜像加速 + 端口映射）
k3d cluster create k8s-project -p 8081:80@loadbalancer \
  --volume "E:/dev/k8s-project/02-k3s/registries.yaml:/etc/rancher/k3s/registries.yaml"

# 1. 构建镜像并导入集群
cd guestbook
docker build -t guestbook:v1 --build-arg APP_VERSION=v1 .
docker build -t guestbook:v2 --build-arg APP_VERSION=v2 .
k3d image import guestbook:v1 guestbook:v2 -c k8s-project

# 2. 部署（先建 namespace）
kubectl apply -f manifests/namespace.yaml
kubectl apply -f manifests/deployment.yaml -f manifests/service.yaml -f manifests/ingress.yaml

# 3. 访问
curl -H "Host: guestbook.local" http://localhost:8081

# 4. 滚动更新 v1→v2
kubectl -n guestbook set image deployment/guestbook guestbook=guestbook:v2
kubectl -n guestbook rollout status deployment/guestbook

# 5. 回滚到 v1
kubectl -n guestbook rollout undo deployment/guestbook
```

## 目录结构

```
02-k3s/
├── registries.yaml       # containerd 镜像加速配置（k3s 专用）
├── guestbook/
│   ├── Dockerfile        # nginx+php-fpm 单容器镜像（SQLite）
│   ├── nginx.conf        # 完整主配置，转发 php 到 127.0.0.1:9000
│   ├── index.php         # 留言板（页面显示内嵌版本号 v1/v2）
│   └── entrypoint.sh     # 同时启动 php-fpm + nginx
├── manifests/
│   ├── namespace.yaml    # guestbook 命名空间
│   ├── deployment.yaml   # 3副本 + 就绪探针 + emptyDir
│   ├── service.yaml      # ClusterIP
│   └── ingress.yaml      # traefik，host guestbook.local
└── bin/k3d.exe           # k3d 二进制（国内下载用 ghfast.top 代理）
```

## 验证结果（2026-08-19）

- [x] 集群节点 Ready，系统组件全 Running（coredns/traefik/metrics-server/local-path-provisioner）
- [x] 通过 Ingress 访问留言板成功，3 副本负载均衡
- [x] 滚动更新 v1→v2：新 Pod 逐批顶上、旧 Pod 逐批终止（默认 maxSurge/maxUnavailable=25%）
- [x] `rollout undo` 回滚：v2 副本终止、v1 恢复，页面回到 v1

## 四个基础设施排障点

1. **ghcr.io 被墙**：k3d 创建集群要拉 `ghcr.io/k3d-io/k3d-proxy`，国内连不上导致集群创建卡死。解法：从 `ghcr.m.daocloud.io` 拉取后 `docker tag` 成 ghcr.io 名。
2. **k3s containerd 不走 Docker 加速**：k3s 内部用 containerd 直连 docker.io 拉镜像被墙，所有 Pod 卡 ContainerCreating（拉不到 pause 镜像）。解法：挂载 `registries.yaml` 把 docker.io 指向 DaoCloud。
3. **kubeconfig 用 host.docker.internal 连不上**：Windows 宿主解析不了。解法：改成 `127.0.0.1:<API端口>` + `insecure-skip-tls-verify`（本地开发集群常规做法）。
4. **containerd 拉镜像 DNS 间歇失败**：部分镜像拉取命中 DNS 失败。解法：宿主机拉好后 `k3d image import` 灌入，containerd 直接用本地镜像，绕开网络。

## 面试一句话

> "我在本地 k3s 集群上部署了一个自写留言板：Deployment 管 3 个副本、Service 负载均衡、Ingress 用 traefik 暴露，实操了滚动更新（新 Pod 逐批顶上）和 `rollout undo` 回滚。过程中解决了国内网络的四个坑：ghcr.io 镜像源、k3s containerd 加速、kubeconfig 连不上、镜像拉取 DNS 抖动。"
