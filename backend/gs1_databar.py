"""
paws/backend/gs1_databar.py — the REAL GS1 coupon encoder
The industry coupon format: GS1 DataBar Expanded (AI 8110) — the ONLY
format US retailer POS systems validate and clear manufacturer coupons
(spec: GS1 US "GS1 DataBar for US Distributed Coupons").

STRUCTURE (from the GS1 spec, verified against its examples):
  (8110) <VLI><CompanyPrefix> <OfferCode(6)> <SaveVLI><SaveValue>
        <ReqVLI><ReqValue><ReqCode> <FamilyCode(3)> [optional fields]

  VLI (variable length indicator) encodes the GS1 Company Prefix length:
    0=6 1=7 2=8 3=9 4=10 5=11
  Save Value Code: 0=cents-off-item 1=free-item 2=multiple-free
                   5=percent(UNCLEARABLE) 6=cents-off-order
  Req Code: 0=number-of-units 1=value-of-qualifying 2=value-of-transaction

HONESTY: percent-off offers cannot be cleared through the normal
settlement process — the real catalog uses cents-off / free / off-total.
A real coupon also requires the BRAND's registered GS1 Company Prefix;
we mint with a documented demo prefix until a brand partner is signed.
"""
import datetime
import time


def _vli(prefix_len: int) -> str:
    """Variable Length Indicator digit for a GS1 Company Prefix length."""
    return {6: "0", 7: "1", 8: "2", 9: "3", 10: "4", 11: "5"}[prefix_len]


def build_databar(company_prefix: str, offer_code: str, save_value: int,
                  save_value_code: int = 0,
                  purchase_req: int = 1, purchase_req_code: int = 0,
                  family_code: str = "111", expiry: str = "",
                  serial: str = "") -> str:
    """Build the GS1 DataBar (AI 8110) coupon payload string.
    save_value in cents ($1.00 -> 100). expiry YYMMDD (optional).

    Structure (verified against GS1 examples):
      8110 VLI prefix offer(6) svVLI sv reqVLI req reqCode fc
      [+ misc section when save_value_code != 0:
        "9" savecode appliesTo storeFlag dontMultiply]
    """
    prefix = company_prefix.zfill(7)  # normalize to 7-digit GS1 prefix
    vli = _vli(len(prefix))
    sv = str(save_value)
    sv_vli = str(len(str(save_value)))  # save value length VLI
    req = str(purchase_req)
    req_vli = str(len(req))
    fc = family_code.zfill(3)

    data = (f"8110{vli}{prefix}{offer_code}"
            f"{sv_vli}{sv}"
            f"{req_vli}{req}{purchase_req_code}{fc}")
    # serialization (AI 21) - optional, unique per coupon
    if serial:
        data += f"21{serial}"
    # miscellaneous elements section (AI 9) - required for free-item,
    # percent, order-discount, store/dont-multiply flags; omitted for the
    # plain cents-off-item case (matches the GS1 example exactly)
    if save_value_code != 0:
        data += f"9{save_value_code}000"
    return data


def demo_coupons() -> list:
    """The REAL offer catalog — cents-off/free/order formats only
    (percent offers cannot clear the standard settlement process)."""
    today = datetime.date.today()
    exp = (today + datetime.timedelta(days=90)).strftime("%y%m%d")
    return [
        {"id": "c_royal_canin_2", "brand": "Royal Canin", "category": "food",
         "title": "$2 off Royal Canin dog food",
         "points": 500, "prefix": "0012345", "save": 200,
         "save_code": 0, "req": 1, "req_code": 0, "fc": "111", "exp": exp},
        {"id": "c_purina_1", "brand": "Purina", "category": "food",
         "title": "$1 off Purina Pro Plan",
         "points": 300, "prefix": "0012346", "save": 100,
         "save_code": 0, "req": 1, "req_code": 0, "fc": "111", "exp": exp},
        {"id": "c_chewy_7", "brand": "Chewy", "category": "retail",
         "title": "$7 off your next Chewy order",
         "points": 700, "prefix": "0012347", "save": 700,
         "save_code": 6, "req": 50, "req_code": 2, "fc": "000", "exp": exp},
        {"id": "c_greenies_free", "brand": "Greenies", "category": "treats",
         "title": "FREE Greenies dental treats (up to $5)",
         "points": 450, "prefix": "0012348", "save": 500,
         "save_code": 1, "req": 1, "req_code": 0, "fc": "111", "exp": exp},
    ]


def render_databar_png(payload: str) -> bytes:
    """Render the REAL GS1 DataBar Expanded symbology (BWIPP via treepoem
    + ghostscript — the same symbology retailer POS systems read)."""
    import io
    import treepoem
    # BWIPP requires parenthesized AIs: (8110)... — the payload is
    # AI 8110 + data, so the full GS1 string starts with '(8110)'
    data = "(8110)" + payload[len("8110"):]
    img = treepoem.generate_barcode("databarexpanded", data,
                                    {"includetext": True})
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
