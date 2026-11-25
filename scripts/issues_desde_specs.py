"""Create or update one GitHub issue per spec task, so agents can reserve tasks visibly.

Reads every ``specs/NNN-slug/tasks.md`` (or the ``## Tasks`` section of a level-3 ``spec.md``) and,
through the ``gh`` CLI, makes sure each pending task has an issue titled ``[NNN-T00X] title`` with the
labels ``spec:NNN``, ``nivel:N`` and ``estado:libre``. Idempotent: existing issues are matched by the
``[NNN-T00X]`` tag in the title and only their title, body and spec/level labels are refreshed;
``estado:*`` labels and assignees belong to the agents and are never touched. Tasks already marked
``[x]`` without an issue are skipped.

Usage: ``python scripts/issues_desde_specs.py [--dry-run] [--repo OWNER/REPO]``
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TAREA = re.compile(r"^- \[(?P<marca>[ ~x])\] (?P<id>T\d{3})\s+(?P<texto>.*)$")
PARTES = re.compile(r"^(?P<titulo>.*?)(?: — files: (?P<files>.*?))?(?: — check: (?P<check>.*))?$")
ETIQUETA = re.compile(r"^\[(?P<tag>\d{3}-T\d{3})\]")
NIVEL = re.compile(r"^Nivel de proceso: (?P<nivel>[1-4])", re.MULTILINE)
ESTADOS = {
    "estado:libre": ("0e8a16", "Tarea sin tomar"),
    "estado:en-curso": ("fbca04", "Un agente la está trabajando"),
    "estado:en-revision": ("1d76db", "PR abierta, esperando revisión"),
}
MAX_TITULO = 120


@dataclass(frozen=True)
class Tarea:
    spec: str  # "003"
    carpeta: str  # "003-latam-relay"
    spec_titulo: str
    nivel: str | None
    archivo: str  # "tasks.md" or "spec.md"
    id: str  # "T001"
    marca: str  # " ", "~" or "x"
    titulo: str
    linea: str
    files: str | None
    check: str | None

    @property
    def tag(self) -> str:
        return f"{self.spec}-{self.id}"


def _lineas_de_tareas(texto: str, solo_seccion: bool) -> list[str]:
    """Join each task line with its indented continuation lines."""
    tareas: list[str] = []
    dentro = not solo_seccion
    abierta = False
    for linea in texto.splitlines():
        if solo_seccion and linea.startswith("## "):
            dentro = linea.strip() == "## Tasks"
            continue
        if not dentro:
            continue
        if linea.startswith("- ["):
            tareas.append(linea.strip())
            abierta = True
        elif abierta and linea.startswith((" ", "\t")) and linea.strip():
            tareas[-1] += " " + linea.strip()
        else:
            abierta = False
    return tareas


def leer_tareas(carpeta: Path) -> list[Tarea]:
    spec_md = carpeta / "spec.md"
    if not spec_md.is_file():
        return []
    spec_texto = spec_md.read_text(encoding="utf-8")
    primera = spec_texto.splitlines()[0] if spec_texto else ""
    spec_titulo = primera.lstrip("# ").split(" — ", 1)[-1].strip()
    nivel = m.group("nivel") if (m := NIVEL.search(spec_texto)) else None
    tasks_md = carpeta / "tasks.md"
    if tasks_md.is_file():
        archivo, texto, solo_seccion = "tasks.md", tasks_md.read_text(encoding="utf-8"), False
    else:
        archivo, texto, solo_seccion = "spec.md", spec_texto, True
    lineas = _lineas_de_tareas(texto, solo_seccion)
    tareas = []
    for linea in lineas:
        if not (t := TAREA.match(linea)) or not (partes := PARTES.match(t.group("texto"))):
            continue
        tareas.append(
            Tarea(
                spec=carpeta.name[:3],
                carpeta=carpeta.name,
                spec_titulo=spec_titulo,
                nivel=nivel,
                archivo=archivo,
                id=t.group("id"),
                marca=t.group("marca"),
                titulo=partes.group("titulo").strip(),
                linea=linea,
                files=partes.group("files"),
                check=partes.group("check"),
            )
        )
    return tareas


def leer_todas(specs: Path) -> list[Tarea]:
    carpetas = sorted(p for p in specs.iterdir() if p.is_dir() and re.match(r"^\d{3}-", p.name))
    return [t for c in carpetas for t in leer_tareas(c)]


def titulo_issue(tarea: Tarea) -> str:
    titulo = f"[{tarea.tag}] {tarea.titulo}"
    return titulo if len(titulo) <= MAX_TITULO else titulo[: MAX_TITULO - 1].rstrip() + "…"


def cuerpo_issue(tarea: Tarea, repo: str) -> str:
    base = f"https://github.com/{repo}/blob/main/specs/{tarea.carpeta}"
    lineas = [
        f"Spec: [{tarea.spec} — {tarea.spec_titulo}]({base}/spec.md) · "
        f"tarea en [{tarea.archivo}]({base}/{tarea.archivo})",
        "",
        "Tarea:",
        "",
        f"> {tarea.linea.split('] ', 1)[-1]}",  # without "- [ ]", so GitHub shows no checkbox
        "",
        f"Check: {tarea.check or '(ver la spec)'}",
        "",
        "Antes de tomarla lee el flujo de reserva en "
        f"[specs/README.md](https://github.com/{repo}/blob/main/specs/README.md): "
        "una tarea en curso por agente, comenta «Tomo esta tarea (agente: nombre)», "
        f"pon `estado:en-curso`, rama `tarea/{tarea.tag}-<slug>` y «Closes #<este issue>» en la PR.",
        "",
        f"<!-- issues_desde_specs: {tarea.tag} -->",
    ]
    return "\n".join(lineas)


def etiquetas_base(tarea: Tarea) -> list[str]:
    etiquetas = [f"spec:{tarea.spec}"]
    if tarea.nivel:
        etiquetas.append(f"nivel:{tarea.nivel}")
    return etiquetas


def planificar(tareas: list[Tarea], issues: list[dict], repo: str) -> list[dict]:
    """Return the actions needed to bring the issues in line with the tasks (pure, no I/O)."""
    por_tag: dict[str, dict] = {}
    for existente in sorted(issues, key=lambda i: i["number"]):
        if (m := ETIQUETA.match(existente["title"])) and m.group("tag") not in por_tag:
            por_tag[m.group("tag")] = existente
    acciones: list[dict] = []
    for tarea in tareas:
        titulo, cuerpo, base = titulo_issue(tarea), cuerpo_issue(tarea, repo), etiquetas_base(tarea)
        issue = por_tag.get(tarea.tag)
        if issue is None:
            if tarea.marca == "x":
                continue
            estado = "estado:en-curso" if tarea.marca == "~" else "estado:libre"
            acciones.append({"accion": "crear", "tag": tarea.tag, "titulo": titulo, "cuerpo": cuerpo,
                             "etiquetas": [*base, estado]})
            continue
        if issue.get("state", "OPEN").upper() != "OPEN":
            continue
        actuales = {e["name"] for e in issue.get("labels", [])}
        faltan = [e for e in base if e not in actuales]
        if issue["title"] != titulo or issue.get("body", "") != cuerpo or faltan:
            acciones.append({"accion": "actualizar", "tag": tarea.tag, "numero": issue["number"],
                             "titulo": titulo, "cuerpo": cuerpo, "etiquetas": faltan})
    return acciones


def _gh(gh: str, *args: str) -> str:
    return subprocess.run([gh, *args], check=True, capture_output=True, text=True).stdout  # noqa: S603


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dry-run", action="store_true", help="show what would change, without writing")
    parser.add_argument("--repo", help="OWNER/REPO (default: the repository of the current directory)")
    args = parser.parse_args(argv)
    gh = shutil.which("gh")
    if gh is None:
        print("Falta el CLI de GitHub (gh): https://cli.github.com", file=sys.stderr)
        return 1
    repo = args.repo or json.loads(_gh(gh, "repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
    issues = json.loads(_gh(gh, "issue", "list", "-R", repo, "--state", "all", "--limit", "1000",
                            "--json", "number,title,body,labels,state"))
    tareas = leer_todas(RAIZ / "specs")
    acciones = planificar(tareas, issues, repo)
    if not acciones:
        print(f"Sin cambios: {len(tareas)} tareas leídas, issues al día.")
        return 0
    etiquetas = {e for a in acciones for e in a["etiquetas"]}
    for accion in acciones:
        destino = f"#{accion['numero']}" if accion["accion"] == "actualizar" else "nuevo"
        print(f"{accion['accion']} {destino}: {accion['titulo']} {accion['etiquetas']}")
    if args.dry_run:
        return 0
    for nombre in sorted(etiquetas | set(ESTADOS)):
        color, descripcion = ESTADOS.get(nombre, ("c5def5" if nombre.startswith("spec:") else "d4c5f9", ""))
        _gh(gh, "label", "create", nombre, "-R", repo, "--color", color, "--description", descripcion,
            "--force")
    for accion in acciones:
        opcion = "--add-label" if accion["accion"] == "actualizar" else "--label"
        etiquetas_args = [x for e in accion["etiquetas"] for x in (opcion, e)]
        if accion["accion"] == "crear":
            _gh(gh, "issue", "create", "-R", repo, "--title", accion["titulo"], "--body", accion["cuerpo"],
                *etiquetas_args)
        else:
            _gh(gh, "issue", "edit", str(accion["numero"]), "-R", repo, "--title", accion["titulo"],
                "--body", accion["cuerpo"], *etiquetas_args)
    print(f"Listo: {len(acciones)} issues creados o actualizados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
