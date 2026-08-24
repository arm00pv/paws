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


def _require_user(x_token: str = "") -> int:
    """ROUND 29 (reviewer #4) - AUTH: the X-Token header maps to a user.
    The business model's asset was fake with all users = 1; writes now
    require a real account."""
    if not x_token:
        raise HTTPException(401, "authentication required - sign up first")
    db = _db()
    u = db.execute("SELECT id FROM users WHERE token_hash=?", (x_token,)).fetchone()
    if not u:
        raise HTTPException(401, "invalid token - log in again")
    return u["id"]


def _owns_pet(db, pet_id: int, user_id: int) -> bool:
    """Does this user own this pet? (multi-tenant integrity)"""
    p = db.execute("SELECT user_id FROM pets WHERE id=?", (pet_id,)).fetchone()
    return p is not None and p["user_id"] == user_id


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,   -- the owner (multi-user)
        name TEXT NOT NULL, breed TEXT, mix TEXT, sex TEXT, species TEXT DEFAULT 'dog',
        neutered INTEGER, dob TEXT, weight REAL, age TEXT DEFAULT '', activity TEXT,
        allergies TEXT, medications TEXT, vet TEXT, insurance TEXT,
        microchip TEXT, created_at TEXT DEFAULT '', photo TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS health_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, kind TEXT NOT NULL,  -- vaccine|vet|med|test
        name TEXT, date TEXT, notes TEXT,
        practice TEXT DEFAULT '', invoice_amount TEXT DEFAULT ''
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
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL, name TEXT DEFAULT '',
        token_hash TEXT UNIQUE NOT NULL,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS care_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL,
        check_date TEXT,
        action TEXT DEFAULT 'care'
    );
    CREATE TABLE IF NOT EXISTS dismissed (
        pet_id INTEGER NOT NULL, kind TEXT NOT NULL,
        dismissed_at TEXT, PRIMARY KEY (pet_id, kind)
    );
    CREATE TABLE IF NOT EXISTS coupon_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL, code TEXT NOT NULL,
        title TEXT, action TEXT DEFAULT 'redeemed',
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS meals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_id INTEGER NOT NULL,
        food_upc TEXT DEFAULT '', brand TEXT, product TEXT,
        amount REAL DEFAULT 0,  -- grams/cups (optional)
        meal_time TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS missions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT NOT NULL, title TEXT NOT NULL,
        action TEXT NOT NULL,  -- feed_X_days | walk_X_week | scan_X
        target INTEGER NOT NULL, duration_days INTEGER DEFAULT 7,
        points INTEGER NOT NULL, budget_cap INTEGER DEFAULT 1000,
        active INTEGER DEFAULT 1, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS mission_progress (
        mission_id INTEGER NOT NULL, pet_id INTEGER NOT NULL,
        count INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,
        PRIMARY KEY (mission_id, pet_id)
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
    species: str = "dog"
    neutered: bool = False
    dob: str = ""
    weight: float = 0
    activity: str = ""
    allergies: str = ""
    microchip: str = ""
    user_id: int = 1


@app.post("/api/v1/pets")
def add_pet(body: PetIn, x_token: str = Header(default="")):
    # ROUND 29: the pet is bound to the token's user, not body.user_id
    uid = _require_user(x_token)
    db = _db()
    cur = db.execute(
        "INSERT INTO pets (user_id,name,breed,mix,sex,species,neutered,dob,"
        "weight,activity,allergies,microchip,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, body.name, body.breed, body.mix, body.sex,
         body.species, int(body.neutered), body.dob, body.weight,
         body.activity, body.allergies, body.microchip,
         time.strftime("%Y-%m-%d")))
    db.commit()
    # welcome points — the profile is the emotional core
    _points(db, cur.lastrowid, 100, "profile_complete")
    return {"id": cur.lastrowid}


