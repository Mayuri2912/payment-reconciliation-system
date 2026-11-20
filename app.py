"""Flask dashboard for the reconciliation engine.

Run:  python app.py        (opens on http://127.0.0.1:5000)
All numbers on every page come from recon.engine.reconcile() on the active CSV files.
"""
from __future__ import annotations

import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)

from recon.engine import CATEGORY_INFO, ReconConfig, ReconError, reconcile
from recon.generator import generate, save_dataset
from recon.report import bar_svg, discrepancy_csv, summary_csv

BASE_DIR = Path(__file__).resolve().parent
MANDATORY = ["NEXT_MONTH_SETTLEMENT", "ROUNDING_DIFFERENCE", "DUPLICATE_ENTRY", "ORPHAN_REFUND"]
OTHER = ["MISSING_SETTLEMENT", "UNEXPECTED_BANK_TXN", "AMOUNT_MISMATCH", "IN_TRANSIT", "INVALID_RECORD"]
PAGE_SIZE = 50


class Store:
    """Holds the active datasets and the latest reconciliation result."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.platform_path = self.dir / "platform_transactions.csv"
        self.bank_path = self.dir / "bank_settlements.csv"
        self.manifest_path = self.dir / "manifest.json"
        self.config = ReconConfig()
        self.result = None
        self.error = None
        if not (self.platform_path.exists() and self.bank_path.exists()):
            self.generate(42)
        else:
            self.run()

    def generate(self, seed: int, inject: bool = True):
        p, b, m = generate(seed=seed, inject=inject)
        save_dataset(p, b, m, self.dir)
        self.run()

    def run(self):
        platform = pd.read_csv(self.platform_path, dtype=str, keep_default_na=False)
        bank = pd.read_csv(self.bank_path, dtype=str, keep_default_na=False)
        self.result = reconcile(platform, bank, self.config)

    def manifest(self):
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return None


def money(value, places=2):
    """Format a Decimal with thousands separators; keep extra decimals if the value has them."""
    if value is None or value == "":
        return ""
    d = Decimal(str(value))
    if places == 2 or d == d.quantize(Decimal("0.01")):
        # show 2 decimals unless the value really needs a third (e.g. 0.005)
        needs_more = d != d.quantize(Decimal("0.01"))
        return f"{d:,.3f}" if needs_more else f"{d:,.2f}"
    return f"{d:,.{places}f}"


def create_app(data_dir=None) -> Flask:
    app = Flask(__name__)
    app.secret_key = "local-demo-only"
    store = Store(Path(data_dir) if data_dir else BASE_DIR / "data" / "active")
    app.config["STORE"] = store
    app.jinja_env.filters["money"] = money

    @app.context_processor
    def inject_common():
        return {"result": store.result, "CATEGORY_INFO": CATEGORY_INFO}

    # ------------------------------------------------------------------ pages
    @app.route("/")
    def overview():
        r = store.result
        counts = r.counts_by_category()
        count_chart = bar_svg([(CATEGORY_INFO[c]["title"], counts.get(c, 0)) for c in MANDATORY + OTHER])
        bridge_chart = bar_svg([(i["label"], i["amount"]) for i in r.bridge if i["count"]], diverging=True)
        cards = [{"key": k, "title": CATEGORY_INFO[k]["title"], "count": counts.get(k, 0),
                  "impact": sum((d["bridge_effect"] for d in r.discrepancies if d["category"] == k), Decimal(0))}
                 for k in MANDATORY]
        return render_template("overview.html", active="overview", counts=counts, cards=cards,
                               count_chart=count_chart, bridge_chart=bridge_chart)

    @app.route("/discrepancies")
    def discrepancies():
        r = store.result
        selected = request.args.get("type", MANDATORY[0])
        if selected not in CATEGORY_INFO:
            abort(404)
        rows = [d for d in r.discrepancies if d["category"] == selected]
        counts = r.counts_by_category()
        return render_template("discrepancies.html", active="discrepancies", selected=selected,
                               rows=rows, counts=counts, mandatory=MANDATORY, other=OTHER,
                               info=CATEGORY_INFO[selected])

    @app.route("/transactions")
    def transactions():
        r = store.result
        dataset = request.args.get("dataset", "platform")
        if dataset not in ("platform", "bank"):
            abort(404)
        query = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "")
        txn_type = request.args.get("type", "")
        sort = request.args.get("sort", "date")
        order = request.args.get("order", "asc")
        page = max(int(request.args.get("page", 1) or 1), 1)

        rows = []
        if dataset == "platform":
            for p in r.platform_rows:
                rows.append({"txn_id": p["txn_id"], "ref": p["original_txn_id"], "settlement_id": p["bank"]["settlement_id"] if p["bank"] else "",
                             "txn_type": p["txn_type"], "amount": p["amount"], "date": p["txn_date"],
                             "settlement_date": p["bank"]["settlement_date"] if p["bank"] else None,
                             "status": p["status"], "match": p["match_status"], "note": p["note"]})
        else:
            for b in r.bank_rows:
                p = b["platform"]
                rows.append({"txn_id": b["txn_id"], "ref": b["batch_id"], "settlement_id": b["settlement_id"],
                             "txn_type": ("REFUND" if b["amount"] < 0 else "PAYMENT"), "amount": b["amount"],
                             "date": p["txn_date"] if p else None, "settlement_date": b["settlement_date"],
                             "status": b["status"], "match": b["match_status"], "note": ""})
        statuses = sorted({x["match"] for x in rows})
        if query:
            rows = [x for x in rows if query in x["txn_id"].lower() or query in x["ref"].lower()
                    or query in x["settlement_id"].lower()]
        if status:
            rows = [x for x in rows if x["match"] == status]
        if txn_type:
            rows = [x for x in rows if x["txn_type"] == txn_type]
        keymap = {"date": lambda x: (x["date"] or x["settlement_date"] or __import__("datetime").date.min),
                  "amount": lambda x: x["amount"], "id": lambda x: x["txn_id"]}
        rows.sort(key=keymap.get(sort, keymap["date"]), reverse=(order == "desc"))
        total = len(rows)
        pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
        page = min(page, pages)
        rows = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        args = {k: v for k, v in request.args.items() if k != "page"}
        return render_template("transactions.html", active="transactions", rows=rows, dataset=dataset,
                               statuses=statuses, total=total, page=page, pages=pages, args=args,
                               q=request.args.get("q", ""), status=status, txn_type=txn_type,
                               sort=sort, order=order)

    @app.route("/report")
    def report():
        return render_template("report.html", active="report", counts=store.result.counts_by_category(),
                               mandatory=MANDATORY, other=OTHER)

    @app.route("/data")
    def data():
        return render_template("data.html", active="data", config=store.config,
                               manifest=store.manifest())

    # ------------------------------------------------------------------ actions
    @app.route("/data/generate", methods=["POST"])
    def data_generate():
        try:
            seed = int(request.form.get("seed", 42))
        except ValueError:
            flash("Seed must be a whole number.", "error")
            return redirect(url_for("data"))
        inject = request.form.get("inject", "yes") == "yes"
        store.generate(seed, inject)
        flash(f"Generated new datasets with seed {seed}{'' if inject else ' (clean, no planted errors)'} and re-ran reconciliation.", "ok")
        return redirect(url_for("overview"))

    @app.route("/data/upload", methods=["POST"])
    def data_upload():
        pf, bf = request.files.get("platform"), request.files.get("bank")
        if not pf or not bf or not pf.filename or not bf.filename:
            flash("Please choose both a platform CSV and a bank CSV.", "error")
            return redirect(url_for("data"))
        try:
            platform = pd.read_csv(io.BytesIO(pf.read()), dtype=str, keep_default_na=False)
            bank = pd.read_csv(io.BytesIO(bf.read()), dtype=str, keep_default_na=False)
            reconcile(platform, bank, store.config)  # validate shape before replacing the active data
        except (ReconError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            flash(f"Upload rejected: {exc}", "error")
            return redirect(url_for("data"))
        platform.to_csv(store.platform_path, index=False)
        bank.to_csv(store.bank_path, index=False)
        if store.manifest_path.exists():
            store.manifest_path.unlink()
        store.run()
        flash("Custom datasets loaded and reconciled.", "ok")
        return redirect(url_for("overview"))

    @app.route("/data/rerun", methods=["POST"])
    def data_rerun():
        try:
            tolerance = Decimal(request.form.get("tolerance", "0.01"))
            if tolerance < 0:
                raise InvalidOperation
        except InvalidOperation:
            flash("Tolerance must be a non-negative number.", "error")
            return redirect(url_for("data"))
        store.config.tolerance = tolerance
        store.run()
        flash(f"Reconciliation re-run with tolerance {tolerance}.", "ok")
        return redirect(url_for("overview"))

    # ------------------------------------------------------------------ downloads and API
    @app.route("/download/<name>")
    def download(name):
        files = {
            "report.csv": lambda: Response(discrepancy_csv(store.result), mimetype="text/csv"),
            "summary.csv": lambda: Response(summary_csv(store.result), mimetype="text/csv"),
            "platform.csv": lambda: send_file(store.platform_path, mimetype="text/csv"),
            "bank.csv": lambda: send_file(store.bank_path, mimetype="text/csv"),
        }
        if name not in files:
            abort(404)
        response = files[name]()
        response.headers["Content-Disposition"] = f"attachment; filename={name}"
        return response

    @app.route("/api/summary")
    def api_summary():
        r = store.result
        return Response(json.dumps({"status": r.status, "period_end": str(r.period_end),
                                    "summary": r.summary, "bridge": r.bridge,
                                    "counts": r.counts_by_category()}, default=str),
                        mimetype="application/json")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
