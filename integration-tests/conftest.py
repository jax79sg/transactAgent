import os, sys
for k, v in (("DB_USER","test"),("DB_PASSWORD","test"),("JWT_SECRET","test-secret-do-not-use-in-prod"),("GEMINI_API_KEY","k"),("OPENROUTER_API_KEY","k"),
             ("GOOGLE_OAUTH_CLIENT_ID","x.apps.googleusercontent.com"),("GOOGLE_OAUTH_CLIENT_SECRET","s"),
             ("GOOGLE_DRIVE_FOLDER_ID","f"),("GOOGLE_DRIVE_BACKUP_FOLDER_ID","b")):
    os.environ.setdefault(k, v)
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ingestion-worker" / "tests"))  # the worker's own test helpers

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer
from transactagent_db.models import Base


@pytest.fixture(scope="session")
def engine():
    with PostgresContainer("postgres:16-alpine") as pg:
        e = create_engine(pg.get_connection_url().replace("psycopg2", "psycopg"))
        Base.metadata.create_all(e)
        yield e
        e.dispose()


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


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient
    from api_service.db import get_db
    from api_service.main import create_app

    app = create_app(run_migrations=False)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
