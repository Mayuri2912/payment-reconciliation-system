"""Reconciliation engine. Pure Python + pandas input, Decimal money, no web code.

Sign convention (both files): PAYMENT amounts are positive, REFUND amounts are negative.
Difference convention:  difference = platform_amount - bank_amount.
"Month-end impact" (bridge_effect) = how much the row moves the November totals gap
(platform net total minus bank net total for settlements dated inside the month).

Every record is put in exactly ONE bucket, so the bridge
    platform total - bank total = sum(bridge effects) + unexplained residual
can be checked. On a healthy run the residual is exactly 0.00.
"""
from __future__ import annotations

import calendar
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from .calendar_utils import add_business_days
from .money import ZERO, parse_amount, round_half_up

PLATFORM_COLS = ["txn_id", "timestamp", "txn_date", "txn_type", "original_txn_id",
                 "amount", "currency", "status"]
BANK_COLS = ["settlement_id", "txn_id", "settlement_date", "amount", "batch_id", "currency", "status"]
PLATFORM_REQUIRED = ["txn_id", "txn_type", "amount", "status"]
BANK_REQUIRED = ["settlement_id", "txn_id", "settlement_date", "amount"]

CATEGORY_INFO = {
    "NEXT_MONTH_SETTLEMENT": {
        "title": "Next-month settlements", "mandatory": True, "severity": "INFO",
        "description": "Recorded by the platform inside the month but settled by the bank after month end. "
                       "The money is not lost: it is a timing difference and clears in the next month's bank data."},
    "ROUNDING_DIFFERENCE": {
        "title": "Rounding differences", "mandatory": True, "severity": "LOW",
        "description": "Platform amounts carry 3 decimals; the bank rounds each line to 2 decimals (half-up). "
                       "Each line differs by less than the tolerance, so lines still match, but the small "
                       "differences add up in the month total."},
    "DUPLICATE_ENTRY": {
        "title": "Duplicate entries", "mandatory": True, "severity": "HIGH",
        "description": "The same transaction ID appears more than once in one dataset. The first record is kept "
                       "and the extra copies are excluded from totals (but kept in the audit list)."},
    "ORPHAN_REFUND": {
        "title": "Orphan refunds", "mandatory": True, "severity": "HIGH",
        "description": "A refund whose original payment cannot be found in the platform data. Money may have "
                       "been returned for a sale that never happened, or the original is outside our data."},
    "MISSING_SETTLEMENT": {
        "title": "Missing settlements", "mandatory": False, "severity": "HIGH",
        "description": "Successful platform transaction with no bank record even after the allowed settlement "
                       "window and grace days. Needs follow-up with the bank."},
    "UNEXPECTED_BANK_TXN": {
        "title": "Unexpected bank transactions", "mandatory": False, "severity": "HIGH",
        "description": "Bank record whose transaction ID is not a successful transaction in the platform data."},
    "AMOUNT_MISMATCH": {
        "title": "Amount mismatches", "mandatory": False, "severity": "HIGH",
        "description": "Matched by ID but the amounts differ by more than the rounding tolerance."},
    "IN_TRANSIT": {
        "title": "In transit (not yet due)", "mandatory": False, "severity": "INFO",
        "description": "No bank record yet, but the bank file does not cover the full settlement window, "
                       "so we cannot call it missing."},
    "INVALID_RECORD": {
        "title": "Invalid records", "mandatory": False, "severity": "HIGH",
        "description": "Rows that could not be read (bad amount, date, type, status or sign). They are "
                       "quarantined and excluded from all totals."},
}
ACTIONABLE = {"DUPLICATE_ENTRY", "ORPHAN_REFUND", "MISSING_SETTLEMENT", "UNEXPECTED_BANK_TXN",
              "AMOUNT_MISMATCH", "INVALID_RECORD"}


class ReconError(ValueError):
    """Raised when an input file has the wrong shape (for example a missing column)."""


@dataclass
class ReconConfig:
    tolerance: Decimal = Decimal("0.01")      # max per-line difference still treated as rounding
    period_end: Optional[date] = None         # default: last day of the most common platform month
    lookahead_days: int = 5                   # bank file is assumed to cover this many days past month end
    max_settle_days: int = 2                  # bank settles within T+2 business days
    grace_days: int = 1                       # extra business day before calling something missing


