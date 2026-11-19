# Coletor de vagas

Script em Python 3.11 ou superior (o CI usa 3.13; só a biblioteca padrão — veja `requirements.txt`) que busca vagas **sem login** nas fontes que responderam a um GET simples e grava um JSON no formato do [pré-filtro](../prefiltro/README.md).

Cada item tem `texto`, `url`, `autor`, `data` e `fonte`. O campo `texto` junta título, empresa, local, modelo de trabalho, nível, salário e um trecho da descrição — o suficiente para o pré-filtro pontuar.

Uso pessoal. Mantenha `atraso_segundos` em 1,2 ou mais e respeite os termos de cada site. A lista das fontes está em [docs/FONTES.md](../docs/FONTES.md).

## Uso

O config versionado é `config.example.json` (perfil genérico). `config.json` fica de fora do Git. Se `config.json` não existir, o script usa o exemplo.

```bash
cd coletor
cp config.example.json config.json   # opcional; edite só a cópia local
cp .env.example .env                 # opcional; GITHUB_TOKEN para a API do GitHub
python3 coletor.py
python3 coletor.py -c config.json -o vagas_coletadas.json
python3 coletor.py --fontes gupy,himalayas,nerdin --keywords "python,backend"
python3 testes.py
```

A saída `vagas_*.json` também fica de fora do Git. Depois, rode o pré-filtro:

```bash
python3 ../prefiltro/prefiltro.py vagas_coletadas.json -o vagas_prefiltradas.json
```

## Token opcional do GitHub

A fonte `backendbr` chama `https://api.github.com`. Sem token o limite é **60 requisições por hora**. Com a variável `GITHUB_TOKEN` (em `coletor/.env` ou no ambiente), o coletor envia `Authorization: Bearer …` **somente** para essa API. O valor não entra no JSON de saída nem no log. Deixe vazio para rodar sem autenticação.

## Configuração (`config.json`)

- `keywords` — termos de busca. Padrão: python, desenvolvedor python, backend, dados, automação, rpa, n8n, ia, devops, qa automação.
- `fontes` — quais coletores rodar. Padrão: `gupy`, `himalayas`, `infojobs`, `catho`, `vagas`, `nerdin`, `backendbr`, `programathor`, `remotar`.
- `backendbr_paginas` — páginas da API do GitHub (100 issues por página). Padrão 1, para respeitar o limite de 60 req/h sem token. Com `GITHUB_TOKEN`, o limite autenticado vale, mas o padrão continua 1.
- `filtro_local.remoto` / `filtro_local.sao_paulo` — quando a fonte aceita filtro, busca remoto e/ou São Paulo (estado). Vaga sem local informado não é descartada aqui; isso fica a cargo do pré-filtro.
- `max_por_busca` — teto de resultados por palavra-chave (nas APIs que paginam).
- `max_paginas` — quantas páginas pedir em cada busca (padrão 1, para não martelar o site).
- `atraso_segundos` — pausa entre requisições (padrão 1,2 s).
- `himalayas_country` — filtro de país da API do Himalayas (padrão `BR`; inclui vagas worldwide abertas a quem está no Brasil).
- `himalayas_seniority` — padrão `Entry-level` e `Mid-level`.
- `saida` — arquivo JSON de saída.

## Fontes que funcionam por HTTP, sem login

Testado em 15–16/11/2026 (fontes originais) e 18/11/2026 (backend-br, Programathor e Remotar), horário de Brasília, com `curl` e User-Agent de navegador, **sem autenticação**.

