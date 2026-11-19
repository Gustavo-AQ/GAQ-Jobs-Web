#!/usr/bin/env python3
"""Testes locais do coletor, sem rede."""

from __future__ import annotations

import os
from pathlib import Path

import coletor

DIR = Path(__file__).resolve().parent


def main() -> int:
    falhas: list[str] = []

    def checar(condicao: bool, msg: str) -> None:
        if not condicao:
            falhas.append(msg)
            print(f"FALHOU: {msg}")
        else:
            print(f"OK: {msg}")

    checar(coletor.slugify("São Paulo") == "sao-paulo", "slugify remove acento")
    checar(
        coletor.infojobs_termo("desenvolvedor python") == "desenvolvedor+python",
        "termo InfoJobs usa +",
    )

    duplicadas = coletor.deduplicar(
        [
            {"url": "https://exemplo.local/vaga/1?utm=1", "texto": "a", "fonte": "gupy"},
            {"url": "https://exemplo.local/vaga/1", "texto": "a de novo", "fonte": "gupy"},
            {"url": "https://exemplo.local/vaga/2", "texto": "b", "fonte": "remotar"},
        ]
    )
    checar(len(duplicadas) == 2, "deduplicar junta a mesma URL sem query")

    exemplo = DIR / "config.example.json"
    checar(exemplo.is_file(), "config.example.json existe")
    cfg = coletor.carregar_config(exemplo)
    checar("backendbr" in cfg.get("fontes", []), "exemplo inclui backendbr")
    checar(float(cfg.get("atraso_segundos", 0)) >= 1.2, "exemplo atrasa pelo menos 1,2 s")
    checar(coletor.resolver_config(None) == exemplo.resolve(), "sem config.json, usa o exemplo")

    texto_cfg = exemplo.read_text(encoding="utf-8")
    checar("/home/" not in texto_cfg, "exemplo não tem caminho absoluto de home")
    checar("GITHUB_TOKEN" not in texto_cfg, "token não fica no JSON de config")

    os.environ.pop("GITHUB_TOKEN", None)
    checar(coletor.cabecalhos_github() == {}, "sem token, header do GitHub fica vazio")
    os.environ["GITHUB_TOKEN"] = "segredo-de-teste"
    checar(
        coletor.cabecalhos_github() == {"Authorization": "Bearer segredo-de-teste"},
        "token vira Bearer só no helper do GitHub",
    )

    dotenv = DIR / ".env.test-local"
    dotenv.write_text(
        'GITHUB_TOKEN="nao-deve-substituir"\nSESSION_SECRET=nao-carregar\n# comentario\n',
        encoding="utf-8",
    )
    os.environ.pop("SESSION_SECRET", None)
    try:
        coletor.carregar_dotenv(dotenv)
        checar(
            os.environ.get("GITHUB_TOKEN") == "segredo-de-teste",
            "dotenv não sobrescreve GITHUB_TOKEN já definido",
        )
        del os.environ["GITHUB_TOKEN"]
        coletor.carregar_dotenv(dotenv)
        checar(
            os.environ.get("GITHUB_TOKEN") == "nao-deve-substituir",
            "dotenv preenche GITHUB_TOKEN quando o ambiente está vazio",
        )
        checar(
            "SESSION_SECRET" not in os.environ,
            "dotenv do coletor ignora qualquer chave que não seja GITHUB_TOKEN",
        )
        checar(
            "nao-deve-substituir" not in exemplo.read_text(encoding="utf-8"),
            "token de teste não foi parar no config de exemplo",
        )
    finally:
        dotenv.unlink(missing_ok=True)
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ.pop("SESSION_SECRET", None)

    checar("backendbr" in coletor.COLETORES and "remotar" in coletor.COLETORES, "coletores registrados")

    checar(coletor._passa_local("híbrido", "", "[Híbrido] Python Pleno"), "híbrido sem cidade passa")
    checar(coletor._passa_local("presencial", "", "Python júnior presencial"), "presencial sem cidade passa")
    checar(coletor._passa_local("", "", "Python pleno"), "sem modelo e sem local passa")
    checar(coletor._passa_local("", "São Paulo", "Python"), "São Paulo passa")
    checar(coletor._passa_local("remoto", "Curitiba", "Python"), "remoto passa mesmo fora de SP")
    checar(not coletor._passa_local("híbrido", "Curitiba", "Python"), "híbrido em Curitiba sai")
    checar(not coletor._passa_local("presencial", "Rio de Janeiro", "Python"), "presencial no Rio sai")

    issue_sem_local = {
        "title": "[Híbrido] Python Pleno",
        "body": "Vaga de python pleno, sem seção de local.\n",
        "html_url": "https://exemplo.local/issues/hibrido-sem-cidade",
        "labels": [{"name": "Híbrido"}, {"name": "Pleno"}],
        "user": {"login": "exemplo"},
        "created_at": "2026-11-01T12:00:00Z",
    }
    issue_curitiba = {
        "title": "[Presencial] Python Pleno",
        "body": "## Localização\nCuritiba\n",
        "html_url": "https://exemplo.local/issues/presencial-curitiba",
        "labels": [{"name": "Presencial"}, {"name": "Pleno"}],
        "user": {"login": "exemplo"},
        "created_at": "2026-11-01T12:00:00Z",
    }
    coletor._CACHE["backendbr"] = [issue_sem_local, issue_curitiba]
    try:
        vagas_bb = coletor.coletar_backendbr(None, {}, "python")
    finally:
        coletor._CACHE.pop("backendbr", None)
    urls_bb = {v.get("url") for v in vagas_bb}
    checar(
        "https://exemplo.local/issues/hibrido-sem-cidade" in urls_bb,
        "backend-br híbrido sem local é mantido",
    )
    checar(
        "https://exemplo.local/issues/presencial-curitiba" not in urls_bb,
        "backend-br presencial em Curitiba sai",
    )

    if falhas:
        print(f"\n{len(falhas)} falha(s).")
        return 1
    print("\nTodos os testes passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
