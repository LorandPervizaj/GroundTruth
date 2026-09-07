"""Build public release artifacts for Metrik deployment.

Run after ETL/analytics on the private data host:

    uv run python scripts/build_release_artifacts.py
"""

from __future__ import annotations

from groundtruth.release import build_release_artifacts


def main() -> None:
    lookup_manifest, annual_path = build_release_artifacts()
    print(f"lookup_cache={lookup_manifest}")
    print(f"annual_report={annual_path}")


if __name__ == "__main__":
    main()
