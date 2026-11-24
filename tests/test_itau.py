import sqlite3

import pytest

import itau

SEARCH_HTML = """
<table id="searchresults">
  <tr><th>Cargo</th><th>Ubicación</th><th>Fecha</th></tr>
  <tr>
    <td><a href="/job/Santiago-Analista-Inteligencia-Cobranza/1338411962/">
      Analista Inteligencia Cobranza</a></td>
    <td>Santiago, CL</td><td>20 nov 2026</td>
  </tr>
  <tr>
    <td><a href="https://otro-sitio.cl/job/1/">Externa</a></td><td>X</td><td>Y</td>
  </tr>
</table>
<a href="/search?q=&startrow=25">Siguiente</a>
<a href="https://otro-sitio.cl/search?startrow=25">Fuera</a>
"""

DETAIL_HTML = """
<div itemprop="description"><p>Manejo de SQL Server.</p>
<script>tracking()</script><p>Python deseable.</p></div>
"""


def test_public_url_only_accepts_the_portal_search_and_job_pages():
    assert itau.public_url("https://trabajaenitau.cl/job/Analista/1338411962/")
    assert itau.public_url("https://trabajaenitau.cl/search")
    assert not itau.public_url("http://trabajaenitau.cl/search")
    assert not itau.public_url("https://otro-sitio.cl/job/1/")
    assert not itau.public_url("https://trabajaenitau.cl/admin")


def test_parse_search_extracts_portal_jobs_and_next_pages():
    jobs, next_pages = itau.parse_search(SEARCH_HTML)
    assert jobs == [{
        "id": "1338411962",
        "titulo": "Analista Inteligencia Cobranza",
        "url": "https://trabajaenitau.cl/job/Santiago-Analista-Inteligencia-Cobranza/1338411962/",
        "ubicacion": "Santiago, CL",
        "fecha": "20 nov 2026",
        "descripcion": None,
    }]
    assert next_pages == ["https://trabajaenitau.cl/search?q=&startrow=25"]


def test_parse_search_rejects_html_without_listing():
    with pytest.raises(ValueError):
        itau.parse_search("<html><body>Acceso denegado</body></html>")


def test_parse_detail_returns_text_without_scripts():
    assert itau.parse_detail(DETAIL_HTML) == "Manejo de SQL Server.\nPython deseable."


def test_parse_detail_rejects_page_without_description():
    with pytest.raises(ValueError):
        itau.parse_detail("<div class='otra'>nada</div>")


def test_importing_twice_keeps_one_row_and_existing_description(tmp_path):
    db = tmp_path / "test.sqlite3"
    job, _ = itau.parse_search(SEARCH_HTML)
    with_description = [{**job[0], "descripcion": "Manejo de SQL Server."}]
    assert itau.save(db, with_description) == 1
    assert itau.save(db, job) == 1  # listing only: no description this time
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT descripcion FROM ofertas_itau").fetchone()[0] == "Manejo de SQL Server."
