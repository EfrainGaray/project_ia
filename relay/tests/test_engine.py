import asyncio
import json
import random
from pathlib import Path

from relay.service.engine import Engine, Robots, load_recipe
from relay.service.store import APROBADA, ENVIADA, ESPERANDO, Store, huella
from relay.service.ws import BrowserError

RELAY = Path(__file__).resolve().parents[1]
ROBOTS_OK = lambda url: (200, "User-agent: *\nDisallow: /privado/\n")  # noqa: E731


class FakeBrowser:
    def __init__(self, pages=None, form=None, blocked_on=None, fail=None):
        self.pages = pages or {}
        self.form = form or {"nombre": "Ana"}
        self.blocked_on = blocked_on
        self.fail = fail or {}
        self.calls: list[tuple] = []
        self.url = None

    async def call(self, cmd, args=None):
        self.calls.append((cmd, args))
        if cmd in self.fail:
            raise BrowserError(self.fail[cmd])
        if cmd == "open":
            self.url = args["url"]
            return {"url": self.url}
        if cmd == "detect":
            return {
                "blocked": self.blocked_on is not None and self.blocked_on in (self.url or ""),
                "signal": "iframe",
            }
        if cmd == "read":
            return self.pages.get(self.url, {}).get("items" if args.get("items") else "record")
        if cmd == "form_values":
            return dict(self.form)
        if cmd == "exists":
            return False
        if cmd == "click":
            return {"url": self.url}
        return True

    def ops(self):
        return [c[0] for c in self.calls]


def engine(browser, tmp_path, **kw):
    kw.setdefault("robots", Robots(fetch=ROBOTS_OK))
    kw.setdefault("pace", (0, 0))

    async def no_sleep(_):
        return None

    kw.setdefault("sleep", no_sleep)
    return Engine(browser, Store(tmp_path / "t.sqlite3"), **kw)


def recipe(*steps, hosts=("portal.cl",), name="prueba"):
    return {"name": name, "base": "https://portal.cl", "hosts": list(hosts), "steps": list(steps)}


def run(eng, rec, inputs=None):
    return asyncio.run(eng.run(rec, inputs))


def test_open_outside_recipe_hosts_is_refused_without_navigating(tmp_path):
    browser = FakeBrowser()
    result = run(engine(browser, tmp_path), recipe({"op": "open", "url": "https://otro.cl/"}))
    assert result["estado"] == "error" and "fuera de los dominios" in result["motivo"]
    assert "open" not in browser.ops()


def test_robots_disallowed_url_is_not_opened(tmp_path):
    browser = FakeBrowser()
    result = run(engine(browser, tmp_path), recipe({"op": "open", "url": "{base}/privado/x"}))
    assert result["estado"] == "error" and "robots.txt" in result["motivo"]
    assert "open" not in browser.ops()


def test_unreachable_robots_means_do_not_read(tmp_path):
    browser = FakeBrowser()
    eng = engine(browser, tmp_path, robots=Robots(fetch=lambda url: (None, "")))
    assert run(eng, recipe({"op": "open", "url": "{base}/"}))["estado"] == "error"
    assert Robots(fetch=lambda url: (404, "")).allowed("https://portal.cl/x")


def test_delays_stay_in_human_range_and_respect_crawl_delay(tmp_path):
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)

    steps = [
        {"op": "open", "url": "{base}/"},
        {"op": "click", "selector": "a"},
        {"op": "click", "selector": "b"},
    ]
    eng = engine(FakeBrowser(), tmp_path, pace=None, rng=random.Random(7), sleep=sleep)
    run(eng, {**recipe(*steps), "pace": [2, 6]})
    assert len(waits) == 3 and all(2 <= w <= 6 for w in waits) and len(set(waits)) == 3
    waits.clear()
    slow = Robots(fetch=lambda url: (200, "User-agent: *\nCrawl-delay: 9\n"))
    run(
        engine(FakeBrowser(), tmp_path, pace=None, robots=slow, sleep=sleep),
        {**recipe(*steps), "pace": [2, 6]},
    )
    assert waits and all(w >= 9 for w in waits)


def test_blocked_page_stops_pauses_recipe_and_does_not_read(tmp_path):
    browser = FakeBrowser(blocked_on="/captcha")
    eng = engine(browser, tmp_path)
    rec = recipe({"op": "open", "url": "{base}/captcha"}, {"op": "read", "fields": {"t": "h1"}})
    result = run(eng, rec)
    assert result["estado"] == "bloqueado" and "verificación o bloqueo" in result["motivo"]
    assert "read" not in browser.ops()
    assert run(eng, rec)["estado"] == "en pausa"
    assert eng.store.resume("prueba") and eng.store.paused("prueba") is None


def test_user_stop_ends_run_as_stopped(tmp_path):
    browser = FakeBrowser(fail={"wait": "detenido por la persona"})
    result = run(
        engine(browser, tmp_path), recipe({"op": "open", "url": "{base}/"}, {"op": "wait", "selector": "x"})
    )
    assert result["estado"] == "detenido"
    assert browser.ops()[-1] == "release"


