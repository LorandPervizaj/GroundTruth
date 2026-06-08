"""Detect and record property lifecycle events between scrapes."""

from decimal import Decimal

from sqlalchemy.orm import Session

from groundtruth.logging import get_logger
from groundtruth.models.enums import PropertyEventType
from groundtruth.models.events import PropertyEvent

logger = get_logger(__name__)


class PropertyEventService:
    """
    Compare current vs previous listing state and emit property_events.

    Enables: days on market, price reductions, discount before sale, price velocity.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def detect_price_change(
        self,
        canonical_property_id: int,
        *,
        scrape_run_id: int | None,
        old_sale: Decimal | None,
        new_sale: Decimal | None,
        old_rent: Decimal | None = None,
        new_rent: Decimal | None = None,
        source_website: str | None = None,
    ) -> PropertyEvent | None:
        """Record a price reduction or increase event."""
        event_type = None
        change_pct = None

        if old_sale and new_sale and new_sale < old_sale:
            event_type = PropertyEventType.PRICE_REDUCED
            change_pct = float((old_sale - new_sale) / old_sale * 100)
        elif old_sale and new_sale and new_sale > old_sale:
            event_type = PropertyEventType.PRICE_INCREASED
            change_pct = float((new_sale - old_sale) / old_sale * 100)
        elif old_rent and new_rent and new_rent < old_rent:
            event_type = PropertyEventType.PRICE_REDUCED
            change_pct = float((old_rent - new_rent) / old_rent * 100)

        if not event_type:
            return None

        event = PropertyEvent(
            canonical_property_id=canonical_property_id,
            scrape_run_id=scrape_run_id,
            event_type=event_type,
            old_sale_price=old_sale,
            new_sale_price=new_sale,
            old_rent_price=old_rent,
            new_rent_price=new_rent,
            price_change_pct=change_pct,
            source_website=source_website,
        )
        self._session.add(event)
        self._session.flush()
        logger.info(
            "property_event_recorded",
            event_type=event_type.value,
            canonical_property_id=canonical_property_id,
            change_pct=change_pct,
        )
        return event

    def record_listed(
        self,
        canonical_property_id: int,
        scrape_run_id: int | None,
        source_website: str,
    ) -> PropertyEvent:
        """Record first-seen listing event."""
        event = PropertyEvent(
            canonical_property_id=canonical_property_id,
            scrape_run_id=scrape_run_id,
            event_type=PropertyEventType.LISTED,
            source_website=source_website,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def record_removed(
        self,
        canonical_property_id: int,
        scrape_run_id: int | None,
        source_website: str | None = None,
    ) -> PropertyEvent:
        """Record listing removal event."""
        event = PropertyEvent(
            canonical_property_id=canonical_property_id,
            scrape_run_id=scrape_run_id,
            event_type=PropertyEventType.REMOVED,
            source_website=source_website,
        )
        self._session.add(event)
        self._session.flush()
        return event
