"""Create only namespaced, loopback/internal synthetic local resources."""

import base64
import datetime as dt
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from azure.data.tables import TableServiceClient
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
NET = "metrik-c-internal-20261030"
FRONT = "metrik-c-loopback-20261030"
LABEL = "metrik.checkpoint-c=20261030"
PG = "metrik-c-postgres"
TABLE = "metrik-c-table"
APP = "metrik-c-candidate"
PROXY = "metrik-c-proxy"
HOST = "checkpoint-c-table.table.cosmos.azure.com"
ROLLBACK = "sha256:632fc5cb2ca183a0401e2e05609f80cb8b0509b20b388fe53dfd09bea412d775"


def run(args, **kwargs):
    p = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p.stdout.strip()


def config():
    return json.loads((OUT / "fixture.json").read_text())


def connection():
    return (
        "DefaultEndpointsProtocol=http;AccountName=localmetrik;AccountKey="
        + config()["tablekey"]
        + ";TableEndpoint=http://127.0.0.1:27402/localmetrik;"
    )


def table():
    return TableServiceClient.from_connection_string(connection()).get_table_client("CheckpointC")


def create():
    OUT.mkdir(parents=True, exist_ok=True)
    assert not (OUT / "fixture.json").exists(), "Retained fixture: refuse overwrite"
    c = dict(
        tablekey=base64.b64encode(os.urandom(32)).decode(),
        password=uuid.uuid4().hex,
        ops=uuid.uuid4().hex,
        identity_header=uuid.uuid4().hex,
        token=uuid.uuid4().hex,
    )
    (OUT / "fixture.json").write_text(json.dumps(c))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5))
        .not_valid_after(dt.datetime.now(dt.UTC) + dt.timedelta(days=14))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (OUT / "server.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (OUT / "server.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    run(["docker", "network", "create", "--internal", "--label", LABEL, NET])
    run(["docker", "network", "create", "--label", LABEL, FRONT])
    run(["docker", "volume", "create", "--label", LABEL, "metrik-c-table-data"])
    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            PG,
            "--label",
            LABEL,
            "--network",
            NET,
            "-p",
            "127.0.0.1:27451:5432",
            "-e",
            "POSTGRES_USER=checkpoint_test",
            "-e",
            "POSTGRES_DB=checkpoint_test",
            "-e",
            "POSTGRES_PASSWORD=" + c["password"],
            "postgres:16-alpine",
        ]
    )
    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            TABLE,
            "--label",
            LABEL,
            "--network",
            NET,
            "-p",
            "127.0.0.1:27402:10002",
            "-e",
            "AZURITE_ACCOUNTS=localmetrik:" + c["tablekey"],
            "-v",
            "metrik-c-table-data:/data",
            "mcr.microsoft.com/azure-storage/azurite:3.35.0",
            "azurite-table",
            "--tableHost",
            "0.0.0.0",
            "--location",
            "/data",
            "--silent",
        ]
    )
    for name in (PG, TABLE):
        run(["docker", "network", "connect", FRONT, name])
    for _ in range(45):
        try:
            svc = TableServiceClient.from_connection_string(connection(), retry_total=0)
            svc.create_table("CheckpointC")
            table().create_entity(
                {"PartitionKey": "_health", "RowKey": "schema-v1", "SchemaVersion": 1}
            )
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Local table startup failed")


def start_proxy(image):
    run(
        [
            "docker",
            "run",
            "-d",
            "--user",
            "0",
            "--name",
            PROXY,
            "--label",
            LABEL,
            "--network",
            NET,
            "--network-alias",
            HOST,
            "-v",
            str(ROOT) + ":/fixture:ro",
            "--entrypoint",
            "/app/.venv/bin/python",
            image,
            "/fixture/table_proxy.py",
        ]
    )


def app(image, name=APP, port=18765, migrate=False):
    c = config()
    env = dict(
        APP_ENV="production",
        DATABASE_URL=f"postgresql+psycopg://checkpoint_test:{c['password']}@{PG}:5432/checkpoint_test",
        HEALTH_CHECK_TOKEN=c["ops"],
        PRODUCT_WRITE_BACKEND="azure_table",
        PRODUCT_TABLE_ENDPOINT="https://" + HOST,
        PRODUCT_TABLE_NAME="CheckpointC",
        PRODUCT_TABLE_IDENTITY_CLIENT_ID="checkpoint-c-synthetic",
        PRODUCT_TABLE_CONNECTION_STRING="",
        IDENTITY_ENDPOINT=f"http://{PROXY}:8080/token",
        IDENTITY_HEADER=c["identity_header"],
        REQUESTS_CA_BUNDLE="/fixture/output/server.pem",
        SSL_CERT_FILE="/fixture/output/server.pem",
        API_REQUIRE_LOOKUP_CACHE="true",
        API_DOCS_ENABLED="false",
        API_RATE_LIMIT_ENABLED="true",
        RUN_MIGRATIONS_ON_START=str(migrate).lower(),
        REQUIRE_SENTRY_DSN="false",
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_CHAT_ID="",
        SENTRY_DSN="",
        PUBLIC_BASE_URL=f"http://127.0.0.1:{port}",
        TRUSTED_HOSTS="localhost,127.0.0.1",
        FORWARDED_ALLOW_IPS="127.0.0.1",
        VALUATION_PUBLIC_ENABLED="true",
        ALERTS_SIGNUP_ENABLED="false",
        API_RATE_LIMIT_CONTACT="1000/hour",
        API_RATE_LIMIT_EVENTS="1000/minute",
        API_RATE_LIMIT_VALUATE="1000/minute",
        DATABASE_POOL_SIZE="2",
        DATABASE_MAX_OVERFLOW="0",
    )
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        LABEL,
        "--network",
        NET,
        "-p",
        f"127.0.0.1:{port}:8000",
        "-v",
        str(ROOT) + ":/fixture:ro",
    ]
    for k, v in env.items():
        args.extend(["-e", k + "=" + v])
    run(args + [image])
    run(["docker", "network", "connect", FRONT, name])
    for _ in range(90):
        try:
            if (
                httpx.get(
                    f"http://127.0.0.1:{port}/api/ready", timeout=2, trust_env=False
                ).status_code
                == 200
            ):
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Local production-mode app not ready; inspect owned logs")


if __name__ == "__main__":
    create()
    print("Created isolated synthetic fixture; no cloud access")
