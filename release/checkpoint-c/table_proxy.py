"""Isolated local Table/identity protocol fixture, never a cloud identity provider.

Only synthetic tokens accepted. Docker internal DNS routes the test-only Azure-shaped
hostname here. TLS stays verified. Backend is owned local Azurite, not Cosmos.
"""

import base64
import hashlib
import hmac
import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

ROOT = Path("/fixture/output")
C = json.loads((ROOT / "fixture.json").read_text())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log payloads or authorization.

    def forward(self):
        if self.server.server_port == 8080:
            query = parse_qs(urlsplit(self.path).query)
            assert self.headers.get("X-IDENTITY-HEADER") == C["identity_header"]
            assert query["resource"] == ["https://cosmos.azure.com"]
            assert query["client_id"] == ["checkpoint-c-synthetic"]
            body = json.dumps(
                dict(
                    access_token=C["token"],
                    expires_on=str(int(time.time()) + 3600),
                    resource="https://cosmos.azure.com",
                    token_type="Bearer",
                )
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        assert self.headers.get("Authorization") == "Bearer " + C["token"]
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        # Batch subrequests also contain absolute URIs; redirect their resource path.
        body = body.replace(
            b"https://checkpoint-c-table.table.cosmos.azure.com/",
            b"http://metrik-c-table:10002/localmetrik/",
        )
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in {"authorization", "host", "content-length", "connection"}
        }
        path = "/localmetrik" + self.path
        signed = (
            self.command
            + "\n"
            + headers.get("Content-MD5", "")
            + "\n"
            + headers.get("Content-Type", "")
            + "\n"
            + self.headers.get("x-ms-date", "")
            + "\n/localmetrik"
            + urlsplit(path).path
        )
        signature = base64.b64encode(
            hmac.new(base64.b64decode(C["tablekey"]), signed.encode(), hashlib.sha256).digest()
        ).decode()
        headers["Authorization"] = "SharedKey localmetrik:" + signature
        response = requests.request(
            self.command,
            "http://metrik-c-table:10002" + path,
            headers=headers,
            data=body,
            timeout=15,
        )
        self.send_response(response.status_code)
        for k, v in response.headers.items():
            if k.lower() not in {
                "connection",
                "transfer-encoding",
                "content-length",
                "content-encoding",
            }:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = forward


identity = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
threading.Thread(target=identity.serve_forever, daemon=True).start()
table = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(ROOT / "server.pem", ROOT / "server.key")
table.socket = context.wrap_socket(table.socket, server_side=True)
table.serve_forever()
