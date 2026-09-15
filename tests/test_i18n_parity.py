"""Albanian/English translation key parity and usage coverage."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "web" / "static" / "i18n.js"
WEB = ROOT / "web"


def _brace_block(text: str, start_idx: int) -> str:
    i = text.find("{", start_idx)
    depth = 0
    for j, ch in enumerate(text[i:], start=i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j]
    return ""


def _keys(block: str) -> set[str]:
    return set(re.findall(r"^\s*([A-Za-z0-9_]+)\s*:", block, flags=re.M))


def _locale_keys() -> tuple[set[str], set[str]]:
    text = I18N.read_text(encoding="utf-8")
    m_sq = re.search(r"\bsq\s*:\s*\{", text)
    m_en = re.search(r"\ben\s*:\s*\{", text)
    assert m_sq and m_en
    return _keys(_brace_block(text, m_sq.start())), _keys(_brace_block(text, m_en.start()))


def test_sq_en_key_sets_match() -> None:
    sq, en = _locale_keys()
    assert sq == en, f"only_sq={sorted(sq - en)[:20]} only_en={sorted(en - sq)[:20]}"


def test_used_keys_exist_in_both_locales() -> None:
    sq, en = _locale_keys()
    used: set[str] = set()
    for path in WEB.rglob("*.html"):
        used |= set(re.findall(r'data-i18n="([^"]+)"', path.read_text(encoding="utf-8")))
    for path in (WEB / "static").glob("*.js"):
        txt = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bt\(\s*"([A-Za-z0-9_]+)"', txt))
        used |= set(re.findall(r"\bt\(\s*'([A-Za-z0-9_]+)'", txt))
    missing_sq = sorted(k for k in used if k not in sq)
    missing_en = sorted(k for k in used if k not in en)
    assert not missing_sq, missing_sq[:30]
    assert not missing_en, missing_en[:30]
