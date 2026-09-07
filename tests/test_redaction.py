"""Tests for PII redaction utilities."""

from groundtruth.processing.redaction import (
    redact_agent,
    redact_provenance,
    redact_text,
    strip_agent_contact_fields,
)


class TestRedactText:
    def test_phone_kosovo_mobile(self) -> None:
        text = "Kontaktoni 044 393 777 për vizitë"
        assert "044" not in redact_text(text)
        assert "[redacted]" in redact_text(text)

    def test_email(self) -> None:
        assert "@" not in redact_text("Email: agent@example.com")

    def test_whatsapp_phrase(self) -> None:
        text = "WhatsApp me on 044123456"
        out = redact_text(text)
        assert "044123456" not in out

    def test_preserves_price_and_area(self) -> None:
        text = "Banesa 78m2, qira 450 euro"
        assert redact_text(text) == text


class TestRedactAgent:
    def test_strips_contact_fields(self) -> None:
        agent = {
            "fullName": "Agency X",
            "email": "secret@pro-rks.com",
            "phone": "+38344123456",
        }
        assert redact_agent(agent) == {"fullName": "Agency X"}

    def test_none_when_empty(self) -> None:
        assert redact_agent({"email": "x@y.com"}) is None


class TestProvenance:
    def test_redacts_snippet(self) -> None:
        prov = {
            "price": {
                "field": "price",
                "source_snippet": "Kontaktoni 044 111 222",
                "value": "450",
            }
        }
        out = redact_provenance(prov)
        assert "044" not in out["price"]["source_snippet"]


class TestStripAgentContactFields:
    def test_extra_fields_agent(self) -> None:
        out = strip_agent_contact_fields(
            {"agent": {"fullName": "A", "phone": "+38344"}, "title": "Sale"}
        )
        assert out["agent"] == {"fullName": "A"}
        assert out["title"] == "Sale"
