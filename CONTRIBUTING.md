# Cómo colaborar

Gracias por ayudar con el asistente de postulaciones. Esta guía explica cómo proponer cambios para que la dueña del proyecto los revise
y apruebe.

## Antes de empezar
- Lee `README.md`, `REQUERIMIENTOS.md` (historia de usuario, criterios de aceptación y fases P0–P3) y `AGENTS.md` (reglas del proyecto,
  también para agentes de código).
- Abre o comenta un *issue* con lo que quieres hacer. Para fuentes nuevas, envío de postulaciones o datos personales, acuerda el enfoque
  antes de escribir código.

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

## Flujo de trabajo
1. Haz un *fork* y crea una rama desde `main` con un nombre descriptivo: `feat/p0-bci`, `fix/itau-fecha`, `docs/requerimientos`.
2. Elige el nivel de proceso según el tamaño del cambio (ver `AGENTS.md`): un arreglo de texto va directo; un error empieza con una
   prueba que falla; un comportamiento nuevo lleva una mini-spec con criterios y un caso negativo.
3. Agrega o actualiza pruebas en `tests/`. Las pruebas no consultan portales reales: usan HTML guardado y datos ficticios.
4. Corre los controles antes de cada commit:
   ```sh
   ruff check . && mypy app.py itau.py tests && pytest
   ```
5. Haz commits pequeños con [conventional commits](https://www.conventionalcommits.org/es/): `feat:`, `fix:`, `test:`, `docs:`,
   `chore:`, `refactor:`.
6. Abre un *pull request* hacia `main` usando la plantilla: qué cambia, cómo probarlo, qué criterio de `REQUERIMIENTOS.md` cubre y qué
   queda pendiente. CI debe quedar en verde.
7. La dueña del proyecto revisa y decide. Nadie hace *merge* de su propio cambio.

## Reglas que no se negocian
- Nunca se envía una postulación sin la aprobación explícita de la persona para ese contenido exacto.
- La persona inicia sesión directamente en cada portal. No se guardan contraseñas, *cookies*, tokens ni sesiones.
- El CV real, el perfil privado y las bases `*.sqlite3` nunca entran al repositorio (`privado/` está en `.gitignore`).
- Los lectores de portales respetan `robots.txt` y los términos de uso, limitan el ritmo y se detienen ante un rechazo o un CAPTCHA.
  No se evaden bloqueos ni la detección de bots.
- Una cita del aviso es siempre literal. Una recomendación de CV no certifica que se cumplan los requisitos.

## Reportar un problema
Incluye qué hiciste, qué esperabas, qué pasó y, si aplica, la fuente y la fecha. Nunca pegues datos personales reales ni credenciales.
