"""
paws/backend/recalls.py — ROUND 23: FOOD RECALL ALERTS (reviewer #6)
The trust play: check what the user feeds against the FDA's public recall
feed, warn them BEFORE they feed a recalled bag, and capture the
switching event (the data brands pay for during recalls).

openFDA is free (no key for low volume). We cache the feed daily so we
don't hammer the API, then match by brand + product keywords.
"""
import json
import time
import urllib.request
import os

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "state", "recall_cache.json")
CACHE_TTL = 86400  # refresh daily


def _fetch_feed(limit: int = 50) -> list:
    """Fetch recent pet-food recalls from openFDA."""
    # pet food is filed under food enforcement; search common pet terms
    url = ("https://api.fda.gov/food/enforcement.json?search="
           "product_description:%22dog+food%22+OR+product_description:"
           "%22cat+food%22+OR+product_description:%22pet+food%22"
           f"&limit={limit}&sort=recall_initiation_date:desc")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "paws/0.1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
        return d.get("results", [])
    except Exception:
        return []


def recall_feed(force: bool = False) -> dict:
    """The cached recall feed (daily refresh)."""
    if not force and os.path.exists(CACHE):
        age = time.time() - os.path.getmtime(CACHE)
        if age < CACHE_TTL:
            try:
                with open(CACHE) as f:
                    return json.load(f)
            except Exception:
                pass
    results = _fetch_feed()
    out = []
    for r in results:
        out.append({
            "firm": r.get("recalling_firm", ""),
            "product": (r.get("product_description") or "")[:120],
            "reason": (r.get("reason_for_recall") or "")[:120],
            "date": r.get("recall_initiation_date", ""),
            "classification": r.get("classification", ""),
            "status": r.get("status", ""),
        })
    feed = {"fetched_at": time.time(), "recalls": out}
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(feed, f)
    except Exception:
        pass
    return feed


def match_recalls(feed: dict, brand: str, product: str) -> list:
    """Does this pet's food match any active recall? Match on brand or
    product keywords (case-insensitive, lenient)."""
    if not brand and not product:
        return []
    b = (brand or "").lower()
    p = (product or "").lower()
    hits = []
    for r in feed.get("recalls", []):
        firm = (r.get("firm") or "").lower()
        prod = (r.get("product") or "").lower()
        # brand/firm match OR product-name keyword overlap
        brand_ok = b and (b in firm or firm in b or any(
            w in firm for w in b.split() if len(w) > 3))
        prod_ok = p and any(
            w in prod for w in p.split() if len(w) > 4)
        if brand_ok or prod_ok:
            hits.append(r)
    return hits
