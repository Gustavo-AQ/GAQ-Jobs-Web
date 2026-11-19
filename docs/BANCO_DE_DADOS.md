# Banco de dados — GAQ Jobs Web

> Documentação técnica da estrutura versionada em `db/`, conferida nos scripts da branch `main` em novembro de 2026. **A definição SQL e as restrições efetivamente aplicadas no PostgreSQL prevalecem sobre este texto.**

## 1. Visão geral

- SGBD: **PostgreSQL 18**.
- Database: **`gaq`**; schema: **`empregos`**.
- O database pode coexistir com outras aplicações, pois os objetos deste projeto ficam no schema `empregos`.
- O site React não acessa SQL diretamente: usa a API FastAPI.
- O n8n/MCP consulta e atualiza vagas por funções PostgreSQL específicas, em vez de receber permissões irrestritas sobre as tabelas.

**Objetos de dados:** `empregos.vagas`, `empregos.vagas_status_hist`, `empregos.web_usuarios`, `empregos.web_sessoes` e `empregos.web_login_tentativas`.

**Objeto de documentação:** [Diagrama entidade-relacionamento](DIAGRAMA_ER.md).

## 2. Instalações e responsabilidade de cada Compose

| Arquivo | Database `gaq` | Schema/tabelas | Web/API | Uso |
|---|---|---|---|---|
| `compose.yaml` | Deve existir | Devem existir | Sim | Produção da Oracle, reaproveita o banco atual |
| `compose.managed.yaml` | Deve existir | Verifica e aplica migrações conhecidas | Sim | Nova instalação usando PostgreSQL existente |
| `compose.standalone.yaml` | Cria automaticamente | Verifica e aplica migrações conhecidas | Sim | Instalação independente com banco persistente |
| `compose.db-bootstrap.yml` | Deve existir | Cria/atualiza via SQL | Não | Bootstrap manual em PostgreSQL existente |
| `compose.db-local.yml` | Cria automaticamente | Cria na primeira inicialização do volume | Não | Laboratório isolado, não é o deploy de produção |

A criação do database `gaq` no modo laboratório vem de `POSTGRES_DB=gaq` da imagem oficial PostgreSQL. **Nenhum dos scripts `db/*.sql` contém `CREATE DATABASE`.**

Ordem de execução completa:

1. `db/000_jobs_whodb.sql` — verifica database `gaq`, cria schema `empregos`, tabelas principais, índices, trigger de auditoria, role do Grok e funções MCP de cadastro/consulta/status iniciais.
2. `db/010_dictionary_whodb.sql` — adiciona comentários sobre tabelas/colunas e a função `mcp_descrever_schema`.
3. `db/020_status_v2_whodb.sql` — amplia auditoria e regras de atualização; **substitui** a implementação inicial da função `mcp_atualizar_status`.
4. `db/001_auth_whodb.sql` — cria tabelas de autenticação, role da aplicação web e privilégios específicos.

Em um banco já utilizado com vagas, **não** execute novamente a cadeia completa de maneira indiscriminada; faça backup e avalie cada migração. Os scripts usam `IF NOT EXISTS` em várias tabelas, mas também recriam funções e triggers. Para instalar somente autenticação web numa instância com as tabelas de vagas corretas, execute apenas `001_auth_whodb.sql`.

Comandos e instruções de rede, credenciais e Coolify: [INSTALACAO.md](INSTALACAO.md).

**Novos Compose condicionais:** consulte [INSTALACAO_CONDICIONAL.md](INSTALACAO_CONDICIONAL.md). Eles criam, além das cinco tabelas de dados da aplicação, uma tabela técnica `empregos.schema_migrations` que registra versão, SHA-256, data e origem da migração; não se trata de uma tabela de negócio.

## 3. Tabela `empregos.vagas`

Registro central da oportunidade; chave primária `id BIGINT GENERATED ALWAYS AS IDENTITY`.

### Identificação, origem e deduplicação

