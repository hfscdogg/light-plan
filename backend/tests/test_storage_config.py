"""Where durable state lands.

The database and the uploaded plan files both have to outlive a deploy.
Uploads are not just a receipt: re-parsing a plan (what the Good/Better/Best
toggle does) re-reads the original file from disk.
"""

import os

from app.config import Settings


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
