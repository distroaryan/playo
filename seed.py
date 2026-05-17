"""
Seed script — Idempotent.

Creates the default merchant and populates a realistic set of ledger entries:
  • 5 CREDIT entries  (incoming earnings)
  • 4 historical DEBIT entries linked to completed SUCCESS payouts
  • 2 historical FAILED payout attempts (no ledger debit — funds released back)
  • Net available balance = ₹1,00,000 (10,000,000 paise)

Usage:
    python seed.py            # normal idempotent run
    python seed.py --reset    # wipe all seed data, then re-seed
    python seed.py --dry-run  # show what would be inserted without touching DB
"""

import os
import sys
import uuid
import django
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playto.settings")
django.setup()

from api.models import Merchant, Ledger, Payout  # noqa: E402
from django.db import transaction                  # noqa: E402

# ──────────────────────────────────────────────────────────────
# Seed identities
# ──────────────────────────────────────────────────────────────

MERCHANT_ID    = uuid.UUID("00000000-0000-0000-0000-000000000000")
MERCHANT_NAME  = "Playto Demo Merchant"
MERCHANT_EMAIL = "demo@playto.dev"

# Historical bank accounts used in seed payouts
BANK_ACCOUNTS = [
    "HDFC-ACC-001",
    "ICICI-ACC-002",
    "AXIS-ACC-003",
    "SBI-ACC-004",
]

# ── Credit entries ────────────────────────────────────────────
# Total credits: ₹1,25,000 (12,500,000 paise)
SEED_CREDITS = [
    {"id": "aaaaaaaa-0001-0000-0000-000000000000", "amount":  5_000_000, "label": "Platform earnings Q1"},
    {"id": "aaaaaaaa-0002-0000-0000-000000000000", "amount":  3_000_000, "label": "Platform earnings Q2"},
    {"id": "aaaaaaaa-0003-0000-0000-000000000000", "amount":  2_000_000, "label": "Bonus credit"},
    {"id": "aaaaaaaa-0004-0000-0000-000000000000", "amount":  1_500_000, "label": "Refund credit"},
    {"id": "aaaaaaaa-0005-0000-0000-000000000000", "amount":  1_000_000, "label": "Platform earnings Q3"},
]

# ── Successful historical payouts (produce a DEBIT ledger entry each) ────────
# Total debits: ₹25,000 (2,500,000 paise)  →  Net balance = ₹1,00,000
SEED_SUCCESS_PAYOUTS = [
    {
        "payout_id":    "cccccccc-0001-0000-0000-000000000000",
        "ledger_id":    "bbbbbbbb-0001-0000-0000-000000000000",
        "amount":        1_000_000,   # ₹10,000
        "bank_account": BANK_ACCOUNTS[0],
        "days_ago":     14,
    },
    {
        "payout_id":    "cccccccc-0002-0000-0000-000000000000",
        "ledger_id":    "bbbbbbbb-0002-0000-0000-000000000000",
        "amount":          750_000,   # ₹7,500
        "bank_account": BANK_ACCOUNTS[1],
        "days_ago":     10,
    },
    {
        "payout_id":    "cccccccc-0003-0000-0000-000000000000",
        "ledger_id":    "bbbbbbbb-0003-0000-0000-000000000000",
        "amount":          500_000,   # ₹5,000
        "bank_account": BANK_ACCOUNTS[2],
        "days_ago":     6,
    },
    {
        "payout_id":    "cccccccc-0004-0000-0000-000000000000",
        "ledger_id":    "bbbbbbbb-0004-0000-0000-000000000000",
        "amount":          250_000,   # ₹2,500
        "bank_account": BANK_ACCOUNTS[3],
        "days_ago":     2,
    },
]

# ── Failed historical payouts (no ledger debit — HOLD was released) ──────────
SEED_FAILED_PAYOUTS = [
    {
        "payout_id":    "dddddddd-0001-0000-0000-000000000000",
        "amount":          200_000,   # ₹2,000  (funds NOT debited)
        "bank_account": BANK_ACCOUNTS[0],
        "days_ago":     8,
    },
    {
        "payout_id":    "dddddddd-0002-0000-0000-000000000000",
        "amount":          100_000,   # ₹1,000  (funds NOT debited)
        "bank_account": BANK_ACCOUNTS[1],
        "days_ago":     4,
    },
]

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"

def _fmt_row(label: str, value: str, width: int = 40) -> str:
    return f"   {label:<{width}} {value}"


# ──────────────────────────────────────────────────────────────
# Core seed logic
# ──────────────────────────────────────────────────────────────

