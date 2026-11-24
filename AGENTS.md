# Asistente de postulaciones — reglas para agentes (Codex, Claude Code y otros)

Lee primero `README.md` y `REQUERIMIENTOS.md` (historia de usuario, criterios de aceptación y fases P0–P3).

## Cómo trabajar
- Antes de cambiar código, elige el nivel de proceso: 1 directo (texto o valor, un archivo) · 2 error (prueba que falla primero,
  luego el arreglo) · 3 mini-spec (comportamiento nuevo: objetivo, criterios con su verificación y un caso negativo) · 4 spec
  completa (fuentes nuevas, envío de postulaciones, datos personales). Nunca bajes de nivel en silencio.
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