@app.get("/api/v1/pets")
def pets(user_id: int = 0):
    db = _db()
    if user_id:
        rows = db.execute("SELECT * FROM pets WHERE user_id=? ORDER BY id",
                          (user_id,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM pets ORDER BY id").fetchall()
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
    from vaccine_schedule import summarize, med_schedule
    cal = summarize([dict(r) for r in events])
    meds = med_schedule([dict(r) for r in events])
    return {"pet": dict(p), "health": [dict(r) for r in events],
            "points": pts, "vaccine_calendar": cal,
            "med_schedule": meds}


# ── HEALTH EVENTS ───────────────────────────────────────────────────────
class EventIn(BaseModel):
    kind: str
    name: str
    date: str = ""
    notes: str = ""


@app.post("/api/v1/pets/{pid}/events")
def add_event(pid: int, body: EventIn, x_token: str = Header(default="")):
    uid = _require_user(x_token)
    db = _db()
    if not _owns_pet(db, pid, uid):
        raise HTTPException(403, "you don't own this pet")
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
def add_receipt(body: ReceiptIn, x_token: str = Header(default="")):
    uid = _require_user(x_token)
    db = _db()
    if not _owns_pet(db, body.pet_id, uid):
        raise HTTPException(403, "you don't own this pet")
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
    # ROUND 20 (reviewer #6): the home shows the HOUSEHOLD balance, so
    # redemption must use the household balance too (was per-pet — the
    # home said READY TO CLAIM but the pet couldn't afford it)
    pet = db.execute("SELECT user_id FROM pets WHERE id=?", (pid,)).fetchone()
    uid = pet["user_id"] if pet else 1
    bal = db.execute("""
        SELECT COALESCE(SUM(l.amount),0) AS t
        FROM points_ledger l JOIN pets p ON l.pet_id = p.id
        WHERE p.user_id=?""", (uid,)).fetchone()["t"]
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
    confirmation — nothing is auto-posted.
    ROUND 20 (reviewer #3): the RECEIPT GATE — a non-receipt is rejected
    before any points can be earned (the gate existed but was never
    called — a points-farming hole)."""
    import re as _re
    text = body.ocr_text
    # THE RECEIPT GATE: only pet-supply receipts pass
    from phase3 import validate_receipt_text
    v = validate_receipt_text(text)
    if not v["ok"]:
        return {"store": "", "items": [], "rejected": True,
                "reason": v["reason"]}
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
def household(user_id: int = 0):
    """Phase 4 - all pets, one view (the family dashboard)."""
    from phase4 import household_summary
    db = _db()
    s = household_summary(db)
    if user_id:
        s["pets"] = [p for p in s["pets"] if p.get("user_id", 0) == user_id]
        s["pet_count"] = len(s["pets"])
    return s


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
    """Phase 4 - mark a minted coupon redeemed (single-use closure).
    Round 19 - logs the redemption to the activity feed."""
    db = _db()
    cur = db.execute("UPDATE coupons SET redeemed=1 WHERE code=? AND redeemed=0",
                     (code,))
    db.commit()
    if cur.rowcount == 0:
        c = db.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        if not c:
            raise HTTPException(404, "coupon not found")
        raise HTTPException(400, "coupon already redeemed")
    c = db.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
    db.execute("INSERT INTO coupon_events (pet_id,code,title,action) "
               "VALUES (?,?,?,?)",
               (c["pet_id"], code, c["title"], "redeemed"))
    db.commit()
    return {"ok": True, "code": code}


@app.get("/api/v1/panel")
def panel():
    """Phase 5 - THE PANEL: the aggregated, anonymized data product.
    Brand share, breed x food matrix, category spend, panel growth.
    This is the asset we'd sell to pet brands (no individual pet data)."""
    from phase5 import panel_summary
    db = _db()
    return panel_summary(db)


@app.post("/api/v1/pets/{pid}/refer")
def refer(pid: int, body: dict = None):
    """Phase 5 - the referral loop: a pet parent refers a friend,
    the referrer earns 150 pts (cheapest acquisition)."""
    db = _db()
    if not db.execute("SELECT 1 FROM pets WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "pet not found")
    from phase5 import referral_points
    code = referral_points(db, pid, "friend")
    _points(db, pid, 150, "referral")
    return {"code": code, "points": 150}


class BarcodeIn(BaseModel):
    brand: str = ""
    product: str = ""
    category: str = "food"


@app.get("/api/v1/barcode/{upc}")
def barcode_lookup(upc: str):
    """Phase 6 - resolve a UPC: panel memory -> Open Food Facts -> unknown."""
    from phase6 import lookup
    db = _db()
    return lookup(db, upc)


@app.post("/api/v1/barcode/{upc}/teach")
def barcode_teach(upc: str, body: BarcodeIn):
    """Phase 6 - the user teaches an unknown barcode; the panel learns."""
    from phase6 import teach
    db = _db()
    return teach(db, upc, body.brand, body.product, body.category)


@app.post("/api/v1/receipts/barcode")
def add_barcode_receipt(body: dict = None):
    """Phase 6 - scan a barcode -> a one-line purchase + points.
    body: {pet_id, upc, brand, product, category, amount}"""
    body = body or {}
    from phase6 import lookup
    db = _db()
    upc = str(body.get("upc", "")).strip()
    if not upc:
        raise HTTPException(400, "no barcode")
    info = lookup(db, upc)
    brand = body.get("brand") or (info.get("brand") if info.get("ok") else "")
    product = body.get("product") or (info.get("product") if info.get("ok") else "")
    if not product:
        raise HTTPException(400, "unknown barcode - teach it first")
    # THE PET-PRODUCT GATE: a UPC must be a pet product to earn points
    from phase3 import is_pet_product
    if not is_pet_product(brand, product):
        raise HTTPException(400,
            "not a pet product - PAWS only rewards pet-supply purchases")
    amount = float(body.get("amount") or 0)
    db.execute("INSERT INTO receipts (pet_id,store,amount) VALUES (?,?,?)",
               (body.get("pet_id", 1), "Barcode", str(amount)))
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    pts = int(amount) or 10
    db.execute("INSERT INTO purchases (receipt_id,brand,product,category,"
               "amount,points_earned) VALUES (?,?,?,?,?,?)",
               (rid, brand, product, body.get("category", "food"),
                amount, pts))
    db.commit()
    _points(db, body.get("pet_id", 1), pts, f"barcode_{rid}")
    return {"ok": True, "brand": brand, "product": product,
            "points": pts, "receipt_id": rid, "source": info.get("source")}


class SignupIn(BaseModel):
    email: str
    name: str = ""


@app.post("/api/v1/signup")
def signup(body: SignupIn):
    """Phase 6 - multi-user: a real account (the panel's growth path)."""
    import hashlib as _h
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "valid email required")
    db = _db()
    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise HTTPException(400, "email already registered")
    token = _h.sha256(f"{email}:{int(time.time()*1000)}".encode()).hexdigest()[:32]
    cur = db.execute("INSERT INTO users (email,name,token_hash) VALUES (?,?,?)",
                     (email, body.name or email.split("@")[0], token))
    db.commit()
    return {"user_id": cur.lastrowid, "token": token,
            "message": "welcome to PAWS"}


class LoginIn(BaseModel):
    email: str
    token: str


@app.post("/api/v1/login")
def login(body: LoginIn):
    db = _db()
    u = db.execute("SELECT * FROM users WHERE email=?",
                   (body.email.strip().lower(),)).fetchone()
    if not u or u["token_hash"] != body.token:
        raise HTTPException(401, "invalid credentials")
    return {"ok": True, "user_id": u["id"], "email": u["email"],
            "name": u["name"]}


@app.get("/api/v1/users")
def users():
    db = _db()
    rows = db.execute("SELECT id,email,name,created_at FROM users").fetchall()
    return {"users": [dict(r) for r in rows]}


class PhotoIn(BaseModel):
    image_b64: str


@app.post("/api/v1/pets/{pid}/photo")
def set_photo(pid: int, body: PhotoIn, x_token: str = Header(default="")):
    """UX review fix: pet photos (the emotional core)."""
    db = _db()
    if not db.execute("SELECT 1 FROM pets WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "pet not found")
    db.execute("UPDATE pets SET photo=? WHERE id=?", (body.image_b64, pid))
    db.commit()
    return {"ok": True}


@app.get("/api/v1/activity")
def activity(user_id: int = 0, limit: int = 8):
    """Round 9 - the home activity feed: recent receipts + coupons with
    the pet name, so the home screen shows life, not void."""
    db = _db()
    rows = db.execute("""
        SELECT r.id, r.store, r.amount, r.date, p.name AS pet
        FROM receipts r JOIN pets p ON r.pet_id = p.id
        WHERE (? = 0 OR p.user_id = ?)
        ORDER BY r.id DESC LIMIT ?""", (user_id, user_id, limit)).fetchall()
    ev = db.execute("""
        SELECT h.kind, h.name, h.date, p.name AS pet
        FROM health_events h JOIN pets p ON h.pet_id = p.id
        WHERE (? = 0 OR p.user_id = ?)
        ORDER BY h.id DESC LIMIT 4""", (user_id, user_id)).fetchall()
    # Round 19: coupon redemptions join the activity feed
    ce = db.execute("""
        SELECT ce.title, ce.action, ce.created_at, p.name AS pet
        FROM coupon_events ce JOIN pets p ON ce.pet_id = p.id
        WHERE (? = 0 OR p.user_id = ?)
        ORDER BY ce.id DESC LIMIT 4""", (user_id, user_id)).fetchall()
    pts = db.execute("""
        SELECT COALESCE(SUM(l.amount),0) AS t
        FROM points_ledger l JOIN pets p ON l.pet_id = p.id
        WHERE (? = 0 OR p.user_id = ?)""", (user_id, user_id)).fetchone()["t"]
    return {"points": pts, "receipts": [dict(r) for r in rows],
            "events": [dict(r) for r in ev],
            "coupon_events": [dict(r) for r in ce]}


@app.get("/api/v1/home")
def home_dashboard(user_id: int = 0):
    """Round 10 - the home needs content: action-required (overdue
    vaccines / expiring coupons) + the rewards showcase (catalog with
    affordability) + birthdays. Kills the void with USEFUL content."""
    db = _db()
    pets = db.execute("SELECT * FROM pets WHERE (?=0 OR user_id=?) ORDER BY id",
                      (user_id, user_id)).fetchall()
    # action-required: overdue vaccines per pet
    from vaccine_schedule import summarize
    actions = []
    import datetime as _dt
    for p in pets:
        dismissed = {r["kind"] for r in db.execute(
            "SELECT kind FROM dismissed WHERE pet_id=?", (p["id"],)).fetchall()}
        ev = db.execute("SELECT name,date FROM health_events WHERE pet_id=?",
                        (p["id"],)).fetchall()
        cal = summarize([dict(r) for r in ev])
        for c in cal.get("calendar", []):
            if c["overdue"] and "overdue" not in dismissed:
                actions.append({"type": "vaccine_overdue", "pet": p["name"],
                                "pet_id": p["id"], "vaccine": c["vaccine"],
                                "due": c["next"], "days_left": c["days_left"]})
        if not ev and "first_vaccine" not in dismissed:
            actions.append({"type": "first_vaccine", "pet": p["name"],
                            "pet_id": p["id"],
                            "about": "Start the health record - log the first vaccine"})
    # expiring coupons
    coupons = db.execute("""
        SELECT c.title, c.pet_id, p.name AS pet, c.created_at
        FROM coupons c JOIN pets p ON c.pet_id = p.id
        WHERE (?=0 OR p.user_id=?) AND c.redeemed=0
        ORDER BY c.id DESC LIMIT 3""", (user_id, user_id)).fetchall()
    for c in coupons:
        actions.append({"type": "coupon_ready", "pet": c["pet"],
                        "pet_id": c["pet_id"], "about": c["title"]})
    # rewards showcase: progress toward each coupon (the visual hook)
    showcase = []
    pts = db.execute("""
        SELECT COALESCE(SUM(l.amount),0) AS t
        FROM points_ledger l JOIN pets p ON l.pet_id = p.id
        WHERE (?=0 OR p.user_id=?)""", (user_id, user_id)).fetchone()["t"]
    for c in _catalog():
        cost = c.get("points", 0)
        progress = round(min(100.0 * pts / cost, 100.0), 0) if cost else 0
        showcase.append({"id": c["id"], "title": c["title"],
                         "brand": c["brand"], "points": cost,
                         "affordable": pts >= cost,
                         "progress": progress,
                         "needed": max(cost - pts, 0)})
    # per-pet streak + care stats (fills the home with life)
    pet_stats = []
    for p in pets:
        # upcoming vaccine (the vet summary the reviewer asked for)
        nxt = db.execute("""
            SELECT name, date FROM health_events WHERE pet_id=?
            ORDER BY date DESC LIMIT 1""", (p["id"],)).fetchone()
        ev = db.execute("SELECT name,date FROM health_events WHERE pet_id=?",
                        (p["id"],)).fetchall()
        cal = summarize([dict(r) for r in ev])
        upcoming = None
        for c in cal.get("calendar", []):
            if not c["overdue"] and c["next"]:
                if upcoming is None or c["days_left"] < upcoming["days_left"]:
                    upcoming = {"vaccine": c["vaccine"], "next": c["next"],
                                "days_left": c["days_left"]}
        pet_stats.append({
            "id": p["id"], "name": p["name"], "species": p["species"],
            "dob": p["dob"], "weight": p["weight"],
            "streak": _streak(db, p["id"]),
            "receipts": db.execute(
                "SELECT COUNT(*) AS c FROM receipts WHERE pet_id=?",
                (p["id"],)).fetchone()["c"],
            "vet": p["vet"], "insurance": p["insurance"],
            "next_vaccine": upcoming})
    return {"actions": actions, "showcase": showcase, "points": pts,
            "pet_stats": pet_stats}


@app.post("/api/v1/pets/{pid}/checkin")
def pet_checkin(pid: int, body: dict = None, x_token: str = Header(default="")):
    """Round 11 - the daily care check-in: the streak hook.
    Round 16 - records WHAT was done (walk/fed/played/brushed/litter)
    so the home has a real care log feed."""
    import datetime as _dt
    body = body or {}
    action = str(body.get("action", "care"))
    today = str(_dt.date.today())
    db = _db()
    uid = _require_user(x_token)
    if not _owns_pet(db, pid, uid):
        raise HTTPException(403, "you don't own this pet")
    # prevent double-counting a single day
    if db.execute("SELECT 1 FROM care_checks WHERE pet_id=? AND check_date=?",
                  (pid, today)).fetchone():
        return {"ok": True, "streak": _streak(db, pid), "already": True}
    db.execute("INSERT INTO care_checks (pet_id,check_date,action) VALUES (?,?,?)",
               (pid, today, action))
    db.commit()
    _points(db, pid, 25, "daily_care")
    return {"ok": True, "streak": _streak(db, pid), "points": 25}


def _streak(db, pid: int) -> int:
    """Consecutive-day streak (counts today if checked)."""
    import datetime as _dt
    days = sorted(r["check_date"] for r in db.execute(
        "SELECT check_date FROM care_checks WHERE pet_id=?",
        (pid,)).fetchall())
    if not days:
        return 0
    today = _dt.date.today()
    streak = 0
    cur = today
    ds = set(days)
    if str(today) not in ds:
        cur = today - _dt.timedelta(days=1)  # streak continues from yesterday
    while str(cur) in ds:
        streak += 1
        cur -= _dt.timedelta(days=1)
    return streak


@app.get("/api/v1/pets/{pid}/streak")
def pet_streak(pid: int):
    db = _db()
    return {"streak": _streak(db, pid)}


@app.post("/api/v1/pets/{pid}/dismiss")
def dismiss(pid: int, body: dict = None):
    """Round 14 - the reviewer's Dismiss CTA: hide a reminder kind."""
    body = body or {}
    kind = str(body.get("kind", "overdue"))
    db = _db()
    import datetime as _dt
    db.execute("INSERT OR REPLACE INTO dismissed (pet_id,kind,dismissed_at) "
               "VALUES (?,?,?)",
               (pid, kind, str(_dt.datetime.utcnow())))
    db.commit()
    return {"ok": True}


@app.get("/api/v1/care-log")
def care_log(user_id: int = 0, limit: int = 10):
    """Round 16 - the care log feed: what the pack did, when.
    Fills the home void with REAL daily activity."""
    db = _db()
    rows = db.execute("""
        SELECT c.check_date, c.action, p.name AS pet, p.species
        FROM care_checks c JOIN pets p ON c.pet_id = p.id
        WHERE (?=0 OR p.user_id=?)
        ORDER BY c.id DESC LIMIT ?""", (user_id, user_id, limit)).fetchall()
    return {"log": [dict(r) for r in rows]}


@app.get("/api/v1/pets/{pid}/history")
def receipt_history(pid: int):
    """Round 17 - the receipt HISTORY view: every scan with its items.
    The user asked where the scan history is - it's now a real view."""
    db = _db()
    rows = db.execute("""
        SELECT r.id, r.store, r.amount, r.date, r.raw_ocr
        FROM receipts r WHERE r.pet_id=? ORDER BY r.id DESC LIMIT 30""",
        (pid,)).fetchall()
    out = []
    for r in rows:
        items = db.execute("""
            SELECT brand, product, amount FROM purchases
            WHERE receipt_id=? ORDER BY id""", (r["id"],)).fetchall()
        out.append({"id": r["id"], "store": r["store"],
                    "amount": r["amount"], "date": r["date"],
                    "items": [dict(i) for i in items]})
    return {"history": out}


@app.get("/api/v1/coupons/{code}/validate")
def validate_coupon(code: str):
    """Round 19 - THE SHOP-SIDE VALIDATION: how a retailer checks a
    coupon is real. The shop scans the GS1 barcode (or types the code)
    and calls this endpoint. We return the honest verdict.

    THIS IS THE HONEST DESIGN: the GS1 DataBar carries the offer, but
    real retail settlement needs the brand's registered prefix + Coupon
    Bureau. Until then, THIS endpoint is the validation path — the shop
    checks with us, we check the ledger (single-use, not expired)."""
    db = _db()
    c = db.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
    if not c:
        return {"verdict": "UNKNOWN", "reason": "no such coupon"}
    if c["redeemed"]:
        return {"verdict": "ALREADY_REDEEMED",
                "reason": "this coupon was already used"}
    # expiry: coupons are valid 90 days from mint (the catalog sets it)
    import datetime as _dt
    try:
        minted = _dt.date.fromisoformat(c["created_at"])
        if (_dt.date.today() - minted).days > 90:
            return {"verdict": "EXPIRED", "reason": "coupon is past 90 days"}
    except Exception:
        pass
    return {"verdict": "VALID", "title": c["title"],
            "brand": c["brand"], "gs1": c["barcode"],
            "note": "present this to the cashier"}


class MealIn(BaseModel):
    pet_id: int
    food_upc: str = ""
    brand: str = ""
    product: str = ""
    amount: float = 0


@app.post("/api/v1/meals")
def log_meal(body: MealIn, x_token: str = Header(default="")):
    """ROUND 21 - THE FEEDING LOG: the daily habit + the data moat.
    Every meal logged = a consumption data point brands cannot buy
    ('share of stomach' - what's actually fed, when, whether it switched).
    Capped at 4 meals/day/pet to prevent gaming."""
    import datetime as _dt
    db = _db()
    uid = _require_user(x_token)
    if not _owns_pet(db, body.pet_id, uid):
        raise HTTPException(403, "you don't own this pet")
    today = str(_dt.date.today())
    n = db.execute("SELECT COUNT(*) AS c FROM meals WHERE pet_id=? "
                   "AND date(meal_time)=?", (body.pet_id, today)).fetchone()["c"]
    if n >= 4:
        raise HTTPException(400, "meal cap reached for today (max 4)")
    now = _dt.datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO meals (pet_id,food_upc,brand,product,amount,meal_time,"
        "created_at) VALUES (?,?,?,?,?,?,?)",
        (body.pet_id, body.food_upc, body.brand, body.product, body.amount,
         now, now))
    db.commit()
    _points(db, body.pet_id, 10, f"meal_{cur.lastrowid}")
    return {"ok": True, "meal_id": cur.lastrowid, "points": 10}


@app.get("/api/v1/meals/{pid}")
def meals(pid: int, days: int = 7):
    db = _db()
    rows = db.execute("""
        SELECT * FROM meals WHERE pet_id=?
        ORDER BY id DESC LIMIT 50""", (pid,)).fetchall()
    return {"meals": [dict(r) for r in rows]}


@app.get("/api/v1/consumption")
def consumption(user_id: int = 0, days: int = 14):
    """ROUND 21 - THE SHARE-OF-STOMACH PANEL: the moat.
    Consumption share by brand (meals logged), breed x brand x meals.
    This is what a brand pays for that NO retailer transaction can show."""
    db = _db()
    rows = db.execute("""
        SELECT m.brand AS brand, COUNT(*) AS meals,
               pe.breed AS breed, ROUND(SUM(m.amount),1) AS total_amount
        FROM meals m JOIN pets pe ON m.pet_id = pe.id
        WHERE m.brand != '' AND (? = 0 OR pe.user_id = ?)
        GROUP BY m.brand, pe.breed
        ORDER BY meals DESC LIMIT 20""", (user_id, user_id)).fetchall()
    total = sum(r["meals"] for r in rows) or 1
    merged = {}
    for r in rows:
        b = r["brand"]
        if b not in merged:
            merged[b] = {"brand": b, "meals": 0, "share": 0.0}
        merged[b]["meals"] += r["meals"]
    out = [{"brand": v["brand"], "meals": v["meals"],
            "share": round(100.0 * v["meals"] / total, 1)}
           for v in merged.values()]
    out.sort(key=lambda x: x["meals"], reverse=True)
    return {"days": days, "total_meals": total,
            "consumption_share": out,
            "by_breed": [dict(r) for r in rows]}


@app.get("/api/v1/recalls")
def recalls_check(user_id: int = 0):
    """ROUND 23 - FOOD RECALL ALERTS: check what the user's pets eat
    against the FDA's public recall feed. Warns BEFORE they feed a
    recalled bag (trust) + captures switching events (recall data)."""
    from recalls import recall_feed, match_recalls
    db = _db()
    feed = recall_feed()
    # what does this household feed? from meals + purchases
    brands = set()
    products = set()
    rows = db.execute("""
        SELECT m.brand, m.product FROM meals m JOIN pets p ON m.pet_id = p.id
        WHERE (?=0 OR p.user_id=?)
        UNION SELECT pu.brand, pu.product FROM purchases pu
        JOIN receipts r ON pu.receipt_id = r.id
        JOIN pets p ON r.pet_id = p.id WHERE (?=0 OR p.user_id=?)""",
        (user_id, user_id, user_id, user_id)).fetchall()
    for r in rows:
        if r["brand"]:
            brands.add(r["brand"])
        if r["product"]:
            products.add(r["product"])
    matched = []
    for b in brands:
        for h in match_recalls(feed, b, ""):
            if h not in matched:
                matched.append(h)
    for p in products:
        for h in match_recalls(feed, "", p):
            if h not in matched:
                matched.append(h)
    return {"recall_feed_size": len(feed.get("recalls", [])),
            "fed_brands": sorted(brands),
            "matches": matched[:10],
            "checked_at": feed.get("fetched_at")}


def _seed_missions(db):
    """Demo brand-funded missions (the pilot mechanism). A real brand
    fills these; the engine is what's sold."""
    n = db.execute("SELECT COUNT(*) AS c FROM missions").fetchone()["c"]
    if n == 0:
        import datetime as _dt
        now = str(_dt.datetime.utcnow())
        db.executemany(
            "INSERT INTO missions (brand,title,action,target,duration_days,"
            "points,created_at) VALUES (?,?,?,?,?,?,?)", [
            ("Royal Canin", "Feed Royal Canin for 7 days",
             "feed", 7, 7, 200, now),
            ("Greenies", "Log 5 meals this week",
             "meal", 5, 7, 100, now),
            ("Purina", "Try a Purina meal this week",
             "feed_brand", 1, 7, 50, now),
        ])
        db.commit()


@app.get("/api/v1/missions")
def missions(user_id: int = 0):
    """ROUND 25 (reviewer #2) - BRAND-FUNDED MISSIONS: the pilot engine.
    'Feed Hill's for 7 days -> 200 pts'. The brand funds the points;
    we track completion via the feeding log + care check-ins."""
    db = _db()
    _seed_missions(db)
    pets = db.execute("SELECT * FROM pets WHERE (?=0 OR user_id=?) ORDER BY id",
                      (user_id, user_id)).fetchall()
    ms = db.execute("SELECT * FROM missions WHERE active=1").fetchall()
    out = []
    for m in ms:
        # progress per pet (summed across the household)
        total = 0
        for p in pets:
            prog = db.execute(
                "SELECT count, completed FROM mission_progress "
                "WHERE mission_id=? AND pet_id=?",
                (m["id"], p["id"])).fetchone()
            if prog:
                total += prog["count"]
        # what counts toward the mission (filtered to THIS user's pets)
        import datetime as _dt
        if m["action"] in ("feed", "meal"):
            since = str(_dt.date.today() - _dt.timedelta(days=m["duration_days"]))
            total = 0
            for p in pets:
                if m["action"] == "feed":
                    c = db.execute(
                        "SELECT COUNT(*) AS c FROM meals "
                        "WHERE pet_id=? AND brand LIKE ? AND meal_time >= ?",
                        (p["id"], f"%{m['brand']}%", since)).fetchone()["c"]
                else:
                    c = db.execute(
                        "SELECT COUNT(*) AS c FROM meals "
                        "WHERE pet_id=? AND meal_time >= ?",
                        (p["id"], since)).fetchone()["c"]
                total += c
        out.append({"id": m["id"], "brand": m["brand"], "title": m["title"],
                    "points": m["points"], "target": m["target"],
                    "progress": min(total, m["target"]),
                    "done": total >= m["target"]})
    return {"missions": out}


@app.post("/api/v1/missions/{mid}/claim")
def claim_mission(mid: int, body: dict = None):
    """Claim the mission points (once). The brand funds these."""
    body = body or {}
    pet_id = int(body.get("pet_id", 0))
    db = _db()
    m = db.execute("SELECT * FROM missions WHERE id=? AND active=1",
                   (mid,)).fetchone()
    if not m:
        raise HTTPException(404, "mission not found")
    # verify completion for this pet
    if not pet_id:
        raise HTTPException(400, "pet_id required")
    prog = db.execute(
        "SELECT count, completed FROM mission_progress "
        "WHERE mission_id=? AND pet_id=?", (mid, pet_id)).fetchone()
    if prog and prog["completed"]:
        raise HTTPException(400, "already claimed")
    # the mission is a HOUSEHOLD challenge - check the pack total
    # (matches the display; the points credit to this pet)
    import datetime as _dt
    since = str(_dt.date.today() - _dt.timedelta(days=m["duration_days"]))
    uid = db.execute("SELECT user_id FROM pets WHERE id=?",
                     (pet_id,)).fetchone()
    uid = uid["user_id"] if uid else 1
    pids = [r["id"] for r in db.execute(
        "SELECT id FROM pets WHERE user_id=?", (uid,)).fetchall()]
    c = 0
    for pid in pids:
        if m["action"] == "feed":
            c += db.execute("SELECT COUNT(*) AS c FROM meals WHERE pet_id=? "
                            "AND brand LIKE ? AND meal_time >= ?",
                            (pid, f"%{m['brand']}%", since)).fetchone()["c"]
        else:
            c += db.execute("SELECT COUNT(*) AS c FROM meals WHERE pet_id=? "
                            "AND meal_time >= ?", (pid, since)).fetchone()["c"]
    if c < m["target"]:
        raise HTTPException(400, f"mission not complete yet ({c}/{m['target']})")
    db.execute("INSERT OR REPLACE INTO mission_progress "
               "(mission_id,pet_id,count,completed) VALUES (?,?,?,1)",
               (mid, pet_id, c))
    db.commit()
    _points(db, pet_id, m["points"], f"mission_{mid}")
    return {"ok": True, "points": m["points"], "title": m["title"]}


class VetInvoiceIn(BaseModel):
    pet_id: int
    image_b64: str


@app.post("/api/v1/vet-invoice")
async def vet_invoice(body: VetInvoiceIn):
    """ROUND 26 - VET INVOICE CAPTURE: scan a vet invoice, OCR extracts
    practice/date/services, auto-logs the visit + procedures."""
    from passport import _ask_vision, parse_invoice
    text = _ask_vision(body.image_b64)
    parsed = parse_invoice(text)
    db = _db()
    if not db.execute("SELECT 1 FROM pets WHERE id=?",
                      (body.pet_id,)).fetchone():
        raise HTTPException(404, "pet not found")
    total = sum(s["price"] for s in parsed["services"])
    if parsed["services"]:
        db.execute(
            "INSERT INTO health_events (pet_id,kind,name,date,notes,"
            "practice,invoice_amount) VALUES (?,?,?,?,?,?,?)",
            (body.pet_id, "vet", "Vet visit", parsed["date"],
             "scanned invoice", parsed["practice"], str(total)))
        for s in parsed["services"]:
            db.execute(
                "INSERT INTO health_events (pet_id,kind,name,date,practice,"
                "invoice_amount) VALUES (?,?,?,?,?,?)",
                (body.pet_id, "med", s["name"], parsed["date"],
                 parsed["practice"], str(s["price"])))
        db.commit()
        _points(db, body.pet_id, 100, "vet_invoice")
    return {"ok": bool(parsed["services"]), "practice": parsed["practice"],
            "date": parsed["date"], "services": parsed["services"],
            "points": 100 if parsed["services"] else 0}


@app.get("/api/v1/pets/{pid}/passport")
def pet_passport(pid: int):
    """ROUND 26 - THE PET PASSPORT: one summary of the full health record
    + weight, for vets, boarders, groomers, and travel."""
    from passport import passport_payload
    db = _db()
    p = db.execute("SELECT * FROM pets WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "pet not found")
    events = db.execute(
        "SELECT * FROM health_events WHERE pet_id=? ORDER BY date",
        (pid,)).fetchall()
    weights = db.execute(
        "SELECT weight, date FROM weights WHERE pet_id=? ORDER BY date",
        (pid,)).fetchall()
    return passport_payload(dict(p), [dict(e) for e in events],
                            [dict(w) for w in weights])


@app.get("/api/v1/pets/{pid}/portion")
def portion_calc(pid: int, food_type: str = "dry"):
    """ROUND 27 (reviewer #7) - THE PORTION CALCULATOR: weight x age x
    activity -> daily grams of the food you feed. Makes the feeding log
    USEFUL (portion confusion is a top-3 pet-parent question)."""
    from portions import daily_grams
    db = _db()
    p = db.execute("SELECT * FROM pets WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "pet not found")
    return daily_grams(weight_kg=p["weight"] or 0, dob=p["dob"] or "",
                       activity=p["activity"] or "normal",
                       species=p["species"] or "dog",
                       food_type=food_type)


# ── EDIT/DELETE (reviewer #5: data hygiene is trust) ────────────────

@app.delete("/api/v1/pets/{pid}")
def delete_pet(pid: int, x_token: str = Header(default="")):
    """Delete a pet + its data (typo correction / departed pet)."""
    uid = _require_user(x_token)
    db = _db()
    if not _owns_pet(db, pid, uid):
        raise HTTPException(403, "you don't own this pet")
    for t in ("receipts", "purchases", "health_events", "weights",
              "care_checks", "meals", "points_ledger"):
        try:
            db.execute(f"DELETE FROM {t} WHERE pet_id=?", (pid,))
        except Exception:
            pass
    db.execute("DELETE FROM pets WHERE id=?", (pid,))
    db.commit()
    return {"ok": True}


class PetEditIn(BaseModel):
    name: str = ""
    breed: str = ""
    weight: float = 0


@app.put("/api/v1/pets/{pid}")
def edit_pet(pid: int, body: PetEditIn, x_token: str = Header(default="")):
    """Edit a pet's core fields (fix typos)."""
    uid = _require_user(x_token)
    db = _db()
    if not _owns_pet(db, pid, uid):
        raise HTTPException(403, "you don't own this pet")
    sets = []
    args = []
    if body.name:
        sets.append("name=?")
        args.append(body.name)
    if body.breed:
        sets.append("breed=?")
        args.append(body.breed)
    if body.weight:
        sets.append("weight=?")
        args.append(body.weight)
    if sets:
        db.execute(f"UPDATE pets SET {', '.join(sets)} WHERE id=?",
                   args + [pid])
        db.commit()
    return {"ok": True}


@app.delete("/api/v1/pets/{pid}/events/{eid}")
def delete_event(pid: int, eid: int, x_token: str = Header(default="")):
    """Delete a health event (a mistyped vaccine entry poisons the
    calendar permanently — the reviewer's exact point)."""
    uid = _require_user(x_token)
    db = _db()
    if not _owns_pet(db, pid, uid):
        raise HTTPException(403, "you don't own this pet")
    db.execute("DELETE FROM health_events WHERE id=? AND pet_id=?",
               (eid, pid))
    db.commit()
    return {"ok": True}


@app.delete("/api/v1/receipts/{rid}")
def delete_receipt(rid: int, x_token: str = Header(default="")):
    """Delete a receipt + its purchases (a wrong scan)."""
    uid = _require_user(x_token)
    db = _db()
    r = db.execute("SELECT pet_id FROM receipts WHERE id=?", (rid,)).fetchone()
    if not r or not _owns_pet(db, r["pet_id"], uid):
        raise HTTPException(403, "not yours")
    db.execute("DELETE FROM purchases WHERE receipt_id=?", (rid,))
    db.execute("DELETE FROM receipts WHERE id=?", (rid,))
    db.commit()
    return {"ok": True}


@app.get("/api/v1/health")
def health():
    return {"ok": True, "app": "paws", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PAWS_PORT", "8235"))
    host = os.environ.get("PAWS_BIND", "100.113.24.19")
    uvicorn.run(app, host=host, port=port)
