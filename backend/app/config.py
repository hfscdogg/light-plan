import logging
import os

from pydantic import PrivateAttr, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

SQLITE_PREFIX = "sqlite:///"


def sqlite_path(database_url: str) -> str | None:
    """Return the file path inside a SQLite URL, or None if there isn't one.

    None covers both non-SQLite URLs (Postgres) and SQLite URLs with no file
    behind them (``sqlite://`` and ``:memory:``), neither of which lives on
    disk and so neither of which can be relocated.
    """
    if not database_url.startswith(SQLITE_PREFIX):
        return None
    path = database_url[len(SQLITE_PREFIX) :]
    if not path or path == ":memory:":
        return None
    return path


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Everything that must survive a redeploy lives under data_dir: the SQLite
    # database and the uploaded plan files.  Container filesystems are wiped on
    # every deploy, so in production this must point at a mounted volume (see
    # "Persistence" in README.md).  database_url and upload_dir are derived
    # from it unless they are set explicitly.
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

    # Human-readable notes about paths that were moved onto data_dir, so
    # startup can report what it did rather than silently rewriting config.
    _rebased: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _resolve_storage_paths(self):
        # Railway and Heroku hand out "postgres://", which SQLAlchemy 2.x
        # rejects — it only registers the "postgresql" dialect.
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql://" + self.database_url[len("postgres://") :]

        # Only rebase when data_dir was named deliberately. Locally the default
        # ./data is just a working directory and relative paths mean what they
        # say; in production data_dir is the volume, and a relative path cannot
        # possibly be durable.
        data_dir_is_explicit = "data_dir" in self.model_fields_set

        if not self.database_url:
            self.database_url = SQLITE_PREFIX + os.path.join(self.data_dir, "lightplan.db")
        elif data_dir_is_explicit:
            path = sqlite_path(self.database_url)
            if path is not None and not os.path.isabs(path):
                # A relative SQLite path inside a container points at the
                # image's writable layer, which the next deploy discards.
                # DATA_DIR was set precisely to avoid that, so honour it.
                moved = os.path.normpath(os.path.join(self.data_dir, path))
                self._rebased.append(
                    f"DATABASE_URL {self.database_url} -> {SQLITE_PREFIX}{moved}"
                )
                self.database_url = SQLITE_PREFIX + moved

        if not self.upload_dir:
            self.upload_dir = os.path.join(self.data_dir, "uploads")
        elif data_dir_is_explicit and not os.path.isabs(self.upload_dir):
            moved = os.path.normpath(os.path.join(self.data_dir, self.upload_dir))
            self._rebased.append(f"UPLOAD_DIR {self.upload_dir} -> {moved}")
            self.upload_dir = moved

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
        path = sqlite_path(self.database_url)
        if path is None:
            return False
        db_file = os.path.abspath(path)
        return not os.path.relpath(db_file, os.getcwd()).startswith(os.pardir)

    def storage_conflicts(self) -> list[str]:
        """Settings that quietly defeat an explicitly configured data_dir.

        An absolute SQLite path outside data_dir, or an upload directory
        outside it, leaves durable state off the volume even though data_dir
        was set — the exact misconfiguration that is invisible until someone
        notices their saved plans are gone.
        """
        if "data_dir" not in self.model_fields_set:
            return []

        conflicts = []
        root = os.path.abspath(self.data_dir)

        def outside(path: str) -> bool:
            return os.path.relpath(os.path.abspath(path), root).startswith(os.pardir)

        db_path = sqlite_path(self.database_url)
        if db_path is not None and outside(db_path):
            conflicts.append(
                f"DATABASE_URL points at {db_path}, outside DATA_DIR ({self.data_dir}) — "
                "the database will not be on the volume"
            )
        if outside(self.upload_dir):
            conflicts.append(
                f"UPLOAD_DIR points at {self.upload_dir}, outside DATA_DIR ({self.data_dir}) — "
                "uploaded plans will not be on the volume"
            )
        return conflicts

    def log_storage_location(self) -> None:
        """Record where durable state lives, and complain if it will not last."""
        logger.info(
            "Storage: database=%s uploads=%s",
            "postgres" if not self.uses_sqlite else self.database_url,
            self.upload_dir,
        )
        for note in self._rebased:
            logger.info("Storage: relative path moved onto DATA_DIR — %s", note)
        for conflict in self.storage_conflicts():
            logger.warning("Storage misconfigured: %s", conflict)

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
