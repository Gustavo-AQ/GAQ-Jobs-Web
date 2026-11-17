-- GAQ Jobs — Migracao v2 de status / WhoDB
-- 16/11/2026. Executar conectado ao banco gaq, como administrador.
-- Um UNICO comando DO para compatibilidade com o Scratchpad do WhoDB.
-- Preserva vagas, IDs, historico, usuarios e credenciais existentes.
-- ATENCAO: os campos de evidencia sao DECLARACOES do agente; o PostgreSQL
-- NAO tem acesso ao Gmail e nao prova sozinho que o email/pedido existe.

DO $migracao$
BEGIN
  IF current_database() <> 'gaq' THEN
    RAISE EXCEPTION 'ABORTADO: banco esperado gaq; conectado em %', current_database();
  END IF;

  -- Permitir auditoria da disponibilidade na mesma tabela de historico.
  ALTER TABLE empregos.vagas_status_hist
    DROP CONSTRAINT IF EXISTS vagas_status_hist_tipo_check;
  ALTER TABLE empregos.vagas_status_hist
    ADD CONSTRAINT vagas_status_hist_tipo_check
    CHECK (tipo IN ('NOTIFICACAO', 'CANDIDATURA', 'DISPONIBILIDADE'));

  EXECUTE $ddl$
  CREATE OR REPLACE FUNCTION empregos.fn_auditar_status()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, empregos
  AS $fn$
  DECLARE
    v_ator TEXT := COALESCE(NULLIF(pg_catalog.current_setting('empregos.actor', true), ''), CURRENT_USER);
    v_obs TEXT := NULLIF(pg_catalog.current_setting('empregos.obs', true), '');
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
    IF NEW.status_disponibilidade IS DISTINCT FROM OLD.status_disponibilidade THEN
      INSERT INTO empregos.vagas_status_hist
        (vaga_id, tipo, status_anterior, status_novo, alterado_por, observacao)
      VALUES
        (NEW.id, 'DISPONIBILIDADE', OLD.status_disponibilidade, NEW.status_disponibilidade, v_ator, v_obs);
    END IF;
    RETURN NEW;
  END;
  $fn$;
  $ddl$;

  DROP TRIGGER IF EXISTS trg_empregos_auditar_status ON empregos.vagas;
  CREATE TRIGGER trg_empregos_auditar_status
    AFTER UPDATE OF status_notificacao, status_candidatura, status_disponibilidade
    ON empregos.vagas
    FOR EACH ROW EXECUTE FUNCTION empregos.fn_auditar_status();

  EXECUTE $ddl$
  CREATE OR REPLACE FUNCTION empregos.mcp_atualizar_status(p JSONB)
  RETURNS JSONB
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, empregos
  AS $fn$
  DECLARE
    v_id BIGINT;
    v_status TEXT;
    v_campo TEXT;
    v_origem TEXT;
    v_evidencia TEXT;
    v_observacao TEXT;
    v_email_id TEXT;
    v_email_remetente TEXT;
    v_email_assunto TEXT;
    v_comprovante TEXT;
    v_atual empregos.vagas%ROWTYPE;
    v_anterior TEXT;
    v_ator TEXT;
    v_obs_hist TEXT;
  BEGIN
    IF p IS NULL OR pg_catalog.jsonb_typeof(p) <> 'object' OR length(p::text) > 12000 THEN
      RAISE EXCEPTION 'Informe um JSON objeto valido (maximo 12000 caracteres)';
    END IF;
    v_id := NULLIF(pg_catalog.btrim(p->>'vaga_id'), '')::BIGINT;
    v_status := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'status')), '');
    v_campo := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'campo')), '');
    v_origem := NULLIF(pg_catalog.upper(pg_catalog.btrim(p->>'origem')), '');
    v_evidencia := LEFT(NULLIF(pg_catalog.btrim(p->>'evidencia'), ''), 1200);
    v_observacao := LEFT(NULLIF(pg_catalog.btrim(p->>'observacao'), ''), 1000);
    v_email_id := LEFT(NULLIF(pg_catalog.btrim(p->>'gmail_message_id'), ''), 255);
    v_email_remetente := LEFT(NULLIF(pg_catalog.btrim(p->>'email_remetente'), ''), 255);
    v_email_assunto := LEFT(NULLIF(pg_catalog.btrim(p->>'email_assunto'), ''), 255);
    v_comprovante := LEFT(NULLIF(pg_catalog.btrim(p->>'comprovante_inscricao'), ''), 2000);

    IF v_id IS NULL OR v_status IS NULL THEN
      RAISE EXCEPTION 'Obrigatorios: vaga_id e status';
    END IF;

    -- Permitir compatibilidade com chamadas antigas NOVA/ENVIADA/INSCRITO.
    IF v_campo IS NULL THEN
      IF v_status IN ('NOVA', 'ENVIADA') THEN
        v_campo := 'NOTIFICACAO';
      ELSIF v_status IN ('ATIVA', 'EXPIRADA', 'DESCONHECIDA') THEN
        v_campo := 'DISPONIBILIDADE';
      ELSE
        v_campo := 'CANDIDATURA';
      END IF;
    END IF;

    IF v_campo = 'NOTIFICACAO' AND v_status NOT IN ('NOVA', 'ENVIADA') THEN
      RAISE EXCEPTION 'NOTIFICACAO aceita NOVA ou ENVIADA';
    ELSIF v_campo = 'CANDIDATURA' AND v_status NOT IN
      ('NAO_AVALIADA', 'INTERESSE', 'DESCARTADA', 'INSCRITO',
       'EM_PROCESSO', 'ENTREVISTA', 'TESTE_TECNICO', 'OFERTA', 'REPROVADO', 'CONTRATADO') THEN
      RAISE EXCEPTION 'Status de candidatura invalido';
    ELSIF v_campo = 'DISPONIBILIDADE' AND v_status NOT IN ('DESCONHECIDA', 'ATIVA', 'EXPIRADA') THEN
      RAISE EXCEPTION 'Status de disponibilidade invalido';
    ELSIF v_campo NOT IN ('NOTIFICACAO', 'CANDIDATURA', 'DISPONIBILIDADE') THEN
      RAISE EXCEPTION 'campo invalido: NOTIFICACAO, CANDIDATURA ou DISPONIBILIDADE';
    END IF;

    SELECT * INTO v_atual FROM empregos.vagas WHERE id = v_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Vaga % nao encontrada', v_id; END IF;
    v_anterior := CASE v_campo
      WHEN 'NOTIFICACAO' THEN v_atual.status_notificacao
      WHEN 'CANDIDATURA' THEN v_atual.status_candidatura
      ELSE v_atual.status_disponibilidade
    END;

    IF v_anterior = v_status THEN
      RETURN pg_catalog.jsonb_build_object('ok', TRUE, 'acao', 'SEM_ALTERACAO',
        'vaga_id', v_id, 'campo', v_campo, 'status', v_status);
    END IF;

    -- Somente a notificacao NOVA -> ENVIADA e automatica, apos informar o usuario.
    -- Nenhuma transicao de candidatura pode ocorrer sem evidencias.
    IF v_campo = 'NOTIFICACAO' AND v_status = 'ENVIADA' AND v_anterior = 'NOVA' THEN
      v_origem := 'NOTIFICACAO';
      v_ator := 'grok_bot:notificacao';
      v_evidencia := COALESCE(v_evidencia, 'Grok informou a vaga ao usuario');
    ELSIF v_campo = 'DISPONIBILIDADE' AND v_origem = 'VERIFICACAO_SITE' THEN
      IF v_evidencia IS NULL THEN
        RAISE EXCEPTION 'Disponibilidade por verificacao de site exige evidencia da pagina consultada';
      END IF;
      v_ator := 'grok_bot:site';
    ELSE
      IF v_origem NOT IN ('PEDIDO_USUARIO', 'EMAIL') OR v_origem IS NULL THEN
        RAISE EXCEPTION 'Alteracao protegida exige origem PEDIDO_USUARIO ou EMAIL';
      END IF;
      IF v_evidencia IS NULL OR length(v_evidencia) < 12 THEN
        RAISE EXCEPTION 'Alteracao protegida exige evidencia detalhada (minimo 12 caracteres)';
      END IF;
      IF v_origem = 'EMAIL' THEN
        IF v_campo = 'NOTIFICACAO' THEN
          RAISE EXCEPTION 'EMAIL nao autoriza reiniciar notificacoes';
        END IF;
        IF v_campo = 'CANDIDATURA' AND v_status IN ('INTERESSE', 'DESCARTADA', 'NAO_AVALIADA') THEN
          RAISE EXCEPTION 'Interesse, descarte e reinicio de candidatura exigem pedido do usuario';
        END IF;
        IF v_email_id IS NULL OR v_email_remetente IS NULL OR v_email_assunto IS NULL THEN
          RAISE EXCEPTION 'EMAIL exige gmail_message_id, email_remetente e email_assunto';
        END IF;
        -- Um mesmo email nao pode justificar vagas ou resultados diferentes.
        IF EXISTS (
          SELECT 1 FROM empregos.vagas_status_hist h
          WHERE h.alterado_por = 'grok_bot:email'
            AND pg_catalog.strpos(COALESCE(h.observacao,''), 'GmailID=' || v_email_id || ';') > 0
            AND (h.vaga_id <> v_id OR h.status_novo <> v_status)
        ) THEN
          RAISE EXCEPTION 'Esta mensagem do Gmail ja foi usada para outra vaga ou outro status';
        END IF;
        v_ator := 'grok_bot:email';
      ELSE
        v_ator := 'grok_bot:pedido_usuario';
      END IF;
    END IF;

    -- Evitar que uma tentativa de preenchimento seja registrada como inscricao concluida.
    IF v_campo = 'CANDIDATURA' AND v_status = 'INSCRITO' THEN
      IF v_origem <> 'PEDIDO_USUARIO' AND v_origem <> 'EMAIL' THEN
        RAISE EXCEPTION 'INSCRITO exige pedido do usuario ou comprovacao por email';
      END IF;
      -- Para candidatura executada pelo bot, registrar confirmacao do portal.
      IF COALESCE((p->>'bot_realizou_inscricao')::BOOLEAN, FALSE) = TRUE AND v_comprovante IS NULL THEN
        RAISE EXCEPTION 'Candidatura realizada pelo bot exige comprovante_inscricao';
      END IF;
    END IF;

    v_obs_hist := LEFT(
      'Origem=' || v_origem || '; ' ||
      CASE WHEN v_email_id IS NOT NULL AND v_origem = 'EMAIL'
           THEN 'GmailID=' || v_email_id || '; Remetente=' || v_email_remetente || '; Assunto=' || v_email_assunto || '; '
           ELSE '' END ||
      'Evidencia=' || COALESCE(v_evidencia, '') ||
      CASE WHEN v_observacao IS NOT NULL THEN '; Obs=' || v_observacao ELSE '' END,
      3000);
    PERFORM pg_catalog.set_config('empregos.actor', v_ator, TRUE);
    PERFORM pg_catalog.set_config('empregos.obs', v_obs_hist, TRUE);

    IF v_campo = 'NOTIFICACAO' THEN
      UPDATE empregos.vagas SET
        status_notificacao = v_status,
        data_envio = CASE WHEN v_status = 'ENVIADA' THEN COALESCE(data_envio, NOW()) ELSE data_envio END,
        atualizado_em = NOW()
      WHERE id = v_id;
    ELSIF v_campo = 'CANDIDATURA' THEN
      UPDATE empregos.vagas SET
        status_candidatura = v_status,
        data_status = NOW(),
        data_inscricao = CASE WHEN v_status = 'INSCRITO' THEN COALESCE(data_inscricao, NOW()) ELSE data_inscricao END,
        comprovante_inscricao = CASE WHEN v_status = 'INSCRITO' THEN COALESCE(v_comprovante, comprovante_inscricao) ELSE comprovante_inscricao END,
        atualizado_em = NOW()
      WHERE id = v_id;
    ELSE
      UPDATE empregos.vagas SET
        status_disponibilidade = v_status,
        atualizado_em = NOW()
      WHERE id = v_id;
    END IF;

    RETURN (
      SELECT pg_catalog.jsonb_build_object(
        'ok', TRUE, 'acao', 'ATUALIZADA', 'vaga_id', v.id,
        'campo', v_campo, 'status_anterior', v_anterior, 'status_novo', v_status,
        'origem', v_origem,
        'status_notificacao', v.status_notificacao,
        'status_candidatura', v.status_candidatura,
        'status_disponibilidade', v.status_disponibilidade,
        'data_envio', v.data_envio, 'data_inscricao', v.data_inscricao
      ) FROM empregos.vagas v WHERE v.id = v_id
    );
  END;
  $fn$;
  $ddl$;


  -- Atualizar o dicionario de dados que o Grok consulta pela quarta ferramenta.
  EXECUTE $ddl$
