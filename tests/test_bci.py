import io
import json
import sqlite3
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from asistente import bci, ofertas
from asistente.ofertas import FalloFuente

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bci"
LISTADO = json.loads((FIXTURES / "listado.json").read_text(encoding="utf-8"))
FICHA = json.loads((FIXTURES / "proceso_39410.json").read_text(encoding="utf-8"))
ROBOTS_OK = "# User-Agent: *\n# Disallow: /\n"
NOT_FOUND = '{"errors":"Lo sentimos, la oferta no existe o ha expirado"}'


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body.encode())
        self.headers = Message()
        self.headers["Content-Type"] = "application/json; charset=utf-8"


class FakeOpener:
    """Responde con fixtures grabados; nunca toca la red."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def open(self, request, timeout):
        url = request.full_url
        self.calls.append((request.get_method(), url, request.data))
        status, body = self.routes.get(url, (404, NOT_FOUND))
        if status != 200:
            raise HTTPError(url, status, "Not Found" if status == 404 else "Forbidden", Message(),
                            io.BytesIO(body.encode()))
        return Response(body)


def portal(routes):
    opener = FakeOpener({bci.ROBOTS: (200, ROBOTS_OK), **routes})
    return bci.Portal(opener=opener, sleep=lambda _: None), opener


def test_parse_listing_maps_recorded_response_to_the_common_model():
    rows, total = bci.parse_listing(LISTADO)
    assert total == 3
    row = next(r for r in rows if r["id_origen"] == "39410")
    assert row == {
        "fuente": "bci", "id_origen": "39410", "empresa": "Bci",
        "cargo": "Especialista Procesos y Proyectos Tarjeta",
        "ubicacion": row["ubicacion"], "fecha_publicacion": row["fecha_publicacion"],
        "enlace": "https://trabajaenbci.cl/offers/proceso/39410", "descripcion": None,
    }
    assert row["ubicacion"] and "Santiago" in row["ubicacion"]
    assert row["fecha_publicacion"] and row["fecha_publicacion"].startswith("2026-")


def test_parse_listing_does_not_keep_staff_names():
    rows, _ = bci.parse_listing(LISTADO)
    assert all("FICTICIA" not in json.dumps(row) for row in rows)


def test_parse_listing_rejects_other_json():
    with pytest.raises(FalloFuente):
        bci.parse_listing({"errors": "Error 404"})


def test_unparseable_publication_date_stays_empty():
    assert bci.fecha_iso("hace 3 días") is None
    assert bci.fecha_iso("24/11/2026") == "2026-11-24"


def test_parse_detail_keeps_requirements_and_desirable_sections():
    text = bci.parse_detail(FICHA)
    assert "\nRequisitos\n" in text and "\nDeseable\n" in text
    assert "Dominio avanzado en Python, SQL, PySpark" in text
    assert "<li>" not in text and "﻿" not in text


def test_parse_detail_without_description_fails():
    with pytest.raises(FalloFuente):
        bci.parse_detail({"title": "Solo título", "desirable_knowledge": None})


def test_listing_and_detail_end_to_end_into_sqlite(tmp_path):
    p, opener = portal({
        bci.SEARCH: (200, json.dumps(LISTADO)),
        bci.DETAIL.format("39410"): (200, json.dumps(FICHA)),
    })
    found, partial = bci.leer(p, paginas=2, detalles=3)
    # Listing first; then three details: 39410 answers, the other two were not recorded and answer 404.
    assert len(found) == 3 and len(partial) == 2
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, found)
    row = ofertas.leer_oferta(db, "bci", "39410")
    assert row is not None and row["estado"] == ofertas.COMPLETA and "Requisitos" in row["descripcion"]
    methods = [c[0] for c in opener.calls]
    assert methods[:2] == ["GET", "POST"]  # robots.txt before anything else
    assert json.loads(opener.calls[1][2]) == {"size": bci.POR_PAGINA, "from": 0}


def test_missing_detail_leaves_offer_pending_and_records_404(tmp_path):
    p, opener = portal({bci.SEARCH: (200, json.dumps(LISTADO))})
    db = tmp_path / "t.sqlite3"
    resumen = ofertas.importar_fuentes(db, {"bci": lambda: bci.leer(p, detalles=1)})
    assert resumen["bci"]["ofertas"] == 3
    with sqlite3.connect(db) as conn:
        estados = {r[0] for r in conn.execute("SELECT estado FROM ofertas")}
        [fallo] = conn.execute("SELECT codigo_http, url, motivo FROM fallos").fetchall()
    assert estados == {"pendiente de descripción"}
    assert fallo[0] == 404 and "/proceso/" in fallo[1] and "no existe o ha expirado" in fallo[2]


def test_refused_listing_records_code_and_reason_and_keeps_previous_rows(tmp_path):
    db = tmp_path / "t.sqlite3"
    ofertas.guardar(db, bci.parse_listing(LISTADO)[0])
    p, opener = portal({bci.SEARCH: (403, '{"errors":"Acceso denegado"}')})
    resumen = ofertas.importar_fuentes(db, {"bci": lambda: bci.leer(p, detalles=3)})
    assert resumen["bci"]["ofertas"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0] == 3
        [fallo] = conn.execute("SELECT fuente, codigo_http, motivo FROM fallos").fetchall()
    assert fallo[:2] == ("bci", 403) and "Acceso denegado" in fallo[2]
    assert len(opener.calls) == 2  # robots + listing; no details after a refusal


def test_robots_disallow_stops_before_any_request():
    opener = FakeOpener({bci.ROBOTS: (200, "User-agent: *\nDisallow: /api/\n")})
    p = bci.Portal(opener=opener, sleep=lambda _: None)
    with pytest.raises(FalloFuente, match="robots.txt"):
        bci.leer(p)
    assert len(opener.calls) == 1


def test_rate_limit_waits_at_least_one_second_or_crawl_delay():
    waits: list[float] = []
    routes = {bci.ROBOTS: (200, "User-agent: *\nCrawl-delay: 4\n"), bci.SEARCH: (200, json.dumps(LISTADO))}
    p = bci.Portal(opener=FakeOpener(routes), sleep=waits.append)
    bci.leer(p)
    assert waits == [4.0]
    assert bci.Portal(opener=FakeOpener({bci.ROBOTS: (200, ROBOTS_OK)}), sleep=waits.append).delay == 1.0


def test_html_instead_of_json_is_a_visible_failure():
    p, opener = portal({bci.SEARCH: (200, "<!doctype html><html></html>")})
    with pytest.raises(FalloFuente, match="no es JSON"):
        bci.leer(p)


@pytest.mark.parametrize("url", [
    "https://trabajaenbci.cl/api/v3/users/sessions/login",
    "http://trabajaenbci.cl/api/v3/bci_portals/_search",
    "https://otro.cl/api/v3/bci_portals/_search",
    "https://trabajaenbci.cl/api/v3/bci_portals/proceso/1?x=1",
])
def test_only_public_endpoints_are_allowed(url):
    assert not bci.public_url(url)


def test_saved_json_import_uses_folder_of_details(tmp_path):
    (tmp_path / "listado.json").write_text(json.dumps(LISTADO), encoding="utf-8")
    (tmp_path / "proceso_39410.json").write_text(json.dumps(FICHA), encoding="utf-8")
    found, partial = bci.leer_guardado([tmp_path / "listado.json"], tmp_path)
    by_id = {row["id_origen"]: row for row in found}
    assert by_id["39410"]["descripcion"] and partial == []
    assert by_id["39393"]["descripcion"] is None
