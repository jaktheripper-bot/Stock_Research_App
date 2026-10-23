FROM python:3.14-slim

WORKDIR /app

ENV MALLOC_TRIM_THRESHOLD_=65536 \
    PYTHONMALLOC=malloc

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-concurrency 60 --timeout-keep-alive 5"]