CREATE OR REPLACE FUNCTION empregos.mcp_descrever_schema()
RETURNS JSONB
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, empregos
AS $query$
WITH tables AS (
   SELECT c.oid, c.relname
   FROM pg_catalog.pg_class c
   JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'empregos' AND c.relname IN ('vagas','vagas_status_hist') AND c.relkind IN ('r','p')
)
SELECT pg_catalog.jsonb_build_object(
 'projeto', 'GAQ Jobs',
 'banco', pg_catalog.current_database(),
 'schema', 'empregos',
 'versao_documentacao', '2.0',
 'orientacao', 'Use somente as funcoes MCP, nao SQL direto. Comentarios sao documentacao; restricoes reais sao aplicadas pelo esquema e pelas funcoes.',
 'tabelas', COALESCE((
   SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
      'nome', t.relname,
      'descricao', pg_catalog.obj_description(t.oid, 'pg_class'),
      'colunas', (SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
          'nome', a.attname,
          'tipo', pg_catalog.format_type(a.atttypid, a.atttypmod),
          'nao_nulo', a.attnotnull,
          'padrao', pg_catalog.pg_get_expr(d.adbin, d.adrelid),
          'descricao', pg_catalog.col_description(t.oid, a.attnum)
      ) ORDER BY a.attnum)
      FROM pg_catalog.pg_attribute a
      LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
      WHERE a.attrelid = t.oid AND a.attnum > 0 AND NOT a.attisdropped)
   ) ORDER BY t.relname) FROM tables t
 ), '[]'::JSONB),
 'ferramentas', pg_catalog.jsonb_build_array(
   pg_catalog.jsonb_build_object('nome','salvar_vaga','obrigatorios', pg_catalog.jsonb_build_array('fonte','url','empresa','cargo'),'funcao','empregos.mcp_salvar_vaga(jsonb)','regra','Salva ou reencontra; retorna vaga_id. Nunca envia status no cadastro.'),
   pg_catalog.jsonb_build_object('nome','consultar_vagas','funcao','empregos.mcp_consultar_vagas(jsonb)','filtros',pg_catalog.jsonb_build_array('id','termo','status','fonte','modelo','nivel','aderencia_min','apenas_nao_enviadas','limite','offset'),'regra','Limite 1..50; status NOVA/ENVIADA e notificacao, outros status sao candidatura.'),
   pg_catalog.jsonb_build_object('nome','atualizar_status_vaga','funcao','empregos.mcp_atualizar_status(jsonb)','status_permitidos', pg_catalog.jsonb_build_array('NOVA','ENVIADA','NAO_AVALIADA','INTERESSE','DESCARTADA','INSCRITO','EM_PROCESSO','ENTREVISTA','TESTE_TECNICO','OFERTA','REPROVADO','CONTRATADO','DESCONHECIDA','ATIVA','EXPIRADA'),'regra','Campos: NOTIFICACAO, CANDIDATURA, DISPONIBILIDADE. NOVA para ENVIADA automatica apos comunicar. CANDIDATURA exige origem PEDIDO_USUARIO ou EMAIL e evidencia. EMAIL exige gmail_message_id, email_remetente e email_assunto; essas provas sao declaradas pelo Grok, nao verificadas pelo banco. DISPONIBILIDADE permite VERIFICACAO_SITE com evidencia.'),
   pg_catalog.jsonb_build_object('nome','descrever_banco','funcao','empregos.mcp_descrever_schema()','regra','Somente leitura de metadados das tabelas empregos.vagas e empregos.vagas_status_hist.')
 )
);
$query$;
  $ddl$;

  EXECUTE $ddl$
  COMMENT ON TABLE empregos.vagas_status_hist IS
    'Historico automatico dos status NOTIFICACAO, CANDIDATURA e DISPONIBILIDADE; origem e evidencia resumidas em observacao';
  $ddl$;
  EXECUTE $ddl$
  COMMENT ON COLUMN empregos.vagas.status_candidatura IS
    'NAO_AVALIADA, INTERESSE, DESCARTADA, INSCRITO, EM_PROCESSO, ENTREVISTA, TESTE_TECNICO, OFERTA, REPROVADO, CONTRATADO. Grok pode alterar mediante PEDIDO_USUARIO ou EMAIL com evidencia declarada; SQL nao verifica autenticidade de emails/pedidos.';
  $ddl$;
  EXECUTE $ddl$
  COMMENT ON COLUMN empregos.vagas.status_disponibilidade IS
    'DESCONHECIDA, ATIVA, EXPIRADA. Independente de candidatura. Verificacao do anuncio, pedido do usuario ou email com evidencia.';
  $ddl$;
  EXECUTE $ddl$
  COMMENT ON COLUMN empregos.vagas_status_hist.tipo IS
    'Tipo de alteracao: NOTIFICACAO, CANDIDATURA ou DISPONIBILIDADE.';
  $ddl$;

  REVOKE ALL ON FUNCTION empregos.mcp_atualizar_status(JSONB) FROM PUBLIC;
  GRANT EXECUTE ON FUNCTION empregos.mcp_atualizar_status(JSONB) TO gaq_jobs_grok;
END;
$migracao$;

-- TESTE POSTERIOR, EM CONSULTA SEPARADA, SEM MODIFICAR REGISTROS:
-- SELECT pg_get_functiondef('empregos.mcp_atualizar_status(jsonb)'::regprocedure);
-- SELECT COUNT(*) FROM empregos.vagas;
-- SELECT COUNT(*) FROM empregos.vagas_status_hist;