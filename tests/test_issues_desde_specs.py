import importlib.util
import sys
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "issues_desde_specs.py"
_spec = importlib.util.spec_from_file_location("issues_desde_specs", RUTA)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["issues_desde_specs"] = mod
_spec.loader.exec_module(mod)

REPO = "dueña/proyecto"


def _specs(tmp_path: Path) -> Path:
    nivel4 = tmp_path / "003-latam"
    nivel4.mkdir()
    (nivel4 / "spec.md").write_text(
        "# 003 — Fichas de LATAM\n\nStatus: ready\n\nNivel de proceso: 4 — portal real.\n", encoding="utf-8"
    )
    (nivel4 / "tasks.md").write_text(
        "# 003 — Tasks\n\n"
        "- [ ] T001 Capturar copias — files: relay/tests/fixtures/*,\n"
        "  specs/003-latam/spec.md — check: los archivos existen\n"
        "- [~] T002 Calibrar selectores — files: relay/recipes/latam.json — check: AC1, AC5\n"
        "- [x] T003 Ya hecha — files: a.py — check: AC2\n\n"
        "| AC | Task |\n|---|---|\n| AC1 | T002 |\n",
        encoding="utf-8",
    )
    nivel3 = tmp_path / "004-recorrido"
    nivel3.mkdir()
    (nivel3 / "spec.md").write_text(
        "# 004 — Recorrido\n\nNivel de proceso: 3 — solo documentación.\n\n"
        "## Scenarios\n- [ ] T999 no es una tarea\n\n"
        "## Tasks\n- [ ] T001 Prueba de documentos — files:\n  tests/test_docs.py — check: AC1\n\n"
        "## As-built\n",
        encoding="utf-8",
    )
    (tmp_path / "_plantilla").mkdir()
    (tmp_path / "_plantilla" / "tasks.md").write_text("- [ ] T001 <tarea> — check: AC1\n", encoding="utf-8")
    return tmp_path


def test_lee_tareas_de_tasks_md_y_de_la_seccion_tasks(tmp_path: Path) -> None:
    tareas = mod.leer_todas(_specs(tmp_path))
    assert [t.tag for t in tareas] == ["003-T001", "003-T002", "003-T003", "004-T001"]
    t1 = tareas[0]
    assert t1.titulo == "Capturar copias"
    assert t1.files == "relay/tests/fixtures/*, specs/003-latam/spec.md"
    assert t1.check == "los archivos existen"
    assert (t1.nivel, t1.archivo, t1.spec_titulo) == ("4", "tasks.md", "Fichas de LATAM")
    assert (tareas[3].nivel, tareas[3].archivo, tareas[3].check) == ("3", "spec.md", "AC1")


def test_no_lee_plantilla_ni_tareas_fuera_de_la_seccion(tmp_path: Path) -> None:
    tags = [t.tag for t in mod.leer_todas(_specs(tmp_path))]
    assert "004-T999" not in tags
    assert not any(t.startswith("_pl") for t in tags)


def test_crea_issues_pendientes_con_etiquetas(tmp_path: Path) -> None:
    acciones = mod.planificar(mod.leer_todas(_specs(tmp_path)), [], REPO)
    por_tag = {a["tag"]: a for a in acciones}
    assert set(por_tag) == {"003-T001", "003-T002", "004-T001"}  # T003 is done: no issue
    assert por_tag["003-T001"]["titulo"] == "[003-T001] Capturar copias"
    assert por_tag["003-T001"]["etiquetas"] == ["spec:003", "nivel:4", "estado:libre"]
    assert por_tag["003-T002"]["etiquetas"][-1] == "estado:en-curso"
    cuerpo = por_tag["004-T001"]["cuerpo"]
    assert f"https://github.com/{REPO}/blob/main/specs/004-recorrido/spec.md" in cuerpo
    assert "> T001 Prueba de documentos" in cuerpo and "Check: AC1" in cuerpo


def test_es_idempotente_y_no_duplica(tmp_path: Path) -> None:
    tareas = mod.leer_todas(_specs(tmp_path))
    creadas = mod.planificar(tareas, [], REPO)
    issues = [
        {"number": n, "title": a["titulo"], "body": a["cuerpo"], "state": "OPEN",
         "labels": [{"name": e} for e in a["etiquetas"]]}
        for n, a in enumerate(creadas, start=1)
    ]
    assert mod.planificar(tareas, issues, REPO) == []


def test_actualiza_sin_tocar_estado_ni_reabrir_cerrados(tmp_path: Path) -> None:
    tareas = mod.leer_todas(_specs(tmp_path))
    issues = [
        {"number": 7, "title": "[003-T001] título viejo", "body": "viejo", "state": "OPEN",
         "labels": [{"name": "estado:en-curso"}]},
        {"number": 9, "title": "[003-T001] duplicado manual", "body": "", "state": "OPEN", "labels": []},
        {"number": 8, "title": "[003-T002] cerrado", "body": "", "state": "CLOSED", "labels": []},
    ]
    acciones = mod.planificar(tareas, issues, REPO)
    actualizar = [a for a in acciones if a["accion"] == "actualizar"]
    assert len(actualizar) == 1 and actualizar[0]["numero"] == 7  # lowest number wins over the duplicate
    assert actualizar[0]["etiquetas"] == ["spec:003", "nivel:4"]
    assert not any(e.startswith("estado:") for e in actualizar[0]["etiquetas"])
    assert not any(a["tag"] in {"003-T001", "003-T002"} for a in acciones if a["accion"] == "crear")


def test_titulo_largo_se_recorta() -> None:
    tarea = mod.Tarea(
        "005", "005-x", "X", "4", "tasks.md", "T001", " ", "a" * 300, "- [ ] T001 ...", None, None
    )
    titulo = mod.titulo_issue(tarea)
    assert len(titulo) == mod.MAX_TITULO and titulo.startswith("[005-T001] ") and titulo.endswith("…")
