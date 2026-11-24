# 002 — P0: lector público de Bci y modelo genérico de oferta

Status: verifying | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 8bdc18c
Request: "Primera entrega: tomar una ficha pública nueva de Bci o LATAM y cerrar el flujo hasta la recomendación."
Relates: REQUERIMIENTOS.md (P0, criterios de aceptación, «Prueba de integración para el piloto»)

Nivel de proceso: 4 (fuente nueva, AGENTS.md).

## Goal
Leer el listado público de Bci y al menos una ficha completa, guardarlas en SQLite con un modelo de oferta común a
todas las fuentes y llevar una ficha nueva hasta una recomendación de CV con citas usando el perfil ficticio.

## Scenarios
### S1 — Importar Bci (P1)
Given el portal público de Bci, when se ejecuta `python -m asistente.bci --detalles 1`, then quedan filas en `ofertas` con
cargo, empresa, ID de origen, fechas de publicación y detección, ubicación, enlace oficial y, para la ficha leída,
la descripción con requisitos.
### S2 — Importar dos veces (P1)
Given una oferta ya guardada con descripción, when se importa de nuevo solo el listado, then sigue habiendo una
fila, los datos del listado se actualizan, la descripción se conserva y la primera fecha de detección no cambia.
### S3 — Fallos visibles (P1)
Given un rechazo HTTP, una ficha que no llega o una fuente que falla, when se importa, then se registra fuente,
fecha, código y motivo; la oferta sin ficha queda «pendiente de descripción»; las otras fuentes siguen guardando.
### S4 — De la ficha a la recomendación (P1)
Given una ficha Bci guardada, when se ejecuta `python app.py --oferta-bd bci:<id> --reglas`, then se muestran
requisitos con su tipo y cita literal, la evidencia del perfil ficticio y un CV recomendado (o «sin preferencia»).

## Requirements
- R1: THE SYSTEM SHALL guardar cada oferta con fuente, id_origen, empresa, cargo, ubicación, fecha_publicacion,
  fecha_deteccion, enlace, descripcion y estado, con (fuente, id_origen) único.
- R2: WHEN se reimporta una oferta THE SYSTEM SHALL actualizar los datos y conservar descripción y fecha de
  detección existentes si la consulta nueva no las trae.
- R3: THE SYSTEM SHALL dejar fecha_publicacion vacía cuando la fuente no la entrega; nunca la llena con la detección.
- R4: WHEN una oferta no tiene descripción THE SYSTEM SHALL marcarla «pendiente de descripción».
- R5: WHEN una fuente o ficha falla THE SYSTEM SHALL registrar fuente, fecha, URL, código HTTP y motivo, conservar
  las filas previas y seguir con las demás fuentes y fichas.
- R6: THE SYSTEM SHALL consultar robots.txt, limitar el ritmo (≥1 s) y detenerse ante un rechazo; sin evasión.
- R7: WHEN se pide `--reglas` THE SYSTEM SHALL extraer requisitos con reglas de Python (tipo por sección o palabra
  «deseable», cita literal) y asociar evidencia por señales del perfil, sin preparar respuestas manuales.
- R8: WHEN la oferta elegida está «pendiente de descripción» THE SYSTEM SHALL decirlo y no recomendar.

## Acceptance
- AC1 (R1, S1): el listado grabado produce filas con todos los campos; la ficha 39410 trae «Requisitos» —
  check: `pytest tests/test_bci.py -k "listing or detail"`
- AC2 (R2, S2): segunda importación sin ficha conserva descripción y primera detección; actualiza el cargo —
  check: `pytest tests/test_ofertas.py -k reimport`
- AC3 (R3, negativo): una oferta sin fecha de publicación la deja vacía aunque haya detección —
  check: `pytest tests/test_ofertas.py -k publication`
- AC4 (R4, R5, S3): ficha que responde 404 → oferta pendiente y fallo con código 404 —
  check: `pytest tests/test_bci.py -k missing_detail`
- AC5 (R5, negativo): listado con HTTP 403 → fallo registrado, sin filas nuevas, filas previas intactas —
  check: `pytest tests/test_bci.py -k refused`
