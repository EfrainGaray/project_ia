import json

from asistente import cobertura, ofertas


def test_cobertura_por_fuente(tmp_path, capsys):
    bd = tmp_path / "postulaciones.sqlite3"
    base = {"cargo": "Analista", "empresa": "Empresa ficticia", "enlace": "https://example.org/oferta"}
    ofertas.guardar(bd, [
        {**base, "fuente": "bci", "id_origen": "1", "descripcion": "Python"},
        {**base, "fuente": "bci", "id_origen": "2"},
    ], momento="2026-11-24T10:00:00+00:00")
    ofertas.registrar_fallo(bd, "bci", ofertas.FalloFuente("anterior"), "2026-11-24T11:00:00+00:00")
    ofertas.registrar_fallo(bd, "bci", ofertas.FalloFuente("rechazo", codigo_http=403),
                            "2026-11-24T11:00:00+00:00")
    ofertas.registrar_fallo(bd, "itau", ofertas.FalloFuente("sin acceso", codigo_http=403))

    cobertura.main(["--bd", str(bd), "--json"])
    bci, itau = json.loads(capsys.readouterr().out)
    assert bci == {
        "fuente": "bci", "ofertas": 2, "completas": 1, "pendientes": 1, "porcentaje_completas": 50,
        "ultima_importacion": "2026-11-24T10:00:00+00:00",
        "ultimo_fallo": {
            "fecha": "2026-11-24T11:00:00+00:00", "url": None, "codigo_http": 403, "motivo": "rechazo",
        },
    }
    assert itau["ofertas"] == 0 and itau["ultima_importacion"] is None
    assert itau["ultimo_fallo"]["motivo"] == "sin acceso"


def test_vacia(tmp_path, capsys):
    bd = tmp_path / "vacia.sqlite3"
    cobertura.main(["--bd", str(bd)])
    assert "sin datos" in capsys.readouterr().out
    cobertura.main(["--bd", str(bd), "--json"])
    assert json.loads(capsys.readouterr().out) == []
