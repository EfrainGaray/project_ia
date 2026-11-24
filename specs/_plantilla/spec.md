# NNN — Título corto

Status: draft | Phase: solid | Domain: code | Created: AAAA-MM-DD | Base commit: <sha>
Request: "Pedido original, literal."
Relates: REQUERIMIENTOS.md (sección o criterio), specs relacionadas

Nivel de proceso: N (por qué, según el triaje de `specs/README.md`).

## Goal
Una o dos frases: qué queda funcionando y para quién.

## Scenarios
### S1 — Nombre (P1)
Given <estado inicial>, when <acción>, then <resultado observable>.

## Requirements
- R1: THE SYSTEM SHALL <comportamiento>.
- R2: WHEN <evento> THE SYSTEM SHALL <comportamiento>.

## Acceptance
- AC1 (R1, S1): <resultado esperado> — check: `pytest tests/test_x.py -k caso`
- AC2 (R2, negativo): <entrada inválida o fallo> → <resultado> — check: `pytest tests/test_x.py -k negativo`

## Edge cases
- <caso borde> → <comportamiento>.

## Out of scope
- <lo que no se hace en esta spec>.

## Method (locked)
Nivel 4: see plan.md → Approach. Nivel 3: describir aquí el enfoque en 2–4 líneas.
Changing it requires a Change log line here.

## Decisions & assumptions
- <supuesto o decisión, con fecha y evidencia si viene de una prueba en vivo>.

## Change log
- AAAA-MM-DD — <cambio> — <motivo>.

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: <señal de uso real> — where: <tabla o archivo> — when: <fecha o plazo> — success: <umbral> — fail: <umbral>.

## Tasks
(Solo nivel 3; en nivel 4 van en tasks.md.)
- [ ] T001 <tarea> — files: <archivos> — check: AC1, AC2

## As-built
(Se completa al cerrar: commits, ADDED / CHANGED / DROPPED, fuera de la spec, no verificado.)
