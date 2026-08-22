"""
paws/backend/vaccine_schedule.py — THE VACCINE CALENDAR ENGINE
Auto-calculates next-due dates for core dog vaccines based on:
  - the vaccine type's standard protocol (AAHA core guidelines)
  - the last administered date
  - age (puppy series vs adult boosters)

This is the STICKY feature: the profile + a *complete dated* vaccine
history is the data moat (brands value it), and reminders make the app
useful between purchases.

Protocols (simplified AAHA core + common non-core):
  DHPP      : puppy 3-dose series (6/10/14 wks) → 1yr booster → every 3 yrs
  Rabies    : 1st dose at 12-16 wks → 1yr → then every 1 or 3 yrs
  Bordetella: every 6-12 months (kennel/daycare requirement)
  Leptospirosis: every 12 months
  Lyme      : every 12 months
  Heartworm test: every 12 months
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VaccineProtocol:
    name: str
    kind: str  # vaccine | test
    puppy_series: list  # [weeks]
    first_booster_months: int = 12
    interval_months: int = 36
    notes: str = ""


PROTOCOLS = {
    "DHPP": VaccineProtocol("DHPP (Distemper/Parvo)", "vaccine",
                            [6, 10, 14], 12, 36,
                            "Core — every 3 years after the 1-year booster"),
    "Rabies": VaccineProtocol("Rabies", "vaccine", [16], 12, 36,
                              "1-yr dose first, then 1- or 3-yr vaccine"),
    "Bordetella": VaccineProtocol("Bordetella (kennel cough)", "vaccine",
                                  [8], 6, 6,
                                  "Every 6-12 months (boarding/daycare)"),
    "Leptospirosis": VaccineProtocol("Leptospirosis", "vaccine",
                                     [12], 12, 12, "Yearly"),
    "Lyme": VaccineProtocol("Lyme", "vaccine", [12], 12, 12, "Yearly"),
    "Heartworm": VaccineProtocol("Heartworm test", "test",
                                 [], 12, 12, "Yearly test"),
    "FleaTick": VaccineProtocol("Flea/tick prevention", "med",
                                [], 1, 1, "Monthly"),
}


def _months_ahead(d: str, months: int) -> str:
    """Add months to a YYYY-MM-DD date (best-effort day clamp)."""
    import datetime
    try:
        dt = datetime.date.fromisoformat(d)
    except Exception:
        return ""
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    day = min(dt.day, 28)  # clamp to avoid month-length issues
    try:
        return datetime.date(y, m, day).isoformat()
    except Exception:
        return ""


def schedule_next(last_date: str, protocol_name: str,
                  is_puppy: bool = False) -> dict:
    """Given the last administered date + vaccine name, return the next
    due date and status window (days until due, overdue flag)."""
    proto = PROTOCOLS.get(protocol_name)
    if not proto:
        return {"ok": False, "error": f"unknown vaccine: {protocol_name}"}
    # puppy series: the schedule is the series itself (handled in UI)
    if is_puppy and proto.puppy_series:
        return {"ok": True, "stage": "puppy-series",
                "next": _months_ahead(last_date, 1),
                "interval_months": 1}
    nxt = _months_ahead(last_date, proto.interval_months)
    return {"ok": True, "stage": "booster", "next": nxt,
            "interval_months": proto.interval_months}


def summarize(events: list) -> dict:
    """Given health events (name/date), produce the calendar:
    next-due per vaccine, overdue flags, days-until."""
    import datetime as _dt
    today = _dt.date.today()
    out = []
    by_name = {}
    for e in events:
        name = (e.get("name") or "").lower()
        if not name:
            continue
        by_name[name] = e.get("date") or ""
    for name, last in by_name.items():
        # match protocol by normalized name
        proto_name = None
        for key in PROTOCOLS:
            if key.lower() in name or name in key.lower():
                proto_name = key
                break
        if not proto_name:
            continue
        nxt = _months_ahead(last, PROTOCOLS[proto_name].interval_months)
        days_left = 9999
        overdue = False
        if nxt:
            try:
                nd = _dt.date.fromisoformat(nxt)
                days_left = (nd - today).days
                overdue = days_left < 0
            except Exception:
                pass
        out.append({"vaccine": PROTOCOLS[proto_name].name,
                    "protocol": proto_name,
                    "last": last, "next": nxt,
                    "days_left": max(days_left, 0),
                    "overdue": overdue})
    out.sort(key=lambda x: (not x["overdue"], x["days_left"]))
    return {"calendar": out, "overdue_count": sum(1 for o in out if o["overdue"]),
            "next_due": min((o for o in out if not o["overdue"]),
                            key=lambda x: x["days_left"],
                            default=None)}
