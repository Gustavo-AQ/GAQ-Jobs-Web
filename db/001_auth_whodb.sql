-- GAQ Jobs Web - migration 001, somente banco gaq, executar como administrador.
-- Um comando DO para compatibilidade com WhoDB (prepared statements).
-- PRESERVA empregos.vagas e empregos.vagas_status_hist.
-- Execute separadamente apos a migracao:
-- ALTER ROLE gaq_jobs_web WITH PASSWORD 'SENHA_FORTE_DIFERENTE_DO_GROK';
DO $gaq$
BEGIN
  IF current_database() <> 'gaq' THEN
    RAISE EXCEPTION 'Banco esperado: gaq. Conectado: %', current_database();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='gaq_jobs_web') THEN
    CREATE ROLE gaq_jobs_web LOGIN;
  END IF;

  CREATE TABLE IF NOT EXISTS empregos.web_usuarios (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'LEITURA'
      CHECK (papel IN ('ADMIN','LEITURA')),
    ativo BOOLEAN NOT NULL DEFAULT true,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_login_em TIMESTAMPTZ
  );
  CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_usuarios_email
    ON empregos.web_usuarios (lower(email));

  CREATE TABLE IF NOT EXISTS empregos.web_sessoes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES empregos.web_usuarios(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em TIMESTAMPTZ NOT NULL,
    revogada_em TIMESTAMPTZ
  );
  CREATE INDEX IF NOT EXISTS ix_jobs_sessoes_usuario
    ON empregos.web_sessoes(usuario_id,expira_em DESC);

  CREATE TABLE IF NOT EXISTS empregos.web_login_tentativas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS ix_jobs_login_tentativas
    ON empregos.web_login_tentativas(email,criado_em DESC);

  REVOKE ALL ON empregos.web_usuarios, empregos.web_sessoes, empregos.web_login_tentativas FROM PUBLIC;
  -- Nao alterar grants PUBLIC das sequencias legadas do schema empregos.
  GRANT CONNECT ON DATABASE gaq TO gaq_jobs_web;
  GRANT USAGE ON SCHEMA empregos TO gaq_jobs_web;

  -- Vagas e historico: somente leitura e alteracao dos campos estritamente permitidos.
  GRANT SELECT ON empregos.vagas, empregos.vagas_status_hist TO gaq_jobs_web;
  GRANT UPDATE (status_candidatura, observacoes, data_status, data_inscricao, atualizado_em)
    ON empregos.vagas TO gaq_jobs_web;

  -- Tabelas exclusivas da autenticacao do painel.
  GRANT SELECT, INSERT, UPDATE, DELETE
    ON empregos.web_usuarios, empregos.web_sessoes, empregos.web_login_tentativas TO gaq_jobs_web;
  GRANT USAGE, SELECT
    ON SEQUENCE empregos.web_usuarios_id_seq,
                empregos.web_sessoes_id_seq,
                empregos.web_login_tentativas_id_seq TO gaq_jobs_web;
END
$gaq$;
