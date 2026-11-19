#!/usr/bin/env python3
"""Pré-filtro barato de posts de vaga, antes de o assistente de IA ler o texto.

Uso:
    python3 prefiltro.py entrada.json -o saida.json [--min-score N] [--ja-enviados arquivo]

Sem --config, usa config.json nesta pasta ou, se ele não existir, config.example.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
DIR_SCRIPT = Path(__file__).resolve().parent


def resolver_config(caminho: str | None = None) -> Path:
    """config.json ao lado do script, se existir; senão config.example.json.

    Um caminho explícito é procurado no diretório atual e, em seguida, nesta pasta.
    """
    if caminho:
        informado = Path(caminho)
        if not informado.is_absolute():
            no_cwd = (Path.cwd() / informado).resolve()
            no_script = (DIR_SCRIPT / informado).resolve()
            if no_cwd.is_file():
                return no_cwd
            if no_script.is_file():
                return no_script
            return no_cwd
        return informado
    for nome in ("config.json", "config.example.json"):
        candidato = DIR_SCRIPT / nome
        if candidato.is_file():
            return candidato
    return DIR_SCRIPT / "config.json"

# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def strip_acentos(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def normalizar(texto: str) -> str:
    texto = strip_acentos(texto).lower()
    texto = texto.replace("#", " ")
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def tokens(texto_norm: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", texto_norm))


def hash_texto(texto_norm: str) -> str:
    return hashlib.sha256(texto_norm.encode("utf-8")).hexdigest()


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    uniao = len(a | b)
    return len(a & b) / uniao if uniao else 0.0


def contem_termo(texto_norm: str, termo: str) -> bool:
    """Casa o termo (já normalizado) com limites de palavra."""
    termo = termo.strip()
    if not termo:
        return False
    # Escapa e permite espaços flexíveis entre as palavras do termo.
    partes = [re.escape(p) for p in termo.split() if p]
    if not partes:
        return False
    padrao = r"(?<![a-z0-9])" + r"\s+".join(partes) + r"(?![a-z0-9])"
    return re.search(padrao, texto_norm) is not None


def alguma_ocorre(texto_norm: str, termos: list[str]) -> bool:
    return any(contem_termo(texto_norm, normalizar(t)) for t in termos)


# ---------------------------------------------------------------------------
# Leitura de entrada
# ---------------------------------------------------------------------------

def carregar_json_ou_texto(caminho: Path) -> list[dict]:
    bruto = caminho.read_text(encoding="utf-8")
    sufixo = caminho.suffix.lower()

    if sufixo == ".jsonl":
        posts = []
        for i, linha in enumerate(bruto.splitlines(), start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"JSONL inválido na linha {i} de {caminho}: {exc}") from exc
            posts.append(_como_post(obj, origem=str(caminho), indice=i))
        return posts

    if sufixo == ".json" or _parece_json(bruto):
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            # Pode ser texto simples que começa com '{' por acaso; tenta texto.
            if sufixo == ".json":
                raise SystemExit(f"JSON inválido em {caminho}: {exc}") from exc
            return _posts_texto(bruto, origem=str(caminho))
        return _posts_de_estrutura(dados, origem=str(caminho))

    return _posts_texto(bruto, origem=str(caminho))


def _parece_json(bruto: str) -> bool:
    s = bruto.lstrip()
    return s.startswith("{") or s.startswith("[")


def _posts_de_estrutura(dados, origem: str) -> list[dict]:
    if isinstance(dados, dict):
        if "texto" in dados:
            itens = [dados]
        else:
            for chave in ("posts", "vagas", "items", "data"):
                if isinstance(dados.get(chave), list):
                    itens = dados[chave]
                    break
            else:
                raise SystemExit(
                    f"JSON em {origem} precisa ser uma lista de posts "
                    "ou um objeto com 'texto' / 'posts' / 'vagas'."
                )
    elif isinstance(dados, list):
        itens = dados
    else:
        raise SystemExit(f"JSON em {origem} tem tipo inesperado: {type(dados).__name__}")

    posts = []
    for i, item in enumerate(itens, start=1):
        posts.append(_como_post(item, origem=origem, indice=i))
    return posts


def _como_post(item, origem: str, indice: int) -> dict:
    if isinstance(item, str):
        return {"texto": item, "fonte": origem, "_indice": indice}
    if not isinstance(item, dict):
        raise SystemExit(f"Post #{indice} em {origem} não é um objeto JSON.")
    post = dict(item)
    if "texto" not in post and "text" in post:
        post["texto"] = post["text"]
    post["_indice"] = indice
    return post


def _posts_texto(bruto: str, origem: str) -> list[dict]:
    blocos = re.split(r"\n\s*---\s*\n", bruto.strip())
    posts = []
    for i, bloco in enumerate(blocos, start=1):
        texto = bloco.strip()
        if texto:
            posts.append({"texto": texto, "fonte": origem, "_indice": i})
    return posts


def carregar_ja_enviados(caminho: Path) -> set[str]:
    bruto = caminho.read_text(encoding="utf-8").strip()
    urls: set[str] = set()
    if not bruto:
        return urls
    if caminho.suffix.lower() == ".json" or bruto[:1] in "{[":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError:
            dados = None
        if dados is not None:
            if isinstance(dados, dict):
                for chave in ("urls", "ja_enviados", "enviados", "items", "vagas", "posts"):
                    if chave in dados:
                        dados = dados[chave]
                        break
            if isinstance(dados, list):
                for item in dados:
                    if isinstance(item, str) and item.strip():
                        urls.add(item.strip())
                    elif isinstance(item, dict):
                        url = item.get("url") or item.get("link")
                        if url:
                            urls.add(str(url).strip())
                return urls
    for linha in bruto.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            urls.add(linha)
    return urls


# ---------------------------------------------------------------------------
# Salário
# ---------------------------------------------------------------------------

def _br_para_float(num: str) -> float | None:
    num = num.strip()
    if not num:
        return None
    # 1.500,00  |  1.500  |  1500,00  |  1500  |  1,5  |  1.5
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", num):
        num = num.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", num):
        num = num.replace(",", ".")
    elif re.fullmatch(r"\d+\.\d{1,2}", num):
        pass  # já é decimal com ponto
    elif re.fullmatch(r"\d+", num):
        pass
    else:
        return None
    try:
        return float(num)
    except ValueError:
        return None


def _valor_k_ou_mil(numero: str, multiplicador: int) -> float | None:
    base = _br_para_float(numero)
    if base is None:
        return None
    return base * multiplicador


def extrair_salarios(texto: str, texto_norm: str) -> dict | None:
    """Devolve {min, max, texto} em BRL mensal, ou None se nada foi encontrado."""
    achados: list[tuple[int, int, float, str]] = []  # start, end, valor, trecho

    def registrar(match: re.Match, valor: float | None) -> None:
        if valor is None:
            return
        # Ignora valores absurdos para salário mensal em BRL de vaga júnior/pleno.
        if valor < 500 or valor > 80000:
            return
        trecho = match.group(0)
        achados.append((match.start(), match.end(), valor, trecho))

    # R$ 1.500,00 | R$1.500 | R$ 1500 | R$ 1,5 mil | R$ 3k
    padrao_rs = re.compile(
        r"r\$\s*(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d{1,2})?)\s*(k|mil)?",
        re.IGNORECASE,
    )
    for m in padrao_rs.finditer(texto_norm):
        bruto_num, sufixo = m.group(1), (m.group(2) or "").lower()
        if sufixo in {"k", "mil"}:
            registrar(m, _valor_k_ou_mil(bruto_num, 1000))
        else:
            registrar(m, _br_para_float(bruto_num))

    # 1,5k / 1.5k / 3k  (sem R$), só em contexto de remuneração ou faixa curta
    padrao_k = re.compile(
        r"(?<![a-z0-9])(\d{1,2}(?:[.,]\d{1,2})?)\s*k(?![a-z0-9])",
        re.IGNORECASE,
    )
    contexto_salario = re.compile(
        r"(salario|remuneracao|faixa|compensacao|pretensao|clt|pj|mensal|por mes|r\$)"
    )
    tem_contexto = contexto_salario.search(texto_norm) is not None
    for m in padrao_k.finditer(texto_norm):
        # Evita recapturar o que já entrou via R$ 3k
        if any(a <= m.start() < b for a, b, _, _ in achados):
            continue
        if tem_contexto or _vizinho_parece_salario(texto_norm, m.start(), m.end()):
            registrar(m, _valor_k_ou_mil(m.group(1), 1000))

    # 2 mil / 1,8 mil (sem R$)
    padrao_mil = re.compile(
        r"(?<![a-z0-9])(\d{1,2}(?:[.,]\d{1,2})?)\s*mil(?![a-z0-9])",
        re.IGNORECASE,
    )
    for m in padrao_mil.finditer(texto_norm):
        if any(a <= m.start() < b for a, b, _, _ in achados):
            continue
        if tem_contexto or _vizinho_parece_salario(texto_norm, m.start(), m.end()):
            registrar(m, _valor_k_ou_mil(m.group(1), 1000))

    if not achados:
        return None

    achados.sort(key=lambda x: x[0])
    valores = [v for _, _, v, _ in achados]
    vmin = int(round(min(valores)))
    vmax = int(round(max(valores)))

    def _brl(n: int) -> str:
        return f"R$ {n:,}".replace(",", ".")

    texto_fmt = _brl(vmin) if vmin == vmax else f"{_brl(vmin)} a {_brl(vmax)}"
    return {"min": vmin, "max": vmax, "texto": texto_fmt}


def _vizinho_parece_salario(texto_norm: str, ini: int, fim: int) -> bool:
    janela = texto_norm[max(0, ini - 40) : min(len(texto_norm), fim + 40)]
    return bool(
        re.search(
            r"(salario|remuneracao|faixa|clt|pj|mensal|ate|a partir|entre|de\s+\d)",
            janela,
        )
    )


def salario_abaixo_do_piso(salario: dict | None, piso: float) -> bool:
    if not salario:
        return False
    # Descarta só quando o teto da faixa (ou o valor único) fica abaixo do piso.
    return salario["max"] < piso


# ---------------------------------------------------------------------------
# Regras duras e pontuação
# ---------------------------------------------------------------------------

def detectar_nivel(texto_norm: str, cfg: dict) -> str | None:
    aceitaveis = cfg.get("niveis_aceitaveis", {})
    # Ordem: o mais específico primeiro.
    for chave in ("pleno_inicial", "trainee", "estagio", "junior", "pleno"):
        termos = aceitaveis.get(chave, [])
        if alguma_ocorre(texto_norm, termos):
            return chave
    return None


def tem_nivel_senior_sem_aceitavel(texto_norm: str, cfg: dict) -> bool:
    if not alguma_ocorre(texto_norm, cfg.get("niveis_senior", [])):
        return False
    aceitaveis = cfg.get("niveis_aceitaveis", {})
    todos = []
    for termos in aceitaveis.values():
        todos.extend(termos)
    return not alguma_ocorre(texto_norm, todos)


def detectar_modelo(texto_norm: str, cfg: dict) -> list[str]:
    modelos = cfg.get("modelo_trabalho", {})
    achados = []
    for nome in ("remoto", "hibrido", "presencial"):
        if alguma_ocorre(texto_norm, modelos.get(nome, [])):
            achados.append(nome)
    return achados


def _casa_local(texto_norm: str, nomes: list[str], abrev: list[str]) -> bool:
    if alguma_ocorre(texto_norm, nomes):
        return True
    for sigla in abrev:
        # Exige contexto de local para siglas curtas (sp, rj, pr...).
        padrao = rf"(?<![a-z0-9]){re.escape(sigla)}(?![a-z0-9])"
        for m in re.finditer(padrao, texto_norm):
            janela = texto_norm[max(0, m.start() - 28) : min(len(texto_norm), m.end() + 28)]
            if re.search(
                r"\b(em|no|na|de|do|da|para|presencial|hibrido|alocado|"
                r"escritorio|sede|cidade|estado|uf|/|-)\b",
                janela,
            ):
                return True
    return False


def local_em_sp(texto_norm: str, cfg: dict) -> bool:
    return _casa_local(
        texto_norm,
        cfg.get("local_sp", []),
        cfg.get("local_sp_abreviacoes", []),
    )


def local_fora_sp(texto_norm: str, cfg: dict) -> bool:
    return _casa_local(
        texto_norm,
        cfg.get("locais_fora_sp", []),
        cfg.get("locais_fora_sp_abreviacoes", []),
    )


# ---------------------------------------------------------------------------
# Filtros eliminatórios configuráveis (vazios / null = desligados)
# ---------------------------------------------------------------------------

def lista_opcional(valor) -> list[str]:
    """None, vazio ou item em branco vira lista vazia (filtro desligado)."""
    if valor is None or valor is False:
        return []
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list):
        return []
    return [str(v).strip() for v in valor if str(v).strip()]


def politica_local(cfg: dict) -> dict | None:
    """Devolve {uf, cidades} ou None se o filtro de local estiver desligado."""
    loc = cfg.get("local_presencial")
    if not loc or not isinstance(loc, dict):
        return None
    uf = str(loc.get("uf") or "").strip()
    if not uf:
        return None
    return {"uf": _normaliza_uf(uf), "cidades": lista_opcional(loc.get("cidades"))}


def _normaliza_uf(uf: str) -> str:
    u = strip_acentos(uf).upper().strip()
    nomes = {
        "SAO PAULO": "SP",
        "RIO DE JANEIRO": "RJ",
        "MINAS GERAIS": "MG",
        "PARANA": "PR",
        "RIO GRANDE DO SUL": "RS",
        "DISTRITO FEDERAL": "DF",
        "SANTA CATARINA": "SC",
        "PERNAMBUCO": "PE",
        "BAHIA": "BA",
        "CEARA": "CE",
        "AMAZONAS": "AM",
        "PARA": "PA",
        "GOIAS": "GO",
        "ESPIRITO SANTO": "ES",
        "RIO GRANDE DO NORTE": "RN",
        "ALAGOAS": "AL",
        "PARAIBA": "PB",
        "PIAUI": "PI",
        "MATO GROSSO": "MT",
        "MATO GROSSO DO SUL": "MS",
    }
    return nomes.get(u, u)


def minutos_de_horario(valor) -> int | None:
    """Converte '19:00', '19h', '19h30' em minutos desde 00:00. Vazio = None."""
    if valor is None:
        return None
    s = strip_acentos(str(valor)).lower().strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})(?:[:h\.](\d{2}))?(?:\s*h(?:oras?)?)?", s)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    if hh == 24 and mm == 0:
        return 24 * 60
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return hh * 60 + mm
    return None


ALIAS_IDIOMAS = {
    "espanhol": ["espanhol", "spanish", "castellano"],
    "spanish": ["espanhol", "spanish", "castellano"],
    "castellano": ["espanhol", "spanish", "castellano"],
    "ingles": ["ingles", "english"],
    "english": ["ingles", "english"],
    "frances": ["frances", "french"],
    "french": ["frances", "french"],
    "alemao": ["alemao", "german", "deutsch"],
    "german": ["alemao", "german", "deutsch"],
    "italiano": ["italiano", "italian"],
    "italian": ["italiano", "italian"],
    "mandarim": ["mandarim", "chines", "chinese"],
    "chines": ["mandarim", "chines", "chinese"],
    "chinese": ["mandarim", "chines", "chinese"],
}

SINAIS_IDIOMA_OBRIGATORIO = [
    "obrigatorio",
    "obrigatoria",
    "obrigatorios",
    "obrigatorias",
    "required",
    "must have",
    "must-have",
    "necessario",
    "necessaria",
    "imprescindivel",
    "fluente",
    "fluent",
    "nativo",
    "native",
    "avancado",
    "advanced",
    "dominio de",
    "dominio do",
    "dominio da",
    "dominio em",
    "proficiency",
    "proficient",
]

SINAIS_IDIOMA_DIFERENCIAL = [
    "diferencial",
    "diferenciais",
    "desejavel",
    "desejaveis",
    "plus",
    "um plus",
    "sera um plus",
    "e um plus",
    "nice to have",
    "nice-to-have",
    "opcional",
    "preferencial",
    "preferivel",
    "sera um diferencial",
    "e um diferencial",
    "como diferencial",
]

_RE_CABECALHO_SECAO = re.compile(
    r"(requisitos?(?:\s+e\s+qualificacoes)?(?:\s+obrigatorios?)?"
    r"|requirements(?:\s+and\s+qualifications)?"
    r"|qualificacoes(?:\s+obrigatorias)?"
    r"|mandatory(?:\s+requirements)?"
    r"|diferenciais"
    r"|desejaveis"
    r"|nice\s+to\s+have"
    r")\s*[:\-]",
)


def _aliases_idioma(idioma: str) -> list[str]:
    chave = normalizar(idioma)
    return ALIAS_IDIOMAS.get(chave, [chave] if chave else [])


def _mencoes_idioma(texto_norm: str, idioma: str) -> list[re.Match]:
    achados: list[re.Match] = []
    for alias in _aliases_idioma(idioma):
        partes = [re.escape(p) for p in alias.split() if p]
        if not partes:
            continue
        padrao = r"(?<![a-z0-9])" + r"\s+".join(partes) + r"(?![a-z0-9])"
        achados.extend(re.finditer(padrao, texto_norm))
    achados.sort(key=lambda m: m.start())
    return achados


def _zonas_secao(texto_norm: str) -> list[tuple[int, int, str]]:
    """Lista (ini, fim, zona) com zona in {'req', 'plus'}."""
    hits = list(_RE_CABECALHO_SECAO.finditer(texto_norm))
    if not hits:
        return []
    plus_titulos = {"diferenciais", "desejaveis", "nice to have"}
    zonas = []
    for i, m in enumerate(hits):
        titulo = re.sub(r"\s+", " ", m.group(1).strip())
        zona = "plus" if any(p in titulo for p in plus_titulos) else "req"
        fim = hits[i + 1].start() if i + 1 < len(hits) else len(texto_norm)
        zonas.append((m.start(), fim, zona))
    return zonas


def _zona_no_ponto(zonas: list[tuple[int, int, str]], pos: int) -> str | None:
    for ini, fim, zona in zonas:
        if ini <= pos < fim:
            return zona
    return None


def _corte_na_proxima_secao(texto_norm: str, pos: int, zonas: list[tuple[int, int, str]]) -> int:
    proximos = [ini for ini, _, _ in zonas if ini > pos]
    return min(proximos) if proximos else len(texto_norm)


def _qualificador_da_mencao(
    texto_norm: str, m: re.Match, zonas: list[tuple[int, int, str]]
) -> str | None:
    """'plus' ou 'req' se um qualificativo está colado à menção do idioma."""
    limite = min(m.end() + 56, _corte_na_proxima_secao(texto_norm, m.end(), zonas))
    apos = texto_norm[m.end() : limite]
    antes = texto_norm[max(0, m.start() - 40) : m.start()]
    if alguma_ocorre(apos, SINAIS_IDIOMA_DIFERENCIAL) or alguma_ocorre(
        antes[-20:], SINAIS_IDIOMA_DIFERENCIAL
    ):
        return "plus"
    if alguma_ocorre(apos, SINAIS_IDIOMA_OBRIGATORIO) or alguma_ocorre(
        antes, SINAIS_IDIOMA_OBRIGATORIO
    ):
        return "req"
    return None


def idioma_obrigatorio_no_texto(texto_norm: str, idioma: str) -> bool:
    """True só quando o idioma aparece como exigência, não como diferencial."""
    mencoes = _mencoes_idioma(texto_norm, idioma)
    if not mencoes:
        return False
    zonas = _zonas_secao(texto_norm)
    for m in mencoes:
        zona = _zona_no_ponto(zonas, m.start())
        qual = _qualificador_da_mencao(texto_norm, m, zonas)
        # Seção "diferenciais" e "é um plus" na própria menção vencem fluente/avançado.
        if zona == "plus" or qual == "plus":
            continue
        if qual == "req" or zona == "req":
            return True
        ini = max(0, m.start() - 120)
        fim = min(len(texto_norm), _corte_na_proxima_secao(texto_norm, m.end(), zonas))
        janela = texto_norm[ini:fim]
        plus_janela = alguma_ocorre(janela, SINAIS_IDIOMA_DIFERENCIAL)
        req_janela = alguma_ocorre(janela, SINAIS_IDIOMA_OBRIGATORIO)
        if req_janela and not plus_janela:
            return True
    return False


def descarte_por_idioma(texto_norm: str, cfg: dict) -> bool:
    idiomas = lista_opcional(cfg.get("idiomas_eliminatorios"))
    if not idiomas:
        return False
    return any(idioma_obrigatorio_no_texto(texto_norm, idioma) for idioma in idiomas)


_RE_FAIXA_HORARIA = re.compile(
    r"(?:(?:das?|de|entre)\s+)?"
    r"(\d{1,2})(?:[:h\.](\d{2}))?(?:\s*h(?:oras?)?)?"
    r"\s*(?:as|ate|-|–|—|/)\s*"
    r"(\d{1,2})(?:[:h\.](\d{2}))?(?:\s*h(?:oras?)?)?"
)

_RE_TERMINO_JORNADA = re.compile(
    r"(?:horario(?:\s+de\s+trabalho)?|jornada|expediente|turno|carga\s+horaria)"
    r".{0,48}?(?:ate|termino|termina|encerramento|saida)\s+(?:as\s+)?"
    r"(\d{1,2})(?:[:h\.](\d{2}))?(?:\s*h(?:oras?)?)?"
)

SINAIS_CONTEXTO_JORNADA = [
    "horario",
    "jornada",
    "expediente",
    "turno",
    "escala",
    "plantao",
    "carga horaria",
    "horario de trabalho",
    "das",
    "de",
    "entre",
]

SINAIS_ESTUDO_NOTURNO = [
    "estudar no periodo noturno",
    "estudar no noturno",
    "estuda no periodo noturno",
    "estudando no periodo noturno",
    "cursando no periodo noturno",
    "cursar no periodo noturno",
    "faculdade no periodo noturno",
    "faculdade no noturno",
    "curso noturno",
    "ensino noturno",
    "periodo noturno da faculdade",
    "periodo noturno da graduacao",
    "graduacao no periodo noturno",
    "universidade no periodo noturno",
]

SINAIS_TURNO_NOTURNO = [
    "turno noturno",
    "periodo noturno",
    "horario noturno",
    "expediente noturno",
    "jornada noturna",
    "plantao noturno",
    "trabalho noturno",
    "vaga noturna",
    "atuacao noturna",
    "escala noturna",
    "night shift",
    "overnight",
    "shift noturno",
]

SINAIS_NEGACAO_NOTURNO = [
    "nao e noturno",
    "nao eh noturno",
    "nao e um turno noturno",
    "sem turno noturno",
    "sem expediente noturno",
    "nao trabalhamos no periodo noturno",
    "nao ha trabalho noturno",
    "exceto noturno",
    "nao noturno",
]

SINAIS_TURNO_TRABALHO_NOTURNO = [
    "turno noturno",
    "horario noturno",
    "expediente noturno",
    "jornada noturna",
    "plantao noturno",
    "trabalho noturno",
    "vaga noturna",
    "night shift",
    "overnight",
]


def _hora_para_minutos(hh: str, mm: str | None) -> int | None:
    h = int(hh)
    m = int(mm) if mm else 0
    if h == 24 and m == 0:
        return 24 * 60
    if 0 <= h <= 23 and 0 <= m <= 59:
        return h * 60 + m
    return None


def _faixa_tem_marcador_de_hora(trecho: str) -> bool:
    return bool(re.search(r"[:h]|horas?", trecho))


def _contexto_de_jornada(texto_norm: str, ini: int, fim: int) -> bool:
    janela = texto_norm[max(0, ini - 50) : min(len(texto_norm), fim + 30)]
    return alguma_ocorre(janela, SINAIS_CONTEXTO_JORNADA) or bool(
        re.search(r"\b(das|de|entre|as|ate)\b", janela)
    )


def horarios_de_termino(texto_norm: str) -> list[int]:
    """Términos de jornada explicitamente declarados, em minutos desde 00:00."""
    fins: list[int] = []
    for m in _RE_FAIXA_HORARIA.finditer(texto_norm):
        trecho = m.group(0)
        if not _faixa_tem_marcador_de_hora(trecho):
            continue
        ini_min = _hora_para_minutos(m.group(1), m.group(2))
        fim_min = _hora_para_minutos(m.group(3), m.group(4))
        if ini_min is None or fim_min is None:
            continue
        if not _contexto_de_jornada(texto_norm, m.start(), m.end()):
            continue
        fins.append(fim_min)
    for m in _RE_TERMINO_JORNADA.finditer(texto_norm):
        fim_min = _hora_para_minutos(m.group(1), m.group(2))
        if fim_min is not None:
            fins.append(fim_min)
    return fins


def _menciona_turno_noturno(texto_norm: str, termos: list[str]) -> bool:
    ativadores: list[str] = []
    for t in termos:
        nt = normalizar(t)
        if nt in {"noturno", "noturna", "night", "overnight", "madrugada"}:
            ativadores.extend(SINAIS_TURNO_NOTURNO)
            if nt == "madrugada":
                ativadores.append("madrugada")
        elif nt:
            ativadores.append(nt)
    vistos: list[str] = []
    for a in ativadores:
        if a not in vistos:
            vistos.append(a)

    if not alguma_ocorre(texto_norm, vistos):
        return False
    if alguma_ocorre(texto_norm, SINAIS_ESTUDO_NOTURNO):
        # "estudar no período noturno" não é jornada de trabalho.
        if not alguma_ocorre(texto_norm, SINAIS_TURNO_TRABALHO_NOTURNO):
            return False
    if alguma_ocorre(texto_norm, SINAIS_NEGACAO_NOTURNO):
        return False
    return True


def descarte_por_horario(texto_norm: str, cfg: dict) -> bool:
    turnos = lista_opcional(cfg.get("horarios_eliminatorios"))
    limite = minutos_de_horario(cfg.get("horario_limite_fim"))
    if not turnos and limite is None:
        return False
    if turnos and _menciona_turno_noturno(texto_norm, turnos):
        return True
    if limite is None:
        return False
    return any(fim > limite for fim in horarios_de_termino(texto_norm))


CIDADES_POR_UF = {
    "RJ": ["rio de janeiro", "niteroi", "duque de caxias", "nova iguacu"],
    "MG": ["belo horizonte", "uberlandia", "contagem", "juiz de fora"],
    "PR": ["curitiba", "londrina", "maringa"],
    "RS": ["porto alegre", "caxias do sul"],
    "DF": ["brasilia"],
    "SC": ["florianopolis", "joinville", "blumenau"],
    "PE": ["recife"],
    "BA": ["salvador"],
    "CE": ["fortaleza"],
    "AM": ["manaus"],
    "PA": ["belem"],
    "GO": ["goiania"],
    "ES": ["vitoria"],
    "RN": ["natal"],
    "AL": ["maceio"],
    "PB": ["joao pessoa"],
    "PI": ["teresina"],
    "MT": ["cuiaba"],
    "MS": ["campo grande"],
}

TERMOS_ESTADO_SP = {
    "estado de sao paulo",
    "interior de sao paulo",
    "grande sao paulo",
    "regiao metropolitana de sao paulo",
    "rmsp",
}

TERMOS_CAPITAL_SP = {
    "capital paulista",
    "capital de sao paulo",
    "cidade de sao paulo",
    "sao paulo capital",
}


def _cidades_especificas(texto_norm: str, nomes: list[str]) -> list[str]:
    """Cidades nominalmente citadas, excluindo termos genéricos de estado."""
    achadas: list[str] = []
    ordenados = sorted({normalizar(n) for n in nomes if n}, key=len, reverse=True)
    ja: set[str] = set()
    for nome in ordenados:
        if nome in TERMOS_ESTADO_SP:
            continue
        if contem_termo(texto_norm, nome) and nome not in ja:
            achadas.append(nome)
            ja.add(nome)
    return achadas


def _cidades_da_uf(cfg: dict, uf: str) -> list[str]:
    if uf == "SP":
        return list(cfg.get("local_sp") or [])
    return list(CIDADES_POR_UF.get(uf, []))


def _em_uf(texto_norm: str, cfg: dict, uf: str) -> bool:
    if uf == "SP":
        return local_em_sp(texto_norm, cfg)
    nomes = list(CIDADES_POR_UF.get(uf, []))
    return _casa_local(texto_norm, nomes, [uf.lower()])


def _fora_uf(texto_norm: str, cfg: dict, uf: str) -> bool:
    if uf == "SP":
        return local_fora_sp(texto_norm, cfg)
    abrev: list[str] = []
    for sigla in list(cfg.get("locais_fora_sp_abreviacoes") or []) + list(
        cfg.get("local_sp_abreviacoes") or []
    ) + ["sp"]:
        if sigla.lower() != uf.lower() and sigla.lower() not in abrev:
            abrev.append(sigla.lower())
    nomes = list(cfg.get("locais_fora_sp") or []) + list(cfg.get("local_sp") or [])
    permitidas = {normalizar(n) for n in CIDADES_POR_UF.get(uf, [])}
    nomes_fora = [n for n in nomes if normalizar(n) not in permitidas]
    return _casa_local(texto_norm, nomes_fora, abrev)


def _cidade_permitida(nome: str, permitidas: set[str]) -> bool:
    n = normalizar(nome)
    if n in permitidas:
        return True
    if n in TERMOS_CAPITAL_SP and (
        "sao paulo" in permitidas or "capital paulista" in permitidas
    ):
        return True
    return False


def descarte_por_local(texto_norm: str, cfg: dict, modelos: list[str]) -> bool:
    """Presencial/híbrido fora da UF (e, se houver lista, fora das cidades).

    Remoto sempre passa. Sem informação de local, não elimina.
    `cidades` vazia = qualquer cidade da UF. Filtro ausente/vazio = desligado.
    """
    pol = politica_local(cfg)
    if pol is None:
        return False
    if "remoto" in modelos:
        return False

    uf = pol["uf"]
    cidades = pol["cidades"]
    fora = _fora_uf(texto_norm, cfg, uf)
    dentro = _em_uf(texto_norm, cfg, uf)

    if not fora and not dentro:
        return False

    if fora and not dentro:
        if "presencial" in modelos or "hibrido" in modelos or not modelos:
            return True
        return False

    if not cidades:
        return False

    permitidas = {normalizar(c) for c in cidades}
    universo = _cidades_da_uf(cfg, uf) + cidades
    mencionadas = _cidades_especificas(texto_norm, universo)
    outras: list[str] = []
    aceitas: list[str] = []
    for c in mencionadas:
        # "são paulo" isolado é ambíguo (cidade ou estado): só rejeita se
        # claramente for outra cidade da UF; aceita se a capital estiver na lista.
        if _cidade_permitida(c, permitidas):
            aceitas.append(c)
            continue
        if c in {"sao paulo", "s. paulo"} and "sao paulo" not in permitidas:
            continue
        outras.append(c)

    if aceitas:
        return False
    if outras:
        return True
    return False


def eh_nao_vaga(texto_norm: str, cfg: dict) -> str | None:
    regras = cfg.get("nao_e_vaga", {})
    if alguma_ocorre(texto_norm, regras.get("curso", [])):
        return "curso/anuncio"
    if alguma_ocorre(texto_norm, regras.get("candidato", [])):
        # Recrutador ou indicação de vaga que por acaso usa 1ª pessoa.
        if alguma_ocorre(texto_norm, cfg.get("sinais_de_vaga", [])):
            return None
        return "nao_e_vaga"
    return None


def habilidades_encontradas(texto_norm: str, cfg: dict) -> list[dict]:
    achadas = []
    for item in cfg.get("habilidades", []):
        aliases = item.get("aliases") or [item.get("termo", "")]
        if alguma_ocorre(texto_norm, aliases):
            achadas.append(item)
    return achadas


def areas_encontradas(texto_norm: str, cfg: dict) -> tuple[list[str], list[str]]:
    areas = cfg.get("areas", {})
    nucleo, adjacentes = [], []
    for item in areas.get("nucleo", []):
        aliases = item.get("aliases") or [item.get("termo", "")]
        if alguma_ocorre(texto_norm, aliases):
            nucleo.append(item.get("termo", "núcleo"))
    for item in areas.get("adjacentes", []):
        aliases = item.get("aliases") or [item.get("termo", "")]
        if alguma_ocorre(texto_norm, aliases):
            adjacentes.append(item.get("termo", "adjacente"))
    return nucleo, adjacentes


def pontuar(texto_norm: str, cfg: dict, salario: dict | None) -> tuple[int, list[str], dict]:
    pesos = cfg.get("pesos", {})
    p_hab = float(pesos.get("habilidades", 50))
    p_area = float(pesos.get("area", 20))
    p_nivel = float(pesos.get("nivel", 15))
    p_mod = float(pesos.get("modelo_local", 15))
    soma_pesos = p_hab + p_area + p_nivel + p_mod or 100.0

    razoes: list[str] = []

    # --- habilidades (0-100) ---
    skills = habilidades_encontradas(texto_norm, cfg)
    soma_skill = sum(float(s.get("peso", 0)) for s in skills)
    teto = float(cfg.get("habilidades_teto", 30)) or 30.0
    comp_hab = min(100.0, 100.0 * soma_skill / teto)
    if skills:
        nomes = ", ".join(s.get("termo", "?") for s in skills)
        razoes.append(f"habilidades: {nomes}")
    else:
        razoes.append("nenhuma habilidade do perfil encontrada")

    # --- área (0-100) ---
    nucleo, adjacentes = areas_encontradas(texto_norm, cfg)
    if nucleo:
        comp_area = 100.0
        razoes.append("área núcleo: " + ", ".join(nucleo))
    elif adjacentes:
        comp_area = 70.0
        razoes.append("área adjacente: " + ", ".join(adjacentes))
    elif skills:
        # Tem stack do CV, mas o anúncio não nomeou a área.
        comp_area = 45.0
        razoes.append("área não nomeada, mas há overlap de stack")
    else:
        comp_area = 10.0
        razoes.append("área pouco aderente ao perfil")

    # --- nível (0-100) ---
    nivel = detectar_nivel(texto_norm, cfg)
    mapa_nivel = {
        "junior": 100.0,
        "trainee": 100.0,
        "estagio": 90.0,
        "pleno_inicial": 90.0,
        "pleno": 70.0,
    }
    rotulo_nivel = {
        "junior": "júnior",
        "trainee": "trainee",
        "estagio": "estágio",
        "pleno_inicial": "pleno inicial",
        "pleno": "pleno",
    }
    if nivel:
        comp_nivel = mapa_nivel[nivel]
        razoes.append(f"nível: {rotulo_nivel[nivel]}")
    else:
        comp_nivel = 50.0
        razoes.append("nível não informado")

    # --- modelo / local (0-100) ---
    modelos = detectar_modelo(texto_norm, cfg)
    em_sp = local_em_sp(texto_norm, cfg)
    if "remoto" in modelos:
        comp_mod = 100.0
        razoes.append("modelo: remoto")
    elif "hibrido" in modelos and em_sp:
        comp_mod = 70.0
        razoes.append("modelo: híbrido em SP")
    elif "presencial" in modelos and em_sp:
        comp_mod = 50.0
        razoes.append("modelo: presencial em SP")
    elif "hibrido" in modelos:
        comp_mod = 55.0
        razoes.append("modelo: híbrido (local não explicitado)")
    elif "presencial" in modelos:
        comp_mod = 35.0
        razoes.append("modelo: presencial (local não explicitado)")
    elif em_sp:
        comp_mod = 55.0
        razoes.append("local em SP, modelo não informado")
    else:
        comp_mod = 55.0
        razoes.append("modelo/local não informado")

    if salario:
        if salario["min"] == salario["max"]:
            razoes.append(f"salário informado: R$ {salario['min']:,}".replace(",", "."))
        else:
            razoes.append(
                f"faixa salarial: R$ {salario['min']:,} a R$ {salario['max']:,}".replace(",", ".")
            )

    score = (
        p_hab * comp_hab
        + p_area * comp_area
        + p_nivel * comp_nivel
        + p_mod * comp_mod
    ) / soma_pesos
    score_int = int(round(min(100.0, max(0.0, score))))

    detalhe = {
        "nivel_detectado": rotulo_nivel.get(nivel) if nivel else None,
        "modelo_detectado": _rotulo_modelo(modelos),
        "salario_detectado": salario,
        "componentes": {
            "habilidades": round(comp_hab, 1),
            "area": round(comp_area, 1),
            "nivel": round(comp_nivel, 1),
            "modelo_local": round(comp_mod, 1),
        },
    }
    return score_int, razoes, detalhe


def _rotulo_modelo(modelos: list[str]) -> str | None:
    if not modelos:
        return None
    mapa = {"remoto": "remoto", "hibrido": "híbrido", "presencial": "presencial"}
    return " ou ".join(mapa[m] for m in modelos)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def filtrar(posts: list[dict], cfg: dict, min_score: float, ja_enviados: set[str]) -> tuple[list[dict], dict]:
    piso = float(cfg.get("salario_piso", 1800))
    limiar_dup = float(cfg.get("similaridade_duplicata", 0.85))

    contagem = {
        "total": len(posts),
        "sem_texto": 0,
        "ja_enviados": 0,
        "duplicata": 0,
        "nao_e_vaga": 0,
        "curso/anuncio": 0,
        "nivel_senior": 0,
        "idioma_obrigatorio": 0,
        "horario_eliminatorio": 0,
        "local_fora_sp": 0,
        "salario_abaixo_piso": 0,
        "score_baixo": 0,
        "mantidos": 0,
    }

    vistos_url: set[str] = set()
    vistos_hash: set[str] = set()
    vistos_tokens: list[set[str]] = []
    mantidos: list[dict] = []

    for post in posts:
        texto = post.get("texto")
        if not texto or not str(texto).strip():
            contagem["sem_texto"] += 1
            continue

        url = (post.get("url") or post.get("link") or "").strip()
        if url and url in ja_enviados:
            contagem["ja_enviados"] += 1
            continue

        if url and url in vistos_url:
            contagem["duplicata"] += 1
            continue

        texto_norm = normalizar(str(texto))
        h = hash_texto(texto_norm)
        toks = tokens(texto_norm)

        if h in vistos_hash or any(jaccard(toks, ant) >= limiar_dup for ant in vistos_tokens):
            contagem["duplicata"] += 1
            if url:
                vistos_url.add(url)
            continue

        # Marca como visto antes das regras duras, para não reprocessar o mesmo texto.
        vistos_hash.add(h)
        vistos_tokens.append(toks)
        if url:
            vistos_url.add(url)

        motivo_nao_vaga = eh_nao_vaga(texto_norm, cfg)
        if motivo_nao_vaga:
            contagem[motivo_nao_vaga] += 1
            continue

        if tem_nivel_senior_sem_aceitavel(texto_norm, cfg):
            contagem["nivel_senior"] += 1
            continue

        modelos = detectar_modelo(texto_norm, cfg)
        if descarte_por_idioma(texto_norm, cfg):
            contagem["idioma_obrigatorio"] += 1
            continue
        if descarte_por_horario(texto_norm, cfg):
            contagem["horario_eliminatorio"] += 1
            continue
        if descarte_por_local(texto_norm, cfg, modelos):
            contagem["local_fora_sp"] += 1
            continue

        salario = extrair_salarios(str(texto), texto_norm)
        if salario_abaixo_do_piso(salario, piso):
            contagem["salario_abaixo_piso"] += 1
            continue

        score, razoes, detalhe = pontuar(texto_norm, cfg, salario)
        if score < min_score:
            contagem["score_baixo"] += 1
            continue

        saida = {k: v for k, v in post.items() if not k.startswith("_")}
        saida["score"] = score
        saida["razoes"] = razoes
        saida["nivel_detectado"] = detalhe["nivel_detectado"]
        saida["modelo_detectado"] = detalhe["modelo_detectado"]
        saida["salario_detectado"] = detalhe["salario_detectado"]
        saida["componentes"] = detalhe["componentes"]
        mantidos.append(saida)

    mantidos.sort(key=lambda p: p["score"], reverse=True)
    contagem["mantidos"] = len(mantidos)
    return mantidos, contagem


def resumo_stdout(contagem: dict, min_score: float) -> str:
    linhas = [
        f"Pré-filtro: {contagem['total']} post(s) lido(s)",
        "Descartados:",
    ]
    mapa = [
        ("sem_texto", "sem texto"),
        ("ja_enviados", "já enviados"),
        ("duplicata", "duplicata"),
        ("nao_e_vaga", "não é vaga"),
        ("curso/anuncio", "curso/anúncio"),
        ("nivel_senior", "nível sênior"),
        ("idioma_obrigatorio", "idioma obrigatório"),
        ("horario_eliminatorio", "horário eliminatório"),
        ("local_fora_sp", "local presencial não permitido"),
        ("salario_abaixo_piso", "salário abaixo do piso"),
        ("score_baixo", f"score < {min_score:g}"),
    ]
    algum = False
    for chave, rotulo in mapa:
        n = contagem.get(chave, 0)
        if n:
            algum = True
            linhas.append(f"  - {rotulo}: {n}")
    if not algum:
        linhas.append("  - nenhum")
    linhas.append(f"Mantidos: {contagem['mantidos']} (score >= {min_score:g})")
    return "\n".join(linhas)


def carregar_config(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo de configuração não encontrado: {caminho}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config JSON inválido em {caminho}: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pré-filtro de posts de vaga (descarta e pontua antes do assistente de IA)."
    )
    p.add_argument("entrada", help="Arquivo JSON, JSONL ou texto (posts separados por ---)")
    p.add_argument("-o", "--output", required=True, help="JSON de saída com as vagas mantidas")
    p.add_argument("--min-score", type=float, default=None, help="Score mínimo (padrão: config, 40)")
    p.add_argument("--ja-enviados", default=None, help="Arquivo com URLs já enviadas (uma por linha ou JSON)")
    p.add_argument(
        "--config",
        default=None,
        help="Caminho do config. Padrão: config.json nesta pasta, ou config.example.json.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    caminho_cfg = resolver_config(args.config)
    cfg = carregar_config(caminho_cfg)
    min_score = args.min_score if args.min_score is not None else float(cfg.get("min_score", 40))

    entrada = Path(args.entrada)
    if not entrada.is_file():
        print(f"Arquivo de entrada não encontrado: {entrada}", file=sys.stderr)
        return 1

    posts = carregar_json_ou_texto(entrada)
    ja_enviados: set[str] = set()
    if args.ja_enviados:
        caminho_env = Path(args.ja_enviados)
        if not caminho_env.is_file():
            print(f"Arquivo --ja-enviados não encontrado: {caminho_env}", file=sys.stderr)
            return 1
        ja_enviados = carregar_ja_enviados(caminho_env)

    mantidos, contagem = filtrar(posts, cfg, min_score, ja_enviados)

    saida = {
        "gerado_em": datetime.now(TZ).isoformat(timespec="seconds"),
        "min_score": min_score,
        "salario_piso": cfg.get("salario_piso", 1800),
        "filtros_eliminatorios": {
            "idiomas_eliminatorios": lista_opcional(cfg.get("idiomas_eliminatorios")),
            "horarios_eliminatorios": lista_opcional(cfg.get("horarios_eliminatorios")),
            "horario_limite_fim": cfg.get("horario_limite_fim") or None,
            "local_presencial": politica_local(cfg),
        },
        "total_lidos": contagem["total"],
        "total_mantidos": contagem["mantidos"],
        "descartes": {k: v for k, v in contagem.items() if k not in {"total", "mantidos"}},
        "vagas": mantidos,
    }
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(resumo_stdout(contagem, min_score))
    print(f"Saída: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
