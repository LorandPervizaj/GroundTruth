"""Warm-thread lifecycle: shutdown join must be deterministic."""

from __future__ import annotations

import threading

from groundtruth.api import comparables_warm as cw


def test_stop_background_comparables_warm_joins_alive_thread() -> None:
    started = threading.Event()
    release = threading.Event()

    def _blocker() -> None:
        started.set()
        release.wait(timeout=5)

    fake = threading.Thread(target=_blocker, name="comparables-warm", daemon=True)
    with cw._lock:
        cw._warm_thread = fake
    fake.start()
    assert started.wait(timeout=2)
    assert fake.is_alive()
    threading.Timer(0.05, release.set).start()
    cw.stop_background_comparables_warm(timeout=2.0)
    assert not fake.is_alive()


def test_stop_background_comparables_warm_noop_when_idle() -> None:
    with cw._lock:
        cw._warm_thread = None
    cw.stop_background_comparables_warm(timeout=0.1)
