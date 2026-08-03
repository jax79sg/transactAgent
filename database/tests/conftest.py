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
    # A test that triggers an IntegrityError (e.g. a CHECK/UNIQUE constraint test) has
    # already caused Postgres to abort and deassociate the transaction; rolling back an
    # already-inactive transaction is a harmless no-op but SQLAlchemy warns about it, so
    # only roll back if it's still active.
    if transaction.is_active:
        transaction.rollback()
    connection.close()
