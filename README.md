# Payment Reconciliation and Discrepancy Detection

## Problem
A payments platform records a transaction the moment a customer pays. The bank settles 1-2 business days later, in batches. At month end the platform total and the bank total do not match. This tool finds out why and shows where the gaps are.

## What it does
- Generates repeatable synthetic datasets (seeded) for November 2026 (bank file runs into December).
- Matches platform transactions to bank settlements by transaction ID.
- Detects and explains the four required discrepancies, plus missing and unexpected bank records so the totals can be fully explained.
- Builds a **bridge**: `platform net total - bank net total = explained items + unexplained residual`. On the sample data the residual is exactly 0.00.
- Flask dashboard and CSV export.

## Run it
```
pip install -r requirements.txt
python app.py                       # http://127.0.0.1:5000
python run_reconciliation.py        # command line run, writes output/*.csv
python -m pytest -q                 # tests, also writes docs/TEST_RESULTS.md
python -m recon.generator --seed 42 --out data/sample    # regenerate the sample CSVs
```
The app creates `data/active/` on first start (seed 42). The Data page can generate new data (any seed, or a clean month), upload your own CSVs, and re-run with a different tolerance.

## Project structure
```
app.py                  Flask dashboard
run_reconciliation.py   CLI runner
recon/engine.py         reconciliation engine (no web code)
recon/generator.py      seeded data generator + manifest of planted errors
recon/report.py         CSV builders and inline SVG charts
recon/money.py, calendar_utils.py
templates/, static/     dashboard pages
tests/                  pytest suite (conftest writes docs/TEST_RESULTS.md)
data/sample/            sample CSVs + manifest (seed 42)
output/                 sample reports from the CLI
docs/                   TEST_RESULTS.md, PRODUCTION_LIMITATIONS.md
prompts/                RAW_PROMPT.md, DISTILLED_PROMPT.md
```

## Assumptions
1. Currency INR, one timezone (IST). Period = the most common month in the platform file (Nov 2026).
2. Amounts are signed in both files: PAYMENT positive, REFUND negative.
3. Bank amounts are **gross**; no fees appear in the data.
4. The bank gives one line per transaction (with a batch ID) and carries the platform transaction ID.
5. Settlement is T+1 or T+2 business days; only Saturday and Sunday are non-business days.
6. A payment with no bank row is "missing" only after T+2 plus 1 grace business day, and only if the bank file covers that date (assumed to run 5 days past month end). Otherwise it is "in transit".
7. The platform stores some amounts with 3 decimals; the bank rounds each line half-up to 2 decimals.
8. Per-line tolerance is 0.01. A smaller difference is rounding; a larger one is an amount mismatch.
9. FAILED platform payments never settle. This is expected, not "missing".
10. A duplicate means the same transaction ID appearing more than once in one dataset (first record kept).

## Data dictionary
Platform: `txn_id, timestamp, txn_date, txn_type (PAYMENT/REFUND), original_txn_id (refunds), amount, currency, status (SUCCESS/FAILED)`.
Bank: `settlement_id, txn_id, settlement_date, amount, batch_id, currency, status (SETTLED)`.

## Detection logic
| Discrepancy | Rule |
|---|---|
| Next-month settlement | Matched by ID, but bank settlement date is after the period end. Reported as timing; month-end impact = the platform amount. |
| Rounding | Matched in the month, line difference is not 0 but within the tolerance. Line differences are summed and compared with what rounding only the total once would give. |
| Duplicate | A transaction ID that repeats inside one dataset. Later copies are excluded from clean totals and kept in the audit list. |
| Orphan refund | A refund whose `original_txn_id` is empty or not a successful payment in the platform data. |
| Others | Missing, in transit, unexpected bank record, amount mismatch, invalid row (so the bridge can balance). |

## Financial method
All money is `Decimal`. Difference = platform amount - bank amount. Totals count successful platform rows in the month and bank rows settled inside the month. Every record falls in exactly one bucket, so the bridge residual is a real check, not a plug figure.

## Sample result (seed 42, from the executed run)
Platform net 6,565,827.46 vs bank net 6,131,873.37, gap 433,954.09: 29 next-month settlements (414,108.205), 111 rounding lines (-0.555 in total, each line 0.005), 1 platform duplicate (218.93), 1 amount mismatch (4,050.00), 2 missing settlements (19,508.01), 2 unexpected bank records (-3,930.50), residual 0.000. One orphan refund (REF-59001, 1,850.00) has no month-end impact because the bank also paid it. See `docs/TEST_RESULTS.md` for the 18 executed tests.

## Known limitations
See `docs/PRODUCTION_LIMITATIONS.md`. Also: no fees, no batch-level matching, no FX, no login or CSRF protection (run locally), orphan refunds whose original is in an older month cannot be told apart from true orphans, and the 9 rounding-cohort lines that settle in December are reported as next-month items, not rounding.
