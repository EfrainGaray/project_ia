# Asistente de postulaciones

Primer prototipo de portafolio. Convierte una oferta en requisitos con citas,
los compara con evidencia del perfil y recomienda un CV. La persona revisa el
PDF y elige qué versión registrar en SQLite.

## Demo local

Requiere Python 3.10 o posterior. Usa la biblioteca estándar.

```sh
python app.py
python app.py --elegir datos --motivo "Destaca mi experiencia analítica"
```

Abre cualquiera de los PDF que muestra el primer comando para previsualizarlo.
La segunda instrucción guarda el nombre y el hash del PDF, la recomendación,
la elección y su motivo. Cada elección agrega una fila al historial local.

Esta demo reproduce la referencia manual de una ficha pública de Itaú y usa
un perfil ficticio. Un requisito respaldado y obligatorio aporta dos puntos a
cada CV que contiene la evidencia. Los otros requisitos respaldados aportan
un punto. Si ningún CV obtiene puntos o hay empate arriba, se pide elegir sin
recomendación.

## Análisis con IA

Configura `OPENAI_API_KEY` en tu entorno local y ejecuta
`python app.py --modelo NOMBRE_DEL_MODELO` con un modelo habilitado en tu cuenta.
Para analizar otra vacante, pasa un archivo de texto con `--oferta`. Puedes
pasar `--perfil privado/perfil.json` con el formato de `demo/perfil.json`. Las
rutas de los PDF son relativas al JSON. Incluye solo la evidencia profesional
que quieras pasar a la API. Los PDF se mantienen locales.

Compara la salida del modelo con `demo/referencia.json` para revisar la
clasificación de SQL Server y Python, los requisitos omitidos y los casos en
que la evidencia es insuficiente. La validación comprueba las citas y las
referencias al perfil. La correspondencia entre ambos requiere revisión humana.

Esta etapa termina al registrar la versión elegida. La lectura automática
de portales y el envío quedan para una fase posterior.
