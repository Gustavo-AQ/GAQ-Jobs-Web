# Instalação condicional do schema — novos Compose

> **Os novos arquivos são opções de implantação. Não substituem automaticamente `compose.yaml`, atualmente utilizado em `jobs.gaqtech.dev`.** Não habilite estes Compose no Coolify da Oracle sem testar os parâmetros e os backups.

## 1. Qual Compose utilizar?

| Arquivo | Banco de dados | Site/API | Migrador | Uso recomendado |
|---|---|---|---|---|
| `compose.yaml` | PostgreSQL externo, já preparado | Sim | Não | Instalação existente na Oracle, sem alterações |
| `compose.managed.yaml` | PostgreSQL externo, database `gaq` existente | Sim | Sim | Nova instalação com banco gerenciado externamente |
| `compose.standalone.yaml` | Cria PostgreSQL 18 e database `gaq` | Sim | Sim | Implantação totalmente independente, em volume persistente |
| `compose.db-bootstrap.yml` | DB externo já existente | Não | Executa scripts escolhidos manualmente | Suporte/recuperação |
| `compose.db-local.yml` | DB isolado de laboratório | Não | Scripts na primeira inicialização do volume | Desenvolvimento |

Em todos os cenários, a interface utiliza React/Nginx e a API utiliza FastAPI. O Compose não importa automaticamente o workflow n8n, não provisiona o primeiro usuário administrador web e não executa backup.

## 2. O que faz o migrador (`migrator/ensure.py`)?

Ao ser executado, o container `migrate`:

1. Conecta ao database **`gaq`** com credencial de migração administrativa (isolada da credencial da API).
2. Obtém um **advisory lock** transacional PostgreSQL para impedir execução simultânea de dois inicializadores compatíveis.
3. Verifica quais objetos de `empregos` já existem.
4. Se o núcleo está vazio, executa **em ordem**:
   - `db/000_jobs_whodb.sql` — schema, vagas, histórico, funções e índices;
   - `db/010_dictionary_whodb.sql` — comentários e função de documentação;
   - `db/020_status_v2_whodb.sql` — auditoria e atualização de status v2;
   - `db/030_comprovante_inscrito_whodb.sql` — comprovante vazio em candidatura já INSCRITO, e recusa quando o texto já existe;
   - `db/001_auth_whodb.sql` — login e sessões do site.
5. Se o núcleo já está instalado, verifica o formato das colunas das tabelas centrais e aplica **apenas migrações conhecidas necessárias**, como adição do dicionário, status v2, comprovante em vaga já INSCRITO ou tabelas web ausentes.
6. Confere as cinco tabelas e seus tipos de colunas, chaves primárias e estrangeiras, índices, funções, trigger v2 e os papéis/permissões principais. Objetos adicionais não são apagados.
7. Registra o resultado em `empregos.schema_migrations`: versão, SHA-256 do arquivo e origem `applied` ou `adopted`.
8. Termina com código de saída 0. Somente então a API inicia, e depois a interface.

**Se detectar divergência não coberta por migração conhecida, interrompe a inicialização.** Não usa `DROP TABLE`, `DROP COLUMN`, `TRUNCATE` ou recriação automática da base. A validação não é uma prova formal de igualdade de todo o catálogo SQL: compara os elementos e regras explicitamente codificados no verificador. Alterações futuras deverão ser versionadas como migrações novas.

O processo é **transacional**: se uma migração ou validação falhar, as alterações de banco da execução são revertidas. Isso não substitui backups.

Em **`GAQ_SCHEMA_MODE=check`**, o migrador apenas verifica, sem alterar schema, roles, senhas nem ledger. Útil para diagnóstico em ambientes existentes. O padrão é `apply`.

**Atenção:** o script `000_jobs_whodb.sql` contém recriação de funções/triggers e `REVOKE` amplos, por isso só é executado automaticamente quando a estrutura principal de vagas não está presente. Ao encontrar um banco parcialmente criado/incompatível, o verificador bloqueia para análise manual.

## 3. Opção A — PostgreSQL existente: `compose.managed.yaml`

Crie uma **nova** aplicação Docker Compose no Coolify, selecionando `/compose.managed.yaml`. Use um PostgreSQL com database `gaq` existente (não use `coolify-db`).

Configure variáveis privadas:

| Nome | Exemplo/observação |
|---|---|
| `GAQ_DB_HOST` | Hostname interno que alcança o PostgreSQL pela rede Docker `coolify` |
| `GAQ_DB_PORT` | `5432` |
| `GAQ_DB_NAME` | `gaq` (único suportado) |
| `GAQ_DB_ADMIN_USER` | Role administrativa para executar DDL, GRANT e CREATE ROLE |
| `GAQ_DB_ADMIN_PASSWORD` | Senha dessa role; somente no container temporário `migrate` |
| `DATABASE_URL` | `postgresql+psycopg://gaq_jobs_web:SENHA@HOST:5432/gaq` |
| `APP_ORIGIN` | `https://dominio.exemplo.com` |
| `SESSION_SECRET` | Gere com `openssl rand -hex 32` |
| `GAQ_SCHEMA_MODE` | `apply`, ou `check` para auditoria sem mudanças |
| `GAQ_DB_WEB_INITIAL_PASSWORD` | Obrigatória apenas se a role `gaq_jobs_web` ainda não existir |
| `GAQ_DB_GROK_INITIAL_PASSWORD` | Obrigatória apenas se a role `gaq_jobs_grok` ainda não existir |
| `SESSION_HOURS` | `72`, opcional |

