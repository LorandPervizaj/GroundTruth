"""The homepage trust snapshot is a fallback artifact; /api/meta stays authoritative."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_home_trust_snapshot.py"
HOME_JS = ROOT / "web" / "static" / "home.js"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_home_trust_snapshot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meta(active_listings: int | None, updated: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        active_listings=active_listings, source_count=6, corpus_updated_at=updated
    )


def test_build_payload_uses_corpus_meta() -> None:
    module = _load_script()
    payload = module.build_payload(_meta(11888, datetime(2026, 10, 4, 23, 33, tzinfo=UTC)))
    assert payload == {"active_listings": 11888, "source_count": 6, "updated_at": "2026-10-04"}


@pytest.mark.parametrize(
    "meta",
    [_meta(0, datetime(2026, 10, 4, tzinfo=UTC)), _meta(None, None), _meta(11888, None)],
)
def test_build_payload_rejects_unusable_meta(meta: SimpleNamespace) -> None:
    assert _load_script().build_payload(meta) is None


def _run_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, meta: SimpleNamespace
) -> tuple[Path, str]:
    module = _load_script()
    out = tmp_path / "home-trust.json"
    out.write_text('{"active_listings": 10750, "updated_at": "2026-09-21"}\n', encoding="utf-8")
    session = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(module, "OUT", out)
    monkeypatch.setattr(module, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(module, "get_corpus_meta", lambda _session: meta)
    module.main()
    return out, out.read_text(encoding="utf-8")


def test_main_keeps_previous_snapshot_when_meta_is_unusable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, content = _run_main(monkeypatch, tmp_path, _meta(0, None))
    assert json.loads(content)["active_listings"] == 10750


def test_main_writes_fresh_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, content = _run_main(monkeypatch, tmp_path, _meta(11888, datetime(2026, 10, 4, tzinfo=UTC)))
    assert json.loads(content) == {
        "active_listings": 11888,
        "source_count": 6,
        "updated_at": "2026-10-04",
    }


def test_home_js_has_no_hardcoded_listing_count() -> None:
    source = HOME_JS.read_text(encoding="utf-8")
    assert "/api/meta" in source or "fetchCorpusMeta" in source
    assert "/static/home-trust.json" in source
    assert re.findall(r"\b\d{4,}\b", source) == []


@pytest.mark.parametrize("runner", ["run_weekly.ps1", "run_weekly_crawl.ps1"])
def test_legacy_weekly_runners_keep_crawl_exit_code(runner: str) -> None:
    script = (ROOT / "scripts" / runner).read_text(encoding="utf-8")
    assert "$crawlExit = $LASTEXITCODE" in script
    assert "exit $crawlExit" in script
    refresh = script.index("update_home_trust_snapshot.py")
    assert script.rindex("if ($crawlExit -eq 0)", 0, refresh) < refresh
