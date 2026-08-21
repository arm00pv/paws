# PAWS — Rewards + Pet Profiles

The Fetch-model applied to pets: **a dog profile + receipt scanning + points → REAL GS1 DataBar coupons**, self-hosted and privacy-first.

Pet health data is **not HIPAA-regulated** (they're animals) — so a full pet profile (vaccines, allergies, weight, purchases) is legal to store, unlike human health apps.

## What works (all real, tested)

```
DOG PROFILE → HEALTH RECORDS → RECEIPT SCAN → POINTS → GS1 COUPON MINT → SCANNABLE BARCODE
```

- **Pet profiles** — breed, weight, DOB, microchip, allergies, health timeline (vaccines/vet visits earn points)
- **Receipt scanning** — camera photo → the local vision model OCRs it → structured items → points (~1 pt per $1)
- **Points engine** — full ledger, balance checks, burn-on-redeem
- **GS1 DataBar coupons (AI 8110)** — the REAL retail coupon format US POS systems validate and clear. Encoder verified byte-for-byte against the GS1 US spec example. Rendered via BWIPP (DataBar Expanded).
- **Honest catalog** — percent-off coupons can't clear the GS1 settlement process, so the catalog only offers cents-off / free-item / off-total formats

## Architecture

```
backend/
  paws_api.py        FastAPI + SQLite (pet profiles, health, receipts, points, coupons)
  gs1_databar.py     the REAL GS1 DataBar coupon encoder + renderer
app/                 Flutter web + Android
  lib/main.dart      dog profile, scan-receipt camera flow, coupon wallet, barcode viewer
state/               paws.db (SQLite, self-hosted)
```

## The business model

1. **Brand shopper data (B2B)** — breed × age × food × spend panel — Mars/Hill's/Purina pay for this today (Hill's buys 98% pet-food transaction data via LiveRamp)
2. **Pet brand promotions** — "scan a Blue Buffalo bag → 50 pts" (Fetch mechanics, pet-specific)
3. **Affiliate** — Chewy/Amazon links
4. **Premium tier** — unlimited profiles, health export

## Run

```bash
cd backend
python paws_api.py              # API on :8235
cd app
flutter build web --base-href=/paws/   # web
flutter build apk                       # Android
```

## Honest status

- The **machine is real**: capture (vision OCR) → points → GS1 mint. 
- The **business deals are the next step**: a real coupon needs a brand's registered GS1 Company Prefix + The Coupon Bureau registration.

**License**: AGPL-3.0 (the codebase is our clean-room implementation; the design pattern follows Securo's provider-backbone architecture, not its code).
