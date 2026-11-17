"""GAQ Jobs Web API: login local e acesso restrito ao schema empregos."""
import re
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.security import (
    csrf_for_session, new_session_token, session_hash, verify_csrf, verify_password
)

app = FastAPI(title="GAQ Jobs Web", docs_url=None, redoc_url=None, openapi_url=None)

Status = Literal[
    "NAO_AVALIADA", "INTERESSE", "DESCARTADA", "INSCRITO", "EM_PROCESSO",
    "ENTREVISTA", "TESTE_TECNICO", "OFERTA", "REPROVADO", "CONTRATADO",
]
Model = Literal["REMOTO", "HIBRIDO", "PRESENCIAL", "NAO_INFORMADO"]
Category = Literal["all", "new", "applied"]
Sort = Literal["recent", "oldest", "score", "cargo"]


class LoginPayload(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    senha: str = Field(min_length=1, max_length=1024)


class UpdatePayload(BaseModel):
    status_candidatura: Status | None = None
    observacoes: str | None = Field(default=None, max_length=5000)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        if request.headers.get("origin", "").rstrip("/") != settings()["app_origin"]:
            return JSONResponse({"detail": "Origem nao permitida"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def current_user(request: Request):
    raw = request.cookies.get(settings()["cookie_name"], "")
    if not (32 <= len(raw) <= 256):
        raise HTTPException(401, "Sessao ausente")
    with engine().connect() as conn:
        row = conn.execute(text("""
            SELECT u.id,u.email,u.papel FROM empregos.web_sessoes s
            JOIN empregos.web_usuarios u ON u.id=s.usuario_id
            WHERE s.token_hash=:hash AND s.revogada_em IS NULL
            AND s.expira_em>now() AND u.ativo
        """), {"hash": session_hash(raw)}).mappings().first()
    if row is None:
        raise HTTPException(401, "Sessao expirada")
    return {**dict(row), "_token": raw}


def admin_with_csrf(request: Request, user=Depends(current_user)):
    if user["papel"] != "ADMIN":
        raise HTTPException(403, "Acesso restrito")
    csrf = request.headers.get("x-csrf-token", "")
    if not verify_csrf(user["_token"], settings()["session_secret"], csrf):
        raise HTTPException(403, "CSRF invalido")
    return user


@app.get("/healthz")
def healthz():
    with engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}


@app.post("/api/v1/auth/login")
def login(body: LoginPayload):
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "E-mail invalido")
    token = None
    user = None
    with engine().begin() as conn:
        failed = conn.execute(text("""
            SELECT count(*) FROM empregos.web_login_tentativas
            WHERE email=:email AND criado_em>now()-interval '15 minutes'
        """), {"email": email}).scalar_one()
        if failed < 8:
            user = conn.execute(text("""
                SELECT id,email,senha_hash,papel,ativo FROM empregos.web_usuarios
                WHERE lower(email)=:email
            """), {"email": email}).mappings().first()
            correct = verify_password(user["senha_hash"] if user else None, body.senha)
            if user is not None and correct and user["ativo"]:
                token = new_session_token()
                conn.execute(text("""
                    INSERT INTO empregos.web_sessoes(usuario_id,token_hash,expira_em)
                    VALUES(:id,:hash,now()+(:hours * interval '1 hour'))
                """), {"id": user["id"], "hash": session_hash(token),
                       "hours": settings()["session_hours"]})
                conn.execute(text("""
                    UPDATE empregos.web_usuarios SET ultimo_login_em=now() WHERE id=:id
                """), {"id": user["id"]})
                conn.execute(text("""
                    DELETE FROM empregos.web_login_tentativas WHERE email=:email
                """), {"email": email})
            else:
                conn.execute(text("""
                    INSERT INTO empregos.web_login_tentativas(email) VALUES(:email)
                """), {"email": email})
    if token is None:
        raise HTTPException(429 if failed >= 8 else 401, "Credenciais invalidas ou conta bloqueada")
    result = JSONResponse({
        "usuario": {"id": user["id"], "email": user["email"], "papel": user["papel"]},
        "csrf_token": csrf_for_session(token, settings()["session_secret"])
    })
    result.set_cookie(
        settings()["cookie_name"], token, httponly=True,
        secure=settings()["cookie_secure"], samesite="strict",
        path="/", max_age=settings()["session_hours"] * 3600
    )
    return result


@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):
    return {
        "usuario": {"id": user["id"], "email": user["email"], "papel": user["papel"]},
        "csrf_token": csrf_for_session(user["_token"], settings()["session_secret"])
    }


@app.post("/api/v1/auth/logout")
def logout(request: Request, user=Depends(current_user)):
    if not verify_csrf(user["_token"], settings()["session_secret"], request.headers.get("x-csrf-token", "")):
        raise HTTPException(403, "CSRF invalido")
    with engine().begin() as conn:
        conn.execute(text("""
            UPDATE empregos.web_sessoes SET revogada_em=now()
            WHERE token_hash=:hash AND revogada_em IS NULL
        """), {"hash": session_hash(user["_token"])})
    response = JSONResponse({"ok": True})
    response.delete_cookie(settings()["cookie_name"], path="/")
    return response


