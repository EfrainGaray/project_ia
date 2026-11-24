"""End-to-end: unpacked extension in Chromium, the local service and local fixture pages (no portals)."""

import asyncio
import json
import sqlite3
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from relay.service.engine import Engine, Robots, load_recipe  # noqa: E402
from relay.service.scheduler import ServerBrowser  # noqa: E402
from relay.service.store import ENVIADA, ESPERANDO, Store  # noqa: E402
from relay.service.ws import BrowserError, RelayServer, encode_frame, read_frame  # noqa: E402

RELAY = Path(__file__).resolve().parents[1]
FIXTURES = RELAY / "tests" / "fixtures"
TOKEN = "token-e2e-0123456789abcdef"
INPUTS = {
    "nombre": "Ana Prueba",
    "correo": "ana@example.com",
    "cargo": "Analista de datos",
    "region": "RM",
    "mensaje": "Me interesa el cargo.",
    "acepto": "true",
}


class Handler(SimpleHTTPRequestHandler):
    posts: list[bytes] = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Handler.posts.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<!doctype html><title>Recibido</title><p>Postulación recibida.</p>".encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    http = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(FIXTURES)))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{http.server_address[1]}"

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def call(coro, timeout=120):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    server = call(RelayServer(TOKEN, port=0).start())
    playwright = sync_api.sync_playwright().start()
    extension = str(RELAY / "extension")
    try:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path_factory.mktemp("chrome")),
            headless=True,
            channel="chromium",
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
        )
    except Exception as error:  # noqa: BLE001
        playwright.stop()
        pytest.skip(f"Chromium with extensions is not available: {error}")
    worker = (
        context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
    )
    worker.evaluate(f"chrome.storage.local.set({{token: '{TOKEN}', port: {server.port}}})")
    call(server.wait_connected(20))
    yield {"base": base, "server": server, "call": call, "context": context, "worker": worker, "loop": loop}
    context.close()
    playwright.stop()
    call(server.close())
    loop.call_soon_threadsafe(loop.stop)
    http.shutdown()


def run(env, recipe, db, inputs=None, sinks=None):
    store = Store(db)
    engine = Engine(ServerBrowser(env["server"]), store, sinks or {}, robots=Robots(), pace=(0, 0))
    return env["call"](engine.run(recipe, inputs)), store


def command(env, cmd, args=None):
    return env["call"](env["server"].connection.call(cmd, args or {}), timeout=60)


def recipe(name, env, prefix=""):
    rec = load_recipe(RELAY / "recipes" / f"{name}.json")
    return {**rec, "base": env["base"] + prefix, "hosts": ["127.0.0.1"]}


def driven_page(env):
    tab_url = env["worker"].evaluate("chrome.tabs.get(drivenTab).then(t => t.url)")
    return next(p for p in env["context"].pages if p.url == tab_url)


def test_banner_and_badge_mark_the_driven_tab_until_release(env):
    command(env, "open", {"url": env["base"] + "/practica/formulario.html", "hosts": ["127.0.0.1"]})
    page = driven_page(env)
    assert page.locator("#relay-banner-host").count() == 1
    assert "controlando esta pestaña" in page.locator("#relay-banner-host .bar").inner_text()
    assert env["worker"].evaluate("chrome.action.getBadgeText({tabId: drivenTab})") == "AUTO"
    command(env, "release")
    assert page.locator("#relay-banner-host").count() == 0
    assert env["worker"].evaluate("chrome.action.getBadgeText({tabId: drivenTab})") == ""


def test_kill_switch_in_banner_stops_all_commands(env):
    command(env, "open", {"url": env["base"] + "/practica/formulario.html", "hosts": ["127.0.0.1"]})
    page = driven_page(env)
    page.locator("#relay-stop").click()
    page.wait_for_function("() => !document.getElementById('relay-banner-host')")
    with pytest.raises(BrowserError, match="detenido"):
        command(env, "wait", {"selector": "#postulacion", "timeout_ms": 1000})
    env["worker"].evaluate("chrome.storage.local.set({stopped: false})")
    assert command(env, "exists", {"selector": "#postulacion"}) is True


def test_extension_refuses_hosts_outside_the_recipe(env):
    with pytest.raises(BrowserError, match="fuera de los dominios"):
        command(env, "open", {"url": env["base"] + "/practica/formulario.html", "hosts": ["trabajaenbci.cl"]})


def test_practice_form_reaches_preview_and_is_not_submitted(env, tmp_path):
    Handler.posts.clear()
    result, store = run(env, recipe("practica_formulario", env), tmp_path / "t.sqlite3", INPUTS)
    assert result["estado"] == ESPERANDO, result
    [preview] = result["datos"]["vista_previa"]
    assert preview["campos"] == {
        "nombre": "Ana Prueba",
        "correo": "ana@example.com",
        "cargo": "Analista de datos",
        "region": "RM",
        "mensaje": "Me interesa el cargo.",
        "acepto": True,
    }
    assert (
        "clave" not in preview["campos"] and "csrf" not in preview["campos"]
    )  # password and hidden excluded
    assert store.approval(preview["huella"])["estado"] == ESPERANDO
    assert Handler.posts == []
    assert "Vista previa: nombre=Ana Prueba" in driven_page(env).locator("#vista").inner_text()


