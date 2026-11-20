from decimal import Decimal as D

import pandas as pd

from recon.engine import ReconConfig, reconcile
from recon.generator import generate


def plat(txn_id, day, amount, typ="PAYMENT", orig="", status="SUCCESS"):
    return dict(txn_id=txn_id, timestamp=f"{day}T12:00:00", txn_date=day, txn_type=typ,
                original_txn_id=orig, amount=str(amount), currency="INR", status=status)


def bank(sid, txn_id, day, amount):
    return dict(settlement_id=sid, txn_id=txn_id, settlement_date=day, amount=str(amount),
                batch_id="B1", currency="INR", status="SETTLED")


def run(p, b, **cfg):
    return reconcile(pd.DataFrame(p), pd.DataFrame(b), ReconConfig(**cfg) if cfg else None)


def cats(result, name):
    return [d for d in result.discrepancies if d["category"] == name]


def test_tc01_exact_matching(actual):
    """ID: TC-01
    Objective: Payments with identical amounts on both sides are matched and nothing is flagged
    Input: 3 payments in Nov, 3 bank lines in Nov, same IDs and amounts
    Expected: 3 matched, no discrepancies, residual 0, status RECONCILED"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("T2", "2026-11-04", "250.50"), plat("T3", "2026-11-05", "75.25")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "T2", "2026-11-05", "250.50"),
         bank("S3", "T3", "2026-11-06", "75.25")]
    r = run(p, b)
    actual.append(f"matched={r.summary['matched_count']}, discrepancies={len(r.discrepancies)}, "
                  f"residual={r.summary['unexplained_residual']}, status={r.status}")
    assert r.summary["matched_count"] == 3 and not r.discrepancies
    assert r.summary["unexplained_residual"] == 0 and r.status == "RECONCILED"


def test_tc02_next_month_settlement(actual):
    """ID: TC-02
    Objective: Detect a November transaction that settles in December and treat it as timing, not missing
    Input: payment 2026-11-30 (500.00), bank settlement 2026-12-01; plus one normal payment
    Expected: one NEXT_MONTH_SETTLEMENT row, zero MISSING rows, month-end impact 500.00, residual 0"""
    p = [plat("T1", "2026-11-30", "500.00"), plat("T2", "2026-11-10", "40.00")]
    b = [bank("S1", "T1", "2026-12-01", "500.00"), bank("S2", "T2", "2026-11-11", "40.00")]
    r = run(p, b)
    row = cats(r, "NEXT_MONTH_SETTLEMENT")[0]
    actual.append(f"next_month={len(cats(r, 'NEXT_MONTH_SETTLEMENT'))}, missing={len(cats(r, 'MISSING_SETTLEMENT'))}, "
                  f"platform_date={row['platform_date']}, settlement_date={row['settlement_date']}, "
                  f"impact={row['bridge_effect']}, residual={r.summary['unexplained_residual']}")
    assert len(cats(r, "NEXT_MONTH_SETTLEMENT")) == 1 and not cats(r, "MISSING_SETTLEMENT")
    assert row["bridge_effect"] == D("500.00") and r.summary["unexplained_residual"] == 0


def test_tc03_aggregate_rounding(actual):
    """ID: TC-03
    Objective: Per-line differences pass the tolerance but add up in the total
    Input: 100 payments of x.xx5 on the platform; bank rounds each line half-up to 2 decimals
    Expected: 100 rounding lines, each 0.005, aggregate 0.500, no amount mismatches, residual 0"""
    p, b = [], []
    for i in range(100):
        amount = D("10.005") + i
        p.append(plat(f"T{i}", "2026-11-03", amount))
        b.append(bank(f"S{i}", f"T{i}", "2026-11-04", amount.quantize(D("0.01"), rounding="ROUND_HALF_UP")))
    r = run(p, b)
    rd = r.rounding
    actual.append(f"lines={rd['lines']}, max_line={rd['max_line_difference']}, aggregate={rd['aggregate_difference']}, "
                  f"if_rounded_once={rd['difference_if_rounded_once']}, residual={r.summary['unexplained_residual']}")
    assert rd["lines"] == 100 and rd["max_line_difference"] == D("0.005")
    assert rd["aggregate_difference"] == D("0.500") and not cats(r, "AMOUNT_MISMATCH")
    assert rd["lines_equal_to_half_up"] == 100 and r.summary["unexplained_residual"] == 0


def test_tc04_duplicate_in_platform(actual):
    """ID: TC-04
    Objective: Detect a duplicate transaction ID in the platform dataset
    Input: platform has T1 twice (same amount), bank has T1 once
    Expected: one DUPLICATE_ENTRY row, dataset PLATFORM, 2nd copy excluded, residual 0"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("T1", "2026-11-03", "100.00")]
    b = [bank("S1", "T1", "2026-11-04", "100.00")]
    r = run(p, b)
    d = cats(r, "DUPLICATE_ENTRY")
    actual.append(f"rows={len(d)}, dataset={d[0]['dataset']}, raw_gap={r.summary['aggregate_difference_raw']}, "
                  f"clean_gap={r.summary['aggregate_difference_clean']}")
    assert len(d) == 1 and d[0]["dataset"] == "PLATFORM"
    assert r.summary["aggregate_difference_raw"] == D("100.00") and r.summary["aggregate_difference_clean"] == 0
    assert r.summary["unexplained_residual"] == 0


