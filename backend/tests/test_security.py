from app.security import session_hash, csrf_for_session, verify_csrf, verify_password, hash_password


def test_session_hash_is_not_plaintext():
    assert session_hash("meu-token") != "meu-token"
    assert len(session_hash("meu-token")) == 64


def test_csrf_bound_to_session_and_secret():
    csrf = csrf_for_session("token-A", "segredo-forte")
    assert verify_csrf("token-A", "segredo-forte", csrf)
    assert not verify_csrf("token-B", "segredo-forte", csrf)
    assert not verify_csrf("token-A", "segredo-diferente", csrf)


def test_argon2_passwords():
    h = hash_password("senha de teste longa")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "senha de teste longa")
    assert not verify_password(h, "incorreta")
    assert not verify_password(None, "incorreta")
