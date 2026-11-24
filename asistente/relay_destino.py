"""Destinos del relay para el asistente: convierten lo leído en el navegador al modelo común de ofertas."""

import re

from asistente import bci
from asistente.ofertas import guardar

CODIGO = re.compile(r"\s*\(c[óo]digo[^)]*\)\s*$", re.IGNORECASE)
SECCIONES = (
    ("Descripción", "mision"),
    ("Funciones", "funciones"),
    ("Requisitos", "requisitos"),
    ("Deseable", "deseable"),
)


def guardar_bci(filas, receta, database):
    ofertas = []
    for fila in filas:
        match = re.search(r"/offers/proceso/([0-9]+)", str(fila.get("enlace") or ""))
        cargo = CODIGO.sub("", " ".join(str(fila.get("cargo") or "").split()))
        if not match or not cargo:
            continue
        partes = [f"{titulo}\n{fila[clave]}" for titulo, clave in SECCIONES if fila.get(clave)]
        ofertas.append(
            {
                "fuente": bci.FUENTE,
                "id_origen": match[1],
                "empresa": bci.EMPRESA,
                "cargo": cargo,
                "ubicacion": fila.get("ubicacion") or None,
                "fecha_publicacion": bci.fecha_iso(fila["fecha_publicacion"])
                if fila.get("fecha_publicacion")
                else None,
                "enlace": bci.OFFER.format(match[1]),
                "descripcion": "\n\n".join(partes) if fila.get("requisitos") or fila.get("mision") else None,
            }
        )
    return guardar(database, ofertas)


def guardar_latam(filas, receta, database):
    ofertas = []
    for fila in filas:
        enlace = str(fila.get("enlace") or "")
        id_origen = str(fila.get("id") or "").strip() or enlace.rstrip("/").rsplit("/", 1)[-1]
        if not enlace or not id_origen or not fila.get("cargo"):
            continue
        ofertas.append(
            {
                "fuente": "latam",
                "id_origen": id_origen,
                "empresa": "LATAM Airlines",
                "cargo": fila["cargo"],
                "ubicacion": fila.get("ubicacion") or None,
                "fecha_publicacion": None,
                "enlace": enlace,
                "descripcion": fila.get("descripcion") or None,
            }
        )
    return guardar(database, ofertas)


DESTINOS = {"ofertas_bci": guardar_bci, "ofertas_latam": guardar_latam}