@dataclass
class ReconResult:
    config: ReconConfig
    period_start: Optional[date]
    period_end: Optional[date]
    summary: dict
    bridge: list
    discrepancies: list
    platform_rows: list
    bank_rows: list
    invalid: list
    rounding: dict
    observations: list
    status: str

    def counts_by_category(self) -> dict:
        counter = Counter(d["category"] for d in self.discrepancies)
        return dict(counter)


# ----------------------------------------------------------------------------- input handling
def _records(df, required, name):
    if df is None or len(df) == 0:
        return []
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ReconError(f"{name} data is missing required column(s): {', '.join(missing)}")
    rows = []
    for rec in df.to_dict("records"):
        rows.append({k: ("" if pd.isna(v) else str(v).strip()) for k, v in rec.items()})
    return rows


def _parse_platform(records):
    valid, invalid = [], []
    if records and "txn_date" not in records[0] and "timestamp" not in records[0]:
        raise ReconError("platform data needs a txn_date or timestamp column")
    for row_no, r in enumerate(records, start=2):  # row 1 is the CSV header
        problems = []
        txn_id = r.get("txn_id", "")
        if not txn_id:
            problems.append("missing txn_id")
        txn_type = r.get("txn_type", "").upper()
        if txn_type not in ("PAYMENT", "REFUND"):
            problems.append(f"unknown txn_type '{r.get('txn_type', '')}'")
        status = r.get("status", "").upper()
        if status not in ("SUCCESS", "FAILED"):
            problems.append(f"unknown status '{r.get('status', '')}'")
        amount = None
        try:
            amount = parse_amount(r.get("amount", ""))
        except ValueError as exc:
            problems.append(str(exc))
        if amount is not None and txn_type == "PAYMENT" and amount <= 0:
            problems.append("PAYMENT amount must be positive")
        if amount is not None and txn_type == "REFUND" and amount >= 0:
            problems.append("REFUND amount must be negative")
        raw_date = r.get("txn_date", "") or r.get("timestamp", "")[:10]
        txn_date = None
        try:
            txn_date = date.fromisoformat(raw_date[:10])
        except ValueError:
            problems.append(f"invalid date '{raw_date}'")
        if problems:
            invalid.append({"dataset": "PLATFORM", "row_no": row_no, "record": r,
                            "txn_id": txn_id, "problems": "; ".join(problems)})
            continue
        valid.append({"row_no": row_no, "txn_id": txn_id, "timestamp": r.get("timestamp", ""),
                      "txn_date": txn_date, "txn_type": txn_type,
                      "original_txn_id": r.get("original_txn_id", ""), "amount": amount,
                      "currency": r.get("currency", "") or "INR", "status": status})
    return valid, invalid


def _parse_bank(records):
    valid, invalid = [], []
    for row_no, r in enumerate(records, start=2):
        problems = []
        txn_id = r.get("txn_id", "")
        if not txn_id:
            problems.append("missing txn_id")
        if not r.get("settlement_id", ""):
            problems.append("missing settlement_id")
        amount = None
        try:
            amount = parse_amount(r.get("amount", ""))
        except ValueError as exc:
            problems.append(str(exc))
        settle = None
        try:
            settle = date.fromisoformat(r.get("settlement_date", "")[:10])
        except ValueError:
            problems.append(f"invalid settlement_date '{r.get('settlement_date', '')}'")
        status = (r.get("status", "") or "SETTLED").upper()
        if status != "SETTLED":
            problems.append(f"unsupported settlement status '{status}'")
        if problems:
            invalid.append({"dataset": "BANK", "row_no": row_no, "record": r,
                            "txn_id": txn_id, "problems": "; ".join(problems)})
            continue
        valid.append({"row_no": row_no, "settlement_id": r["settlement_id"], "txn_id": txn_id,
                      "settlement_date": settle, "amount": amount,
                      "batch_id": r.get("batch_id", ""), "currency": r.get("currency", "") or "INR",
                      "status": status})
    return valid, invalid


