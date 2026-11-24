# 005 — Plan

## Approach (locked)
- `asistente/candidaturas.py` (biblioteca estándar, SQLite en la misma base `postulaciones.sqlite3`):
  - tablas `candidaturas` (con `UNIQUE` parcial de una activa por oferta) y `candidatura_eventos`;
  - `huella(destino, cargo, pdf_sha256, respuestas)` con `json.dumps(..., sort_keys=True, ensure_ascii=False,
    separators=(",", ":"))` y SHA-256;
  - `TRANSICIONES` como diccionario `estado → estados permitidos`; una sola función `cambiar_estado()` que valida,
    escribe el evento y actualiza la fila en la misma transacción;
  - `crear()`, `actualizar_contenido()` (recalcula la huella; si estaba «aprobado» vuelve a «listo»), `aprobar(huella)`,
    `marcar_envio(resultado)` con `enviado` / `incierto` / `no_enviado`.
- CLI `python -m asistente.candidaturas` con `crear`, `responder`, `listo`, `mostrar` (contenido + huella),
  `aprobar <huella>`, `enviado [--comprobante]`, `incierto`, `no-enviado`, `historial`.
- Estados en español sin tildes en la base: `borrador`, `listo`, `aprobado`, `enviado`, `por_verificar`.

## Constitution check
- AGENTS.md: aprobación del contenido exacto, cambio → nueva aprobación, envío incierto → verificar antes de
  reintentar, datos ficticios en pruebas, la base fuera del repositorio. Fase `solid`.

## Files
- new: `asistente/candidaturas.py`, `tests/test_candidaturas.py`
- changed: `README.md` (uso de la CLI), `REQUERIMIENTOS.md` (estado actual)
