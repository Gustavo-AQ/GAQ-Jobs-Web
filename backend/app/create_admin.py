"""Execute no container: python -m app.create_admin --email email@dominio.com"""
import argparse
import getpass
import re
from sqlalchemy import text
from app.db import engine
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Criar administrador local no GAQ Jobs.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        parser.error("E-mail invalido")
    password = getpass.getpass("Senha (minimo 12 caracteres): ")
    if len(password) < 12:
        parser.error("Senha curta demais")
    if password != getpass.getpass("Confirme a senha: "):
        parser.error("As senhas nao coincidem")
    with engine().begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM empregos.web_usuarios WHERE lower(email) = :email"),
            {"email": email},
        ).first()
        if exists:
            parser.error("Esse e-mail ja existe. Nenhuma alteracao aplicada.")
        conn.execute(
            text("""INSERT INTO empregos.web_usuarios (email, senha_hash, papel)
                    VALUES (:email, :hash, 'ADMIN')"""),
            {"email": email, "hash": hash_password(password)},
        )
    print("Administrador criado. Nenhuma senha foi exibida.")


if __name__ == "__main__":
    main()
