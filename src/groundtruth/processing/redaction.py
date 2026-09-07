"""PII redaction for public display, exports, and debug tooling.

Contact data in listing descriptions is research input only. User-facing surfaces
and default export/debug output must not reproduce phones, emails, or messenger handles.
"""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "[redacted]"

# Kosovo / regional mobiles and landlines; international +383 variants.
_PHONE_RE = re.compile(
    r"""
    (?<!\d)
    (?:
        (?:(?:\+|00)?383[\s.\-]?)?     # country code (optional)
        (?:0)?                           # trunk zero
        (?:4[3-9]|2[89]|3[89])           # operator prefix
        [\s.\-]?
        (?:\d[\s.\-]?){6,8}              # remaining digits
    )
    (?!\d)
    """,
    re.VERBOSE,
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# WhatsApp / Viber / Telegram / messenger deep links and @handles in contact context.
_MESSENGER_RE = re.compile(
    r"(?i)\b(?:whatsapp|viber|telegram|signal|messenger)"
    r"(?:\s*(?:me\s+on|nr\.?|numri|kontaktoni|contact))?\s*[:@]?\s*[\w./+\-]+"
)

_SOCIAL_URL_RE = re.compile(
    r"(?i)https?://(?:www\.)?(?:wa\.me|api\.whatsapp\.com|viber://|t\.me|m\.me)/\S+"
)

_AGENT_CONTACT_KEYS = frozenset({"email", "phone", "mobile", "telephone", "whatsapp", "viber"})


def redact_text(text: str | None, *, max_length: int | None = None) -> str:
    """Strip phone numbers, emails, and messenger handles from free text."""
    if not text:
        return ""
    out = _SOCIAL_URL_RE.sub(_REDACTED, text)
    out = _MESSENGER_RE.sub(_REDACTED, out)
    out = _EMAIL_RE.sub(_REDACTED, out)
    out = _PHONE_RE.sub(_REDACTED, out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    if max_length is not None and len(out) > max_length:
        return out[:max_length] + "…"
    return out


def redact_agent(agent: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep agency display name only; drop direct contact fields."""
    if not agent or not isinstance(agent, dict):
        return None
    name = agent.get("fullName") or agent.get("name") or agent.get("agencyName")
    if not name:
        return None
    return {"fullName": str(name)}


def redact_provenance_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Redact snippets in a single provenance field record."""
    out = dict(entry)
    if "source_snippet" in out and out["source_snippet"]:
        out["source_snippet"] = redact_text(str(out["source_snippet"]), max_length=120)
    if "value" in out and isinstance(out["value"], str):
        out["value"] = redact_text(out["value"], max_length=200)
    return out


def redact_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    """Redact all field provenance entries for safe terminal/export display."""
    return {key: redact_provenance_entry(val) for key, val in provenance.items()}


def strip_agent_contact_fields(extra_fields: dict[str, Any] | None) -> dict[str, Any]:
    """Remove contact-bearing agent payload before persisting parsed extras."""
    if not extra_fields:
        return {}
    out = dict(extra_fields)
    if "agent" in out:
        out["agent"] = redact_agent(out.get("agent"))  # type: ignore[arg-type]
    return out
