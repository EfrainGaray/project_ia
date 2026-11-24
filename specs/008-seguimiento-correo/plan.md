# 008 — Plan

## Approach (locked)
- `asistente/correo.py` con la biblioteca estándar: `email` (`BytesParser(policy=default)`) para `.eml` y `mailbox.mbox`
  para `.mbox`; `html.parser` para pasar HTML a texto.
- Reglas en un diccionario por clase: remitentes conocidos por fuente (por ejemplo, dominios de los portales), frases
  de asunto y cuerpo («hemos recibido tu postulación», «entrevista», «no continuarás en el proceso»). La primera frase
  que calza es la cita.
- Asociación: empresa por dominio del remitente o nombre en el texto; cargo o `id_origen` contra `candidaturas` (005).
- Tabla `correo_eventos` (huella del archivo única, candidatura nullable, clase, cita, fecha, remitente, asunto, estado
  `asociado` / `por_revisar` / `confirmado`).
- `confirmar <evento>` llama a `asistente.candidaturas.marcar_envio("enviado", comprobante=...)` para confirmaciones o
  solo marca el evento para entrevistas y rechazos.
- CLI: `python -m asistente.correo importar <carpeta|archivo>`, `pendientes`, `confirmar <id>`.

## Constitution check
- AGENTS.md: sin credenciales ni conexión a la cuenta, datos mínimos, nada cambia sin confirmación, pruebas con
  correos ficticios, la base fuera del repositorio. Fase `solid`.

## Files
- new: `asistente/correo.py`, `tests/test_correo.py`, `tests/fixtures/correo/*.eml`, `tests/fixtures/correo/muestra.mbox`
- changed: `README.md`, `REQUERIMIENTOS.md` (estado actual)
