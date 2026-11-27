import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_demo, report


class PublishedArtifactTests(unittest.TestCase):
    def test_published_owner_demo_matches_current_review_rules(self):
        original = build_demo.ROOT / "demo"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            demo = root / "demo"
            demo.mkdir()
            shutil.copyfile(original / "index.template.html", demo / "index.template.html")
            with patch.object(build_demo, "ROOT", root):
                build_demo.main()
            self.assertEqual((demo / "index.html").read_text(encoding="utf-8"),
                             (original / "index.html").read_text(encoding="utf-8"))

    def test_supplier_report_counts_only_recorded_invoices(self):
        buffer = io.StringIO()
        report.write_report(buffer)
        rows = list(csv.DictReader(io.StringIO(buffer.getvalue())))
        self.assertEqual([int(row["query_cents"]) for row in rows], [20000, 14000, 0])
        self.assertEqual(sum(int(row["invoiced_cents"]) for row in rows), 732000)
        self.assertEqual(sum(int(row["supported_cents"]) for row in rows), 698000)
        self.assertEqual(sum(int(row["invoices_to_query"]) for row in rows), 2)
        self.assertEqual(sum(int(row["lines_to_query"]) for row in rows), 3)