| Coluna | Tipo | Finalidade |
|---|---|---|
| `id` | BIGINT | Identificador gerado automaticamente (PK) |
| `fonte` | TEXT, obrigatório | Origem: LinkedIn, Gupy, Nerdin etc.; 1–100 caracteres úteis |
| `id_externo` | TEXT | Identificador da vaga no portal |
| `url` | TEXT, obrigatório | URL original HTTP(S) |
| `url_canonica` | TEXT, obrigatório e UNIQUE | URL normalizada para evitar vagas duplicadas |
| `hash_texto` | TEXT | MD5 indicativo de possíveis republicações; não é chave única |
| `empresa` | TEXT, obrigatório | Empresa anunciante |
| `cargo` | TEXT, obrigatório | Título da vaga |

Regras: `url_canonica` é única. Existe índice único parcial em `(fonte,id_externo)` quando `id_externo` não é nulo. A função `mcp_salvar_vaga` procura primeiro uma vaga já registrada pela URL canônica ou identificador externo; a nova coleta não deve apagar dados pessoais/status existentes. O banco remove fragmentos e barras finais da URL canônica, mas o agente precisa remover parâmetros de rastreamento quando aplicável.

### Classificação, requisitos e remuneração

| Coluna | Tipo | Regra |
|---|---|---|
| `nivel` | TEXT | Senioridade ou nível informado |
| `modelo` | TEXT | `REMOTO`, `HIBRIDO`, `PRESENCIAL`, `NAO_INFORMADO` ou NULL |
| `cidade` | TEXT | Localidade, se conhecida |
| `uf` | TEXT | Se presente, exatamente dois caracteres |
| `pais` | TEXT | Padrão `Brasil` |
| `tipo_contrato` | TEXT | CLT, PJ, ESTAGIO etc.; texto livre |
| `salario_min` | NUMERIC(12,2) | Valor ≥ 0, se conhecido |
| `salario_max` | NUMERIC(12,2) | Valor ≥ 0 e ≥ `salario_min`, quando ambos informados |
| `moeda` | VARCHAR(3) | Três letras maiúsculas; padrão `BRL` |
| `aderencia` | SMALLINT | 0–100, pode ser NULL |
| `score_prefiltro` | SMALLINT | 0–100, pode ser NULL; diferente de aderência |
| `habilidades_pedidas` | TEXT | Requisitos e tecnologias |
| `o_que_falta` | TEXT | Lacunas da análise de compatibilidade |
| `como_candidatar` | TEXT | Instruções para candidatura |
| `prazo` | DATE | Prazo de inscrição, se divulgado |
| `descricao` | TEXT | Descrição da vaga |

O schema não possui coluna para a periodicidade do salário. Não assuma que valores sejam mensais sem essa informação na descrição.

### Status, observações e datas

| Coluna | Tipo | Regra |
|---|---|---|
| `status_notificacao` | TEXT, obrigatório | `NOVA`/`ENVIADA`; padrão `NOVA` |
| `status_candidatura` | TEXT, obrigatório | Ver seção 5; padrão `NAO_AVALIADA` |
| `status_disponibilidade` | TEXT, obrigatório | `DESCONHECIDA`/`ATIVA`/`EXPIRADA`; padrão `DESCONHECIDA` |
| `data_status` | TIMESTAMPTZ | Atualização operacional de candidatura |
| `observacoes` | TEXT | Notas pessoais editáveis pelo painel; não alteradas pela ferramenta de cadastro MCP |
| `data_envio` | TIMESTAMPTZ | Primeira notificação informada |
| `data_inscricao` | TIMESTAMPTZ | Data de inscrição registrada |
| `comprovante_inscricao` | TEXT | Comprovante fornecido ao atualizar inscrição via MCP |
| `data_publicacao` | DATE | Data divulgada no anúncio |
| `primeira_coleta` | TIMESTAMPTZ | Primeira coleta; padrão `now()` |
| `ultima_verificacao` | TIMESTAMPTZ | Última verificação/coleta |
| `atualizado_em` | TIMESTAMPTZ | Última atualização técnica |

Datas de coleta e publicação são conceitos diferentes: o filtro do painel utiliza `primeira_coleta`, convertida para `America/Sao_Paulo`.

## 4. Histórico e autenticação

### `empregos.vagas_status_hist`

| Campo | Tipo | Uso |
|---|---|---|
| `id` | BIGINT IDENTITY, PK | Evento |
| `vaga_id` | BIGINT, FK | Referência a `vagas.id` com `ON DELETE CASCADE` |
| `tipo` | TEXT | `NOTIFICACAO`, `CANDIDATURA` ou `DISPONIBILIDADE` (após v2) |
| `status_anterior` | TEXT | Valor antes da alteração |
| `status_novo` | TEXT | Novo valor |
| `alterado_em` | TIMESTAMPTZ | Horário da mudança |
| `alterado_por` | TEXT | Identificação do ator |
| `observacao` | TEXT | Justificativa/evidência registrada |

