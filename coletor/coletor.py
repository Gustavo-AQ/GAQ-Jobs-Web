#!/usr/bin/env python3
"""Coletor de vagas em HTTP puro (somente biblioteca padrão), sem login.

Fontes ativas: Gupy (API JSON pública), Himalayas (API JSON pública),
InfoJobs, Catho, Vagas.com.br e Nerdin (HTML público), backend-br (API do
GitHub), Programathor (HTML) e Remotar (API JSON pública). Indeed, 99jobs e
Wellfound ficam de fora: bloqueio ou login — veja o README.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
TZ_SP = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def carregar_config(caminho: Path) -> dict[str, Any]:
    with caminho.open(encoding="utf-8") as fh:
        return json.load(fh)


def carregar_dotenv(caminho: Path | None = None) -> None:
    """Lê GITHUB_TOKEN de um .env simples, sem dependência extra.

    Não sobrescreve a variável se ela já estiver no ambiente e ignora qualquer
    outra chave (para não puxar segredo do painel). O arquivo coletor/.env
    fica de fora do Git.
    """
    arquivo = caminho or (DIR / ".env")
    if not arquivo.is_file():
        return
    if (os.environ.get("GITHUB_TOKEN") or "").strip():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        if linha.startswith("export "):
            linha = linha[len("export ") :].strip()
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        if chave != "GITHUB_TOKEN":
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {'"', "'"}:
            valor = valor[1:-1]
        if valor:
            os.environ["GITHUB_TOKEN"] = valor
        return


def token_github() -> str:
    return (os.environ.get("GITHUB_TOKEN") or "").strip()


def cabecalhos_github() -> dict[str, str]:
    """Authorization só para api.github.com. Nunca anexar este header a outros sites."""
    token = token_github()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def resolver_config(caminho: str | None) -> Path:
    """config.json ao lado do script, se existir; senão config.example.json.

    Um caminho explícito é procurado no diretório atual e, em seguida, nesta pasta.
    """
    if caminho:
        informado = Path(caminho)
        if not informado.is_absolute():
            no_cwd = (Path.cwd() / informado).resolve()
            no_script = (DIR / informado).resolve()
            if no_cwd.is_file():
                return no_cwd
            if no_script.is_file():
                return no_script
            return no_cwd
        return informado
    for nome in ("config.json", "config.example.json"):
        candidato = DIR / nome
        if candidato.is_file():
            return candidato
    return DIR / "config.json"


def slugify(texto: str, sep: str = "-") -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", sep, texto).strip(sep)
    return texto or "vaga"


def infojobs_termo(texto: str) -> str:
    """InfoJobs usa + no lugar de espaço no slug da URL."""
    return slugify(texto, sep="+")


def strip_tags(texto: str) -> str:
    if not texto:
        return ""
    texto = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", texto)
    texto = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", texto)
    texto = re.sub(r"(?i)<br\s*/?>", "\n", texto)
    texto = re.sub(r"(?i)</p>", "\n", texto)
    texto = re.sub(r"(?i)</div>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto)
    return texto.strip()


def compactar(texto: str, limite: int = 1200) -> str:
    texto = strip_tags(texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > limite:
        return texto[: limite - 1].rstrip() + "…"
    return texto


def agora_iso() -> str:
    return datetime.now(TZ_SP).isoformat(timespec="seconds")


def iso_de_unix(ts: int | float | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), TZ_SP).isoformat(timespec="seconds")
    except (OSError, ValueError, TypeError, OverflowError):
        return ""


def iso_de_gupy(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return dt.astimezone(TZ_SP).isoformat(timespec="seconds")
    except ValueError:
        return valor


def iso_de_infojobs(valor: str | None) -> str:
    """Ex.: '2026/11/12 11:23:00' (sem fuso explícito; tratamos como horário de Brasília)."""
    if not valor:
        return ""
    valor = valor.strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(valor, fmt).replace(tzinfo=TZ_SP).isoformat(timespec="seconds")
        except ValueError:
            continue
    return valor


def iso_de_catho(valor: str | None) -> str:
    """Ex.: 'Publicada em 05/11' (assume o ano corrente no fuso de Brasília)."""
    if not valor:
        return ""
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", valor)
    if not m:
        return valor.strip()
    dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    ano_i = int(ano) if ano else datetime.now(TZ_SP).year
    if ano_i < 100:
        ano_i += 2000
    try:
        return datetime(ano_i, mes, dia, tzinfo=TZ_SP).isoformat(timespec="seconds")
    except ValueError:
        return valor.strip()


def iso_de_vagas(valor: str | None) -> str:
    if not valor:
        return ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", valor)
    if not m:
        return iso_de_catho(valor)
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d, tzinfo=TZ_SP).isoformat(timespec="seconds")
    except ValueError:
        return valor.strip()


def iso_de_nerdin(valor: str | None) -> str:
    """Ex.: '2026-11-14T12:39:22-05:00' no <time datetime> do card."""
    if not valor:
        return ""
    valor = valor.strip()
    try:
        dt = datetime.fromisoformat(valor)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_SP)
        return dt.astimezone(TZ_SP).isoformat(timespec="seconds")
    except ValueError:
        return valor


def montar_texto(
    titulo: str = "",
    empresa: str = "",
    local: str = "",
    modelo: str = "",
    nivel: str = "",
    salario: str = "",
    descricao: str = "",
) -> str:
    linhas = []
    if titulo:
        linhas.append(f"Título: {titulo}")
    if empresa:
        linhas.append(f"Empresa: {empresa}")
    if local:
        linhas.append(f"Local: {local}")
    if modelo:
        linhas.append(f"Modelo: {modelo}")
    if nivel:
        linhas.append(f"Nível: {nivel}")
    if salario:
        linhas.append(f"Salário: {salario}")
    if descricao:
        linhas.append(f"Descrição: {compactar(descricao)}")
    return "\n".join(linhas)


def item(
    *,
    fonte: str,
    url: str,
    autor: str = "",
    data: str = "",
    titulo: str = "",
    empresa: str = "",
    local: str = "",
    modelo: str = "",
    nivel: str = "",
    salario: str = "",
    descricao: str = "",
) -> dict[str, str]:
    return {
        "fonte": fonte,
        "autor": autor or empresa or "",
        "data": data or "",
        "url": url,
        "texto": montar_texto(
            titulo=titulo,
            empresa=empresa or autor,
            local=local,
            modelo=modelo,
            nivel=nivel,
            salario=salario,
            descricao=descricao,
        ),
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class ClienteHTTP:
    def __init__(self, user_agent: str, timeout: int, atraso: float) -> None:
        self.timeout = timeout
        self.atraso = atraso
        self._ultimo = 0.0
        self.user_agent = user_agent
        jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.erros: list[dict[str, Any]] = []
        self.requisicoes = 0

    def _esperar(self) -> None:
        if self._ultimo and self.atraso > 0:
            falta = self.atraso - (time.monotonic() - self._ultimo)
            if falta > 0:
                time.sleep(falta)

    def get(
        self,
        url: str,
        *,
        accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        referer: str | None = None,
        origem: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Devolve (status, corpo texto, url final). Corpo vazio se falhar de vez."""
        self._esperar()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if referer:
            headers["Referer"] = referer
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers, method="GET")
        self.requisicoes += 1
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                status = getattr(resp, "status", None) or resp.getcode() or 200
                final = resp.geturl()
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                charset = "utf-8"
                m = re.search(r"charset=([^\s;]+)", ctype, re.I)
                if m:
                    charset = m.group(1).strip("\"'")
                corpo = raw.decode(charset, errors="replace")
                self._ultimo = time.monotonic()
                if status >= 400:
                    self.erros.append(
                        {"url": url, "status": status, "origem": origem, "final": final}
                    )
                return int(status), corpo, final
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read() or b""
            except Exception:
                raw = b""
            corpo = raw.decode("utf-8", errors="replace")
            self._ultimo = time.monotonic()
            self.erros.append(
                {"url": url, "status": exc.code, "origem": origem, "detalhe": str(exc.reason)}
            )
            return int(exc.code), corpo, url
        except Exception as exc:  # noqa: BLE001 — rede instável não pode derrubar a coleta
            self._ultimo = time.monotonic()
            self.erros.append({"url": url, "status": 0, "origem": origem, "detalhe": str(exc)})
            return 0, "", url


