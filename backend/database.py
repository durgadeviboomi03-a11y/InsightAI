"""
backend/database.py

Database engine and session management for InsightAI.

Sets up:
- The SQLAlchemy engine (connection to MySQL, configured via DATABASE_URL)
- A session factory (SessionLocal) for creating per-request DB sessions
- The declarative Base class that all ORM models inherit from
- A FastAPI dependency (get_db) for injecting a DB session into route handlers
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from loguru import logger

from backend.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """
    Base class for all ORM models.

    Every model in backend/models.py will inherit from this, which is how
    SQLAlchemy discovers them for Base.metadata.create_all() in main.py.
    """
    pass


# ---------- Engine ----------
# pool_pre_ping=True checks that a pooled connection is still alive before
# using it, preventing "MySQL server has gone away" errors after idle periods.
# pool_recycle=3600 proactively recycles connections older than 1 hour, which
# avoids MySQL's default wait_timeout from silently dropping stale connections.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,  # Logs raw SQL statements when DEBUG=True — useful for development
)

# ---------- Session Factory ----------
# autocommit=False and autoflush=False give explicit control over when
# changes are committed/flushed, which is the recommended FastAPI pattern.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session per request.

    Usage in a route:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...

    The session is always closed after the request finishes, even if an
    exception occurs, thanks to the try/finally block.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error(f"Database session error, rolling back: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> bool:
    """
    Verifies the database is reachable. Useful for startup checks or
    a health-check endpoint that wants to confirm DB connectivity,
    not just that the API process is running.
    """
    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
        logger.info("Database connection verified successfully.")
        return True
    except Exception as exc:
        logger.error(f"Database connection failed: {exc}")
        return False