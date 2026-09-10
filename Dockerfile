FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY clients/web ./clients/web

RUN pip install --upgrade pip && pip install ".[cloud]"

RUN useradd --create-home --uid 10001 iras && \
    mkdir -p /app/data /app/logs && chown -R iras:iras /app

USER iras
EXPOSE 8000

CMD ["python", "-m", "iras.cloud_api"]
