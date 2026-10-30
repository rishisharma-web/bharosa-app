"""SQLite engine and session helpers."""
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        path = get_settings().db_path
        _engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return _engine


def session() -> Session:
    return Session(get_engine(), expire_on_commit=False)


def create_all() -> None:
    import app.models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(get_engine())


def rebuild() -> None:
    """Drop and recreate every table. Used by seed / reset."""
    import app.models  # noqa: F401

    eng = get_engine()
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
