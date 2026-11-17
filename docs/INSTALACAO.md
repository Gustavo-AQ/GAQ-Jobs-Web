# Instalação GAQ Jobs Web — Coolify

## Ambiente atual

Oracle MASTER ARM64; banco PostgreSQL 18, database gaq, schema empregos. n8n/Grok já conectados por MCP. O Compose principal NÃO cria outro banco.

## 1. Faça backup e migre apenas a autenticação

No WhoDB, conectado ao database gaq com usuário administrador, execute o arquivo db/001_auth_whodb.sql. É um único comando DO e preserva as tabelas vagas e vagas_status_hist.

Em execução SQL separada:

    ALTER ROLE gaq_jobs_web WITH PASSWORD 'SENHA_FORTE_EXCLUSIVA';

Nunca reutilize a senha do usuário gaq_jobs_grok.

Verifique:

    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'empregos' ORDER BY table_name;

Novas tabelas: web_usuarios, web_sessoes, web_login_tentativas.

## 2. Compose opcional de tabelas

O arquivo compose.db-bootstrap.yml NÃO é utilizado no deploy do site. Ele é executado manualmente quando necessário, usando um PostgreSQL de administração e a rede privada Docker coolify.

Preencha .env.db-bootstrap conforme .env.db-bootstrap.example (não versione).

Somente as tabelas e permissões do painel web no banco atual:

    docker compose --env-file .env.db-bootstrap -f compose.db-bootstrap.yml --profile setup run --rm init-web

Em um banco vazio, para recriar toda a estrutura GAQ Jobs:

    docker compose --env-file .env.db-bootstrap -f compose.db-bootstrap.yml --profile full-setup run --rm init-full

ATENÇÃO: modo full redefine funções/triggers existentes. Faça backup e use apenas quando necessário.

## 3. Banco de laboratório separado (opcional)

Para testar fora do banco oficial:

    LOCAL_DB_PASSWORD='SENHA_LOCAL' docker compose -f compose.db-local.yml up -d

Esse compose cria PostgreSQL 18 e o database gaq, executando SQLs apenas quando o volume estiver vazio. Ele não publica porta. Não apague seu volume com down -v se quiser manter os dados.

## 4. Configure o Coolify

1. Adicione repositório Gustavo-AQ/GAQ-Jobs-Web como Application.
2. Build Pack Docker Compose, localização /compose.yaml.
3. Branch de teste feat/gaq-jobs-web-v1; main após integração.
4. Configure as variáveis privadas:
   - DATABASE_URL = postgresql+psycopg://gaq_jobs_web:SENHA_URL_ENCODED@HOST_INTERNO:5432/gaq
   - APP_ORIGIN = https://jobs.gaqtech.dev
   - SESSION_SECRET = valor de openssl rand -hex 32
   - SESSION_HOURS = 72 (opcional)
5. Configure o domínio HTTPS jobs.gaqtech.dev no serviço web, porta interna 80.
6. Nunca abra a API ou PostgreSQL usando ports; web fala com api pela rede Docker.
7. Faça Deploy e confira os health checks.

O backend está na rede Docker coolify para alcançar o PostgreSQL existente. O hostname correto é o mesmo usado na rede interna pelos demais containers, se alcançável nessa rede. Não use coolify-db.

## 5. Crie o primeiro administrador

Com terminal interativo do container API:

    python -m app.create_admin --email SEU_EMAIL

Ou via Docker Compose local:

    docker compose exec api python -m app.create_admin --email SEU_EMAIL

Informe a senha somente no prompt, nunca em argumentos, env ou Git.

## 6. Teste após deploy

Confirme login, dashboard com vagas reais, botão Abrir vaga, busca, filtros, edição de status e histórico no WhoDB. Teste com uma vaga de laboratório. O Grok e o Whisper devem continuar funcionando. Logout deve encerrar sessão.

A aplicação usa autenticação interna; mudar de domínio exige atualizar APP_ORIGIN, domínio Coolify e DNS, sem perder usuários. Sessões antigas podem exigir login novo.

## Diagnóstico e segurança

- 401: sessão ausente/expirada.
- 403: origem diferente de APP_ORIGIN, CSRF ou usuário sem permissão.
- 500 no login: execute a migração SQL web e verifique gaq_jobs_web.
- API unhealthy: confira DATABASE_URL, credenciais e rede Docker.
- Nginx 502: API não disponível na rede do Compose.
- Não existe recuperação de senha por email nesta primeira versão.
- Cookies seguros exigem HTTPS.

Documentação oficial: https://coolify.io/docs/applications/builds/docker-compose
