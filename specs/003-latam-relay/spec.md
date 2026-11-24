# 003 — Fichas de LATAM renderizadas vía relay en vivo

Status: ready | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "LATAM fichas renderizadas vía relay en vivo."
Relates: REQUERIMIENTOS.md (flujo 1, P0, «Prueba de integración para el piloto»), 001 (relay, receta
`latam_ofertas` por calibrar), 002 (modelo común `ofertas`)

Nivel de proceso: 4 — portal real que solo se puede leer en el Chrome de Ayelén (sesión y navegador de la persona),
selectores desconocidos hoy (el sitio responde 403 a navegadores automatizados sin sesión) y la fuente es nueva en la
tabla común.

## Goal
Con la extensión del relay en el Chrome de Ayelén, la receta `latam_ofertas` lee el listado y al menos una ficha
completa de LATAM (cargo, ubicación, enlace oficial, ID de origen, descripción con requisitos y fecha de publicación si
existe) y la guarda en `ofertas` con `fuente='latam'`. Si LATAM bloquea, la corrida se detiene con el motivo.

## Scenarios
### S1 — Calibrar con una página guardada (P1)
Given una copia del DOM renderizado del listado y de una ficha de LATAM (guardada por Ayelén desde su Chrome, sin datos
personales), when se ejecuta la receta contra esas páginas locales, then se leen cargo, enlace, ubicación, ID y
descripción con requisitos.
### S2 — Corrida en vivo (P1)
Given Chrome de Ayelén con la extensión conectada, when ejecuta `python -m relay.service.cli run relay/recipes/latam_ofertas.json`,
then la pestaña queda marcada, se leen el listado y hasta 5 fichas a ritmo humano y las ofertas quedan en `ofertas`.
### S3 — LATAM bloquea (P1)
Given que LATAM muestra «Access Denied», un CAPTCHA o una página de verificación, when corre la receta, then la corrida
queda «bloqueado» con la señal, la receta queda en pausa y no hay reintento automático.

## Requirements
- R1: THE SYSTEM SHALL leer de cada ficha de LATAM cargo, ubicación, enlace oficial, ID de origen, descripción y fecha
  de publicación cuando la página la muestre.
- R2: THE SYSTEM SHALL guardar las fichas en `ofertas` con `fuente='latam'` y `empresa='LATAM Airlines'`, con las reglas
  de 002 (una fila por ID, la descripción existente se conserva, la detección nunca reemplaza a la publicación).
- R3: WHEN el listado trae una oferta sin ficha legible THE SYSTEM SHALL guardarla «pendiente de descripción».
- R4: WHEN las fichas viven en otro dominio (por ejemplo, un sistema de reclutamiento externo) THE SYSTEM SHALL agregar
  ese dominio a `hosts` de la receta solo después de revisar su `robots.txt` y anotarlo en Decisions.
- R5: WHEN LATAM muestra un bloqueo THE SYSTEM SHALL detenerse sin intentar rodearlo (regla de 001, R7).

## Acceptance
- AC1 (R1, S1): la receta lee los campos de la copia guardada del listado y la ficha — check:
  `pytest relay/tests/test_extension.py -k latam_recorded`
- AC2 (R2): `guardar_latam` deja una fila por ID con `fuente='latam'`; la segunda importación sin descripción conserva la
  existente — check: `pytest tests/test_relay_destino.py -k latam`
- AC3 (R2, negativo): una ficha sin fecha de publicación deja `fecha_publicacion` vacía — check:
  `pytest tests/test_relay_destino.py -k latam_sin_fecha`
- AC4 (R3, negativo): una fila sin descripción queda «pendiente de descripción» — check:
  `pytest tests/test_relay_destino.py -k latam_pendiente`
- AC5 (R5, negativo): la copia guardada de la página «Access Denied» de LATAM deja la corrida «bloqueado» y no lee —
  check: `pytest relay/tests/test_extension.py -k latam_denied`
- AC6 (S2, manual): corrida en vivo en el Chrome de Ayelén con ≥1 ficha completa — check: observación anotada en
  `## Verify` (fecha, URL, cantidad de ofertas y fichas, estado de la corrida). Si LATAM bloquea, se anota el bloqueo
  y AC6 queda como «no accesible», no como aprobado.

## Edge cases
- La página carga ofertas con scroll infinito → la receta usa `paginate` con un máximo; nunca recorre sin límite.
- Ofertas fuera de Chile en el mismo listado → se guardan con su ubicación; el filtro por país queda para la persona.
- El ID no aparece en la ficha → se usa el último segmento del enlace (comportamiento actual de `guardar_latam`).

## Out of scope
- Postular en LATAM. Leer páginas que exijan iniciar sesión para ver la ficha (si pasa, se anota y se detiene).
- Cambiar el motor o la extensión del relay (si hace falta, se abre otra spec).

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- 2026-11-24: `https://www.latamairlines.com/cl/es/trabaja-con-nosotros` respondió 403 «Access Denied» a `curl` y a un
  Chromium automatizado sin sesión. No se intentó rodearlo. Se supone que en el Chrome normal de Ayelén carga; si no,
  la spec termina con LATAM marcado «no accesible» y la evidencia.
- Las copias guardadas se limpian antes de entrar al repositorio: sin nombres de personas, correos ni datos de sesión.

## Change log

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: corridas de `latam_ofertas` con estado «ok» — where: `relay_corridas` — when: +7 días de uso — success: ≥80 % —
  fail: <50 % (recalibrar selectores).
- O2: corridas «bloqueado» — where: `relay_corridas` — when: +7 días — success: 0 — fail: ≥1 (pausar la receta y
  revisar términos y ritmo antes de seguir).

## As-built