def bloqueado(status: int, corpo: str) -> bool:
    if status in (401, 403, 429, 503):
        return True
    trecho = (corpo or "")[:4000].lower()
    sinais = (
        "just a moment",
        "cf-mitigated",
        "attention required",
        "datadome",
        "captcha",
        "challenge-platform",
        "enable javascript and cookies",
    )
    return any(s in trecho for s in sinais)


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------


def coletar_gupy(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """API pública do portal: https://portal.gupy.io/api/job-search/jobs (sem auth)."""
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    consultas: list[dict[str, str]] = []
    if cfg.get("filtro_local", {}).get("remoto", True):
        consultas.append({"jobName": keyword, "workplaceType": "remote"})
    if cfg.get("filtro_local", {}).get("sao_paulo", True):
        consultas.append({"jobName": keyword, "state": "São Paulo"})
    if not consultas:
        consultas.append({"jobName": keyword})

    limite = min(int(cfg.get("max_por_busca", 40)), 100)
    max_paginas = max(1, int(cfg.get("max_paginas", 1)))

    for params_base in consultas:
        for pagina in range(max_paginas):
            offset = pagina * min(limite, 100)
            params = dict(params_base)
            params.update({"offset": str(offset), "limit": str(min(limite, 100))})
            url = "https://portal.gupy.io/api/job-search/jobs?" + urllib.parse.urlencode(params)
            status, corpo, _ = http.get(
                url, accept="application/json,text/plain,*/*;q=0.8", origem="gupy"
            )
            if status != 200 or not corpo:
                log(f"  gupy falhou ({status}) {url}")
                break
            try:
                dados = json.loads(corpo)
            except json.JSONDecodeError:
                log("  gupy: resposta não é JSON")
                break
            rows = dados.get("data") or []
            for row in rows:
                job_url = (row.get("jobUrl") or "").strip()
                if not job_url or job_url in visto:
                    continue
                empresa = (row.get("careerPageName") or "").strip()
                if empresa.lower() in {"confidencial", "empresa confidencial"}:
                    continue
                visto.add(job_url)
                cidade = (row.get("city") or "").strip()
                estado = (row.get("state") or "").strip()
                local = " ".join(p for p in (cidade, estado) if p)
                modelo_raw = (row.get("workplaceType") or "").strip()
                modelo = {
                    "remote": "remoto",
                    "hybrid": "híbrido",
                    "on-site": "presencial",
                    "onsite": "presencial",
                }.get(modelo_raw, modelo_raw)
                vagas.append(
                    item(
                        fonte="gupy",
                        url=job_url,
                        autor=empresa,
                        data=iso_de_gupy(row.get("publishedDate")),
                        titulo=(row.get("name") or "").strip(),
                        empresa=empresa,
                        local=local,
                        modelo=modelo,
                        descricao=row.get("description") or "",
                    )
                )
            if len(rows) < min(limite, 100):
                break
            if len(vagas) >= limite and len(consultas) == 1:
                break
    return vagas


def coletar_himalayas(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """API pública, sem chave: https://himalayas.app/jobs/api/search"""
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    limite = int(cfg.get("max_por_busca", 40))
    params: dict[str, str] = {"q": keyword, "sort": "recent"}
    country = cfg.get("himalayas_country")
    if country:
        params["country"] = str(country)
    seniority = cfg.get("himalayas_seniority") or []
    if seniority:
        params["seniority"] = ",".join(seniority)

    for pagina in range(1, max_paginas + 1):
        params["page"] = str(pagina)
        url = "https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(params)
        status, corpo, _ = http.get(
            url, accept="application/json,text/plain,*/*;q=0.8", origem="himalayas"
        )
        if status != 200 or not corpo:
            log(f"  himalayas falhou ({status}) {url}")
            break
        try:
            dados = json.loads(corpo)
        except json.JSONDecodeError:
            log("  himalayas: resposta não é JSON")
            break
        rows = dados.get("jobs") or []
        if not rows:
            break
        for row in rows:
            job_url = (row.get("guid") or row.get("applicationLink") or "").strip()
            if not job_url or job_url in visto:
                continue
            visto.add(job_url)
            locs = row.get("locationRestrictions") or []
            if isinstance(locs, list):
                local = ", ".join(str(x) for x in locs[:8])
                if len(locs) > 8:
                    local += f" (+{len(locs) - 8})"
            else:
                local = str(locs)
            salario = ""
            if row.get("minSalary") or row.get("maxSalary"):
                moeda = row.get("currency") or ""
                periodo = row.get("salaryPeriod") or ""
                lo, hi = row.get("minSalary"), row.get("maxSalary")
                if lo and hi:
                    faixa = f"{lo}–{hi}"
                else:
                    faixa = str(lo or hi)
                salario = " ".join(p for p in (moeda, faixa, periodo) if p)
            nivel = ""
            sen = row.get("seniority") or []
            if isinstance(sen, list):
                nivel = ", ".join(str(x) for x in sen)
            elif sen:
                nivel = str(sen)
            vagas.append(
                item(
                    fonte="himalayas",
                    url=job_url,
                    autor=(row.get("companyName") or "").strip(),
                    data=iso_de_unix(row.get("pubDate")),
                    titulo=(row.get("title") or "").strip(),
                    empresa=(row.get("companyName") or "").strip(),
                    local=local or "remoto",
                    modelo="remoto",
                    nivel=nivel,
                    salario=salario,
                    descricao=row.get("excerpt") or row.get("description") or "",
                )
            )
            if len(vagas) >= limite:
                return vagas
        if len(rows) < 20:
            break
    return vagas


def _cards_infojobs(html_pagina: str) -> list[dict[str, str]]:
    encontrados: list[dict[str, str]] = []
    matches = list(
        re.finditer(
            r'data-id="(\d+)"[^>]*data-href="([^"]+)"|data-href="([^"]+)"[^>]*data-id="(\d+)"',
            html_pagina,
        )
    )
    for i, m in enumerate(matches):
        if m.group(1):
            vid, href = m.group(1), m.group(2)
        else:
            href, vid = m.group(3), m.group(4)
        ini = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else min(len(html_pagina), ini + 5000)
        card = html_pagina[ini:fim]
        titulo = ""
        tm = re.search(r'js_vacancyTitle[^>]*>(.*?)</', card, re.S)
        if tm:
            titulo = strip_tags(tm.group(1))
        empresa = ""
        cm = re.search(
            r'<a[^>]+href="https://www\.infojobs\.com\.br/[^"]+"[^>]*>(.*?)</a>',
            card,
            re.S,
        )
        if cm:
            empresa = strip_tags(cm.group(1))
            empresa = re.split(r"Este selo indica", empresa, flags=re.I)[0]
            empresa = re.sub(r"\s+", " ", empresa).strip()
        data_raw = ""
        dm = re.search(r'js_date[^>]*data-value="([^"]+)"', card)
        if dm:
            data_raw = dm.group(1)
        local = ""
        # "Belo Horizonte - MG" aparece num div.mb-8 logo após a empresa
        lm = re.search(r"<div class=\"mb-8\">\s*([^<]+?)\s*<span", card)
        if not lm:
            lm = re.search(r">\s*([A-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõç ]+ - [A-Z]{2})\s*<", card)
        if lm:
            local = strip_tags(lm.group(1))
        salario = ""
        modelo = ""
        sm = re.search(r"icon-money.*?</svg>\s*([^<]+)", card, re.S)
        if sm:
            salario = strip_tags(sm.group(1))
        mm = re.search(r"icon-buildings.*?</svg>\s*([^<]+)", card, re.S)
        if mm:
            modelo = strip_tags(mm.group(1))
        # home office / remoto às vezes vem no mesmo bloco
        if re.search(r"home office|remoto", card, re.I) and not modelo:
            modelo = "remoto"
        snippet = ""
        # último parágrafo de texto médio costuma ser o resumo
        paras = re.findall(r'<div class="text-medium">\s*(.*?)\s*</div>', card, re.S)
        if paras:
            snippet = strip_tags(paras[-1])
        if href.startswith("/"):
            url = "https://www.infojobs.com.br" + href
        elif href.startswith("http"):
            url = href
        else:
            url = "https://www.infojobs.com.br/" + href
        encontrados.append(
            {
                "id": vid,
                "url": url,
                "titulo": titulo,
                "empresa": empresa,
                "data": iso_de_infojobs(data_raw),
                "local": local,
                "salario": salario,
                "modelo": modelo,
                "descricao": snippet,
            }
        )
    return encontrados


def coletar_infojobs(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    termo = infojobs_termo(keyword)
    urls: list[str] = []
    if cfg.get("filtro_local", {}).get("remoto", True):
        urls.append(
            f"https://www.infojobs.com.br/vagas-de-emprego-{termo}-trabalho-home-office.aspx"
        )
    if cfg.get("filtro_local", {}).get("sao_paulo", True):
        urls.append(
            f"https://www.infojobs.com.br/vagas-de-emprego-{termo}-em-sao-paulo,-sp.aspx"
        )
    if not urls:
        urls.append(f"https://www.infojobs.com.br/vagas-de-emprego-{termo}.aspx")

    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    for list_url in urls:
        # página 1: HTML da listagem
        # páginas seguintes: endpoint de fragmento (JSON com HTML)
        status, corpo, _ = http.get(list_url, referer="https://www.infojobs.com.br/", origem="infojobs")
        if bloqueado(status, corpo):
            log(f"  infojobs bloqueou ({status}) {list_url}")
            break
        if status != 200 or not corpo:
            log(f"  infojobs falhou ({status}) {list_url}")
            continue
        cards = _cards_infojobs(corpo)
        for c in cards:
            if c["url"] in visto:
                continue
            visto.add(c["url"])
            vagas.append(
                item(
                    fonte="infojobs",
                    url=c["url"],
                    autor=c["empresa"],
                    data=c["data"],
                    titulo=c["titulo"],
                    empresa=c["empresa"],
                    local=c["local"],
                    modelo=c["modelo"],
                    salario=c["salario"],
                    descricao=c["descricao"],
                )
            )

        for pagina in range(2, max_paginas + 1):
            enc = urllib.parse.quote(list_url, safe="")
            frag = (
                "https://www.infojobs.com.br/mf-publicarea/VacancyList/"
                f"GetVacancyListFragment?url={enc}&page={pagina}"
            )
            status, corpo, _ = http.get(
                frag,
                accept="application/json,text/javascript,*/*;q=0.8",
                referer=list_url,
                origem="infojobs",
            )
            if status != 200 or not corpo or bloqueado(status, corpo):
                log(f"  infojobs fragmento falhou ({status}) page={pagina}")
                break
            try:
                dados = json.loads(corpo)
            except json.JSONDecodeError:
                break
            html_frag = dados.get("listFragmentHTML") or ""
            extra = _cards_infojobs(html_frag)
            novos = 0
            for c in extra:
                if c["url"] in visto:
                    continue
                visto.add(c["url"])
                novos += 1
                vagas.append(
                    item(
                        fonte="infojobs",
                        url=c["url"],
                        autor=c["empresa"],
                        data=c["data"],
                        titulo=c["titulo"],
                        empresa=c["empresa"],
                        local=c["local"],
                        modelo=c["modelo"],
                        salario=c["salario"],
                        descricao=c["descricao"],
                    )
                )
            if dados.get("eof") or novos == 0:
                break
    return vagas


def _cards_catho(html_pagina: str) -> list[dict[str, str]]:
    encontrados: list[dict[str, str]] = []
    for m in re.finditer(
        r'<li[^>]*data-offer-item="(\d+)"[^>]*>(.*?)</li>',
        html_pagina,
        re.S,
    ):
        oid, card = m.group(1), m.group(2)
        am = re.search(
            r'<a[^>]+href="([^"]+)"[^>]*title="([^"]+)"[^>]*data-navigation-offer',
            card,
        )
        if not am:
            am = re.search(r'<h2 class="title_offer">\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', card, re.S)
            if not am:
                continue
            href, titulo = am.group(1), strip_tags(am.group(2))
        else:
            href, titulo = am.group(1), html.unescape(am.group(2))
        empresa = ""
        em = re.search(r'<span class="text-12">([^<]+)</span>', card)
        if em:
            empresa = strip_tags(em.group(1))
        local = ""
        # " - Belo Horizonte" depois do ícone de local
        lm = re.search(r"i_job_location.*?</span>\s*<strong>.*?</strong>\s*[-–]\s*([^<]+)", card, re.S)
        if lm:
            local = strip_tags(lm.group(1))
        salario = ""
        sm = re.search(r"i_salary.*?<strong>([^<]+)</strong>", card, re.S)
        if sm:
            salario = strip_tags(sm.group(1))
        data_raw = ""
        dm = re.search(r'class="tag[^"]*"[^>]*>\s*(Publicada[^<]+)', card)
        if dm:
            data_raw = strip_tags(dm.group(1))
        if href.startswith("/"):
            url = "https://www.catho.com.br" + href
        else:
            url = href
        encontrados.append(
            {
                "id": oid,
                "url": url,
                "titulo": titulo,
                "empresa": empresa,
                "local": local,
                "salario": salario,
                "data": iso_de_catho(data_raw),
                "descricao": data_raw,
            }
        )
    return encontrados


def coletar_catho(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    slug = slugify(keyword)
    urls: list[str] = []
    if cfg.get("filtro_local", {}).get("remoto", True):
        # work_model[0]=remote na listagem nacional
        urls.append(
            f"https://www.catho.com.br/vagas/{slug}/?work_model%5B0%5D=remote&order=dataAtualizacao"
        )
    if cfg.get("filtro_local", {}).get("sao_paulo", True):
        urls.append(
            f"https://www.catho.com.br/vagas/{slug}/sao-paulo-sp/?order=dataAtualizacao"
        )
    if not urls:
        urls.append(f"https://www.catho.com.br/vagas/{slug}/?order=dataAtualizacao")

    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    for base in urls:
        for pagina in range(1, max_paginas + 1):
            url = base
            if pagina > 1:
                sep = "&" if "?" in base else "?"
                url = f"{base}{sep}page={pagina}"
            status, corpo, _ = http.get(url, referer="https://www.catho.com.br/", origem="catho")
            if bloqueado(status, corpo):
                log(f"  catho bloqueou ({status}) {url}")
                return vagas
            if status != 200 or not corpo:
                log(f"  catho falhou ({status}) {url}")
                break
            cards = _cards_catho(corpo)
            if not cards:
                break
            novos = 0
            # detecta remoto pelo próprio filtro da URL
            modelo = "remoto" if "work_model" in url else ""
            for c in cards:
                if c["url"] in visto:
                    continue
                visto.add(c["url"])
                novos += 1
                vagas.append(
                    item(
                        fonte="catho",
                        url=c["url"],
                        autor=c["empresa"],
                        data=c["data"],
                        titulo=c["titulo"],
                        empresa=c["empresa"],
                        local=c["local"] or ("São Paulo - SP" if "sao-paulo-sp" in url else ""),
                        modelo=modelo or c.get("modelo", ""),
                        salario=c["salario"],
                        descricao=c["descricao"],
                    )
                )
            if novos == 0:
                break
    return vagas


def _cards_vagas(html_pagina: str) -> list[dict[str, str]]:
    encontrados: list[dict[str, str]] = []
    for m in re.finditer(r'<li class="vaga[^"]*"[\s\S]*?</li>', html_pagina):
        card = m.group(0)
        am = re.search(
            r'<a class="link-detalhes-vaga"[^>]*data-id-vaga="(\d+)"[^>]*title="([^"]+)"[^>]*href="([^"]+)"',
            card,
        )
        if not am:
            am = re.search(
                r'<a class="link-detalhes-vaga"[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*data-id-vaga="(\d+)"',
                card,
            )
            if not am:
                continue
            href, titulo, vid = am.group(1), html.unescape(am.group(2)), am.group(3)
        else:
            vid, titulo, href = am.group(1), html.unescape(am.group(2)), am.group(3)
        empresa = ""
        em = re.search(r'<span class="emprVaga">\s*([^<]+)', card)
        if em:
            empresa = strip_tags(em.group(1))
        nivel = ""
        nm = re.search(r'<span class="nivelVaga">\s*([^<]+)', card)
        if nm:
            nivel = strip_tags(nm.group(1))
        local = ""
        lm = re.search(r'<div class="vaga-local">([\s\S]*?)</div>', card)
        if lm:
            local = strip_tags(lm.group(1))
            # remove texto de tooltip
            local = re.split(r"A empresa aceita", local)[0].strip()
        data_raw = ""
        dm = re.search(r'<span class="data-publicacao">([\s\S]*?)</span>', card)
        if dm:
            data_raw = strip_tags(dm.group(1))
        snippet = ""
        sm = re.search(r'<div class="detalhes">([\s\S]*?)</div>', card)
        if sm:
            snippet = strip_tags(sm.group(1))
        if href.startswith("/"):
            url = "https://www.vagas.com.br" + href
        else:
            url = href
        encontrados.append(
            {
                "id": vid,
                "url": url,
                "titulo": titulo,
                "empresa": empresa,
                "nivel": nivel,
                "local": local,
                "data": iso_de_vagas(data_raw),
                "descricao": snippet,
            }
        )
    return encontrados


def coletar_vagas(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """HTML público. URLs com parâmetros entre colchetes tendem a cair no Cloudflare; usamos só o path."""
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    slug = slugify(keyword)
    urls: list[tuple[str, str]] = []
    # nacional (pode incluir remoto e outros estados; o pré-filtro descarta presencial fora de SP)
    urls.append((f"https://www.vagas.com.br/vagas-de-{slug}", ""))
    if cfg.get("filtro_local", {}).get("sao_paulo", True):
        urls.append((f"https://www.vagas.com.br/vagas-de-{slug}-em-sao-paulo", "São Paulo"))

    for url, local_hint in urls:
        status, corpo, _ = http.get(url, referer="https://www.vagas.com.br/", origem="vagas")
        if bloqueado(status, corpo):
            log(f"  vagas bloqueou ({status}) {url}")
            return vagas
        if status != 200 or not corpo:
            log(f"  vagas falhou ({status}) {url}")
            continue
        for c in _cards_vagas(corpo):
            if c["url"] in visto:
                continue
            visto.add(c["url"])
            modelo = ""
            loc = c["local"] or local_hint
            if re.search(r"home office|remoto|100%\s*home", loc, re.I):
                modelo = "remoto"
            vagas.append(
                item(
                    fonte="vagas",
                    url=c["url"],
                    autor=c["empresa"],
                    data=c["data"],
                    titulo=c["titulo"],
                    empresa=c["empresa"],
                    local=loc,
                    modelo=modelo,
                    nivel=c["nivel"],
                    descricao=c["descricao"],
                )
            )
    return vagas



def _cards_nerdin(html_pagina: str) -> list[dict[str, str]]:
    encontrados: list[dict[str, str]] = []
    for m in re.finditer(
        r'<div class="vaga-card"([^>]*)>([\s\S]*?)(?=<div class="vaga-card"|<footer\b|\Z)',
        html_pagina,
    ):
        attrs, corpo = m.group(1), m.group(2)
        corpo = re.split(r'<nav\b|id="paginacao"|class="pagination"', corpo, maxsplit=1)[0]
        hm = re.search(r'data-href="([^"]+)"', attrs + " " + corpo)
        if not hm:
            hm = re.search(
                r'href="((?:https://www\.nerdin\.com\.br/)?vaga_emprego/[^"]+)"',
                corpo,
            )
        if not hm:
            continue
        href = html.unescape(hm.group(1))
        if href.startswith("vaga_emprego/"):
            url = "https://www.nerdin.com.br/" + href
        elif href.startswith("/"):
            url = "https://www.nerdin.com.br" + href
        else:
            url = href
        tm = re.search(r'<h3 class="vaga-titulo">([\s\S]*?)</h3>', corpo)
        titulo = strip_tags(tm.group(1) if tm else "")
        titulo = re.sub(r"\s*Nova\s*$", "", titulo).strip()
        rm = re.search(r'<p class="vaga-resumo-linha">([\s\S]*?)</p>', corpo)
        resumo = strip_tags(rm.group(1) if rm else "")
        sm = re.search(r'<div class="vaga-salario-destaque"[\s\S]*?</div>', corpo)
        salario = strip_tags(sm.group(0) if sm else "")
        em = re.search(r'class="vaga-empresa-nome"[^>]*>([\s\S]*?)</span>', corpo)
        empresa = strip_tags(em.group(1) if em else "")
        lm = re.search(r'<div class="vaga-local-linha"[\s\S]*?</div>', corpo)
        local = strip_tags(lm.group(0) if lm else "")
        data = ""
        dm = re.search(r'<time[^>]*datetime="([^"]+)"', corpo)
        if dm:
            data = iso_de_nerdin(html.unescape(dm.group(1)))
        mm = re.search(r'<p class="vaga-meta-extra">([\s\S]*?)</p>', corpo)
        meta = strip_tags(mm.group(1) if mm else "")
        tags = [
            strip_tags(t)
            for t in re.findall(r'class="hashtag"[^>]*>([\s\S]*?)</a>', corpo)
        ]
        nivel = ""
        modelo = ""
        for parte in [p.strip() for p in resumo.split("•") if p.strip()]:
            baixo = parte.lower()
            if re.search(r"home office|remoto|h[ií]brido|presencial", baixo):
                modelo = parte
            elif re.search(
                r"j[uú]nior|junior|pleno|s[eê]nior|senior|est[aá]gio|estagio|trainee|todos",
                baixo,
            ):
                nivel = parte
        if not modelo and re.search(r"home office|remoto", local, re.I):
            modelo = "remoto"
        desc_bits = [x for x in (resumo, meta, " ".join(tags)) if x]
        encontrados.append(
            {
                "url": url,
                "titulo": titulo,
                "empresa": empresa,
                "local": local,
                "salario": salario,
                "nivel": nivel,
                "modelo": modelo,
                "data": data,
                "descricao": " | ".join(desc_bits),
            }
        )
    return encontrados


def _urls_nerdin(keyword: str, cfg: dict[str, Any]) -> list[str]:
    """Monta buscas públicas em vagas.php. Não mistura remoto com busca_local=SP
    (a combinação zera o resultado, porque vagas home office não usam UF)."""
    filtro = cfg.get("filtro_local") or {}
    remoto = bool(filtro.get("remoto", True))
    sp = bool(filtro.get("sao_paulo", True))
    modos: list[dict[str, str]] = []
    if remoto:
        modos.append({"filtro_home_office": "1"})
    if sp:
        modos.append({"busca_local": "SP"})
    if not modos:
        modos.append({})
    buscas: list[dict[str, str]] = [{"busca": keyword}]
    # Plataforma= é mais preciso para stacks cadastradas (ex.: python).
    # Termos que não existem no catálogo só devolvem 0 cards.
    if keyword.strip() and " " not in keyword.strip():
        buscas.append({"Plataforma": keyword.strip()})
    urls: list[str] = []
    vistos: set[str] = set()
    for busca in buscas:
        for modo in modos:
            params = {**busca, **modo}
            url = "https://www.nerdin.com.br/vagas.php?" + urllib.parse.urlencode(params)
            if url not in vistos:
                vistos.add(url)
                urls.append(url)
    return urls


def coletar_nerdin(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """HTML público de https://www.nerdin.com.br/vagas.php, sem login."""
    vagas: list[dict[str, str]] = []
    visto: set[str] = set()
    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    for base in _urls_nerdin(keyword, cfg):
        for pagina in range(1, max_paginas + 1):
            url = base if pagina == 1 else f"{base}&pagina={pagina}"
            status, corpo, _ = http.get(
                url,
                referer="https://www.nerdin.com.br/vagas.php",
                origem="nerdin",
            )
            if bloqueado(status, corpo):
                log(f"  nerdin bloqueou ({status}) {url}")
                return vagas
            if status != 200 or not corpo:
                log(f"  nerdin falhou ({status}) {url}")
                break
            cards = _cards_nerdin(corpo)
            if not cards:
                break
            novos = 0
            for c in cards:
                if not c["url"] or c["url"] in visto:
                    continue
                visto.add(c["url"])
                novos += 1
                modelo = c["modelo"]
                if not modelo and "filtro_home_office=1" in url:
                    modelo = "remoto"
                local = c["local"]
                if not local and "busca_local=SP" in url:
                    local = "SP"
                vagas.append(
                    item(
                        fonte="nerdin",
                        url=c["url"],
                        autor=c["empresa"],
                        data=c["data"],
                        titulo=c["titulo"],
                        empresa=c["empresa"],
                        local=local,
                        modelo=modelo,
                        nivel=c["nivel"],
                        salario=c["salario"],
                        descricao=c["descricao"],
                    )
                )
            if novos == 0:
                break
    return vagas


# ---------------------------------------------------------------------------
# Fontes novas (18/11/2026): backend-br, Programathor, Remotar
# ---------------------------------------------------------------------------

_CACHE: dict[str, Any] = {}
_SENIOR_RE = re.compile(
    r"\b(s[eê]nior|senior|sr\.?|especialista|staff|principal|tech lead|"
    r"engineering manager|gerente|diretor|head of|\bhead\b|manager)\b",
    re.I,
)


def _nivel_inicial(texto: str) -> bool:
    return bool(
        re.search(
            r"\b(j[uú]nior|junior|pleno|est[aá]gio|trainee|early career|entry[- ]level|jr\.?)\b",
            _norm(texto),
        )
    )


def _parece_senior(titulo: str, nivel: str = "") -> bool:
    """Sênior/gestão, exceto quando o próprio anúncio marca júnior/pleno/trainee."""
    # Tech lead / gestão quase nunca é júnior, mesmo com etiqueta "Pleno".
    if re.search(r"\b(tech lead|engineering manager|gerente|diretor|head of|manager|lead)\b", titulo, re.I):
        return True
    if _nivel_inicial(f"{titulo} {nivel}"):
        # Ainda descarta se o título também diz sênior (vaga encoberta).
        return bool(re.search(r"\b(s[eê]nior|senior|sr\.?|especialista|staff|principal)\b", titulo, re.I))
    return bool(_SENIOR_RE.search(titulo) or _SENIOR_RE.search(nivel))


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _casa_keyword(keyword: str, texto: str) -> bool:
    """Casa a palavra-chave como palavra inteira (evita 'ia' casar com 'experiência')."""
    kw = _norm(keyword).strip()
    if not kw:
        return True
    alvo = _norm(texto)
    if kw in {"ia", "ai"}:
        return re.search(r"(?<![a-z0-9])(ia|ai|inteligencia artificial)(?![a-z0-9])", alvo) is not None
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", alvo) is not None


def _passa_local(modelo: str = "", local: str = "", extra: str = "") -> bool:
    """Mantém remoto, São Paulo, ou vaga sem local/modelo informado."""
    t = _norm(f"{modelo} {local} {extra}")
    if any(s in t for s in ("remot", "home office", "anywhere", "worldwide")):
        return True
    if "sao paulo" in t or re.search(r"\bsp\b", t):
        return True
    if not _norm(local) and not _norm(modelo):
        return True
    return False


def _secao_md(corpo: str, *titulos: str) -> str:
    if not corpo or not titulos:
        return ""
    nomes = "|".join(re.escape(t) for t in titulos)
    m = re.search(
        rf"^\#{{1,3}}\s*(?:{nomes})\s*$\n+(.+?)(?=^\#{{1,3}}\s|\Z)",
        corpo,
        flags=re.I | re.M | re.S,
    )
    return m.group(1).strip() if m else ""


def _empresa_backendbr(titulo: str) -> str:
    m = re.search(r"\b(?:na|no|at)\s+(.+)$", titulo, re.I)
    if m:
        return m.group(1).strip(" -–|")
    m = re.match(r"\[[^\]]+\]\s*(.+)$", titulo)
    if not m:
        return ""
    partes = re.split(r"\s+[-–]\s+", m.group(1))
    if len(partes) < 2:
        return ""
    cand = partes[-1].strip()
    if len(cand) > 60 or _SENIOR_RE.search(cand):
        return ""
    if re.search(r"j[uú]nior|pleno|est[aá]gio|trainee", cand, re.I):
        return ""
    return cand


def _issues_backendbr(http: ClienteHTTP, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if "backendbr" in _CACHE:
        return _CACHE["backendbr"]
    issues: list[dict[str, Any]] = []
    paginas = max(1, int(cfg.get("backendbr_paginas", 1)))
    for pagina in range(1, paginas + 1):
        url = (
            "https://api.github.com/repos/backend-br/vagas/issues?"
            + urllib.parse.urlencode({"state": "open", "per_page": "100", "page": str(pagina)})
        )
        status, corpo, _ = http.get(
            url,
            accept="application/vnd.github+json",
            origem="backendbr",
            extra_headers=cabecalhos_github(),
        )
        if status != 200 or not corpo:
            aviso = (
                "limite autenticado da API do GitHub"
                if token_github()
                else "limite sem token é 60 req/h"
            )
            log(f"  backendbr falhou ({status}) {url} — {aviso}")
            break
        try:
            lote = json.loads(corpo)
        except json.JSONDecodeError:
            log("  backendbr: resposta não é JSON")
            break
        if not isinstance(lote, list):
            log("  backendbr: formato inesperado")
            break
        issues.extend(i for i in lote if isinstance(i, dict) and "pull_request" not in i)
        if len(lote) < 100:
            break
    _CACHE["backendbr"] = issues
    return issues


def coletar_backendbr(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """Issues abertas de github.com/backend-br/vagas (API pública do GitHub).

    Baixa uma vez por execução (até 100 issues por página) e filtra localmente
    por palavra-chave. Sem GITHUB_TOKEN o limite é 60 req/h; com token, o
    limite autenticado. O token nunca é enviado a outros sites.
    """
    vagas: list[dict[str, str]] = []
    for i in _issues_backendbr(http, cfg):
        labels = [
            l.get("name", "") if isinstance(l, dict) else str(l)
            for l in i.get("labels") or []
        ]
        nlabels = {_norm(l) for l in labels}
        if nlabels & {"senior", "especialista"}:
            continue
        titulo = (i.get("title") or "").strip()
        corpo = i.get("body") or ""
        if not _casa_keyword(keyword, f"{titulo} {' '.join(labels)} {corpo}"):
            continue
        nivel = ", ".join(
            l for l in labels if _norm(l) in {"junior", "pleno", "estagio", "trainee"}
        )
        if _parece_senior(titulo, nivel):
            continue
        if "remoto" in nlabels or "remote" in nlabels:
            modelo = "remoto"
        elif "hibrido" in nlabels:
            modelo = "híbrido"
        elif "presencial" in nlabels:
            modelo = "presencial"
        else:
            modelo = ""
        colchete = re.match(r"\[([^\]]+)\]", titulo)
        if not modelo and colchete:
            c = _norm(colchete.group(1))
            if "remot" in c:
                modelo = "remoto"
            elif "hibrid" in c:
                modelo = "híbrido"
            elif "presencial" in c:
                modelo = "presencial"
        local = compactar(
            _secao_md(corpo, "Localização", "Location", "Local"), limite=200
        )
        if not local and colchete and modelo not in {"remoto", "híbrido", "presencial"}:
            local = colchete.group(1).strip()
        if not _passa_local(modelo, local, titulo):
            continue
        empresa = _empresa_backendbr(titulo)
        contrato = ", ".join(l for l in labels if _norm(l) in {"clt", "pj", "contrato"})
        salario = compactar(
            _secao_md(corpo, "Faixa salarial", "Salary range", "Salário"), limite=200
        )
        vagas.append(
            item(
                fonte="backendbr",
                url=i.get("html_url") or "",
                autor=empresa or (i.get("user") or {}).get("login", ""),
                data=iso_de_gupy(i.get("created_at")),
                titulo=titulo,
                empresa=empresa,
                local=local,
                modelo=" ".join(p for p in (modelo, contrato) if p),
                nivel=nivel,
                salario=salario,
                descricao=corpo,
            )
        )
    return vagas


def _cards_programathor(html_pagina: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for bloco in re.split(r'<div class="cell-list\s*">', html_pagina)[1:]:
        m = re.search(r'href="(/jobs/\d+-[^"]+)"', bloco)
        if not m:
            continue
        # Evita cortar em cell-list-content (prefixo "cell-list").
        bloco = re.split(r'<div class="(?:cell-list\s*"|pagination)', bloco)[0]
        titulo_m = re.search(r"<h3[^>]*>(.*?)</h3>", bloco, re.S)
        titulo = strip_tags(titulo_m.group(1) if titulo_m else "")
        if not titulo:
            slug = re.sub(r"^\d+-", "", m.group(1).rsplit("/", 1)[-1]).replace("-", " ")
            titulo = slug
        icones: dict[str, str] = {}
        icon_div = re.search(
            r"class=['\"]cell-list-content-icon['\"][^>]*>(.*?)</div>", bloco, re.S
        )
        if icon_div:
            for raw in re.findall(r"<span[^>]*>(.*?)</span>", icon_div.group(1), re.S):
                txt = strip_tags(raw)
                if not txt:
                    continue
                if "fa-briefcase" in raw:
                    icones["empresa"] = txt
                elif "fa-map-marker" in raw:
                    icones["local"] = txt
                elif "fa-chart-bar" in raw:
                    icones["nivel"] = txt
                elif "fa-file-alt" in raw:
                    icones["contrato"] = txt
                elif "fa-money" in raw or "fa-dollar" in raw:
                    icones["salario"] = txt
        empresa_m = re.search(r"alt=\"([^\"]+)\"|alt='([^']+)'|alt=([^\s>]+)", bloco)
        # O <span> da maleta costuma ter o nome completo; alt às vezes vem sem aspas.
        if icones.get("empresa"):
            empresa = icones["empresa"]
        elif empresa_m:
            empresa = html.unescape(next(g for g in empresa_m.groups() if g))
        else:
            empresa = ""
        skills = [
            strip_tags(s)
            for s in re.findall(r"class=['\"]tag-list[^'\"]*['\"][^>]*>(.*?)</span>", bloco, re.S)
        ]
        cards.append(
            {
                "url": "https://programathor.com.br" + m.group(1),
                "titulo": titulo,
                "empresa": empresa,
                "local": icones.get("local", ""),
                "nivel": icones.get("nivel", ""),
                "contrato": icones.get("contrato", ""),
                "salario": icones.get("salario", ""),
                "skills": [s for s in skills if s],
                "texto": strip_tags(bloco),
            }
        )
    return cards


def _pagina_programathor(url: str, pagina: int) -> str:
    if pagina <= 1:
        return url
    if "?" in url:
        base, qs = url.split("?", 1)
        return f"{base.rstrip('/')}/page/{pagina}?{qs}"
    return f"{url.rstrip('/')}/page/{pagina}"


def _lista_programathor(http: ClienteHTTP, cfg: dict[str, Any]) -> list[dict[str, str]]:
    if "programathor" in _CACHE:
        return _CACHE["programathor"]
    urls = cfg.get("programathor_urls") or [
        "https://programathor.com.br/jobs?expertise=J%C3%BAnior",
        "https://programathor.com.br/jobs-city/remoto?expertise=Pleno",
        "https://programathor.com.br/jobs-python",
        "https://programathor.com.br/jobs-city/sao-paulo?expertise=J%C3%BAnior",
    ]
    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    vistos: dict[str, dict[str, str]] = {}
    for base in urls:
        for pagina in range(1, max_paginas + 1):
            url = _pagina_programathor(base, pagina)
            status, corpo, _ = http.get(
                url, referer="https://programathor.com.br/jobs", origem="programathor"
            )
            if bloqueado(status, corpo):
                log(
                    f"  programathor bloqueou ({status}) {url} "
                    "— o site responde 429 se receber vários pedidos seguidos"
                )
                _CACHE["programathor"] = list(vistos.values())
                return _CACHE["programathor"]
            if status != 200 or not corpo:
                log(f"  programathor falhou ({status}) {url}")
                break
            cards = _cards_programathor(corpo)
            if not cards:
                break
            novos = 0
            for c in cards:
                if c["url"] not in vistos:
                    vistos[c["url"]] = c
                    novos += 1
            if novos == 0:
                break
    _CACHE["programathor"] = list(vistos.values())
    log(f"  programathor: {len(vistos)} cards na listagem (antes do filtro de palavra-chave)")
    return _CACHE["programathor"]


def coletar_programathor(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """HTML público do Programathor (Rails).

    ?search= e ?q= são ignorados pelo site; a busca útil é por slug
    (/jobs-python) ou filtro (expertise, jobs-city/remoto). Baixamos poucas
    listagens uma vez e filtramos localmente por palavra-chave.
    """
    vagas: list[dict[str, str]] = []
    for c in _lista_programathor(http, cfg):
        nivel_n = _norm(c["nivel"])
        titulo = c["titulo"]
        if nivel_n in {"senior"} or _parece_senior(titulo, c["nivel"] + " " + c["url"]):
            continue
        hay = " ".join([titulo, c["empresa"], c["local"], c["nivel"], " ".join(c["skills"]), c["url"].replace("-", " ")])
        if not _casa_keyword(keyword, hay):
            continue
        modelo = "remoto" if "remot" in _norm(c["local"]) else ""
        if not _passa_local(modelo, c["local"], titulo):
            continue
        contrato = c["contrato"]
        vagas.append(
            item(
                fonte="programathor",
                url=c["url"],
                autor=c["empresa"],
                titulo=titulo,
                empresa=c["empresa"],
                local=c["local"],
                modelo=" ".join(p for p in (modelo, contrato) if p),
                nivel=c["nivel"],
                salario=c["salario"],
                descricao=c["texto"],
            )
        )
    return vagas


def coletar_remotar(http: ClienteHTTP, cfg: dict[str, Any], keyword: str) -> list[dict[str, str]]:
    """API JSON pública do site: https://api.remotar.com.br/jobs?search=..."""
    vagas: list[dict[str, str]] = []
    max_paginas = max(1, int(cfg.get("max_paginas", 1)))
    limite = int(cfg.get("max_por_busca", 40))
    for pagina in range(1, max_paginas + 1):
        url = "https://api.remotar.com.br/jobs?" + urllib.parse.urlencode(
            {"search": keyword, "page": str(pagina)}
        )
        status, corpo, _ = http.get(
            url,
            accept="application/json",
            referer="https://remotar.com.br/",
            origem="remotar",
        )
        if status != 200 or not corpo:
            log(f"  remotar falhou ({status}) {url}")
            break
        try:
            dados = json.loads(corpo)
        except json.JSONDecodeError:
            log("  remotar: resposta não é JSON")
            break
        rows = dados.get("data") or []
        for r in rows:
            if r.get("expired") or r.get("active") is False:
                continue
            tags = [
                ((t.get("tag") or {}).get("name") or "").strip()
                for t in r.get("jobTags") or []
            ]
            tags_n = " ".join(_norm(t) for t in tags)
            titulo = (r.get("title") or "").strip()
            if "senior" in tags_n or "especialista" in tags_n:
                continue
            if _parece_senior(titulo, " ".join(tags)):
                continue
            # Só título/tags/categoria: a descrição da API cita "IA" com frequência
            # e a busca ?search= é ampla demais (devolve vagas sem relação).
            hay = " ".join(
                [
                    titulo,
                    r.get("subtitle") or "",
                    " ".join(tags),
                    " ".join(
                        ((c.get("category") or {}).get("name") or "")
                        for c in r.get("jobCategories") or []
                    ),
                ]
            )
            if not _casa_keyword(keyword, hay):
                continue
            tipo = r.get("type") or ""
            local = ", ".join(p for p in (r.get("city") or "", r.get("state") or "") if p)
            modelo = {"remote": "remoto", "hybrid": "híbrido", "onsite": "presencial"}.get(
                tipo, tipo
            )
            if not _passa_local(modelo, local, " ".join(tags)):
                continue
            cats = [
                ((c.get("category") or {}).get("name") or "")
                for c in r.get("jobCategories") or []
            ]
            nivel = ", ".join(
                t for t in tags if re.search(r"j[uú]nior|pleno|est[aá]gio|trainee", t, re.I)
            )
            sal = r.get("jobSalary") or {}
            salario = ""
            if sal.get("from") or sal.get("to"):
                lo, hi = (sal.get("from") or 0) / 100, (sal.get("to") or 0) / 100
                faixa = f"{lo:.0f}–{hi:.0f}" if lo and hi else f"{lo or hi:.0f}"
                salario = f"{sal.get('currency') or ''} {faixa} {sal.get('type') or ''}".strip()
            empresa = r.get("companyDisplayName") or (r.get("company") or {}).get("name") or ""
            vagas.append(
                item(
                    fonte="remotar",
                    url=f"https://remotar.com.br/job/{r.get('id')}",
                    autor=empresa,
                    data=iso_de_gupy(r.get("createdAt")),
                    titulo=titulo,
                    empresa=empresa,
                    local=local or "remoto",
                    modelo=modelo,
                    nivel=nivel,
                    salario=salario,
                    descricao=(
                        f"Tags: {', '.join(t for t in tags if t)}. "
                        f"Categorias: {', '.join(c for c in cats if c)}. "
                        + ((r.get("subtitle") or "").strip() + ". " if r.get("subtitle") else "")
                        + (r.get("description") or "")
                    ),
                )
            )
            if len(vagas) >= limite:
                return vagas
        per = int((dados.get("meta") or {}).get("per_page") or 50)
        if len(rows) < per:
            break
    return vagas


COLETORES = {
    "gupy": coletar_gupy,
    "himalayas": coletar_himalayas,
    "infojobs": coletar_infojobs,
    "catho": coletar_catho,
    "vagas": coletar_vagas,
    "nerdin": coletar_nerdin,
    "backendbr": coletar_backendbr,
    "programathor": coletar_programathor,
    "remotar": coletar_remotar,
}


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def deduplicar(vagas: list[dict[str, str]]) -> list[dict[str, str]]:
    saida: list[dict[str, str]] = []
    visto_url: set[str] = set()
    visto_txt: set[str] = set()
    for v in vagas:
        url = (v.get("url") or "").split("?")[0].rstrip("/")
        chave = url.lower() if url else re.sub(r"\s+", " ", (v.get("texto") or "").lower())
        if not chave or chave in visto_url or chave in visto_txt:
            continue
        if url:
            visto_url.add(chave)
        else:
            visto_txt.add(chave)
        saida.append(v)
    return saida


def coletar(cfg: dict[str, Any]) -> dict[str, Any]:
    carregar_dotenv()
    if token_github() and "backendbr" in [f.lower() for f in (cfg.get("fontes") or [])]:
        log("backendbr: GITHUB_TOKEN presente (o valor não é exibido)")
    keywords = cfg.get("keywords") or []
    fontes = [f.lower() for f in (cfg.get("fontes") or [])]
    desconhecidas = [f for f in fontes if f not in COLETORES]
    if desconhecidas:
        log(f"Fontes ignoradas (sem coletor HTTP): {', '.join(desconhecidas)}")
    fontes = [f for f in fontes if f in COLETORES]
    http = ClienteHTTP(
        user_agent=cfg.get("user_agent") or "Mozilla/5.0",
        timeout=int(cfg.get("timeout_segundos", 25)),
        atraso=float(cfg.get("atraso_segundos", 1.2)),
    )
    por_fonte: dict[str, int] = {f: 0 for f in fontes}
    todas: list[dict[str, str]] = []

    for fonte in fontes:
        fn = COLETORES[fonte]
        log(f"== {fonte} ==")
        for kw in keywords:
            log(f"  palavra-chave: {kw}")
            try:
                lote = fn(http, cfg, kw)
            except Exception as exc:  # noqa: BLE001
                log(f"  erro em {fonte}/{kw}: {exc}")
                http.erros.append({"url": "", "status": 0, "origem": fonte, "detalhe": str(exc)})
                lote = []
            por_fonte[fonte] += len(lote)
            todas.extend(lote)
            log(f"    +{len(lote)} (acumulado bruto {len(todas)})")

    unicas = deduplicar(todas)
    resumo = {
        "coletado_em": agora_iso(),
        "keywords": keywords,
        "fontes": fontes,
        "requisicoes": http.requisicoes,
        "brutas": len(todas),
        "unicas": len(unicas),
        "por_fonte_bruto": por_fonte,
        "erros": http.erros,
    }
    return {"resumo": resumo, "vagas": unicas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coletor de vagas (HTTP, sem login).")
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="JSON de configuração. Padrão: config.json nesta pasta, ou config.example.json.",
    )
    parser.add_argument("-o", "--saida", default=None, help="Arquivo JSON de saída")
    parser.add_argument(
        "--fontes",
        default=None,
        help="Lista separada por vírgula (ex.: gupy,himalayas). Sobrescreve o config.",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Lista separada por vírgula. Sobrescreve o config.",
    )
    args = parser.parse_args(argv)

    cfg_path = resolver_config(args.config)
    if not cfg_path.is_file():
        log(
            f"Config não encontrado: {cfg_path}. "
            "Copie config.example.json para config.json ou passe -c."
        )
        return 2
    if cfg_path.name == "config.example.json":
        log("Usando config.example.json (copie para config.json para personalizar sem versionar).")
    cfg = carregar_config(cfg_path)
    if args.fontes:
        cfg["fontes"] = [s.strip() for s in args.fontes.split(",") if s.strip()]
    if args.keywords:
        cfg["keywords"] = [s.strip() for s in args.keywords.split(",") if s.strip()]

    saida = Path(args.saida or cfg.get("saida") or "vagas_coletadas.json")
    if not saida.is_absolute():
        saida = DIR / saida

    resultado = coletar(cfg)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    r = resultado["resumo"]
    print(
        f"Coletadas {r['unicas']} vagas únicas "
        f"(brutas {r['brutas']}) em {r['requisicoes']} requisições."
    )
    print("Por fonte (bruto): " + ", ".join(f"{k}={v}" for k, v in r["por_fonte_bruto"].items()))
    if r["erros"]:
        print(f"Avisos/erros HTTP: {len(r['erros'])} (detalhes no JSON de saída, campo resumo.erros)")
    print(f"Saída: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
