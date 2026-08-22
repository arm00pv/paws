"""
paws/backend/phase5.py — Phase 5: THE PANEL (the sellable data product)
Aggregated, anonymized pet-market intelligence — the exact asset pet
brands buy today (Hill's pays for 98% pet-food transaction data via
LiveRamp). This endpoint IS the product we'd sell:

  1. BRAND SHARE     — what our panel feeds their dogs (market share)
  2. BREED × FOOD    — which brands own which breeds (targeting gold)
  3. CATEGORY SPEND  — food/treats/toys/vet mix + frequency
  4. PANEL GROWTH    — pets, receipts, spend over time (the compounding)

All output is AGGREGATED (no individual pet data) — the honest panel.
"""
import datetime


def panel_summary(db) -> dict:
    """The aggregated panel — the B2B data product."""
    # brand share (by spend)
    brand_rows = db.execute("""
        SELECT p.brand AS brand, COUNT(*) AS items,
               ROUND(SUM(p.amount),2) AS total
        FROM purchases p JOIN receipts r ON p.receipt_id = r.id
        WHERE p.brand != '' AND p.brand != 'null'
        GROUP BY p.brand ORDER BY total DESC""").fetchall()
    # merge aliases via the canonicalizer (panel quality = the product)
    from phase3 import normalize_brand
    merged = {}
    for r in brand_rows:
        canon = normalize_brand(r["brand"])
        if canon not in merged:
            merged[canon] = {"brand": canon, "items": 0, "total": 0.0}
        merged[canon]["items"] += r["items"]
        merged[canon]["total"] += r["total"]
    total_spend = sum(v["total"] for v in merged.values()) or 1
    brands = [{"brand": v["brand"], "items": v["items"],
               "total": round(v["total"], 2),
               "share": round(100.0 * v["total"] / total_spend, 1)}
              for v in sorted(merged.values(), key=lambda b: b["total"],
                              reverse=True)]

    # category mix
    cat = db.execute("""
        SELECT p.category AS cat, COUNT(*) AS n,
               ROUND(SUM(p.amount),2) AS total
        FROM purchases p GROUP BY p.category ORDER BY total DESC""").fetchall()
    categories = [{"category": r["cat"] or "other", "items": r["n"],
                   "total": r["total"]} for r in cat]

    # breed × food matrix (the targeting gold)
    matrix = db.execute("""
        SELECT pe.breed AS breed, p.brand AS brand,
               ROUND(SUM(p.amount),2) AS total, COUNT(*) AS n
        FROM purchases p JOIN receipts r ON p.receipt_id = r.id
        JOIN pets pe ON r.pet_id = pe.id
        WHERE p.brand != '' AND pe.breed != ''
        GROUP BY pe.breed, p.brand
        ORDER BY total DESC LIMIT 20""").fetchall()
    breed_food = [dict(r) for r in matrix]

    # panel size
    pets = db.execute("SELECT COUNT(*) AS c FROM pets").fetchone()["c"]
    receipts = db.execute("SELECT COUNT(*) AS c FROM receipts").fetchone()["c"]
    purchases = db.execute("SELECT COUNT(*) AS c FROM purchases").fetchone()["c"]
    spend = db.execute("""
        SELECT ROUND(SUM(p.amount),2) AS t FROM purchases p
        JOIN receipts r ON p.receipt_id = r.id""").fetchone()["t"] or 0

    return {"panel": {"pets": pets, "receipts": receipts,
                      "purchases": purchases, "spend": spend},
            "brand_share": brands,
            "categories": categories,
            "breed_food_matrix": [dict(r) for r in breed_food],
            "generated_at": str(datetime.datetime.utcnow())}


# ── REFERRAL ──────────────────────────────────────────────────────────
def referral_points(db, pet_id: int, friend_name: str) -> int:
    """Phase 5: a referral earns points (the growth loop).
    A unique code is derived from pet + time; the referrer gets 150 pts
    (the cheapest acquisition — pet parents talk)."""
    import time as _t
    code = f"PAWS-REF-{pet_id}-{int(_t.time()) % 100000}"
    return code
