from collections.abc import Generator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """
    Plain (non-tenant-scoped) DB session — used only for auth endpoints that run
    *before* a merchant_id is known (e.g. login itself). Every other route should
    use get_tenant_db below.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant_context(db: Session, merchant_id: UUID) -> None:
    """
    Sets the Postgres session variable that every tenant table's Row-Level
    Security policy checks against (see migrations/versions/0001_initial.py).
    This is the enforcement point: even if application code forgets a
    `WHERE merchant_id = ...` filter, RLS blocks cross-tenant reads/writes
    at the database layer.
    """
    db.execute(text("SET LOCAL app.current_merchant_id = :mid"), {"mid": str(merchant_id)})
