"""Modelo común de ofertas: una fila por fuente e ID de origen, y registro de fallos por fuente."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

PENDIENTE = "pendiente de descripción"
COMPLETA = "completa"
CAMPOS = (
    "fuente", "id_origen", "empresa", "cargo", "ubicacion", "fecha_publicacion", "enlace", "descripcion",
)
ESQUEMA = """
    CREATE TABLE IF NOT EXISTS ofertas (
        fuente TEXT NOT NULL,
        id_origen TEXT NOT NULL,
        empresa TEXT NOT NULL,
        cargo TEXT NOT NULL,
        ubicacion TEXT,
        fecha_publicacion TEXT,
        fecha_deteccion TEXT NOT NULL,
        fecha_actualizacion TEXT NOT NULL,
        enlace TEXT NOT NULL,
        descripcion TEXT,
        estado TEXT NOT NULL,
        UNIQUE (fuente, id_origen)
    );
    CREATE TABLE IF NOT EXISTS fallos (
        id INTEGER PRIMARY KEY,
        fuente TEXT NOT NULL,
        fecha TEXT NOT NULL,
        url TEXT,
        codigo_http INTEGER,
        motivo TEXT NOT NULL
    );
"""
UPSERT = """
    INSERT INTO ofertas (fuente, id_origen, empresa, cargo, ubicacion, fecha_publicacion, fecha_deteccion,
                         fecha_actualizacion, enlace, descripcion, estado)
    VALUES (:fuente, :id_origen, :empresa, :cargo, :ubicacion, :fecha_publicacion, :ahora, :ahora, :enlace,
            :descripcion, :estado)
    ON CONFLICT (fuente, id_origen) DO UPDATE SET
        empresa = excluded.empresa,
        cargo = excluded.cargo,
        ubicacion = COALESCE(excluded.ubicacion, ofertas.ubicacion),
        fecha_publicacion = COALESCE(excluded.fecha_publicacion, ofertas.fecha_publicacion),
        fecha_actualizacion = excluded.fecha_actualizacion,
        enlace = excluded.enlace,
        descripcion = COALESCE(excluded.descripcion, ofertas.descripcion),
        estado = CASE WHEN COALESCE(excluded.descripcion, ofertas.descripcion) IS NULL
                      THEN :pendiente ELSE :completa END
"""


class FalloFuente(Exception):
    """Una consulta a un portal falló; conserva la URL y el código HTTP si existe."""

    def __init__(self, motivo, url=None, codigo_http=None):
        super().__init__(motivo)
        self.url = url
        self.codigo_http = codigo_http


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(database):
    db = sqlite3.connect(database)
    db.executescript(ESQUEMA)
    return db


def guardar(database, ofertas, momento=None):
    momento = momento or ahora()
    filas = []
    for oferta in ofertas:
        fila = {campo: oferta.get(campo) for campo in CAMPOS}
        if not fila["descripcion"] or not str(fila["descripcion"]).strip():
            fila["descripcion"] = None
        fila.update(ahora=momento, pendiente=PENDIENTE, completa=COMPLETA,
                    estado=COMPLETA if fila["descripcion"] else PENDIENTE)
        filas.append(fila)
    with closing(conectar(database)) as db, db:
        db.executemany(UPSERT, filas)
        return db.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0]


def registrar_fallo(database, fuente, error, momento=None):
    with closing(conectar(database)) as db, db:
        db.execute(
            "INSERT INTO fallos (fuente, fecha, url, codigo_http, motivo) VALUES (?, ?, ?, ?, ?)",
            (fuente, momento or ahora(), getattr(error, "url", None), getattr(error, "codigo_http", None),
             str(error)),
        )


def importar_fuentes(database, fuentes):
    """Ejecuta cada fuente por separado. Un fallo queda registrado y no detiene a las demás.

    Cada fuente es una función sin argumentos que devuelve (ofertas, fallos_parciales).
    """
    resumen = {}
    for nombre, leer in fuentes.items():
        try:
            ofertas, parciales = leer()
        except (FalloFuente, OSError, ValueError) as error:
            registrar_fallo(database, nombre, error)
            resumen[nombre] = {"ofertas": 0, "fallos": [str(error)]}
            continue
        guardar(database, ofertas)
        for parcial in parciales:
            registrar_fallo(database, nombre, parcial)
        resumen[nombre] = {"ofertas": len(ofertas), "fallos": [str(parcial) for parcial in parciales]}
    return resumen


def leer_oferta(database, fuente, id_origen):
    with closing(conectar(database)) as db:
        db.row_factory = sqlite3.Row
        fila = db.execute(
            "SELECT * FROM ofertas WHERE fuente = ? AND id_origen = ?", (fuente, str(id_origen))
        ).fetchone()
    return dict(fila) if fila else None
