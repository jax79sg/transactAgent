import os

# Set before any test module (or its imports) can trigger
# ingestion_worker.config.Settings() at collection/import time -- pydantic-settings
# validates immediately on construction, which happens at module import, before any
# fixture runs. Must be module-level here, not inside a fixture (caught by actually
# running the suite: fixture-scoped env vars were too late for e.g. test_retry.py,
# which imports ingestion_worker.clients.retry -> ingestion_worker.config at collection).
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_DRIVE_FOLDER_ID", "test-drive-folder-id")
os.environ.setdefault("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "test-drive-backup-folder-id")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer
from transactagent_db.models import Base


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