def test_tc05_duplicate_in_bank(actual):
    """ID: TC-05
    Objective: Detect a duplicate transaction ID in the bank dataset
    Input: platform T1 once; bank has T1 twice with different settlement IDs, same month
    Expected: one DUPLICATE_ENTRY row, dataset BANK, bank clean total excludes the copy, residual 0"""
    p = [plat("T1", "2026-11-03", "100.00")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "T1", "2026-11-05", "100.00")]
    r = run(p, b)
    d = cats(r, "DUPLICATE_ENTRY")
    actual.append(f"rows={len(d)}, dataset={d[0]['dataset']}, bank_raw={r.summary['bank_net_total']}, "
                  f"bank_clean={r.summary['bank_net_clean']}")
    assert len(d) == 1 and d[0]["dataset"] == "BANK"
    assert r.summary["bank_net_total"] == D("200.00") and r.summary["bank_net_clean"] == D("100.00")
    assert r.summary["unexplained_residual"] == 0


def test_tc06_orphan_refund(actual):
    """ID: TC-06
    Objective: Detect a refund whose original payment does not exist
    Input: refund R1 (-50.00) referencing T999, which is not in the platform data; bank paid it out
    Expected: one ORPHAN_REFUND row naming the missing original T999"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("R1", "2026-11-05", "-50.00", "REFUND", "T999")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "R1", "2026-11-06", "-50.00")]
    r = run(p, b)
    d = cats(r, "ORPHAN_REFUND")
    actual.append(f"rows={len(d)}, id={d[0]['txn_id']}, explanation={d[0]['explanation'][:90]}")
    assert len(d) == 1 and d[0]["txn_id"] == "R1" and "T999" in d[0]["explanation"]


def test_tc07_missing_and_in_transit(actual):
    """ID: TC-07
    Objective: A payment with no bank record is Missing only after the settlement window; otherwise In transit
    Input: payment 2026-11-10 with no bank row; payment 2026-11-30 with no bank row and a bank file covering 1 day past month end
    Expected: 11-10 payment is MISSING_SETTLEMENT, 11-30 payment is IN_TRANSIT"""
    p = [plat("OLD", "2026-11-10", "100.00"), plat("NEW", "2026-11-30", "60.00"), plat("OK", "2026-11-02", "5.00")]
    b = [bank("S1", "OK", "2026-11-03", "5.00")]
    r = run(p, b, lookahead_days=1)
    actual.append(f"missing={[d['txn_id'] for d in cats(r, 'MISSING_SETTLEMENT')]}, "
                  f"in_transit={[d['txn_id'] for d in cats(r, 'IN_TRANSIT')]}, residual={r.summary['unexplained_residual']}")
    assert [d["txn_id"] for d in cats(r, "MISSING_SETTLEMENT")] == ["OLD"]
    assert [d["txn_id"] for d in cats(r, "IN_TRANSIT")] == ["NEW"] and r.summary["unexplained_residual"] == 0


def test_tc08_unexpected_bank_txn(actual):
    """ID: TC-08
    Objective: A bank record with no platform transaction is flagged
    Input: bank line X1 (300.00) in November, platform has only T1
    Expected: one UNEXPECTED_BANK_TXN row, month-end impact -300.00, residual 0"""
    p = [plat("T1", "2026-11-03", "100.00")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "X1", "2026-11-09", "300.00")]
    r = run(p, b)
    d = cats(r, "UNEXPECTED_BANK_TXN")
    actual.append(f"rows={len(d)}, impact={d[0]['bridge_effect']}, residual={r.summary['unexplained_residual']}")
    assert len(d) == 1 and d[0]["bridge_effect"] == D("-300.00") and r.summary["unexplained_residual"] == 0


def test_tc09_empty_datasets(actual):
    """ID: TC-09
    Objective: Empty inputs do not crash
    Input: empty DataFrames (with and without columns)
    Expected: status NO DATA, zero counts, no exception"""
    r1 = reconcile(pd.DataFrame(), pd.DataFrame())
    r2 = reconcile(pd.DataFrame(columns=["txn_id", "txn_type", "amount", "status", "txn_date"]), None)
    actual.append(f"status={r1.status}/{r2.status}, discrepancies={len(r1.discrepancies)}")
    assert r1.status == "NO DATA" and r2.status == "NO DATA" and r1.summary["platform_records"] == 0


def test_tc10_invalid_records(actual):
    """ID: TC-10
    Objective: Bad rows are quarantined, excluded from totals and reported
    Input: platform rows with non-numeric amount, missing ID, bad date, positive refund; one good row
    Expected: 4 invalid records, only the good row counted, residual 0"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("T2", "2026-11-03", "abc"), plat("", "2026-11-03", "5.00"),
         plat("T4", "not-a-date", "5.00"), plat("R5", "2026-11-04", "10.00", "REFUND", "T1")]
    b = [bank("S1", "T1", "2026-11-04", "100.00")]
    r = run(p, b)
    actual.append(f"invalid={r.summary['invalid_records']}, platform_net={r.summary['platform_net_total']}, "
                  f"invalid_rows_reported={len(cats(r, 'INVALID_RECORD'))}")
    assert r.summary["invalid_records"] == 4 and r.summary["platform_net_total"] == D("100.00")
    assert len(cats(r, "INVALID_RECORD")) == 4 and r.summary["unexplained_residual"] == 0


