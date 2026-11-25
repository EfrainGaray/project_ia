"""Reporte local de ofertas y fallos por fuente."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from asistente import ofertas

CONSULTA = """
WITH conteos AS (
    SELECT fuente, COUNT(*) AS ofertas,
           COUNT(CASE WHEN estado = :completa THEN 1 END) AS completas,
           MAX(fecha_actualizacion) AS ultima_importacion
    FROM ofertas GROUP BY fuente
), fallos_ordenados AS (
    SELECT fuente, fecha, url, codigo_http, motivo,
           ROW_NUMBER() OVER (PARTITION BY fuente ORDER BY fecha DESC, id DESC) AS posicion
    FROM fallos
), fuentes AS (
    SELECT fuente FROM conteos UNION SELECT fuente FROM fallos_ordenados
)
SELECT fuentes.fuente, COALESCE(conteos.ofertas, 0) AS ofertas,
       COALESCE(conteos.completas, 0) AS completas, conteos.ultima_importacion,
       fallo.fecha, fallo.url, fallo.codigo_http, fallo.motivo
FROM fuentes
LEFT JOIN conteos ON fuentes.fuente = conteos.fuente
LEFT JOIN fallos_ordenados AS fallo ON fuentes.fuente = fallo.fuente AND fallo.posicion = 1
ORDER BY fuentes.fuente
"""


def reporte(bd: Path) -> list[dict]:
    with closing(ofertas.conectar(bd)) as db:
        db.row_factory = sqlite3.Row
        filas = db.execute(CONSULTA, {"completa": ofertas.COMPLETA}).fetchall()
    resultado = []
    for fila in filas:
        total, completas = fila["ofertas"], fila["completas"]
        fallo = None
        if fila["fecha"] is not None:
            fallo = {campo: fila[campo] for campo in ("fecha", "url", "codigo_http", "motivo")}
        resultado.append({
            "fuente": fila["fuente"], "ofertas": total, "completas": completas,
            "pendientes": total - completas,
            "porcentaje_completas": round(completas * 100 / total, 2) if total else 0,
            "ultima_importacion": fila["ultima_importacion"], "ultimo_fallo": fallo,
        })
    return resultado


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Muestra la cobertura de ofertas por fuente.")
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--json", action="store_true", help="Devuelve el reporte en JSON.")
    args = parser.parse_args(argv)
    try:
        filas = reporte(args.bd)
    except sqlite3.Error as error:
        parser.exit(1, f"Error: {error}\n")
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2))
        return
    if not filas:
        print("Cobertura: sin datos.")
        return
    for fila in filas:
        print(f"{fila['fuente']} · {fila['ofertas']} ofertas · {fila['completas']} completas "
              f"({fila['porcentaje_completas']:g} %) · {fila['pendientes']} pendientes")
        print(f"  Última importación con ofertas: {fila['ultima_importacion'] or 'sin registro'}")
        fallo = fila["ultimo_fallo"]
        if fallo:
            codigo = f" · HTTP {fallo['codigo_http']}" if fallo["codigo_http"] is not None else ""
            print(f"  Último fallo: {fallo['fecha']}{codigo} · {fallo['motivo']}")
        else:
            print("  Último fallo: sin registro")


if __name__ == "__main__":
    main()
