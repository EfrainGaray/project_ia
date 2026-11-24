import json
from pathlib import Path

import pytest

import app
from asistente import bci, reglas

ROOT = Path(app.__file__).resolve().parent
PROFILE = json.loads((ROOT / "demo" / "perfil.json").read_text(encoding="utf-8"))
FICHA = json.loads((ROOT / "tests" / "fixtures" / "bci" / "proceso_39410.json").read_text(encoding="utf-8"))
OFFER = "Especialista Procesos y Proyectos Tarjeta\nBci\nhttps://trabajaenbci.cl/offers/proceso/39410\n\n" + \
    bci.parse_detail(FICHA)


def by_evidence(rows):
    return {row["evidencia"]: row for row in rows if row["evidencia"]}


def test_bci_detail_gives_typed_rows_with_literal_quotes_and_a_recommendation():
    rows = reglas.extraer(OFFER, PROFILE)
    app.validate(rows, OFFER, PROFILE["evidencias"])
    found = by_evidence(rows)
    assert found["etl"]["tipo"] == "obligatorio" and found["etl"]["estado"] == "respaldado"
    assert found["etl"]["cita"] == (
        "Experiencia en desarrollo e implementación de pipelines ETL/ELT y conceptos de Data Engineering."
    )
    assert any(r["tipo"] == "deseable" for r in rows)
    assert app.recommend(rows, PROFILE["versiones"])[0] == "automatizacion"


def test_required_level_or_years_keep_the_row_pending_even_with_evidence():
    rows = by_evidence(reglas.extraer(OFFER, PROFILE))
    assert rows["python"]["estado"] == "por confirmar"  # «Dominio avanzado en Python»
    assert rows["datos"]["estado"] == "por confirmar"  # «Experiencia mínima de 2 a 3 años»


def test_description_and_functions_are_not_requirements():
    rows = reglas.extraer(OFFER, PROFILE)
    assert not any(r["cita"].startswith("Liderar") for r in rows)


def test_itau_demo_without_sections_uses_profile_signals():
    offer = (ROOT / "demo" / "oferta.txt").read_text(encoding="utf-8")
    rows = by_evidence(reglas.extraer(offer, PROFILE))
    assert rows["python"]["tipo"] == "deseable" and rows["python"]["estado"] == "respaldado"
    assert rows["sql"]["estado"] == "por confirmar"  # listed in the profile without an example of use


def test_no_requirements_found_is_an_error():
    with pytest.raises(ValueError):
        reglas.extraer("Cargo\nEmpresa\nTexto sin requisitos reconocibles.", PROFILE)
