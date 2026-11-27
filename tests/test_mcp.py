"""Exercise discovery, scenarios and recoverable errors over a real MCP stdio pipe."""

import sys
import unittest

from mcp import Client, StdioServerParameters

from invoice_review import core


class InvoiceReviewProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_workflow_over_stdio(self):
        process = StdioServerParameters(
            command=sys.executable,
            args=["-B", "-m", "invoice_review.mcp_server"],
        )
        async with Client(process, read_timeout_seconds=30) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(
                set(tools), {"list_invoice_exceptions", "get_invoice_review", "get_source_record"}
            )
            for tool in tools.values():
                self.assertIs(tool.annotations.read_only_hint, True)
                self.assertIs(tool.annotations.destructive_hint, False)
                self.assertIs(tool.annotations.idempotent_hint, True)
                self.assertIs(tool.annotations.open_world_hint, False)

            queue = await client.call_tool("list_invoice_exceptions", {})
            self.assertFalse(queue.is_error)
            self.assertEqual(queue.structured_content["invoices"], core.list_invoice_exceptions())
            ids = {row["invoice_id"] for row in queue.structured_content["invoices"]}
            self.assertIn("INV-1042", ids)
            self.assertNotIn("INV-1043", ids)

            reference = {"invoice_id": "INV-1042"}
            recorded = await client.call_tool("get_invoice_review", reference)
            self.assertFalse(recorded.is_error)
            self.assertEqual(recorded.structured_content, core.get_invoice_review("INV-1042"))
            alternate = await client.call_tool(
                "get_invoice_review", {**reference, "scenario": "variation_draft"}
            )
            self.assertFalse(alternate.is_error)
            self.assertGreater(
                alternate.structured_content["query_cents"], recorded.structured_content["query_cents"]
            )
            cited_ids = {
                source for line in alternate.structured_content["lines"] for source in line["source_ids"]
            }
            self.assertIn("VAR-1040-A", cited_ids)
            source = await client.call_tool(
                "get_source_record", {"source_id": "VAR-1040-A", "scenario": "variation_draft"}
            )
            self.assertFalse(source.is_error)
            self.assertEqual(source.structured_content["source_id"], "VAR-1040-A")
            self.assertEqual(source.structured_content["status"].lower(), "draft")

            for name, arguments, message in [
                ("get_invoice_review", {"invoice_id": "INV-MISSING"}, "Unknown record ID"),
                ("get_source_record", {"source_id": "MISSING"}, "Unknown record ID"),
                ("get_invoice_review", {**reference, "scenario": "undefined"}, "scenario"),
                ("get_invoice_review", {"invoice_id": "INV-1043", "scenario": "variation_draft"}, "INV-1042"),
            ]:
                with self.subTest(tool=name, arguments=arguments):
                    error = await client.call_tool(name, arguments)
                    self.assertTrue(error.is_error)
                    self.assertIn(message, error.content[0].text)

            replay = await client.call_tool("get_invoice_review", reference)
            self.assertEqual(replay.structured_content, recorded.structured_content)


if __name__ == "__main__":
    unittest.main()
