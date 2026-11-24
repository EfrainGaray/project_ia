import asyncio

from relay.service.scheduler import Scheduler, ServerBrowser
from relay.service.store import Store


class Conn:
    def __init__(self):
        self.closed = asyncio.Event()


class FakeServer:
    connection = None


class FakeEngine:
    def __init__(self):
        self.runs: list[str] = []

    async def run(self, recipe, inputs=None):
        self.runs.append(recipe["name"])
        return {"estado": "ok"}


def make(tmp_path, clock):
    server, engine = FakeServer(), FakeEngine()
    jobs = [
        {"recipe": {"name": "a"}, "every_minutes": 60, "jitter_minutes": 10},
        {"recipe": {"name": "b"}, "every_minutes": 30, "jitter_minutes": 0},
    ]
    store = Store(tmp_path / "t.sqlite3")
    return server, engine, store, Scheduler(server, engine, store, jobs, clock=clock)


def test_nothing_runs_without_a_connected_extension(tmp_path):
    now = [1000.0]
    server, engine, _, scheduler = make(tmp_path, lambda: now[0])
    assert asyncio.run(scheduler.tick()) == [] and engine.runs == []
    conn = Conn()
    conn.closed.set()
    server.connection = conn
    assert asyncio.run(scheduler.tick()) == []


def test_due_recipes_run_when_connected_and_reschedule_with_jitter(tmp_path):
    now = [1000.0]
    server, engine, store, scheduler = make(tmp_path, lambda: now[0])
    server.connection = Conn()
    asyncio.run(scheduler.tick())
    assert engine.runs == ["a", "b"]
    assert 1000 + 3600 <= scheduler.due["a"] <= 1000 + 3600 + 600
    assert scheduler.due["b"] == 1000 + 1800
    now[0] = 1000 + 1800
    asyncio.run(scheduler.tick())
    assert engine.runs == ["a", "b", "b"]


def test_paused_recipe_is_skipped(tmp_path):
    now = [1000.0]
    server, engine, store, scheduler = make(tmp_path, lambda: now[0])
    server.connection = Conn()
    store.pause("a", "bloqueo")
    asyncio.run(scheduler.tick())
    assert engine.runs == ["b"]


def test_server_browser_without_connection_raises(tmp_path):
    async def go():
        try:
            await ServerBrowser(FakeServer()).call("detect")
        except ConnectionError:
            return True
        return False

    assert asyncio.run(go())