**Senhas das roles já existentes são preservadas.** A senha inicial não é alterada se a role já existia.

O frontend deve ter apenas seu domínio HTTPS vinculado pelo proxy Coolify, na porta interna 80. **Não exponha** PostgreSQL/8000. Configure o DNS e depois crie manualmente a primeira conta ADMIN pela CLI da API:

```bash
python -m app.create_admin --email endereco@exemplo.com
```

O serviço `migrate` termina após a verificação; não deve permanecer em execução como daemon.

**Atenção a reimplantações:** `depends_on: service_completed_successfully` garante a ordem quando a tarefa é executada, mas **não obriga o Docker Compose a recriar um container `migrate` já concluído**. Para auditar/aplicar mudanças em uma implantação existente, execute explicitamente a tarefa novamente ou recrie esse serviço como parte do processo de atualização. Por exemplo, no host com as mesmas variáveis privadas do projeto, `docker compose -f compose.managed.yaml run --rm migrate`. Não presuma que todo Redeploy de frontend executou uma nova verificação do banco.

## 4. Opção B — Instalação independente: `compose.standalone.yaml`

Crie uma nova aplicação Docker Compose no Coolify com o arquivo `/compose.standalone.yaml`. Ele cria, em rede Docker privada:

- `db`: PostgreSQL 18 + database inicial `gaq` + volume persistente `gaq_jobs_pgdata`.
- `migrate`: verificação/inicialização das tabelas e privilégios no banco.
- `api`: FastAPI, aguardando o sucesso de `migrate`.
- `web`: Nginx/React, aguardando a saúde da API.

Variáveis obrigatórias:

| Nome | Utilização |
|---|---|
| `GAQ_DB_ADMIN_PASSWORD` | Senha inicial do superusuário Postgres do container |
| `GAQ_DB_WEB_PASSWORD` | Senha da role web; **apenas letras e números** para evitar codificação de URL |
| `GAQ_DB_GROK_PASSWORD` | Senha inicial da role MCP |
| `APP_ORIGIN` | Domínio público HTTPS |
| `SESSION_SECRET` | Segredo aleatório, mínimo 32 caracteres |

Variáveis opcionais: `SESSION_HOURS=72` e `GAQ_SCHEMA_MODE=apply`.

O PostgreSQL **não tem `ports:` públicos**, e os dados permanecem no volume `gaq_jobs_pgdata` mesmo com recriação do container. **Não use `docker compose down -v`** nem exclua o volume ao fazer manutenção.

Após a instalação, crie o ADMIN pelo container da API e configure o workflow n8n (se desejar usar o Grok) manualmente com a role `gaq_jobs_grok`. No standalone, o banco está em uma rede isolada; um n8n externo não acessa `db` automaticamente. Para conectá-lo, será preciso planejar uma rede compartilhada privada ou outra conexão protegida; não abra o banco à Internet.

A senha `GAQ_DB_ADMIN_PASSWORD` do ambiente é usada na criação inicial do PostgreSQL. Alterá-la posteriormente no Coolify **não altera por si só** a senha armazenada dentro de um volume PostgreSQL já inicializado.

## 5. Cuidados antes de usar no seu servidor atual

- Seu `compose.yaml` atual **continua intacto**. O uso dos novos arquivos é opcional.
- Não crie uma segunda aplicação standalone apontando para o mesmo domínio `jobs.gaqtech.dev` sem planejamento do proxy.
- Faça backup do `gaq` antes de migrar um ambiente com vagas reais.
- Teste `GAQ_SCHEMA_MODE=check` com as credenciais de migração num ambiente de ensaio antes de trocar a aplicação original.
- Se o ambiente já existe e a estrutura apresenta diferenças, **não tente corrigir manualmente removendo colunas ou recriando tabelas em produção**. Crie uma migração explícita, com backup e plano de rollback.
- A verificação considera objeto faltante/regras conhecidas, mas não corrige alterações arbitrárias nem executa upgrades de major version do PostgreSQL.

## 6. Diagnóstico

- `migrate` termina com erro: leia logs desse container. `api` não deve iniciar.
- "Role ... ainda não existia": defina as variáveis de senha inicial.
- "Tipo divergente": schema incompatível; não alterar dados até revisar migração.
- "Arquivo versionado alterado": crie uma migração nova, não sobrescreva SQL antigo.
- `api` unhealthy: verifique URL da role `gaq_jobs_web`, credenciais, rede Docker e endpoint `/healthz`.
- `web` com 502: verifique se `api` está saudável.
- Altere login/segredo sempre sem colocá-los no Git ou em logs.

## 7. Referências

- [Estrutura do banco e regras](BANCO_DE_DADOS.md)
- [Diagrama ER](DIAGRAMA_ER.md)
- [Instalação original](INSTALACAO.md)
- [Workflow MCP](N8N_MCP.md)
- [Compose de produção original](../compose.yaml)
- [Compose com banco externo](../compose.managed.yaml)
- [Compose standalone](../compose.standalone.yaml)
- [Migrador](../migrator/ensure.py)

Documentação técnica: [Docker Compose service_completed_successfully](https://docs.docker.com/compose/how-tos/startup-order/) · [Imagem PostgreSQL](https://hub.docker.com/_/postgres) · [PostgreSQL DDL transacional](https://www.postgresql.org/docs/current/sql-begin.html)
