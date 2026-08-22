"""
paws/backend/paws_api.py — PAWS
The rewards + pet-profile app: "Fetch for fur".
Users build a dog profile + scan receipts → earn points → redeem for
MANUFACTURER/retail-APPROVED digital discount coupons (Code 128 barcodes,
scannable at retail POS).

THE MONEY (the Fetch model, pet-specific):
  - brand shopper data (breed × age × food × spend) — sold to pet brands
  - pet-brand promotions ("scan a Blue Buffalo bag → 50 pts")
  - affiliate (Chewy/Amazon)
  - premium tier (unlimited profiles, health export)
Pet health data is NOT HIPAA-regulated — a full medical profile is legal.

Stack: FastAPI + SQLite (self-hosted, same pattern as Vault).
"""
import base64
import hashlib
import io
import json
import os
import sqlite3
import time
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.dirname(BASE), "state")
os.makedirs(STATE, exist_ok=True)
DB = os.path.join(STATE, "paws.db")

# ── the coupon catalog: manufacturer/retail-approved discounts ────────
# each coupon is a real-style offer; redemption happens at the retailer
# via the scannable Code 128 barcode (the retailer's POS recognizes it)
def _demo_catalog():
    """The REAL coupon catalog - GS1 DataBar formats only (cents-off /
    free / off-total). Percent offers cannot clear the standard coupon
    settlement process, so they are NOT offered. Demo prefixes until a
    brand partner signs (a real coupon needs the brand's GS1 prefix)."""
    from gs1_databar import demo_coupons as _dc
    out = []
    for i, c in enumerate(_dc()):
        out.append({"id": c["id"], "brand": c["brand"],
                    "category": c["category"], "title": c["title"],
                    "points": c["points"], "index": i,
                    "prefix": c["prefix"], "save": c["save"],
                    "save_code": c["save_code"], "req": c["req"],
                    "req_code": c["req_code"], "fc": c["fc"]})
    return out


