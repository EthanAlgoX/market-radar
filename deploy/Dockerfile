FROM node:22.14.0-bookworm-slim AS web
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/market-radar/backend/.venv/bin:$PATH \
    RADAR_DATA_DIR=/data \
    XDG_CACHE_HOME=/data/cache \
    HOME=/home/radar
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.3 \
    && groupadd --gid 10001 radar \
    && useradd --uid 10001 --gid radar --create-home radar \
    && mkdir -p /data \
    && chown radar:radar /data
WORKDIR /opt/market-radar/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python
COPY backend/app/ ./app/
COPY --from=web /build/frontend/dist/ /opt/market-radar/frontend/dist/
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3).close()"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
