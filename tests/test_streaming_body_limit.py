"""Exercise the actual ASGI boundary without product writes or database access."""

import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from groundtruth.api.security import MaxBodySizeMiddleware


async def invoke(chunks, *, headers=(), method="POST", path="/api/contact", downstream=None):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json"), *headers],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]
    sent, calls, reads = [], [], []

    async def receive():
        reads.append(True)
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def app(scope, receive, send):
        calls.append(True)
        if downstream:
            return await downstream(scope, receive, send)
        body = await Request(scope, receive).body()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})

    await MaxBodySizeMiddleware(app)(scope, receive, async_sender(sent))
    return sent, calls, reads


def async_sender(messages):
    async def send(message):
        messages.append(message)

    return send


@pytest.fixture(autouse=True)
def small_limit(monkeypatch):
    monkeypatch.setenv("API_MAX_BODY_BYTES", "16")
    from groundtruth.config import get_settings

    get_settings.cache_clear()


@pytest.mark.parametrize("length", [None, b"", b"invalid", b"-1", b"0", b"1", b"9" * 5000])
async def test_actual_overflow_rejected_before_handler(length):
    headers = [] if length is None else [(b"content-length", length)]
    sent, calls, reads = await invoke([b"12345678", b"123456789", b"unread tail"], headers=headers)
    assert sent[0]["status"] == 413
    assert not calls
    assert len(reads) <= 2


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
async def test_exact_boundary_and_empty_frames(method):
    sent, calls, _ = await invoke([b"", b"12345678", b"", b"12345678"], method=method)
    assert sent[0]["status"] == 200
    assert sent[-1]["body"] == b"1234567812345678"
    assert len(calls) == 1


async def test_declared_oversize_does_not_read_body():
    sent, calls, reads = await invoke([b"small"], headers=[(b"content-length", b"17")])
    assert sent[0]["status"] == 413
    assert not calls and not reads


async def test_duplicate_lengths_cannot_bypass_actual_limit():
    sent, calls, _ = await invoke(
        [b"x" * 17], headers=[(b"content-length", b"0"), (b"content-length", b"1")]
    )
    assert sent[0]["status"] == 413 and not calls


async def test_disconnect_does_not_start_handler():
    calls = []

    async def app(*args):
        calls.append(True)

    async def receive():
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": "/other", "headers": [], "query_string": b""}
    await MaxBodySizeMiddleware(app)(scope, receive, async_sender([]))
    assert not calls


async def test_get_passthrough():
    sent, calls, _ = await invoke([b"x" * 17], method="GET")
    assert sent[0]["status"] == 200 and calls


async def test_websocket_passthrough():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    await MaxBodySizeMiddleware(app)({"type": "websocket"}, None, None)
    assert calls == ["websocket"]


async def test_small_json_and_downstream_base_middleware():
    app = FastAPI()

    class Observe(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            assert await request.body() == b'{"ok":true}'
            return await call_next(request)

    app.add_middleware(Observe)

    @app.post("/api/contact")
    async def contact(payload: dict):
        return payload

    sent, calls, _ = await invoke([b'{"ok":', b"true}"], downstream=app)
    assert sent[0]["status"] == 200 and calls
    assert b"".join(m.get("body", b"") for m in sent) == b'{"ok":true}'


async def test_replay_then_real_disconnect():
    async def downstream(scope, receive, send):
        first = await receive()
        assert first == {"type": "http.request", "body": b"ok", "more_body": False}
        assert (await receive())["type"] == "http.disconnect"

    await invoke([b"ok"], downstream=downstream)
