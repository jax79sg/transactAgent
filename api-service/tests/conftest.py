import os

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
    # api_service.config.Settings requires these env vars at import time
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
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
    # See database/tests/conftest.py for why this guards against an already-inactive transaction.
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    from api_service.auth.security import hash_password
    from transactagent_db.models import User

    user = User(username="account_owner", password_hash=hash_password("correct horse battery staple"))
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def auth_headers(client, test_user):
    response = client.post(
        "/auth/login", json={"username": "account_owner", "password": "correct horse battery staple"}
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}
