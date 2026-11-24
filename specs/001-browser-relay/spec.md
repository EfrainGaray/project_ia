# 001 — Relay de navegador propio: recetas en el Chrome de la persona

Status: verifying | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 8bdc18c
Request: "Construir nuestra propia extensión: ejecutar recetas por portal (abrir página, esperar, leer campos,
paginar, completar un formulario hasta una VISTA PREVIA) dentro del Chrome donde la persona ya inició sesión,
con un programador local, a ritmo humano, guardando los resultados en el mismo SQLite."
Relates: REQUERIMIENTOS.md (flujo 1 y 4, P0 y P2), 002 (modelo común de ofertas)

Nivel de proceso: 4 (envío de postulaciones y sesiones de la persona, AGENTS.md).

## Goal
Una extensión de Chrome (MV3) y un servicio local en Python, conectados por WebSocket en `127.0.0.1`, ejecutan
recetas declarativas en una pestaña visible del Chrome de la persona, guardan lo leído en SQLite y nunca envían
nada sin una aprobación ligada al contenido exacto.

## Scenarios
### S1 — Leer ofertas en el navegador de la persona (P1)
Given Chrome abierto con la extensión conectada, when el programador ejecuta la receta de Bci, then se abre una
pestaña marcada (insignia y franja), se leen el listado, la paginación y las fichas a ritmo humano, y las ofertas
quedan en la tabla `ofertas`.
### S2 — Portal que necesita renderizado (P1)
Given un portal que arma su contenido con JavaScript (LATAM), when corre su receta, then espera los selectores
renderizados y lee los campos; si el portal muestra un bloqueo, la corrida se detiene con el motivo.
### S3 — Formulario hasta la vista previa (P1)
Given un formulario de práctica, when corre la receta, then se completan los campos, se muestra la vista previa,
se guarda el contenido exacto con su huella SHA-256 como «esperando aprobación» y no se envía.
### S4 — Enviar solo lo aprobado (P2)
Given una aprobación para una huella, when la receta pide enviar, then el servicio vuelve a leer el formulario;
si la huella coincide hace clic en enviar, si cambió algo se detiene y pide una nueva aprobación.
### S5 — Detener (P1)
Given una corrida en curso, when la persona pulsa «Detener» en la franja o en la ventana de la extensión, then
la extensión deja de aceptar comandos, quita la marca y el servicio registra la corrida como detenida.

## Requirements
- R1: THE SYSTEM SHALL ejecutar recetas declarativas (JSON) con pasos `open`, `wait`, `read`, `click`,
  `paginate`, `fill`, `preview`, `submit` y `save`.
- R2: THE SYSTEM SHALL operar solo en pestañas que la propia extensión abrió en la sesión y solo en los dominios
  que declara la receta.
- R3: WHILE una pestaña está siendo controlada THE SYSTEM SHALL mostrar una insignia en el ícono y una franja
  visible en la página con un botón «Detener».
- R4: WHEN la persona pulsa «Detener» THE SYSTEM SHALL rechazar todo comando posterior hasta que la persona la
  reactive desde la ventana de la extensión.
- R5: THE SYSTEM SHALL esperar entre pasos un retardo aleatorio dentro de un rango de ritmo humano (por defecto
  2–6 s) y nunca menos que el `Crawl-delay` del portal.
- R6: WHEN un paso abre una URL THE SYSTEM SHALL consultar `robots.txt` del dominio y omitirla si está prohibida.
- R7: WHEN la página muestra señales de CAPTCHA o bloqueo (iframes o elementos de reCAPTCHA, hCaptcha, Turnstile,
  textos de acceso denegado) THE SYSTEM SHALL detener la corrida, registrar la señal y pausar la receta hasta
  que la persona la reanude. Nunca intenta resolverlo ni rodearlo.
- R8: THE SYSTEM SHALL no leer ni guardar contraseñas, cookies, tokens ni campos `type=password`; la extensión
  no pide los permisos `cookies` ni `debugger`.
- R9: WHEN una receta llega a `preview` THE SYSTEM SHALL guardar el contenido leído del formulario y su huella
  SHA-256 como «esperando aprobación» y no enviar.
- R10: WHEN una receta llega a `submit` THE SYSTEM SHALL enviar solo si existe una aprobación para la huella del
  contenido leído en ese momento; si no, se detiene en «esperando aprobación».
- R11: THE SYSTEM SHALL ejecutar las recetas programadas solo mientras haya una extensión conectada y registrar
  cada corrida (inicio, fin, estado, motivo).
- R12: THE SYSTEM SHALL aceptar conexiones solo desde `127.0.0.1` con origen `chrome-extension://` y un token de
  emparejamiento; la extensión solo obedece a un servicio que prueba conocer ese token.

## Acceptance
- AC1 (R1, S3): la receta del formulario de práctica llega a la vista previa y guarda contenido y huella —
  check: `pytest relay/tests/test_extension.py -k practice_form`
- AC2 (R9, R10, negativo): sin aprobación, el formulario no se envía (el servidor de prueba no recibe POST) —
  check: `pytest relay/tests/test_extension.py -k not_submitted`
- AC3 (R10, S4): con aprobación de la huella se envía; si un campo cambia después de aprobar, se detiene —
  check: `pytest relay/tests/test_extension.py -k approved` y `pytest relay/tests/test_engine.py -k changed`
- AC4 (R1, S1): la receta de Bci sobre páginas locales con el DOM real lee listado, paginación y ficha y guarda
  en `ofertas` — check: `pytest relay/tests/test_extension.py -k bci`
- AC5 (S2): la receta de LATAM espera contenido renderizado por JavaScript — check:
  `pytest relay/tests/test_extension.py -k rendered`
