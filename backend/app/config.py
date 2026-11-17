import os
from functools import lru_cache
from urllib.parse import urlsplit


@lru_cache
def settings():
    database_url = os.getenv("DATABASE_URL", "")
    app_origin = os.getenv("APP_ORIGIN", "").rstrip("/")
    session_secret = os.getenv("SESSION_SECRET", "")
    cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() in ("true", "1", "yes")
    if not database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        raise RuntimeError("DATABASE_URL deve apontar para o PostgreSQL gaq via psycopg.")
    if len(session_secret) < 32:
        raise RuntimeError("SESSION_SECRET precisa de pelo menos 32 caracteres aleatorios.")
    parsed = urlsplit(app_origin)
    if not parsed.hostname or parsed.scheme not in ("http", "https"):
        raise RuntimeError("APP_ORIGIN deve ser uma origem HTTP(S) valida, sem caminho.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RuntimeError("APP_ORIGIN deve conter somente protocolo e dominio.")
    if cookie_secure and parsed.scheme != "https":
        raise RuntimeError("COOKIE_SECURE=true exige APP_ORIGIN com HTTPS.")
    return {
        "database_url": database_url.replace("postgresql://", "postgresql+psycopg://", 1),
        "app_origin": app_origin,
        "session_secret": session_secret,
        "cookie_secure": cookie_secure,
        "cookie_name": "__Host-gaq_jobs" if cookie_secure else "gaq_jobs_dev",
        "session_hours": max(1, min(int(os.getenv("SESSION_HOURS", "72")), 720)),
    }
