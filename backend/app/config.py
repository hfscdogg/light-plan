import logging
import os

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Everything that must survive a redeploy lives under data_dir: the SQLite
    # database and the uploaded plan files.  Container filesystems are wiped on
    # every deploy, so in production this must point at a mounted volume (see
    # "Persistence" in README.md).  database_url and upload_dir are derived from
    # it unless they are set explicitly.
    data_dir: str = "./data"
    database_url: str = ""
    upload_dir: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]
    claude_model: str = "claude-sonnet-4-20250514"
    gemini_model: str = "gemini-2.5-pro"
    max_upload_size_mb: int = 50
    basic_auth_user: str = ""
    basic_auth_pass: str = ""

    model_config = {"env_file": ".env", "protected_namespaces": ("settings_",)}

    @model_validator(mode="after")
    def _resolve_storage_paths(self):
        if not self.database_url:
            db_path = os.path.join(self.data_dir, "lightplan.db")
            self.database_url = f"sqlite:///{db_path}"

        # Railway and Heroku hand out "postgres://", which SQLAlchemy 2.x
        # rejects — it only registers the "postgresql" dialect.
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql://" + self.database_url[len("postgres://") :]

        if not self.upload_dir:
            self.upload_dir = os.path.join(self.data_dir, "uploads")

        return self

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def storage_is_ephemeral(self) -> bool:
        """True when durable state is being written somewhere a deploy will wipe.

        Only meaningful on a container host. SQLite under the app's own working
        directory means the database is part of the image's writable layer and
        is discarded on the next deploy, along with every uploaded plan.
        """
        if not self.uses_sqlite:
            return False
        db_file = os.path.abspath(self.database_url.replace("sqlite:///", "", 1))
        return not os.path.relpath(db_file, os.getcwd()).startswith(os.pardir)

    def log_storage_location(self) -> None:
        """Record where durable state lives, and complain if it will not last."""
        logger.info(
            "Storage: database=%s uploads=%s",
            "postgres" if not self.uses_sqlite else self.database_url,
            self.upload_dir,
        )
        # RAILWAY_ENVIRONMENT is set by Railway on every deploy; treat its
        # presence as "this is a container that gets replaced".
        if os.getenv("RAILWAY_ENVIRONMENT") and self.storage_is_ephemeral():
            logger.warning(
                "Storage is EPHEMERAL: %s sits inside the app directory, so the "
                "database and every uploaded plan are lost on the next deploy. "
                "Mount a volume and set DATA_DIR to it, or attach Postgres and "
                "set DATABASE_URL. See README.md#persistence",
                self.database_url,
            )


settings = Settings()