def _catalog():
    return _demo_catalog()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, breed TEXT, mix TEXT, sex TEXT,
        neutered INTEGER, dob TEXT, weight REAL, activity TEXT,
        allergies TEXT, medications TEXT, vet TEXT, insurance TEXT,
        microchip TEXT, created_at TEXT DEFAULT '', photo TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS health_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, kind TEXT NOT NULL,  -- vaccine|vet|med|test
        name TEXT, date TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, store TEXT, date TEXT DEFAULT '',
        amount TEXT DEFAULT '0', total TEXT, raw_ocr TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL REFERENCES receipts(id),
        brand TEXT, product TEXT, category TEXT, amount REAL DEFAULT 0,
        points_earned INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS points_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, amount INTEGER, reason TEXT,
        created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, catalog_id TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL, barcode TEXT NOT NULL,
        title TEXT, brand TEXT, points_cost INTEGER, redeemed INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS weights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, weight REAL NOT NULL,
        date TEXT, created_at TEXT
    );
    """)
    return conn


app = FastAPI(title="PAWS", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── PET PROFILE ────────────────────────────────────────────────────────
class PetIn(BaseModel):
    name: str
    breed: str = ""
    mix: str = ""
    sex: str = ""
    neutered: bool = False
    dob: str = ""
    weight: float = 0
    activity: str = ""
    allergies: str = ""
    microchip: str = ""


@app.post("/api/v1/pets")
def add_pet(body: PetIn):
    db = _db()
    cur = db.execute(
        "INSERT INTO pets (name,breed,mix,sex,neutered,dob,weight,activity,"
        "allergies,microchip,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (body.name, body.breed, body.mix, body.sex, int(body.neutered),
         body.dob, body.weight, body.activity, body.allergies,
         body.microchip, time.strftime("%Y-%m-%d")))
    db.commit()
    # welcome points — the profile is the emotional core
    _points(db, cur.lastrowid, 100, "profile_complete")
    return {"id": cur.lastrowid}


@app.get("/api/v1/pets")
def pets():
    db = _db()
    rows = db.execute("SELECT * FROM pets").fetchall()
    return {"pets": [dict(r) for r in rows]}


@app.get("/api/v1/pets/{pid}")
def pet_detail(pid: int):
    db = _db()
    p = db.execute("SELECT * FROM pets WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "pet not found")
    events = db.execute(
        "SELECT * FROM health_events WHERE pet_id=? ORDER BY date",
        (pid,)).fetchall()
    pts = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM points_ledger WHERE pet_id=?",
        (pid,)).fetchone()["t"]
    # THE VACCINE CALENDAR - the sticky feature: auto-calculated next-due
    from vaccine_schedule import summarize
    cal = summarize([dict(r) for r in events])
    return {"pet": dict(p), "health": [dict(r) for r in events],
            "points": pts, "vaccine_calendar": cal}


# ── HEALTH EVENTS ───────────────────────────────────────────────────────
class EventIn(BaseModel):
    kind: str
    name: str
    date: str = ""
    notes: str = ""


@app.post("/api/v1/pets/{pid}/events")
def add_event(pid: int, body: EventIn):
    db = _db()
    db.execute("INSERT INTO health_events (pet_id,kind,name,date,notes) "
               "VALUES (?,?,?,?,?)",
               (pid, body.kind, body.name, body.date, body.notes))
    db.commit()
    # recording health data earns points (the data is the asset)
    pts = {"vaccine": 150, "vet": 100, "test": 60, "med": 60}.get(body.kind, 50)
    _points(db, pid, pts, f"health_{body.kind}")
    return {"ok": True, "points": pts}


# ── THE LEDGER: receipts + purchases ─────────────────────────────────────
class PurchaseIn(BaseModel):
    brand: str
    product: str
    category: str = "food"
    amount: float = 0


class ReceiptIn(BaseModel):
    pet_id: int
    store: str = ""
    amount: float = 0
    purchases: list = []
    raw_ocr: str = ""


@app.post("/api/v1/receipts")
def add_receipt(body: ReceiptIn):
    db = _db()
    cur = db.execute("INSERT INTO receipts (pet_id,store,amount,raw_ocr) "
                     "VALUES (?,?,?,?)",
                     (body.pet_id, body.store, body.amount, body.raw_ocr))
    rid = cur.lastrowid
    total_pts = 0
    for p in body.purchases:
        p = p if isinstance(p, dict) else p.model_dump()
        amt = float(p.get("amount") or 0)
        pts = int(amt) or 10  # ~1 pt per $1
        total_pts += pts
        db.execute("INSERT INTO purchases (receipt_id,brand,product,category,"
                   "amount,points_earned) VALUES (?,?,?,?,?,?)",
                   (rid, p.get("brand", ""), p.get("product", ""),
                    p.get("category", "food"), amt, pts))
    db.commit()
    _points(db, body.pet_id, total_pts, f"receipt_{rid}")
    return {"receipt_id": rid, "points": total_pts}


# ── POINTS ENGINE ────────────────────────────────────────────────────────────
def _points(db, pet_id: int, amount: int, reason: str):
    db.execute("INSERT INTO points_ledger (pet_id,amount,reason) VALUES (?,?,?)",
               (pet_id, amount, reason))
    db.commit()


@app.get("/api/v1/pets/{pid}/points")
def points(pid: int):
    db = _db()
    rows = db.execute("SELECT * FROM points_ledger WHERE pet_id=? "
                      "ORDER BY id DESC LIMIT 50", (pid,)).fetchall()
    bal = db.execute("SELECT COALESCE(SUM(amount),0) FROM points_ledger "
                      "WHERE pet_id=?", (pid,)).fetchone()[0]
    return {"balance": bal, "ledger": [dict(r) for r in rows]}


# ── THE COUPON MINT — points → manufacturer-approved scannable barcode ───
def _code128_png(data: str) -> bytes:
    import barcode
    from barcode.writer import ImageWriter
    c = barcode.get("code128", data, writer=ImageWriter())
    buf = io.BytesIO()
    c.write(buf, options={"module_width": 0.25, "module_height": 10,
                          "font_size": 8, "quiet_zone": 6.5})
    return buf.getvalue()


@app.get("/api/v1/coupons/catalog")
def coupon_catalog():
    return {"coupons": _catalog()}


@app.post("/api/v1/pets/{pid}/coupons/{catalog_id}")
def mint_coupon(pid: int, catalog_id: str):
    cat = next((c for c in _catalog() if c["id"] == catalog_id), None)
    if not cat:
        raise HTTPException(404, "unknown coupon")
    db = _db()
    bal = db.execute("SELECT COALESCE(SUM(amount),0) FROM points_ledger "
                      "WHERE pet_id=?", (pid,)).fetchone()[0]
    cost = cat.get("points", 0)
    if bal < cost:
        raise HTTPException(400, f"need {cost} points, have {bal}")
    # burn the points
    _points(db, pid, -cost, f"redeem_{cat['id']}")
    # THE GS1 PAYLOAD - a REAL retailer-POS coupon (AI 8110 DataBar),
    # serialized (AI 21) so each mint is unique + single-use
    from gs1_databar import build_databar
    offer_code = f"{cat['index']+1:06d}"
    # serialization stays SERVER-SIDE (single-use tracking); the DataBar
    # carries the core GS1 coupon fields (the spec's serial field has a
    # separate encoding BWIPP's coupon parser doesn't accept inline)
    payload = build_databar(cat["prefix"], offer_code, cat["save"],
                            cat["save_code"], cat["req"], cat["req_code"],
                            cat["fc"])
    code = f"{catalog_id}-{pid}-{int(time.time())}"
    db.execute(
        "INSERT INTO coupons (pet_id,catalog_id,code,barcode,title,"
        "brand,points_cost,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (pid, cat["id"], code, payload, cat["title"], cat["brand"],
         cost, time.strftime("%Y-%m-%d")))
    db.commit()
    return {"code": code, "title": cat["title"], "brand": cat["brand"],
            "gs1_databar": payload}


@app.get("/api/v1/coupons/{code}/barcode.png")
def coupon_barcode(code: str):
    """The scannable coupon — Code 128 PNG the retailer POS reads."""
    db = _db()
    c = db.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
    if not c:
        raise HTTPException(404, "coupon not found")
    from gs1_databar import render_databar_png
    payload = c["barcode"]
    png = render_databar_png(payload)
    return Response(content=png, media_type="image/png",
                    headers={"X-Coupon": c["title"], "X-Brand": code,
                             "X-GS1-DataBar": payload})


@app.get("/api/v1/pets/{pid}/coupons")
def my_coupons(pid: int):
    db = _db()
    rows = db.execute("SELECT * FROM coupons WHERE pet_id=? "
                      "ORDER BY created_at DESC", (pid,)).fetchall()
    return {"coupons": [dict(r) for r in rows]}


class OcrIn(BaseModel):
    image_b64: str


@app.post("/api/v1/ocr-receipt")
async def ocr_receipt(body: OcrIn):
    """OCR a receipt photo with the institution's local vision model
    (LFM2.5-VL via the vision_world lane — queue-aware, no cloud).
    Returns raw text; the client parses it into purchases."""
    try:
        import base64 as _b64, sys as _sys
        _sys.path.insert(0, "/home/zixen15/are")
        from vision_world import ask_vision
        import tempfile
        img = _b64.b64decode(body.image_b64)
        tmp = os.path.join(tempfile.gettempdir(), f"paws_{int(time.time())}.png")
        with open(tmp, "wb") as f:
            f.write(img)
        text = ask_vision(
            tmp,
            "You are a receipt reader. Extract from this pet-supply receipt: "
            "store name, date, and every line item with brand/product and "
            "price. Return STRICT JSON: "
            '{"store": "...", "date": "...", "items": [{"brand": "...", '
            '"product": "...", "amount": 12.34}]}. Only the JSON, nothing else.')
        os.remove(tmp)
        return {"text": text}
    except Exception as e:
        return {"text": "", "error": str(e)[:100]}


class ParseIn(BaseModel):
    ocr_text: str


@app.post("/api/v1/parse-ocr")
def parse_ocr(body: ParseIn):
    """Turn raw OCR output into structured line items (with the local 27B
    when available, else a mechanical fallback). The app shows these for
    confirmation — nothing is auto-posted."""
    import re as _re
    text = body.ocr_text
    items = []
    store = ""
    # try JSON first (the vision model was asked for strict JSON)
    m = _re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            d = json.loads(m.group(0))
            store = d.get("store", "")
            for it in d.get("items", [])[:20]:
                amt = it.get("amount", it.get("price", 0)) or 0
                items.append({"brand": str(it.get("brand", "")),
                              "product": str(it.get("product", "")),
                              "price": float(amt)})
        except Exception:
            items = []
    # mechanical fallback: ITEM | PRICE lines
    if not items:
        for line in text.splitlines():
            mm = _re.match(r"([A-Za-z][^|]*?)\s*\|\s*([\d.]+)", line)
            if mm:
                items.append({"brand": "", "product": mm.group(1).strip(),
                              "price": float(mm.group(2))})
    # price fallback: when the vision JSON omits amounts, pull the first
    # decimal after each product from the RAW text (mechanical, honest)
    flat = _re.sub(r"\s+", " ", text)
    for it in items:
        if not it.get("price"):
            prod = _re.escape(it["product"][:14])
            pm = _re.search(prod + r"[^\d]{0,20}(\d+\.\d{2})", flat)
            if pm:
                try:
                    it["price"] = float(pm.group(1))
                except Exception:
                    pass
    return {"store": store, "items": items}


class EmailIn(BaseModel):
    pet_id: int
    email_text: str


@app.post("/api/v1/receipts/email")
def import_email(body: EmailIn):
    """Phase 3: pasted Chewy/Amazon order confirmation -> purchases."""
    from phase3 import parse_email_text
    parsed = parse_email_text(body.email_text)
    items = parsed["items"]
    if not items:
        return {"ok": False, "reason": "no line items found in the email",
                "items": []}
    db = _db()
    total = round(sum(i["price"] for i in items), 2)
    cur = db.execute("INSERT INTO receipts (pet_id,store,amount,raw_ocr) "
                     "VALUES (?,?,?,?)",
                     (body.pet_id, parsed["store"], str(total),
                      body.email_text[:2000]))
    rid = cur.lastrowid
    pts = 0
    for i in items:
        p = int(i["price"]) or 5
        pts += p
        db.execute("INSERT INTO purchases (receipt_id,brand,product,category,"
                   "amount,points_earned) VALUES (?,?,?,?,?,?)",
                   (rid, i["brand"], i["product"], "food", i["price"], p))
    db.commit()
    _points(db, body.pet_id, pts, f"email_receipt_{rid}")
    return {"store": parsed["store"], "items": items, "total": total,
            "points": pts, "receipt_id": rid}


@app.get("/api/v1/pets/{pid}/spend")
def brand_spend(pid: int):
    """Phase 3 - the BRAND-SPEND VIEW: the data panel's output."""
    from phase3 import BRAND_SPEND_SQL
    db = _db()
    pet = db.execute("SELECT * FROM pets WHERE id=?", (pid,)).fetchone()
    if not pet:
        raise HTTPException(404, "pet not found")
    rows = db.execute(BRAND_SPEND_SQL, (pid,)).fetchall()
    all_spend = db.execute("""
        SELECT ROUND(SUM(p.amount),2) AS t FROM purchases p
        JOIN receipts r ON p.receipt_id = r.id WHERE r.pet_id=?""",
        (pid,)).fetchone()["t"] or 0
    from phase3 import normalize_brand
    merged = {}
    for r in rows:
        canon = normalize_brand(r["brand"])
        if canon not in merged:
            merged[canon] = {"brand": canon, "items": 0, "total": 0.0}
        merged[canon]["items"] += r["items"]
        merged[canon]["total"] = round(merged[canon]["total"] + r["total"], 2)
    brands = sorted(merged.values(), key=lambda b: b["total"], reverse=True)
    return {"pet": pet["name"], "breed": pet["breed"],
            "total_spend": all_spend, "brands": brands}