FORM = [
    {"op": "open", "url": "{base}/form"},
    {"op": "fill", "fields": {"#nombre": "{input.nombre}"}},
    {"op": "preview", "form": "#f"},
    {"op": "submit", "form": "#f", "button": "#enviar"},
]


def test_preview_waits_for_approval_and_does_not_click_submit(tmp_path):
    browser = FakeBrowser(form={"nombre": "Ana"})
    eng = engine(browser, tmp_path)
    result = run(eng, recipe(*FORM), {"nombre": "Ana"})
    assert result["estado"] == ESPERANDO
    clave = huella("prueba", "https://portal.cl/form", {"nombre": "Ana"})
    assert eng.store.approval(clave)["estado"] == ESPERANDO
    assert ("click", {"selector": "#enviar", "settle_ms": 1500}) not in browser.calls


def test_approved_content_is_sent_once_and_changed_content_needs_new_approval(tmp_path):
    browser = FakeBrowser(form={"nombre": "Ana"})
    eng = engine(browser, tmp_path)
    run(eng, recipe(*FORM), {"nombre": "Ana"})
    clave = huella("prueba", "https://portal.cl/form", {"nombre": "Ana"})
    assert eng.store.approve(clave) and eng.store.approval(clave)["estado"] == APROBADA

    browser.form = {"nombre": "Ana María"}  # changed after approval
    result = run(eng, recipe(*FORM), {"nombre": "Ana María"})
    assert result["estado"] == ESPERANDO and not any(c[0] == "click" for c in browser.calls)

    browser.form = {"nombre": "Ana"}
    assert run(eng, recipe(*FORM), {"nombre": "Ana"})["estado"] == "ok"
    assert eng.store.approval(clave)["estado"] == ENVIADA
    clicks = [c for c in browser.calls if c[0] == "click"]
    assert len(clicks) == 1

    assert run(eng, recipe(*FORM), {"nombre": "Ana"})["estado"] == ESPERANDO  # already sent: no duplicate
    assert len([c for c in browser.calls if c[0] == "click"]) == 1


def test_approve_unknown_hash_fails(tmp_path):
    assert not Store(tmp_path / "t.sqlite3").approve("0" * 64)


def test_missing_input_value_is_an_error(tmp_path):
    result = run(engine(FakeBrowser(), tmp_path), recipe(*FORM), {})
    assert result["estado"] == "error" and "input.nombre" in result["motivo"]


def test_foreach_keeps_failed_items_and_save_reaches_sink(tmp_path):
    pages = {
        "https://portal.cl/": {"items": [{"enlace": "/a"}, {"enlace": "/b"}, {"enlace": "/a"}]},
        "https://portal.cl/a": {"record": {"texto": "A"}},
    }
    browser = FakeBrowser(pages=pages)
    saved = []
    eng = engine(browser, tmp_path, sinks={"destino": lambda rows, rec, db: saved.append((rows, db))})

    async def failing_wait(cmd, args=None, original=browser.call):
        if cmd == "wait" and str(browser.url).endswith("/b"):
            raise BrowserError("estructura cambió: no apareció .x")
        return await original(cmd, args)

    browser.call = failing_wait  # type: ignore[method-assign]
    rec = recipe(
        {"op": "open", "url": "{base}/"},
        {"op": "read", "items": ".card", "into": "filas", "fields": {"enlace": "a"}},
        {
            "op": "foreach",
            "in": "filas",
            "unique": "enlace",
            "steps": [
                {"op": "open", "url": "{item.enlace}"},
                {"op": "wait", "selector": ".x"},
                {"op": "read", "into": "item", "fields": {"texto": "p"}},
            ],
        },
        {"op": "save", "from": "filas", "to": "destino"},
    )
    assert run(eng, rec)["estado"] == "ok"
    rows, db = saved[0]
    assert db == tmp_path / "t.sqlite3"
    assert rows[0] == {"enlace": "/a", "texto": "A"}
    assert rows[1]["enlace"] == "/b" and "estructura cambió" in rows[1]["_error"]
    assert len(rows) == 2


def test_manifest_does_not_request_cookies_or_debugger():
    manifest = json.loads((RELAY / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert not {"cookies", "debugger", "webRequest", "history"} & set(manifest["permissions"])


def test_shipped_recipes_load_and_only_use_known_steps():
    known = {"open", "wait", "read", "click", "paginate", "foreach", "fill", "preview", "submit", "save"}

    def ops(steps):
        for step in steps:
            yield step["op"]
            yield from ops(step.get("steps", []))

    for path in (RELAY / "recipes").glob("*_*.json"):
        if path.name.startswith("agenda"):
            continue
        rec = load_recipe(path)
        assert set(ops(rec["steps"])) <= known, path.name
