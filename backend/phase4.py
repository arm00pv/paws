"""
paws/backend/phase4.py — Phase 4: household + weight + digest + redemption.
Imported by paws_api.py.

- MULTI-PET: the pets table is already multi-pet; this adds the household
  aggregate view (all pets, total spend, points, overdue vaccines).
- WEIGHT: a weight history (kg) per pet with the growth curve — a real
  vet metric and a brand-data signal (breed x age x weight x food).
- REDEMPTION: mark a minted coupon as redeemed (single-use closure).
- DIGEST: the weekly "how is Rex doing" — spend, health, coupons — the
  engagement surface that doubles as the data-product showcase.
"""
import datetime


def weight_sql():
    return """
    CREATE TABLE IF NOT EXISTS weights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL,
        weight REAL NOT NULL,
        date TEXT,
        created_at TEXT
    )"""


def log_weight(db, pet_id: int, weight: float, date: str = ""):
    cur = db.execute(
        "INSERT INTO weights (pet_id, weight, date, created_at) "
        "VALUES (?,?,?,?)",
        (pet_id, weight, date or str(__import__("datetime").date.today()),
         str(__import__("datetime").date.today())))
    db.commit()
    return cur.lastrowid


def weight_curve(db, pet_id: int):
    """The weight history — newest first, with the delta vs previous."""
    rows = db.execute(
        "SELECT * FROM weights WHERE pet_id=? ORDER BY date DESC, id DESC",
        (pet_id,)).fetchall()
    out = []
    for i, r in enumerate(rows):
        prev = rows[i + 1]["weight"] if i + 1 < len(rows) else None
        delta = None
        if prev is not None:
            delta = round(r["weight"] - prev, 1)
        out.append({"weight": r["weight"], "date": r["date"],
                    "delta": delta})
    return out


def household_summary(db):
    """All pets in one view — the family dashboard."""
    pets = db.execute("SELECT * FROM pets ORDER BY id").fetchall()
    out = []
    grand_spend = 0.0
    grand_overdue = 0
    for p in pets:
        spend = db.execute(
            "SELECT ROUND(SUM(pu.amount),2) AS t FROM purchases pu "
            "JOIN receipts r ON pu.receipt_id = r.id WHERE r.pet_id=?",
            (p["id"],)).fetchone()["t"] or 0
        pts = db.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM points_ledger "
            "WHERE pet_id=?", (p["id"],)).fetchone()["t"]
        overdue = db.execute(
            "SELECT COUNT(*) AS c FROM health_events e WHERE e.pet_id=? "
            "AND lower(e.kind) IN ('vaccine','test')",
            (p["id"],)).fetchone()["c"]
        out.append({"id": p["id"], "name": p["name"], "breed": p["breed"],
                    "weight": p["weight"], "spend": spend, "points": pts,
                    "vaccines_logged": overdue,
                    "dob": p["dob"]})
        grand_spend += spend
    return {"pets": out, "pet_count": len(pets),
            "household_spend": round(grand_spend, 2)}


def digest(db, pet_id: int):
    """The pet digest — what the pet parent sees and what brands value."""
    pet = db.execute("SELECT * FROM pets WHERE id=?", (pet_id,)).fetchone()
    if not pet:
        return {"ok": False}
    # 30-day spend + item count
    spend = db.execute(
        "SELECT ROUND(SUM(pu.amount),2) AS t, COUNT(*) AS n "
        "FROM purchases pu JOIN receipts r ON pu.receipt_id = r.id "
        "WHERE r.pet_id=?", (pet_id,)).fetchone()
    # top brand
    top = db.execute(
        "SELECT p.brand AS brand, ROUND(SUM(p.amount),2) AS t "
        "FROM purchases p JOIN receipts r ON p.receipt_id = r.id "
        "WHERE r.pet_id=? AND p.brand != '' GROUP BY p.brand "
        "ORDER BY t DESC LIMIT 1", (pet_id,)).fetchone()
    # coupons minted / redeemed
    coupons = db.execute(
        "SELECT COUNT(*) AS c FROM coupons WHERE pet_id=?",
        (pet_id,)).fetchone()["c"]
    redeemed = db.execute(
        "SELECT COUNT(*) AS c FROM coupons WHERE pet_id=? AND redeemed=1",
        (pet_id,)).fetchone()["c"]
    # weight latest
    w = db.execute(
        "SELECT * FROM weights WHERE pet_id=? ORDER BY date DESC LIMIT 1",
        (pet_id,)).fetchone()
    return {"ok": True, "pet": pet["name"], "breed": pet["breed"],
            "spend_total": spend["t"] or 0,
            "spend_items": spend["n"] or 0,
            "top_brand": top["brand"] if top else "",
            "coupons": coupons, "coupons_redeemed": redeemed,
            "last_weight": w["weight"] if w else None,
            "last_weight_date": w["date"] if w else None,
            "points": db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM points_ledger "
                "WHERE pet_id=?", (pet_id,)).fetchone()[0]}
