"""Servidor WebSocket mínimo (RFC 6455, solo texto) para hablar con la extensión en 127.0.0.1.

Emparejamiento: la extensión envía un nonce y su prueba HMAC del token; el servicio la verifica y
responde con su propia prueba, para que la extensión solo obedezca a quien conoce el token.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 4_000_000
LOCAL = {"127.0.0.1", "::1"}


def proof(token, role, nonce):
    return hmac.new(token.encode(), f"{role}:{nonce}".encode(), hashlib.sha256).hexdigest()


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()  # noqa: S324 (RFC 6455)


def encode_frame(payload, opcode=1, mask=False):
    data = payload.encode() if isinstance(payload, str) else payload
    head = bytes([0x80 | opcode])
    size = len(data)
    bit = 0x80 if mask else 0
    if size < 126:
        head += bytes([bit | size])
    elif size < 65536:
        head += bytes([bit | 126]) + struct.pack("!H", size)
    else:
        head += bytes([bit | 127]) + struct.pack("!Q", size)
    if mask:
        key = os.urandom(4)
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
        head += key
    return head + data


async def read_frame(reader, require_mask=True):
    first, second = await reader.readexactly(2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    size = second & 0x7F
    if size == 126:
        (size,) = struct.unpack("!H", await reader.readexactly(2))
    elif size == 127:
        (size,) = struct.unpack("!Q", await reader.readexactly(8))
    if size > MAX_MESSAGE:
        raise ConnectionError("Mensaje demasiado grande.")
    if require_mask and not masked:
        raise ConnectionError("El cliente debe enmascarar sus tramas.")
    key = await reader.readexactly(4) if masked else b""
    data = await reader.readexactly(size)
    if masked:
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return bool(first & 0x80), opcode, data


class Connection:
    """Una extensión conectada. `call()` envía un comando y espera su respuesta."""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()
        self.next_id = 0
        self.closed = asyncio.Event()

    async def send(self, message):
        self.writer.write(encode_frame(json.dumps(message, ensure_ascii=False)))
        await self.writer.drain()

    async def receive(self):
        parts = []
        while True:
            fin, opcode, data = await read_frame(self.reader)
            if opcode == 8:
                raise ConnectionError("La extensión cerró la conexión.")
            if opcode == 9:
                self.writer.write(encode_frame(data, opcode=10))
                continue
            if opcode == 10:
                continue
            if opcode in (1, 0):
                parts.append(data)
                if fin:
                    return json.loads(b"".join(parts).decode())
            else:
                raise ConnectionError("Tipo de trama no admitido.")

    async def call(self, cmd, args=None, timeout=60.0):
        if self.closed.is_set():
            raise ConnectionError("La extensión no está conectada.")
        self.next_id += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[self.next_id] = future
        await self.send({"id": self.next_id, "cmd": cmd, "args": args or {}})
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(self.next_id, None)

    async def pump(self):
        try:
            while True:
                message = await self.receive()
                if "id" in message and message["id"] in self.pending:
                    future = self.pending[message["id"]]
                    if message.get("ok"):
                        future.set_result(message.get("result"))
                    else:
                        future.set_exception(
                            BrowserError(str(message.get("error") or "Error de la extensión."))
                        )
                elif message.get("type") == "event":
                    await self.events.put(message)
        except (ConnectionError, asyncio.IncompleteReadError, json.JSONDecodeError, OSError):
            pass
        finally:
            self.closed.set()
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("La extensión se desconectó."))
            self.writer.close()


class BrowserError(Exception):
    """La extensión rechazó o no pudo ejecutar un comando."""


class RelayServer:
    def __init__(self, token, host="127.0.0.1", port=8765):
        if not token or len(token) < 16:
            raise ValueError("El token de emparejamiento debe tener al menos 16 caracteres.")
        self.token = token
        self.host = host
        self.port = port
        self.connection: Connection | None = None
        self.connected = asyncio.Event()
        self.server: asyncio.base_events.Server | None = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle, self.host, self.port)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        if self.connection:
            self.connection.writer.close()

    async def wait_connected(self, timeout=30.0):
        await asyncio.wait_for(self.connected.wait(), timeout)
        return self.connection

    async def handle(self, reader, writer):
        try:
            await self.accept(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, OSError):
            writer.close()

    async def accept(self, reader, writer):
        peer = writer.get_extra_info("peername")[0]
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = raw.decode("latin-1").split("\r\n")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        origin = headers.get("origin", "")
        key = headers.get("sec-websocket-key")
        if (
            peer not in LOCAL
            or not origin.startswith("chrome-extension://")
            or not key
            or headers.get("upgrade", "").lower() != "websocket"
        ):
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            raise ConnectionError("Conexión rechazada: solo la extensión local puede conectarse.")
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key(key)}\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        connection = Connection(reader, writer)
        hello = await asyncio.wait_for(connection.receive(), 10)
        nonce = str(hello.get("nonce", ""))
        if (
            hello.get("type") != "hello"
            or len(nonce) < 16
            or not hmac.compare_digest(str(hello.get("proof", "")), proof(self.token, "client", nonce))
        ):
            writer.write(encode_frame(b"", opcode=8))
            raise ConnectionError("Token de emparejamiento inválido.")
        await connection.send({"type": "welcome", "proof": proof(self.token, "server", nonce)})
        if self.connection and not self.connection.closed.is_set():
            self.connection.writer.close()
        self.connection = connection
        self.connected.set()
        await connection.pump()
        if self.connection is connection:
            self.connected.clear()
