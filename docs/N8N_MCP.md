# Workflow GAQ Jobs — n8n MCP

Arquivo: n8n/GAQ_Jobs_MCP_importar.json.

Esse arquivo é um workflow independente. O caminho do webhook no n8n é `gaq-jobs-web-v1` (é o path do trigger, não a branch Git; o deploy do painel usa `main`). Não substitui o fluxo legado "Pipeline de Análise de Vagas com IA" (WhatsApp e Google Sheets) nem um bot antigo de Whisper/Telegram: esses fluxos são separados deste painel.

## Quatro ferramentas

1. salvar_vaga: SELECT empregos.mcp_salvar_vaga($1::jsonb) AS resultado;
2. consultar_vagas: SELECT empregos.mcp_consultar_vagas($1::jsonb) AS resultado;
3. atualizar_status_vaga: SELECT empregos.mcp_atualizar_status($1::jsonb) AS resultado;
4. descrever_banco: SELECT empregos.mcp_descrever_schema() AS resultado;

Todas utilizam o PostgreSQL gaq por meio do usuário gaq_jobs_grok.

## Como importar

1. Importe o JSON no n8n via Import from File.
2. Nos quatro nós PostgreSQL, atribua a credencial Postgres ORACLE com o usuário gaq_jobs_grok.
3. No MCP Server Trigger, configure Bearer Auth com um token forte.
4. Publique o workflow e copie a Production URL apresentada pelo n8n.
5. Para o Grok, configure o conector HTTPS remoto e o cabeçalho HTTP Authorization: Bearer SEU_TOKEN.
6. Verifique que o endpoint é do tipo Streamable HTTP, sem /sse.
7. Teste primeiro consultar_vagas e descrever_banco, sem modificar dados.

O workflow usa o MCP Server Trigger typeVersion 2, necessário para Streamable HTTP. Seu n8n precisa suportar essa versão.

## Controle de alterações

A função de status v2 exige justificativa para mudanças sensíveis com origem `PEDIDO_USUARIO` ou `EMAIL`. O PostgreSQL não verifica sozinho a mensagem real no Gmail. Para segurança independente, é necessário um fluxo de validação com credenciais Gmail próprias no n8n.

`atualizar_status_vaga` chama `empregos.mcp_atualizar_status(jsonb)`. Além de mudar status, ela trata o comprovante assim:

- Candidatura já `INSCRITO`, com `comprovante_inscricao` vazio (`NULL` ou só espaços): envie `comprovante_inscricao`, origem `PEDIDO_USUARIO` ou `EMAIL` e evidência (mínimo de 12 caracteres; no `EMAIL`, também `gmail_message_id`, `email_remetente` e `email_assunto`). O status permanece `INSCRITO` e a ação volta `COMPROVANTE_REGISTRADO`. Esse `EMAIL` também consome a mensagem: o mesmo `gmail_message_id` não justifica outra vaga nem outro status. O registro fica fora do histórico de status do painel.
- Comprovante já preenchido: o agente não pode trocá-lo. A função responde `ok=false` e ação `COMPROVANTE_JA_EXISTENTE`, sem gravar. Não há parâmetro de bypass.
- A coluna `observacoes` não é alterada por essa ferramenta.

A correção de um comprovante errado é do usuário, direto no banco (WhoDB ou SQL administrativo). O painel web não tem campo para esse texto, e a role da API não tem `UPDATE` na coluna. Reimportar este workflow só atualiza a descrição mostrada ao modelo; a regra passa a valer quando `db/030_comprovante_inscrito_whodb.sql` é aplicada no database `gaq`. O comando e o script de conferência estão em [BANCO_DE_DADOS.md](BANCO_DE_DADOS.md).

Não inclua senhas nem credenciais ao exportar os workflows.

Documentação n8n: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/
