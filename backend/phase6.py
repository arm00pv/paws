"""
paws/backend/phase6.py — Phase 6: barcode capture + local UPC knowledge base.
- SCAN: a UPC/EAN barcode → look up the product.
- The lookup checks OUR OWN cache first (every scan enriches it — the
  panel becomes the knowledge base: brand x UPC x product, self-learning),
  then Open Food Facts (free, no key, but no pet-food coverage), then an
  honest "unknown — tell us what it is" path where the user teaches the
  cache. That user-entered record becomes panel knowledge.

This is the moat in miniature: 1,000 scans = a proprietary UPC -> brand
catalog nobody else has, built for free by the users themselves.
"""
import datetime
import json
import sqlite3
import urllib.request

OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"


def ensure_table(db):
    db.execute("""
    CREATE TABLE IF NOT EXISTS upcatalog (
        upc TEXT PRIMARY KEY,
        brand TEXT,
        product TEXT,
        category TEXT DEFAULT 'food',
        source TEXT DEFAULT 'user',   -- user | openfoodfacts | panel
        first_seen TEXT,
        last_seen TEXT,
        scan_count INTEGER DEFAULT 1
    )""")


def lookup(db, upc: str) -> dict:
    """Resolve a UPC: local cache -> Open Food Facts -> honest unknown."""
    ensure_table(db)
    upc = (upc or "").strip()
    if not upc:
        return {"ok": False, "reason": "no barcode"}

    # 1. THE LOCAL KNOWLEDGE BASE (the panel's own memory)
    row = db.execute("SELECT * FROM upcatalog WHERE upc=?", (upc,)).fetchone()
    if row:
        db.execute("UPDATE upcatalog SET scan_count=scan_count+1, "
                   "last_seen=? WHERE upc=?",
                   (str(datetime.date.today()), upc))
        db.commit()
        return {"ok": True, "upc": upc, "brand": row["brand"],
                "product": row["product"], "category": row["category"],
                "source": row["source"], "scan_count": row["scan_count"]}

    # 2. OPEN FOOD FACTS (free, no key; weak on pet food but honest)
    try:
        with urllib.request.urlopen(OFF_API.format(upc), timeout=10) as r:
            d = json.loads(r.read().decode())
        if d.get("status") == 1:
            p = d.get("product", {})
            brand = (p.get("brands") or "").split(",")[0].strip()
            name = (p.get("product_name") or "").strip()
            if name:
                db.execute(
                    "INSERT OR REPLACE INTO upcatalog "
                    "(upc,brand,product,source,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?)",
                    (upc, brand, name, "openfood",
                     str(datetime.date.today()), str(datetime.date.today())))
                db.commit()
                return {"ok": True, "upc": upc, "brand": brand,
                        "product": name, "category": "food",
                        "source": "openfood"}
    except Exception:
        pass

    # 3. honest unknown — the user teaches us (and the panel learns)
    return {"ok": False, "upc": upc, "source": "unknown",
            "message": "New barcode — tell us what this is and every "
                       "future scan recognizes it (that's the panel's "
                       "superpower)"}


def teach(db, upc: str, brand: str, product: str, category: str = "food"):
    """The user's first scan teaches the panel; it never forgets."""
    ensure_table(db)
    db.execute(
        "INSERT OR REPLACE INTO upcatalog "
        "(upc,brand,product,category,source,first_seen,last_seen,scan_count) "
        "VALUES (?,?,?,?,?,?,?,1)",
        (upc, brand, product, category, "user",
         str(datetime.date.today()), str(datetime.date.today())))
    db.commit()
    return {"ok": True, "upc": upc, "brand": brand, "product": product,
            "source": "user", "learned": True}


def cache_size(db):
    try:
        return db.execute("SELECT COUNT(*) AS c FROM upcatalog").fetchone()["c"]
    except Exception:
        return 0
