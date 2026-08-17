"""DB session factory. Unlike Unit 2's per-request dependency, this worker uses a
session-per-task-iteration pattern (opened at the start of each poll cycle's work,
closed at the end)."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ingestion_worker.config import settings

engine = create_engine(settings.database_url, pool_size=5, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
