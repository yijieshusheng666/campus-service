# 校园综合服务平台 - 后端镜像
# 构建：docker build -t campus-api ./backend
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖再拷代码：利用 Docker 层缓存，改代码不用重装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

# 上传目录（运行时建议挂卷，否则容器重建文件丢失）
RUN mkdir -p uploads

EXPOSE 8001

# 启动时先跑数据库迁移再拉起服务（幂等，已是最新则跳过）
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001"]
