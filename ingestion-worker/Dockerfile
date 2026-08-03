FROM python:3.12-slim

# pdf2image (NFR Requirements Question 2 = B) requires the poppler-utils system package.
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY database /app/database
COPY ingestion-worker/pyproject.toml /app/ingestion-worker/pyproject.toml
COPY ingestion-worker/src /app/ingestion-worker/src

RUN pip install --no-cache-dir -e /app/database -e /app/ingestion-worker

WORKDIR /app/ingestion-worker

CMD ["python", "-m", "ingestion_worker.main"]
