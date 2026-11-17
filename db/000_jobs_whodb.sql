-- GAQ CLOUD - instalacao adaptada para WhoDB Scratchpad (2026-11-16)
-- SQL unico: cole TODO o bloco no Scratchpad e clique em Correr uma vez.
-- Execucao atomica: erro desfaz todos os objetos criados nesta tentativa.
-- Banco conectado obrigatoriamente: gaq.
-- ATENCAO: apos o sucesso, execute ALTER ROLE com uma senha forte SEPARADAMENTE.

DO $gaq_install$
BEGIN

  EXECUTE $gaq_sql_1$
DO $dbcheck$
BEGIN
    IF pg_catalog.current_database() <> 'gaq' THEN
        RAISE EXCEPTION 'ABORTADO: rode no banco gaq, nao em %', pg_catalog.current_database();
    END IF;
END;
$dbcheck$;
$gaq_sql_1$;

  EXECUTE $gaq_sql_2$
CREATE SCHEMA IF NOT EXISTS empregos;
$gaq_sql_2$;

  EXECUTE $gaq_sql_3$
REVOKE ALL ON SCHEMA empregos FROM PUBLIC;
$gaq_sql_3$;

  EXECUTE $gaq_sql_4$
DO $create_role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'gaq_jobs_grok') THEN
        CREATE ROLE gaq_jobs_grok LOGIN;
    END IF;
END;
$create_role$;
$gaq_sql_4$;

  EXECUTE $gaq_sql_5$
CREATE TABLE IF NOT EXISTS empregos.vagas (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fonte                 TEXT NOT NULL CHECK (length(btrim(fonte)) BETWEEN 1 AND 100),
    id_externo            TEXT,
    url                   TEXT NOT NULL CHECK (url ~* '^https?://[^[:space:]]+$'),
    url_canonica          TEXT NOT NULL UNIQUE CHECK (url_canonica ~* '^https?://[^[:space:]]+$'),
    hash_texto            TEXT,

    empresa               TEXT NOT NULL CHECK (length(btrim(empresa)) > 0),
    cargo                 TEXT NOT NULL CHECK (length(btrim(cargo)) > 0),
    nivel                 TEXT,
    modelo                TEXT CHECK (modelo IS NULL OR modelo IN ('REMOTO','HIBRIDO','PRESENCIAL','NAO_INFORMADO')),
    cidade                TEXT,
    uf                    TEXT CHECK (uf IS NULL OR length(uf) = 2),
    pais                  TEXT NOT NULL DEFAULT 'Brasil',
    tipo_contrato         TEXT,
    salario_min           NUMERIC(12,2) CHECK (salario_min IS NULL OR salario_min >= 0),
    salario_max           NUMERIC(12,2) CHECK (salario_max IS NULL OR salario_max >= 0),
    moeda                 VARCHAR(3) NOT NULL DEFAULT 'BRL' CHECK (moeda ~ '^[A-Z]{3}$'),
    aderencia             SMALLINT CHECK (aderencia IS NULL OR aderencia BETWEEN 0 AND 100),
    score_prefiltro       SMALLINT CHECK (score_prefiltro IS NULL OR score_prefiltro BETWEEN 0 AND 100),
    habilidades_pedidas   TEXT,
    o_que_falta           TEXT,
    como_candidatar       TEXT,
    prazo                 DATE,
    descricao             TEXT,

    status_notificacao    TEXT NOT NULL DEFAULT 'NOVA'
                          CHECK (status_notificacao IN ('NOVA','ENVIADA')),
    status_candidatura    TEXT NOT NULL DEFAULT 'NAO_AVALIADA'
                          CHECK (status_candidatura IN (
                              'NAO_AVALIADA', 'INTERESSE', 'DESCARTADA', 'INSCRITO',
                              'EM_PROCESSO', 'ENTREVISTA', 'TESTE_TECNICO',
                              'OFERTA', 'REPROVADO', 'CONTRATADO')),
    status_disponibilidade TEXT NOT NULL DEFAULT 'DESCONHECIDA'
                          CHECK (status_disponibilidade IN ('ATIVA','EXPIRADA','DESCONHECIDA')),
    data_status           TIMESTAMPTZ,
    observacoes           TEXT, -- campo pessoal: Grok nao pode alterar
    data_envio            TIMESTAMPTZ,
    data_inscricao        TIMESTAMPTZ,
    comprovante_inscricao TEXT,
    data_publicacao       DATE,
    primeira_coleta       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultima_verificacao    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_salarios_ordem CHECK (
        salario_min IS NULL OR salario_max IS NULL OR salario_max >= salario_min
    )
);
$gaq_sql_5$;

  EXECUTE $gaq_sql_6$