- AC6 (R5): una fuente que falla no impide que otra guarde — check: `pytest tests/test_ofertas.py -k other_sources`
- AC7 (R6, negativo): robots.txt que prohíbe la ruta → no se consulta — check: `pytest tests/test_bci.py -k robots`
- AC8 (R7, S4): la ficha 39410 da Python obligatorio respaldado con cita literal y recomienda un CV —
  check: `pytest tests/test_reglas.py`
- AC9 (R8, negativo): `--oferta-bd` de una oferta pendiente sale con error explicando «pendiente de descripción» —
  check: `pytest tests/test_app.py -k pending`
- AC10 (S1, manual): una corrida en vivo lee el listado y una ficha — check: observación anotada en
  «Decisions & assumptions» (URL, fecha, método).

## Edge cases
- Bci entrega HTML en lugar de JSON (ruta inexistente) → fallo «respuesta no es JSON».
- Fecha de publicación con formato distinto a dd/mm/aaaa → se guarda vacía y se anota, no se inventa.
- La ficha llega sin requisitos ni descripción → sigue pendiente.

## Out of scope
- Migrar `itau.py` a la tabla común (queda su tabla `ofertas_itau`; se hará en otra entrega).
- Coincidencias entre fuentes, LATAM (va por la extensión, spec 001), envío de postulaciones.
- Interfaz distinta de la terminal.

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- Prueba en vivo 2026-11-24: `https://trabajaenbci.cl/offers/` es una SPA. Sus datos vienen de la misma API pública que
  usa el sitio sin sesión: listado `POST https://trabajaenbci.cl/api/v3/bci_portals/_search` (JSON estilo
  Elasticsearch, 45 ofertas ese día, paginado con `size`/`from`) y ficha
  `GET https://trabajaenbci.cl/api/v3/bci_portals/proceso/<id>` (introducción, funciones, requisitos excluyentes y
  deseables). `robots.txt` no restringe rutas. Una ficha inexistente responde 404 con motivo en JSON.
- ID de origen = `postulation_process_id` (aparece en el enlace oficial `/offers/proceso/<id>`).
- Fecha de publicación = `published_at_date_text`; detección = momento de la importación (UTC, ISO).
- El listado trae nombres de jefatura y contraparte: no se guardan; en los fixtures se reemplazaron por
  «PERSONA FICTICIA».
- Los fixtures son respuestas reales grabadas (listado recortado a 3 ofertas); las pruebas no hacen llamadas en vivo.

## Change log
- 2026-11-24 — módulos nuevos en el paquete `asistente/` (no en la raíz) y `[tool.setuptools]` explícito en
  `pyproject.toml` — la autodetección de setuptools falla con más de un paquete en la raíz — sin cambio de método.

## Verify
Verdict: verified (2026-11-24, commit 0a23043). AC1–AC9: cada `check:` pasa (`pytest`, 54 pruebas; ruff y mypy
limpios). Mutaciones: quitar el `COALESCE` de la descripción o la consulta a robots.txt hace fallar AC2 y AC7.
AC10: corrida en vivo 2026-11-24 19:26 UTC, `python -m asistente.bci --paginas 1 --detalles 3` → 20 ofertas, 3
completas, 0 fallos, 8,8 s; la segunda corrida sin fichas conservó las 3 descripciones y la fecha de detección.
`app.py --oferta-bd bci:39393 --reglas` mostró requisitos con cita; `bci:39410` sin ficha salió con «pendiente de
descripción». No verificado: términos de uso del sitio (no se encontró una página de términos para el portal).

## Observe (define now, read after ship)
- O1: fichas completas por corrida en vivo — where: `SELECT estado, COUNT(*) FROM ofertas WHERE fuente='bci'` —
  when: primera semana de uso — success: ≥90 % «completa» con `--detalles` igual al total — fail: <70 %.
- O2: fallos de acceso — where: tabla `fallos` — when: misma semana — success: 0 rechazos 403/429 — fail: cualquiera
  (detenerse y revisar términos antes de seguir).

## As-built