| Fonte | Método | Filtros úteis | Observação |
| --- | --- | --- | --- |
| **Gupy** | API JSON pública `https://portal.gupy.io/api/job-search/jobs` | `jobName`, `workplaceType=remote\|hybrid\|on-site`, `state=São Paulo` (por extenso; `SP` não funciona), `offset`, `limit` (máx. 100) | Sem login, HTTP 200. A API oficial `api.gupy.io` é para empresas e pede auth. O host antigo `employability-portal.gupy.io` está fora do ar (404). |
| **Himalayas** | API JSON pública `https://himalayas.app/jobs/api/search` (também há `/jobs/api` e RSS `/jobs/rss`) | `q`, `country`, `seniority`, `employment_type`, `sort=recent`, `page` | Sem chave, HTTP 200. Tudo é remoto. `country=BR` inclui vagas worldwide abertas ao Brasil. |
| **InfoJobs Brasil** | HTML da listagem + fragmento JSON ` /mf-publicarea/VacancyList/GetVacancyListFragment` | URLs `/vagas-de-emprego-{termo}-trabalho-home-office.aspx` e `/vagas-de-emprego-{termo}-em-sao-paulo,-sp.aspx` | Sem login, HTTP 200, ~20 cards por página. Não há API oficial documentada. |
| **Catho** | HTML da listagem `/vagas/{slug}/` | `sao-paulo-sp` no path, `work_model[0]=remote`, `order=dataAtualizacao`, `page` | Sem login, HTTP 200. Mostra uma página de resultados (ex.: 20 de 628); o site convida a cadastrar para ver o restante. API oficial é para recrutadores. |
| **Vagas.com.br** | HTML `/vagas-de-{slug}` e `/vagas-de-{slug}-em-sao-paulo` | Path de cidade; `ordenar_por=mais_recentes` | A listagem simples responde 200, mas o volume pode ser baixo. URLs com `m[]=100% Home Office` caíram no **Cloudflare challenge (403)**. Use só o path. |
| **Nerdin** (`nerdin.com.br`) | HTML público `https://www.nerdin.com.br/vagas.php` (~20 cards/página). Sem API/RSS de vagas (404). Só há JSON em `ajax/buscar_cidades.php`. | Busca oficial: `busca` (cargo/stack/cidade). Também `busca_vaga`, `busca_plataforma`, `busca_local`. Filtros: `filtro_home_office=1`, `filtro_hibrido=1`, `filtro_nivel[]` (4=Estágio, 3=Júnior, 6=Trainee, 2=Pleno, 1=Sênior, 7=Todos), `filtro_faixa_salarial`, `pagina`. Atalho de stack: `Plataforma=python` (equivale a `/vagas-python.php`). `busca_local=SP` cobre o estado. | Sem login e sem Cloudflare na listagem/detalhe (Apache, HTTP 200). **Não combine** `filtro_home_office=1` com `busca_local=SP` (zera o resultado). `q`, `palavra`, `pesquisa`, `dias` e `periodo` são ignorados. `PermiteTrabalhoRemoto=1` não é remoto — acabou filtrando híbrido. Login só entra para favoritar e, na prática, para se candidatar (`vaga_candidatura.php`, bloqueado no robots.txt). E-mail/WhatsApp da empresa são Premium. A página da vaga (título, empresa, salário, descrição) é pública e tem JSON-LD `JobPosting`. O coletor lê só a listagem. |
| **backend-br** (`backend-br/vagas`) | API pública do GitHub `https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100` (o site [backend-br.github.io/vagas](https://backend-br.github.io/vagas/) só lista essas issues). | Uma única busca por execução (cache local); o filtro de palavra-chave roda em título, corpo e labels. Labels úteis: `Júnior`, `Pleno`, `Remoto`, `CLT`, `PJ`. Descarta `Sênior`/`Especialista` e títulos de gestão. URL da vaga = `html_url` da issue. | Sem login de site de emprego, HTTP 200. Sem token o limite é **60 req/h** — por isso não há um GET por palavra-chave. `GITHUB_TOKEN` opcional sobe para o limite autenticado e só vai no header dessa API. `backendbr_paginas` controla quantas páginas de 100 issues buscar (padrão 1). |
| **Programathor** (`programathor.com.br`) | HTML público das listagens `/jobs`, `/jobs-python`, `/jobs-city/remoto` e `/jobs-city/sao-paulo`. | `?search=` e `?q=` são **ignorados** pelo site. Filtros que funcionam: `expertise=Júnior / Pleno / Sênior`, `remoto=true` (redireciona para `/jobs-city/remoto`), `contract_type`, paginação `/page/N`. O coletor baixa poucas listagens uma vez e filtra localmente. | Sem login, HTTP 200. Há **Cloudflare**: rajadas de pedidos caem em **429**. Usar o atraso padrão (≥1,2 s). A combinação `remoto + Júnior` estava vazia no teste de 18/11/2026. O coletor descarta Sênior pelo nível do card e pelo título. |
| **Remotar** (`remotar.com.br`) | API JSON pública `https://api.remotar.com.br/jobs` (a listagem do site é Next.js e não traz as vagas no HTML). | `search`, `page` (50 por página). Campos: título, empresa, tags (Júnior/Pleno/Sênior, CLT/PJ, remoto), categorias, salário (valores em centavos), `createdAt`. URL pública da vaga: `https://remotar.com.br/job/{id}`. | Sem login, HTTP 200, sem Cloudflare. Tudo é (ou aceita) remoto. O coletor reaplica o filtro de palavra-chave no título/tags/descrição (a busca da API é ampla) e descarta Sênior/gestão. |

## Fontes que **não** entram no coletor

| Fonte | O que aconteceu no teste | Caminho possível depois |
| --- | --- | --- |
| **Indeed Brasil** (`br.indeed.com`) | Busca HTML: **403** + Cloudflare. RSS (`/rss?q=`): **404**. Não há API pública utilizável. | Navegador (e, se ainda bloquear, login/cookies). |
| **99jobs** | `/opportunities`, `/jobs` e `/search?q=python` redirecionam **302** para a home. `/opportunities/filtered_search?search=python` devolveu **500**. Sem API pública. | Ficou de fora de propósito. O coletor não faz login. |
| **Wellfound** | GET na página SEO (`/role/...`) às vezes devolve HTML 200 com vagas em `__NEXT_DATA__`, mas a página embute **Cloudflare Turnstile**. GraphQL interno pede sessão. Sem API pública. | Navegador; busca completa costuma exigir login. |

Nenhuma destas fontes foi acessada com cadastro ou senha.

## Saída

JSON com `resumo` (quando coletou, quantas requisições, brutas vs. únicas, erros HTTP) e `vagas` (lista no formato do pré-filtro). Datas, quando dá para interpretar, saem em ISO 8601 no fuso **America/Sao_Paulo** (UTC−3).

O coletor **não** aplica o piso salarial nem a nota de aderência — isso é papel do pré-filtro.