def test_tc11_duplicate_excluded_from_totals(actual):
    """ID: TC-11
    Objective: Duplicates do not distort the clean totals and originals stay available for audit
    Input: platform T1 (100.00) three times, T2 (50.00) once; bank T1, T2 once
    Expected: raw platform 350.00, excluded 200.00, clean 150.00 = bank 150.00; all 4 platform rows still listed"""
    p = [plat("T1", "2026-11-03", "100.00")] * 3 + [plat("T2", "2026-11-03", "50.00")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "T2", "2026-11-04", "50.00")]
    r = run(p, b)
    s = r.summary
    actual.append(f"raw={s['platform_net_total']}, excluded={s['duplicate_amount_excluded']}, clean={s['platform_net_clean']}, "
                  f"audit_rows={len(r.platform_rows)}")
    assert (s["platform_net_total"], s["duplicate_amount_excluded"], s["platform_net_clean"]) == (D("350.00"), D("200.00"), D("150.00"))
    assert s["aggregate_difference_clean"] == 0 and len(r.platform_rows) == 4


def test_tc12_financial_calculations(actual):
    """ID: TC-12
    Objective: Totals, matched and unmatched amounts are computed correctly with Decimal
    Input: payments 1000.00 and 2000.50, refund -500.00 (orig 1000.00); bank has all three in Nov
    Expected: payments 3000.50, refunds -500.00, net 2500.50 on both sides, gap 0"""
    p = [plat("T1", "2026-11-03", "1000.00"), plat("T2", "2026-11-04", "2000.50"),
         plat("R1", "2026-11-06", "-500.00", "REFUND", "T1")]
    b = [bank("S1", "T1", "2026-11-04", "1000.00"), bank("S2", "T2", "2026-11-05", "2000.50"),
         bank("S3", "R1", "2026-11-09", "-500.00")]
    s = run(p, b).summary
    actual.append(f"payments={s['platform_payments_total']}, refunds={s['platform_refunds_total']}, "
                  f"net={s['platform_net_total']}/{s['bank_net_total']}, gap={s['aggregate_difference_raw']}")
    assert s["platform_payments_total"] == D("3000.50") and s["platform_refunds_total"] == D("-500.00")
    assert s["platform_net_total"] == s["bank_net_total"] == D("2500.50") and s["aggregate_difference_raw"] == 0


