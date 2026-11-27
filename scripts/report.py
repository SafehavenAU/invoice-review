"""Write a supplier-level exception report to standard output as CSV."""

import csv
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from invoice_review.core import get_invoice_review, list_invoices


def write_report(stream):
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("""
            CREATE TABLE reviewed_lines (
                invoice_id TEXT, supplier TEXT, amount_cents INTEGER,
                supported_cents INTEGER, query_cents INTEGER
            )
        """)
        for invoice in list_invoices():
            review = get_invoice_review(invoice["invoice_id"])
            db.executemany(
                "INSERT INTO reviewed_lines VALUES (?, ?, ?, ?, ?)",
                [(review["invoice_id"], review["supplier"], line["amount_cents"],
                  line["supported_cents"], line["query_cents"]) for line in review["lines"]],
            )
        cursor = db.execute((ROOT / "sql/exception_report.sql").read_text(encoding="utf-8"))
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([column[0] for column in cursor.description])
        writer.writerows(cursor)


if __name__ == "__main__":
    write_report(sys.stdout)
