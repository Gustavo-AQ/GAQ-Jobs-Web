-- Verificacao da regra de comprovante em vaga ja INSCRITO.
-- Nao e migracao: nao entra no migrador nem no init do laboratorio.
-- Execute depois de db/030_comprovante_inscrito_whodb.sql, no database gaq:
--   psql -v ON_ERROR_STOP=1 -d gaq -f db/030_comprovante_inscrito_verificar.sql
-- A transacao termina com ROLLBACK. O bloco tambem apaga as vagas de teste
-- antes de sair, para o caso de o cliente confirmar a transacao.

BEGIN;

DO $verifica$
DECLARE
  v_vazio BIGINT;
  v_branco BIGINT;
  v_texto_vazio BIGINT;
  v_transicao BIGINT;
  v_sobrescrever BIGINT;
  v_notificacao BIGINT;
  v_site BIGINT;
  v_bot BIGINT;
  v_email BIGINT;
  v_email_outra BIGINT;
  v_email_reuso BIGINT;
  v_uso BIGINT;
  v_sem_campo BIGINT;
  v_interesse BIGINT;
  v_longo BIGINT;
  v_hist BIGINT;
  v_hist_depois BIGINT;
  v_data TIMESTAMPTZ := TIMESTAMPTZ '2020-01-02 03:04:05+00';
  v_obs TEXT := 'nota pessoal que nao pode mudar';
  v_proto TEXT := 'Portal mostrou protocolo ABC-123';
  r JSONB;
  v_comp TEXT;
  v_status TEXT;
  v_obs_lida TEXT;
  v_data_lida TIMESTAMPTZ;
  v_data_status TIMESTAMPTZ;
  v_notif TEXT;
  v_disp TEXT;