-- O ID da vaga em um portal e um segundo indicador confiavel de duplicacao.
CREATE UNIQUE INDEX IF NOT EXISTS ux_empregos_vagas_fonte_id_externo
    ON empregos.vagas (fonte, id_externo) WHERE id_externo IS NOT NULL;
$gaq_sql_6$;

  EXECUTE $gaq_sql_7$
CREATE INDEX IF NOT EXISTS ix_empregos_vagas_coleta
    ON empregos.vagas (primeira_coleta DESC);
$gaq_sql_7$;

  EXECUTE $gaq_sql_8$
CREATE INDEX IF NOT EXISTS ix_empregos_vagas_status
    ON empregos.vagas (status_notificacao, status_candidatura);
$gaq_sql_8$;

  EXECUTE $gaq_sql_9$
CREATE INDEX IF NOT EXISTS ix_empregos_vagas_aderencia
    ON empregos.vagas (aderencia DESC NULLS LAST);
$gaq_sql_9$;

  EXECUTE $gaq_sql_10$
CREATE INDEX IF NOT EXISTS ix_empregos_vagas_hash
    ON empregos.vagas (hash_texto) WHERE hash_texto IS NOT NULL;
$gaq_sql_10$;

  EXECUTE $gaq_sql_11$
CREATE TABLE IF NOT EXISTS empregos.vagas_status_hist (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vaga_id         BIGINT NOT NULL REFERENCES empregos.vagas (id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('NOTIFICACAO','CANDIDATURA')),
    status_anterior TEXT,
    status_novo     TEXT NOT NULL,
    alterado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alterado_por    TEXT NOT NULL DEFAULT CURRENT_USER,
    observacao      TEXT
);
$gaq_sql_11$;

  EXECUTE $gaq_sql_12$
CREATE INDEX IF NOT EXISTS ix_empregos_vagas_hist_vaga_data
    ON empregos.vagas_status_hist (vaga_id, alterado_em DESC);
$gaq_sql_12$;

  EXECUTE $gaq_sql_13$
-- O historico e gerado automaticamente mesmo quando voce alterar status
-- via uma futura interface propria, desde que a alteracao use UPDATE.
CREATE OR REPLACE FUNCTION empregos.fn_auditar_status()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, empregos
AS $function$
DECLARE
    v_ator TEXT := COALESCE(NULLIF(pg_catalog.current_setting('empregos.actor', true), ''), CURRENT_USER);
    v_obs  TEXT := NULLIF(pg_catalog.current_setting('empregos.obs', true), '');
BEGIN
    IF NEW.status_notificacao IS DISTINCT FROM OLD.status_notificacao THEN
        INSERT INTO empregos.vagas_status_hist
            (vaga_id, tipo, status_anterior, status_novo, alterado_por, observacao)
        VALUES
            (NEW.id, 'NOTIFICACAO', OLD.status_notificacao, NEW.status_notificacao, v_ator, v_obs);
    END IF;
    IF NEW.status_candidatura IS DISTINCT FROM OLD.status_candidatura THEN
        INSERT INTO empregos.vagas_status_hist
            (vaga_id, tipo, status_anterior, status_novo, alterado_por, observacao)
        VALUES
            (NEW.id, 'CANDIDATURA', OLD.status_candidatura, NEW.status_candidatura, v_ator, v_obs);
    END IF;
    RETURN NEW;
END;
$function$;
$gaq_sql_13$;

  EXECUTE $gaq_sql_14$
DROP TRIGGER IF EXISTS trg_empregos_auditar_status ON empregos.vagas;
$gaq_sql_14$;

  EXECUTE $gaq_sql_15$
CREATE TRIGGER trg_empregos_auditar_status
AFTER UPDATE OF status_notificacao, status_candidatura ON empregos.vagas
FOR EACH ROW EXECUTE FUNCTION empregos.fn_auditar_status();
$gaq_sql_15$;

  EXECUTE $gaq_sql_16$
