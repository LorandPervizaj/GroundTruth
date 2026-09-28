"""Owner controls for the Azure weekly scrape job.

The public app uses its managed identity. It never stores an Azure password.
That identity needs permission to read, start, and stop Microsoft.App jobs,
including job executions, in the research resource group.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx

from groundtruth.logging import get_logger

logger = get_logger(__name__)

_API = "2024-03-01"
_RUNNING = {"Running", "Processing", "Degraded"}
_DEFAULT_INTERVAL_SECONDS = 30 * 60

_lock = threading.Lock()
_auto_update = False
_stop = threading.Event()
_thread: threading.Thread | None = None
_was_running = False


def auto_update_enabled() -> bool:
    with _lock:
        return _auto_update


def set_auto_update(enabled: bool) -> None:
    global _auto_update
    with _lock:
        _auto_update = enabled


def scrape_snapshot() -> tuple[bool, str]:
    """Return whether a scrape execution is active, plus a short owner message."""
    try:
        return _scrape_snapshot()
    except Exception:
        logger.exception("scrape_status_failed")
        return False, "Could not read scrape status."


def start_scrape() -> str:
    job = _job_name()
    group = os.getenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "").strip()
    if not _configured():
        return _unconfigured(job)
    token = _access_token()
    if token is None:
        return _no_identity()
    found, message = _job_exists(token, job)
    if not found:
        return message
    response = _arm(
        "POST",
        f"{_job_url(job)}/start",
        token,
    )
    if response.status_code in {200, 202}:
        return f"Start requested for {job} in {group}."
    logger.warning("scrape_start_failed", status=response.status_code)
    return f"Could not start {job}. Azure returned {response.status_code}."


def stop_scrape() -> str:
    job = _job_name()
    if not _configured():
        return _unconfigured(job)
    token = _access_token()
    if token is None:
        return _no_identity()
    found, message = _job_exists(token, job)
    if not found:
        return message
    running, error = _running_executions(token, job)
    if error:
        return error
    if not running:
        return f"{job} is not running."
    stopped: list[str] = []
    for name in running:
        response = _arm(
            "POST",
            f"{_job_url(job)}/executions/{name}/stop",
            token,
        )
        if response.status_code in {200, 202}:
            stopped.append(name)
        else:
            logger.warning("scrape_stop_failed", status=response.status_code, execution=name)
            return f"Could not stop {name}. Azure returned {response.status_code}."
    return "Stop requested for " + ", ".join(stopped) + "."


def auto_update_reply(argument: str) -> str:
    """Turn 30-minute progress messages on or off. Idle scrapes stay quiet."""
    choice = argument.strip().lower()
    if choice in {"on", "start", "enable"}:
        set_auto_update(True)
        enabled = True
    elif choice in {"off", "stop", "disable"}:
        set_auto_update(False)
        enabled = False
    elif choice == "":
        enabled = not auto_update_enabled()
        set_auto_update(enabled)
    else:
        return "Use /auto_update on or /auto_update off."
    running, status = scrape_snapshot()
    state = "on" if enabled else "off"
    extra = ""
    if enabled:
        extra = (
            "\nWhile a scrape is running, this chat gets a progress message every 30 minutes."
            if running
            else "\nNo scrape is running. The next running scrape will send updates every 30 minutes."
        )
    return f"Automatic scrape updates are {state}.\n{status}{extra}"


def start_scrape_watch() -> None:
    """Start the progress thread. It stays quiet until /auto_update is enabled."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_watch_loop, name="scrape-watch", daemon=True)
    _thread.start()


def stop_scrape_watch() -> None:
    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
        thread.join(timeout=2)


def publish_scrape_progress() -> None:
    """Send one progress message when updates are on and a scrape is active."""
    global _was_running
    if not auto_update_enabled():
        _was_running = False
        return
    running, text = scrape_snapshot()
    if running:
        _notify(text)
        _was_running = True
    elif _was_running:
        _notify(f"The scrape stopped.\n{text}")
        _was_running = False


