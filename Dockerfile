# Metrik production runtime — web API only (no Scrapy/Playwright research stack).
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    APP_ENV=production \
    LOG_FORMAT=json

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY web ./web
COPY data/api ./data/api
COPY data/claims ./data/claims
COPY data/datasets ./data/datasets
COPY data/gazetteers ./data/gazetteers
COPY data/product ./data/product
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY reports/templates ./reports/templates
# Verified release lookup cache (Option A for Azure beta). Build context must include
# a hashed release under reports/generated/lookup_cache before production push.
# Local/CI builds without a release may copy an empty tree; the app fails closed at ready.
COPY reports/generated/lookup_cache ./reports/generated/lookup_cache
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh

# Install Metrik runtime (+ web) only — research tooling stays out of the public image.
RUN uv sync --extra web --frozen --no-dev \
    && sed -i 's/\r$//' ./scripts/docker-entrypoint.sh \
    && chmod +x ./scripts/docker-entrypoint.sh

RUN addgroup --system metrik \
    && adduser --system --ingroup metrik --home /app metrik \
    && chown -R metrik:metrik /app

USER metrik

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3)"

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
