import logging

from groundtruth.logging import configure_logging


def test_httpx_request_urls_are_not_logged() -> None:
    configure_logging()

    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