-- Ferramenta MCP 1: salvar ou reencontrar vaga (idempotente).
-- Entrada: OBJETO JSON com fonte, url, empresa, cargo obrigatorios.
-- Todos os demais campos sao opcionais.
-- Nao aceita campos de controle do usuario (status/observacoes) no cadastro.
CREATE OR REPLACE FUNCTION empregos.mcp_salvar_vaga(p JSONB)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, empregos
AS $function$
DECLARE
    v_fonte      TEXT;
    v_url        TEXT;
    v_canonica   TEXT;
    v_id_externo TEXT;
    v_empresa    TEXT;
    v_cargo      TEXT;
    v_hash       TEXT;
    v_modelo     TEXT;
    v_id         BIGINT;
    v_duplicada  BIGINT;
    v_acao       TEXT;
BEGIN
    IF p IS NULL OR pg_catalog.jsonb_typeof(p) <> 'object' THEN
        RAISE EXCEPTION 'Esperado um objeto JSON com os dados da vaga';
    END IF;
    IF length(p::text) > 250000 THEN
        RAISE EXCEPTION 'JSON muito grande (limite: 250000 caracteres)';
    END IF;

    v_fonte      := NULLIF(pg_catalog.btrim(p->>'fonte'), '');
    v_url        := NULLIF(pg_catalog.btrim(p->>'url'), '');
    v_id_externo := NULLIF(pg_catalog.btrim(p->>'id_externo'), '');
    v_empresa    := NULLIF(pg_catalog.btrim(p->>'empresa'), '');
    v_cargo      := NULLIF(pg_catalog.btrim(p->>'cargo'), '');
    IF v_fonte IS NULL OR v_url IS NULL OR v_empresa IS NULL OR v_cargo IS NULL THEN
        RAISE EXCEPTION 'Campos obrigatorios: fonte, url, empresa, cargo';
    END IF;
    IF v_url !~* '^https?://[^[:space:]]+$' THEN
        RAISE EXCEPTION 'URL invalida: deve iniciar com http(s)';
    END IF;
    -- Remocao de fragmento / barra final. Para utm, gclid etc., Grok
    -- deve fornecer url_canonica sem parametros de rastreamento.
    v_canonica := NULLIF(pg_catalog.btrim(p->>'url_canonica'), '');
    v_canonica := pg_catalog.regexp_replace(pg_catalog.split_part(COALESCE(v_canonica, v_url), '#', 1), '/+$', '');
    IF v_canonica !~* '^https?://[^[:space:]]+$' THEN
        RAISE EXCEPTION 'url_canonica invalida';
    END IF;
    v_modelo := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'modelo')), '');
    IF v_modelo IS NULL THEN v_modelo := 'NAO_INFORMADO'; END IF;

    -- Hash indicativo, nao UNIQUE: textos padronizados podem aparecer em vagas diferentes.
    -- Nao aceitar hash de formato arbitrario enviado pelo agente; calcular no servidor.
    IF NULLIF(pg_catalog.btrim(p->>'descricao'), '') IS NOT NULL THEN
        v_hash := pg_catalog.md5(
            pg_catalog.lower(pg_catalog.regexp_replace(pg_catalog.btrim(p->>'descricao'), '[[:space:]]+', ' ', 'g'))
            || '|' || pg_catalog.lower(v_empresa) || '|' || pg_catalog.lower(v_cargo)
        );
    END IF;

    -- Reencontrar pela identificacao externa ou pela URL canonica.
    SELECT id INTO v_id
    FROM empregos.vagas
    WHERE url_canonica = v_canonica
       OR (v_id_externo IS NOT NULL AND fonte = v_fonte AND id_externo = v_id_externo)
    ORDER BY CASE WHEN url_canonica = v_canonica THEN 0 ELSE 1 END
    LIMIT 1 FOR UPDATE;

    IF v_id IS NULL THEN
        INSERT INTO empregos.vagas (
            fonte, id_externo, url, url_canonica, hash_texto,
            empresa, cargo, nivel, modelo, cidade, uf, pais, tipo_contrato,
            salario_min, salario_max, moeda, aderencia, score_prefiltro,
            habilidades_pedidas, o_que_falta, como_candidatar, prazo,
            descricao, data_publicacao
        ) VALUES (
            v_fonte, v_id_externo, v_url, v_canonica, v_hash,
            v_empresa, v_cargo, NULLIF(p->>'nivel', ''), v_modelo,
            NULLIF(p->>'cidade',''), NULLIF(pg_catalog.upper(p->>'uf'), ''),
            COALESCE(NULLIF(p->>'pais',''), 'Brasil'), NULLIF(p->>'tipo_contrato',''),
            NULLIF(p->>'salario_min','')::NUMERIC(12,2),
            NULLIF(p->>'salario_max','')::NUMERIC(12,2),
            COALESCE(NULLIF(pg_catalog.upper(p->>'moeda'), ''), 'BRL'),
            NULLIF(p->>'aderencia','')::SMALLINT,
            NULLIF(p->>'score_prefiltro','')::SMALLINT,
            NULLIF(p->>'habilidades_pedidas',''), NULLIF(p->>'o_que_falta',''),
            NULLIF(p->>'como_candidatar',''), NULLIF(p->>'prazo','')::DATE,
            NULLIF(p->>'descricao',''), NULLIF(p->>'data_publicacao','')::DATE
        )
        ON CONFLICT (url_canonica) DO NOTHING
        RETURNING id INTO v_id;
        IF v_id IS NOT NULL THEN
            v_acao := 'CADASTRADA';
        END IF;
    END IF;

    -- Pode haver conflito concorrente com a URL; apenas atualizar campos tecnicos.
    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM empregos.vagas
        WHERE url_canonica = v_canonica FOR UPDATE;
    END IF;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'Nao foi possivel identificar o registro da vaga';
    END IF;

    IF v_acao IS NULL THEN v_acao := 'REENCONTRADA'; END IF;
    IF v_acao = 'REENCONTRADA' THEN
        UPDATE empregos.vagas AS v
        SET ultima_verificacao = NOW(),
            atualizado_em = NOW(),
            descricao = COALESCE(NULLIF(p->>'descricao',''), v.descricao),
            hash_texto = COALESCE(v_hash, v.hash_texto),
            aderencia = COALESCE(NULLIF(p->>'aderencia','')::SMALLINT, v.aderencia),
            score_prefiltro = COALESCE(NULLIF(p->>'score_prefiltro','')::SMALLINT, v.score_prefiltro),
            habilidades_pedidas = COALESCE(NULLIF(p->>'habilidades_pedidas',''), v.habilidades_pedidas),
            o_que_falta = COALESCE(NULLIF(p->>'o_que_falta',''), v.o_que_falta),
            salario_min = COALESCE(NULLIF(p->>'salario_min','')::NUMERIC(12,2), v.salario_min),
            salario_max = COALESCE(NULLIF(p->>'salario_max','')::NUMERIC(12,2), v.salario_max),
            prazo = COALESCE(NULLIF(p->>'prazo','')::DATE, v.prazo),
            data_publicacao = COALESCE(NULLIF(p->>'data_publicacao','')::DATE, v.data_publicacao)
        WHERE v.id = v_id;
        -- NAO alterar status_notificacao, status_candidatura, status_disponibilidade,
        -- data_envio, data_inscricao, observacoes, comprovante_inscricao.
    END IF;

    IF v_hash IS NOT NULL THEN
        SELECT id INTO v_duplicada
        FROM empregos.vagas
        WHERE id <> v_id AND hash_texto = v_hash
        ORDER BY id LIMIT 1;
    END IF;

    RETURN (
        SELECT pg_catalog.jsonb_build_object(
            'ok', TRUE, 'acao', v_acao, 'vaga_id', v.id,
            'status_notificacao', v.status_notificacao,
            'status_candidatura', v.status_candidatura,
            'possivel_duplicata_id', v_duplicada,
            'url_canonica', v.url_canonica
        )
        FROM empregos.vagas v WHERE v.id = v_id
    );
