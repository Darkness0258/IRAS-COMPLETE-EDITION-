FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY clients/web ./clients/web

# v5 cloud includes PostgreSQL persistence, browser workflows, artifact output,
# encrypted sync/vault support, and signed skill verification.
RUN pip install --upgrade pip && \
    pip install ".[cloud,browser,artifacts,crypto]" && \
    python -m playwright install --with-deps chromium

RUN useradd --create-home --uid 10001 iras && \
    mkdir -p /app/data /app/logs && chown -R iras:iras /app

USER iras
EXPOSE 10000

CMD ["python", "-m", "iras.cloud_api"]
