# Relay de navegador

Ejecuta «recetas» (abrir una página, esperar, leer campos, paginar, completar un formulario hasta una vista
previa) dentro del Chrome de la persona, donde ella ya inició sesión, y guarda lo leído en SQLite. Tiene dos
partes que hablan por WebSocket en `127.0.0.1`:

- `extension/`: extensión de Chrome (Manifest V3). Solo actúa en la pestaña que ella misma abre, la marca con la
  insignia `AUTO` y una franja roja con el botón **Detener**, y no pide permisos de cookies ni de depuración.
- `service/`: servicio local en Python, solo con la biblioteca estándar. Ejecuta las recetas, consulta
  `robots.txt`, espera entre pasos un tiempo aleatorio de ritmo humano, se detiene ante un CAPTCHA o un bloqueo
  y guarda corridas, resultados y aprobaciones.

Especificación: `specs/001-browser-relay/`. La carpeta no depende del asistente; cada proyecto registra sus
destinos de resultados (el asistente usa `asistente/relay_destino.py`).

## Reglas

- La persona inicia sesión directamente en cada portal. El relay no lee ni guarda contraseñas, cookies, tokens
  ni campos ocultos.
- Nunca se envía nada sin aprobación. `preview` guarda el contenido exacto del formulario y su huella SHA-256 como
  «esperando aprobación». `submit` vuelve a leer el formulario y solo envía si esa huella fue aprobada; si cambió
  un campo, la huella cambia y se pide una nueva aprobación. Un contenido ya enviado no se vuelve a enviar.
- Si aparece una verificación (reCAPTCHA, hCaptcha, Turnstile) o un texto de acceso denegado, la corrida se
  detiene y la receta queda en pausa hasta que la persona la reanude. El relay no intenta resolverlo ni rodearlo.
- **Detener** (en la franja o en la ventana de la extensión) hace que la extensión rechace todo comando hasta
  que la persona pulse **Reactivar**.

## Uso

1. Instala el proyecto: `python3 -m pip install -e .`
2. Carga la extensión: `chrome://extensions` → activa «Modo de desarrollador» → «Cargar descomprimida» → elige
   `relay/extension`.
3. Empareja: `python3 -m relay.service.cli token` muestra el token. Pégalo en la ventana de la extensión y guarda.
4. Corre una receta una vez, con Chrome abierto:

```sh
python3 -m relay.service.cli --destinos asistente.relay_destino:DESTINOS run relay/recipes/bci_ofertas.json
```

5. Programador local (corre las recetas vencidas solo mientras Chrome y la extensión están conectados):

```sh
python3 -m relay.service.cli --destinos asistente.relay_destino:DESTINOS serve relay/recipes/agenda.example.json
```

6. Formulario: revisa el contenido exacto con `show <huella>` y apruébalo con `approve <huella>`. Si una receta
   quedó en pausa por un bloqueo: `resume <receta>`.

## Recetas incluidas

| Receta | Estado |
|---|---|
| `bci_ofertas.json` | Selectores del sitio real (2026-11-24). Lee listado, paginación y fichas; guarda en `ofertas`. |
| `latam_ofertas.json` | Por calibrar: el sitio rechaza navegadores automatizados sin sesión (403). Ajustar los selectores en el Chrome de la persona. |
| `practica_formulario.json` | Formulario de práctica local hasta la vista previa; envío solo con huella aprobada. |

Pasos disponibles: `open`, `wait`, `read` (con `items`, `selector`, `attr`, `heading`, `label`), `click`,
`paginate`, `foreach`, `fill`, `preview`, `submit` y `save`.

## Pruebas

```sh
python3 -m pip install -e ".[dev,relay-test]"
python3 -m playwright install chromium
pytest relay/tests
```

`test_extension.py` carga la extensión sin empaquetar en Chromium y la prueba contra páginas locales de
`tests/fixtures/` (copias de la estructura de Bci, una página que se arma con JavaScript, el formulario de
práctica y una página con CAPTCHA). No consulta portales reales.