END;
$function$;
$gaq_sql_16$;

  EXECUTE $gaq_sql_17$
-- Ferramenta MCP 2: consultar vagas com filtros e paginacao (max 50 por chamada).
-- Exemplo: {"termo":"python", "modelo":"REMOTO", "status":"NOVA", "limite":10}
CREATE OR REPLACE FUNCTION empregos.mcp_consultar_vagas(p JSONB DEFAULT '{}'::JSONB)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, empregos
AS $function$
DECLARE
    v_limite INTEGER;
    v_offset INTEGER;
    v_termo TEXT;
    v_status TEXT;
    v_fonte TEXT;
    v_modelo TEXT;
    v_nivel TEXT;
    v_aderencia SMALLINT;
    v_id BIGINT;
    v_total BIGINT;
    v_resultado JSONB;
BEGIN
    IF p IS NULL OR pg_catalog.jsonb_typeof(p) <> 'object' THEN
        RAISE EXCEPTION 'Filtros devem ser um objeto JSON (pode ser {})';
    END IF;
    v_limite := LEAST(GREATEST(COALESCE(NULLIF(p->>'limite','')::INTEGER, 20), 1), 50);
    v_offset := LEAST(GREATEST(COALESCE(NULLIF(p->>'offset','')::INTEGER, 0), 0), 10000);
    v_termo := NULLIF(pg_catalog.btrim(p->>'termo'), '');
    v_status := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'status')), '');
    v_fonte := NULLIF(pg_catalog.btrim(p->>'fonte'), '');
    v_modelo := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'modelo')), '');
    v_nivel := NULLIF(pg_catalog.btrim(p->>'nivel'), '');
    v_aderencia := NULLIF(p->>'aderencia_min','')::SMALLINT;
    v_id := NULLIF(p->>'id','')::BIGINT;

    WITH filtradas AS (
        SELECT v.* FROM empregos.vagas v
        WHERE (v_id IS NULL OR v.id = v_id)
          AND (v_termo IS NULL OR (
              v.cargo ILIKE '%' || v_termo || '%' OR
              v.empresa ILIKE '%' || v_termo || '%' OR
              COALESCE(v.habilidades_pedidas, '') ILIKE '%' || v_termo || '%' OR
              COALESCE(v.descricao, '') ILIKE '%' || v_termo || '%'))
          AND (v_status IS NULL OR
              (v_status = 'NOVA' AND v.status_notificacao = 'NOVA') OR
              (v_status = 'ENVIADA' AND v.status_notificacao = 'ENVIADA') OR
              (v_status NOT IN ('NOVA','ENVIADA') AND v.status_candidatura = v_status))
          AND (v_fonte IS NULL OR v.fonte ILIKE v_fonte)
          AND (v_modelo IS NULL OR v.modelo = v_modelo)
          AND (v_nivel IS NULL OR v.nivel ILIKE v_nivel)
          AND (v_aderencia IS NULL OR v.aderencia >= v_aderencia)
          AND (COALESCE((p->>'apenas_nao_enviadas')::BOOLEAN, FALSE) = FALSE
               OR v.status_notificacao = 'NOVA')
    ), pagina AS (
        SELECT id, fonte, id_externo, url, empresa, cargo, nivel, modelo, cidade, uf, pais,
               tipo_contrato, salario_min, salario_max, moeda, aderencia, score_prefiltro,
               habilidades_pedidas, o_que_falta, como_candidatar, prazo,
               LEFT(descricao, 1500) AS resumo_descricao,
               status_notificacao, status_candidatura, status_disponibilidade,
               observacoes, data_publicacao, data_envio, data_inscricao,
               comprovante_inscricao, primeira_coleta, ultima_verificacao
        FROM filtradas
        ORDER BY primeira_coleta DESC, id DESC
        LIMIT v_limite OFFSET v_offset
    )
    SELECT (SELECT COUNT(*) FROM filtradas),
           COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(pagina)) FROM pagina), '[]'::JSONB)
    INTO v_total, v_resultado;

    RETURN pg_catalog.jsonb_build_object('ok', TRUE, 'total', v_total,
        'limite', v_limite, 'offset', v_offset, 'vagas', v_resultado);
