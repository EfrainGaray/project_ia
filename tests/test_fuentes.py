import sys
from contextlib import closing
from email.message import Message
from urllib.error import HTTPError

import pytest
from test_itau import DETAIL_HTML, SEARCH_HTML

import itau
from asistente import ofertas


def test_itau_importa_listado_y_ficha(tmp_path, monkeypatch):
    bd = tmp_path / "ofertas.sqlite3"
    listado = tmp_path / "listado.html"
    listado.write_text(SEARCH_HTML, encoding="utf-8")
    (tmp_path / "1338411962.html").write_text(DETAIL_HTML, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["itau.py", "--bd", str(bd), "--html", str(listado),
                                      "--fichas", str(tmp_path)])
    itau.main()
    fila = ofertas.leer_oferta(bd, "itau", "1338411962")
    assert fila["estado"] == ofertas.COMPLETA
    assert "Python deseable." in fila["descripcion"]


def test_itau_refused_registra_codigo_y_conserva_ofertas(tmp_path, monkeypatch):
    bd = tmp_path / "ofertas.sqlite3"
    trabajos, _ = itau.parse_search(SEARCH_HTML)
    itau.save(bd, trabajos)

    def abrir(self, request, timeout):
        if request.full_url.endswith("/robots.txt"):
            return RespuestaRobots()
        raise HTTPError(request.full_url, 403, "Forbidden", Message(), None)

    class RespuestaRobots:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        @property
        def headers(self):
            return self

        def get_content_charset(self):
            return "utf-8"

        def read(self, _):
            return b"User-agent: *\nDisallow:\n"

    monkeypatch.setattr("urllib.request.OpenerDirector.open", abrir)
    monkeypatch.setattr(itau.time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["itau.py", "--bd", str(bd)])
    with pytest.raises(SystemExit) as salida:
        itau.main()
    assert salida.value.code == 1
    assert ofertas.leer_oferta(bd, "itau", "1338411962") is not None
    with closing(ofertas.conectar(bd)) as db:
        fallo = db.execute("SELECT codigo_http, url, motivo FROM fallos WHERE fuente='itau'").fetchone()
    assert fallo[:2] == (403, itau.SEARCH)
    assert "HTTP 403" in fallo[2]
