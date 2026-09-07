"""Export published claims as reasoning traces for machine consumption."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from groundtruth.claims import active_claims, load_claims
from groundtruth.config import PROJECT_ROOT

app = typer.Typer()


def _policy_links() -> dict[str, str]:
    """Map claim_id -> policy_id from decision policy JSON files."""
    links: dict[str, str] = {}
    policy_dir = PROJECT_ROOT / "data" / "decision_policies"
    if not policy_dir.is_dir():
        return links
    for path in policy_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        pid = data.get("policy_id")
        if not pid:
            continue
        for cid in data.get("depends_on_claims") or []:
            links[str(cid)] = pid
    return links


@app.command()
def export(
    output: Path = typer.Option(PROJECT_ROOT / "data" / "api" / "claims.json"),
    published_only: bool = typer.Option(True),
) -> None:
    """Write reasoning traces + dependency edges (not prose RAG)."""
    claims = active_claims() if published_only else load_claims()
    if published_only:
        claims = [c for c in claims if c.status == "published"]

    policies = _policy_links()
    traces = [c.to_reasoning_trace(policy_id=policies.get(c.claim_id)) for c in claims]
    edges = [
        {"from": dep, "to": trace["claim"], "type": "depends_on"}
        for trace in traces
        for dep in trace["depends_on"]
    ]

    payload = {
        "schema": "groundtruth.reasoning/v1",
        "count": len(traces),
        "claims": traces,
        "edges": edges,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(f"Exported {len(traces)} reasoning traces to {output}")


if __name__ == "__main__":
    app()
