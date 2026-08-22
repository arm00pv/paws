# PAWS — Brand Partnership Pitch (v1)

## The one-paragraph pitch

> **PAWS is a rewards + pet-profile app where pet parents scan receipts, emails,
> and barcodes to earn points — and every scan builds a clean, first-party,
> purchase-verified panel: breed × age × weight × food × brand spend.
> We are the fetch-for-fur data network, and your brand can buy the audience.**

## Who we'd pitch (the pet industry's actual buyers)

| Brand | Why they buy | What we'd sell them |
|---|---|---|
| **Hill's Pet Nutrition** (Colgate, $3.7B) | Already pays a premium provider covering 98% of pet-food transactions via LiveRamp Clean Room (documented) | Their exact customers' real purchase history — breed × food × weight, fresher than the panel |
| **Purina / Mars Pet** | 6B impressions across 18 retail-media networks in 2025 — heavy shopper-data spenders | Category targeting: "buyers who feed X also buy Y" |
| **Blue Buffalo / General Mills** | DTC acquisition budgets; wants first-party pet-parent data | New-pet-parent detection + first-food-brand preference |
| **DTC brands** (Farmer's Dog, Ollie, Spot & Tango) | Subscription brands die without owner data | Household composition + food-switching signals |
| **Chewy Ads** | $12B retailer with a retail-media network; 1-in-3 clicks converts | Our panel as an **off-platform** extension of their audience |

## What we sell (the product menu)

### 1. The Panel — aggregated market intelligence (`/api/v1/panel`)
- Brand share by spend and units (already built)
- **Breed × food matrix** (already built) — the targeting gold: "German Shepherds buy Royal Canin at 79% share"
- Category mix: food / treats / toys / vet
- Panel growth (pets, receipts, spend over time)
- **Priced like the panels they already buy** (Hill's pays premium for clean room data) — anchor at the panel rate, not per-record

### 2. Custom audiences (B2B activation)
- Anonymized segments: "German Shepherd owners buying Purina" → matchable cohort
- Deliverable via clean room (LiveRamp-compatible) or our own export
- Price: CPM-style or per-matched-audience

### 3. Branded promotions (Fetch mechanics, pet-specific)
- "Scan a Blue Buffalo bag → 50 pts" — the brand funds the points
- **The coupon mint IS the sales mechanism**: our GS1 DataBar coupons are tracked, single-use, and redeemable at retail — the brand sees exactly what converted
- Price: per-redemption + media fee (the PETZ model: "pay only when the coupon is redeemed")

### 4. The knowledge base (the compounding moat)
- Our self-learning UPC catalog (every taught scan = proprietary UPC→brand data)
- A brand pays for coverage in *our* catalog (their SKUs, their shelf visibility)
- Price: listing + insights

---

## Why this is defensible (the honest moat)

1. **Pet health data is NOT HIPAA-regulated** — we hold the full medical + purchase profile, legally
2. **First-party, purchase-verified** — unlike surveys or panels, every row is a real transaction
3. **The panel self-feeds** — users do the work (scan/photo/email) to earn points; our cost per record is near zero
4. **The UPC knowledge base compounds** — nobody else has 1000 taught pet UPCs
5. **No giant in the seat** — Fetch/IBotta treat pets as a line on a grocery receipt; Chewy has accounts, not a rewards data play

---

## The honest gaps (what we must do before real money)

| Gap | Why it matters | Effort |
|---|---|---|
| **Real users** | Brand contracts are sized by panel coverage (100s → 1000s of pets) | Public launch + growth loop (referral built) |
| **The Coupon Bureau / GS1 registration** | Real retail redemption needs the 8112 Universal Coupon standard + bureau account | Business relationship, ~weeks |
| **A brand's GS1 Company Prefix** | Coupons must carry the brand's own prefix | The deal itself |
| **A signed pilot** | First check > everything; even $5k pilot proves the model | Pitch + relationship |
| **Watchtower deploy** | Public surface for real signups | Network pending |

---

## The pitch sequence (the actual ask)

1. **Cold open**: "We have X pets, Y receipts, Z spend of purchase-verified, breed-tagged pet data — from pet parents who opted in by scanning their own receipts. Here's your brand share in our panel."
2. **The demo:** live panel, breed × food matrix, the UPC catalog
3. **The pilot:** $X/mo for a 3-month panel subscription + one branded promotion ("scan a [brand] bag → points")
4. **The scale:** 10x panel → premium data deal

---

*Built with the institution's stack: panel intelligence from real receipts/emails/barcodes, GS1 DataBar coupons, self-hosted infra. The product is real; the relationship is the next build.*
