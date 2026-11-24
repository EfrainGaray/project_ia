# 003 — Tasks

Toma una tarea marcándola `[~] (agente: nombre)`; una tarea por PR; `[x]` solo con la evidencia del `check:` en la PR.

- [ ] T001 Capturar con Ayelén el listado, una ficha y (si aparece) la página de bloqueo; limpiar datos personales;
  anotar URL, fecha y dominios en Decisions — files: relay/tests/fixtures/latam_real/*, specs/003-latam-relay/spec.md —
  check: los archivos existen y `grep -EIn "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|[0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3}-[0-9kK]" relay/tests/fixtures/latam_real/*`
  no muestra correos ni RUT
- [ ] T002 Calibrar selectores de `latam_ofertas.json` contra las copias — files: relay/recipes/latam_ofertas.json,
  relay/tests/test_extension.py — check: AC1, AC5
- [ ] T003 Ajustar `guardar_latam` (empresa, fecha de publicación, pendiente) — files: asistente/relay_destino.py,
  tests/test_relay_destino.py — check: AC2, AC3, AC4
- [ ] T004 Corrida en vivo en el Chrome de Ayelén y anotarla en Verify; README con los pasos de calibración — files:
  specs/003-latam-relay/spec.md, relay/README.md — check: AC6

| AC | Task |
|---|---|
| AC1 | T002 |
| AC2 | T003 |
| AC3 | T003 |
| AC4 | T003 |
| AC5 | T002 |
| AC6 | T004 |
