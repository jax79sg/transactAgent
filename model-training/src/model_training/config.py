"""Environment-sourced configuration. Reuses the SAME DB/oMLX env vars the other
4 units already read from the root .env (NFR Design: "Config Loading — Reuses, Does
Not Duplicate") -- this is a host-run tool, so it reads .env directly via
python-dotenv rather than the 2 containerized services' env_file/override-file
mechanism (AR-32/WR-33), which is docker-compose-specific and doesn't apply here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env")

    # Infrastructure Design: loopback-only host port published for this unit's
    # read-only access -- distinct from the containers' own internal
    # DB_HOST=database/DB_PORT=5432, which is unaffected.
    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "transactagent"
    db_user: str
    db_password: str

    # Same OpenRouter-compatible endpoint ingestion-worker's openrouter_client.py
    # already points at the oMLX server -- reused read-only by evaluate() (MTR-7),
    # never written to, never proxied through ingestion-worker's own code.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_api_key: str

    @property
    def database_url(self) -> str:
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = Settings()
