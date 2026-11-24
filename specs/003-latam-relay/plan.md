# 003 — Plan

## Approach (locked)
- Sin código nuevo en el motor ni en la extensión: se calibra `relay/recipes/latam_ofertas.json` (selectores reales,
  `hosts`, `pace` 4–10 s, `max` de fichas) y se ajusta `guardar_latam` en `asistente/relay_destino.py` (fecha de
  publicación, ubicación, empresa).
- Captura de las páginas: Ayelén abre el listado y una ficha en su Chrome y guarda el HTML renderizado
  (Chrome → «Guardar como» → «Página web, solo HTML», o copiar `document.documentElement.outerHTML` desde DevTools).
  Se limpian datos personales y quedan como `relay/tests/fixtures/latam_real/listado.html` y `ficha.html` (la página
  sintética actual de `relay/tests/fixtures/latam/` se mantiene para la prueba de renderizado de 001). Si LATAM bloquea,
  se guarda también esa página como `denegado.html`.
- Las pruebas Playwright sirven esas copias desde el servidor local de fixtures, igual que las de Bci.
- La corrida en vivo es una observación manual con la extensión en el Chrome de Ayelén.

## Constitution check
- AGENTS.md: la persona abre su propio Chrome; nada de cookies ni credenciales; robots.txt; ritmo humano; detenerse
  ante bloqueos; fixtures sin datos personales. Fase `solid`.

## Files
- new: `relay/tests/fixtures/latam_real/{listado,ficha,denegado}.html`
- changed: `relay/recipes/latam_ofertas.json`, `asistente/relay_destino.py`, `relay/tests/test_extension.py`,
  `tests/test_relay_destino.py`, `relay/README.md` (cómo calibrar una receta)
