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
# ── RECEIPT VALIDATION — the user's point: not ANYTHING can be a receipt ──
# The vision model must confirm store + date + line items before a scan
# counts. A random photo (dog, wall, person) is rejected.
RECEIPT_HINTS = ("store", "receipt", "total", "subtotal", "tax", "thank you",
                 "qty", "item", "price", "cashier", "register", "order",
                 "checkout", "purchase", "sold", "amount", "payment")


def validate_receipt_text(text: str) -> dict:
    """Heuristic receipt check: does the OCR text look like a receipt?
    Returns {ok, reason}. The vision model's JSON (store/date/items) is
    the primary signal; the raw text is the fallback."""
    low = text.lower()
    hits = sum(1 for h in RECEIPT_HINTS if h in low)
    has_store = any(k in low for k in ("store", "petsmart", "chewy", "petco",
                                       "amazon", "walmart", "target", "costco",
                                       "pet supplies", "pets first"))
    has_money = "$" in text or "total" in low or "subtotal" in low
    if has_store and (has_money or hits >= 2):
        return {"ok": True, "reason": "receipt-like (store + money)"}
    if hits >= 3 and has_money:
        return {"ok": True, "reason": "receipt-like (items + money)"}
    return {"ok": False,
            "reason": "does not look like a receipt (no store/items/money) — "
                      "only pet-supply receipts earn points"}


# ── UPC PET-PRODUCT CHECK — the user's point: a UPC must be a pet product ──
# The panel's own catalog + a pet-brand whitelist gate what counts.
PET_BRANDS = ("royal canin", "purina", "hill", "blue buffalo", "greenies",
              "pedigree", "friskies", "beneful", "kong", "chuckit", "barkbox",
              "zesty paws", "farmer", "ollie", "vetmedin", "petco", "petsmart",
              "chewy", "whiskas", "fancy feast", "temptations", "meow mix",
              "iams", "eukanuba", "nutro", "taste of the wild", "orijen",
              "acana", "wellness", "nulo", "stella", "chewy")


def is_pet_product(brand: str, product: str) -> bool:
    """Is this a pet product? The brand whitelist + product hints."""
    b = (brand or "").lower()
    p = (product or "").lower()
    if any(k in b for k in PET_BRANDS):
        return True
    if any(k in p for k in ("dog", "cat", "puppy", "kitten", "pet", "kibble",
                            "treat", "litter", "chew", "toy", "collar",
                            "leash", "bowl", "food", "dental")):
        return True
    return False


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
