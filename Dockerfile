FROM ghcr.1ms.run/astral-sh/uv:0.8.11 AS uv
FROM docker.1ms.run/library/python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md cls_telegraph.py ./
COPY archive/ ./archive/
RUN uv sync --frozen --no-dev --no-editable
ENTRYPOINT ["python", "-m", "archive.scheduler"]
