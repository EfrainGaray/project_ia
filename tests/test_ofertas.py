import sqlite3

from asistente import ofertas
from asistente.ofertas import FalloFuente


def oferta(**changes):
    base = {"fuente": "bci", "id_origen": "1", "empresa": "Bci", "cargo": "Analista de datos",
            "ubicacion": "Santiago", "fecha_publicacion": "2026-11-20",
            "enlace": "https://trabajaenbci.cl/offers/proceso/1", "descripcion": "Requisitos\nPython."}
    return {**base, **changes}


def filas(db):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM ofertas ORDER BY fuente, id_origen")]


def test_reimport_keeps_one_row_description_and_first_detection(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta()], momento="2026-11-20T10:00:00+00:00")
    total = ofertas.guardar(db, [oferta(cargo="Analista de datos senior", descripcion=None)],
                            momento="2026-11-24T10:00:00+00:00")
    [row] = filas(db)
    assert total == 1
    assert row["cargo"] == "Analista de datos senior"
    assert row["descripcion"] == "Requisitos\nPython."
    assert row["estado"] == ofertas.COMPLETA
    assert row["fecha_deteccion"] == "2026-11-20T10:00:00+00:00"
    assert row["fecha_actualizacion"] == "2026-11-24T10:00:00+00:00"


def test_reimport_updates_description_when_new_one_arrives(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta(descripcion=None)])
    assert filas(db)[0]["estado"] == ofertas.PENDIENTE
    ofertas.guardar(db, [oferta(descripcion="Requisitos\nSQL.")])
    assert filas(db)[0]["descripcion"] == "Requisitos\nSQL."
    assert filas(db)[0]["estado"] == ofertas.COMPLETA


def test_same_id_in_another_source_is_another_row(tmp_path):
    db = tmp_path / "t.sqlite3"
    assert ofertas.guardar(db, [oferta(), oferta(fuente="itau")]) == 2


def test_missing_publication_date_stays_empty_and_is_not_the_detection_date(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta(fecha_publicacion=None)], momento="2026-11-24T10:00:00+00:00")
    [row] = filas(db)
    assert row["fecha_publicacion"] is None
    assert row["fecha_deteccion"] == "2026-11-24T10:00:00+00:00"


def test_reimport_without_publication_date_keeps_the_known_one(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta()])
    ofertas.guardar(db, [oferta(fecha_publicacion=None)])
    assert filas(db)[0]["fecha_publicacion"] == "2026-11-20"


def test_blank_description_is_pending(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta(descripcion="   ")])
    assert filas(db)[0]["estado"] == "pendiente de descripción"
    assert filas(db)[0]["descripcion"] is None


def test_failing_source_is_recorded_and_other_sources_keep_working(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, [oferta(id_origen="viejo")])

    def rota():
        raise FalloFuente("Bci devolvió HTTP 403 (Forbidden).", "https://trabajaenbci.cl/x", 403)

    def sana():
        return [oferta(fuente="itau", id_origen="9")], []

    resumen = ofertas.importar_fuentes(db, {"bci": rota, "itau": sana})
    assert resumen["bci"]["ofertas"] == 0 and resumen["itau"]["ofertas"] == 1
    assert {(r["fuente"], r["id_origen"]) for r in filas(db)} == {("bci", "viejo"), ("itau", "9")}
    with sqlite3.connect(db) as conn:
        [fallo] = conn.execute("SELECT fuente, url, codigo_http, motivo FROM fallos").fetchall()
    assert fallo[:3] == ("bci", "https://trabajaenbci.cl/x", 403)
    assert "403" in fallo[3]


def test_partial_failures_are_recorded_and_offers_saved(tmp_path):
    db = tmp_path / "t.sqlite3"
    parcial = FalloFuente("HTTP 404", "https://trabajaenbci.cl/api/v3/bci_portals/proceso/1", 404)
    resumen = ofertas.importar_fuentes(db, {"bci": lambda: ([oferta(descripcion=None)], [parcial])})
    assert resumen["bci"] == {"ofertas": 1, "fallos": ["HTTP 404"]}
    assert filas(db)[0]["estado"] == ofertas.PENDIENTE


def test_leer_oferta_returns_none_when_missing(tmp_path):
    assert ofertas.leer_oferta(tmp_path / "t.sqlite3", "bci", "404") is None
