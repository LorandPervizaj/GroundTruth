"""Verify Metrik release artifacts without rebuilding them."""

from __future__ import annotations

import sys

from groundtruth.config import get_settings
from groundtruth.release import verify_release_artifacts


def main() -> None:
    settings = get_settings()
    print(f"environment={settings.app_env}")
    try:
        for line in verify_release_artifacts():
            print(line)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
