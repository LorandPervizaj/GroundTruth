"""Fresh disposable databases must load references without invalid sequence IDs."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from groundtruth.config import get_settings


@pytest.mark.parametrize("existing,incoming,expected", [(None, [], 1), (None, [47, 52], 53), (80, [47], 81)])
def test_reference_sequence_handles_empty_and_explicit_ids(require_postgres, existing, incoming, expected):
    spec = importlib.util.spec_from_file_location("release_load_gazetteers", Path("scripts/load_gazetteers.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(str(get_settings().database_url))
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("CREATE TEMP TABLE neighborhoods (id integer)"))
            connection.execute(text("CREATE TEMP SEQUENCE neighborhoods_id_seq"))
            if existing is not None:
                connection.execute(text("INSERT INTO neighborhoods VALUES (:id)"), {"id": existing})
            with Session(bind=connection) as session:
                module._reserve_neighborhood_ids(session, [{"id": value} for value in incoming])
                assert session.execute(text("SELECT nextval('neighborhoods_id_seq')")).scalar_one() == expected
            transaction.rollback()
    finally:
        engine.dispose()