def test_approved_hash_is_submitted_once_and_a_change_needs_new_approval(env, tmp_path):
    Handler.posts.clear()
    db = tmp_path / "t.sqlite3"
    result, store = run(env, recipe("practica_formulario", env), db, INPUTS)
    clave = result["datos"]["vista_previa"][0]["huella"]
    assert store.approve(clave)

    changed, _ = run(env, recipe("practica_formulario", env), db, {**INPUTS, "mensaje": "Otro texto."})
    assert changed["estado"] == ESPERANDO and Handler.posts == []

    sent, _ = run(env, recipe("practica_formulario", env), db, INPUTS)
    assert sent["estado"] == "ok", sent
    assert len(Handler.posts) == 1 and b"nombre=Ana+Prueba" in Handler.posts[0]
    assert store.approval(clave)["estado"] == ENVIADA

    again, _ = run(env, recipe("practica_formulario", env), db, INPUTS)
    assert again["estado"] == ESPERANDO and len(Handler.posts) == 1


def test_password_fields_are_never_filled(env, tmp_path):
    rec = {
        "name": "clave",
        "base": env["base"],
        "hosts": ["127.0.0.1"],
        "steps": [
            {"op": "open", "url": "{base}/practica/formulario.html"},
            {"op": "fill", "fields": {"#clave": "secreto"}},
        ],
    }
    result, _ = run(env, rec, tmp_path / "t.sqlite3")
    assert result["estado"] == "error" and "contraseñas" in result["motivo"]


def test_bci_recipe_reads_listing_pagination_and_details_into_offers(env, tmp_path):
    from asistente.relay_destino import DESTINOS

    db = tmp_path / "t.sqlite3"
    result, _ = run(env, recipe("bci_ofertas", env, "/bci"), db, sinks=DESTINOS)
    assert result["estado"] == "ok", result
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = {r["id_origen"]: dict(r) for r in conn.execute("SELECT * FROM ofertas WHERE fuente = 'bci'")}
    assert set(rows) == {"39393", "39410", "39319"}  # page 2 came from pagination; duplicate 39410 merged
    full = rows["39410"]
    assert full["cargo"] == "Especialista Procesos y Proyectos Tarjeta"
    assert full["enlace"] == "https://trabajaenbci.cl/offers/proceso/39410"
    assert full["fecha_publicacion"] == "2026-11-21" and full["ubicacion"] == "Santiago"
    assert full["estado"] == "completa" and "\nRequisitos\n" in full["descripcion"]
    assert "Dominio avanzado en Python, SQL, PySpark" in full["descripcion"]
    assert rows["39319"]["estado"] == "pendiente de descripción"  # its detail page does not exist


def test_rendered_page_recipe_waits_for_javascript_content(env, tmp_path):
    from asistente.relay_destino import DESTINOS

    db = tmp_path / "t.sqlite3"
    result, _ = run(
        env,
        {
            **recipe("latam_ofertas", env),
            "steps": [
                {**step, "url": "{base}/latam/"} if step["op"] == "open" and "{base}" in step["url"] else step
                for step in load_recipe(RELAY / "recipes" / "latam_ofertas.json")["steps"]
            ],
        },
        db,
        sinks=DESTINOS,
    )
    assert result["estado"] == "ok", result
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id_origen, cargo, estado, descripcion FROM ofertas WHERE fuente = 'latam'"
        ).fetchall()
    assert {r[0] for r in rows} == {"ana-001", "ing-002"}
    assert all(r[2] == "completa" and "Python" in r[3] for r in rows)


def test_captcha_page_stops_the_run_without_reading(env, tmp_path):
    rec = {
        "name": "bloqueo",
        "base": env["base"],
        "hosts": ["127.0.0.1"],
        "steps": [
            {"op": "open", "url": "{base}/bloqueo/captcha.html"},
            {"op": "read", "items": ".offer-hit-card", "into": "x", "fields": {"t": "h2"}},
        ],
    }
    result, store = run(env, rec, tmp_path / "t.sqlite3")
    assert result["estado"] == "bloqueado" and "iframe" in result["motivo"]
    assert "x" not in result["datos"]
    assert store.paused("bloqueo")


def test_extension_does_not_obey_a_service_without_the_token(env):
    """A rogue local service that cannot prove the token gets no answer to its commands."""
    replies: list[bytes] = []

    async def handler(reader, writer):
        from relay.service.ws import accept_key

        raw = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        key = next(
            line.split(":", 1)[1].strip()
            for line in raw.split("\r\n")
            if line.lower().startswith("sec-websocket-key")
        )
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key(key)}\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        await read_frame(reader)  # hello
        writer.write(encode_frame(json.dumps({"type": "welcome", "proof": "0" * 64})))
        writer.write(encode_frame(json.dumps({"id": 1, "cmd": "detect", "args": {}})))
        await writer.drain()
        try:
            while True:
                _, opcode, data = await asyncio.wait_for(read_frame(reader), 4)
                if opcode == 1:
                    replies.append(data)
                if opcode == 8:
                    break
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            pass
        writer.close()

    async def start():
        return await asyncio.start_server(handler, "127.0.0.1", 0)

    rogue_server = env["call"](start())
    port = rogue_server.sockets[0].getsockname()[1]
    env["worker"].evaluate(f"chrome.storage.local.set({{port: {port}}})")
    env["call"](asyncio.sleep(6))
    assert not [r for r in replies if b'"id"' in r]
    env["worker"].evaluate(f"chrome.storage.local.set({{port: {env['server'].port}}})")
    rogue_server.close()
    env["server"].connected.clear()
    env["call"](env["server"].wait_connected(20))
