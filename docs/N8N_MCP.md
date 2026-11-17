# Workflow GAQ Jobs — n8n MCP

Arquivo: n8n/GAQ_Jobs_MCP_importar.json.

Esse arquivo é um workflow NOVO e independente, com caminho gaq-jobs-web-v1. Não substitui o workflow do Grok já funcional nem o bot de Whisper/Telegram.

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

A função de status v2 exige justificativa para mudanças sensíveis com origem PEDIDO_USUARIO ou EMAIL. O PostgreSQL não verifica sozinho a mensagem real no Gmail. Para segurança independente, é necessário um fluxo de validação com credenciais Gmail próprias no n8n.

Não inclua senhas nem credenciais ao exportar os workflows.

Documentação n8n: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/
