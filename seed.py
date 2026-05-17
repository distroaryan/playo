"""
Seed script — Idempotent.

Creates 2 users with associated merchants and populates realistic ledger entries:

  User 1: Tesla  <test1@cmail.com>  password: test1
  User 2: Mark   <test2@cmail.com>  password: test2

For each merchant:
  • 6 CREDIT entries        (incoming earnings)
  • 5 SUCCESS payout pairs  (DEBIT ledger entries, linked to completed payouts)
  • 2 FAILED payout records (no ledger debit — funds released back)
  • Net available balance   = ₹1,00,000 exactly (10,000,000 paise)

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

from django.contrib.auth.models import User          # noqa: E402
from django.db import transaction                     # noqa: E402
from api.models import Merchant, Ledger, Payout       # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Seed identities — fixed UUIDs so the script is always idempotent
# ──────────────────────────────────────────────────────────────────────────────

USERS = [
    {
        "username": "test1@cmail.com",
        "email":    "test1@cmail.com",
        "password": "test1",
        "name":     "Tesla",
    },
    {
        "username": "test2@cmail.com",
        "email":    "test2@cmail.com",
        "password": "test2",
        "name":     "Mark",
    },
]

MERCHANTS = [
    {
        "id":    uuid.UUID("11111111-0000-0000-0000-000000000001"),
        "name":  "Tesla",
        "email": "test1@cmail.com",
    },
    {
        "id":    uuid.UUID("22222222-0000-0000-0000-000000000002"),
        "name":  "Mark",
        "email": "test2@cmail.com",
    },
]

# Shared bank accounts
BANK_ACCOUNTS = [
    "HDFC-ACC-001",
    "ICICI-ACC-002",
    "AXIS-ACC-003",
    "SBI-ACC-004",
    "KOTAK-ACC-005",
]

# ──────────────────────────────────────────────────────────────────────────────
# Per-merchant ledger data
# Design:  total_credits − total_debits  = 10,000,000 paise  (₹1,00,000)
#
#   Total credits : 13,500,000 paise  (₹1,35,000)
#   Total debits  :  3,500,000 paise  (₹  35,000)
#   Net balance   : 10,000,000 paise  (₹1,00,000) ✓
# ──────────────────────────────────────────────────────────────────────────────

def _merchant_data(prefix: str):
    """
    Return (credits, success_payouts, failed_payouts) for a merchant.
    `prefix` is a short hex string that keeps all UUIDs unique per merchant.
    """
    credits = [
        {"id": f"{prefix}aaaa-0001-0000-0000-000000000000", "amount": 3_000_000, "label": "Platform earnings Q1"},
        {"id": f"{prefix}aaaa-0002-0000-0000-000000000000", "amount": 2_500_000, "label": "Platform earnings Q2"},
        {"id": f"{prefix}aaaa-0003-0000-0000-000000000000", "amount": 2_000_000, "label": "Platform earnings Q3"},
        {"id": f"{prefix}aaaa-0004-0000-0000-000000000000", "amount": 2_000_000, "label": "Bonus credit"},
        {"id": f"{prefix}aaaa-0005-0000-0000-000000000000", "amount": 1_500_000, "label": "Refund credit"},
        {"id": f"{prefix}aaaa-0006-0000-0000-000000000000", "amount": 2_500_000, "label": "Platform earnings Q4"},
    ]
    # Total credits = 13,500,000

    success_payouts = [
        {
            "payout_id":  f"{prefix}cccc-0001-0000-0000-000000000000",
            "ledger_id":  f"{prefix}bbbb-0001-0000-0000-000000000000",
            "amount":      1_000_000,   # ₹10,000
            "bank_account": BANK_ACCOUNTS[0],
            "days_ago":    30,
        },
        {
            "payout_id":  f"{prefix}cccc-0002-0000-0000-000000000000",
            "ledger_id":  f"{prefix}bbbb-0002-0000-0000-000000000000",
            "amount":        800_000,   # ₹8,000
            "bank_account": BANK_ACCOUNTS[1],
            "days_ago":    21,
        },
        {
            "payout_id":  f"{prefix}cccc-0003-0000-0000-000000000000",
            "ledger_id":  f"{prefix}bbbb-0003-0000-0000-000000000000",
            "amount":        700_000,   # ₹7,000
            "bank_account": BANK_ACCOUNTS[2],
            "days_ago":    14,
        },
        {
            "payout_id":  f"{prefix}cccc-0004-0000-0000-000000000000",
            "ledger_id":  f"{prefix}bbbb-0004-0000-0000-000000000000",
            "amount":        600_000,   # ₹6,000
            "bank_account": BANK_ACCOUNTS[3],
            "days_ago":     7,
        },
        {
            "payout_id":  f"{prefix}cccc-0005-0000-0000-000000000000",
            "ledger_id":  f"{prefix}bbbb-0005-0000-0000-000000000000",
            "amount":        400_000,   # ₹4,000
            "bank_account": BANK_ACCOUNTS[4],
            "days_ago":     3,
        },
    ]
    # Total debits = 3,500,000 → net = 13,500,000 − 3,500,000 = 10,000,000 ✓

    failed_payouts = [
        {
            "payout_id":  f"{prefix}dddd-0001-0000-0000-000000000000",
            "amount":        300_000,   # ₹3,000 — funds NOT debited
            "bank_account": BANK_ACCOUNTS[0],
            "days_ago":    12,
        },
        {
            "payout_id":  f"{prefix}dddd-0002-0000-0000-000000000000",
            "amount":        150_000,   # ₹1,500 — funds NOT debited
            "bank_account": BANK_ACCOUNTS[1],
            "days_ago":     5,
        },
    ]

    return credits, success_payouts, failed_payouts


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"

def _fmt(label: str, value: str, width: int = 44) -> str:
    return f"   {label:<{width}} {value}"


# ──────────────────────────────────────────────────────────────────────────────
# Reset
# ──────────────────────────────────────────────────────────────────────────────

def reset_seed():
    print("── Resetting seed data ──────────────────────────────────")

    emails = [u["email"] for u in USERS]
    m_ids  = [m["id"]    for m in MERCHANTS]

    # Collect all fixed payout / ledger IDs across both merchants
    all_payout_ids = []
    all_ledger_ids = []
    for m in MERCHANTS:
        prefix = m["id"].hex[:4]
        credits, success_payouts, failed_payouts = _merchant_data(prefix)
        all_payout_ids += [uuid.UUID(p["payout_id"]) for p in success_payouts + failed_payouts]
        all_ledger_ids += [uuid.UUID(p["ledger_id"]) for p in success_payouts]
        all_ledger_ids += [uuid.UUID(c["id"])        for c in credits]

    with transaction.atomic():
        l_del, _ = Ledger.objects.filter(id__in=all_ledger_ids).delete()
        p_del, _ = Payout.objects.filter(id__in=all_payout_ids).delete()
        m_del, _ = Merchant.objects.filter(id__in=m_ids).delete()
        u_del, _ = User.objects.filter(username__in=emails).delete()

    print(f"   Deleted {l_del} ledger entries, {p_del} payouts, {m_del} merchant(s), {u_del} user(s)")
    print("── Reset complete ───────────────────────────────────────\n")


# ──────────────────────────────────────────────────────────────────────────────
# Seed
# ──────────────────────────────────────────────────────────────────────────────

def seed(dry_run: bool = False):
    print("── Seeding Playto database ──────────────────────────────")
    if dry_run:
        print("   [DRY RUN] No changes will be written.\n")

    now = timezone.now()

    for user_def, merchant_def in zip(USERS, MERCHANTS):
        email  = user_def["email"]
        name   = user_def["name"]
        prefix = merchant_def["id"].hex[:4]

        print(f"\n── {name} ({email}) ─────────────────────────────────")

        # ── 1. Django User ────────────────────────────────────────────
        if not dry_run:
            user, u_created = User.objects.get_or_create(
                username=email,
                defaults={"email": email, "first_name": name}
            )
            if u_created:
                user.set_password(user_def["password"])
                user.save()
            print(_fmt("User", f"{'created' if u_created else 'already exists'} → {user.username}"))
        else:
            print(_fmt("User", f"[would upsert] {email}"))

        # ── 2. Merchant ───────────────────────────────────────────────
        if not dry_run:
            merchant, m_created = Merchant.objects.update_or_create(
                id=merchant_def["id"],
                defaults={"name": name, "email": email},
            )
            print(_fmt("Merchant", f"{'created' if m_created else 'already exists'} → {merchant}"))
        else:
            print(_fmt("Merchant", f"[would upsert] {name} <{email}>"))
            merchant = None

        credits, success_payouts, failed_payouts = _merchant_data(prefix)

        # ── 3. Credit entries (idempotent) ────────────────────────────
        if not dry_run:
            credit_uuids = [uuid.UUID(c["id"]) for c in credits]
            del_count, _ = Ledger.objects.filter(id__in=credit_uuids).delete()
            if del_count:
                print(_fmt("  Credits cleared", f"{del_count} existing rows removed"))

            for i, c in enumerate(credits):
                entry = Ledger.objects.create(
                    id=uuid.UUID(c["id"]),
                    merchant=merchant,
                    entry_type="CREDIT",
                    amount_paise=c["amount"],
                    payout=None,
                )
                # Spread entries over past 90 days for realistic timeline
                ts = now - timedelta(days=90 - i * 14)
                Ledger.objects.filter(id=entry.id).update(created_at=ts, updated_at=ts)

        total_credits = sum(c["amount"] for c in credits)
        print(_fmt(f"  Credits inserted ({len(credits)})", _rupees(total_credits)))

        # ── 4. Successful payouts + DEBIT ledger entries ───────────────
        total_debits  = 0
        success_count = 0

        for p in success_payouts:
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
                    Payout.objects.filter(id=pid).update(
                        created_at=created_t, updated_at=created_t
                    )

                    Ledger.objects.filter(id=lid).delete()
                    debit = Ledger.objects.create(
                        id=lid,
                        merchant=merchant,
                        entry_type="DEBIT",
                        amount_paise=-p["amount"],
                        payout=payout,
                    )
                    Ledger.objects.filter(id=debit.id).update(
                        created_at=created_t, updated_at=created_t
                    )

            total_debits  += p["amount"]
            success_count += 1

        print(_fmt(f"  SUCCESS payouts inserted ({success_count})", f"−{_rupees(total_debits)}"))

        # ── 5. Failed payouts (no ledger entry) ───────────────────────
        fail_count = 0
        for p in failed_payouts:
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
                Payout.objects.filter(id=pid).update(
                    created_at=created_t, updated_at=created_t
                )
            fail_count += 1

        print(_fmt(f"  FAILED payouts inserted ({fail_count})", "no funds debited"))

        # ── Per-merchant summary ──────────────────────────────────────
        net = total_credits - total_debits
        ledger_rows = len(credits) + success_count  # credits + debit entries
        print()
        print(f"   ┌──────────────────────────────────────────────────┐")
        print(f"   │  Ledger rows   : {ledger_rows:>5} entries                     │")
        print(f"   │  Total Credits : {_rupees(total_credits):>20}           │")
        print(f"   │  Total Debits  : {('−' + _rupees(total_debits)):>21}           │")
        print(f"   │  ─────────────────────────────────────────────── │")
        print(f"   │  Net Balance   : {_rupees(net):>20}           │")
        print(f"   └──────────────────────────────────────────────────┘")

    print()
    print("── Done ─────────────────────────────────────────────────\n")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args       = sys.argv[1:]
    do_reset   = "--reset"   in args
    do_dry_run = "--dry-run" in args

    if do_reset and not do_dry_run:
        reset_seed()

    seed(dry_run=do_dry_run)
