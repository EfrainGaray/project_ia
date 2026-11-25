"""Candidaturas locales, huella de revisión e historial de estados."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from asistente import ofertas

TRANSICIONES = {
    "borrador": {"listo"},
    "listo": {"aprobado", "listo"},
    "aprobado": {"enviado", "por_verificar", "listo"},
    "por_verificar": {"enviado", "aprobado"},
    "enviado": set(),
}

ESQUEMA = """
    CREATE TABLE IF NOT EXISTS candidaturas (
        id INTEGER PRIMARY KEY,
        fuente TEXT NOT NULL,
        id_origen TEXT NOT NULL,
        decision_id INTEGER NOT NULL REFERENCES decisiones(id),
        destino TEXT NOT NULL,
        cargo TEXT NOT NULL,
        cv_version TEXT NOT NULL,
        archivo TEXT NOT NULL,
        pdf_sha256 TEXT NOT NULL,
        respuestas TEXT NOT NULL,
        estado TEXT NOT NULL CHECK (estado IN ('borrador','listo','aprobado','enviado','por_verificar')),
        huella TEXT NOT NULL,
        aprobada_en TEXT,
        enviada_en TEXT,
        comprobante TEXT,
        FOREIGN KEY (fuente, id_origen) REFERENCES ofertas (fuente, id_origen)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS candidatura_activa_por_oferta
        ON candidaturas(fuente, id_origen) WHERE estado <> 'enviado';
    CREATE TABLE IF NOT EXISTS candidatura_eventos (
        id INTEGER PRIMARY KEY,
        candidatura_id INTEGER NOT NULL REFERENCES candidaturas(id),
        estado_anterior TEXT NOT NULL,
        estado_nuevo TEXT NOT NULL,
        fecha TEXT NOT NULL,
        huella TEXT NOT NULL,
        motivo TEXT NOT NULL
    );
"""


def _conectar(database: str | Path) -> sqlite3.Connection:
    db = ofertas.conectar(database)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(ESQUEMA)
        db.row_factory = sqlite3.Row
    except sqlite3.Error:
        db.close()
        raise
    return db


def _json_canonico(valor: dict) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def huella(destino: str, cargo: str, pdf_sha256: str, respuestas: dict[str, str]) -> str:
    contenido = _json_canonico({
        "destino": destino, "cargo": cargo, "pdf_sha256": pdf_sha256, "respuestas": respuestas,
    })
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _sha256_pdf(archivo: Path) -> str:
    try:
        return hashlib.sha256(archivo.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError("No se pudo leer el PDF de la candidatura.") from error


def crear(
    database: str | Path,
    fuente: str,
    id_origen: str,
    decision_id: int,
    archivo: str | Path,
    respuestas: dict[str, str] | None = None,
) -> int:
    """Crea un borrador a partir de una oferta y la decisión que registró el PDF."""
    pdf = Path(archivo).resolve()
    pdf_sha256 = _sha256_pdf(pdf)
    respuestas = {} if respuestas is None else respuestas
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        oferta = db.execute(
            "SELECT cargo, enlace FROM ofertas WHERE fuente = ? AND id_origen = ?",
            (fuente, id_origen),
        ).fetchone()
        if oferta is None:
            raise ValueError("No existe la oferta indicada.")
        existe_tabla = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'decisiones'"
        ).fetchone()
        decision = db.execute(
            "SELECT cv_elegido, archivo, sha256 FROM decisiones WHERE id = ?", (decision_id,),
        ).fetchone() if existe_tabla else None
        if decision is None:
            raise ValueError("No existe la decisión de CV indicada.")
        if (pdf.name, pdf_sha256) != (decision["archivo"], decision["sha256"]):
            raise ValueError("El PDF no coincide con el registrado en la decisión de CV.")
        destino, cargo = oferta["enlace"], oferta["cargo"]
        resultado = db.execute("""
            INSERT INTO candidaturas (
                fuente, id_origen, decision_id, destino, cargo, cv_version,
                archivo, pdf_sha256, respuestas, estado, huella
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?)
            ON CONFLICT(fuente, id_origen) WHERE estado <> 'enviado' DO NOTHING
        """, (
            fuente, id_origen, decision_id, destino, cargo, decision["cv_elegido"], str(pdf),
            pdf_sha256, _json_canonico(respuestas), huella(destino, cargo, pdf_sha256, respuestas),
        ))
        if resultado.rowcount != 1 or resultado.lastrowid is None:
            raise ValueError("Ya existe una candidatura activa para esta oferta.")
        return resultado.lastrowid


def _fila(db: sqlite3.Connection, candidatura_id: int) -> sqlite3.Row:
    fila = db.execute("SELECT * FROM candidaturas WHERE id = ?", (candidatura_id,)).fetchone()
    if fila is None:
        raise ValueError("No existe la candidatura indicada.")
    return fila


def leer(database: str | Path, candidatura_id: int) -> dict:
    with closing(_conectar(database)) as db:
        candidatura = dict(_fila(db, candidatura_id))
    candidatura["respuestas"] = json.loads(candidatura["respuestas"])
    return candidatura


def cambiar_estado(
    database: str | Path,
    candidatura_id: int,
    nuevo_estado: str,
    *,
    huella_vista: str | None = None,
    motivo: str | None = None,
    comprobante: str | None = None,
) -> None:
    """Valida la transición y guarda el nuevo estado y el evento juntos."""
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        fila = _fila(db, candidatura_id)
        anterior = fila["estado"]
        if nuevo_estado not in TRANSICIONES[anterior]:
            raise ValueError(f"Transición no permitida: {anterior} → {nuevo_estado}.")
        if nuevo_estado == "listo" and anterior != "borrador":
            raise ValueError("Transición a listo reservada para cambios de contenido.")
        if anterior == "listo":
            if huella_vista != fila["huella"]:
                raise ValueError("La huella de aprobación no coincide con la candidatura.")
        if anterior in {"listo", "aprobado"}:
            if _sha256_pdf(Path(fila["archivo"])) != fila["pdf_sha256"]:
                raise ValueError("El PDF cambió desde que se guardó la candidatura.")

        fecha = ofertas.ahora()
        aprobada_en = fecha if anterior == "listo" else fila["aprobada_en"]
        enviada_en = fecha if nuevo_estado == "enviado" else None
        db.execute("""
            UPDATE candidaturas SET estado = ?, aprobada_en = ?, enviada_en = ?, comprobante = ?
            WHERE id = ?
        """, (nuevo_estado, aprobada_en, enviada_en, comprobante if enviada_en else None, candidatura_id))
        db.execute("""
            INSERT INTO candidatura_eventos (
                candidatura_id, estado_anterior, estado_nuevo, fecha, huella, motivo
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (candidatura_id, anterior, nuevo_estado, fecha, fila["huella"], motivo or nuevo_estado))


def aprobar(database: str | Path, candidatura_id: int, huella_vista: str) -> None:
    cambiar_estado(database, candidatura_id, "aprobado", huella_vista=huella_vista, motivo="Aprobación")
