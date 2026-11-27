"""Local read-only HTTP access to the same invoice review used by the MCP tools."""

from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from invoice_review import core


class Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class Summary(Record):
    invoice_id: str
    supplier: str
    job: str
    currency: str
    total_cents: int
    supported_cents: int
    query_cents: int


class Line(Record):
    description: str
    amount_cents: int
    supported_cents: int
    query_cents: int
    status: Literal["supported", "query", "partial"]
    reason: str
    source_ids: list[str]


class Review(Summary):
    scenario: str
    quote_cents: int
    invoice_source_id: str
    lines: list[Line]
    draft_question: str


class Source(Record):
    source_id: str
    kind: str
    title: str
    status: str
    excerpt: str


Scenario = Literal["recorded", "variation_draft"]
app = FastAPI(
    title="Invoice Review",
    version="0.1.0",
    description="Review fictional supplier invoices against recorded purchasing evidence. "
    "All amounts are AUD cents excluding GST. The draft scenario is a read-only counterfactual.",
)


@app.get("/invoices", response_model=list[Summary])
def invoices():
    """List every sample invoice and its recorded totals."""
    return core.list_invoices()


@app.get("/exceptions", response_model=list[Summary])
def exceptions():
    """List invoices with an amount to query, largest first."""
    return core.list_invoice_exceptions()


@app.get("/invoices/{invoice_id}", response_model=Review, responses={404: {"description": "Unknown invoice"}})
def invoice_review(invoice_id: str, scenario: Scenario = "recorded"):
    """Get a line-by-line review. The draft scenario applies to INV-1042."""
    try:
        return core.get_invoice_review(invoice_id, scenario)
    except KeyError:
        raise HTTPException(404, detail="Unknown invoice ID.") from None
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from None


@app.get("/sources/{source_id}", response_model=Source, responses={404: {"description": "Unknown source"}})
def source(source_id: str, scenario: Scenario = "recorded"):
    """Read a source document using the same scenario as its review."""
    try:
        return core.get_source_record(source_id, scenario)
    except KeyError:
        raise HTTPException(404, detail="Unknown source ID.") from None
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from None


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)
