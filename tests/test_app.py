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
