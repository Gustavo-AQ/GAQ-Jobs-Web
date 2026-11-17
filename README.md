# GAQ Jobs Web

Painel privado de vagas e candidaturas da GAQ CLOUD.

Stack: React + TypeScript + Vite, FastAPI, PostgreSQL 18 e Docker Compose (Coolify). O Grok Bot continua utilizando o mesmo banco por meio do n8n/MCP.

## Funcionalidades

- Login próprio com Argon2id, sessões por cookies protegidos, validação de origem e CSRF.
- Sidebar recolhível, filtros de modalidade, contrato, aderência e data de coleta, busca e paginação.
- Detalhes, link original da vaga, status de candidatura e observações pessoais.
- Histórico auditável já existente em empregos.vagas_status_hist.
- Implantação sem adicionar outro banco PostgreSQL à Oracle.

## Arquivos

- compose.yaml: produção; apenas web e API.
- compose.db-bootstrap.yml: inicialização SQL opcional contra um banco PostgreSQL existente.
- compose.db-local.yml: PostgreSQL isolado para laboratório.
- db/: instaladores de tabelas, migração v2 e autenticação local.
- n8n/GAQ_Jobs_MCP_importar.json: workflow importável com 4 ferramentas, sem senhas.
- docs/INSTALACAO.md: instruções completas para Coolify e PostgreSQL.
- docs/USO.md: guia do painel.
- docs/N8N_MCP.md: guia para conectar o Grok.

## Instalação na Oracle

Como o banco gaq e as tabelas empregos.vagas e empregos.vagas_status_hist já existem, faça backup e execute somente db/001_auth_whodb.sql no WhoDB. Defina uma senha exclusiva para gaq_jobs_web, configure DATABASE_URL, APP_ORIGIN e SESSION_SECRET no Coolify, publique a aplicação a partir de compose.yaml e crie o primeiro administrador pelo terminal da API.

Não crie outro banco nem execute full bootstrap no PostgreSQL de produção sem backup e avaliação.

## Situação

Código em desenvolvimento, com branch própria e testes CI. O funcionamento em produção dependerá da configuração das credenciais, da conexão na rede Docker e da validação de deploy.
