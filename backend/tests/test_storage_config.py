"""Where durable state lands.

The database and the uploaded plan files both have to outlive a deploy.
Uploads are not just a receipt: re-parsing a plan (what the Good/Better/Best
toggle does) re-reads the original file from disk.
"""

import os

import pytest

from app.config import Settings


@pytest.fixture
def no_data_dir_env(monkeypatch):
    """conftest exports DATA_DIR for the app tests; unset it for these."""
    monkeypatch.delenv("DATA_DIR", raising=False)


def test_database_and_uploads_derive_from_data_dir():
    s = Settings(data_dir="/var/lightplan", database_url="", upload_dir="")

    assert s.database_url == "sqlite:////var/lightplan/lightplan.db"
    assert s.upload_dir == os.path.join("/var/lightplan", "uploads")


def test_explicit_values_win_over_data_dir():
    s = Settings(
        data_dir="/var/lightplan",
        database_url="postgresql://user:pw@db.internal:5432/lightplan",
        upload_dir="/mnt/plans",
    )

    assert s.database_url == "postgresql://user:pw@db.internal:5432/lightplan"
    assert s.upload_dir == "/mnt/plans"


def test_postgres_scheme_is_normalized():
    """Railway and Heroku hand out postgres://, which SQLAlchemy 2.x rejects."""
    s = Settings(database_url="postgres://user:pw@db.internal:5432/lightplan")

    assert s.database_url.startswith("postgresql://")
    assert s.database_url == "postgresql://user:pw@db.internal:5432/lightplan"
    assert not s.uses_sqlite


def test_postgresql_scheme_is_left_alone():
    url = "postgresql://user:pw@db.internal:5432/lightplan"
    assert Settings(database_url=url).database_url == url


def test_sqlite_inside_the_app_directory_is_flagged_ephemeral():
    """The default is fine locally and wrong on a container host."""
    s = Settings(data_dir="./data", database_url="", upload_dir="")

    assert s.uses_sqlite
    assert s.storage_is_ephemeral()


def test_sqlite_on_a_mounted_volume_is_not_ephemeral(tmp_path):
    s = Settings(data_dir=str(tmp_path), database_url="", upload_dir="")

    assert s.uses_sqlite
    assert not s.storage_is_ephemeral()


def test_postgres_is_never_ephemeral():
    s = Settings(database_url="postgres://user:pw@db.internal:5432/lightplan")

    assert not s.storage_is_ephemeral()


