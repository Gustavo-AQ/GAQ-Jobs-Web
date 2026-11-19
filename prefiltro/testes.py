#!/usr/bin/env python3
"""Testa os filtros eliminatórios ligados e desligados, usando exemplos.json."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import prefiltro as pf

DIR = Path(__file__).resolve().parent
EXEMPLOS = DIR / "exemplos.json"
# O config versionado é o exemplo. config.json local (gitignored) não entra no teste,
# para o CI passar sem perfil pessoal.
CONFIG = DIR / "config.example.json"

# Com o config de exemplo (filtros ligados: espanhol obrigatório, noturno,
# término depois das 19:00, presencial/híbrido em qualquer cidade de SP).
MANTER_COM_FILTROS = {
    "https://exemplo.local/vagas/python-ia-junior-remoto",
    "https://exemplo.local/vagas/backend-pleno-inicial-sp",
    "https://exemplo.local/vagas/rpa-junior-remoto",
    "https://exemplo.local/vagas/python-junior-remoto-espanhol-diferencial",
    "https://exemplo.local/vagas/python-junior-remoto-ate-18h",
    "https://exemplo.local/vagas/python-junior-remoto-horario-a-combinar",
    "https://exemplo.local/vagas/python-junior-hibrido-campinas",
    "https://exemplo.local/vagas/python-junior-presencial-sem-cidade",
    "https://exemplo.local/vagas/python-junior-hibrido-estuda-noturno",
}

DESCARTAR_POR = {
    "https://exemplo.local/vagas/python-junior-remoto-espanhol-obrigatorio": "idioma_obrigatorio",
    "https://exemplo.local/vagas/python-junior-remoto-turno-noturno": "horario_eliminatorio",
    "https://exemplo.local/vagas/python-junior-remoto-ate-20h": "horario_eliminatorio",
    "https://exemplo.local/vagas/python-junior-curitiba": "local_fora_sp",
}

DESCARTAR_OUTROS = {
    "https://exemplo.local/posts/open-to-work": "nao_e_vaga",
    "https://exemplo.local/vagas/senior-tech-lead": "nivel_senior",
    "https://exemplo.local/vagas/trainee-dados-1500": "salario_abaixo_piso",
    "https://exemplo.local/cursos/python-ia": "curso/anuncio",
    "https://exemplo.local/vagas/vendedor-junior-sp": "score_baixo",
}


def _por_url(posts: list[dict]) -> dict[str, dict]:
    return {p["url"]: p for p in posts if p.get("url")}


def _motivo(post: dict, cfg: dict, min_score: float) -> str | None:
    """Aplica as regras a um único post e devolve o motivo de descarte, ou None se mantido."""
    mantidos, contagem = pf.filtrar([post], cfg, min_score, set())
    if mantidos:
        return None
    # Sem o post de duplicata ao lado, a 2ª cópia da vaga Python IA não cai
    # por duplicata — por isso este helper é para posts isolados.
    for chave, n in contagem.items():
        if chave in {"total", "mantidos"} or not n:
            continue
        return chave
    return "descarte_desconhecido"


def _urls_mantidas(posts: list[dict], cfg: dict, min_score: float) -> set[str]:
    mantidos, _ = pf.filtrar(posts, cfg, min_score, set())
    return {p.get("url") for p in mantidos if p.get("url")}


def _cfg_desligado(cfg: dict, **overrides) -> dict:
    novo = copy.deepcopy(cfg)
    novo.update(overrides)
    return novo


def main() -> int:
    cfg = pf.carregar_config(CONFIG)
    posts = pf.carregar_json_ou_texto(EXEMPLOS)
    min_score = float(cfg.get("min_score", 40))
    falhas: list[str] = []

    def checar(condicao: bool, msg: str) -> None:
        if not condicao:
            falhas.append(msg)
            print(f"FALHOU: {msg}")
        else:
            print(f"OK: {msg}")

    # --- config de execução: campos presentes e no valor combinado ---
    checar(cfg.get("idiomas_eliminatorios") == ["espanhol"], "config idiomas = [espanhol]")
    checar(cfg.get("horarios_eliminatorios") == ["noturno"], "config horarios = [noturno]")
    checar(cfg.get("horario_limite_fim") == "19:00", "config horario_limite_fim = 19:00")
    checar(
        cfg.get("local_presencial") == {"uf": "SP", "cidades": []},
        "config local_presencial = UF SP, cidades vazia",
    )

    # --- com filtros ligados ---
    mantidas = _urls_mantidas(posts, cfg, min_score)
    for url in MANTER_COM_FILTROS:
        checar(url in mantidas, f"ligado: manter {url.rsplit('/', 1)[-1]}")
    # A duplicata proposital some no pipeline completo.
    checar(
        sum(1 for p in posts if p.get("url") == "https://exemplo.local/vagas/python-ia-junior-remoto") == 2,
        "exemplos incluem a duplicata proposital",
    )

    por_url = _por_url(posts)
    for url, motivo in {**DESCARTAR_POR, **DESCARTAR_OUTROS}.items():
        got = _motivo(por_url[url], cfg, min_score)
        checar(got == motivo, f"ligado: {url.rsplit('/', 1)[-1]} descartar por {motivo} (obtido: {got})")

    # --- cada filtro desligado: o caso correspondente passa a ser mantido ---
    cfg_sem_idioma = _cfg_desligado(cfg, idiomas_eliminatorios=[])
    checar(
        "https://exemplo.local/vagas/python-junior-remoto-espanhol-obrigatorio"
        in _urls_mantidas(posts, cfg_sem_idioma, min_score),
        "idioma desligado: espanhol obrigatório é mantido",
    )
    # O diferencial continua mantido.
    checar(
        "https://exemplo.local/vagas/python-junior-remoto-espanhol-diferencial"
        in _urls_mantidas(posts, cfg_sem_idioma, min_score),
        "idioma desligado: espanhol diferencial continua mantido",
    )

    cfg_sem_horario = _cfg_desligado(
        cfg, horarios_eliminatorios=[], horario_limite_fim=None
    )
    for slug in (
        "python-junior-remoto-turno-noturno",
        "python-junior-remoto-ate-20h",
    ):
        url = f"https://exemplo.local/vagas/{slug}"
        checar(
            url in _urls_mantidas(posts, cfg_sem_horario, min_score),
            f"horário desligado: {slug} é mantido",
        )

    # Só o limite de término desligado: turno noturno ainda elimina; 20h passa.
    cfg_sem_limite = _cfg_desligado(cfg, horario_limite_fim="")
    checar(
        "https://exemplo.local/vagas/python-junior-remoto-ate-20h"
        in _urls_mantidas(posts, cfg_sem_limite, min_score),
        "só limite desligado: término 20h é mantido",
    )
    checar(
        _motivo(por_url["https://exemplo.local/vagas/python-junior-remoto-turno-noturno"], cfg_sem_limite, min_score)
        == "horario_eliminatorio",
        "só limite desligado: turno noturno ainda elimina",
    )

    cfg_sem_local = _cfg_desligado(cfg, local_presencial=None)
    checar(
        "https://exemplo.local/vagas/python-junior-curitiba"
        in _urls_mantidas(posts, cfg_sem_local, min_score),
        "local desligado: híbrido em Curitiba é mantido",
    )
    for loc in ({}, {"uf": ""}, {"uf": None, "cidades": ["São Paulo"]}):
        cfg_l = _cfg_desligado(cfg, local_presencial=loc)
        checar(
            "https://exemplo.local/vagas/python-junior-curitiba"
            in _urls_mantidas(posts, cfg_l, min_score),
            f"local desligado ({loc!r}): Curitiba é mantido",
        )

    # cidades preenchida: Campinas (interior) sai; capital e remoto ficam.
    cfg_capital = _cfg_desligado(cfg, local_presencial={"uf": "SP", "cidades": ["São Paulo"]})
    checar(
        "https://exemplo.local/vagas/python-junior-hibrido-campinas"
        not in _urls_mantidas(posts, cfg_capital, min_score),
        "cidades=[São Paulo]: híbrido em Campinas é descartado",
    )
    checar(
        _motivo(por_url["https://exemplo.local/vagas/python-junior-hibrido-campinas"], cfg_capital, min_score)
        == "local_fora_sp",
        "cidades=[São Paulo]: Campinas cai no filtro de local",
    )
    checar(
        "https://exemplo.local/vagas/backend-pleno-inicial-sp"
        in _urls_mantidas(posts, cfg_capital, min_score),
        "cidades=[São Paulo]: híbrido na capital é mantido",
    )
    checar(
        "https://exemplo.local/vagas/python-junior-presencial-sem-cidade"
        in _urls_mantidas(posts, cfg_capital, min_score),
        "cidades=[São Paulo]: presencial sem cidade não é eliminado",
    )
    checar(
        "https://exemplo.local/vagas/python-ia-junior-remoto"
        in _urls_mantidas(posts, cfg_capital, min_score),
        "cidades=[São Paulo]: remoto continua passando",
    )

    # --- casos unitários extras (texto isolado) ---
    casos_idioma = [
        ("idioma espanhol e ingles sao desejaveis. requisitos: python, fastapi.", False),
        ("requisitos: espanhol. diferenciais: ingles. python junior remoto.", True),
        ("localization content manager, spanish (latin america and spain). python.", False),
        ("required: fluent spanish. python junior remoto, fastapi.", True),
        ("spanish is a plus. python junior remoto, fastapi.", False),
    ]
    for texto, esperado in casos_idioma:
        got = pf.descarte_por_idioma(pf.normalizar(texto), cfg)
        checar(got is esperado, f"idioma unitário esperado={esperado} got={got}: {texto[:60]}")

    casos_hora = [
        ("horario de trabalho das 13h as 19h. python fastapi.", False),
        ("12x36 das 10h as 22h. python fastapi.", True),
        ("entrevista as 20h. python junior remoto fastapi.", False),
        ("expediente ate 20h. python fastapi junior remoto.", True),
        ("sem expediente noturno. python fastapi junior remoto.", False),
    ]
    for texto, esperado in casos_hora:
        got = pf.descarte_por_horario(pf.normalizar(texto), cfg)
        checar(got is esperado, f"horário unitário esperado={esperado} got={got}: {texto[:60]}")

    if falhas:
        print(f"\n{len(falhas)} falha(s).")
        return 1
    print(f"\nTodos os testes passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
