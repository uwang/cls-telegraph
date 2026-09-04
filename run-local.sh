#!/usr/bin/env bash
# 从任意目录构建并启动本项目；Ctrl+C 退出日志查看，容器继续运行。
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if ! command -v docker >/dev/null 2>&1; then
    echo "未找到 Docker，请先安装并启动 Docker Desktop。" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose 不可用，请安装 Docker Compose 插件。" >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "无法连接 Docker 引擎，请确认 Docker 已启动且当前用户有访问权限。" >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "已从 .env.example 创建 .env；默认不推送 Bark，填写 BARK_DEVICE_KEYS 后重新运行即可。"
fi

docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up -d --build archive
echo "服务已启动。Ctrl+C 仅退出日志查看；停止服务请运行 docker compose down。"
docker compose -f compose.yaml logs --tail=100 -f archive
