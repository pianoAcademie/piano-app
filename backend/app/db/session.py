from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _configure_postgres_session(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    try:
        # Avoid long lock waits from stale transactions in admin workflows.
        cursor.execute("SET lock_timeout TO '3s'")
        cursor.execute("SET idle_in_transaction_session_timeout TO '15s'")
    finally:
        cursor.close()
