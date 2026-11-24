import json
import sqlite3
from pathlib import Path

import pytest

import app

DEMO = Path(app.__file__).resolve().parent / "demo"
OFFER = (DEMO / "oferta.txt").read_text(encoding="utf-8")
PROFILE = json.loads((DEMO / "perfil.json").read_text(encoding="utf-8"))
REFERENCE = json.loads((DEMO / "referencia.json").read_text(encoding="utf-8"))
EVIDENCE = PROFILE["evidencias"]


def row(**changes):
    base = {"requisito": "Python", "cita": "Conocimientos de Python (deseable).", "tipo": "deseable",
            "estado": "respaldado", "evidencia": "python"}
    return {**base, **changes}


def test_reference_analysis_is_valid():
    app.validate(REFERENCE, OFFER, EVIDENCE)


@pytest.mark.parametrize("bad", [
    row(cita="Una frase que no está en el aviso."),
    row(tipo="importante"),
    row(estado="quizás"),
    row(evidencia="inexistente"),
    row(estado="respaldado", evidencia=None),
    row(requisito="  "),
])
def test_validate_rejects_rows_without_valid_quote_or_evidence(bad):
    with pytest.raises(ValueError):
        app.validate([bad], OFFER, EVIDENCE)


def test_validate_rejects_empty_analysis():
    with pytest.raises(ValueError):
        app.validate([], OFFER, EVIDENCE)


def test_reference_recommends_the_data_cv():
    recommendation, scores = app.recommend(REFERENCE, PROFILE["versiones"])
    assert recommendation == "datos"
    assert scores == {"datos": 5, "frontend": 2, "automatizacion": 3}


def test_required_backed_requirement_scores_two_and_desirable_one():
    versions = {"a": {"evidencias": ["python"]}, "b": {"evidencias": ["coordinacion"]}}
    rows = [row(), row(requisito="Coordinación", tipo="obligatorio", evidencia="coordinacion",
                       cita="Habilidades para coordinar iniciativas con distintas áreas de la organización.")]
    assert app.recommend(rows, versions) == ("b", {"a": 1, "b": 2})


def test_tie_at_the_top_gives_no_recommendation():
    versions = {"a": {"evidencias": ["python"]}, "b": {"evidencias": ["python"]}}
    assert app.recommend([row()], versions)[0] is None


def test_no_points_gives_no_recommendation():
    versions = {"a": {"evidencias": ["frontend"]}}
    assert app.recommend([row(estado="por confirmar", evidencia=None)], versions) == (None, {"a": 0})


def test_record_keeps_recommendation_choice_and_pdf_hash(tmp_path):
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 demo")
    db = tmp_path / "test.sqlite3"
    first = app.record(db, "referencia manual", OFFER, REFERENCE, "datos", "frontend", pdf, "prefiero React")
    second = app.record(db, "referencia manual", OFFER, REFERENCE, "datos", "datos", pdf, "")
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id, cv_recomendado, cv_elegido, archivo, length(sha256), motivo FROM decisiones"
        ).fetchall()
    assert [first, second] == [1, 2]
    assert rows[0] == (1, "datos", "frontend", "cv.pdf", 64, "prefiero React")
    assert rows[1][2] == "datos"


def run_app(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["app.py", *argv])
    app.main()


def test_pending_offer_from_db_explains_and_does_not_recommend(tmp_path, monkeypatch, capsys):
    from asistente import ofertas
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [{"fuente": "bci", "id_origen": "7", "empresa": "Bci", "cargo": "Analista",
                          "enlace": "https://trabajaenbci.cl/offers/proceso/7"}])
    with pytest.raises(SystemExit) as exit_info:
        run_app(monkeypatch, "--bd", str(db), "--oferta-bd", "bci:7", "--reglas")
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert "pendiente de descripción" in err


def test_missing_offer_from_db_is_an_error(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run_app(monkeypatch, "--bd", str(tmp_path / "t.sqlite3"), "--oferta-bd", "bci:404", "--reglas")
    assert "No hay una oferta" in capsys.readouterr().err


def test_complete_offer_from_db_reaches_recommendation_and_records_choice(tmp_path, monkeypatch, capsys):
    import json as _json

    from asistente import bci, ofertas
    fixtures = Path(__file__).resolve().parent / "fixtures" / "bci"
    rows, _ = bci.parse_listing(_json.loads((fixtures / "listado.json").read_text(encoding="utf-8")))
    detail = bci.parse_detail(_json.loads((fixtures / "proceso_39410.json").read_text(encoding="utf-8")))
    for row in rows:
        row["descripcion"] = detail if row["id_origen"] == "39410" else None
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, rows)
    run_app(monkeypatch, "--bd", str(db), "--oferta-bd", "bci:39410", "--reglas",
            "--elegir", "datos", "--motivo", "prefiero destacar análisis")
    out = capsys.readouterr().out
    assert "Análisis: reglas" in out and "CV recomendado: automatizacion" in out
    assert "Aviso: Experiencia en desarrollo e implementación de pipelines ETL/ELT" in out
    _, versions = out.split("CV recomendado: automatizacion", 1)
    other_versions, automation = versions.split("automatizacion (2 puntos)", 1)
    assert "Evidencia fuera de este CV · Experiencia en desarrollo" in other_versions
    assert "+2 · Experiencia en desarrollo e implementación de pipelines ETL/ELT" in automation
    assert "Dominio avanzado" not in versions
    with sqlite3.connect(db) as conn:
        query = "SELECT cv_recomendado, cv_elegido, length(sha256) FROM decisiones"
        decision = conn.execute(query).fetchone()
    assert decision == ("automatizacion", "datos", 64)


def test_model_and_rules_together_are_rejected(monkeypatch):
    with pytest.raises(SystemExit):
        run_app(monkeypatch, "--modelo", "x", "--reglas")
