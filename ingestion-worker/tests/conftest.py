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


@pytest.fixture(autouse=True)
def recorded_usage(monkeypatch):
    """Issue #28 (Costs page): every model client records what a paid call cost. No test may reach a real database
    through that, so the recorder is replaced by a collector for every test; a test reads the list to see what would
    have been recorded, and the tests of the recorder itself put the real one back."""
    from ingestion_worker import usage

    collected: list[dict] = []
    monkeypatch.setattr(usage, "record_model_usage", lambda session_factory, **fields: collected.append(fields))
    return collected


@pytest.fixture(autouse=True)
def _never_list_the_real_drive_folder_for_ignored_items(request, monkeypatch):
    """The pipeline also lists what the watched folder holds but the scan does not read (BR-54). Tests that run the
    pipeline patch the PDF listing only; without this they would reach for real Drive credentials. test_drive_client
    exercises the real function and is left alone; a test that wants ignored items patches it itself."""
    if request.module.__name__.rsplit(".", 1)[-1] == "test_drive_client":
        return
    from ingestion_worker.clients import drive_client

    monkeypatch.setattr(drive_client, "list_folder_ignored_items", lambda db: [])
