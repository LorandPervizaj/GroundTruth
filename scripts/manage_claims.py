"""CLI for immutable claim registry operations."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from groundtruth.claims import (
    Claim,
    active_claims,
    dataset_fingerprint,
    load_claims,
    next_claim_id,
    register_claim,
    sha256_file,
    sha256_sql,
    supersede_claim,
)
from groundtruth.database.session import get_session_factory
from groundtruth.methodology.version import METHODOLOGY_VERSION

app = typer.Typer()
console = Console()


@app.command("list")
def list_claims(active_only: bool = typer.Option(False, "--active")) -> None:
    claims = active_claims() if active_only else load_claims()
    table = Table(title="Claim registry")
    for col in ("claim_id", "claim_type", "status", "n", "methodology_version", "statement"):
        table.add_column(col)
    for claim in claims:
        table.add_row(
            claim.claim_id,
            claim.claim_type,
            claim.status,
            claim.n,
            claim.methodology_version,
            claim.statement[:60],
        )
    console.print(table)


@app.command("register")
def register(
    statement: str = typer.Option(..., help="Exact claim text"),
    claim_type: str = typer.Option("fact", help="fact|interpretation|negative|method"),
    claim_id: str | None = typer.Option(None),
    etl_date: str = typer.Option(""),
    etl_run_id: str = typer.Option(""),
    parser_version: str = typer.Option("1.3.0"),
    notebook: Path | None = typer.Option(None),
    query_path: str = typer.Option(""),
    sql: str = typer.Option("", help="SQL text to hash"),
    n: int | None = typer.Option(None),
    reviewer: str = typer.Option(""),
    status: str = typer.Option("draft"),
    notes: str = typer.Option(""),
    fingerprint_dataset: bool = typer.Option(False, help="Hash current DB snapshot"),
) -> None:
    """Register a new immutable claim."""
    claims = load_claims()
    cid = claim_id or next_claim_id(claims)
    dataset_hash = ""
    if fingerprint_dataset:
        session = get_session_factory()()
        try:
            dataset_hash = dataset_fingerprint(session, parser_version=parser_version)
        finally:
            session.close()

    claim = Claim(
        claim_id=cid,
        statement=statement,
        claim_type=claim_type,  # type: ignore[arg-type]
        etl_run_id=etl_run_id,
        etl_date=etl_date,
        parser_version=parser_version,
        methodology_version=METHODOLOGY_VERSION,
        notebook_path=str(notebook) if notebook else "",
        notebook_hash=sha256_file(notebook) if notebook and notebook.exists() else "",
        query_path=query_path,
        sql_hash=sha256_sql(sql) if sql else "",
        dataset_hash=dataset_hash,
        n=str(n) if n is not None else "",
        reviewer=reviewer,
        status=status,  # type: ignore[arg-type]
        notes=notes,
    )
    register_claim(claim)
    console.print(f"[green]Registered {cid}[/green]")


@app.command("supersede")
def supersede(
    old_id: str = typer.Option(..., help="Claim to supersede, e.g. GT-002"),
    statement: str = typer.Option(..., help="New claim statement"),
    claim_type: str = typer.Option("fact"),
    new_id: str | None = typer.Option(None),
    status: str = typer.Option("published"),
    notes: str = typer.Option(""),
) -> None:
    """Supersede an old claim with a new immutable claim."""
    new_claim = Claim(
        claim_id=new_id or "",
        statement=statement,
        claim_type=claim_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        methodology_version=METHODOLOGY_VERSION,
        notes=notes,
    )
    result = supersede_claim(old_id, new_claim)
    console.print(f"[green]Superseded {old_id} with {result.claim_id}[/green]")


@app.command("fingerprint")
def fingerprint(parser_version: str = typer.Option("1.3.0")) -> None:
    """Print dataset fingerprint for current normalized listings."""
    session = get_session_factory()()
    try:
        fp = dataset_fingerprint(session, parser_version=parser_version)
        console.print(fp)
    finally:
        session.close()


if __name__ == "__main__":
    app()
