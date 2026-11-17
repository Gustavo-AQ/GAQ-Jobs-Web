-- GAQ Jobs: documentacao no PostgreSQL 18 + ferramenta de consulta de metadados
-- Uso: executar o arquivo inteiro no WhoDB, conectado como ADMIN ao database gaq.
-- Um unico comando DO: evita erro do WhoDB com multiplos prepared statements.
-- Nao altera tabelas, registros, historico ou funcoes MCP existentes.
-- Cria COMENTARIOS e uma nova funcao de LEITURA empregos.mcp_descrever_schema().
-- Reexecutavel: comentarios anteriores serao atualizados com este texto.

DO $gaq_doc_install$
DECLARE
    r RECORD;
BEGIN
    IF pg_catalog.current_database() <> 'gaq' THEN
       RAISE EXCEPTION 'Rode o script apenas no database gaq';
    END IF;
    IF pg_catalog.to_regclass('empregos.vagas') IS NULL OR pg_catalog.to_regclass('empregos.vagas_status_hist') IS NULL THEN
       RAISE EXCEPTION 'As tabelas empregos.vagas e empregos.vagas_status_hist precisam existir';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'gaq_jobs_grok') THEN
       RAISE EXCEPTION 'Role gaq_jobs_grok nao existe; execute primeiro o instalador do GAQ Jobs';
    END IF;

    EXECUTE pg_catalog.format('COMMENT ON SCHEMA empregos IS %L', 'GAQ Jobs: armazenamento de vagas, acompanhamento de candidatura e historico. Acesso do bot restrito a funcoes MCP.');
    EXECUTE pg_catalog.format('COMMENT ON TABLE empregos.vagas IS %L', 'Tabela principal de oportunidades de emprego. Estados de notificacao e candidatura independentes. O Grok grava apenas atraves das funcoes MCP.');
    EXECUTE pg_catalog.format('COMMENT ON TABLE empregos.vagas_status_hist IS %L', 'Historico automatico de mudancas de status_notificacao e status_candidatura via gatilho. Nao audita disponibilidade.');

    -- Comentarios coluna a coluna a partir do dicionario aprovado.
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.id IS %L', 'Chave primaria da vaga, gerada pelo PostgreSQL. Use como vaga_id nas ferramentas de status e consultas. Nao forneca ao cadastrar. | Preenchimento/validacao: Automatico; imutavel. | Tipo: BIGINT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.fonte IS %L', 'Portal ou origem da vaga (ex.: LinkedIn, Gupy, Nerdin, site de carreiras). Mantida como texto, sem catalogo fechado. | Preenchimento/validacao: Grok no cadastro; obrigatorio; 1 a 100 caracteres. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.id_externo IS %L', 'Identificador da oportunidade fornecido pelo portal. A combinacao (fonte, id_externo) precisa ser unica quando o id_externo nao e nulo. | Preenchimento/validacao: Grok no cadastro; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.url IS %L', 'URL original do anuncio. Deve comecar com http:// ou https:// e nao pode conter espacos. | Preenchimento/validacao: Grok no cadastro; obrigatorio. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.url_canonica IS %L', 'Endereco normalizado, usado na deduplicacao. O servidor remove fragmento # e barras finais; o Grok deve remover parametros de rastreamento (utm_*, gclid etc.) antes de enviar. Na ausencia deste campo, e derivado de url. | Preenchimento/validacao: Grok no cadastro; opcional no JSON, obrigatoria/unica no banco. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.hash_texto IS %L', 'MD5 calculado a partir da descricao normalizada, empresa e cargo. Serve para apontar possiveis repostagens; nao e uma chave unica, nao prova que duas vagas sao a mesma. | Preenchimento/validacao: Calculado pelo banco; nao enviar. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.empresa IS %L', 'Nome da empresa contratante; precisa conter texto nao vazio. Se empresa nao estiver identificada, nao invente uma empresa real. | Preenchimento/validacao: Grok no cadastro; obrigatorio. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.cargo IS %L', 'Titulo da oportunidade, por exemplo Desenvolvedor Python Junior; texto nao vazio. | Preenchimento/validacao: Grok no cadastro; obrigatorio. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.nivel IS %L', 'Senioridade como JUNIOR, PLENO, SENIOR, TRAINEE ou ESTAGIO. O banco nao impoe enumeracao; mantenha consistencia. | Preenchimento/validacao: Grok no cadastro; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.modelo IS %L', 'Modalidade de trabalho: REMOTO, HIBRIDO, PRESENCIAL ou NAO_INFORMADO. O MCP de cadastro transforma em maiusculas e usa NAO_INFORMADO quando ausente. | Preenchimento/validacao: Grok no cadastro; opcional; enum validada. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.cidade IS %L', 'Cidade da oportunidade, quando especificada. Nao adivinhar localizacao. | Preenchimento/validacao: Grok no cadastro; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.uf IS %L', 'Sigla do estado, como SP, RJ ou MG. O MCP de cadastro converte para maiusculas; o banco valida apenas o comprimento 2, nao a existencia da UF. | Preenchimento/validacao: Grok no cadastro; opcional; exatamente 2 caracteres. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.pais IS %L', 'Pais da vaga, como Brasil ou Portugal. Se omitido, valor padrao Brasil; corrija quando vaga for internacional. | Preenchimento/validacao: Grok no cadastro; opcional; padrao Brasil. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.tipo_contrato IS %L', 'Regime ou tipo de contrato, por exemplo CLT, PJ, ESTAGIO, TEMPORARIO. Texto livre, sem CHECK fechado. | Preenchimento/validacao: Grok no cadastro; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.salario_min IS %L', 'Menor valor de remuneracao informado, na moeda do campo moeda. Numero decimal sem simbolo de moeda. A periodicidade nao possui coluna especifica: inclua na descricao/comentario da vaga quando necessario. | Preenchimento/validacao: Grok no cadastro; opcional; >= 0. | Tipo: NUMERIC(12,2).');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.salario_max IS %L', 'Maior valor de remuneracao informado. Se o anuncio nao trouxer salario, deixe ambos nulos; nao inventar valor. | Preenchimento/validacao: Grok no cadastro; opcional; >= salario_min quando ambos. | Tipo: NUMERIC(12,2).');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.moeda IS %L', 'Codigo de moeda de 3 letras maiusculas, ex.: BRL, USD ou EUR. O banco valida o formato, nao a validade na lista ISO. | Preenchimento/validacao: Grok no cadastro; opcional; padrao BRL. | Tipo: VARCHAR(3).');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.aderencia IS %L', 'Estimativa de correspondencia da vaga ao perfil/curriculo do usuario. Nao atribuir 100 sem criterios; documentar justificativa em o_que_falta ou descricao. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional; 0 a 100. | Tipo: SMALLINT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.score_prefiltro IS %L', 'Nota dos filtros objetivos (modalidade, nivel, localizacao, requisitos). Diferente de aderencia, que representa compatibilidade geral. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional; 0 a 100. | Tipo: SMALLINT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.habilidades_pedidas IS %L', 'Tecnologias e competencias exigidas ou desejadas, em texto legivel. Ex.: Python; PostgreSQL; Docker; APIs REST. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.o_que_falta IS %L', 'Lacunas identificadas entre requisitos e perfil do usuario. Nao classificar como falta algo que nao esteja no anuncio ou no perfil analisado. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.como_candidatar IS %L', 'Como aplicar: link, instrucoes do portal, email divulgado no anuncio, etapas e observacoes. Nao armazenar senhas pessoais. | Preenchimento/validacao: Grok no cadastro; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.prazo IS %L', 'Data final de inscricao, se conhecida. Caso nao divulgada, deixar nulo. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional; AAAA-MM-DD. | Tipo: DATE.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.descricao IS %L', 'Texto original ou extracao fiel da vaga. Na consulta MCP, apenas os primeiros 1500 caracteres sao retornados como resumo_descricao. JSON enviado ao cadastro tem limite total de 250000 caracteres. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.status_notificacao IS %L', 'NOVA significa nao comunicada; ENVIADA significa vaga enviada/apresentada ao usuario. Nao equivale a candidatura submetida. | Preenchimento/validacao: Automatico e MCP atualizar_status; NOVA|ENVIADA. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.status_candidatura IS %L', 'Andamento da candidatura: NAO_AVALIADA, INTERESSE, DESCARTADA, INSCRITO, EM_PROCESSO, ENTREVISTA, TESTE_TECNICO, OFERTA, REPROVADO, CONTRATADO. O Grok so pode transicionar para INSCRITO conforme regras do MCP. | Preenchimento/validacao: Automatico e MCP atualizar_status (apenas INSCRITO); outros estados manuais. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.status_disponibilidade IS %L', 'Disponibilidade do anuncio: DESCONHECIDA, ATIVA ou EXPIRADA. Independente do andamento da candidatura; as ferramentas MCP existentes nao alteram esse campo. | Preenchimento/validacao: Default DESCONHECIDA; sem atualizacao pelo MCP atual. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.data_status IS %L', 'Instante da ultima atualizacao operacional da candidatura conforme o fluxo. A funcao do Grok o define ao mudar para INSCRITO; atualizacoes manuais devem tratar este campo. | Preenchimento/validacao: Automatico ao marcar INSCRITO pelo MCP; caso contrario administracao manual. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.observacoes IS %L', 'Notas pessoais do usuario sobre a oportunidade/candidatura. A consulta MCP pode retornar o campo, mas salvar_vaga e atualizar_status_vaga nao o editam. | Preenchimento/validacao: Somente usuario/admin; Grok nao escreve. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.data_envio IS %L', 'Data/hora em que a vaga foi comunicada ao usuario pelo fluxo. Em repeticoes, mantem o primeiro instante. | Preenchimento/validacao: Automatico ao primeiro status ENVIADA. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.data_inscricao IS %L', 'Data/hora de candidatura confirmada. Nao preencher apenas porque abriu ou preencheu o formulario. | Preenchimento/validacao: Automatico quando status INSCRITO confirmado. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.comprovante_inscricao IS %L', 'Texto de comprovacao: mensagem exibida pelo portal, numero do protocolo ou referencia de confirmacao. Ate 2000 caracteres na funcao MCP; nao inclua credenciais/senhas. | Preenchimento/validacao: MCP atualizar_status quando INSCRITO confirmado. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.data_publicacao IS %L', 'Data informada pelo site como publicacao da vaga. Nao confundir com primeira_coleta; nula se desconhecida. | Preenchimento/validacao: Grok no cadastro ou revisita; opcional; AAAA-MM-DD. | Tipo: DATE.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.primeira_coleta IS %L', 'Data/hora em que o registro entrou pela primeira vez no banco. | Preenchimento/validacao: Automatico no INSERT; imutavel pelo MCP. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.ultima_verificacao IS %L', 'Data/hora da ultima reavaliacao realizada pela ferramenta salvar_vaga para vaga reencontrada. | Preenchimento/validacao: Automatico no INSERT e na revisita da mesma vaga. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas.atualizado_em IS %L', 'Ultima atualizacao de dados efetuada pelas funcoes MCP; nao e garantia de atualizacao para SQL manual que nao ajuste este campo. | Preenchimento/validacao: Automatico nos INSERTs e UPDATEs do MCP. | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.id IS %L', 'Identificador unico do evento historico. | Preenchimento/validacao: Automatico. | Tipo: BIGINT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.vaga_id IS %L', 'ID da vaga a que o evento pertence. Chave estrangeira para empregos.vagas.id; historico e apagado se a vaga for excluida (ON DELETE CASCADE). | Preenchimento/validacao: Automatico no gatilho. | Tipo: BIGINT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.tipo IS %L', 'Qual familia de status mudou. O gatilho atual nao audita status_disponibilidade. | Preenchimento/validacao: Automatico; NOTIFICACAO|CANDIDATURA. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.status_anterior IS %L', 'Valor anterior do status alterado. | Preenchimento/validacao: Automatico. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.status_novo IS %L', 'Valor novo do status alterado. | Preenchimento/validacao: Automatico. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.alterado_em IS %L', 'Data/hora do evento no historico. | Preenchimento/validacao: Automatico (NOW()). | Tipo: TIMESTAMPTZ.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.alterado_por IS %L', 'Identificador do ator. O MCP usa grok_bot; outros UPDATEs usam o contexto da conexao, salvo definicao explicita de empregos.actor. | Preenchimento/validacao: Automatico. | Tipo: TEXT.');
    EXECUTE pg_catalog.format('COMMENT ON COLUMN empregos.vagas_status_hist.observacao IS %L', 'Texto breve do motivo do status, com limite de ate 1000 caracteres para entrada do MCP. | Preenchimento/validacao: Automatico ou fornecido pelo MCP. | Tipo: TEXT.');

    -- Metadados com consulta estaticamente restrita a duas tabelas conhecidas.
    EXECUTE $function_def$
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
 'versao_documentacao', '1.1',
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
   pg_catalog.jsonb_build_object('nome','atualizar_status_vaga','funcao','empregos.mcp_atualizar_status(jsonb)','status_permitidos', pg_catalog.jsonb_build_array('NOVA','ENVIADA','INSCRITO'),'regra','INSCRITO exige confirmacao=true, comprovante_inscricao e confirmacao real do portal. Nao sobrescrever status pessoais.'),
   pg_catalog.jsonb_build_object('nome','descrever_banco','funcao','empregos.mcp_descrever_schema()','regra','Somente leitura de metadados das tabelas empregos.vagas e empregos.vagas_status_hist.')
 )
);
$query$;
$function_def$;

    EXECUTE 'REVOKE ALL ON FUNCTION empregos.mcp_descrever_schema() FROM PUBLIC';
    EXECUTE 'GRANT EXECUTE ON FUNCTION empregos.mcp_descrever_schema() TO gaq_jobs_grok';
    EXECUTE pg_catalog.format('COMMENT ON FUNCTION empregos.mcp_descrever_schema() IS %L', 'Ferramenta MCP de leitura de metadados: retorna nomes, tipos, regras documentadas e comentarios das tabelas empregos.vagas e empregos.vagas_status_hist.');
END;
$gaq_doc_install$;

-- Apos executar no WhoDB, em outra consulta, valide:
-- SELECT empregos.mcp_descrever_schema();
-- No n8n crie um 4o Postgres Tool descrever_banco, query:
-- SELECT empregos.mcp_descrever_schema() AS resultado;
-- Nao coloque esse SELECT junto do DO na mesma execucao WhoDB.