class WeightIn(BaseModel):
    weight: float
    date: str = ""


@app.post("/api/v1/pets/{pid}/weight")
def add_weight(pid: int, body: WeightIn):
    """Phase 4 - log a weight (the vet-loved health metric)."""
    from phase4 import log_weight
    db = _db()
    if not db.execute("SELECT 1 FROM pets WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "pet not found")
    log_weight(db, pid, body.weight, body.date)
    _points(db, pid, 50, f"weight_{pid}")
    return {"ok": True, "points": 50}


@app.get("/api/v1/pets/{pid}/weight")
def weight_curve(pid: int):
    """Phase 4 - the weight history with deltas."""
    from phase4 import weight_curve as _wc
    db = _db()
    return {"pet_id": pid, "curve": _wc(db, pid)}


@app.get("/api/v1/household")
def household():
    """Phase 4 - all pets, one view (the family dashboard)."""
    from phase4 import household_summary
    db = _db()
    return household_summary(db)


@app.get("/api/v1/pets/{pid}/digest")
def pet_digest(pid: int):
    """Phase 4 - the pet digest: spend, top brand, coupons, weight."""
    from phase4 import digest
    db = _db()
    d = digest(db, pid)
    if not d.get("ok"):
        raise HTTPException(404, "pet not found")
    return d


@app.post("/api/v1/coupons/{code}/redeem")
def redeem_coupon(code: str):
    """Phase 4 - mark a minted coupon redeemed (single-use closure)."""
    db = _db()
    cur = db.execute("UPDATE coupons SET redeemed=1 WHERE code=? AND redeemed=0",
                     (code,))
    db.commit()
    if cur.rowcount == 0:
        c = db.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        if not c:
            raise HTTPException(404, "coupon not found")
        raise HTTPException(400, "coupon already redeemed")
    return {"ok": True, "code": code}


@app.get("/api/v1/health")
def health():
    return {"ok": True, "app": "paws", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PAWS_PORT", "8235"))
    host = os.environ.get("PAWS_BIND", "100.113.24.19")
    uvicorn.run(app, host=host, port=port)
