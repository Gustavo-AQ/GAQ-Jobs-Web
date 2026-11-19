# Migrador de schema GAQ Jobs

O `ensure.py` é usado exclusivamente nos novos Compose `compose.managed.yaml` e `compose.standalone.yaml`. Não é utilizado no Compose existente da Oracle.

- Inicializa um schema completamente vazio com os arquivos SQL de `db/`.
- Em um banco com vagas, aplica somente migrações reconhecidas (dicionário, v2, autenticação).
- Audita tipos de colunas, índices, FKs, PKs, principais privilégios e funções.
- Para em caso de divergência não conhecida.
- Não deleta registros nem modifica senhas de roles existentes.
- Cria tabela de controle `empregos.schema_migrations` (não contém vagas e não integra o diagrama de entidades de negócio).

Exige uma conexão administrativa ao database `gaq`. O container utiliza `psycopg`. As senhas entram como variáveis privadas, não no código.

**Não use o migrador como rotina periódica de reconciliação arbitrária de schema.** Todas as modificações futuras devem ser migradas por arquivos versionados, com revisão e backup.

Veja instruções e variáveis em [docs/INSTALACAO_CONDICIONAL.md](../docs/INSTALACAO_CONDICIONAL.md).