BEGIN
  IF current_database() <> 'gaq' THEN
    RAISE EXCEPTION 'ABORTADO: banco esperado gaq; conectado em %', current_database();
  END IF;
  IF pg_catalog.strpos(
       pg_catalog.pg_get_functiondef('empregos.mcp_atualizar_status(jsonb)'::regprocedure),
       'COMPROVANTE_REGISTRADO'
     ) = 0
     OR pg_catalog.strpos(
       pg_catalog.pg_get_functiondef('empregos.mcp_atualizar_status(jsonb)'::regprocedure),
       'COMPROVANTE_JA_EXISTENTE'
     ) = 0
     OR pg_catalog.to_regclass('empregos.vagas_email_uso') IS NULL
  THEN
    RAISE EXCEPTION 'FALHA: aplique db/030_comprovante_inscrito_whodb.sql antes desta verificacao';
  END IF;
  IF pg_catalog.has_table_privilege('gaq_jobs_grok', 'empregos.vagas_email_uso', 'SELECT')
     OR pg_catalog.has_table_privilege('gaq_jobs_grok', 'empregos.vagas_email_uso', 'INSERT')
     OR pg_catalog.has_table_privilege('gaq_jobs_grok', 'empregos.vagas_email_uso', 'UPDATE')
  THEN
    RAISE EXCEPTION 'FALHA: gaq_jobs_grok nao pode acessar vagas_email_uso direto';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'gaq_jobs_web')
     AND (
       pg_catalog.has_table_privilege('gaq_jobs_web', 'empregos.vagas_email_uso', 'SELECT')
       OR pg_catalog.has_table_privilege('gaq_jobs_web', 'empregos.vagas_email_uso', 'INSERT')
       OR pg_catalog.has_table_privilege('gaq_jobs_web', 'empregos.vagas_email_uso', 'UPDATE')
     )
  THEN
    RAISE EXCEPTION 'FALHA: gaq_jobs_web nao pode acessar vagas_email_uso direto';
  END IF;

  DELETE FROM empregos.vagas
  WHERE url_canonica LIKE 'https://example.invalid/gaq-comprovante-%';

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura,
    observacoes, data_inscricao, data_status
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-vazio',
    'https://example.invalid/gaq-comprovante-vazio', 'Verificacao', 'Cargo vazio',
    'INSCRITO', v_obs, v_data, v_data
  ) RETURNING id INTO v_vazio;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura,
    observacoes, comprovante_inscricao, data_inscricao
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-branco',
    'https://example.invalid/gaq-comprovante-branco', 'Verificacao', 'Cargo branco',
    'INSCRITO', v_obs, '   ', v_data
  ) RETURNING id INTO v_branco;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura,
    observacoes, comprovante_inscricao
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-texto-vazio',
    'https://example.invalid/gaq-comprovante-texto-vazio', 'Verificacao', 'Cargo string vazia',
    'INSCRITO', v_obs, ''
  ) RETURNING id INTO v_texto_vazio;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-transicao',
    'https://example.invalid/gaq-comprovante-transicao', 'Verificacao', 'Cargo transicao',
    v_obs
  ) RETURNING id INTO v_transicao;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura,
    observacoes, comprovante_inscricao
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-sobrescrever',
    'https://example.invalid/gaq-comprovante-sobrescrever', 'Verificacao', 'Cargo sobrescrever',
    'INTERESSE', v_obs, 'protocolo antigo'
  ) RETURNING id INTO v_sobrescrever;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-notificacao',
    'https://example.invalid/gaq-comprovante-notificacao', 'Verificacao', 'Cargo notificacao',
    v_obs
  ) RETURNING id INTO v_notificacao;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura,
    observacoes, comprovante_inscricao
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-site',
    'https://example.invalid/gaq-comprovante-site', 'Verificacao', 'Cargo site',
    'INSCRITO', v_obs, 'proto site'
  ) RETURNING id INTO v_site;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-bot',
    'https://example.invalid/gaq-comprovante-bot', 'Verificacao', 'Cargo bot',
    v_obs
  ) RETURNING id INTO v_bot;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-email',
    'https://example.invalid/gaq-comprovante-email', 'Verificacao', 'Cargo email',
    'INSCRITO', v_obs
  ) RETURNING id INTO v_email;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-email-outra',
    'https://example.invalid/gaq-comprovante-email-outra', 'Verificacao', 'Cargo email outra',
    v_obs
  ) RETURNING id INTO v_email_outra;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-email-reuso',
    'https://example.invalid/gaq-comprovante-email-reuso', 'Verificacao', 'Cargo email reuso',
    'INSCRITO', v_obs
  ) RETURNING id INTO v_email_reuso;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-sem-campo',
    'https://example.invalid/gaq-comprovante-sem-campo', 'Verificacao', 'Cargo sem campo',
    'INSCRITO', v_obs
  ) RETURNING id INTO v_sem_campo;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-interesse',
    'https://example.invalid/gaq-comprovante-interesse', 'Verificacao', 'Cargo interesse',
    'INTERESSE', v_obs
  ) RETURNING id INTO v_interesse;

  INSERT INTO empregos.vagas (
    fonte, url, url_canonica, empresa, cargo, status_candidatura, observacoes
  ) VALUES (
    'VERIFICACAO', 'https://example.invalid/gaq-comprovante-longo',
    'https://example.invalid/gaq-comprovante-longo', 'Verificacao', 'Cargo longo',
    'INSCRITO', v_obs
  ) RETURNING id INTO v_longo;

  SELECT count(*) INTO v_hist
  FROM empregos.vagas_status_hist WHERE vaga_id = v_vazio;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas'
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' OR (r->>'ok')::boolean IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'FALHA: INSCRITO sem comprovante novo deveria ser SEM_ALTERACAO: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', ''
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' THEN
    RAISE EXCEPTION 'FALHA: comprovante string vazia nao e preenchimento: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', '   '
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' THEN
    RAISE EXCEPTION 'FALHA: comprovante so com espacos nao e preenchimento: %', r;
  END IF;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
      'comprovante_inscricao', v_proto,
      'evidencia', 'Usuario confirmou o protocolo no portal de vagas'
    ));
    RAISE EXCEPTION 'FALHA: origem ausente deveria recusar o preenchimento';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%PEDIDO_USUARIO ou EMAIL%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado sem origem: %', SQLERRM;
      END IF;
  END;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
      'origem', 'PEDIDO_USUARIO', 'evidencia', 'curta',
      'comprovante_inscricao', v_proto
    ));
    RAISE EXCEPTION 'FALHA: evidencia curta deveria recusar o preenchimento';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%evidencia detalhada%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado com evidencia curta: %', SQLERRM;
      END IF;
  END;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
      'origem', 'EMAIL',
      'evidencia', 'Email do portal confirmou a inscricao realizada',
      'comprovante_inscricao', v_proto
    ));
    RAISE EXCEPTION 'FALHA: EMAIL sem campos do Gmail deveria recusar';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%gmail_message_id%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado no EMAIL incompleto: %', SQLERRM;
      END IF;
  END;

  SELECT comprovante_inscricao, status_candidatura, observacoes, data_inscricao
  INTO v_comp, v_status, v_obs_lida, v_data_lida
  FROM empregos.vagas WHERE id = v_vazio;
  IF v_comp IS NOT NULL OR v_status IS DISTINCT FROM 'INSCRITO'
     OR v_obs_lida IS DISTINCT FROM v_obs OR v_data_lida IS DISTINCT FROM v_data THEN
    RAISE EXCEPTION 'FALHA: tentativa invalida alterou a vaga vazia';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'pedido_usuario',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', '  ' || v_proto || '  ',
    'observacao', 'isto nao pode ir para a coluna observacoes'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO'
     OR (r->>'ok')::boolean IS DISTINCT FROM TRUE
     OR r->>'status' IS DISTINCT FROM 'INSCRITO'
     OR r->>'status_novo' IS DISTINCT FROM 'INSCRITO'
     OR r->>'comprovante_inscricao' IS DISTINCT FROM v_proto THEN
    RAISE EXCEPTION 'FALHA: preenchimento de comprovante vazio: %', r;
  END IF;

  SELECT count(*) INTO v_hist_depois
  FROM empregos.vagas_status_hist WHERE vaga_id = v_vazio;
  SELECT comprovante_inscricao, status_candidatura, status_notificacao,
         status_disponibilidade, observacoes, data_inscricao, data_status
  INTO v_comp, v_status, v_notif, v_disp, v_obs_lida, v_data_lida, v_data_status
  FROM empregos.vagas WHERE id = v_vazio;
  IF v_comp IS DISTINCT FROM v_proto OR v_status IS DISTINCT FROM 'INSCRITO'
     OR v_notif IS DISTINCT FROM 'NOVA' OR v_disp IS DISTINCT FROM 'DESCONHECIDA'
     OR v_obs_lida IS DISTINCT FROM v_obs OR v_data_lida IS DISTINCT FROM v_data
     OR v_data_status IS DISTINCT FROM v_data OR v_hist_depois IS DISTINCT FROM v_hist THEN
    RAISE EXCEPTION 'FALHA: preenchimento mudou status, datas, observacoes ou historico';
  END IF;
  SELECT count(*) INTO v_uso FROM empregos.vagas_email_uso WHERE vaga_id = v_vazio;
  IF v_uso <> 0 THEN
    RAISE EXCEPTION 'FALHA: pedido do usuario nao deve consumir mensagem de Gmail';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario enviou um segundo protocolo diferente do primeiro',
    'comprovante_inscricao', 'outro protocolo XYZ'
  ));
  IF (r->>'ok')::boolean IS DISTINCT FROM FALSE
     OR r->>'acao' IS DISTINCT FROM 'COMPROVANTE_JA_EXISTENTE'
     OR r->>'erro' IS DISTINCT FROM 'COMPROVANTE_JA_EXISTENTE' THEN
    RAISE EXCEPTION 'FALHA: comprovante existente deveria ser recusado: %', r;
  END IF;
  SELECT comprovante_inscricao, status_candidatura, observacoes
  INTO v_comp, v_status, v_obs_lida
  FROM empregos.vagas WHERE id = v_vazio;
  IF v_comp IS DISTINCT FROM v_proto OR v_status IS DISTINCT FROM 'INSCRITO'
     OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: recusa alterou comprovante, status ou observacoes';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario repetiu o mesmo protocolo que ja estava gravado',
    'comprovante_inscricao', v_proto
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_JA_EXISTENTE' OR (r->>'ok')::boolean IS DISTINCT FROM FALSE THEN
    RAISE EXCEPTION 'FALHA: repetir o mesmo comprovante nao pode ser ignorado em silencio: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario so confirmou que o status continua inscrito'
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' OR (r->>'ok')::boolean IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'FALHA: chamada sem comprovante continua SEM_ALTERACAO: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_branco, 'status', 'INSCRITO', 'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', 'protocolo do campo em branco'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO' THEN
    RAISE EXCEPTION 'FALHA: comprovante so com espacos deveria aceitar preenchimento: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_texto_vazio, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', 'protocolo da string vazia'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO' THEN
    RAISE EXCEPTION 'FALHA: comprovante string vazia deveria aceitar preenchimento: %', r;
  END IF;

  SELECT count(*) INTO v_hist FROM empregos.vagas_status_hist WHERE vaga_id = v_transicao;
  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_transicao, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario pediu para marcar a inscricao como concluida',
    'comprovante_inscricao', 'protocolo da transicao',
    'observacao', 'nota de historico que nao e a coluna observacoes'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' OR r->>'status_novo' IS DISTINCT FROM 'INSCRITO' THEN
    RAISE EXCEPTION 'FALHA: transicao para INSCRITO com comprovante: %', r;
  END IF;
  SELECT count(*) INTO v_hist_depois FROM empregos.vagas_status_hist WHERE vaga_id = v_transicao;
  SELECT comprovante_inscricao, observacoes INTO v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_transicao;
  IF v_comp IS DISTINCT FROM 'protocolo da transicao' OR v_obs_lida IS DISTINCT FROM v_obs
     OR v_hist_depois <> v_hist + 1 THEN
    RAISE EXCEPTION 'FALHA: transicao nao gravou comprovante, mexeu em observacoes ou nao auditou';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_transicao, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario tentou trocar o protocolo depois da inscricao',
    'comprovante_inscricao', 'protocolo substituto'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_JA_EXISTENTE' THEN
    RAISE EXCEPTION 'FALHA: segundo comprovante apos INSCRITO: %', r;
  END IF;
  SELECT comprovante_inscricao INTO v_comp FROM empregos.vagas WHERE id = v_transicao;
  IF v_comp IS DISTINCT FROM 'protocolo da transicao' THEN
    RAISE EXCEPTION 'FALHA: comprovante da transicao foi sobrescrito';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_sobrescrever, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario pediu INSCRITO e mandou um protocolo diferente',
    'comprovante_inscricao', 'protocolo novo'
  ));
  IF (r->>'ok')::boolean IS DISTINCT FROM FALSE
     OR r->>'acao' IS DISTINCT FROM 'COMPROVANTE_JA_EXISTENTE'
     OR r->>'status' IS DISTINCT FROM 'INTERESSE' THEN
    RAISE EXCEPTION 'FALHA: troca de comprovante na transicao deveria recusar: %', r;
  END IF;
  SELECT status_candidatura, comprovante_inscricao, observacoes
  INTO v_status, v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_sobrescrever;
  IF v_status IS DISTINCT FROM 'INTERESSE' OR v_comp IS DISTINCT FROM 'protocolo antigo'
     OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: recusa na transicao alterou status, comprovante ou observacoes';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_sobrescrever, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario pediu INSCRITO repetindo o protocolo que ja existia',
    'comprovante_inscricao', 'protocolo antigo'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' OR r->>'status_novo' IS DISTINCT FROM 'INSCRITO' THEN
    RAISE EXCEPTION 'FALHA: mesmo comprovante nao deveria impedir a mudanca de status: %', r;
  END IF;
  SELECT comprovante_inscricao, observacoes INTO v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_sobrescrever;
  IF v_comp IS DISTINCT FROM 'protocolo antigo' OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: status mudou, mas o comprovante ou observacoes foram reescritos';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_notificacao, 'status', 'ENVIADA'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' OR r->>'status_novo' IS DISTINCT FROM 'ENVIADA' THEN
    RAISE EXCEPTION 'FALHA: NOVA para ENVIADA: %', r;
  END IF;
  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_notificacao, 'status', 'ENVIADA',
    'comprovante_inscricao', 'nao deve gravar neste campo'
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' THEN
    RAISE EXCEPTION 'FALHA: ENVIADA repetida deveria continuar SEM_ALTERACAO: %', r;
  END IF;
  SELECT comprovante_inscricao, observacoes INTO v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_notificacao;
  IF v_comp IS NOT NULL OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: notificacao gravou comprovante ou observacoes';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_site, 'campo', 'DISPONIBILIDADE', 'status', 'ATIVA',
    'origem', 'VERIFICACAO_SITE',
    'evidencia', 'A pagina do anuncio ainda lista a vaga como aberta',
    'comprovante_inscricao', 'tentativa de trocar pelo caminho de disponibilidade'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' OR r->>'status_novo' IS DISTINCT FROM 'ATIVA' THEN
    RAISE EXCEPTION 'FALHA: disponibilidade por VERIFICACAO_SITE: %', r;
  END IF;
  SELECT comprovante_inscricao, status_candidatura, status_disponibilidade, observacoes
  INTO v_comp, v_status, v_disp, v_obs_lida
  FROM empregos.vagas WHERE id = v_site;
  IF v_comp IS DISTINCT FROM 'proto site' OR v_status IS DISTINCT FROM 'INSCRITO'
     OR v_disp IS DISTINCT FROM 'ATIVA' OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: disponibilidade alterou comprovante, candidatura ou observacoes';
  END IF;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_bot, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
      'origem', 'PEDIDO_USUARIO',
      'evidencia', 'O bot concluiu a inscricao e o usuario pediu o registro',
      'bot_realizou_inscricao', TRUE
    ));
    RAISE EXCEPTION 'FALHA: bot sem comprovante deveria recusar INSCRITO';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%exige comprovante_inscricao%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado no bot sem comprovante: %', SQLERRM;
      END IF;
  END;
  SELECT status_candidatura INTO v_status FROM empregos.vagas WHERE id = v_bot;
  IF v_status IS DISTINCT FROM 'NAO_AVALIADA' THEN
    RAISE EXCEPTION 'FALHA: bot sem comprovante mudou o status';
  END IF;
  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_bot, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'O bot concluiu a inscricao e o usuario pediu o registro',
    'bot_realizou_inscricao', TRUE,
    'comprovante_inscricao', 'protocolo do bot'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' THEN
    RAISE EXCEPTION 'FALHA: bot com comprovante deveria marcar INSCRITO: %', r;
  END IF;
  SELECT comprovante_inscricao, observacoes INTO v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_bot;
  IF v_comp IS DISTINCT FROM 'protocolo do bot' OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: inscricao do bot nao preservou observacoes ou o comprovante';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_email, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'EMAIL',
    'evidencia', 'Email do portal confirmou a inscricao realizada',
    'comprovante_inscricao', 'protocolo vindo do email',
    'gmail_message_id', 'msg-comprovante-1',
    'email_remetente', 'portal@example.invalid',
    'email_assunto', 'Inscricao confirmada'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO' OR r->>'status' IS DISTINCT FROM 'INSCRITO' THEN
    RAISE EXCEPTION 'FALHA: EMAIL deveria registrar comprovante vazio: %', r;
  END IF;
  SELECT count(*) INTO v_hist_depois
  FROM empregos.vagas_status_hist WHERE vaga_id = v_email;
  SELECT count(*) INTO v_uso
  FROM empregos.vagas_email_uso
  WHERE gmail_message_id = 'msg-comprovante-1' AND vaga_id = v_email AND status = 'INSCRITO';
  IF v_hist_depois <> 0 OR v_uso <> 1 THEN
    RAISE EXCEPTION 'FALHA: EMAIL do comprovante deveria gravar vagas_email_uso sem historico de status';
  END IF;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_email_reuso, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
      'origem', 'EMAIL',
      'evidencia', 'A mesma mensagem nao pode registrar outro comprovante',
      'comprovante_inscricao', 'protocolo reutilizado',
      'gmail_message_id', 'msg-comprovante-1',
      'email_remetente', 'portal@example.invalid',
      'email_assunto', 'Inscricao confirmada'
    ));
    RAISE EXCEPTION 'FALHA: o mesmo Gmail ID deveria ser recusado em outro comprovante';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%ja foi usada%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado no reuso do comprovante: %', SQLERRM;
      END IF;
  END;
  SELECT comprovante_inscricao, status_candidatura, observacoes
  INTO v_comp, v_status, v_obs_lida
  FROM empregos.vagas WHERE id = v_email_reuso;
  SELECT count(*) INTO v_uso
  FROM empregos.vagas_email_uso WHERE vaga_id = v_email_reuso;
  IF v_comp IS NOT NULL OR v_status IS DISTINCT FROM 'INSCRITO'
     OR v_obs_lida IS DISTINCT FROM v_obs OR v_uso <> 0 THEN
    RAISE EXCEPTION 'FALHA: reuso de Gmail alterou a outra vaga ou gravou o uso';
  END IF;

  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_email_reuso, 'campo', 'CANDIDATURA', 'status', 'EM_PROCESSO',
      'origem', 'EMAIL',
      'evidencia', 'A mesma mensagem nao pode mudar outro status',
      'gmail_message_id', 'msg-comprovante-1',
      'email_remetente', 'portal@example.invalid',
      'email_assunto', 'Inscricao confirmada'
    ));
    RAISE EXCEPTION 'FALHA: Gmail usado no comprovante deveria bloquear outro status';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%ja foi usada%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado ao bloquear status com Gmail do comprovante: %', SQLERRM;
      END IF;
  END;
  SELECT status_candidatura, observacoes INTO v_status, v_obs_lida
  FROM empregos.vagas WHERE id = v_email_reuso;
  IF v_status IS DISTINCT FROM 'INSCRITO' OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: bloqueio do Gmail mudou status ou observacoes';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_email_outra, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'EMAIL',
    'evidencia', 'Outro email do portal confirmou uma inscricao distinta',
    'comprovante_inscricao', 'protocolo da outra vaga',
    'gmail_message_id', 'msg-comprovante-unica',
    'email_remetente', 'portal@example.invalid',
    'email_assunto', 'Inscricao confirmada'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' THEN
    RAISE EXCEPTION 'FALHA: EMAIL deveria marcar a outra vaga como INSCRITO: %', r;
  END IF;
  BEGIN
    PERFORM empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
      'vaga_id', v_transicao, 'campo', 'CANDIDATURA', 'status', 'EM_PROCESSO',
      'origem', 'EMAIL',
      'evidencia', 'O mesmo email nao pode justificar outro status',
      'gmail_message_id', 'msg-comprovante-unica',
      'email_remetente', 'portal@example.invalid',
      'email_assunto', 'Inscricao confirmada'
    ));
    RAISE EXCEPTION 'FALHA: o mesmo Gmail ID deveria ser recusado em outro status';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE '%ja foi usada%' THEN
        RAISE EXCEPTION 'FALHA: erro inesperado na reutilizacao de Gmail: %', SQLERRM;
      END IF;
  END;
  SELECT status_candidatura INTO v_status FROM empregos.vagas WHERE id = v_transicao;
  IF v_status IS DISTINCT FROM 'INSCRITO' THEN
    RAISE EXCEPTION 'FALHA: Gmail reutilizado mudou o status da vaga';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_sem_campo, 'status', 'INSCRITO', 'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou o protocolo no portal de vagas',
    'comprovante_inscricao', 'protocolo sem campo explicito'
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO' OR r->>'campo' IS DISTINCT FROM 'CANDIDATURA' THEN
    RAISE EXCEPTION 'FALHA: INSCRITO sem campo explicito deveria preencher comprovante: %', r;
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_interesse, 'campo', 'CANDIDATURA', 'status', 'INTERESSE',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario mantem interesse e anexou um texto de comprovante',
    'comprovante_inscricao', 'nao deve gravar fora de INSCRITO'
  ));
  IF r->>'acao' IS DISTINCT FROM 'SEM_ALTERACAO' THEN
    RAISE EXCEPTION 'FALHA: INTERESSE repetido deveria ser SEM_ALTERACAO: %', r;
  END IF;
  SELECT comprovante_inscricao INTO v_comp FROM empregos.vagas WHERE id = v_interesse;
  IF v_comp IS NOT NULL THEN
    RAISE EXCEPTION 'FALHA: comprovante foi gravado sem status INSCRITO';
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_longo, 'campo', 'CANDIDATURA', 'status', 'INSCRITO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario confirmou um protocolo mais longo que o limite',
    'comprovante_inscricao', repeat('A', 2001)
  ));
  IF r->>'acao' IS DISTINCT FROM 'COMPROVANTE_REGISTRADO'
     OR length(r->>'comprovante_inscricao') <> 2000 THEN
    RAISE EXCEPTION 'FALHA: comprovante deveria ser truncado em 2000 caracteres: %', length(r->>'comprovante_inscricao');
  END IF;

  r := empregos.mcp_atualizar_status(pg_catalog.jsonb_build_object(
    'vaga_id', v_vazio, 'campo', 'CANDIDATURA', 'status', 'EM_PROCESSO',
    'origem', 'PEDIDO_USUARIO',
    'evidencia', 'Usuario pediu para avancar a candidatura no processo',
    'comprovante_inscricao', 'nao deve substituir o protocolo ja gravado'
  ));
  IF r->>'acao' IS DISTINCT FROM 'ATUALIZADA' OR r->>'status_novo' IS DISTINCT FROM 'EM_PROCESSO' THEN
    RAISE EXCEPTION 'FALHA: avancar a candidatura nao deveria esbarrar no comprovante: %', r;
  END IF;
  SELECT comprovante_inscricao, observacoes INTO v_comp, v_obs_lida
  FROM empregos.vagas WHERE id = v_vazio;
  IF v_comp IS DISTINCT FROM v_proto OR v_obs_lida IS DISTINCT FROM v_obs THEN
    RAISE EXCEPTION 'FALHA: mudanca para EM_PROCESSO alterou comprovante ou observacoes';
  END IF;

  IF pg_catalog.strpos(empregos.mcp_descrever_schema()::text, 'COMPROVANTE_REGISTRADO') = 0
     OR pg_catalog.strpos(empregos.mcp_descrever_schema()::text, 'COMPROVANTE_JA_EXISTENTE') = 0
     OR pg_catalog.strpos(empregos.mcp_descrever_schema()::text, '"versao_documentacao": "2.1"') = 0 THEN
    RAISE EXCEPTION 'FALHA: descrever_schema nao publica a regra nova do comprovante';
  END IF;
  IF pg_catalog.strpos(
       COALESCE(pg_catalog.col_description('empregos.vagas'::regclass, (
         SELECT a.attnum FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = 'empregos.vagas'::regclass
           AND a.attname = 'comprovante_inscricao' AND NOT a.attisdropped
       )), ''),
       'COMPROVANTE_JA_EXISTENTE'
     ) = 0 THEN
    RAISE EXCEPTION 'FALHA: comentario da coluna comprovante_inscricao nao foi atualizado';
  END IF;

  DELETE FROM empregos.vagas
  WHERE url_canonica LIKE 'https://example.invalid/gaq-comprovante-%';
END;
$verifica$;

ROLLBACK;
