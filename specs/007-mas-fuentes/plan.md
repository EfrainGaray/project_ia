# 007 — Plan

## Approach (locked)
- Una fuente = un módulo `asistente/<fuente>.py` (lectura directa) o una receta `relay/recipes/<fuente>_ofertas.json` +
  destino en `asistente/relay_destino.py` (relay). Mismo contrato que `asistente/bci.py`: `parse_listing()`,
  `parse_detail()`, `FUENTE`, `EMPRESA`, y guardar con `asistente.ofertas.guardar()`; fallos con `registrar_fallo()`.
- Lectura directa con el mismo cliente que Bci e Itaú: `urllib`, User-Agent propio, robots.txt, retardo ≥1 s o
  `Crawl-delay`, sin redirecciones a otros dominios, límite de tamaño.
- Itaú: función `migrar(database)` en `itau.py` que copia `ofertas_itau` → `ofertas` (`INSERT ... ON CONFLICT`) y
  `save()` pasa a usar `guardar()`. La tabla vieja no se borra.
- `asistente/cobertura.py`: una consulta agregada sobre `ofertas` y `fallos`; salida de texto y `--json`.
- Fixtures por fuente en `tests/fixtures/<fuente>/` (respuestas reales grabadas, datos de personas reemplazados por
  «PERSONA FICTICIA»); `tests/test_fuentes.py` parametrizado por fuente.

## Constitution check
- AGENTS.md: robots.txt y términos, ritmo limitado, detenerse ante rechazos, sin evasión, fixtures sin datos personales.
  Fase `solid`.

## Files
- new: `asistente/{bancochile,sky,cajalosandes,coopeuch}.py` o sus recetas (según el método de cada una),
  `asistente/cobertura.py`, `tests/test_fuentes.py`, `tests/test_cobertura.py`, `tests/fixtures/<fuente>/*`
- changed: `itau.py`, `tests/test_itau.py`, `asistente/relay_destino.py` (si hay recetas), `README.md`,
  `REQUERIMIENTOS.md` (estado actual), CI (`mypy` si hay módulos nuevos fuera de `asistente/`)