O trigger `trg_empregos_auditar_status`, associado à função `fn_auditar_status()`, cria o histórico em alterações de status, quando o valor muda. Usa as configurações de transação `empregos.actor` e `empregos.obs` para atribuição da ação. Alterar somente `observacoes` não gera um evento desse histórico de status.

### `empregos.web_usuarios`

- `id` BIGINT IDENTITY (PK), `email` TEXT obrigatório com índice único sobre `lower(email)`.
- `senha_hash` TEXT obrigatório (a API grava hash **Argon2id**, nunca senha em texto puro).
- `papel` TEXT: `ADMIN` ou `LEITURA`; padrão `LEITURA`.
- `ativo` BOOLEAN, padrão verdadeiro.
- `criado_em`, `atualizado_em` e `ultimo_login_em` TIMESTAMPTZ.

### `empregos.web_sessoes`

- `id` BIGINT IDENTITY (PK).
- `usuario_id` BIGINT, FK para `web_usuarios.id` com `ON DELETE CASCADE`.
- `token_hash` CHAR(64), único; token puro fica somente no cookie de sessão.
- `criado_em`, `expira_em` e `revogada_em` TIMESTAMPTZ.
- Índice para consultas por `usuario_id` e expiração.

### `empregos.web_login_tentativas`

- `id` BIGINT IDENTITY (PK), `email` TEXT obrigatório e `criado_em` TIMESTAMPTZ.
- Registra tentativas de autenticação inválidas para limitar novas tentativas (8 em 15 minutos por e-mail, na implementação atual).
- **Não tem chave estrangeira** para `web_usuarios`: o e-mail pode não pertencer a uma conta existente.
- Os scripts não criam política periódica automática de exclusão dessas tentativas; trate retenção/limpeza como melhoria operacional futura.

## 5. Regras das três famílias de status (migração v2)

| Família | Valores |
|---|---|
| `NOTIFICACAO` | `NOVA`, `ENVIADA` |
| `CANDIDATURA` | `NAO_AVALIADA`, `INTERESSE`, `DESCARTADA`, `INSCRITO`, `EM_PROCESSO`, `ENTREVISTA`, `TESTE_TECNICO`, `OFERTA`, `REPROVADO`, `CONTRATADO` |
| `DISPONIBILIDADE` | `DESCONHECIDA`, `ATIVA`, `EXPIRADA` |

**As famílias são independentes:** uma vaga pode ter candidatura `EM_PROCESSO` e anúncio `EXPIRADA`, sem contradição.

Regras implementadas por `mcp_atualizar_status(jsonb)` na v2:

- Atualização de `NOTIFICACAO` de `NOVA` para `ENVIADA` pode ser registrada automaticamente **após a vaga ter sido informada ao usuário**.
- Mudanças protegidas exigem origem `PEDIDO_USUARIO` ou `EMAIL` e evidência com pelo menos 12 caracteres; mudanças de disponibilidade por `VERIFICACAO_SITE` exigem evidência da página consultada.
- Origem `EMAIL` exige `gmail_message_id`, `email_remetente` e `email_assunto`; não permite decidir `INTERESSE`, `DESCARTADA` ou `NAO_AVALIADA`, que dependem de pedido do usuário.
- A função impede reutilizar o mesmo Gmail ID para justificar outra vaga ou outro status.
- Para marcar `INSCRITO` quando o próprio bot realizou a inscrição (`bot_realizou_inscricao=true`), exige `comprovante_inscricao`. A data inicial de inscrição é preservada em chamadas posteriores.
- Uma atualização para o mesmo status retorna `SEM_ALTERACAO`, sem evento duplicado de alteração.

**Limitação de confiança importante:** a função PostgreSQL valida os campos de evidência fornecidos pelo agente, mas **não autentica o conteúdo do Gmail**. A confirmação independente depende de um fluxo que consulte o provedor de e-mail.

O **painel web** tem outra autorização: um usuário autenticado `ADMIN` pode atualizar `status_candidatura` e `observacoes` via FastAPI; `LEITURA` não pode. A API não exige os mesmos campos de evidência do MCP.

