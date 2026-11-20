# Distilled prompt

**Problem.** A payments company's books don't balance at month end. The platform records every transaction instantly; the bank settles 1-2 days later. Find out why and show where the gaps are.

**Data.** No files given. Generate seeded, repeatable CSVs: platform transactions (ID, timestamp, date, PAYMENT/REFUND, original ref, amount, currency, status) and bank settlements (settlement ID, txn ID, date, amount, batch ID, currency, status). November 2026 platform data, bank settlements running into December. State assumptions.

**Four mandatory discrepancies** (detected from the data, not hardcoded):
1. A transaction recorded in November that settles in December (timing, not missing).
2. Rounding differences invisible per line but visible in the sum (Decimal, explicit half-up rule, tolerance).
3. A duplicate entry in one dataset (excluded from totals, kept for audit).
4. A refund with no matching original payment (orphan refund).

**Engine.** Match by transaction ID; compare amounts; classify every record into exactly one bucket; build a bridge `platform total - bank total = explained items + residual` with residual 0.00; also report missing and unexpected bank records without calling every unmatched row "missing".

**Stack.** Python, pandas, Decimal, Flask dashboard (overview, discrepancies with explanations, transactions with search/filter, report, data management), CSV export. (Planned React/FastAPI replaced by Flask because package installs were blocked.)

**Tests.** pytest for all four scenarios, bank-side duplicates, missing, unexpected, empty and invalid input, duplicate exclusion, financial totals, refunds, reproducibility, dashboard and CSV export.

**Deliverables.** Source ZIP, README, assumptions, raw and distilled prompts, test cases, deployed link, demo video, and three production-limitation sentences.
