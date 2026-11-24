"""Motor de recetas: ejecuta pasos declarativos en la pestaña que controla la extensión.

Reglas que aplica en cada corrida: solo dominios de la receta, robots.txt, ritmo humano con variación,
detención ante CAPTCHA o bloqueo, y envío solo con una aprobación de la huella del contenido exacto.
"""

import asyncio
import json
import random
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from relay.service.store import APROBADA, ESPERANDO, huella
from relay.service.ws import BrowserError

AGENT = "AsistentePostulaciones"
PACE = (2.0, 6.0)
TEMPLATE = re.compile(r"\{(base|item|input)(?:\.([A-Za-z0-9_]+))?\}")


class Stop(Exception):
    def __init__(self, estado, motivo):
        super().__init__(motivo)
        self.estado = estado
        self.motivo = motivo


def load_recipe(path):
    recipe = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("name", "hosts", "steps"):
        if key not in recipe:
            raise ValueError(f"La receta {path} no tiene «{key}».")
    return recipe


def fetch_robots(url):
    request = Request(url, headers={"User-Agent": AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read(500_000).decode("utf-8", "replace")
    except HTTPError as error:
        return error.code, ""
    except (URLError, OSError):
        return None, ""


class Robots:
    """robots.txt por dominio, con caché. Sin respuesta legible, no se lee el sitio."""

    def __init__(self, fetch=fetch_robots, agent=AGENT):
        self.fetch = fetch
        self.agent = agent
        self.cache: dict[str, RobotFileParser | None] = {}

    def parser(self, url):
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self.cache:
            status, text = self.fetch(root + "/robots.txt")
            parser = RobotFileParser()
            if status == 200:
                parser.parse(text.splitlines())
            elif status is not None and 400 <= status < 500 and status not in (401, 403):
                parser.parse([])  # no robots.txt: everything allowed
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
            self.cache[root] = parser
        return self.cache[root]

    def allowed(self, url):
        return self.parser(url).can_fetch(self.agent, url)

    def delay(self, url):
        return float(self.parser(url).crawl_delay(self.agent) or 0)


class Engine:
    def __init__(self, browser, store, sinks=None, robots=None, rng=None, sleep=asyncio.sleep, pace=None):
        self.browser = browser
        self.store = store
        self.sinks = sinks or {}
        self.robots = robots or Robots()
        self.rng = rng or random.Random()  # noqa: S311 (pacing jitter, not security)
        self.sleep = sleep
        self.pace_override = pace

    async def run(self, recipe, inputs=None):
        name = recipe["name"]
        if self.store.paused(name):
            return {"corrida": None, "estado": "en pausa", "motivo": self.store.paused(name), "datos": {}}
        corrida = self.store.start_run(name)
        ctx = {
            "recipe": recipe,
            "corrida": corrida,
            "vars": {},
            "item": None,
            "url": None,
            "input": inputs or {},
            "estado": "ok",
            "motivo": None,
        }
        try:
            await self.steps(recipe["steps"], ctx)
        except Stop as stop:
            ctx["estado"], ctx["motivo"] = stop.estado, stop.motivo
            if stop.estado == "bloqueado":
                self.store.pause(name, stop.motivo)
        except ConnectionError as error:
            ctx["estado"], ctx["motivo"] = "interrumpido", str(error)
        finally:
            try:
                await self.browser.call("release")
            except (BrowserError, ConnectionError):
                pass
        self.store.finish_run(corrida, ctx["estado"], ctx["motivo"])
        return {"corrida": corrida, "estado": ctx["estado"], "motivo": ctx["motivo"], "datos": ctx["vars"]}

    async def call(self, cmd, args=None):
        try:
            return await self.browser.call(cmd, args or {})
        except BrowserError as error:
            message = str(error)
            if message.startswith("detenido"):
                raise Stop("detenido", "La persona detuvo la extensión.") from error
            raise Stop("error", message) from error

    async def pace(self, ctx, url=None):
        low, high = self.pace_override or ctx["recipe"].get("pace") or PACE
        wait = self.rng.uniform(low, high)
        target = url or ctx["url"]
        if target:
            wait = max(wait, self.robots.delay(target))
        await self.sleep(wait)
        return wait

    def render(self, text, ctx):
        def value(match):
            scope, key = match[1], match[2]
            if scope == "base":
                return str(ctx["recipe"].get("base", ""))
            source = ctx["item"] if scope == "item" else ctx["input"]
            if source is None or key not in source or source[key] is None:
                raise Stop("error", f"Falta el dato {match[0]} para la receta.")
            return str(source[key])

        return TEMPLATE.sub(value, str(text))

    def check_url(self, url, ctx):
        host = urlsplit(url).hostname or ""
        if urlsplit(url).scheme not in ("http", "https") or host not in ctx["recipe"]["hosts"]:
            raise Stop("error", f"{url} está fuera de los dominios de la receta.")
        if not self.robots.allowed(url):
            raise Stop("error", f"robots.txt no permite leer {url}.")

    async def detect(self):
        result = await self.call("detect")
        if result and result.get("blocked"):
            raise Stop("bloqueado", f"El portal mostró una verificación o bloqueo: {result.get('signal')}.")

    async def steps(self, steps, ctx):
        for step in steps:
            await getattr(self, f"op_{step['op']}")(step, ctx)

    async def op_open(self, step, ctx):
        url = urljoin(ctx["url"] or ctx["recipe"].get("base", ""), self.render(step["url"], ctx))
        self.check_url(url, ctx)
        await self.pace(ctx, url)
        result = await self.call("open", {"url": url, "hosts": ctx["recipe"]["hosts"]})
        ctx["url"] = (result or {}).get("url") or url
        await self.detect()

    async def op_wait(self, step, ctx):
        await self.call("wait", {"selector": step["selector"], "timeout_ms": step.get("timeout_ms", 15000)})

    async def op_read(self, step, ctx):
        result = await self.call("read", {"items": step.get("items"), "fields": step["fields"]})
        into = step.get("into", "datos")
        if into == "item":
            ctx["item"].update(result or {})
        elif step.get("items"):
            ctx["vars"].setdefault(into, []).extend(result or [])
        else:
            ctx["vars"].setdefault(into, []).append(result or {})

    async def op_click(self, step, ctx):
        await self.pace(ctx)
        result = await self.call(
            "click", {"selector": step["selector"], "settle_ms": step.get("settle_ms", 800)}
        )
        ctx["url"] = (result or {}).get("url") or ctx["url"]
        await self.detect()

    async def op_paginate(self, step, ctx):
        await self.steps(step["steps"], ctx)
        for _ in range(step.get("max_pages", 1) - 1):
            if not await self.call("exists", {"selector": step["next"]}):
                break
            await self.op_click({"selector": step["next"], "settle_ms": step.get("settle_ms", 1500)}, ctx)
            await self.steps(step["steps"], ctx)

    async def op_foreach(self, step, ctx):
        seen = set()
        items = []
        for item in ctx["vars"].get(step["in"], []):
            key = item.get(step.get("unique", "")) if step.get("unique") else id(item)
            if key not in seen:
                seen.add(key)
                items.append(item)
        for item in items[: step.get("max", len(items))]:
            ctx["item"] = item
            try:
                await self.steps(step["steps"], ctx)
            except Stop as stop:
                if stop.estado != "error":
                    raise
                item["_error"] = stop.motivo
        ctx["item"] = None
        ctx["vars"][step["in"]] = items

    async def op_fill(self, step, ctx):
        fields = {selector: self.render(value, ctx) for selector, value in step["fields"].items()}
        await self.pace(ctx)
        await self.call("fill", {"fields": fields})

    async def op_preview(self, step, ctx):
        if step.get("button"):
            await self.op_click({"selector": step["button"]}, ctx)
        campos = await self.call("form_values", {"form": step["form"]})
        clave = self.store.request_approval(ctx["recipe"]["name"], ctx["url"], campos)
        ctx["vars"]["vista_previa"] = [{"huella": clave, "url": ctx["url"], "campos": campos}]
        ctx["estado"], ctx["motivo"] = ESPERANDO, f"Revisa y aprueba la huella {clave}."

    async def op_submit(self, step, ctx):
        campos = await self.call("form_values", {"form": step["form"]})
        clave = huella(ctx["recipe"]["name"], ctx["url"], campos)
        approval = self.store.approval(clave)
        if not approval or approval["estado"] != APROBADA:
            self.store.request_approval(ctx["recipe"]["name"], ctx["url"], campos)
            estado = approval["estado"] if approval else "sin aprobación"
            raise Stop(ESPERANDO, f"El contenido actual (huella {clave}) está «{estado}»; no se envió.")
        await self.op_click({"selector": step["button"], "settle_ms": step.get("settle_ms", 1500)}, ctx)
        self.store.mark_sent(clave)
        ctx["estado"], ctx["motivo"] = "ok", f"Enviado el contenido aprobado {clave}."

    async def op_save(self, step, ctx):
        rows = ctx["vars"].get(step["from"], [])
        destino = step.get("to", step["from"])
        self.store.save_results(ctx["corrida"], ctx["recipe"]["name"], destino, rows)
        if destino in self.sinks:
            self.sinks[destino](rows, ctx["recipe"], self.store.database)
