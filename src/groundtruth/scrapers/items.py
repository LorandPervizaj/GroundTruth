"""Scrapy item definitions."""

import scrapy


class ListingItem(scrapy.Item):
    """Raw listing item emitted by spiders before pipeline processing."""

    source_website = scrapy.Field()
    spider_version = scrapy.Field()
    source_listing_id = scrapy.Field()
    original_url = scrapy.Field()
    raw_payload = scrapy.Field()
    raw_html = scrapy.Field()
    content_hash = scrapy.Field()
    scraped_at = scrapy.Field()