END;
$function$;
$gaq_sql_17$;

  EXECUTE $gaq_sql_18$
-- Ferramenta MCP 3: somente NOVA, ENVIADA ou INSCRITO.
-- INSCRITO EXIGE comprovante_inscricao E confirmacao=true (evidencia declarada
-- pelo agente; confirmar a veracidade depende da verificacao no portal).
-- Exemplos:
--   {"vaga_id": 10, "status": "ENVIADA"}
--   {"vaga_id": 10, "status": "INSCRITO", "confirmacao": true,
--    "comprovante_inscricao": "Portal mostrou: candidatura enviada - protocolo ABC"}
CREATE OR REPLACE FUNCTION empregos.mcp_atualizar_status(p JSONB)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, empregos
AS $function$
DECLARE
    v_id BIGINT;
    v_status TEXT;
    v_comprovante TEXT;
    v_observacao TEXT;
    v_atual empregos.vagas%ROWTYPE;
    v_acao TEXT := 'SEM_ALTERACAO';
BEGIN
    IF p IS NULL OR pg_catalog.jsonb_typeof(p) <> 'object' THEN
        RAISE EXCEPTION 'Esperado objeto JSON';
    END IF;
    v_id := NULLIF(p->>'vaga_id','')::BIGINT;
    v_status := pg_catalog.upper(pg_catalog.btrim(p->>'status'));
    v_comprovante := NULLIF(pg_catalog.btrim(p->>'comprovante_inscricao'), '');
    v_observacao := LEFT(NULLIF(pg_catalog.btrim(p->>'observacao'), ''), 1000);

    IF v_id IS NULL OR v_status NOT IN ('NOVA','ENVIADA','INSCRITO') OR v_status IS NULL THEN
        RAISE EXCEPTION 'Forneca vaga_id e status: NOVA, ENVIADA ou INSCRITO';
    END IF;
    SELECT * INTO v_atual FROM empregos.vagas WHERE id = v_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Vaga % nao encontrada', v_id; END IF;
    PERFORM pg_catalog.set_config('empregos.actor', 'grok_bot', TRUE);
    PERFORM pg_catalog.set_config('empregos.obs', COALESCE(v_observacao, ''), TRUE);

    IF v_status = 'NOVA' THEN
        -- NOVA e estado inicial de notificacao. Nunca retroceder registros.
        IF v_atual.status_notificacao <> 'NOVA' OR v_atual.status_candidatura <> 'NAO_AVALIADA' THEN
            RAISE EXCEPTION 'Proibido retroceder vaga % para NOVA', v_id;
        END IF;
    ELSIF v_status = 'ENVIADA' THEN
        IF v_atual.status_notificacao = 'NOVA' THEN
            UPDATE empregos.vagas SET status_notificacao = 'ENVIADA',
                data_envio = COALESCE(data_envio, NOW()), atualizado_em = NOW()
            WHERE id = v_id;
            v_acao := 'ATUALIZADA';
        END IF;
    ELSIF v_status = 'INSCRITO' THEN
        IF v_atual.status_candidatura = 'INSCRITO' THEN
            -- Idempotente: chamada repetida nao altera a data inicial.
            NULL;
        ELSE
            IF v_atual.status_candidatura NOT IN ('NAO_AVALIADA','INTERESSE') THEN
                RAISE EXCEPTION 'Status atual % protegido: nao sobrescrever', v_atual.status_candidatura;
            END IF;
            IF COALESCE((p->>'confirmacao')::BOOLEAN, FALSE) <> TRUE OR v_comprovante IS NULL THEN
                RAISE EXCEPTION 'INSCRITO exige confirmacao=true e comprovante_inscricao nao vazio';
            END IF;
            UPDATE empregos.vagas
            SET status_candidatura = 'INSCRITO', data_status = NOW(),
                data_inscricao = COALESCE(data_inscricao, NOW()),
                comprovante_inscricao = LEFT(v_comprovante, 2000), atualizado_em = NOW()
            WHERE id = v_id;
            v_acao := 'ATUALIZADA';
        END IF;
    END IF;

    RETURN (
        SELECT pg_catalog.jsonb_build_object(
            'ok', TRUE, 'acao', v_acao, 'vaga_id', v.id,
            'status_notificacao', v.status_notificacao,
            'status_candidatura', v.status_candidatura,
            'data_envio', v.data_envio,
            'data_inscricao', v.data_inscricao
        ) FROM empregos.vagas v WHERE v.id = v_id
    );
