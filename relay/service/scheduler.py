"""Programador local: corre recetas vencidas solo mientras la extensión está conectada."""

import asyncio
import random
import time

from relay.service.ws import BrowserError


class ServerBrowser:
    """Envía comandos a la extensión conectada en este momento (se reconecta sola)."""

    def __init__(self, server):
        self.server = server

    async def call(self, cmd, args=None):
        connection = self.server.connection
        if connection is None or connection.closed.is_set():
            raise ConnectionError("La extensión no está conectada.")
        return await connection.call(cmd, args)


class Scheduler:
    def __init__(self, server, engine, store, jobs, rng=None, clock=time.time):
        self.server = server
        self.engine = engine
        self.store = store
        self.jobs = jobs
        self.rng = rng or random.Random()  # noqa: S311 (pacing jitter, not security)
        self.clock = clock
        self.due = {job["recipe"]["name"]: clock() for job in jobs}

    def connected(self):
        connection = self.server.connection
        return connection is not None and not connection.closed.is_set()

    async def tick(self):
        results = []
        for job in self.jobs:
            name = job["recipe"]["name"]
            now = self.clock()
            if not self.connected() or now < self.due[name] or self.store.paused(name):
                continue
            try:
                result = await self.engine.run(job["recipe"], job.get("inputs"))
            except (BrowserError, ConnectionError) as error:
                result = {"estado": "interrumpido", "motivo": str(error)}
            results.append((name, result))
            every = job.get("every_minutes", 360) * 60
            jitter = job.get("jitter_minutes", 30) * 60
            self.due[name] = now + every + self.rng.uniform(0, jitter)
        return results

    async def loop(self, interval=30.0):
        while True:
            for name, result in await self.tick():
                print(f"{name}: {result['estado']} {result.get('motivo') or ''}".rstrip(), flush=True)
            await asyncio.sleep(interval)
