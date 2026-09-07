"""Load gazetteer JSON files into PostgreSQL reference tables."""

import typer
from rich.console import Console
from sqlalchemy import text

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.logging import configure_logging
from groundtruth.models.reference import Building, Complex, District, Neighborhood, Street

console = Console()


def _upsert_neighborhood(session, entry: dict) -> None:
    existing = session.query(Neighborhood).filter_by(slug=entry["slug"]).first()
    if existing:
        existing.name = entry["name"]
        existing.city = entry["city"]
        existing.centroid_lat = entry.get("centroid_lat")
        existing.centroid_lng = entry.get("centroid_lng")
        existing.aliases = entry.get("aliases")
        return
    session.add(
        Neighborhood(
            id=entry.get("id"),
            name=entry["name"],
            slug=entry["slug"],
            city=entry["city"],
            centroid_lat=entry.get("centroid_lat"),
            centroid_lng=entry.get("centroid_lng"),
            aliases=entry.get("aliases"),
        )
    )


def _upsert_street(session, entry: dict, neighborhood_map: dict[str, int]) -> None:
    existing = session.query(Street).filter_by(slug=entry["slug"]).first()
    nh_id = neighborhood_map.get(entry.get("neighborhood_slug"))
    if not nh_id:
        return
    if existing:
        existing.name = entry["name"]
        existing.neighborhood_id = nh_id
        existing.aliases = entry.get("aliases")
        return
    session.add(
        Street(
            id=entry.get("id"),
            name=entry["name"],
            slug=entry["slug"],
            neighborhood_id=nh_id,
            aliases=entry.get("aliases"),
        )
    )


def _upsert_district(session, entry: dict, neighborhood_map: dict[str, int]) -> None:
    existing = session.query(District).filter_by(slug=entry["slug"]).first()
    nh_id = neighborhood_map.get(entry.get("neighborhood_slug"))
    if not nh_id:
        return
    if existing:
        existing.name = entry["name"]
        existing.neighborhood_id = nh_id
        existing.aliases = entry.get("aliases")
        existing.district_type = entry.get("district_type")
        return
    session.add(
        District(
            id=entry.get("id"),
            name=entry["name"],
            slug=entry["slug"],
            neighborhood_id=nh_id,
            aliases=entry.get("aliases"),
            district_type=entry.get("district_type"),
        )
    )


def _upsert_complex(
    session,
    entry: dict,
    neighborhood_map: dict[str, int],
    district_map: dict[str, int],
) -> None:
    existing = session.query(Complex).filter_by(slug=entry["slug"]).first()
    nh_slug = entry.get("neighborhood_slug")
    nh_id = neighborhood_map.get(nh_slug)
    if not nh_id:
        return
    district_id = (
        district_map.get(entry.get("district_slug")) if entry.get("district_slug") else None
    )
    if existing:
        existing.name = entry["name"]
        existing.neighborhood_id = nh_id
        existing.district_id = district_id
        existing.aliases = entry.get("aliases")
        existing.notes = entry.get("notes")
        return
    session.add(
        Complex(
            id=entry.get("id"),
            name=entry["name"],
            slug=entry["slug"],
            neighborhood_id=nh_id,
            district_id=district_id,
            aliases=entry.get("aliases"),
            notes=entry.get("notes"),
        )
    )


def _upsert_building(
    session, entry: dict, neighborhood_map: dict[str, int], complex_map: dict[str, int]
) -> None:
    existing = session.query(Building).filter_by(slug=entry["slug"]).first()
    if existing:
        existing.name = entry["name"]
        existing.complex_id = complex_map.get(entry.get("complex_slug"))
        existing.neighborhood_id = neighborhood_map.get(entry.get("neighborhood_slug"))
        existing.aliases = entry.get("aliases")
        return
    session.add(
        Building(
            id=entry.get("id"),
            name=entry["name"],
            slug=entry["slug"],
            complex_id=complex_map.get(entry.get("complex_slug")),
            neighborhood_id=neighborhood_map.get(entry.get("neighborhood_slug")),
            aliases=entry.get("aliases"),
        )
    )


def load() -> None:
    """Import JSON gazetteers into neighborhoods, streets, complexes, buildings tables."""
    configure_logging()
    settings = get_settings()
    gazetteer = GazetteerService(settings.gazetteer_dir)
    gazetteer.load()

    session_factory = get_session_factory()
    session = session_factory()

    try:
        max_id = (
            session.query(Neighborhood.id).order_by(Neighborhood.id.desc()).limit(1).scalar() or 0
        )
        session.execute(text(f"SELECT setval('neighborhoods_id_seq', {max_id}, true)"))

        for entry in gazetteer._data.get("neighborhoods", []):
            _upsert_neighborhood(session, entry)

        session.flush()
        neighborhood_map = {n.slug: n.id for n in session.query(Neighborhood).all()}

        for entry in gazetteer._data.get("streets", []):
            _upsert_street(session, entry, neighborhood_map)

        session.flush()

        deprecated_street_slugs = {"rruga-b-lakrishte", "rruga-b-mati-1"}
        for slug in deprecated_street_slugs:
            orphan = session.query(Street).filter_by(slug=slug).first()
            if orphan:
                session.delete(orphan)

        session.flush()

        for entry in gazetteer._data.get("districts", []):
            _upsert_district(session, entry, neighborhood_map)

        session.flush()
        district_map = {d.slug: d.id for d in session.query(District).all()}

        for entry in gazetteer._data.get("complexes", []):
            _upsert_complex(session, entry, neighborhood_map, district_map)

        session.flush()

        for entry in gazetteer._data.get("neighborhoods", []):
            if not entry.get("canonical_slug"):
                continue
            merged = session.query(Neighborhood).filter_by(slug=entry["slug"]).first()
            if merged and merged.slug != entry["canonical_slug"]:
                merged.aliases = entry.get("aliases")
        complex_map = {c.slug: c.id for c in session.query(Complex).all()}

        for entry in gazetteer._data.get("buildings", []):
            _upsert_building(session, entry, neighborhood_map, complex_map)

        counts = {
            "neighborhoods": session.query(Neighborhood).count(),
            "districts": session.query(District).count(),
            "streets": session.query(Street).count(),
            "complexes": session.query(Complex).count(),
            "buildings": session.query(Building).count(),
        }
        session.commit()
        console.print(f"[green]Gazetteers loaded: {counts}[/green]")
    except Exception as exc:
        session.rollback()
        console.print(f"[red]Failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        session.close()


if __name__ == "__main__":
    typer.run(load)
