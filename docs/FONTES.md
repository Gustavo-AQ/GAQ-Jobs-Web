# Fontes de vagas

Há dois jeitos de achar vaga neste projeto. Os dois são somente leitura na origem: ninguém se candidata nem envia mensagem a partir do coletor ou do navegador do assistente. O que passa na análise é gravado depois, no PostgreSQL (`schema empregos`), pelas ferramentas MCP.

Uso pessoal. Em coleta HTTP, mantenha pausa de pelo menos **1,2 s** entre pedidos (`atraso_segundos` no coletor). Respeite os termos de uso de cada site. Sem token, a API do GitHub permite **60 requisições por hora**.

## Pelo assistente de IA, no navegador

O assistente abre o site já logado, lê o que está na tela e não altera a conta. Não há coletor HTTP para estas fontes.

| Fonte | Onde | O que ler |
| --- | --- | --- |
| **LinkedIn** | Feed e posts de recrutadores | Posts de gente anunciando vaga. A aba Empregos (jobs) fica de fora desta rotina. |
| **Padrinho** | [meupadrinho.com.br](https://meupadrinho.com.br) | Vagas e indicações visíveis na conta. |
| **Robô de Vagas** | [app.robodevagas.com.br](https://app.robodevagas.com.br) | Lista que o produto já reuniu para a conta. |

O texto lido segue para a análise do assistente (aderência e rotina semanal das 5 melhores), não para o pré-filtro em Python.

## Pelo coletor, sem login

Pasta `coletor/`. HTTP público (API JSON ou HTML), sem cadastro e sem senha. Detalhe de URL, paginação e o que cada site ignora está no [README do coletor](../coletor/README.md).

| Fonte | Como o coletor lê | Nota de uso |
| --- | --- | --- |
| **backend-br/vagas** | Issues abertas em `github.com/backend-br/vagas`, pela API pública do GitHub | Uma busca por execução, filtro de palavra-chave local. Sem `GITHUB_TOKEN`: 60 req/h. Com token (veja `coletor/.env.example`): limite autenticado, header só nessa API. |
| **Remotar** | API JSON pública `api.remotar.com.br` | Sem login. Quase tudo é remoto. |
| **Programathor** | HTML público das listagens | Cloudflare responde **429** se os pedidos vierem em rajada. Não desça o atraso de 1,2 s. |
| **Gupy** | API JSON pública do portal (`portal.gupy.io`) | A API de empresas (`api.gupy.io`) pede autenticação e não é usada. |
| **NerdIn** | HTML público de `nerdin.com.br` | Sem login. Não misturar filtro de home office com busca por UF (a combinação zera o resultado). |
| **Vagas.com.br** | HTML público do path da busca | Parâmetros entre colchetes tendem a cair no Cloudflare. O coletor usa só o path. |
| **Catho** | HTML público da listagem | A listagem aberta mostra uma página; o restante pede cadastro, que o coletor não faz. |
| **InfoJobs** | HTML da listagem e fragmento público | Sem API oficial documentada para este uso. |
| **Himalayas** | API JSON pública, sem chave | Vagas remotas. `country=BR` inclui worldwide aberto a quem está no Brasil. |

A saída do coletor entra no [pré-filtro](../prefiltro/README.md). Só então o assistente lê o que sobrou, dá a nota de aderência e escolhe o top 5 da semana.

## De fora, por escolha

Estas três não entram no coletor nem na rotina do navegador. No teste em que o coletor foi montado, Indeed e Wellfound caíram em bloqueio (Cloudflare), e a 99jobs não expôs busca pública estável. A decisão é não usá-las.

| Fonte | Por que ficou de fora |
| --- | --- |
| **Indeed** | Busca HTML com 403 / Cloudflare. RSS da busca respondeu 404. Sem API pública utilizável sem login. |
| **99jobs** | Rotas de busca redirecionavam para a home ou respondiam erro. Sem API pública. |
| **Wellfound** | A página às vezes traz HTML, mas embute desafio Cloudflare; a busca completa pede sessão. |

Nenhuma delas foi acessada com cadastro ou senha.

## O que não é fonte deste repositório

O fluxo antigo chamado "Pipeline de Análise de Vagas com IA" (WhatsApp e Google Sheets) e qualquer bot de Whisper ou Telegram são outro sistema, legado. Não alimentam este coletor, este pré-filtro nem o painel em [https://jobs.gaqtech.dev](https://jobs.gaqtech.dev).
