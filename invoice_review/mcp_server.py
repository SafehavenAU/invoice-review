"""Local MCP tools for reviewing the fictional invoice packet."""

from collections.abc import Callable
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import core
from .email_review import model_input


Scenario = Literal["recorded", "variation_draft"]
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
server = MCPServer(
    "invoice-review",
    instructions=(
        "Review the supplied fictional purchasing records. Amounts are integer cents. "
        "Cite the source IDs returned with each invoice line. Use the same scenario "
        "when fetching the source. Draft questions are for a human reviewer."
    ),
)


@server.tool(annotations=READ_ONLY)
def list_invoice_exceptions() -> dict[str, Any]:
    """List recorded invoices with queries, including IDs, suppliers, jobs and totals in cents."""
    return {"invoices": core.list_invoice_exceptions()}


def _read_record(
    reader: Callable[[str, str], dict[str, Any]], record_id: str, scenario: Scenario
) -> dict[str, Any]:
    try:
        return reader(record_id, scenario)
    except KeyError as error:
        raise ToolError(f"Unknown record ID: {record_id}") from error
    except ValueError as error:
        raise ToolError(str(error)) from error


@server.tool(annotations=READ_ONLY)
def get_invoice_review(invoice_id: str, scenario: Scenario = "recorded") -> dict[str, Any]:
    """Read totals, line decisions, cited source IDs and a draft supplier question.

    The variation_draft scenario shows INV-1042 with its change order still in draft.
    """
    return _read_record(core.get_invoice_review, invoice_id, scenario)


@server.tool(annotations=READ_ONLY)
def get_source_record(source_id: str, scenario: Scenario = "recorded") -> dict[str, Any]:
    """Read one fictional record's ID, document kind, title, status and evidence excerpt."""
    return _read_record(core.get_source_record, source_id, scenario)


@server.tool(annotations=READ_ONLY)
def get_approval_email_packet(example: Literal["clear", "unclear"]) -> dict[str, Any]:
    """Read the sample Xero bill extras and candidate email threads for a fresh interpretation.

    Both examples concern INV-1042. Returns original message text and IDs after matching
    the supplier and job. Cite verbatim evidence and flag ambiguous replies for a reviewer.
    """
    return model_input(example)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
