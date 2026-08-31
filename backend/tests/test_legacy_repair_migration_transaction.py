"""Repairs must share Alembic's connection and never commit its outer transaction."""
import importlib
import importlib.util
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

URL = os.environ.get("ANNUAL_PRICING_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")
CASES = [
    ("20260828_0215_reactivate_assas_thursday_17_slot.py", "scripts.repair_prod_assas_thursday_17_slot"),
    ("20260828_0216_reconcile_assas_thursday_17_series.py", "scripts.reconcile_prod_assas_thursday_17_series"),
    ("20260828_0217_move_diane_ceroux_to_friday_17.py", "scripts.move_prod_diane_ceroux_to_friday_17"),
    ("20260828_0218_move_diane_ceroux_accent_safe.py", "scripts.move_prod_diane_ceroux_to_friday_17"),
    ("20260828_0219_move_diane_unique_recurring.py", "scripts.move_prod_diane_ceroux_to_friday_17"),
]


@pytest.fixture
def connection():
    assert URL.rsplit("/", 1)[-1] == "piano_annual_pricing_metadata", "Never run against live data"
    engine = create_engine(URL)
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(text("SET LOCAL lock_timeout = '200ms'"))
        yield conn
        if tx.is_active:
            tx.rollback()
    engine.dispose()


def load_migration(filename):
    spec = importlib.util.spec_from_file_location("repair_migration", Path(__file__).parents[1] / "alembic/versions" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename, script_name", CASES)
def test_missing_target_with_schema_lock_keeps_alembic_transaction(connection, monkeypatch, filename, script_name):
    script = importlib.import_module(script_name)
    standalone = Mock(side_effect=AssertionError("A migration must not open its own connection"))
    monkeypatch.setattr(script, "SessionLocal", standalone)
    connection.execute(text("LOCK TABLE course_sessions IN ACCESS EXCLUSIVE MODE"))
    connection.execute(text("LOCK TABLE users IN ACCESS EXCLUSIVE MODE"))
    with Operations.context(MigrationContext.configure(connection)):
        load_migration(filename).upgrade()
    standalone.assert_not_called()
    assert connection.in_transaction()
    assert connection.scalar(text("SELECT 1")) == 1


@pytest.mark.parametrize("filename, script_name", CASES)
@pytest.mark.parametrize("script_action", ["commit", "rollback", "error"])
def test_script_cannot_commit_or_rollback_outer_migration(connection, monkeypatch, filename, script_name, script_action):
    script = importlib.import_module(script_name)
    connection.execute(text("CREATE TABLE repair_transaction_probe (id integer)"))
    connection.execute(text("INSERT INTO repair_transaction_probe VALUES (1)"))
    backend_pid = connection.scalar(text("SELECT pg_backend_pid()"))

    def repair(argv, *, session_factory):
        assert argv == ["--apply", "--allow-missing"]
        with session_factory() as db:
            assert db.scalar(text("SELECT pg_backend_pid()")) == backend_pid
            db.execute(text("INSERT INTO repair_transaction_probe VALUES (2)"))
            if script_action == "error":
                raise RuntimeError("repair failed")
            getattr(db, script_action)()
        return 0

    monkeypatch.setattr(script, "main", repair)
    with Operations.context(MigrationContext.configure(connection)):
        if script_action == "error":
            with pytest.raises(RuntimeError, match="repair failed"):
                load_migration(filename).upgrade()
        else:
            load_migration(filename).upgrade()
    assert connection.in_transaction()
    assert connection.scalar(text("SELECT count(*) FROM repair_transaction_probe")) == (2 if script_action == "commit" else 1)
    connection.rollback()
    assert not inspect(connection).has_table("repair_transaction_probe")
