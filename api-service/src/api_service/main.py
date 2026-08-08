"""FastAPI application entrypoint for Unit 2: API Service."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_service.ai_assistant.router import router as ai_assistant_router
from api_service.auth.router import router as auth_router
from api_service.backup.router import router as backup_router
from api_service.categories.router import router as categories_router
from api_service.config import settings
from api_service.dashboards.router import router as dashboards_router
from api_service.drive_connect.router import router as drive_connect_router
from api_service.errors import register_exception_handlers
from api_service.health import router as health_router
from api_service.ingestion.router import router as ingestion_router
from api_service.recategorization.router import router as recategorization_router
from api_service.transactions.router import router as transactions_router
from transactagent_db.migrate import run_migrations_with_lock

_DATABASE_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "database" / "alembic.ini"


def _make_lifespan(run_migrations: bool):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_migrations:
            # Fail-fast auto-migrate-with-advisory-lock pattern, reused from Unit 1's NFR Design.
            run_migrations_with_lock(_DATABASE_ALEMBIC_INI)
        yield

    return lifespan


def create_app(run_migrations: bool = True) -> FastAPI:
    """`run_migrations=False` is used by the test suite, which manages its own schema
    via testcontainers + Base.metadata.create_all rather than invoking real Alembic."""
    app = FastAPI(
        title="Bank Transaction Insights API",
        lifespan=_make_lifespan(run_migrations),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(transactions_router)
    app.include_router(dashboards_router)
    app.include_router(ingestion_router)
    app.include_router(categories_router)
    app.include_router(drive_connect_router)
    app.include_router(ai_assistant_router)
    app.include_router(recategorization_router)
    app.include_router(backup_router)

    return app


app = create_app()
