"""Command line runner: reconciles the CSV files and writes the reports to output/.

Usage:  python run_reconciliation.py [--platform PATH] [--bank PATH] [--out output]
"""
import argparse
from pathlib import Path

import pandas as pd

from recon.engine import reconcile
from recon.report import discrepancy_csv, summary_csv


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=str(base / "data/sample/platform_transactions.csv"))
    parser.add_argument("--bank", default=str(base / "data/sample/bank_settlements.csv"))
    parser.add_argument("--out", default=str(base / "output"))
    args = parser.parse_args()

    platform = pd.read_csv(args.platform, dtype=str, keep_default_na=False)
    bank = pd.read_csv(args.bank, dtype=str, keep_default_na=False)
    result = reconcile(platform, bank)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "discrepancy_report.csv").write_text(discrepancy_csv(result))
    (out / "reconciliation_summary.csv").write_text(summary_csv(result))

    s = result.summary
    print(f"Status: {result.status}  (period {result.period_start} to {result.period_end})")
    print(f"Platform net {s['platform_net_total']}  Bank net {s['bank_net_total']}  Gap {s['aggregate_difference_raw']}")
    for item in result.bridge:
        if item["count"]:
            print(f"  {item['label']:<42}{item['count']:>5}  {item['amount']:>14}")
    print(f"  Unexplained residual: {s['unexplained_residual']}")
    for key, count in sorted(result.counts_by_category().items()):
        print(f"  {key}: {count}")
    print(f"Reports written to {out}")


if __name__ == "__main__":
    main()
