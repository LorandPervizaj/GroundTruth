"""Owner scrape commands control only the GitHub research workflow."""

from unittest.mock import Mock

import httpx

from groundtruth.services.product_notifications import owner_command_reply, telegram_command_reply
from groundtruth.services.scrape_control import scrape_snapshot, start_scrape, stop_scrape

RUNS = "/repos/LorandPervizaj/GroundTruth/actions/workflows/groundtruth-weekly-local.yml/runs"
DISPATCH = (
    "/repos/LorandPervizaj/GroundTruth/actions/workflows/groundtruth-weekly-local.yml/dispatches"
)


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("GROUNDTRUTH_GITHUB_TOKEN", "github_pat_secret")
    monkeypatch.delenv("GROUNDTRUTH_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GROUNDTRUTH_GITHUB_WORKFLOW", raising=False)


def _response(status: int, payload: dict | None = None) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = payload or {}
    return response


def _run(run_id: int, status: str, conclusion: str | None = None) -> dict:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "run_started_at": "2026-09-29T10:00:00Z",
        "html_url": f"https://github.com/LorandPervizaj/GroundTruth/actions/runs/{run_id}",
    }


def _github(monkeypatch, handler) -> Mock:
    request = Mock(side_effect=handler)
    monkeypatch.setattr("groundtruth.services.scrape_control.httpx.request", request)
    return request


def _path(url: str) -> str:
    return url.removeprefix("https://api.github.com")


def test_help_lists_scrape_commands_without_auto_update() -> None:
    help_text = telegram_command_reply("/help")
    assert "/scrape_start" in help_text
    assert "/scrape_stop" in help_text
    assert "/auto_update" not in help_text
    assert "feedback" in help_text


def test_unconfigured_service_never_calls_github(monkeypatch) -> None:
    monkeypatch.delenv("GROUNDTRUTH_GITHUB_TOKEN", raising=False)
    request = _github(monkeypatch, lambda *a, **k: _response(500))
    assert "not configured" in owner_command_reply("/scrape")
    assert "not configured" in start_scrape()
    assert "not configured" in stop_scrape()
    assert request.call_count == 0


def test_invalid_workflow_name_is_treated_as_unconfigured(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("GROUNDTRUTH_GITHUB_WORKFLOW", "../../secrets")
    request = _github(monkeypatch, lambda *a, **k: _response(200))
    assert "not configured" in start_scrape()
    assert request.call_count == 0


def test_requests_use_the_restricted_token_and_api_version(monkeypatch) -> None:
    _configure(monkeypatch)
    request = _github(monkeypatch, lambda *a, **k: _response(200, {"workflow_runs": []}))
    owner_command_reply("/scrape")
    headers = request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer github_pat_secret"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_status_reports_running_workflow(monkeypatch) -> None:
    _configure(monkeypatch)

    def handler(method, url, **_kwargs):
        assert (method, _path(url)) == ("GET", RUNS)
        return _response(200, {"workflow_runs": [_run(42, "in_progress")]})

    _github(monkeypatch, handler)
    running, text = scrape_snapshot()
    assert running is True
    assert "Research is running" in text
    assert "Run 42: in_progress" in text


def test_status_reports_latest_conclusion(monkeypatch) -> None:
    _configure(monkeypatch)
    _github(
        monkeypatch,
        lambda *a, **k: _response(200, {"workflow_runs": [_run(41, "completed", "failure")]}),
    )
    running, text = scrape_snapshot()
    assert running is False
    assert "Run 41: failure" in text


def test_status_with_no_runs(monkeypatch) -> None:
    _configure(monkeypatch)
    _github(monkeypatch, lambda *a, **k: _response(200, {"workflow_runs": []}))
    assert scrape_snapshot() == (False, "No research run has been recorded yet.")


def test_status_survives_github_errors(monkeypatch) -> None:
    _configure(monkeypatch)
    _github(monkeypatch, Mock(side_effect=httpx.ConnectError("down")))
    running, text = scrape_snapshot()
    assert running is False
    assert "Could not read" in text
    assert "github_pat_secret" not in text


def test_start_dispatches_master(monkeypatch) -> None:
    _configure(monkeypatch)
    calls: list[tuple[str, str, dict | None]] = []

    def handler(method, url, **kwargs):
        calls.append((method, _path(url), kwargs.get("json")))
        if method == "GET":
            return _response(200, {"workflow_runs": [_run(41, "completed", "success")]})
        return _response(204)

    _github(monkeypatch, handler)
    assert "requested on master" in start_scrape()
    assert calls[-1] == ("POST", DISPATCH, {"ref": "master"})


def test_start_refuses_overlap(monkeypatch) -> None:
    _configure(monkeypatch)
    request = _github(
        monkeypatch, lambda *a, **k: _response(200, {"workflow_runs": [_run(42, "queued")]})
    )
    text = start_scrape()
    assert "already queued" in text
    assert request.call_count == 1


def test_start_reports_permission_failure(monkeypatch) -> None:
    _configure(monkeypatch)

    def handler(method, url, **_kwargs):
        if method == "GET":
            return _response(200, {"workflow_runs": []})
        return _response(403)

    _github(monkeypatch, handler)
    assert "GitHub returned 403" in start_scrape()


def test_stop_cancels_active_run(monkeypatch) -> None:
    _configure(monkeypatch)
    calls: list[tuple[str, str]] = []

    def handler(method, url, **_kwargs):
        calls.append((method, _path(url)))
        if method == "GET":
            return _response(
                200, {"workflow_runs": [_run(42, "in_progress"), _run(41, "completed", "success")]}
            )
        return _response(202)

    _github(monkeypatch, handler)
    assert stop_scrape() == "Cancellation requested for run 42."
    assert calls[-1] == ("POST", "/repos/LorandPervizaj/GroundTruth/actions/runs/42/cancel")


def test_stop_with_nothing_active(monkeypatch) -> None:
    _configure(monkeypatch)
    request = _github(
        monkeypatch,
        lambda *a, **k: _response(200, {"workflow_runs": [_run(41, "completed", "success")]}),
    )
    assert stop_scrape() == "No research run is active."
    assert request.call_count == 1


def test_auto_update_is_retired() -> None:
    text = owner_command_reply("/auto_update on")
    assert "retired" in text


def test_public_app_no_longer_imports_a_scrape_watch() -> None:
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "src" / "groundtruth" / "api" / "app.py"
    assert "scrape_watch" not in app.read_text(encoding="utf-8")
