from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from app import record
from asistente import candidaturas, ofertas, revision

PERFIL = Path(__file__).resolve().parents[1] / "demo" / "perfil.json"


@pytest.fixture
def vista(tmp_path):
    bd = tmp_path / "postulaciones.sqlite3"
    pdf = PERFIL.parent / "cv" / "datos.pdf"
    ofertas.guardar(bd, [{
        "fuente": "demo", "id_origen": "1", "empresa": "Banco de prueba",
        "cargo": "Analista", "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [
        {"tipo": "obligatorio", "cita": "Uso de Python", "evidencia": "python", "estado": "respaldado"},
    ], "datos", "datos", pdf, "Ejemplo")
    identificador = candidaturas.crear(bd, "demo", "1", decision, pdf, {"motivación": "Datos <b>"})
    candidaturas.cambiar_estado(bd, identificador, "listo")
    with revision.servidor(bd, 0, PERFIL) as servidor:
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        try:
            yield bd, identificador, f"http://127.0.0.1:{servidor.server_port}"
        finally:
            servidor.shutdown()
            hilo.join()


def test_muestra_candidatura_y_pdf(vista):
    bd, identificador, base = vista
    fila = candidaturas.leer(bd, identificador)
    with urlopen(base + "/") as respuesta:
        assert f"/candidatura/{identificador}" in respuesta.read().decode()
    with urlopen(f"{base}/candidatura/{identificador}") as respuesta:
        html = respuesta.read().decode()
    for texto in ("Analista", "Banco de prueba", "Uso de Python", "validación de archivos", "datos.pdf",
                  "example.org/oferta", "Datos &lt;b&gt;", fila["huella"]):
        assert texto in html
    assert "Datos <b>" not in html
    with urlopen(f"{base}/pdf/datos?id={identificador}&huella={fila['huella']}") as respuesta:
        assert respuesta.headers.get_content_type() == "application/pdf"
        assert respuesta.read() == (PERFIL.parent / "cv" / "datos.pdf").read_bytes()


@pytest.mark.parametrize("ruta", ["/pdf/../../etc/passwd", "/pdf/desconocido", "/pdf/%2e%2e%2fetc%2fpasswd"])
def test_pdf_ruta_fuera_de_lista(vista, ruta):
    _, _, base = vista
    with pytest.raises(HTTPError) as error:
        urlopen(base + ruta)
    assert error.value.code == 404


def test_host_no_local_rechazado(vista):
    _, _, base = vista
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base, headers={"Host": "ejemplo.com"}))
    assert error.value.code == 403
