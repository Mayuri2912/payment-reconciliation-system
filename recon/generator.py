"""Synthetic data generator (seeded, repeatable).

Creates a PLATFORM file and a BANK file for one month, plus a MANIFEST that lists exactly what
was planted. The engine never reads the manifest; tests compare the engine output to it.

Data assumptions (also in README):
  * Currency INR, one timezone (IST). Month = November 2026, bank file runs into December.
  * Signed amounts: PAYMENT is positive, REFUND is negative, in both files.
  * Bank amounts are GROSS (no fees in the data).
  * Platform keeps up to 3 decimals for some amounts; the bank rounds each line half-up to 2.
  * Bank settles 1 or 2 business days after the platform date (weekends skipped).
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .calendar_utils import add_business_days, month_end
from .money import round_half_up
from .engine import PLATFORM_COLS, BANK_COLS

CURRENCY = "INR"


def _money(rng: random.Random) -> Decimal:
    return Decimal(rng.randint(10000, 2500000)) / 100  # 100.00 .. 25000.00


def _platform_row(txn_id, when: datetime, txn_type, original, amount: Decimal, status="SUCCESS"):
    return {
        "txn_id": txn_id,
        "timestamp": when.strftime("%Y-%m-%dT%H:%M:%S"),
        "txn_date": when.strftime("%Y-%m-%d"),
        "txn_type": txn_type,
        "original_txn_id": original,
        "amount": str(amount),
        "currency": CURRENCY,
        "status": status,
    }


def generate(seed: int = 42, year: int = 2026, month: int = 11, inject: bool = True,
             n_payments: int = 520, n_refunds: int = 30, n_failed: int = 8,
             n_rounding_lines: int = 120):
    """Return (platform_df, bank_df, manifest). `inject=False` gives a clean month (no planted errors)."""
    rng = random.Random(seed)
    last_day = month_end(year, month).day
    weights = [1 if date(year, month, d).weekday() >= 5 else 4 for d in range(1, last_day + 1)]

    def random_time(day: int, start_hour=8, end_hour=22) -> datetime:
        return datetime(year, month, day, rng.randint(start_hour, end_hour),
                        rng.randint(0, 59), rng.randint(0, 59))

    payments = []  # dicts: when, amount, special
    for _ in range(n_payments):
        day = rng.choices(range(1, last_day + 1), weights=weights)[0]
        payments.append({"when": random_time(day), "amount": _money(rng), "tag": "normal"})

    # Fixed payments near month end so next-month settlement is always demonstrated.
    for day, hour in ((last_day - 3, 16), (last_day, 11), (last_day, 21)):
        payments.append({"when": datetime(year, month, day, hour, rng.randint(0, 59), 0),
                         "amount": _money(rng), "tag": "month_end"})

    payments.sort(key=lambda p: p["when"])
    for i, p in enumerate(payments, start=1):
        p["id"] = f"TXN-{100000 + i}"
        p["lag"] = rng.choice([1, 1, 1, 1, 1, 1, 2, 2, 2, 2])

    eligible = [p for p in payments if p["tag"] == "normal"]
    rng.shuffle(eligible)
    manifest = []

    # Rounding cohort: platform keeps 3 decimals ending in 5, bank rounds half-up (+0.005 each).
    rounding_ids = []
    if inject:
        for p in eligible[:n_rounding_lines]:
            p["amount"] = p["amount"] + Decimal("0.005")
            p["tag"] = "rounding"
            rounding_ids.append(p["id"])
        manifest.append({"type": "ROUNDING_DIFFERENCE", "dataset": "BOTH", "txn_ids": rounding_ids,
                         "expected_lines": len(rounding_ids),
                         "expected_total_difference_bank_minus_platform": str(Decimal("0.005") * len(rounding_ids))})
    pool = [p for p in eligible if p["tag"] == "normal"]

    # Special single cases.
    specials = {}
    if inject:
        duplicate_src = pool.pop()
        mismatch_p = pool.pop()
        mismatch_p["tag"] = "mismatch"
        mismatch_p["amount"] = Decimal("4500.00")
        specials["mismatch"] = mismatch_p
        missing = []
        for _ in range(2):
            m = pool.pop()
            m["tag"] = "missing"
            missing.append(m)
        duplicate_src["tag"] = "duplicate_src"
        specials["duplicate_src"] = duplicate_src
        specials["missing"] = missing
    refund_candidates = [p for p in pool if p["when"].day <= last_day - 8]
    rng.shuffle(refund_candidates)
    refunds = []
    for p in refund_candidates[:n_refunds]:
        p["tag"] = "refunded"
        gap_days = rng.randint(1, 5)
        when = (p["when"] + timedelta(days=gap_days)).replace(hour=rng.randint(10, 19))
        amount = p["amount"] if rng.random() < 0.5 else round_half_up(p["amount"] / 2)
        refunds.append({"when": when, "original": p["id"], "amount": -amount,
                        "lag": rng.choice([1, 1, 2])})
    refunds.sort(key=lambda r: r["when"])
    for i, r in enumerate(refunds, start=1):
        r["id"] = f"REF-{50000 + i}"

    failed_pool = [p for p in pool if p["tag"] == "normal"][:n_failed]
    failed = []
    for i, p in enumerate(failed_pool, start=1):
        failed.append({"id": f"TXN-F{i:04d}", "when": random_time(rng.randint(1, last_day - 3)),
                       "amount": _money(rng)})

    # ---- Build platform rows
    platform_rows = []
    for p in payments:
        platform_rows.append((p["when"], 0, _platform_row(p["id"], p["when"], "PAYMENT", "", p["amount"])))
        if inject and p["tag"] == "duplicate_src":
            platform_rows.append((p["when"], 1, _platform_row(p["id"], p["when"], "PAYMENT", "", p["amount"])))
    for r in refunds:
        platform_rows.append((r["when"], 0, _platform_row(r["id"], r["when"], "REFUND", r["original"], r["amount"])))
    for f in failed:
        platform_rows.append((f["when"], 0, _platform_row(f["id"], f["when"], "PAYMENT", "", f["amount"], "FAILED")))
    orphan = None
    if inject:
        orphan_when = datetime(year, month, 18, 14, 25, 10)
        orphan = {"id": "REF-59001", "when": orphan_when, "original": "TXN-999999",
                  "amount": Decimal("-1850.00"), "lag": 1}
        platform_rows.append((orphan_when, 0, _platform_row(orphan["id"], orphan_when, "REFUND",
                                                            orphan["original"], orphan["amount"])))
    platform_rows.sort(key=lambda x: (x[0], x[1]))
    platform_df = pd.DataFrame([r for _, _, r in platform_rows], columns=PLATFORM_COLS)

    # ---- Build bank rows
    bank_items = []  # (settlement_date, txn_id, amount)
    missing_ids = {m["id"] for m in specials.get("missing", [])}
    for p in payments:
        if p["id"] in missing_ids:
            continue
        settle = add_business_days(p["when"].date(), p["lag"])
        amount = p["amount"]
        if p["tag"] == "rounding":
            amount = round_half_up(amount)
        if p["tag"] == "mismatch":
            amount = Decimal("450.00")
        bank_items.append((settle, p["id"], amount))
    for r in refunds + ([orphan] if orphan else []):
        settle = add_business_days(r["when"].date(), r["lag"])
        bank_items.append((settle, r["id"], r["amount"]))
    if inject:
        bank_items.append((date(year, month, 13), "TXN-EXT-0001", Decimal("2750.00")))
        bank_items.append((date(year, month, 20), "TXN-EXT-0002", Decimal("1180.50")))
    bank_items.sort(key=lambda x: (x[0], x[1]))
    bank_rows = []
    for n, (settle, txn_id, amount) in enumerate(bank_items, start=1):
        bank_rows.append({
            "settlement_id": f"SETL-{n:06d}",
            "txn_id": txn_id,
            "settlement_date": settle.strftime("%Y-%m-%d"),
            "amount": str(amount),
            "batch_id": f"BATCH-{settle.strftime('%Y%m%d')}-01",
            "currency": CURRENCY,
            "status": "SETTLED",
        })
    bank_df = pd.DataFrame(bank_rows, columns=BANK_COLS)

    # ---- Manifest (ground truth for tests only)
    period_end = month_end(year, month)
    next_month_ids = [txn_id for settle, txn_id, _ in bank_items
                      if settle > period_end and not txn_id.startswith("TXN-EXT")]
    manifest.insert(0, {"type": "NEXT_MONTH_SETTLEMENT", "dataset": "BANK", "txn_ids": next_month_ids})
    if inject:
        manifest.append({"type": "DUPLICATE_ENTRY", "dataset": "PLATFORM",
                         "txn_ids": [specials["duplicate_src"]["id"]],
                         "amount": str(specials["duplicate_src"]["amount"])})
        manifest.append({"type": "ORPHAN_REFUND", "dataset": "PLATFORM", "txn_ids": [orphan["id"]],
                         "missing_original": orphan["original"], "amount": str(orphan["amount"])})
        manifest.append({"type": "AMOUNT_MISMATCH", "dataset": "BOTH",
                         "txn_ids": [specials["mismatch"]["id"]], "platform": "4500.00", "bank": "450.00"})
        manifest.append({"type": "MISSING_SETTLEMENT", "dataset": "BANK",
                         "txn_ids": [m["id"] for m in specials["missing"]]})
        manifest.append({"type": "UNEXPECTED_BANK_TXN", "dataset": "BANK",
                         "txn_ids": ["TXN-EXT-0001", "TXN-EXT-0002"]})
    manifest.append({"type": "EXPECTED_NO_SETTLEMENT", "dataset": "PLATFORM",
                     "txn_ids": [f["id"] for f in failed], "note": "FAILED payments never settle (legitimate)"})
    return platform_df, bank_df, manifest


def save_dataset(platform_df, bank_df, manifest, directory) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    platform_df.to_csv(directory / "platform_transactions.csv", index=False)
    bank_df.to_csv(directory / "bank_settlements.csv", index=False)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic platform and bank CSV files")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/sample")
    parser.add_argument("--clean", action="store_true", help="no planted discrepancies")
    args = parser.parse_args()
    p, b, m = generate(seed=args.seed, inject=not args.clean)
    save_dataset(p, b, m, args.out)
    print(f"platform rows: {len(p)}, bank rows: {len(b)} -> {args.out}")


if __name__ == "__main__":
    main()