def reset_seed():
    """Wipe all seed data so we start with a clean slate."""
    print("── Resetting seed data ─────────────────────────────")

    # Collect all known seed IDs
    payout_ids  = [uuid.UUID(p["payout_id"]) for p in SEED_SUCCESS_PAYOUTS + SEED_FAILED_PAYOUTS]
    ledger_ids  = [uuid.UUID(e["ledger_id"]) for e in SEED_SUCCESS_PAYOUTS]
    credit_ids  = [uuid.UUID(c["id"])        for c in SEED_CREDITS]

    with transaction.atomic():
        l_del, _ = Ledger.objects.filter(id__in=ledger_ids + credit_ids).delete()
        p_del, _ = Payout.objects.filter(id__in=payout_ids).delete()
        m_del, _ = Merchant.objects.filter(id=MERCHANT_ID).delete()

    print(f"   Deleted {l_del} ledger entries, {p_del} payouts, {m_del} merchant(s)")
    print("── Reset complete ──────────────────────────────────\n")


def seed(dry_run: bool = False):
    print("── Seeding Playto database ─────────────────────────")
    if dry_run:
        print("   [DRY RUN] No changes will be written.\n")

    now = timezone.now()

    # ── 1. Merchant (idempotent) ──────────────────────────────
    if not dry_run:
        merchant, created = Merchant.objects.update_or_create(
            id=MERCHANT_ID,
            defaults={"name": MERCHANT_NAME, "email": MERCHANT_EMAIL},
        )
        print(_fmt_row("Merchant", f"{'created' if created else 'already exists'} → {merchant}"))
    else:
        print(_fmt_row("Merchant", f"[would upsert] {MERCHANT_NAME} <{MERCHANT_EMAIL}>"))

    # ── 2. Credit entries (idempotent: delete-then-insert) ────
    if not dry_run:
        credit_uuids = [uuid.UUID(c["id"]) for c in SEED_CREDITS]
        del_count, _ = Ledger.objects.filter(id__in=credit_uuids).delete()
        if del_count:
            print(_fmt_row("Credits cleared", f"{del_count} existing rows removed"))

        for c in SEED_CREDITS:
            Ledger.objects.create(
                id=uuid.UUID(c["id"]),
                merchant=merchant,
                entry_type="CREDIT",
                amount_paise=c["amount"],
                payout=None,
            )

    total_credits = sum(c["amount"] for c in SEED_CREDITS)
    print(_fmt_row(f"Credits inserted ({len(SEED_CREDITS)} entries)", _rupees(total_credits)))

    # ── 3. Successful historical payouts + DEBIT ledger entries ──────────────
    total_debits = 0
    success_count = 0

    for p in SEED_SUCCESS_PAYOUTS:
        pid       = uuid.UUID(p["payout_id"])
        lid       = uuid.UUID(p["ledger_id"])
        created_t = now - timedelta(days=p["days_ago"])

        if not dry_run:
            with transaction.atomic():
                payout, _ = Payout.objects.update_or_create(
                    id=pid,
                    defaults={
                        "merchant":        merchant,
                        "bank_account_id": p["bank_account"],
                        "amount_paise":    p["amount"],
                        "status":          "SUCCESS",
                        "retry_count":     0,
                    },
                )
                # Force created_at (use update to bypass auto_now_add)
                Payout.objects.filter(id=pid).update(created_at=created_t, updated_at=created_t)

                # Idempotently recreate the DEBIT ledger entry
                Ledger.objects.filter(id=lid).delete()
                Ledger.objects.create(
                    id=lid,
                    merchant=merchant,
                    entry_type="DEBIT",
                    amount_paise=-p["amount"],
                    payout=payout,
                )
                Ledger.objects.filter(id=lid).update(created_at=created_t, updated_at=created_t)

        total_debits  += p["amount"]
        success_count += 1

    print(_fmt_row(f"SUCCESS payouts inserted ({success_count})", f"-{_rupees(total_debits)}"))

    # ── 4. Failed historical payouts (no ledger entry) ────────
    fail_count = 0
    for p in SEED_FAILED_PAYOUTS:
        pid       = uuid.UUID(p["payout_id"])
        created_t = now - timedelta(days=p["days_ago"])

        if not dry_run:
            Payout.objects.update_or_create(
                id=pid,
                defaults={
                    "merchant":        merchant,
                    "bank_account_id": p["bank_account"],
                    "amount_paise":    p["amount"],
                    "status":          "FAILED",
                    "retry_count":     3,
                },
            )
            Payout.objects.filter(id=pid).update(created_at=created_t, updated_at=created_t)

        fail_count += 1

    print(_fmt_row(f"FAILED payouts inserted ({fail_count})", "no funds debited"))

    # ── 5. Summary ────────────────────────────────────────────
    net = total_credits - total_debits
    print()
    print("   ┌─────────────────────────────────────────────┐")
    print(f"   │  Total Credits:  {_rupees(total_credits):>25}      │")
    print(f"   │  Total Debits:  -{_rupees(total_debits):>25}      │")
    print(f"   │  ─────────────────────────────────────────  │")
    print(f"   │  Net Balance:    {_rupees(net):>25}      │")
    print("   └─────────────────────────────────────────────┘")
    print()
    print("── Done ────────────────────────────────────────────\n")


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    do_reset   = "--reset"   in args
    do_dry_run = "--dry-run" in args

    if do_reset and not do_dry_run:
        reset_seed()

    seed(dry_run=do_dry_run)
