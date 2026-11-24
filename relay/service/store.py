"""SQLite del relay: corridas, resultados, aprobaciones por huella y recetas en pausa."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

ESQUEMA = """
    CREATE TABLE IF NOT EXISTS relay_corridas (
        id INTEGER PRIMARY KEY,
        receta TEXT NOT NULL,
        inicio TEXT NOT NULL,
        fin TEXT,
        estado TEXT NOT NULL,
        motivo TEXT
    );
    CREATE TABLE IF NOT EXISTS relay_resultados (
        id INTEGER PRIMARY KEY,
        corrida INTEGER NOT NULL REFERENCES relay_corridas(id),
        receta TEXT NOT NULL,
        destino TEXT NOT NULL,
        datos TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS relay_aprobaciones (
        huella TEXT PRIMARY KEY,
        receta TEXT NOT NULL,
        url TEXT NOT NULL,
        contenido TEXT NOT NULL,
        estado TEXT NOT NULL,
        creada TEXT NOT NULL,
        aprobada TEXT,
        enviada TEXT
    );
    CREATE TABLE IF NOT EXISTS relay_pausas (
        receta TEXT PRIMARY KEY,
        motivo TEXT NOT NULL,
        fecha TEXT NOT NULL
    );
"""
ESPERANDO = "esperando aprobación"
APROBADA = "aprobada"
ENVIADA = "enviada"


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def huella(receta, url, campos):
    """SHA-256 del contenido exacto: receta, destino y cada campo con su valor."""
    canon = json.dumps(
        {"receta": receta, "url": url, "campos": campos},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode()).hexdigest()


class Store:
    def __init__(self, database):
        self.database = database
        with closing(self.connect()) as db, db:
            db.executescript(ESQUEMA)

    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        return db

    def start_run(self, receta):
        with closing(self.connect()) as db, db:
            return db.execute(
                "INSERT INTO relay_corridas (receta, inicio, estado) VALUES (?, ?, 'en curso')",
                (receta, ahora()),
            ).lastrowid

    def finish_run(self, corrida, estado, motivo=None):
        with closing(self.connect()) as db, db:
            db.execute(
                "UPDATE relay_corridas SET fin = ?, estado = ?, motivo = ? WHERE id = ?",
                (ahora(), estado, motivo, corrida),
            )

    def run(self, corrida):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM relay_corridas WHERE id = ?", (corrida,)).fetchone()
        return dict(row) if row else None

    def last_run(self, receta):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM relay_corridas WHERE receta = ? ORDER BY id DESC LIMIT 1", (receta,)
            ).fetchone()
        return dict(row) if row else None

    def save_results(self, corrida, receta, destino, filas):
        with closing(self.connect()) as db, db:
            db.executemany(
                "INSERT INTO relay_resultados (corrida, receta, destino, datos) VALUES (?, ?, ?, ?)",
                [(corrida, receta, destino, json.dumps(fila, ensure_ascii=False)) for fila in filas],
            )

    def request_approval(self, receta, url, campos):
        clave = huella(receta, url, campos)
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT INTO relay_aprobaciones (huella, receta, url, contenido, estado, creada)
                   VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(huella) DO NOTHING""",
                (
                    clave,
                    receta,
                    url,
                    json.dumps(campos, ensure_ascii=False, sort_keys=True),
                    ESPERANDO,
                    ahora(),
                ),
            )
        return clave

    def approval(self, clave):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM relay_aprobaciones WHERE huella = ?", (clave,)).fetchone()
        return dict(row) if row else None

    def approve(self, clave):
        """La persona aprueba un contenido exacto ya revisado. Devuelve False si la huella no existe."""
        with closing(self.connect()) as db, db:
            changed = db.execute(
                "UPDATE relay_aprobaciones SET estado = ?, aprobada = ? WHERE huella = ? AND estado = ?",
                (APROBADA, ahora(), clave, ESPERANDO),
            ).rowcount
        return bool(changed)

    def mark_sent(self, clave):
        with closing(self.connect()) as db, db:
            db.execute(
                "UPDATE relay_aprobaciones SET estado = ?, enviada = ? WHERE huella = ?",
                (ENVIADA, ahora(), clave),
            )

    def pause(self, receta, motivo):
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO relay_pausas (receta, motivo, fecha) VALUES (?, ?, ?)",
                (receta, motivo, ahora()),
            )

    def paused(self, receta):
        with closing(self.connect()) as db:
            row = db.execute("SELECT motivo FROM relay_pausas WHERE receta = ?", (receta,)).fetchone()
        return row[0] if row else None

    def resume(self, receta):
        with closing(self.connect()) as db, db:
            return bool(db.execute("DELETE FROM relay_pausas WHERE receta = ?", (receta,)).rowcount)
