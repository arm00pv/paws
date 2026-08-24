"""
paws/backend/passport.py — ROUND 26: VET INVOICE CAPTURE + PET PASSPORT
(reviewer #8 + agy's "1-click Pet Passport")
- Scan a vet invoice: OCR extracts practice/date/services, auto-logs
  them into the health record (the 'show the new vet' use case).
- The passport: one summary of the full health record + weight, for
  vets, boarders, groomers, and travel.
"""
import json
import os
import base64
import tempfile
import datetime


def _ask_vision(image_b64: str) -> str:
    """Route through the institution's local vision model (queue-aware)."""
    import sys
    sys.path.insert(0, "/home/zixen15/are")
    from vision_world import ask_vision
    img = base64.b64decode(image_b64)
    tmp = os.path.join(tempfile.gettempdir(),
                       f"paws_vet_{int(__import__('time').time())}.png")
    with open(tmp, "wb") as f:
        f.write(img)
    text = ask_vision(
        tmp,
        "Extract from this vet invoice: the practice name, the date, and "
        "every procedure or service with its price. Return STRICT JSON "
        'with keys "practice", "date", "services" where services is a '
        'list of {"name": "...", "price": 45.00}. Only the JSON.')
    os.remove(tmp)
    return text


def parse_invoice(text: str) -> dict:
    """Parse the OCR JSON into practice + services (with a fallback)."""
    import re
    practice = ""
    date = ""
    services = []
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            d = json.loads(m.group(0))
            practice = str(d.get("practice", ""))
            date = str(d.get("date", ""))
            for s in d.get("services", [])[:20]:
                services.append({"name": str(s.get("name", "")),
                                 "price": float(s.get("price", 0) or 0)})
        except Exception:
            services = []
    if not services:
        # fallback: NAME ... $xx.xx lines
        for line in text.splitlines():
            mm = re.match(r"([A-Za-z][^|]{2,60}?)\s+\$?([\d.]+)", line)
            if mm:
                services.append({"name": mm.group(1).strip(),
                                 "price": float(mm.group(2))})
    return {"practice": practice, "date": date, "services": services}


def passport_payload(pet, events, weights) -> dict:
    """The passport summary: pet info + vaccine/visit records + weight."""
    return {
        "pet": {"name": pet["name"], "breed": pet["breed"],
                "species": pet["species"], "sex": pet["sex"],
                "dob": pet["dob"], "weight": pet["weight"],
                "microchip": pet["microchip"], "vet": pet["vet"],
                "insurance": pet["insurance"]},
        "vaccines": [{"name": e["name"], "date": e["date"],
                      "practice": e["practice"]}
                     for e in events if e["kind"] == "vaccine"],
        "visits": [{"name": e["name"], "date": e["date"],
                    "practice": e["practice"],
                    "amount": e["invoice_amount"]}
                   for e in events if e["kind"] in ("vet", "test", "med")],
        "weight_history": [{"weight": w["weight"], "date": w["date"]}
                           for w in weights],
        "generated": str(datetime.datetime.utcnow()),
    }
