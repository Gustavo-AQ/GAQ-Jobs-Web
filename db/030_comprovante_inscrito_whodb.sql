-- GAQ Jobs — Comprovante em candidatura que já está INSCRITO
-- Idempotente (CREATE OR REPLACE). Executar no database gaq, como administrador.
-- Um único comando DO, para o Scratchpad do WhoDB.
-- Não apaga vagas, não altera observacoes e não cria bypass para o MCP
-- substituir um comprovante que já tem conteúdo.
--
-- Correção de comprovante já preenchido: o usuário, direto no banco
-- (WhoDB ou SQL administrativo). O painel web edita status_candidatura e
-- observacoes; não edita comprovante_inscricao. A role gaq_jobs_web não tem
-- UPDATE nessa coluna. Não existe origem que autorize o agente a trocar o texto.

DO $migracao$
BEGIN
  IF current_database() <> 'gaq' THEN
    RAISE EXCEPTION 'ABORTADO: banco esperado gaq; conectado em %', current_database();
  END IF;

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
    v_comprovante_atual TEXT;
    v_registrar_comprovante BOOLEAN := FALSE;
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
    v_comprovante_atual := NULLIF(pg_catalog.btrim(v_atual.comprovante_inscricao), '');
    -- Preenche comprovante vazio sem mudar o status, só quando já está INSCRITO.
    v_registrar_comprovante :=
      v_campo = 'CANDIDATURA'
      AND v_status = 'INSCRITO'
      AND v_anterior = v_status
      AND v_comprovante IS NOT NULL
      AND v_comprovante_atual IS NULL;

    -- Comprovante com conteúdo é imutável pelo agente. Recusa explícita, sem
    -- gravar status nem texto. Não há origem que autorize a troca por esta função.
    IF v_campo = 'CANDIDATURA'
       AND v_status = 'INSCRITO'
       AND v_comprovante IS NOT NULL
       AND v_comprovante_atual IS NOT NULL
       AND (
         v_anterior = v_status
         OR v_comprovante IS DISTINCT FROM v_comprovante_atual
       )
    THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', FALSE,
        'acao', 'COMPROVANTE_JA_EXISTENTE',
        'erro', 'COMPROVANTE_JA_EXISTENTE',
        'vaga_id', v_id,
        'campo', v_campo,
        'status', v_atual.status_candidatura,
        'mensagem', 'comprovante_inscricao ja possui conteudo e e imutavel pelo agente. A correcao e manual, feita pelo usuario direto no banco. O painel web nao edita este campo e esta funcao nao aceita bypass.'
      );
    END IF;

    IF v_anterior = v_status AND NOT v_registrar_comprovante THEN
      RETURN pg_catalog.jsonb_build_object('ok', TRUE, 'acao', 'SEM_ALTERACAO',
        'vaga_id', v_id, 'campo', v_campo, 'status', v_status);
    END IF;

    -- Somente a notificacao NOVA -> ENVIADA e automatica, apos informar o usuario.
    -- Nenhuma transicao de candidatura pode ocorrer sem evidencias.
    -- O preenchimento de comprovante vazio em vaga ja INSCRITO usa a mesma trava.
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

    -- Só o comprovante: status, data_inscricao, data_status e observacoes ficam como estão.
    -- Não gera histórico de status, porque nenhuma família de status mudou.
    IF v_registrar_comprovante THEN
      UPDATE empregos.vagas SET
        comprovante_inscricao = v_comprovante,
        atualizado_em = NOW()
      WHERE id = v_id;

      RETURN (
        SELECT pg_catalog.jsonb_build_object(
          'ok', TRUE, 'acao', 'COMPROVANTE_REGISTRADO', 'vaga_id', v.id,
          'campo', v_campo, 'status', v.status_candidatura,
          'status_anterior', v_anterior, 'status_novo', v.status_candidatura,
          'origem', v_origem,
          'comprovante_inscricao', v.comprovante_inscricao,
          'status_notificacao', v.status_notificacao,
          'status_candidatura', v.status_candidatura,
          'status_disponibilidade', v.status_disponibilidade,
          'data_envio', v.data_envio, 'data_inscricao', v.data_inscricao
        ) FROM empregos.vagas v WHERE v.id = v_id
      );
    END IF;

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
        comprovante_inscricao = CASE
          WHEN v_status = 'INSCRITO'
               AND v_comprovante IS NOT NULL
               AND NULLIF(pg_catalog.btrim(comprovante_inscricao), '') IS NULL
            THEN v_comprovante
          ELSE comprovante_inscricao
        END,
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

  EXECUTE $ddl$
  COMMENT ON FUNCTION empregos.mcp_atualizar_status(JSONB) IS
    'Atualiza um status via MCP. Se CANDIDATURA ja esta INSCRITO e comprovante_inscricao esta vazio, preenche o comprovante (acao COMPROVANTE_REGISTRADO) sem mudar o status. Se o comprovante ja tem conteudo, recusa com ok=false e acao COMPROVANTE_JA_EXISTENTE. Nao altera observacoes e nao oferece bypass.';
  $ddl$;

  EXECUTE $ddl$
  COMMENT ON COLUMN empregos.vagas.comprovante_inscricao IS
    'Texto de comprovacao: mensagem do portal, protocolo ou referencia. Ate 2000 caracteres na funcao MCP; nao inclua credenciais. NULL ou texto em branco conta como vazio: com CANDIDATURA ja INSCRITO, atualizar_status_vaga pode preencher (origem EMAIL ou PEDIDO_USUARIO e evidencia) e retorna COMPROVANTE_REGISTRADO, sem mudar o status. Se ja houver conteudo, o agente recebe COMPROVANTE_JA_EXISTENTE (ok=false) e o texto nao muda. Substituicao somente pelo usuario, direto no banco; o painel web nao edita esta coluna e o MCP nao tem bypass. | Tipo: TEXT.';
  $ddl$;

  -- A regra lida pelo agente em descrever_banco fica junto da funcao.
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
 'versao_documentacao', '2.1',
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
   pg_catalog.jsonb_build_object('nome','atualizar_status_vaga','funcao','empregos.mcp_atualizar_status(jsonb)','status_permitidos', pg_catalog.jsonb_build_array('NOVA','ENVIADA','NAO_AVALIADA','INTERESSE','DESCARTADA','INSCRITO','EM_PROCESSO','ENTREVISTA','TESTE_TECNICO','OFERTA','REPROVADO','CONTRATADO','DESCONHECIDA','ATIVA','EXPIRADA'),'regra','Campos: NOTIFICACAO, CANDIDATURA, DISPONIBILIDADE. NOVA para ENVIADA automatica apos comunicar. CANDIDATURA exige origem PEDIDO_USUARIO ou EMAIL e evidencia. EMAIL exige gmail_message_id, email_remetente e email_assunto; essas provas sao declaradas pelo Grok, nao verificadas pelo banco. DISPONIBILIDADE permite VERIFICACAO_SITE com evidencia. Se CANDIDATURA ja esta INSCRITO e comprovante_inscricao esta vazio (NULL ou branco), a mesma chamada com comprovante_inscricao, origem PEDIDO_USUARIO ou EMAIL e evidencia preenche o comprovante, mantem o status e retorna acao COMPROVANTE_REGISTRADO. Se o comprovante ja tem conteudo, ele e imutavel pelo agente: ok=false e acao COMPROVANTE_JA_EXISTENTE, sem alterar o texto. Correcao de comprovante existente e manual, pelo usuario, direto no banco. Nao ha origem que autorize o MCP a substituir. A funcao nao altera observacoes.'),
   pg_catalog.jsonb_build_object('nome','descrever_banco','funcao','empregos.mcp_descrever_schema()','regra','Somente leitura de metadados das tabelas empregos.vagas e empregos.vagas_status_hist.')
 )
);
$query$;
  $ddl$;

  REVOKE ALL ON FUNCTION empregos.mcp_atualizar_status(JSONB) FROM PUBLIC;
  GRANT EXECUTE ON FUNCTION empregos.mcp_atualizar_status(JSONB) TO gaq_jobs_grok;
  REVOKE ALL ON FUNCTION empregos.mcp_descrever_schema() FROM PUBLIC;
  GRANT EXECUTE ON FUNCTION empregos.mcp_descrever_schema() TO gaq_jobs_grok;
END;
$migracao$;

-- Conferencia opcional, em outra execucao, sem manter dados de teste:
-- psql -v ON_ERROR_STOP=1 -d gaq -f db/030_comprovante_inscrito_verificar.sql
-- SELECT pg_get_functiondef('empregos.mcp_atualizar_status(jsonb)'::regprocedure);
