## Qué cambia

## Criterio de `REQUERIMIENTOS.md` que cubre

## Cómo probarlo
```sh
ruff check . && mypy app.py itau.py tests && pytest
```

## Pendiente o riesgos

- [ ] Pruebas nuevas o actualizadas, con un caso negativo
- [ ] Sin datos personales reales, credenciales ni bases `*.sqlite3`
- [ ] Sin consultas a portales reales en las pruebas
