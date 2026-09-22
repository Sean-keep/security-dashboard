# Stage 1: builder — install deps into a venv. Toolchain is only needed here.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Compilers / MySQL client headers are kept in the builder only. They exist so
# any sdist without a wheel can still build; nothing from them is copied into
# the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime — slim image, no compilers.
FROM python:3.11-slim AS runtime

# No MySQL C client library (libmariadb3 / libmysqlclient) is installed here:
# requirements use pymysql and aiomysql, both pure-Python drivers. They do not
# link against libmysqlclient, so the C client would only add attack surface.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Non-root user. /app/data holds SQLite + scheduler logs and must be writable.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app /app/data

USER appuser
WORKDIR /app

EXPOSE 5000

# GET /health pings the DB, so this only goes green when the app can serve and
# the database is reachable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"

CMD ["/app/start.sh"]
