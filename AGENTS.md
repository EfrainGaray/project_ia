# Asistente de postulaciones — reglas para agentes (Codex, Claude Code y otros)

Lee primero `README.md` y `REQUERIMIENTOS.md` (historia de usuario, criterios de aceptación y fases P0–P3).

## Cómo trabajar
- Primer paso siempre: **Triaje (Organic Driven Development, Gentle-AI)**. Elige el nivel de proceso: 1 directo (texto o valor,
  un archivo) · 2 error (prueba que falla primero, luego el arreglo) · 3 mini-spec (comportamiento nuevo acotado: un `spec.md`
  con criterios, su verificación y un caso negativo) · 4 spec completa (`spec.md` + `plan.md` + `tasks.md`). Decide por archivos
  tocados, riesgo, si lo ve una persona, si es reversible y qué tan entendido está. Portales, envío de postulaciones, datos
  personales y formatos públicos (esquema SQLite, recetas, protocolo del relay) son nivel ≥ 3. Escala, nunca bajes de nivel en
  silencio. Criterios completos en `specs/README.md`.
- Specs en `specs/NNN-slug/` (índice y flujo en `specs/README.md`, plantilla en `specs/_plantilla/`): lee spec → plan → tasks;
  toma una tarea con `[~] (agente: nombre)`; pruebas primero; corre el `check:` de cada criterio y pega la evidencia en la PR;
  una tarea por PR; el enfoque de `plan.md` está bloqueado (si no estás de acuerdo, detente y explícalo); cierra con
  `## As-built`.
- Cada criterio de aceptación de `REQUERIMIENTOS.md` que implementes tiene su prueba en `tests/` con un caso negativo.
- Antes de cada commit: `ruff check .`, `mypy app.py itau.py asistente relay tests` y `pytest` en verde. CI corre lo mismo.
- Commits atómicos con conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).

## Reglas del dominio (no negociables)
- Nada se envía a un portal sin aprobación explícita de la persona para ese contenido exacto; si cambia, se vuelve a aprobar.
- La persona inicia sesión directamente en cada portal: el código nunca guarda contraseñas, tokens ni sesiones.
- El CV real, el perfil privado y la base `*.sqlite3` quedan fuera del repositorio (`privado/` está en `.gitignore`).
  Los ejemplos y las pruebas usan datos ficticios.
- Lectores de portales: respetar `robots.txt` y términos de uso, ritmo limitado, detenerse y mostrar el código si el portal rechaza.
  No evadir bloqueos ni detección de bots.
- Una cita del aviso siempre es literal; una recomendación de CV nunca certifica que se cumplan los requisitos.

## Reservar una tarea (issues)

Cada tarea de una spec tiene un *issue* titulado `[NNN-T00X] título`, con etiquetas `spec:NNN`, `nivel:N` y `estado:libre |
en-curso | en-revision`. Se crean o actualizan con `python scripts/issues_desde_specs.py` (agrega `--dry-run` para ver los cambios sin
escribir). El script es idempotente: no duplica issues ni toca los estados ni las asignaciones.

Antes de empezar:
1. Revisa que no tengas otro issue en `estado:en-curso`: **un agente, una tarea a la vez**.
2. Si el issue ya está en curso o tiene a alguien asignado, elige otro.
3. Comenta «Tomo esta tarea (agente: tu-nombre)», asígnate y cambia la etiqueta a `estado:en-curso`.
4. Trabaja en la rama `tarea/NNN-T00X-descripcion-corta`; el PR dice `Closes #N` y pasa el issue a `estado:en-revision`.
5. Si dejas la tarea, coméntalo, quítate la asignación y vuelve a `estado:libre`.

