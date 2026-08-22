"""
paws/backend/phase3.py — Phase 3 endpoints: email import + brand spend.
Imported by paws_api.py (kept separate to avoid the quoting minefield of
inline regexes in the main file).
"""
import re

# ── BRAND NORMALIZATION - the data-quality core of the panel ──
BRAND_ALIASES = {
    "royal canin": "Royal Canin",
    "hills science diet": "Hill's Science Diet",
    "science diet": "Hill's Science Diet",
    "hills": "Hill's Science Diet",
    "greenies": "Greenies",
    "blue buffalo": "Blue Buffalo",
    "blue": "Blue Buffalo",
    "purina pro plan": "Purina Pro Plan",
    "purina": "Purina",
    "barkbox": "BarkBox",
    "chuckit": "Chuckit!",
    "farmer's dog": "The Farmer's Dog",
    "farmers dog": "The Farmer's Dog",
    "zesty paws": "Zesty Paws",
    "petco": "Petco",
    "petsmart": "PetSmart",
    "kong": "KONG",
    "pedigree": "Pedigree",
    "beneful": "Beneful",
    "friskies": "Friskies",
}


def normalize_brand(raw: str) -> str:
    """Canonicalize a messy brand string (case-insensitive)."""
    if not raw:
        return ""
    key = raw.strip().lower()
    for alias, canon in BRAND_ALIASES.items():
        if alias in key:
            return canon
    return raw.strip()


# ── EMAIL IMPORT ─────────────────────────────────────────────────────
def parse_email_text(text: str) -> dict:
    """Parse a pasted Chewy/Amazon order confirmation: line items.
    No OAuth — the user pastes the email; we extract mechanically."""
    items = []
    store = "Chewy" if "chewy" in text.lower() else (
        "Amazon" if "amazon" in text.lower() else "")
    # pattern 1: "Product Name ... $12.34" (brand-ish lines)
    pat = re.compile(
        r"([A-Za-z][A-Za-z0-9 &'/-]{3,60}?)[\s\n]+\$?([\d]+\.[\d]{2})")
    for m in pat.finditer(text):
        prod = m.group(1).strip()
        low = prod.lower()
        if any(k in low for k in (
                "order", "total", "subtotal", "shipping", "tax", "chewy",
                "amazon", "payment", "saved", "discount", "promo", "billing",
                "customer", "confirmation", "delivery", "address", "items",
                "quantity", "price", "email", "submitted", "view", "track")):
            continue
        items.append({"brand": "", "product": prod[:60],
                      "price": float(m.group(2).replace(",", ""))})
        if len(items) >= 12:
            break
    # pattern 2: "Item  description .... $12.34" (column spacing)
    if not items:
        for line in text.splitlines():
            mm = re.match(r"(.{4,60}?)\s{2,}\$?([\d,]+\.\d{2})", line)
            if mm and not any(k in line.lower() for k in
                              ("order", "total", "tax", "shipping")):
                items.append({"brand": "", "product": mm.group(1).strip(),
                              "price": float(mm.group(2).replace(",", ""))})
    # pattern 3: numbered line items like "1. Blue Buffalo ...\n   Qty: 1  Price: $62.99"
    if not items:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            mm = re.match(r"\d+\.\s+(.+)($|\s+Qty)", lines[i])
            if mm:
                prod = mm.group(1).strip()
                # look ahead up to 3 lines for a Price: $xx.xx
                price = None
                for j in range(i + 1, min(i + 4, len(lines))):
                    pm = re.search(r"Price:\s*\$?([\d,]+\.\d{2})", lines[j])
                    if pm:
                        price = float(pm.group(1).replace(",", ""))
                        break
                    if re.search(r"(Subtotal|Total|Shipping|Tax):", lines[j]):
                        break
                if price is not None and not any(
                        k in prod.lower() for k in
                        ("order", "subtotal", "total", "shipping", "tax")):
                    first = prod.split()[0] if prod.split() else ""
                    items.append({"brand": normalize_brand(first),
                                  "product": prod[:60], "price": price})
            i += 1
    return {"store": store, "items": items}


# ── BRAND SPEND ───────────────────────────────────────────────────────
BRAND_SPEND_SQL = """
    SELECT p.brand AS brand, COUNT(*) AS items,
           ROUND(SUM(p.amount),2) AS total
    FROM purchases p JOIN receipts r ON p.receipt_id = r.id
    WHERE r.pet_id=? AND p.brand != '' AND p.brand != 'null'
    GROUP BY p.brand ORDER BY total DESC"""
