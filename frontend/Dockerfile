# 校园综合服务平台 - 前端镜像（构建 + nginx 托管 + 反向代理后端）
# 注意：构建上下文必须是仓库根目录（见 docker-compose.yml 的 context: .），
# 因为需要引用 deploy/nginx-docker.conf
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# 容器版 nginx 配置：与 deploy/nginx-campus.conf 同规则，
# 区别是后端地址指向 compose 服务名 api:8001，且 /ws 关闭访问日志（token 在 query 里）
COPY deploy/nginx-docker.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
