import hashlib
import sqlite3
from contextlib import closing

import pytest

from app import record
from asistente import candidaturas, ofertas


@pytest.fixture
def candidatura(tmp_path):
    bd = tmp_path / "postulaciones.sqlite3"
    pdf = tmp_path / "datos.pdf"
    pdf.write_bytes(b"%PDF-1.4 ejemplo ficticio")
    ofertas.guardar(bd, [{
        "fuente": "bci", "id_origen": "1", "empresa": "Banco de prueba",
        "cargo": "Analista", "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [], "datos", "datos", pdf, "Ejemplo")
    identificador = candidaturas.crear(
        bd, "bci", "1", decision, pdf, {"motivación": "Análisis", "experiencia": "Python"},
    )
    return bd, identificador, decision, pdf


def test_aprobar(candidatura):
    bd, identificador, decision, pdf = candidatura
    fila = candidaturas.leer(bd, identificador)
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    contenido = (
        '{"cargo":"Analista","destino":"https://example.org/oferta",'
        f'"pdf_sha256":"{pdf_sha}","respuestas":{{"experiencia":"Python","motivación":"Análisis"}}}}'
    )
    assert fila["huella"] == hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    assert fila["decision_id"] == decision
    assert fila["estado"] == "borrador"

    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, fila["huella"])

    aprobada = candidaturas.leer(bd, identificador)
    assert aprobada["estado"] == "aprobado"
    assert aprobada["aprobada_en"]
    assert aprobada["huella"] == fila["huella"]


def test_huella_distinta(candidatura):
    bd, identificador, _, _ = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    with pytest.raises(ValueError, match="huella"):
        candidaturas.aprobar(bd, identificador, "0" * 64)
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


def test_aprobar_rechaza_pdf_modificado(candidatura):
    bd, identificador, _, pdf = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    fila = candidaturas.leer(bd, identificador)
    pdf.write_bytes(b"%PDF-1.4 contenido distinto")
    with pytest.raises(ValueError, match="PDF"):
        candidaturas.aprobar(bd, identificador, fila["huella"])
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


@pytest.mark.parametrize("estado", ["borrador", "listo"])
def test_transicion_directa_a_enviado_se_rechaza(candidatura, estado):
    bd, identificador, _, _ = candidatura
    if estado == "listo":
        candidaturas.cambiar_estado(bd, identificador, "listo")
    with pytest.raises(ValueError, match="Transición"):
        candidaturas.cambiar_estado(bd, identificador, "enviado")
    assert candidaturas.leer(bd, identificador)["estado"] == estado


def test_eventos(candidatura):
    bd, identificador, _, _ = candidatura
    fila = candidaturas.leer(bd, identificador)
    candidaturas.cambiar_estado(bd, identificador, "listo", motivo="Revisión preparada")
    candidaturas.aprobar(bd, identificador, fila["huella"])

    with closing(sqlite3.connect(bd)) as db:
        eventos = db.execute("""
            SELECT estado_anterior, estado_nuevo, fecha, huella, motivo
            FROM candidatura_eventos WHERE candidatura_id = ? ORDER BY id
        """, (identificador,)).fetchall()
    assert [(anterior, nuevo) for anterior, nuevo, *_ in eventos] == [
        ("borrador", "listo"), ("listo", "aprobado"),
    ]
    assert eventos[0][-1] == "Revisión preparada"
    assert all(fecha and huella == fila["huella"] and motivo for _, _, fecha, huella, motivo in eventos)


def test_eventos_y_estado_se_guardan_en_la_misma_transaccion(candidatura):
    bd, identificador, _, _ = candidatura
    with closing(sqlite3.connect(bd)) as db, db:
        db.execute("""
            CREATE TRIGGER impedir_evento BEFORE INSERT ON candidatura_eventos
            BEGIN
                SELECT RAISE(ABORT, 'error de prueba');
            END
        """)
    with pytest.raises(sqlite3.IntegrityError, match="error de prueba"):
        candidaturas.cambiar_estado(bd, identificador, "listo")
    assert candidaturas.leer(bd, identificador)["estado"] == "borrador"


def test_una_sola_candidatura_activa_por_oferta(candidatura):
    bd, identificador, decision, pdf = candidatura
    with pytest.raises(ValueError, match="activa"):
        candidaturas.crear(bd, "bci", "1", decision, pdf)

    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, candidaturas.leer(bd, identificador)["huella"])
    candidaturas.cambiar_estado(bd, identificador, "enviado")
    assert candidaturas.crear(bd, "bci", "1", decision, pdf) != identificador
