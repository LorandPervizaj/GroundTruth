"""Owner scrape commands talk to Azure only through the app identity."""

from unittest.mock import Mock

from groundtruth.services.product_notifications import owner_command_reply, telegram_command_reply
from groundtruth.services.scrape_control import (
    publish_scrape_progress,
    set_auto_update,
    start_scrape,
    stop_scrape,
)


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub")
    monkeypatch.setenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", "rg-metrik-beta-eus2")
    monkeypatch.setenv("GROUNDTRUTH_AZURE_JOB_NAME", "job-groundtruth-weekly")
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity.local/token")
    monkeypatch.setenv("IDENTITY_HEADER", "identity-header")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")


def _token(monkeypatch) -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"access_token": "arm-token"}
    monkeypatch.setattr(
        "groundtruth.services.scrape_control.httpx.get",
        Mock(return_value=response),
    )


def _arm(monkeypatch, handler) -> Mock:
    request = Mock(side_effect=handler)
    monkeypatch.setattr("groundtruth.services.scrape_control.httpx.request", request)
    return request


def _response(status: int, payload: dict | None = None) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = payload or {}
    return response


def test_help_lists_scrape_commands() -> None:
    help_text = telegram_command_reply("/help")
    assert "/scrape_start" in help_text
    assert "/auto_update on" in help_text
    assert "feedback" in help_text


def test_scrape_status_without_azure_config(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    monkeypatch.delenv("GROUNDTRUTH_AZURE_RESOURCE_GROUP", raising=False)
    text = owner_command_reply("/scrape")
    assert "No scrape is running" in text
    assert "not configured" in text


def test_scrape_status_reports_missing_job(monkeypatch) -> None:
    _configure(monkeypatch)
    _token(monkeypatch)

    def handler(method, url, **_kwargs):
        assert method == "GET"
        assert url.endswith("/jobs/job-groundtruth-weekly")
        return _response(404)

    _arm(monkeypatch, handler)
    text = owner_command_reply("/scrape")
    assert "not deployed" in text
    assert "not be started" in text


def test_scrape_status_reports_running_execution(monkeypatch) -> None:
    _configure(monkeypatch)
    _token(monkeypatch)

    def handler(method, url, **_kwargs):
        if url.endswith("/executions"):
            return _response(200, {"value": [{"name": "run-1", "properties": {"status": "Running"}}]})
        return _response(200, {"name": "job-groundtruth-weekly"})

    _arm(monkeypatch, handler)
    text = owner_command_reply("/scrape")
    assert "Scrape is running" in text
    assert "run-1" in text


def test_start_refuses_missing_job(monkeypatch) -> None:
    _configure(monkeypatch)
    _token(monkeypatch)
    request = _arm(monkeypatch, lambda method, url, **_kwargs: _response(404))
    text = start_scrape()
    assert "not deployed" in text
    assert request.call_count == 1


def test_stop_targets_running_execution(monkeypatch) -> None:
    _configure(monkeypatch)
    _token(monkeypatch)
    calls: list[tuple[str, str]] = []

    def handler(method, url, **_kwargs):
        calls.append((method, url))
        if url.endswith("/executions"):
            return _response(200, {"value": [{"name": "run-1", "properties": {"status": "Running"}}]})
        if url.endswith("/executions/run-1/stop"):
            return _response(202)
        return _response(200, {})

    _arm(monkeypatch, handler)
    assert stop_scrape() == "Stop requested for run-1."
    assert calls[-1] == ("POST", calls[-1][1])
    assert calls[-1][1].endswith("/executions/run-1/stop")


def test_auto_update_stays_quiet_until_a_scrape_is_running(monkeypatch) -> None:
    set_auto_update(False)
    monkeypatch.setattr(
        "groundtruth.services.scrape_control.scrape_snapshot",
        lambda: (False, "No scrape is running."),
    )
    sent: list[str] = []
    monkeypatch.setattr("groundtruth.services.scrape_control._notify", sent.append)
    text = owner_command_reply("/auto_update on")
    assert "are on" in text
    publish_scrape_progress()
    assert sent == []

    monkeypatch.setattr(
        "groundtruth.services.scrape_control.scrape_snapshot",
        lambda: (True, "Scrape is running."),
    )
    publish_scrape_progress()
    assert sent == ["Scrape is running."]

    monkeypatch.setattr(
        "groundtruth.services.scrape_control.scrape_snapshot",
        lambda: (False, "No scrape is running."),
    )
    publish_scrape_progress()
    assert sent[-1].startswith("The scrape stopped.")
    set_auto_update(False)


def test_auto_update_rejects_unknown_argument() -> None:
    set_auto_update(False)
    assert owner_command_reply("/automatic_update maybe") == "Use /auto_update on or /auto_update off."
    set_auto_update(False)
