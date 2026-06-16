# Stage 1: Build frontend
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20.12.0 AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim-buster

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai
ENV FRONTEND_DIST=/app/frontend/dist
ENV FRONTEND_DIST_ENABLED=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

EXPOSE 6060

CMD ["hypercorn", "app:app", "--config", "app_config.toml"]