def _watch_loop() -> None:
    while not _stop.is_set():
        if _stop.wait(_interval_seconds()):
            return
        publish_scrape_progress()


def _interval_seconds() -> float:
    raw = os.getenv("SCRAPE_UPDATE_INTERVAL_SECONDS", "").strip()
    if not raw:
        return float(_DEFAULT_INTERVAL_SECONDS)
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return float(_DEFAULT_INTERVAL_SECONDS)


def _notify(text: str) -> None:
    from groundtruth.services.product_notifications import notify_product_submission

    notify_product_submission("scrape", {"message": text})


def _scrape_snapshot() -> tuple[bool, str]:
    job = _job_name()
    group = os.getenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "").strip()
    if not _configured():
        return False, _unconfigured(job)
    token = _access_token()
    if token is None:
        return False, _no_identity()
    found, message = _job_exists(token, job)
    if not found:
        return False, message
    running, error = _running_executions(token, job)
    if error:
        return False, error
    if not running:
        return False, f"No scrape is running.\nJob {job} in {group} is idle."
    listed = ", ".join(running)
    return True, f"Scrape is running.\nJob {job} in {group}.\nExecution: {listed}"


def _configured() -> bool:
    return bool(
        os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
        and os.getenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "").strip()
    )


def _job_name() -> str:
    return os.getenv("GROUNDTRUTH_AZURE_JOB_NAME", "job-groundtruth-weekly").strip()


def _unconfigured(job: str) -> str:
    return (
        f"No scrape is running.\n{job} is not configured on this service, "
        "so the bot cannot see or start it."
    )


def _no_identity() -> str:
    return "No scrape is running. This service has no Azure identity to inspect the job."


def _job_exists(token: str, job: str) -> tuple[bool, str]:
    response = _arm("GET", _job_url(job), token)
    if response.status_code == 200:
        return True, ""
    if response.status_code == 404:
        group = os.getenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "").strip()
        return False, (
            f"No scrape is running.\n{job} is not deployed in {group}, "
            "so it cannot be started from the bot yet."
        )
    logger.warning("scrape_job_lookup_failed", status=response.status_code)
    return False, f"Could not read {job}. Azure returned {response.status_code}."


def _running_executions(token: str, job: str) -> tuple[list[str] | None, str]:
    response = _arm("GET", f"{_job_url(job)}/executions", token)
    if response.status_code != 200:
        logger.warning("scrape_executions_failed", status=response.status_code)
        return None, f"Could not list scrape executions. Azure returned {response.status_code}."
    payload = response.json()
    names: list[str] = []
    for item in payload.get("value") or []:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") or {}
        status = str(props.get("status") or "")
        if status in _RUNNING and item.get("name"):
            names.append(str(item["name"]))
    return names, ""


def _job_url(job: str) -> str:
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    group = os.getenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "").strip()
    return (
        "https://management.azure.com"
        f"/subscriptions/{subscription}"
        f"/resourceGroups/{group}"
        f"/providers/Microsoft.App/jobs/{job}"
    )


def _arm(
    method: str,
    url: str,
    token: str,
    *,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    return httpx.request(
        method,
        url,
        params={"api-version": _API},
        headers={"Authorization": f"Bearer {token}"},
        json=json,
        timeout=20.0,
    )


def _access_token() -> str | None:
    endpoint = os.getenv("IDENTITY_ENDPOINT", "").strip()
    header = os.getenv("IDENTITY_HEADER", "").strip()
    if not endpoint or not header:
        return None
    params = {
        "api-version": "2019-08-01",
        "resource": "https://management.azure.com/",
    }
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    if client_id:
        params["client_id"] = client_id
    try:
        response = httpx.get(
            endpoint,
            params=params,
            headers={"X-IDENTITY-HEADER": header},
            timeout=10.0,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
    except (httpx.HTTPError, OSError, ValueError):
        logger.exception("azure_identity_token_failed")
        return None
    return str(token) if token else None
