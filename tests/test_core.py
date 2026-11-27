import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from invoice_review import core


@contextmanager
def changed_packet(change):
    """Create an independent, temporary packet for a mismatch or malformed-document test."""
    invoices = json.loads((core.DATA_DIR / "invoices.json").read_text(encoding="utf-8"))
    evidence = json.loads((core.DATA_DIR / "evidence.json").read_text(encoding="utf-8"))
    change(invoices, evidence)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        for name, value in [("invoices", invoices), ("evidence", evidence)]:
            (directory / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        with patch.object(core, "DATA_DIR", directory):
            yield


class InvoiceReviewTests(unittest.TestCase):
    def test_flagship_separates_paperwork_from_authorisation(self):
        review = core.get_invoice_review("INV-1042")
        self.assertEqual(
            (review["total_cents"], review["quote_cents"], review["supported_cents"], review["query_cents"]),
            (540000, 480000, 520000, 20000),
        )
        self.assertEqual(review["currency"], "AUD")
        self.assertEqual(review["lines"][0]["source_ids"], ["INV-1042", "Q-1040"])
        self.assertEqual(review["lines"][1]["source_ids"], ["INV-1042", "VAR-1040-A"])
        request = review["lines"][2]
        self.assertEqual(request["source_ids"], ["INV-1042", "REQ-1040-D"])
        self.assertEqual((request["status"], request["supported_cents"]), ("query", 0))
        self.assertIn("Disposal of removed fittings", review["draft_question"])
        self.assertIn("200.00", review["draft_question"])

    def test_source_status_matches_comparison_and_replays_without_mutation(self):
        before = core.get_invoice_review("INV-1042")
        simulated = core.get_invoice_review("INV-1042", "variation_draft")
        self.assertEqual((simulated["supported_cents"], simulated["query_cents"]), (480000, 60000))
        changed = simulated["lines"][1]
        self.assertEqual((changed["status"], changed["supported_cents"]), ("query", 0))
        self.assertIn("draft", changed["reason"])
        self.assertIn("600.00", simulated["draft_question"])
        for source in changed["source_ids"]:
            self.assertEqual(core.get_source_record(source, "variation_draft")["source_id"], source)
        self.assertEqual(core.get_source_record("VAR-1040-A", "variation_draft")["status"], "draft")
        self.assertEqual(core.get_source_record("VAR-1040-A")["status"], "approved")
        self.assertEqual(core.get_invoice_review("INV-1042"), before)

    def test_allowance_is_shared_and_ambiguous_charge_stays_open(self):
        review = core.get_invoice_review("INV-1044")
        initial, repeat, ambiguous = review["lines"][1:]
        self.assertEqual((initial["status"], initial["supported_cents"]), ("supported", 15000))
        self.assertEqual((repeat["status"], repeat["supported_cents"], repeat["query_cents"]),
                         ("partial", 5000, 10000))
        self.assertEqual((ambiguous["status"], ambiguous["query_cents"]), ("query", 4000))
        self.assertIn("multiple", ambiguous["reason"])
        self.assertEqual(ambiguous["source_ids"], ["INV-1044", "Q-1044"])

    def test_clean_invoice_has_no_question(self):
        clean = core.get_invoice_review("INV-1043")
        self.assertEqual((clean["supported_cents"], clean["query_cents"]), (98000, 0))
        self.assertEqual(clean["draft_question"], "")

    def test_all_reported_amounts_balance_and_all_citations_resolve(self):
        for row in core.list_invoices():
            review = core.get_invoice_review(row["invoice_id"])
            self.assertEqual({key: review[key] for key in row}, row)
            self.assertEqual(sum(line["amount_cents"] for line in review["lines"]), row["total_cents"])
            self.assertEqual(row["supported_cents"] + row["query_cents"], row["total_cents"])
            for line in review["lines"]:
                self.assertEqual(line["supported_cents"] + line["query_cents"], line["amount_cents"])
                for source_id in line["source_ids"]:
                    source = core.get_source_record(source_id)
                    self.assertEqual(source["source_id"], source_id)
                    self.assertTrue(source["excerpt"])

    def test_only_affected_invoices_sorted_by_amount_then_id(self):
        self.assertEqual([r["invoice_id"] for r in core.list_invoices()], ["INV-1042", "INV-1044", "INV-1043"])
        self.assertEqual([r["invoice_id"] for r in core.list_invoice_exceptions()], ["INV-1042", "INV-1044"])

    def test_duplicate_attachment_does_not_increase_allowance_or_repeat_citation(self):
        def change(invoices, _):
            invoices[2]["evidence_ids"] += ["VAR-1044-F", "Q-1044"]
        with changed_packet(change):
            review = core.get_invoice_review("INV-1044")
            self.assertEqual((review["query_cents"], review["quote_cents"]), (14000, 90000))
            self.assertEqual(review["lines"][2]["source_ids"], ["INV-1044", "VAR-1044-F"])
            self.assertEqual(len(core.list_invoice_exceptions()), 2)

    def test_paperwork_must_match_both_supplier_and_job(self):
        for field, wrong_value in [("supplier", "Other electrical contractor"), ("job", "Other fit-out")]:
            with self.subTest(field=field):
                def change(_, evidence):
                    variation = next(doc for doc in evidence if doc["source_id"] == "VAR-1040-A")
                    variation[field] = wrong_value
                with changed_packet(change):
                    line = core.get_invoice_review("INV-1042")["lines"][1]
                    self.assertEqual((line["supported_cents"], line["source_ids"]), (0, ["INV-1042"]))

    def test_missing_alias_is_not_assigned_the_closest_label(self):
        def change(invoices, _):
            invoices[0]["lines"][0]["description"] = "Miscellaneous electrical charges"
        with changed_packet(change):
            line = core.get_invoice_review("INV-1042")["lines"][0]
            self.assertEqual(line["status"], "query")
            self.assertEqual(line["query_cents"], 480000)
            self.assertEqual(line["source_ids"], ["INV-1042"])

    def test_reject_unknown_ids_and_unsupported_scenarios(self):
        for unknown in ("INV-9999", "Q-1040"):
            with self.assertRaises(KeyError):
                core.get_invoice_review(unknown)
        with self.assertRaises(KeyError):
            core.get_source_record("missing")
        with self.assertRaises(ValueError):
            core.get_invoice_review("INV-1042", "unknown")
        with self.assertRaises(ValueError):
            core.get_invoice_review("INV-1043", "variation_draft")
        with self.assertRaises(ValueError):
            core.get_source_record("Q-1044", "variation_draft")

    def test_sample_total_and_identifier_validation(self):
        def bad_total(invoices, _):
            invoices[0]["total_cents"] += 1
        with changed_packet(bad_total), self.assertRaisesRegex(ValueError, "total"):
            core.list_invoices()
        def duplicate_id(_, evidence):
            evidence.append(dict(evidence[0]))
        with changed_packet(duplicate_id), self.assertRaisesRegex(ValueError, "unique"):
            core.list_invoices()


if __name__ == "__main__":
    unittest.main()
