"""Quick probe script for Gjirafa HTML structure."""
import re

import httpx

for url in [
    "https://listime.gjirafa.com/Shpallje/Patundshmeri",
    "https://listime.gjirafa.com/Top/Patundshmeri",
]:
    r = httpx.get(url, timeout=30, follow_redirects=True)
    print("URL", url, "->", r.url, r.status_code)
    ids = re.findall(r"banesa-\d+", r.text)
    print("  banesa ids:", len(set(ids)), list(sorted(set(ids)))[:5])
    links = re.findall(r'href="([^"]*Patundshmeri[^"]*)"', r.text)
    print("  href links:", len(set(links)), list(sorted(set(links)))[:5])
