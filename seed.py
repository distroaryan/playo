"""
Seed script — Idempotent.
Creates the default merchant and populates ledger entries.
Net balance = ₹1,00,000 (10,000,000 paise).

Usage:  python seed.py
"""

import os
import sys
import uuid
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playto.settings")
django.setup()

from api.models import Merchant, Ledger, Payout  # noqa: E402

MERCHANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
MERCHANT_NAME = "Playto Demo Merchant"
MERCHANT_EMAIL = "demo@playto.dev"

# ── Target: net balance = ₹1,00,000 = 10,000,000 paise ──────
# Credits total:  12,500,000 paise  (₹1,25,000)
# Debits  total:  -2,500,000 paise  (₹25,000)
# Net:            10,000,000 paise  (₹1,00,000)

SEED_ENTRIES = [
    # ── Credits ───────────────────────────────────────────────
    {"id": "aaaaaaaa-0001-0000-0000-000000000000", "type": "CREDIT", "amount":  5_000_000},  # ₹50,000
    {"id": "aaaaaaaa-0002-0000-0000-000000000000", "type": "CREDIT", "amount":  3_000_000},  # ₹30,000
    {"id": "aaaaaaaa-0003-0000-0000-000000000000", "type": "CREDIT", "amount":  2_000_000},  # ₹20,000
    {"id": "aaaaaaaa-0004-0000-0000-000000000000", "type": "CREDIT", "amount":  1_500_000},  # ₹15,000
    {"id": "aaaaaaaa-0005-0000-0000-000000000000", "type": "CREDIT", "amount":  1_000_000},  # ₹10,000

    # ── Debits (successful past payouts) ──────────────────────
    {"id": "bbbbbbbb-0001-0000-0000-000000000000", "type": "DEBIT",  "amount": -1_000_000},  # -₹10,000
    {"id": "bbbbbbbb-0002-0000-0000-000000000000", "type": "DEBIT",  "amount":   -750_000},  # -₹7,500
    {"id": "bbbbbbbb-0003-0000-0000-000000000000", "type": "DEBIT",  "amount":   -500_000},  # -₹5,000
    {"id": "bbbbbbbb-0004-0000-0000-000000000000", "type": "DEBIT",  "amount":   -250_000},  # -₹2,500
]


def seed():
    print("── Seeding Playto database ─────────────────────────")

    # 1. Merchant (idempotent)
    merchant, created = Merchant.objects.update_or_create(
        id=MERCHANT_ID,
        defaults={"name": MERCHANT_NAME, "email": MERCHANT_EMAIL},
    )
    print(f"   Merchant {'created' if created else 'already exists'}: {merchant}")

    # 2. Wipe old seed ledger rows and re-insert (idempotent)
    seed_ids = [uuid.UUID(e["id"]) for e in SEED_ENTRIES]
    deleted, _ = Ledger.objects.filter(id__in=seed_ids).delete()
    if deleted:
        print(f"   Cleared {deleted} previous seed ledger entries")

    for entry in SEED_ENTRIES:
        Ledger.objects.create(
            id=uuid.UUID(entry["id"]),
            merchant=merchant,
            entry_type=entry["type"],
            amount_paise=entry["amount"],
            payout=None,
        )

    # 3. Summary
    total = sum(e["amount"] for e in SEED_ENTRIES)
    credits = sum(e["amount"] for e in SEED_ENTRIES if e["amount"] > 0)
    debits = sum(e["amount"] for e in SEED_ENTRIES if e["amount"] < 0)

    print(f"   Inserted {len(SEED_ENTRIES)} ledger entries")
    print(f"   Credits:  ₹{credits / 100:,.2f}")
    print(f"   Debits:   ₹{abs(debits) / 100:,.2f}")
    print(f"   Net:      ₹{total / 100:,.2f}")
    print("── Done ────────────────────────────────────────────\n")


if __name__ == "__main__":
    seed()
