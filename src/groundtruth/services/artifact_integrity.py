"""Release artifact integrity state for production startup and readiness."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ArtifactIntegrityState:
    """In-process result of the last release-artifact verification."""

    verified: bool = False
    error: str | None = None
    details: list[str] = field(default_factory=list)


_lock = threading.Lock()
_state = ArtifactIntegrityState()


def get_artifact_integrity_state() -> ArtifactIntegrityState:
    with _lock:
        return ArtifactIntegrityState(
            verified=_state.verified,
            error=_state.error,
            details=list(_state.details),
        )


def reset_artifact_integrity_state() -> None:
    with _lock:
        _state.verified = False
        _state.error = None
        _state.details = []


def verify_and_record_release_artifacts() -> ArtifactIntegrityState:
    """Run verify_release_artifacts and store the outcome for readiness checks."""
    from groundtruth.release import verify_release_artifacts

    reset_artifact_integrity_state()
    try:
        details = verify_release_artifacts()
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.critical("artifact_verification_failed: %s", msg)
        with _lock:
            _state.verified = False
            _state.error = msg
            _state.details = []
        return get_artifact_integrity_state()

    logger.info("artifact_verification_ok: %s", "; ".join(details))
    with _lock:
        _state.verified = True
        _state.error = None
        _state.details = list(details)
    return get_artifact_integrity_state()
