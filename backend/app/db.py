from functools import lru_cache
from sqlalchemy import create_engine
from app.config import settings


@lru_cache
def engine():
    return create_engine(
        settings()["database_url"],
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
        pool_timeout=15,
        connect_args={"connect_timeout": 8, "application_name": "gaq_jobs_web"},
    )