END;
$function$;
$gaq_sql_18$;

  EXECUTE $gaq_sql_19$
-- Privilegios: ferramentas MCP nao acessam dados por SQL direto.
REVOKE ALL ON ALL TABLES IN SCHEMA empregos FROM PUBLIC;
$gaq_sql_19$;

  EXECUTE $gaq_sql_20$
REVOKE ALL ON ALL SEQUENCES IN SCHEMA empregos FROM PUBLIC;
$gaq_sql_20$;

  EXECUTE $gaq_sql_21$
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA empregos FROM PUBLIC;
$gaq_sql_21$;

  EXECUTE $gaq_sql_22$
GRANT USAGE ON SCHEMA empregos TO gaq_jobs_grok;
$gaq_sql_22$;

  EXECUTE $gaq_sql_23$
GRANT CONNECT ON DATABASE gaq TO gaq_jobs_grok;
$gaq_sql_23$;

  EXECUTE $gaq_sql_24$
GRANT EXECUTE ON FUNCTION empregos.mcp_salvar_vaga(JSONB) TO gaq_jobs_grok;
$gaq_sql_24$;

  EXECUTE $gaq_sql_25$
GRANT EXECUTE ON FUNCTION empregos.mcp_consultar_vagas(JSONB) TO gaq_jobs_grok;
$gaq_sql_25$;

  EXECUTE $gaq_sql_26$
GRANT EXECUTE ON FUNCTION empregos.mcp_atualizar_status(JSONB) TO gaq_jobs_grok;
$gaq_sql_26$;

END;
$gaq_install$;