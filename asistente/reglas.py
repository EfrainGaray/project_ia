"""Extrae requisitos con reglas simples y los asocia a evidencia del perfil por señales explícitas.

Cubre señales claras: secciones «Requisitos» y «Deseable», la palabra «deseable» en la frase y
palabras clave declaradas en el perfil. Lo ambiguo queda «por confirmar» para revisión humana.
"""

import re
import unicodedata

SECCIONES = {"requisitos": "obligatorio", "deseable": "deseable"}
OTRAS = {"descripción", "funciones", "condiciones"}
DESEABLE = re.compile(r"\b(deseable|valorable|valorado)\b", re.IGNORECASE)
# Duración o nivel exigido: la evidencia del perfil no los acredita por sí sola.
EXIGENCIA = re.compile(r"\b\d+\s*(?:a\s*\d+\s*)?años\b|\b(avanzad[oa]|expert[oa])\b", re.IGNORECASE)


def normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def buscar_senal(frase, senales):
    plana = normalizar(frase)
    for evidencia, senal in senales.items():
        for palabra in senal["palabras"]:
            if re.search(rf"\b{re.escape(normalizar(palabra))}\b", plana):
                return evidencia, senal
    return None, None


def extraer(oferta, perfil):
    senales = perfil.get("señales", {})
    lineas = [linea.strip() for linea in oferta.splitlines() if linea.strip()]
    con_secciones = any(normalizar(linea) in SECCIONES for linea in lineas)
    tipo_seccion = None
    filas = []
    for linea in lineas:
        clave = normalizar(linea)
        if clave in SECCIONES:
            tipo_seccion = SECCIONES[clave]
            continue
        if clave in {normalizar(o) for o in OTRAS}:
            tipo_seccion = None
            continue
        evidencia, senal = buscar_senal(linea, senales)
        if con_secciones and tipo_seccion is None:
            continue
        if not con_secciones and senal is None:
            continue
        tipo = "deseable" if DESEABLE.search(linea) else (tipo_seccion or "sin especificar")
        respaldado = bool(senal and senal.get("respaldo") and not EXIGENCIA.search(linea))
        filas.append({
            "requisito": evidencia or linea[:60],
            "cita": linea,
            "tipo": tipo,
            "estado": "respaldado" if respaldado else "por confirmar",
            "evidencia": evidencia,
        })
    if not filas:
        raise ValueError("Las reglas no encontraron requisitos; revisa la ficha o usa --modelo.")
    return filas
