"""Línea de comandos del relay: emparejar, servir con programador, correr una receta y aprobar envíos."""

import argparse
import asyncio
import importlib
import json
import os
import secrets
import sys
from pathlib import Path

from relay.service.engine import Engine, load_recipe
from relay.service.scheduler import Scheduler, ServerBrowser
from relay.service.store import Store
from relay.service.ws import RelayServer

TOKEN_FILE = Path(os.environ.get("RELAY_TOKEN_FILE", Path.home() / ".config" / "relay" / "token"))


def token():
    if not TOKEN_FILE.is_file():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def load_sinks(path):
    if not path:
        return {}
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name or "DESTINOS")


async def serve(args, store):
    server = await RelayServer(token(), port=args.puerto).start()
    engine = Engine(ServerBrowser(server), store, load_sinks(args.destinos))
    config = json.loads(Path(args.agenda).read_text(encoding="utf-8"))
    jobs = [{**job, "recipe": load_recipe(Path(args.agenda).parent / job["receta"])} for job in config]
    print(
        f"Esperando la extensión en ws://127.0.0.1:{server.port} · {len(jobs)} recetas programadas",
        flush=True,
    )
    await Scheduler(server, engine, store, jobs).loop()


async def run_once(args, store):
    server = await RelayServer(token(), port=args.puerto).start()
    print(f"Esperando la extensión en ws://127.0.0.1:{server.port} …", flush=True)
    await server.wait_connected(timeout=300)
    inputs = json.loads(Path(args.datos).read_text(encoding="utf-8")) if args.datos else None
    result = await Engine(ServerBrowser(server), store, load_sinks(args.destinos)).run(
        load_recipe(args.receta), inputs
    )
    await server.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m relay.service.cli", description=__doc__)
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--puerto", type=int, default=8765)
    parser.add_argument(
        "--destinos", help="Destinos de resultados, por ejemplo asistente.relay_destino:DESTINOS"
    )
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("token", help="Muestra el token para pegarlo en la extensión.")
    p_serve = sub.add_parser("serve", help="Servicio con programador local.")
    p_serve.add_argument("agenda", help="JSON con recetas, intervalo y variación.")
    p_run = sub.add_parser("run", help="Corre una receta una vez.")
    p_run.add_argument("receta")
    p_run.add_argument("--datos", help="JSON con los valores para completar formularios.")
    p_show = sub.add_parser("show", help="Muestra el contenido exacto de una huella.")
    p_show.add_argument("huella")
    p_approve = sub.add_parser("approve", help="Aprueba el contenido exacto de una huella.")
    p_approve.add_argument("huella")
    p_resume = sub.add_parser("resume", help="Reanuda una receta pausada por un bloqueo.")
    p_resume.add_argument("receta")
    args = parser.parse_args(argv)

    if args.orden == "token":
        print(token())
        return 0
    store = Store(args.bd)
    if args.orden == "show":
        approval = store.approval(args.huella)
        if not approval:
            parser.exit(1, "No existe esa huella.\n")
        print(
            json.dumps(
                {**approval, "contenido": json.loads(approval["contenido"])}, ensure_ascii=False, indent=2
            )
        )
    elif args.orden == "approve":
        if not store.approve(args.huella):
            parser.exit(1, "La huella no existe o no está esperando aprobación.\n")
        print("Aprobada. Si cambia cualquier campo, la huella cambia y se vuelve a pedir aprobación.")
    elif args.orden == "resume":
        print("Reanudada." if store.resume(args.receta) else "La receta no estaba en pausa.")
    elif args.orden == "run":
        result = asyncio.run(run_once(args, store))
        print(json.dumps({k: v for k, v in result.items() if k != "datos"}, ensure_ascii=False))
    elif args.orden == "serve":
        asyncio.run(serve(args, store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
