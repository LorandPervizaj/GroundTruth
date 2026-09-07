"""Typed scrape-time error codes (separate from ETL validation codes)."""

from __future__ import annotations

from enum import StrEnum


class ScrapeErrorCode(StrEnum):
    """Stable codes recorded on spiders and scrape_run metadata."""

    PARSE_EXCEPTION = "parse_exception"
    JSON_DECODE = "json_decode"
    UNEXPECTED_SHAPE = "unexpected_shape"
    MISSING_PAYLOAD = "missing_payload"
    SOFT_BLOCK = "soft_block"
    EMPTY_INDEX = "empty_index"
    HTTP_403 = "http_403"
    HTTP_429 = "http_429"
