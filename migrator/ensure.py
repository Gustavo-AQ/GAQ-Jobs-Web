#!/usr/bin/env python3
"""GAQ Jobs schema bootstrap: fail-closed, transactional and non-destructive.

Run as a PostgreSQL migration administrator, never as the web or Grok role.
It does NOT create the PostgreSQL database. It expects an existing 'gaq'.
"""
import hashlib
import logging
import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

LOG = logging.getLogger("gaq-schema")
# Docker uses /opt/gaq/sql; running from the repository uses ../db.
_DEFAULT_SQL_DIR = Path(__file__).parent / "sql"
SQL_ROOT = Path(os.getenv("GAQ_SQL_DIR", str(
    _DEFAULT_SQL_DIR if _DEFAULT_SQL_DIR.is_dir() else Path(__file__).parent.parent / "db"
)))
SCRIPTS = {
    "base": "000_jobs_whodb.sql",
    "dictionary": "010_dictionary_whodb.sql",
    "status_v2": "020_status_v2_whodb.sql",
    "comprovante_inscrito": "030_comprovante_inscrito_whodb.sql",
    "auth": "001_auth_whodb.sql",
}
BASE_TABLES = {"vagas", "vagas_status_hist"}
WEB_TABLES = {"web_usuarios", "web_sessoes", "web_login_tentativas"}

# All documented columns, with canonical pg_catalog.format_type() output.
COLUMNS = {
    "vagas": {
        "id": "bigint", "fonte": "text", "id_externo": "text", "url": "text",
        "url_canonica": "text", "hash_texto": "text", "empresa": "text",
        "cargo": "text", "nivel": "text", "modelo": "text", "cidade": "text",
        "uf": "text", "pais": "text", "tipo_contrato": "text",
        "salario_min": "numeric(12,2)", "salario_max": "numeric(12,2)",
        "moeda": "character varying(3)", "aderencia": "smallint",
        "score_prefiltro": "smallint", "habilidades_pedidas": "text",
        "o_que_falta": "text", "como_candidatar": "text", "prazo": "date",
        "descricao": "text", "status_notificacao": "text",
        "status_candidatura": "text", "status_disponibilidade": "text",
        "data_status": "timestamp with time zone", "observacoes": "text",
        "data_envio": "timestamp with time zone",
        "data_inscricao": "timestamp with time zone",
        "comprovante_inscricao": "text", "data_publicacao": "date",
        "primeira_coleta": "timestamp with time zone",
        "ultima_verificacao": "timestamp with time zone",
        "atualizado_em": "timestamp with time zone",
    },
    "vagas_status_hist": {
        "id": "bigint", "vaga_id": "bigint", "tipo": "text",
        "status_anterior": "text", "status_novo": "text",
        "alterado_em": "timestamp with time zone",
        "alterado_por": "text", "observacao": "text",
    },
    "web_usuarios": {
        "id": "bigint", "email": "text", "senha_hash": "text",
        "papel": "text", "ativo": "boolean",
        "criado_em": "timestamp with time zone",
        "atualizado_em": "timestamp with time zone",
        "ultimo_login_em": "timestamp with time zone",
    },
    "web_sessoes": {
        "id": "bigint", "usuario_id": "bigint", "token_hash": "character(64)",
        "criado_em": "timestamp with time zone",
        "expira_em": "timestamp with time zone",
        "revogada_em": "timestamp with time zone",
    },
    "web_login_tentativas": {
        "id": "bigint", "email": "text",
        "criado_em": "timestamp with time zone",
    },
}
REQUIRED_NOT_NULL = {
    "vagas": {"id", "fonte", "url", "url_canonica", "empresa", "cargo",
              "pais", "moeda", "status_notificacao", "status_candidatura",
              "status_disponibilidade", "primeira_coleta", "ultima_verificacao",
              "atualizado_em"},
    "vagas_status_hist": {"id", "vaga_id", "tipo", "status_novo",
                         "alterado_em", "alterado_por"},
    "web_usuarios": {"id", "email", "senha_hash", "papel", "ativo",
                     "criado_em", "atualizado_em"},
    "web_sessoes": {"id", "usuario_id", "token_hash", "criado_em", "expira_em"},
    "web_login_tentativas": {"id", "email", "criado_em"},
}
INDEXES = (
    "ux_empregos_vagas_fonte_id_externo",
    "ix_empregos_vagas_coleta",
    "ix_empregos_vagas_status",
    "ix_empregos_vagas_aderencia",
    "ix_empregos_vagas_hash",
    "ix_empregos_vagas_hist_vaga_data",
    "ux_jobs_usuarios_email",
    "ix_jobs_sessoes_usuario",
    "ix_jobs_login_tentativas",
)
PROCEDURES = (
    "empregos.mcp_salvar_vaga(jsonb)",
    "empregos.mcp_consultar_vagas(jsonb)",
    "empregos.mcp_atualizar_status(jsonb)",
    "empregos.mcp_descrever_schema()",
    "empregos.fn_auditar_status()",
)