@app.get("/api/v1/resumo")
def resumo(user=Depends(current_user)):
    with engine().connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) AS total,
              count(*) FILTER(WHERE status_candidatura='NAO_AVALIADA') AS para_avaliar,
              count(*) FILTER(WHERE status_candidatura IN (
                'INSCRITO','EM_PROCESSO','ENTREVISTA','TESTE_TECNICO',
                'OFERTA','REPROVADO','CONTRATADO')) AS inscricoes,
              count(*) FILTER(WHERE status_candidatura='ENTREVISTA') AS entrevistas
            FROM empregos.vagas
        """)).mappings().one()
    return dict(row)


def job_clauses(termo, modelo, contrato, aderencia_min, inicio, fim, categoria):
    clauses, params = [], {}
    if termo:
        clauses.append("(cargo ILIKE :termo OR empresa ILIKE :termo OR fonte ILIKE :termo OR coalesce(habilidades_pedidas,'') ILIKE :termo OR coalesce(descricao,'') ILIKE :termo)")
        params["termo"] = "%" + termo + "%"
    if modelo:
        clauses.append("modelo=:modelo")
        params["modelo"] = modelo
    if contrato:
        clauses.append("upper(tipo_contrato)=:contrato")
        params["contrato"] = contrato.upper()
    if aderencia_min is not None:
        clauses.append("aderencia>=:aderencia_min")
        params["aderencia_min"] = aderencia_min
    if inicio:
        clauses.append("timezone('America/Sao_Paulo',primeira_coleta)::date>=:inicio")
        params["inicio"] = inicio
    if fim:
        clauses.append("timezone('America/Sao_Paulo',primeira_coleta)::date<=:fim")
        params["fim"] = fim
    if categoria == "new":
        clauses.append("status_candidatura IN ('NAO_AVALIADA','INTERESSE')")
    if categoria == "applied":
        clauses.append("status_candidatura IN ('INSCRITO','EM_PROCESSO','ENTREVISTA','TESTE_TECNICO','OFERTA','REPROVADO','CONTRATADO')")
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


@app.get("/api/v1/vagas")
def vagas(
    termo: str = Query("", max_length=150),
    modelo: Model | None = None,
    contrato: str | None = Query(None, max_length=40),
    aderencia_min: int | None = Query(None, ge=0, le=100),
    inicio: date | None = None, fim: date | None = None,
    categoria: Category = "all", ordenar: Sort = "recent",
    limite: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    user=Depends(current_user),
):
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "Data inicial maior que a final")
    where, params = job_clauses(termo.strip(), modelo, contrato, aderencia_min, inicio, fim, categoria)
    ordering = {
        "recent": "primeira_coleta DESC,id DESC",
        "oldest": "primeira_coleta ASC,id ASC",
        "score": "aderencia DESC NULLS LAST,primeira_coleta DESC,id DESC",
        "cargo": "cargo ASC,id ASC"
    }[ordenar]
    with engine().connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM empregos.vagas " + where), params).scalar_one()
        rows = conn.execute(text("""
            SELECT id,fonte,id_externo,empresa,cargo,nivel,modelo,cidade,uf,pais,
                tipo_contrato,salario_min,salario_max,moeda,aderencia,score_prefiltro,
                habilidades_pedidas,status_notificacao,status_candidatura,
                status_disponibilidade,primeira_coleta,data_publicacao,url
            FROM empregos.vagas
        """ + where + " ORDER BY " + ordering + " LIMIT :limite OFFSET :offset"),
            {**params, "limite": limite, "offset": offset}).mappings().all()
    return jsonable_encoder({"total": total, "limite": limite, "offset": offset,
                             "vagas": [dict(row) for row in rows]})


@app.get("/api/v1/vagas/{vaga_id}")
def detalhes(vaga_id: int, user=Depends(current_user)):
    with engine().connect() as conn:
        row = conn.execute(text("SELECT * FROM empregos.vagas WHERE id=:id"),
                           {"id": vaga_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Vaga nao encontrada")
    return jsonable_encoder(dict(row))


@app.get("/api/v1/vagas/{vaga_id}/historico")
def historico(vaga_id: int, user=Depends(current_user)):
    with engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT id,vaga_id,tipo,status_anterior,status_novo,alterado_em,
                alterado_por,observacao
            FROM empregos.vagas_status_hist
            WHERE vaga_id=:id ORDER BY alterado_em DESC,id DESC LIMIT 100
        """), {"id": vaga_id}).mappings().all()
    return jsonable_encoder({"historico": [dict(r) for r in rows]})


@app.patch("/api/v1/vagas/{vaga_id}")
def atualizar(vaga_id: int, body: UpdatePayload, user=Depends(admin_with_csrf)):
    if body.status_candidatura is None and body.observacoes is None:
        raise HTTPException(422, "Informe status_candidatura ou observacoes")
    with engine().begin() as conn:
        old = conn.execute(text("""
            SELECT status_candidatura FROM empregos.vagas WHERE id=:id FOR UPDATE
        """), {"id": vaga_id}).mappings().first()
        if old is None:
            raise HTTPException(404, "Vaga nao encontrada")
        if body.status_candidatura and body.status_candidatura != old["status_candidatura"]:
            conn.execute(text("SELECT set_config('empregos.actor',:actor,true)"),
                         {"actor": "gaq_jobs_web:" + user["email"][:150]})
            conn.execute(text("SELECT set_config('empregos.obs',:obs,true)"),
                         {"obs": "Atualizacao manual no painel web"})
            conn.execute(text("""
                UPDATE empregos.vagas SET status_candidatura=:status,
                    data_status=now(),
                    data_inscricao=CASE WHEN :status='INSCRITO'
                        THEN coalesce(data_inscricao,now()) ELSE data_inscricao END,
                    atualizado_em=now()
                WHERE id=:id
            """), {"status": body.status_candidatura, "id": vaga_id})
        if body.observacoes is not None:
            conn.execute(text("""
                UPDATE empregos.vagas SET observacoes=:notes,atualizado_em=now()
                WHERE id=:id
            """), {"notes": body.observacoes, "id": vaga_id})
    return detalhes(vaga_id, user=user)
