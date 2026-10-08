import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> str:
    """
    Reads DATABASE_URL (e.g. the Supabase connection string) and selects the
    psycopg 3 driver, since Supabase hands out plain "postgresql://" URLs.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init_engine():
    global engine
    if engine is None:
        engine = create_engine(database_url(), pool_pre_ping=True)
        SessionLocal.configure(bind=engine)
    return engine


def get_db():
    """FastAPI dependency: `def endpoint(db: Session = Depends(get_db))`."""
    init_engine()
    with SessionLocal() as session:
        yield session
