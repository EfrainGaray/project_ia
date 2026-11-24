# 001 — Plan

## Approach (locked)
- **Extensión MV3** (`relay/extension/`): service worker que abre un WebSocket a `ws://127.0.0.1:<puerto>`,
  ejecuta comandos primitivos con `chrome.tabs` y `chrome.scripting` (`open`, `wait`, `read`, `click`, `fill`,
  `detect`, `release`) solo sobre pestañas que ella misma abrió, marca la pestaña (insignia + franja con
  «Detener») y guarda el estado detenido en `chrome.storage.local`. Ventana (`popup`) con estado, «Detener»,
  «Reactivar» y el token de emparejamiento. Mantiene el service worker vivo con un latido cada 20 s.
- **Servicio** (`relay/service/`, biblioteca estándar):
  - `ws.py`: servidor WebSocket mínimo (handshake, tramas de texto, ping/pong, cierre), verificación de origen,
    token y prueba HMAC hacia la extensión.
  - `engine.py`: motor de recetas; secuencia pasos, aplica dominios permitidos, `robots.txt`, retardos con
    variación, detección de bloqueo tras cada navegación, huellas y aprobaciones, y entrega resultados a destinos.
  - `store.py`: SQLite (`relay_corridas`, `relay_resultados`, `relay_aprobaciones`, `relay_pausas`).
  - `scheduler.py`: programador local; corre recetas vencidas solo con una extensión conectada.
  - `cli.py`: `serve`, `run <receta>`, `approve <huella>`, `resume <receta>`, `status`.
- **Recetas** (`relay/recipes/*.json`): `bci_ofertas`, `latam_ofertas`, `practica_formulario`.
- **Destino del asistente**: `asistente/relay_destino.py` convierte filas leídas al modelo de 002.
- **Pruebas**: unitarias del servidor, motor y programador con un navegador falso; Playwright con la extensión
  sin empaquetar en Chromium contra páginas locales (`relay/tests/fixtures/`), sin portales reales.

## Constitution check
- AGENTS.md: aprobación por contenido exacto, sesión iniciada por la persona, nada de credenciales, robots.txt,
  ritmo limitado, detenerse ante bloqueos. Fase tratada como `solid`.

## Files
- new: `relay/README.md`, `relay/extension/{manifest.json,background.js,banner.js,popup.html,popup.js}`,
  `relay/service/{__init__,ws,engine,store,scheduler,cli}.py`, `relay/recipes/*.json`,
  `relay/tests/**`, `asistente/relay_destino.py`
- changed: `pyproject.toml` (paquete `relay`, extra `relay-test` con Playwright), CI (job de Playwright)
