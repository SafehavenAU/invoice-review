import unittest

from fastapi.testclient import TestClient

from invoice_review import core
from invoice_review.http_api import app


class HttpContractTests(unittest.TestCase):
    def test_views_share_the_core_results(self):
        with TestClient(app) as client:
            for path, expected in (
                ("/invoices", core.list_invoices()),
                ("/exceptions", core.list_invoice_exceptions()),
                ("/invoices/INV-1042", core.get_invoice_review("INV-1042")),
                ("/invoices/INV-1042?scenario=variation_draft",
                 core.get_invoice_review("INV-1042", "variation_draft")),
                ("/sources/VAR-1040-A?scenario=variation_draft",
                 core.get_source_record("VAR-1040-A", "variation_draft")),
            ):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), expected)

    def test_invalid_requests_have_explicit_status_codes(self):
        with TestClient(app) as client:
            for path, status in (
                ("/invoices/unknown", 404),
                ("/sources/unknown", 404),
                ("/invoices/INV-1043?scenario=variation_draft", 422),
                ("/invoices/INV-1042?scenario=unknown", 422),
            ):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, status)

    def test_openapi_describes_the_read_only_review(self):
        with TestClient(app) as client:
            spec = client.get("/openapi.json").json()
            self.assertEqual(set(spec["paths"]), {"/invoices", "/exceptions", "/invoices/{invoice_id}", "/sources/{source_id}"})
            self.assertTrue(all(set(operations) == {"get"} for operations in spec["paths"].values()))
            self.assertIn("supported_cents", spec["components"]["schemas"]["Review"]["properties"])