## 6. Funções MCP

| Função | Operação | Observação |
|---|---|---|
| `empregos.mcp_salvar_vaga(jsonb)` | Insere ou reencontra vagas | Obrigatórios: `fonte`, `url`, `empresa`, `cargo`; JSON até 250.000 caracteres |
| `empregos.mcp_consultar_vagas(jsonb)` | Consulta com filtros | Limite entre 1 e 50 registros por chamada, deslocamento até 10.000 |
| `empregos.mcp_atualizar_status(jsonb)` | Atualiza um status | Versão vigente após executar `020_status_v2_whodb.sql` |
| `empregos.mcp_descrever_schema()` | Descreve metadados | Consulta de leitura de estrutura e comentários das tabelas de vagas |

O agente usa essas quatro funções por ferramentas PostgreSQL no workflow n8n. A função `mcp_descrever_schema()` expõe apenas as tabelas de **vagas e histórico**, não as tabelas privadas da autenticação.

**Nota de manutenção:** os comentários de `010_dictionary_whodb.sql` e parte dos metadados publicados por `mcp_descrever_schema()` descrevem o comportamento inicial. A migração `020_status_v2_whodb.sql` substitui a implementação de status; em caso de divergência, consulte seu código e as restrições reais.

## 7. Usuários e privilégios

- `gaq_jobs_grok`: role de login com `USAGE` no schema e `EXECUTE` nas funções MCP. O fluxo n8n não deve conectar como `postgres`.
- `gaq_jobs_web`: role de login da API; `SELECT` nas tabelas de vagas e histórico; `UPDATE` somente em colunas específicas da candidatura e observações; DML nas três tabelas de autenticação.
- `postgres` ou administrador equivalente: usa privilégios elevados **apenas** para migrações e gestão de roles; não deve ser credencial da aplicação.
- Usuários da aplicação (`ADMIN` e `LEITURA`) não são roles PostgreSQL individuais, mas registros em `web_usuarios`.

No bootstrap, as roles são criadas **sem senhas explícitas**. Defina senhas fortes e diferentes fora do Git:

```sql
ALTER ROLE gaq_jobs_grok WITH PASSWORD 'SENHA_GROK';
ALTER ROLE gaq_jobs_web WITH PASSWORD 'SENHA_WEB';
```

Depois crie a primeira conta ADMIN pelo terminal interativo do container da API:

```bash
python -m app.create_admin --email endereco@exemplo.com
```

## 8. Índices e integridade

- `vagas`: PK `id`, UNIQUE `url_canonica`, UNIQUE parcial `(fonte,id_externo)`, índices de coleta, status, aderência e hash não nulo.
- `vagas_status_hist`: índice `(vaga_id,alterado_em DESC)` e FK com exclusão em cascata.
- `web_usuarios`: unicidade case-insensitive de e-mail (`lower(email)`).
- `web_sessoes`: unicidade de `token_hash` e índice de usuário/expiração.
- `web_login_tentativas`: índice por e-mail e data.

Exclusão em cascata significa que apagar uma vaga remove seu histórico, e apagar um usuário web remove suas sessões. **Não exclua dados para “limpar testes” sem avaliar essas dependências.**

## 9. Consultas úteis (somente leitura)

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'empregos'
ORDER BY table_name;

SELECT id, empresa, cargo, status_candidatura
FROM empregos.vagas
ORDER BY primeira_coleta DESC
LIMIT 10;

SELECT vaga_id, tipo, status_anterior, status_novo, alterado_em
FROM empregos.vagas_status_hist
ORDER BY alterado_em DESC
LIMIT 20;

SELECT empregos.mcp_descrever_schema();
```

Nunca coloque senhas, `DATABASE_URL`, tokens MCP ou hashes de sessão nos arquivos versionados.

## 10. Referências internas

- [Instalação e Compose](INSTALACAO.md)
- [Diagrama ER](DIAGRAMA_ER.md)
- [Manual do painel](USO.md)
- [Integração n8n/MCP](N8N_MCP.md)
- [SQL de criação](../db/000_jobs_whodb.sql)
- [Migração v2](../db/020_status_v2_whodb.sql)
- [SQL de autenticação](../db/001_auth_whodb.sql)