def test_tc13_refund_treatment(actual):
    """ID: TC-13
    Objective: A refund with a valid original is matched, reduces the net total and is not an orphan
    Input: payment T1 100.00, partial refund R1 -40.00 referencing T1, both settled in Nov
    Expected: no ORPHAN_REFUND, 2 matched, platform net 60.00"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("R1", "2026-11-05", "-40.00", "REFUND", "T1")]
    b = [bank("S1", "T1", "2026-11-04", "100.00"), bank("S2", "R1", "2026-11-06", "-40.00")]
    r = run(p, b)
    actual.append(f"orphans={len(cats(r, 'ORPHAN_REFUND'))}, matched={r.summary['matched_count']}, net={r.summary['platform_net_total']}")
    assert not cats(r, "ORPHAN_REFUND") and r.summary["matched_count"] == 2 and r.summary["platform_net_total"] == D("60.00")


def test_tc14_reproducible_generation(actual):
    """ID: TC-14
    Objective: The same seed gives identical datasets and results; a different seed does not
    Input: generate(42) twice, generate(7) once
    Expected: identical CSV text and summary for seed 42, different data for seed 7"""
    a1, b1, _ = generate(42)
    a2, b2, _ = generate(42)
    a3, _, _ = generate(7)
    r1, r2 = reconcile(a1, b1), reconcile(a2, b2)
    same = a1.to_csv() == a2.to_csv() and b1.to_csv() == b2.to_csv() and r1.summary == r2.summary
    actual.append(f"seed42_identical={same}, seed7_differs={a1.to_csv() != a3.to_csv()}")
    assert same and a1.to_csv() != a3.to_csv()


def test_tc15_generated_data_detects_all_four(actual):
    """ID: TC-15
    Objective: On the generated dataset the engine finds every planted mandatory discrepancy from the data alone
    Input: generate(42) with planted next-month, rounding, duplicate and orphan refund; engine never sees the manifest
    Expected: engine IDs match manifest; residual exactly 0"""
    p, b, manifest = generate(42)
    r = reconcile(p, b)
    m = {x["type"]: x for x in manifest}
    nm_found = {d["txn_id"] for d in cats(r, "NEXT_MONTH_SETTLEMENT")}
    rounding_found = {d["txn_id"] for d in cats(r, "ROUNDING_DIFFERENCE")}
    planted_rounding = set(m["ROUNDING_DIFFERENCE"]["txn_ids"])
    dup = cats(r, "DUPLICATE_ENTRY")
    orphan = cats(r, "ORPHAN_REFUND")
    actual.append(f"next_month={len(nm_found)}, rounding={len(rounding_found)} of {len(planted_rounding)} planted "
                  f"(rest settled next month), dup={[d['txn_id'] for d in dup]}, orphan={[d['txn_id'] for d in orphan]}, "
                  f"residual={r.summary['unexplained_residual']}")
    assert nm_found == set(m["NEXT_MONTH_SETTLEMENT"]["txn_ids"])
    assert rounding_found == planted_rounding - nm_found and len(rounding_found) > 50
    assert [d["txn_id"] for d in dup] == m["DUPLICATE_ENTRY"]["txn_ids"] and dup[0]["dataset"] == "PLATFORM"
    assert [d["txn_id"] for d in orphan] == m["ORPHAN_REFUND"]["txn_ids"]
    assert {d["txn_id"] for d in cats(r, "MISSING_SETTLEMENT")} == set(m["MISSING_SETTLEMENT"]["txn_ids"])
    assert {d["txn_id"] for d in cats(r, "UNEXPECTED_BANK_TXN")} == set(m["UNEXPECTED_BANK_TXN"]["txn_ids"])
    assert r.summary["unexplained_residual"] == 0 and r.rounding["aggregate_difference"] > 0


def test_tc16_clean_month_has_no_false_alarms(actual):
    """ID: TC-16
    Objective: No false positives on clean data
    Input: generate(42, inject=False)
    Expected: no duplicates, orphan refunds, rounding, mismatches, missing or unexpected rows; residual 0"""
    p, b, _ = generate(42, inject=False)
    r = reconcile(p, b)
    bad = {k: v for k, v in r.counts_by_category().items() if k != "NEXT_MONTH_SETTLEMENT"}
    actual.append(f"non-timing discrepancies={bad}, next_month={r.counts_by_category().get('NEXT_MONTH_SETTLEMENT', 0)}, "
                  f"status={r.status}, residual={r.summary['unexplained_residual']}")
    assert bad == {} and r.summary["unexplained_residual"] == 0 and r.status == "RECONCILED"


def test_tc17_tolerance_boundary(actual):
    """ID: TC-17
    Objective: Difference of 0.01 is rounding, 0.02 is an amount mismatch (tolerance 0.01)
    Input: two matched payments with bank amounts 0.01 and 0.02 higher
    Expected: one ROUNDING_DIFFERENCE and one AMOUNT_MISMATCH"""
    p = [plat("T1", "2026-11-03", "100.00"), plat("T2", "2026-11-03", "100.00")]
    b = [bank("S1", "T1", "2026-11-04", "100.01"), bank("S2", "T2", "2026-11-04", "100.02")]
    r = run(p, b)
    actual.append(f"rounding={[d['txn_id'] for d in cats(r, 'ROUNDING_DIFFERENCE')]}, mismatch={[d['txn_id'] for d in cats(r, 'AMOUNT_MISMATCH')]}")
    assert [d["txn_id"] for d in cats(r, "ROUNDING_DIFFERENCE")] == ["T1"]
    assert [d["txn_id"] for d in cats(r, "AMOUNT_MISMATCH")] == ["T2"]


def test_tc18_dashboard_and_csv_export(tmp_path, actual):
    """ID: TC-18
    Objective: Every dashboard page loads and CSV exports contain the real results
    Input: Flask test client on a fresh temp data folder
    Expected: all pages 200, report.csv has the four mandatory categories, API summary matches the engine"""
    from app import create_app
    app = create_app(tmp_path)
    client = app.test_client()
    codes = {}
    for url in ("/", "/discrepancies?type=NEXT_MONTH_SETTLEMENT", "/discrepancies?type=ROUNDING_DIFFERENCE",
                "/discrepancies?type=DUPLICATE_ENTRY", "/discrepancies?type=ORPHAN_REFUND",
                "/transactions", "/transactions?dataset=bank", "/report", "/data"):
        codes[url] = client.get(url).status_code
    csv_text = client.get("/download/report.csv").get_data(as_text=True)
    api = client.get("/api/summary").get_json()
    engine = app.config["STORE"].result
    actual.append(f"all_200={all(c == 200 for c in codes.values())}, csv_lines={len(csv_text.splitlines())}, "
                  f"api_gap={api['summary']['aggregate_difference_raw']}")
    assert all(c == 200 for c in codes.values())
    for name in ("NEXT_MONTH_SETTLEMENT", "ROUNDING_DIFFERENCE", "DUPLICATE_ENTRY", "ORPHAN_REFUND"):
        assert name in csv_text
    assert Decimal_eq(api["summary"]["aggregate_difference_raw"], engine.summary["aggregate_difference_raw"])
    assert client.get("/download/summary.csv").status_code == 200


def Decimal_eq(a, b):
    return D(str(a)) == D(str(b))
