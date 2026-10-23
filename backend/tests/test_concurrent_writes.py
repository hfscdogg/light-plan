"""Other writes while a plan is being read.

Oct 21: a second "Test Plan" created while an upload was still analyzing got
a 500, "database is locked".  The upload held SQLite's one write lock for the
whole minute of model calls, and every other writer gave up after 5 seconds.
"""

import sqlite3

from app.config import settings, sqlite_path
from conftest import upload_plan


def test_the_database_takes_writes_while_a_plan_is_analyzed(
    client, project, stub_parser, monkeypatch
):
    from app.services import plan_parser as plan_parser_module

    stubbed_parse = plan_parser_module.PlanParser.parse_plan
    writes = []

    def parse_while_someone_else_writes(self, *args, **kwargs):
        # Stands in for another request writing mid-analysis.  A short
        # timeout: if the upload holds the write lock this fails at once.
        conn = sqlite3.connect(sqlite_path(settings.database_url), timeout=0.2)
        try:
            conn.execute(
                "UPDATE projects SET name = name WHERE id = ?", (project["id"],)
            )
            conn.commit()
            writes.append("ok")
        except sqlite3.OperationalError as e:
            writes.append(str(e))
        finally:
            conn.close()
        return stubbed_parse(self, *args, **kwargs)

    monkeypatch.setattr(
        plan_parser_module.PlanParser, "parse_plan", parse_while_someone_else_writes
    )

    r = upload_plan(client, project["id"])

    assert r.status_code == 201, r.text
    assert writes == ["ok"]
