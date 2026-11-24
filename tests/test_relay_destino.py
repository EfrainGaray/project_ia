from asistente import ofertas
from asistente.relay_destino import guardar_bci, guardar_latam


def test_bci_rows_from_the_browser_become_common_offers(tmp_path):
    db = tmp_path / "t.sqlite3"
    filas = [
        {
            "cargo": "Analista de Datos\n(CÓDIGO s1)",
            "enlace": "http://127.0.0.1:9/bci/offers/proceso/77.html",
            "ubicacion": "Santiago",
            "fecha_publicacion": "21/11/2026",
            "requisitos": "Python.",
            "deseable": "SQL.",
        },
        {
            "cargo": "Sin ficha",
            "enlace": "https://trabajaenbci.cl/offers/proceso/78",
            "_error": "estructura cambió",
        },
        {"cargo": "Sin enlace válido", "enlace": "https://trabajaenbci.cl/otra"},
    ]
    assert guardar_bci(filas, {}, db) == 2
    full = ofertas.leer_oferta(db, "bci", "77")
    assert full is not None
    assert full["cargo"] == "Analista de Datos"
    assert full["enlace"] == "https://trabajaenbci.cl/offers/proceso/77"
    assert full["fecha_publicacion"] == "2026-11-21"
    assert full["descripcion"] == "Requisitos\nPython.\n\nDeseable\nSQL."
    pending = ofertas.leer_oferta(db, "bci", "78")
    assert (
        pending is not None
        and pending["estado"] == ofertas.PENDIENTE
        and pending["fecha_publicacion"] is None
    )


def test_latam_rows_need_link_and_title(tmp_path):
    db = tmp_path / "t.sqlite3"
    filas = [
        {
            "cargo": "Analista",
            "enlace": "https://www.latamairlines.com/empleo/abc-1",
            "descripcion": "Python",
        },
        {"cargo": "", "enlace": "https://www.latamairlines.com/empleo/x"},
    ]
    assert guardar_latam(filas, {}, db) == 1
    row = ofertas.leer_oferta(db, "latam", "abc-1")
    assert row is not None and row["estado"] == ofertas.COMPLETA
