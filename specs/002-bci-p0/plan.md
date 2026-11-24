# 002 — Plan

## Approach (locked)
- Lectura directa de la API JSON pública de `trabajaenbci.cl` con `urllib` (biblioteca estándar), igual que
  `itau.py`: User-Agent propio, `robots.txt`, retardo ≥1 s (o `Crawl-delay`), sin redirecciones, límite de tamaño.
  Sin navegador ni proveedor externo: el JSON ya trae la ficha completa.
- `asistente/ofertas.py`: modelo común (tabla `ofertas` con `UNIQUE(fuente, id_origen)` y tabla `fallos`), `guardar()` con
  upsert que conserva descripción y primera detección, `importar_fuentes()` que aísla cada fuente.
- `asistente/bci.py`: `parse_listing()`, `parse_detail()` (HTML → texto con secciones «Descripción», «Funciones»,
  «Requisitos», «Deseable»), `Portal` con `fetch_json()`, CLI con `--paginas`, `--detalles`, `--json` (respaldo
  con respuestas guardadas).
- `asistente/reglas.py`: extracción por secciones y palabra «deseable»; evidencia por `señales` del perfil
  (`palabras` + `respaldo`). Salida con el formato que ya valida `app.validate()`.
- `app.py`: `--reglas` y `--oferta-bd fuente:id`; el resto del flujo (validar, recomendar, elegir, registrar) igual.

## Constitution check
- AGENTS.md: nivel 4, pruebas por criterio con negativo, ruff/mypy/pytest en verde, sin datos personales reales,
  sin envío, sin evasión. Fase sin declarar; se trata como `solid` (hay CI y pruebas).

## Files
- new: `asistente/ofertas.py`, `asistente/bci.py`, `asistente/reglas.py`, `tests/test_ofertas.py`, `tests/test_bci.py`, `tests/test_reglas.py`,
  `tests/fixtures/bci/*.json`
- changed: `app.py` (flags), `demo/perfil.json` (`señales`), `tests/test_app.py`, `README.md`,
  `REQUERIMIENTOS.md` (estado actual), CI (`mypy` sobre los módulos nuevos)