def test_ephemeral_storage_warns_on_railway(caplog, monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    s = Settings(data_dir="./data", database_url="", upload_dir="")

    with caplog.at_level("WARNING"):
        s.log_storage_location()

    assert any("EPHEMERAL" in r.message for r in caplog.records), (
        "a deploy that silently discards every saved plan should say so"
    )


def test_no_warning_when_storage_is_durable(caplog, monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    s = Settings(data_dir=str(tmp_path), database_url="", upload_dir="")

    with caplog.at_level("WARNING"):
        s.log_storage_location()

    assert not [r for r in caplog.records if "EPHEMERAL" in r.message]


def test_no_warning_off_a_container_host(caplog, monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    s = Settings(data_dir="./data", database_url="", upload_dir="")

    with caplog.at_level("WARNING"):
        s.log_storage_location()

    assert not [r for r in caplog.records if "EPHEMERAL" in r.message]


# --- Relative paths when DATA_DIR is named deliberately ------------------
#
# Production hit this: DATABASE_URL=sqlite:///./lightplan.db and
# UPLOAD_DIR=./uploads were left over from the original setup, so a correctly
# mounted volume and a correct DATA_DIR were both silently ignored and every
# saved plan still died with the container.


def test_relative_sqlite_path_moves_onto_an_explicit_data_dir():
    s = Settings(
        data_dir="/var/lightplan",
        database_url="sqlite:///./lightplan.db",
        upload_dir="./uploads",
    )

    assert s.database_url == "sqlite:////var/lightplan/lightplan.db"
    assert s.upload_dir == "/var/lightplan/uploads"


def test_relative_subdirectories_keep_their_shape():
    s = Settings(data_dir="/var/lightplan", database_url="sqlite:///./db/plan.db",
                 upload_dir="./files/plans")

    assert s.database_url == "sqlite:////var/lightplan/db/plan.db"
    assert s.upload_dir == "/var/lightplan/files/plans"


def test_rebasing_is_reported_not_silent():
    """Rewriting someone's explicit config must be visible in the log."""
    s = Settings(data_dir="/var/lightplan", database_url="sqlite:///./lightplan.db",
                 upload_dir="./uploads")

    notes = " ".join(s._rebased)
    assert "DATABASE_URL" in notes and "UPLOAD_DIR" in notes


def test_relative_paths_are_left_alone_without_an_explicit_data_dir(no_data_dir_env):
    """Locally ./data is just a working directory; relative means relative."""
    s = Settings(database_url="sqlite:///./lightplan.db", upload_dir="./uploads")

    assert s.database_url == "sqlite:///./lightplan.db"
    assert s.upload_dir == "./uploads"


def test_absolute_paths_are_never_moved():
    s = Settings(data_dir="/var/lightplan", database_url="sqlite:////srv/plan.db",
                 upload_dir="/srv/uploads")

    assert s.database_url == "sqlite:////srv/plan.db"
    assert s.upload_dir == "/srv/uploads"


def test_postgres_is_never_moved():
    """Attaching Postgres must still win over DATA_DIR, as documented."""
    s = Settings(data_dir="/var/lightplan",
                 database_url="postgres://user:pw@db.internal:5432/lightplan")

    assert s.database_url == "postgresql://user:pw@db.internal:5432/lightplan"
    assert not s._rebased


def test_in_memory_sqlite_is_never_moved():
    for url in ("sqlite://", "sqlite:///:memory:"):
        assert Settings(data_dir="/var/lightplan", database_url=url).database_url == url


# --- Conflicts that defeat an explicit data_dir --------------------------


def test_absolute_database_outside_data_dir_is_a_conflict():
    s = Settings(data_dir="/var/lightplan", database_url="sqlite:////srv/plan.db")

    assert any("DATABASE_URL" in c for c in s.storage_conflicts())


def test_upload_dir_outside_data_dir_is_a_conflict():
    s = Settings(data_dir="/var/lightplan", upload_dir="/srv/uploads")

    assert any("UPLOAD_DIR" in c for c in s.storage_conflicts())


def test_paths_inside_data_dir_are_not_conflicts():
    s = Settings(data_dir="/var/lightplan", database_url="", upload_dir="")

    assert s.storage_conflicts() == []


def test_rebased_paths_are_not_conflicts():
    """The relative paths we just moved are on the volume now."""
    s = Settings(data_dir="/var/lightplan", database_url="sqlite:///./lightplan.db",
                 upload_dir="./uploads")

    assert s.storage_conflicts() == []


def test_postgres_is_not_a_conflict():
    s = Settings(data_dir="/var/lightplan",
                 database_url="postgresql://user:pw@db/lightplan")

    assert not [c for c in s.storage_conflicts() if "DATABASE_URL" in c]


def test_no_conflicts_reported_without_an_explicit_data_dir(no_data_dir_env):
    s = Settings(database_url="sqlite:////srv/plan.db", upload_dir="/srv/uploads")

    assert s.storage_conflicts() == []


def test_conflicts_are_logged_as_warnings(caplog):
    s = Settings(data_dir="/var/lightplan", upload_dir="/srv/uploads")

    with caplog.at_level("WARNING"):
        s.log_storage_location()

    assert any("Storage misconfigured" in r.message for r in caplog.records)


def test_production_misconfiguration_resolves_onto_the_volume(caplog):
    """End to end on the exact variables the live service was running."""
    s = Settings(
        data_dir="/var/lightplan",
        database_url="sqlite:///./lightplan.db",
        upload_dir="./uploads",
    )

    assert s.database_url == "sqlite:////var/lightplan/lightplan.db"
    assert s.upload_dir == "/var/lightplan/uploads"
    assert not s.storage_is_ephemeral()
    assert s.storage_conflicts() == []

    with caplog.at_level("WARNING"):
        s.log_storage_location()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
