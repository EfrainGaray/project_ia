# 006 — Plan

## Approach (locked)
- `asistente/revision.py` con `http.server.ThreadingHTTPServer` (biblioteca estándar, sin framework ni JavaScript
  obligatorio): HTML generado con `html.escape`, CSS en línea con `prefers-color-scheme` y diseño de una columna.
- Rutas: `GET /` (lista de candidaturas), `GET /candidatura/<id>`, `GET /pdf/<version>` (solo versiones conocidas,
  `Content-Type: application/pdf`, mostrado con `<embed>`), `POST /candidatura/<id>/aprobar` (campos `huella`, `token`),
  `POST /candidatura/<id>/cv` (campos `version`, `token`).
- La lógica de estados y huella es la de `asistente/candidaturas.py` (005); la vista no recalcula reglas propias.
- Token de formulario aleatorio (`secrets.token_urlsafe`) generado al iniciar el servidor; verificación de `Host`.
- CLI: `python -m asistente.revision [--bd] [--puerto 8770]`, imprime la URL.
- Pruebas: servidor en un hilo con puerto libre y peticiones con `urllib`; datos ficticios y los PDFs de `demo/cv/`.

## Constitution check
- AGENTS.md: aprobación del contenido exacto (la huella mostrada), solo local, nada de credenciales, datos ficticios
  en pruebas. Diseño claro/oscuro y móvil. Fase `solid`.

## Files
- new: `asistente/revision.py`, `tests/test_revision.py`
- changed: `README.md` (cómo abrir la vista), `REQUERIMIENTOS.md` (estado actual)
