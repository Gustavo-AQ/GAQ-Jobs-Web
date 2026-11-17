from datetime import date
from app.main import job_clauses


def test_filters_with_parameters():
    sql, params = job_clauses("Python", "REMOTO", "CLT", 80, date(2026,1,1), None, "new")
    assert ":termo" in sql
    assert params["termo"] == "%Python%"
    assert params["modelo"] == "REMOTO"
    assert params["aderencia_min"] == 80
    assert "NAO_AVALIADA" in sql


def test_empty_filters():
    sql, params = job_clauses("", None, None, None, None, None, "all")
    assert sql == "" and params == {}
