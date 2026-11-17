import hashlib
import hmac
import secrets
from argon2 import PasswordHasher, exceptions as argon_errors

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash("senha-inexistente-para-timing")


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(hash_value: str | None, password: str) -> bool:
    try:
        return hasher.verify(hash_value or DUMMY_HASH, password)
    except (argon_errors.VerificationError, argon_errors.InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(40)


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_for_session(token: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), ("gaq-jobs-csrf:" + token).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf(token: str, secret: str, supplied: str) -> bool:
    return bool(supplied) and hmac.compare_digest(csrf_for_session(token, secret), supplied)
