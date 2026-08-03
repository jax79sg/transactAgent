FROM python:3.12-slim

WORKDIR /app

# Install the sibling database package (Unit 1) and this service's own dependencies.
COPY database /app/database
COPY api-service/pyproject.toml /app/api-service/pyproject.toml
COPY api-service/src /app/api-service/src

RUN pip install --no-cache-dir -e /app/database -e /app/api-service

WORKDIR /app/api-service

EXPOSE 8000

CMD ["uvicorn", "api_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
