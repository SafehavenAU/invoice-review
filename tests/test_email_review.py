import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from invoice_review import email_review as review
from scripts import build_email_demo


class EmailApprovalTests(unittest.TestCase):
    def setUp(self):
        self.mail = review._load("approval_mail.json")
        self.bill = review._bill(review._load("xero_bill.json"), self.mail)
        self.threads = review._threads(self.mail, self.mail["scenarios"][0])
        self.recording = review._load("approval_ai_reads.json")["scenarios"]["clear"]
        self.line = next(i for i in self.recording["items"] if i["line_id"] == "after_hours")

    def after_hours_status(self, approvers=None):
        result = review.review_scenario(self.bill, self.threads,
                                        self.mail["approvers"] if approvers is None else approvers,
                                        self.recording)
        return next(i["status"] for i in result["items"] if i["line_id"] == "after_hours")

    def test_both_replays_and_unclear_follow_up(self):
        data = review.build_bundle()
        clear, unclear = (scenario["result"] for scenario in data["scenarios"])
        self.assertEqual((clear["supported_cents"], clear["query_cents"]), (520000, 20000))
        self.assertEqual((unclear["supported_cents"], unclear["query_cents"]), (480000, 60000))
        for result, expected_after_hours in [(clear, "supported"), (unclear, "unclear")]:
            items = {i["line_id"]: i for i in result["items"]}
            self.assertEqual(items["disposal"]["status"], "price_only")
            self.assertEqual(items["after_hours"]["status"], expected_after_hours)
            self.assertTrue(items["disposal"]["draft_question"].strip())
        self.assertTrue(any(i["draft_question"] for i in unclear["items"] if i["status"] == "unclear"))

    def test_model_receives_only_job_and_supplier_candidates(self):
        for scenario in ("clear", "unclear"):
            model_input = review.model_input(scenario)
            self.assertEqual({t["id"] for t in model_input["threads"]}, {"T-17", "T-23"})
            self.assertNotIn("Fern Hall", json.dumps(model_input))
            self.assertEqual({line["id"] for line in model_input["lines"]}, {"after_hours", "disposal"})
            saved = review._load("approval_ai_reads.json")["scenarios"][scenario]
            self.assertEqual(review.input_digest(model_input), saved["input_sha256"])
        altered = deepcopy(self.mail)
        altered["threads"][0]["supplier"] = "An unrelated firm"
        threads = review._threads(altered, altered["scenarios"][0])
        self.assertNotIn("T-17", {t["id"] for t in review._input(self.bill, threads)["threads"]})

    def test_same_price_approval_from_wrong_job_stays_open(self):
        self.line.update(thread_id="T-31", approver_message_id="M-302",
                         quotes=[{"message_id": "M-302", "text": "Approved for $400 ex GST at Fern Hall."}])
        self.assertEqual(self.after_hours_status(), "review")

    def test_excerpts_must_match_the_id_and_actual_text(self):
        for quote in ({"message_id": "M-302", "text": "Approved for $400 ex GST at Fern Hall."},
                      {"message_id": "M-102", "text": "I approve $750 for another job."}):
            with self.subTest(quote=quote):
                self.line["quotes"] = [quote]
                self.assertEqual(self.after_hours_status(), "review")

    def test_sender_authority_limit_and_quoted_amount(self):
        self.assertEqual(self.after_hours_status({}), "review")
        sender = next(iter(self.mail["approvers"]))
        self.assertEqual(self.after_hours_status({sender: 39999}), "review")
        self.assertEqual(self.after_hours_status({sender: 40000}), "supported")
        self.line["approved_cents"] = 40001
        self.assertEqual(self.after_hours_status(), "review")

    def test_input_change_requires_fresh_recording(self):
        self.threads[0]["messages"][0]["body"] += " Newly supplied information."
        with self.assertRaisesRegex(ValueError, "different bill or email"):
            self.after_hours_status()

    def test_one_reply_cannot_fund_two_equal_extras(self):
        bill = deepcopy(self.bill)
        bill["lines"].append({"id": "second_visit", "description": "Another visit", "cents": 40000})
        bill["total_cents"] += 40000
        self.recording["items"].append({**self.line, "line_id": "second_visit"})
        self.recording["input_sha256"] = review.input_digest(review._input(bill, self.threads))
        result = review.review_scenario(bill, self.threads, self.mail["approvers"], self.recording)
        for item in result["items"]:
            if item["line_id"] in {"after_hours", "second_visit"}:
                self.assertEqual(item["status"], "review")
                self.assertNotIn("authority_note", item)

    def test_unconditional_reply_must_explicitly_confirm_amount(self):
        reply = next(m for t in self.threads for m in t["messages"] if m["id"] == "M-102")
        for body in ("I approve the evening visit.", "Can I approve $400?",
                     "I approve $400 if the site manager signs off.", "I do not approve $400."):
            with self.subTest(body=body):
                reply["body"] = body
                self.line["quotes"] = [{"message_id": reply["id"], "text": body}]
                self.recording["input_sha256"] = review.input_digest(review._input(self.bill, self.threads))
                self.assertEqual(self.after_hours_status(), "review")

    def test_unknown_or_missing_extra_line_rejected(self):
        self.line["line_id"] = "unrelated"
        with self.assertRaisesRegex(ValueError, "each extra bill line"):
            self.after_hours_status()

    def test_browser_artifact_matches_current_inputs_and_model_readings(self):
        demo = build_email_demo.ROOT / "demo"
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "email-approvals.html"
            case_output = Path(temp) / "case-study.html"
            build_email_demo.main(output, case_output)
            self.assertEqual(output.read_text(encoding="utf-8"),
                             (demo / "email-approvals.html").read_text(encoding="utf-8"))
            self.assertEqual(case_output.read_text(encoding="utf-8"),
                             (build_email_demo.ROOT / "case-study/index.html").read_text(encoding="utf-8"))