class SchemaProblem(RuntimeError):
    """Unsafe or unsupported migration state."""


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def schema_tables(conn):
    return set(row[0] for row in conn.execute(
        """SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'empregos'"""
    ).fetchall())


def role_exists(conn, name):
    return bool(scalar(conn, "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (name,)))


def v2_ready(conn):
    if not scalar(conn, "SELECT to_regclass('empregos.vagas_status_hist') IS NOT NULL"):
        return False
    check = scalar(conn, """
        SELECT COALESCE((
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid=to_regclass('empregos.vagas_status_hist')
              AND conname='vagas_status_hist_tipo_check'
        ), '')""")
    trigger = scalar(conn, """
        SELECT COALESCE((
            SELECT pg_get_triggerdef(oid)
            FROM pg_trigger
            WHERE tgrelid=to_regclass('empregos.vagas')
              AND tgname='trg_empregos_auditar_status' AND NOT tgisinternal
        ), '')""")
    status_fn = scalar(conn, """
        SELECT COALESCE((
            SELECT pg_get_functiondef(to_regprocedure('empregos.mcp_atualizar_status(jsonb)'))
            WHERE to_regprocedure('empregos.mcp_atualizar_status(jsonb)') IS NOT NULL
        ), '')""")
    return ("DISPONIBILIDADE" in check and
            "status_disponibilidade" in trigger and
            "bot_realizou_inscricao" in status_fn and
            "VERIFICACAO_SITE" in status_fn)


def comprovante_ready(conn):
    """True quando a função de status já sabe preencher ou recusar comprovante."""
    status_fn = scalar(conn, """
        SELECT COALESCE((
            SELECT pg_get_functiondef(to_regprocedure('empregos.mcp_atualizar_status(jsonb)'))
            WHERE to_regprocedure('empregos.mcp_atualizar_status(jsonb)') IS NOT NULL
        ), '')""")
    return ("COMPROVANTE_REGISTRADO" in status_fn and
            "COMPROVANTE_JA_EXISTENTE" in status_fn)


def verify_columns(conn, names):
    for table in names:
        rows = conn.execute("""
            SELECT a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod) AS typ, a.attnotnull
            FROM pg_catalog.pg_attribute a
            WHERE a.attrelid=to_regclass(%s) AND a.attnum>0 AND NOT a.attisdropped
        """, (f"empregos.{table}",)).fetchall()
        found = {row[0]: (row[1], row[2]) for row in rows}
        for col, expected_type in COLUMNS[table].items():
            if col not in found:
                raise SchemaProblem(f"Coluna ausente: empregos.{table}.{col}. Migração manual versionada necessária.")
            actual_type, is_required = found[col]
            if actual_type != expected_type:
                raise SchemaProblem(
                    f"Tipo divergente: empregos.{table}.{col}: {actual_type}; esperado {expected_type}."
                )
            if col in REQUIRED_NOT_NULL[table] and not is_required:
                raise SchemaProblem(f"NOT NULL ausente: empregos.{table}.{col}.")
    LOG.info("Todas as colunas e tipos obrigatórios conferidos.")


def verify_fk(conn, source, target, column):
    row = conn.execute("""
        SELECT pg_get_constraintdef(c.oid), c.confdeltype
        FROM pg_constraint c
        WHERE c.conrelid=to_regclass(%s) AND c.confrelid=to_regclass(%s)
          AND c.contype='f'
    """, (f"empregos.{source}", f"empregos.{target}")).fetchall()
    if not any(f"FOREIGN KEY ({column})" in desc and delete_action == "c" for desc, delete_action in row):
        raise SchemaProblem(f"FK {source}.{column} -> {target}.id com CASCADE ausente.")


def verify(conn):
    tables = schema_tables(conn)
    for table in COLUMNS:
        if table not in tables:
            raise SchemaProblem(f"Tabela ausente: empregos.{table}.")
    verify_columns(conn, COLUMNS)

    for table in ("vagas", "vagas_status_hist", "web_usuarios", "web_sessoes", "web_login_tentativas"):
        if not scalar(conn, """
            SELECT EXISTS (SELECT 1 FROM pg_constraint
                WHERE conrelid=to_regclass(%s) AND contype='p')
        """, (f"empregos.{table}",)):
            raise SchemaProblem(f"Chave primária ausente: empregos.{table}.")
    verify_fk(conn, "vagas_status_hist", "vagas", "vaga_id")
    verify_fk(conn, "web_sessoes", "web_usuarios", "usuario_id")
    for name in INDEXES:
        if scalar(conn, "SELECT to_regclass(%s)", (f"empregos.{name}",)) is None:
            raise SchemaProblem(f"Índice ausente: empregos.{name}.")
    for name in PROCEDURES:
        if scalar(conn, "SELECT to_regprocedure(%s)", (name,)) is None:
            raise SchemaProblem(f"Função ausente: {name}.")
    if not v2_ready(conn):
        raise SchemaProblem("Migração de status v2 ausente ou incompleta.")
    if not comprovante_ready(conn):
        raise SchemaProblem("Migração de comprovante em vaga já INSCRITO ausente ou incompleta.")
    for role in ("gaq_jobs_web", "gaq_jobs_grok"):
        if not role_exists(conn, role):
            raise SchemaProblem(f"Role ausente: {role}.")
    if not scalar(conn, """
        SELECT has_table_privilege('gaq_jobs_web', 'empregos.vagas', 'SELECT')
        AND has_column_privilege('gaq_jobs_web','empregos.vagas','status_candidatura','UPDATE')
        AND has_table_privilege('gaq_jobs_grok', 'empregos.vagas', 'SELECT') = false
    """):
        raise SchemaProblem("Permissões web/Grok inesperadas; verifique GRANT/REVOKE.")
    checks = [row[0] for row in conn.execute("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid=to_regclass('empregos.vagas_status_hist') AND contype='c'
    """)]
    if not any("DISPONIBILIDADE" in chk for chk in checks):
        raise SchemaProblem("Constraint de histórico de status v2 ausente.")
    LOG.info("Validação de tabelas, chaves, índices, funções e privilégios concluída.")


def apply_sql(conn, key):
    filename = SCRIPTS[key]
    sql_file = SQL_ROOT / filename
    if not sql_file.is_file():
        raise SchemaProblem(f"Arquivo de migração não encontrado: {filename}")
    LOG.info("Executando migração conhecida: %s", filename)
    conn.execute(sql_file.read_text(encoding="utf-8"))


def set_initial_password(conn, role, environment, role_preexisted):
    if role_preexisted:
        LOG.info("Role %s já existia; senha preservada.", role)
        return
    password = os.getenv(environment, "")
    if len(password) < 24:
        raise SchemaProblem(
            f"{environment} precisa ter ao menos 24 caracteres ao criar {role}; nada foi aplicado."
        )
    conn.execute(sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
        sql.Identifier(role), sql.Literal(password)
    ))
    LOG.info("Senha inicial definida para %s (valor não exibido).", role)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mode = os.getenv("GAQ_SCHEMA_MODE", "apply").lower()
    if mode not in ("apply", "check"):
        raise SchemaProblem("GAQ_SCHEMA_MODE deve ser apply ou check.")
    if os.getenv("PGDATABASE", "gaq") != "gaq":
        raise SchemaProblem("Proteção: PGDATABASE precisa ser gaq.")
    conninfo = dict(
        host=os.environ["PGHOST"],
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "gaq"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        connect_timeout=12,
        application_name="gaq_jobs_schema_migrator",
    )
    with psycopg.connect(**conninfo) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(319007, 202611)")
            if scalar(conn, "SELECT current_database()") != "gaq":
                raise SchemaProblem("Conectado a database diferente de gaq.")
            current_tables = schema_tables(conn)
            partial_core = current_tables & BASE_TABLES
            if partial_core and partial_core != BASE_TABLES:
                raise SchemaProblem("Banco parcialmente criado (vagas/histórico). Requer revisão manual.")
            before_roles = {role: role_exists(conn, role) for role in ("gaq_jobs_web", "gaq_jobs_grok")}
            applied = []

            if not partial_core:
                if current_tables:
                    raise SchemaProblem(
                        "Schema empregos contém outras tabelas, mas falta o núcleo de vagas. "
                        "Recusando bootstrap para preservar objetos existentes."
                    )
                if mode == "check":
                    raise SchemaProblem("Schema GAQ Jobs ainda não instalado (modo check).")
                for key in ("base", "dictionary", "status_v2", "comprovante_inscrito", "auth"):
                    apply_sql(conn, key)
                    applied.append(key)
            else:
                # Existing databases: never rerun the broad-permission baseline.
                verify_columns(conn, BASE_TABLES)
                if scalar(conn, "SELECT to_regprocedure('empregos.mcp_descrever_schema()')") is None:
                    if mode == "check":
                        raise SchemaProblem("Dicionário de dados ausente (modo check).")
                    apply_sql(conn, "dictionary")
                    applied.append("dictionary")
                if not v2_ready(conn):
                    if mode == "check":
                        raise SchemaProblem("Migração de status v2 necessária (modo check).")
                    apply_sql(conn, "status_v2")
                    applied.append("status_v2")
                if not comprovante_ready(conn):
                    if mode == "check":
                        raise SchemaProblem(
                            "Migração de comprovante em vaga já INSCRITO necessária (modo check)."
                        )
                    apply_sql(conn, "comprovante_inscrito")
                    applied.append("comprovante_inscrito")

                existing_web = current_tables & WEB_TABLES
                needs_auth = (existing_web != WEB_TABLES or
                              not before_roles["gaq_jobs_web"])
                if needs_auth:
                    if mode == "check":
                        raise SchemaProblem("Autenticação web incompleta (modo check).")
                    apply_sql(conn, "auth")
                    applied.append("auth")

            if mode == "apply":
                set_initial_password(conn, "gaq_jobs_web",
                                     "GAQ_DB_WEB_INITIAL_PASSWORD", before_roles["gaq_jobs_web"])
                set_initial_password(conn, "gaq_jobs_grok",
                                     "GAQ_DB_GROK_INITIAL_PASSWORD", before_roles["gaq_jobs_grok"])
            verify(conn)

            if mode == "apply":
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS empregos.schema_migrations (
                        version TEXT PRIMARY KEY,
                        file_sha256 CHAR(64) NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        origin TEXT NOT NULL CHECK (origin IN ('applied','adopted'))
                    )
                """)
                # Track known migration scripts. Existing installation is "adopted",
                # rather than claiming that the new runner applied it.
                for key, filename in SCRIPTS.items():
                    digest = hashlib.sha256((SQL_ROOT / filename).read_bytes()).hexdigest()
                    record = conn.execute(
                        "SELECT file_sha256 FROM empregos.schema_migrations WHERE version=%s", (key,)
                    ).fetchone()
                    if record and record[0] != digest:
                        raise SchemaProblem(
                            f"Arquivo versionado alterado para {key}. "
                            "Crie nova migração; não altere uma migração existente."
                        )
                    if not record:
                        conn.execute("""
                            INSERT INTO empregos.schema_migrations
                               (version, file_sha256, origin) VALUES (%s,%s,%s)
                        """, (key, digest, "applied" if key in applied else "adopted"))
                LOG.info("Banco verificado. Migrações executadas: %s.",
                         ", ".join(applied) if applied else "nenhuma")
            else:
                LOG.info("Modo check: estrutura válida, nenhuma alteração realizada.")
    LOG.info("Concluído. API pode iniciar.")


if __name__ == "__main__":
    try:
        main()
    except (SchemaProblem, psycopg.Error, KeyError, ValueError) as error:
        # Never print connection strings, passwords, or PG environment values.
        LOG.error("Inicialização segura interrompida: %s", error)
        raise SystemExit(1) from None
