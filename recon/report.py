"""CSV report builders and small inline-SVG charts (no extra libraries)."""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from html import escape

REPORT_COLUMNS = ["category", "severity", "dataset", "txn_id", "settlement_id", "txn_type",
                  "platform_date", "settlement_date", "expected_amount", "actual_amount",
                  "difference", "month_end_impact", "explanation", "suggested_action"]


def discrepancy_csv(result) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_COLUMNS)
    for d in result.discrepancies:
        writer.writerow([
            d["category"], d["severity"], d["dataset"], d["txn_id"], d["settlement_id"], d["txn_type"],
            d["platform_date"] or "", d["settlement_date"] or "", d["expected_amount"], d["actual_amount"],
            d["difference"], d["bridge_effect"], d["explanation"], d["suggested_action"]])
    return buffer.getvalue()


def summary_csv(result) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "item", "count", "amount"])
    s = result.summary
    writer.writerow(["status", result.status, "", ""])
    writer.writerow(["period", f"{result.period_start} to {result.period_end}", "", ""])
    for key in ("platform_payments_total", "platform_refunds_total", "platform_net_total",
                "bank_payments_total", "bank_refunds_total", "bank_net_total",
                "aggregate_difference_raw", "duplicate_amount_excluded", "platform_net_clean",
                "bank_net_clean", "aggregate_difference_clean", "matched_platform_amount",
                "unmatched_platform_amount", "gross_discrepancy_amount"):
        writer.writerow(["totals", key, "", s[key]])
    for key in ("platform_records", "bank_records", "matched_count", "unmatched_platform_count",
                "unexpected_bank_count", "discrepancy_count", "actionable_count", "invalid_records"):
        writer.writerow(["counts", key, s[key], ""])
    for item in result.bridge:
        writer.writerow(["bridge", item["label"], item["count"], item["amount"]])
    writer.writerow(["bridge", "Explained difference", "", s["explained_difference"]])
    writer.writerow(["bridge", "Unexplained residual", "", s["unexplained_residual"]])
    rd = result.rounding
    writer.writerow(["rounding", "lines", rd["lines"], ""])
    writer.writerow(["rounding", "aggregate difference (bank minus platform)", "", rd["aggregate_difference"]])
    writer.writerow(["rounding", "difference if rounded once on total", "", rd["difference_if_rounded_once"]])
    return buffer.getvalue()


def bar_svg(items, diverging=False, width=560, bar_height=22, gap=8, label_width=210) -> str:
    """items: list of (label, value). Returns an inline SVG string."""
    if not items:
        return ""
    values = [Decimal(str(v)) for _, v in items]
    top = max([abs(v) for v in values] + [Decimal("0.000001")])
    chart_width = width - label_width - 90
    height = len(items) * (bar_height + gap) + gap
    zero_x = label_width + (chart_width / 2 if diverging else 0)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    for i, ((label, _), value) in enumerate(zip(items, values)):
        y = gap + i * (bar_height + gap)
        scale = (chart_width / 2 if diverging else chart_width) / float(top)
        length = max(float(abs(value)) * scale, 1.5 if value != 0 else 0)
        x = zero_x if value >= 0 else zero_x - length
        color = "#2563eb" if value >= 0 else "#dc2626"
        if not diverging:
            color = "#2563eb"
        parts.append(f'<text x="{label_width - 8}" y="{y + bar_height * 0.7}" text-anchor="end" '
                     f'font-size="12" fill="#334155">{escape(str(label))}</text>')
        parts.append(f'<rect x="{x:.1f}" y="{y}" width="{length:.1f}" height="{bar_height}" rx="3" fill="{color}"/>')
        text_x = x + length + 6 if value >= 0 else x - 6
        anchor = "start" if value >= 0 else "end"
        shown = f"{value:,.2f}" if diverging else f"{int(value)}"
        parts.append(f'<text x="{text_x:.1f}" y="{y + bar_height * 0.7}" text-anchor="{anchor}" '
                     f'font-size="12" fill="#0f172a">{shown}</text>')
    if diverging:
        parts.append(f'<line x1="{zero_x}" y1="0" x2="{zero_x}" y2="{height}" stroke="#94a3b8"/>')
    parts.append("</svg>")
    return "".join(parts)