def _infer_period_end(platform_valid, bank_valid) -> Optional[date]:
    dates = [r["txn_date"] for r in platform_valid] or [r["settlement_date"] for r in bank_valid]
    if not dates:
        return None
    (year, month), _ = Counter((d.year, d.month) for d in dates).most_common(1)[0]
    return date(year, month, calendar.monthrange(year, month)[1])


def _disc(category, dataset, txn_id, settlement_id, txn_type, platform_date, settlement_date,
          platform_amount, bank_amount, bridge_effect, explanation, action):
    info = CATEGORY_INFO[category]
    return {
        "category": category, "title": info["title"], "severity": info["severity"],
        "mandatory": info["mandatory"], "dataset": dataset, "txn_id": txn_id,
        "settlement_id": settlement_id, "txn_type": txn_type,
        "platform_date": platform_date, "settlement_date": settlement_date,
        "expected_amount": platform_amount, "actual_amount": bank_amount,
        "difference": platform_amount - bank_amount, "bridge_effect": bridge_effect,
        "explanation": explanation, "suggested_action": action,
    }


# ----------------------------------------------------------------------------- main entry
def reconcile(platform_df, bank_df, config: Optional[ReconConfig] = None) -> ReconResult:
    cfg = config or ReconConfig()
    p_records = _records(platform_df, PLATFORM_REQUIRED, "platform")
    b_records = _records(bank_df, BANK_REQUIRED, "bank")
    p_valid, p_invalid = _parse_platform(p_records)
    b_valid, b_invalid = _parse_bank(b_records)

    period_end = cfg.period_end or _infer_period_end(p_valid, b_valid)
    period_start = period_end.replace(day=1) if period_end else None
    coverage_end = period_end + timedelta(days=cfg.lookahead_days) if period_end else None

    def in_period(d: date) -> bool:
        return period_start is not None and period_start <= d <= period_end

    discrepancies: list = []

    # ---- 1. duplicates (platform), by transaction ID, first record kept in file order
    first_p, p_id_rows = {}, {}
    for r in p_valid:
        p_id_rows.setdefault(r["txn_id"], []).append(r)
        r["is_duplicate"] = r["txn_id"] in first_p
        if not r["is_duplicate"]:
            first_p[r["txn_id"]] = r
    first_b, b_id_rows = {}, {}
    for r in b_valid:
        b_id_rows.setdefault(r["txn_id"], []).append(r)
        r["is_duplicate"] = r["txn_id"] in first_b
        if not r["is_duplicate"]:
            first_b[r["txn_id"]] = r

    # ---- 2. platform records: classify each into exactly one bucket
    platform_payments = platform_refunds = ZERO
    for r in p_valid:
        r["in_totals"] = r["status"] == "SUCCESS" and in_period(r["txn_date"])
        if r["in_totals"]:
            if r["txn_type"] == "PAYMENT":
                platform_payments += r["amount"]
            else:
                platform_refunds += r["amount"]
        r["bank"] = None
        r["note"] = ""

    matched_p = []              # (platform row, bank row)
    rounding_rows, mismatch_rows = [], []
    bridge = {k: {"count": 0, "amount": ZERO} for k in (
        "DUPLICATE_PLATFORM", "DUPLICATE_BANK", "NEXT_MONTH", "ROUNDING", "AMOUNT_MISMATCH",
        "MISSING", "IN_TRANSIT", "UNEXPECTED_BANK")}

    def add_bridge(key, amount):
        bridge[key]["count"] += 1
        bridge[key]["amount"] += amount

    for r in p_valid:
        if r["is_duplicate"]:
            r["match_status"] = "DUPLICATE (excluded)"
            original = first_p[r["txn_id"]]
            same = (original["amount"] == r["amount"] and original["timestamp"] == r["timestamp"]
                    and original["txn_type"] == r["txn_type"])
            how = ("identical to the first record (same amount, type and timestamp)" if same
                   else "different from the first record, so the copies conflict")
            effect = r["amount"] if r["in_totals"] else ZERO
            if r["in_totals"]:
                add_bridge("DUPLICATE_PLATFORM", effect)
            discrepancies.append(_disc(
                "DUPLICATE_ENTRY", "PLATFORM", r["txn_id"], "", r["txn_type"], r["txn_date"], None,
                r["amount"], ZERO, effect,
                f"Transaction ID {r['txn_id']} appears {len(p_id_rows[r['txn_id']])} times in the platform "
                f"dataset (file rows {', '.join(str(x['row_no']) for x in p_id_rows[r['txn_id']])}). "
                f"Row {r['row_no']} is {how}. The first record is kept; this copy is excluded from totals.",
                "Check the platform ingestion or retry logic. Remove the extra copy after confirming it "
                "was not a real second payment."))
            continue
        if not in_period(r["txn_date"]):
            r["match_status"] = "OUT OF PERIOD"
            continue
        if r["status"] == "FAILED":
            r["match_status"] = "NO SETTLEMENT EXPECTED"
            r["note"] = "Failed platform transaction: not expected at the bank."
            continue
        b = first_b.get(r["txn_id"])
        if b is None:
            latest = add_business_days(r["txn_date"], cfg.max_settle_days + cfg.grace_days)
            r["expected_by"] = latest
            if latest <= coverage_end:
                r["match_status"] = "MISSING SETTLEMENT"
                add_bridge("MISSING", r["amount"])
                discrepancies.append(_disc(
                    "MISSING_SETTLEMENT", "BANK", r["txn_id"], "", r["txn_type"], r["txn_date"], None,
                    r["amount"], ZERO, r["amount"],
                    f"No bank record found. Expected by {latest} (T+{cfg.max_settle_days} business days plus "
                    f"{cfg.grace_days} grace day) and the bank file covers up to {coverage_end}.",
                    "Raise a query with the bank for this transaction ID."))
            else:
                r["match_status"] = "IN TRANSIT"
                add_bridge("IN_TRANSIT", r["amount"])
                discrepancies.append(_disc(
                    "IN_TRANSIT", "BANK", r["txn_id"], "", r["txn_type"], r["txn_date"], None,
                    r["amount"], ZERO, r["amount"],
                    f"No bank record yet. Settlement is due by {latest}, which is after the bank file "
                    f"coverage ({coverage_end}), so it cannot be called missing.",
                    "Re-check when the next bank file arrives."))
            continue
        r["bank"] = b
        if b["settlement_date"] > period_end:
            r["match_status"] = "MATCHED - NEXT MONTH"
            add_bridge("NEXT_MONTH", r["amount"])
            days = (b["settlement_date"] - r["txn_date"]).days
            discrepancies.append(_disc(
                "NEXT_MONTH_SETTLEMENT", "BANK", r["txn_id"], b["settlement_id"], r["txn_type"],
                r["txn_date"], b["settlement_date"], r["amount"], b["amount"], r["amount"],
                f"Platform date {r['txn_date']} is in {period_start:%B}; the bank settled it on "
                f"{b['settlement_date']} ({days} calendar days later) which is in the next month. The amounts "
                f"{'agree' if r['amount'] == b['amount'] else 'differ (' + str(b['amount']) + ' at bank)'}. "
                f"It is a timing difference, not a missing payment.",
                "No correction needed. Carry it forward as a reconciling item for the month-end report."))
            continue
        delta = b["amount"] - r["amount"]  # bank minus platform
        r["delta"] = delta
        matched_p.append((r, b))
        if delta == 0:
            r["match_status"] = "MATCHED"
        elif abs(delta) <= cfg.tolerance:
            r["match_status"] = "MATCHED - ROUNDING"
            rounding_rows.append((r, b, delta))
            add_bridge("ROUNDING", -delta)
            discrepancies.append(_disc(
                "ROUNDING_DIFFERENCE", "BOTH", r["txn_id"], b["settlement_id"], r["txn_type"],
                r["txn_date"], b["settlement_date"], r["amount"], b["amount"], -delta,
                f"Platform {r['amount']} vs bank {b['amount']}: line difference {delta:+} is within the "
                f"tolerance of {cfg.tolerance}, so the line is matched. Bank amount "
                f"{'equals' if round_half_up(r['amount']) == b['amount'] else 'does not equal'} the platform "
                f"amount rounded half-up to 2 decimals. Lines like this add up in the month total.",
                "Agree one rounding rule (where and how) with the bank and book the total as a rounding item."))
        else:
            r["match_status"] = "AMOUNT MISMATCH"
            mismatch_rows.append((r, b, delta))
            add_bridge("AMOUNT_MISMATCH", -delta)
            discrepancies.append(_disc(
                "AMOUNT_MISMATCH", "BOTH", r["txn_id"], b["settlement_id"], r["txn_type"],
                r["txn_date"], b["settlement_date"], r["amount"], b["amount"], -delta,
                f"Platform {r['amount']} vs bank {b['amount']}: difference {delta:+} is larger than the "
                f"tolerance of {cfg.tolerance}, so this is not rounding.",
                "Check the source of the amount (typo, partial settlement, fee) and correct the wrong side."))

    # ---- 3. orphan refunds (reusable check on the clean platform records)
    for r in p_valid:
        if r["is_duplicate"] or r["txn_type"] != "REFUND":
            continue
        ref = r["original_txn_id"]
        original = first_p.get(ref) if ref else None
        reason = None
        if not ref:
            reason = "the refund has no original transaction reference"
        elif original is None:
            reason = f"original transaction {ref} does not exist in the platform dataset"
        elif original["txn_type"] != "PAYMENT":
            reason = f"referenced transaction {ref} is a {original['txn_type']}, not a payment"
        elif original["status"] != "SUCCESS":
            reason = f"original payment {ref} has status {original['status']}, so there was nothing to refund"
        if reason:
            b = r.get("bank") or first_b.get(r["txn_id"])
            bank_amount = b["amount"] if b and in_period(b["settlement_date"]) else ZERO
            r["note"] = "Orphan refund: " + reason
            discrepancies.append(_disc(
                "ORPHAN_REFUND", "PLATFORM", r["txn_id"], b["settlement_id"] if b else "", "REFUND",
                r["txn_date"], b["settlement_date"] if b else None, r["amount"], bank_amount, ZERO,
                f"Refund {r['txn_id']} cannot be matched to a payment: {reason}. "
                f"{'The bank also paid it out (' + str(b['amount']) + ' on ' + str(b['settlement_date']) + '), so ' + str(abs(r['amount'])) + ' left the company without a supporting sale.' if b else 'It has not been settled by the bank.'}",
                "Find the original payment (it may be in an older month). If none exists, treat as an "
                "unauthorised or erroneous refund and escalate."))

    # ---- 4. bank records
    bank_payments = bank_refunds = ZERO
    matched_ids = {r["txn_id"] for r in p_valid
                   if r.get("bank") is not None and not r["is_duplicate"]}
    bank_rows_out = []
    for b in b_valid:
        b["in_totals"] = in_period(b["settlement_date"])
        if b["in_totals"]:
            if b["amount"] >= 0:
                bank_payments += b["amount"]
            else:
                bank_refunds += b["amount"]
        b["platform"] = first_p.get(b["txn_id"])
        if b["is_duplicate"]:
            b["match_status"] = "DUPLICATE (excluded)"
            effect = -b["amount"] if b["in_totals"] else ZERO
            if b["in_totals"]:
                add_bridge("DUPLICATE_BANK", effect)
            discrepancies.append(_disc(
                "DUPLICATE_ENTRY", "BANK", b["txn_id"], b["settlement_id"], "", None, b["settlement_date"],
                ZERO, b["amount"], effect,
                f"Transaction ID {b['txn_id']} appears {len(b_id_rows[b['txn_id']])} times in the bank dataset "
                f"(file rows {', '.join(str(x['row_no']) for x in b_id_rows[b['txn_id']])}). "
                f"Settlement {b['settlement_id']} is a repeat and is excluded from clean totals.",
                "Ask the bank whether it paid twice or the file was loaded twice; reclaim if paid twice."))
        elif b["txn_id"] in matched_ids:
            p = first_p[b["txn_id"]]
            b["match_status"] = ("MATCHED - NEXT MONTH" if b["settlement_date"] > period_end
                                 else p["match_status"])
        else:
            p = first_p.get(b["txn_id"])
            if p is None:
                why = "its transaction ID is not in the platform dataset"
            elif p["status"] == "FAILED":
                why = "the platform marks this transaction FAILED, but the bank paid it"
            elif not in_period(p["txn_date"]):
                why = f"the platform transaction is dated {p['txn_date']}, outside the reconciliation period"
            else:
                why = "no matching platform record could be used"
            b["match_status"] = "UNEXPECTED"
            effect = -b["amount"] if b["in_totals"] else ZERO
            if b["in_totals"]:
                add_bridge("UNEXPECTED_BANK", effect)
            discrepancies.append(_disc(
                "UNEXPECTED_BANK_TXN", "BANK", b["txn_id"], b["settlement_id"], "", None,
                b["settlement_date"], ZERO, b["amount"], effect,
                f"Bank settlement {b['settlement_id']} on {b['settlement_date']} for {b['amount']}: {why}. "
                f"It could also be a prior-month carry-in or a wrongly credited amount."
                + ("" if b["in_totals"] else " It is dated outside the period, so it does not move the totals."),
                "Identify the payer. If it is a prior-month payment, record it as a carry-in; otherwise "
                "ask the bank to investigate."))

    # ---- 5. invalid records go to the report too
    for inv in p_invalid + b_invalid:
        discrepancies.append(_disc(
            "INVALID_RECORD", inv["dataset"], inv["txn_id"], "", "", None, None, ZERO, ZERO, ZERO,
            f"File row {inv['row_no']} was rejected: {inv['problems']}. Excluded from all totals.",
            "Correct the source row and load it again."))

    # ---- 6. rounding analysis (transaction-level versus aggregate-level)
    line_delta = sum((d for _, _, d in rounding_rows), ZERO)
    platform_sum = sum((r["amount"] for r, _, _ in rounding_rows), ZERO)
    bank_sum = sum((b["amount"] for _, b, _ in rounding_rows), ZERO)
    rounding = {
        "lines": len(rounding_rows),
        "tolerance": cfg.tolerance,
        "rounding_rule": "ROUND_HALF_UP to 2 decimals, applied by the bank to each line",
        "platform_sum": platform_sum,
        "bank_sum": bank_sum,
        "aggregate_difference": line_delta,                       # bank minus platform, sum of line deltas
        "max_line_difference": max((abs(d) for _, _, d in rounding_rows), default=ZERO),
        "lines_equal_to_half_up": sum(1 for r, b, _ in rounding_rows if round_half_up(r["amount"]) == b["amount"]),
        "round_once_on_total": round_half_up(platform_sum),
        # If the bank had rounded only the TOTAL once, the effect would be this small:
        "difference_if_rounded_once": round_half_up(platform_sum) - platform_sum,
        "largest_single_line": max((abs(d) for _, _, d in rounding_rows), default=ZERO),
    }

    # ---- 7. totals, bridge, status
    platform_net_raw = platform_payments + platform_refunds
    bank_net_raw = bank_payments + bank_refunds
    raw_gap = platform_net_raw - bank_net_raw
    dup_platform = bridge["DUPLICATE_PLATFORM"]["amount"]
    dup_bank = -bridge["DUPLICATE_BANK"]["amount"]
    explained = sum((v["amount"] for v in bridge.values()), ZERO)
    residual = raw_gap - explained
    matched_platform_amount = sum((r["amount"] for r, _ in matched_p), ZERO)
    matched_bank_amount = sum((b["amount"] for _, b in matched_p), ZERO)
    unmatched_keys = ("NEXT_MONTH", "MISSING", "IN_TRANSIT")
    unmatched_platform_count = sum(bridge[k]["count"] for k in unmatched_keys)
    unmatched_platform_amount = sum((bridge[k]["amount"] for k in unmatched_keys), ZERO)
    gross_discrepancy_amount = sum((abs(d["bridge_effect"]) for d in discrepancies), ZERO)
    actionable = [d for d in discrepancies if d["category"] in ACTIONABLE]

    summary = {
        "platform_records": len(p_records), "bank_records": len(b_records),
        "platform_valid": len(p_valid), "bank_valid": len(b_valid),
        "invalid_records": len(p_invalid) + len(b_invalid),
        "platform_payments_total": platform_payments, "platform_refunds_total": platform_refunds,
        "platform_net_total": platform_net_raw,
        "bank_payments_total": bank_payments, "bank_refunds_total": bank_refunds,
        "bank_net_total": bank_net_raw,
        "matched_count": len(matched_p), "matched_platform_amount": matched_platform_amount,
        "matched_bank_amount": matched_bank_amount,
        "unmatched_platform_count": unmatched_platform_count,
        "unmatched_platform_amount": unmatched_platform_amount,
        "unexpected_bank_count": bridge["UNEXPECTED_BANK"]["count"],
        "duplicate_amount_excluded_platform": dup_platform,
        "duplicate_amount_excluded_bank": dup_bank,
        "duplicate_amount_excluded": dup_platform + dup_bank,
        "platform_net_clean": platform_net_raw - dup_platform,
        "bank_net_clean": bank_net_raw - dup_bank,
        "aggregate_difference_raw": raw_gap,
        "aggregate_difference_clean": (platform_net_raw - dup_platform) - (bank_net_raw - dup_bank),
        "explained_difference": explained,
        "unexplained_residual": residual,
        "discrepancy_count": len(discrepancies),
        "actionable_count": len(actionable),
        "gross_discrepancy_amount": gross_discrepancy_amount,
        "failed_platform_count": sum(1 for r in p_valid if r["status"] == "FAILED" and not r["is_duplicate"]),
        "settlement_basis": "GROSS (no fees in the data)",
    }

    labels = {
        "DUPLICATE_PLATFORM": "Duplicate entries in platform data",
        "DUPLICATE_BANK": "Duplicate entries in bank data",
        "NEXT_MONTH": "Settled next month (timing)",
        "ROUNDING": "Rounding differences (sum of lines)",
        "AMOUNT_MISMATCH": "Amount mismatches",
        "MISSING": "Missing settlements",
        "IN_TRANSIT": "In transit (not yet due)",
        "UNEXPECTED_BANK": "Unexpected bank transactions",
    }
    bridge_list = [{"key": k, "label": labels[k], "count": v["count"], "amount": v["amount"]}
                   for k, v in bridge.items()]

    if not p_records and not b_records:
        status = "NO DATA"
    elif residual != 0:
        status = "UNEXPLAINED DIFFERENCE"
    elif actionable:
        status = "EXPLAINED - ACTION REQUIRED"
    else:
        status = "RECONCILED"

    observations = []
    if status == "NO DATA":
        observations.append("No records were provided.")
    else:
        observations.append(
            f"Raw platform net total {platform_net_raw:,.3f} vs bank net total {bank_net_raw:,.3f}: "
            f"gap {raw_gap:,.3f}. Explained by the items below: {explained:,.3f}. "
            f"Unexplained residual: {residual:,.3f}.")
        if bridge["NEXT_MONTH"]["count"]:
            observations.append(
                f"{bridge['NEXT_MONTH']['count']} transaction(s) worth {bridge['NEXT_MONTH']['amount']:,.2f} settled "
                f"after month end. This is timing and should clear next month.")
        if rounding["lines"]:
            observations.append(
                f"{rounding['lines']} lines differ by rounding. Each line is at most {rounding['max_line_difference']}, "
                f"but together they add {rounding['aggregate_difference']:+} to the bank total. Rounding only the "
                f"total once would have changed it by just {rounding['difference_if_rounded_once']:+}; the gap "
                f"comes from rounding every line.")
        if dup_platform or dup_bank:
            observations.append(
                f"Duplicate entries worth {dup_platform + dup_bank:,.2f} were excluded from the clean totals.")
        orphans = [d for d in discrepancies if d["category"] == "ORPHAN_REFUND"]
        if orphans:
            observations.append(f"{len(orphans)} orphan refund(s) worth {sum((abs(d['expected_amount']) for d in orphans), ZERO):,.2f} "
                                f"have no valid original payment.")
        if bridge["MISSING"]["count"] or bridge["UNEXPECTED_BANK"]["count"]:
            observations.append(
                f"{bridge['MISSING']['count']} missing settlement(s) and {bridge['UNEXPECTED_BANK']['count']} "
                f"unexpected bank record(s) need follow-up.")
        if summary["failed_platform_count"]:
            observations.append(
                f"{summary['failed_platform_count']} FAILED platform transaction(s) have no bank record. "
                f"This is expected and not counted as missing.")

    return ReconResult(
        config=cfg, period_start=period_start, period_end=period_end, summary=summary,
        bridge=bridge_list, discrepancies=discrepancies,
        platform_rows=p_valid, bank_rows=b_valid, invalid=p_invalid + b_invalid,
        rounding=rounding, observations=observations, status=status)