- AC6 (R7, negativo): una página con un iframe de reCAPTCHA detiene la corrida con estado «bloqueado» y no lee —
  check: `pytest relay/tests/test_extension.py -k captcha` y `pytest relay/tests/test_engine.py -k blocked`
- AC7 (R4, S5): «Detener» hace que la extensión rechace comandos y quite la franja — check:
  `pytest relay/tests/test_extension.py -k kill`
- AC8 (R3): la pestaña controlada muestra la franja y la insignia — check:
  `pytest relay/tests/test_extension.py -k banner`
- AC9 (R2, negativo): un `open` fuera de los dominios de la receta se rechaza sin navegar — check:
  `pytest relay/tests/test_engine.py -k host`
- AC10 (R6, negativo): una URL prohibida por `robots.txt` no se abre — check: `pytest relay/tests/test_engine.py -k robots`
- AC11 (R5): los retardos están en el rango configurado y respetan el `Crawl-delay` — check:
  `pytest relay/tests/test_engine.py -k delay`
- AC12 (R11): sin extensión conectada el programador no corre nada; con extensión corre lo vencido — check:
  `pytest relay/tests/test_scheduler.py`
- AC13 (R12, negativo): una conexión sin token u origen distinto se rechaza; un servicio sin token no recibe
  obediencia — check: `pytest relay/tests/test_server.py` y `pytest relay/tests/test_extension.py -k token`
- AC14 (R8): el manifiesto no pide `cookies` ni `debugger` y la lectura omite campos de contraseña — check:
  `pytest relay/tests/test_extension.py -k password` y `pytest relay/tests/test_engine.py -k manifest`

## Success criteria
- SC1: en el Chrome real de la persona, la receta de Bci deja ≥10 ofertas con descripción en una corrida.
- SC2: cero envíos sin aprobación registrada (verificable en la tabla de aprobaciones).

## Edge cases
- Chrome cierra el service worker: la conexión se reabre sola; una corrida a medias queda «interrumpida».
- La persona cierra la pestaña controlada: la corrida termina «interrumpida».
- Selectores que no aparecen dentro del tiempo: la corrida se detiene con «estructura cambió: <selector>».
- La persona no inició sesión en un portal que lo exige: la receta lo detecta por un selector y se detiene.

## Out of scope
- Envío real a un portal de empleo (solo práctica en esta entrega; Banco de Chile se evalúa después).
- Resolver o rodear CAPTCHA, cambiar huellas del navegador, rotar IP o simular eventos de entrada «confiables».
- Publicar la extensión en Chrome Web Store; empaquetado para otros navegadores.

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- Se construye una extensión propia; no se porta openclaw ni PhantomRelay. Del relay de openclaw solo se tomó la
  idea de un servicio local que manda comandos a la extensión por WebSocket.
- `chrome.scripting` y `chrome.tabs` en lugar de `chrome.debugger`: alcanza para leer el DOM, hacer clic y
  completar campos, pide menos permisos y no genera eventos de entrada «confiables» (no se hace pasar por una
  persona). Contracara: algunos sitios ignoran clics sintéticos; en ese caso la receta se detiene.
- Bci (2026-11-24): selectores tomados del DOM renderizado real (`.offer-hit-card`, `.sk-pagination-navigation`,
  `.single-offer .label-subtitle`).
- LATAM (2026-11-24): `https://www.latamairlines.com/cl/es/trabaja-con-nosotros` responde 403 «Access Denied» a
  `curl` y a un navegador automatizado sin sesión. No se intentó rodearlo. La receta de LATAM queda con selectores
  por calibrar en el Chrome de la persona; las pruebas usan una página local que se renderiza con JavaScript.
- El servicio usa solo la biblioteca estándar (WebSocket RFC 6455 mínimo, solo texto) para que `relay/` se pueda
  copiar a otros proyectos sin dependencias.
- Genérico: `relay/` no importa nada del asistente; los resultados se entregan a «destinos» (`save`) que cada
  proyecto registra. El asistente registra el destino `ofertas`.

## Change log
- 2026-11-24 — `save` guarda también las filas cuya ficha falló (quedan «pendiente de descripción» en vez de
  perderse); destinos reciben `(filas, receta, base_de_datos)` — sin cambio de método.

## Verify
Verdict: partial (2026-11-24). AC1–AC14: cada `check:` pasa (91 pruebas en total, 10 con la extensión cargada en
Chromium sin interfaz; ruff y mypy limpios; Python 3.10 y 3.13). Mutaciones: aceptar un servicio sin prueba de token
o ignorar el iframe de reCAPTCHA en la extensión hace fallar AC13 y AC6.
Prueba real de la receta de Bci (extensión en Chromium, 2 páginas, 2 fichas, ritmo 2–4 s): 18 ofertas leídas,
2 fichas completas con «Requisitos», corrida «ok».
No verificado: SC1 y SC2 en el Chrome de la persona; la receta de LATAM contra el sitio real (responde 403 a
navegadores automatizados sin sesión); el comportamiento del service worker tras horas de inactividad.

## Observe (define now, read after ship)
- O1: corridas programadas con estado «ok» — where: tabla `relay_corridas` — when: +7 días de uso — success: ≥80 %
  — fail: <50 % (revisar selectores).
- O2: corridas «bloqueado» — where: `relay_corridas` — when: +7 días — success: 0 — fail: ≥1 en un portal (pausar
  esa receta y revisar términos o ritmo).
- O3: envíos sin aprobación — where: `relay_aprobaciones` y la persona — when: cada uso — success: 0 — fail: 1.

## As-built
