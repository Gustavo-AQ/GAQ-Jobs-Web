# Diagrama entidade-relacionamento (ER) — GAQ Jobs

Modelo lógico das **cinco tabelas reais** do schema `empregos`, conforme os instaladores SQL atuais.

## Diagrama

```mermaid
erDiagram
    VAGAS ||--o{ VAGAS_STATUS_HIST : "id para vaga_id"
    WEB_USUARIOS ||--o{ WEB_SESSOES : "id para usuario_id"

    VAGAS {
        bigint id PK
        text fonte
        text id_externo
        text url
        text url_canonica UK
        text hash_texto
        text empresa
        text cargo
        text nivel
        text modelo
        text cidade
        text uf
        text pais
        text tipo_contrato
        numeric salario_min
        numeric salario_max
        varchar moeda
        smallint aderencia
        smallint score_prefiltro
        text habilidades_pedidas
        text o_que_falta
        text como_candidatar
        date prazo
        text descricao
        text status_notificacao
        text status_candidatura
        text status_disponibilidade
        timestamptz data_status
        text observacoes
        timestamptz data_envio
        timestamptz data_inscricao
        text comprovante_inscricao
        date data_publicacao
        timestamptz primeira_coleta
        timestamptz ultima_verificacao
        timestamptz atualizado_em
    }
    VAGAS_STATUS_HIST {
        bigint id PK
        bigint vaga_id FK
        text tipo
        text status_anterior
        text status_novo
        timestamptz alterado_em
        text alterado_por
        text observacao
    }
    WEB_USUARIOS {
        bigint id PK
        text email UK
        text senha_hash
        text papel
        boolean ativo
        timestamptz criado_em
        timestamptz atualizado_em
        timestamptz ultimo_login_em
    }
    WEB_SESSOES {
        bigint id PK
        bigint usuario_id FK
        char token_hash UK
        timestamptz criado_em
        timestamptz expira_em
        timestamptz revogada_em
    }
    WEB_LOGIN_TENTATIVAS {
        bigint id PK
        text email
        timestamptz criado_em
    }
```

**Como interpretar:**

- `VAGAS (1) → VAGAS_STATUS_HIST (0..N)`: uma vaga tem zero ou muitos eventos de status. FK `vaga_id` com `ON DELETE CASCADE`.
- `WEB_USUARIOS (1) → WEB_SESSOES (0..N)`: uma conta tem zero ou muitas sessões. FK `usuario_id` com `ON DELETE CASCADE`.
- `WEB_LOGIN_TENTATIVAS` não possui FK para `WEB_USUARIOS`. O campo `email` é apenas texto para registrar tentativas, inclusive de contas inexistentes.
- Também **não há FK** entre contas web e vagas ou histórico. O autor da mudança fica como texto em `vagas_status_hist.alterado_por`.
- `UK` é a unicidade. O `email` web é único via índice `lower(email)`; `url_canonica` tem UNIQUE. Existe ainda um índice único **parcial** em `vagas(fonte,id_externo)` quando `id_externo` não é nulo; índices parciais não são expressos pelo diagrama ER.

## Diagrama funcional (sem implicar chaves estrangeiras)

```mermaid
flowchart LR
    bot["Grok / agente"] --> mcp["n8n MCP"]
    mcp --> fun["Funções empregos.mcp_*"]
    fun --> vagas[("empregos.vagas")]
    vagas -->|trigger após UPDATE de status| hist[("empregos.vagas_status_hist")]

    usuario["Usuário no navegador"] --> web["React/Nginx"]
    web --> api["FastAPI"]
    api --> vagas
    api --> auth[("empregos.web_usuarios")]
    api --> sessoes[("empregos.web_sessoes")]
    api --> tentativas[("empregos.web_login_tentativas")]
```

## Restrições e ressalvas

Os diagramas não substituem `CHECK`, `UNIQUE`, `NOT NULL`, triggers nem permissões. O SQL define:

- Três famílias independentes de status: `NOTIFICACAO`, `CANDIDATURA`, `DISPONIBILIDADE`.
- Auditoria por trigger depois da migração `020_status_v2_whodb.sql`.
- Controle de login via `web_usuarios`, sessão com hash em `web_sessoes` e proteção contra repetição de tentativas em `web_login_tentativas`.
- Campos financeiros e de aderência sujeitos a validações; diferentes colunas podem ser opcionais.

Para os tipos, regras, funções e limitações completas, consulte [BANCO_DE_DADOS.md](BANCO_DE_DADOS.md). Os scripts SQL [000](../db/000_jobs_whodb.sql), [020](../db/020_status_v2_whodb.sql), [030](../db/030_comprovante_inscrito_whodb.sql) e [001](../db/001_auth_whodb.sql) são as fontes de implementação.

> O Mermaid é renderizado diretamente pelo GitHub; não é necessário manter imagens estáticas.
