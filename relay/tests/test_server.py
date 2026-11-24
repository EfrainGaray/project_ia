import asyncio
import base64
import json
import os

import pytest

from relay.service.ws import BrowserError, RelayServer, encode_frame, proof, read_frame

TOKEN = "token-de-prueba-0123456789"


async def client(port, origin="chrome-extension://abcdef", token=TOKEN, nonce="n" * 32):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    key = base64.b64encode(os.urandom(16)).decode()
    writer.write(
        (
            f"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: {origin}\r\n\r\n"
        ).encode()
    )
    await writer.drain()
    status = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n")[0]
    if b"101" not in status:
        return status, reader, writer
    hello = {"type": "hello", "nonce": nonce, "proof": proof(token, "client", nonce)}
    writer.write(encode_frame(json.dumps(hello), mask=True))
    await writer.drain()
    return status, reader, writer


async def receive(reader):
    _, opcode, data = await asyncio.wait_for(read_frame(reader, require_mask=False), 5)
    return opcode, data


def test_frames_roundtrip_including_long_payloads():
    async def go():
        for size in (5, 300, 70_000):
            reader = asyncio.StreamReader()
            reader.feed_data(encode_frame("x" * size, mask=True))
            fin, opcode, data = await read_frame(reader)
            assert (fin, opcode, data) == (True, 1, b"x" * size)

    asyncio.run(go())


def test_unmasked_client_frame_is_rejected():
    async def go():
        reader = asyncio.StreamReader()
        reader.feed_data(encode_frame("hola"))
        with pytest.raises(ConnectionError):
            await read_frame(reader)

    asyncio.run(go())


def test_paired_extension_gets_server_proof_and_answers_commands():
    async def go():
        server = await RelayServer(TOKEN, port=0).start()
        status, reader, writer = await client(server.port)
        assert b"101" in status
        _, data = await receive(reader)
        welcome = json.loads(data)
        assert welcome == {"type": "welcome", "proof": proof(TOKEN, "server", "n" * 32)}
        connection = await server.wait_connected(5)

        async def extension():
            _, data = await receive(reader)
            command = json.loads(data)
            assert command["cmd"] == "read"
            writer.write(
                encode_frame(json.dumps({"id": command["id"], "ok": True, "result": {"a": 1}}), mask=True)
            )
            _, data = await receive(reader)
            command = json.loads(data)
            writer.write(
                encode_frame(json.dumps({"id": command["id"], "ok": False, "error": "detenido"}), mask=True)
            )
            await writer.drain()

        task = asyncio.create_task(extension())
        assert await connection.call("read", {"fields": {}}) == {"a": 1}
        with pytest.raises(BrowserError, match="detenido"):
            await connection.call("wait")
        await task
        writer.close()
        await server.close()

    asyncio.run(go())


def test_wrong_token_is_rejected_and_never_connected():
    async def go():
        server = await RelayServer(TOKEN, port=0).start()
        _, reader, writer = await client(server.port, token="otro-token-cualquiera-123")
        opcode, _ = await receive(reader)
        assert opcode == 8
        await asyncio.sleep(0.1)
        assert not server.connected.is_set()
        writer.close()
        await server.close()

    asyncio.run(go())


def test_web_page_origin_is_refused_with_403():
    async def go():
        server = await RelayServer(TOKEN, port=0).start()
        status, _, writer = await client(server.port, origin="https://sitio-cualquiera.cl")
        assert b"403" in status
        writer.close()
        await server.close()

    asyncio.run(go())


def test_short_token_is_refused():
    with pytest.raises(ValueError):
        RelayServer("corto")
