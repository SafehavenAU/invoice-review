"""A deterministic, exact-alias baseline for reviewing invoices in a supplied document packet.

Amounts are integer Australian cents, excluding GST. An evidence document can support
several invoice lines, up to its explicit allowance for that work. The example includes
one invoice per job and does not track payments or allowances across historical bills.
"""

import json
import re
from datetime import date
from pathlib import Path


DATA_DIR = Path(__file__).with_name("data")
APPROVED_EVIDENCE = {("quote", "accepted"), ("variation", "approved")}
FUNDING_STATES = {
    "quote": {"accepted", "draft"},
    "variation": {"approved", "draft"},
    "request": {"requested"},
}
SUMMARY_FIELDS = (
    "invoice_id", "supplier", "job", "total_cents", "supported_cents", "query_cents", "currency",
)


def _normalise(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _money(cents):
    return f"AUD {cents // 100:,}.{cents % 100:02}"


def _catalogue():
    invoices = json.loads((DATA_DIR / "invoices.json").read_text(encoding="utf-8"))
    evidence = json.loads((DATA_DIR / "evidence.json").read_text(encoding="utf-8"))
    docs = {doc["source_id"]: doc for doc in [*invoices, *evidence]}
    if len(docs) != len(invoices) + len(evidence):
        raise ValueError("Source identifiers must be unique across the sample.")
    evidence_ids = {doc["source_id"] for doc in evidence}
    for doc in invoices:
        if doc["kind"] != "invoice" or doc["currency"] != "AUD":
            raise ValueError(f"Unexpected invoice type or currency on {doc['source_id']}.")
        date.fromisoformat(doc["issued_on"])
        if not all(doc[field].strip() for field in ("supplier", "buyer", "job")):
            raise ValueError(f"Missing supplier, buyer or job on {doc['source_id']}.")
        amounts = [line["amount_cents"] for line in doc["lines"]]
        if not amounts or any(type(amount) is not int or amount <= 0 for amount in amounts):
            raise ValueError(f"Expected positive whole cents on {doc['source_id']}.")
        if type(doc["total_cents"]) is not int or sum(amounts) != doc["total_cents"]:
            raise ValueError(f"Line amounts disagree with the total on {doc['source_id']}.")
        if not set(doc["evidence_ids"]) <= evidence_ids:
            raise ValueError(f"Missing evidence in packet {doc['source_id']}.")
    for doc in evidence:
        if doc["status"] not in FUNDING_STATES.get(doc["kind"], set()):
            raise ValueError(f"Unknown evidence type or status on {doc['source_id']}.")
        works = [item["work"] for item in doc["items"]]
        if len(set(works)) != len(works):
            raise ValueError(f"Repeated allowance for a work item on {doc['source_id']}.")
        for item in doc["items"]:
            if type(item["amount_cents"]) is not int or item["amount_cents"] <= 0:
                raise ValueError(f"Invalid allowance on {doc['source_id']}.")
            if not item["aliases"] or any(not _normalise(alias) for alias in item["aliases"]):
                raise ValueError(f"Unusable work description on {doc['source_id']}.")
    return invoices, docs


def _check_scenario(scenario, source_id, docs):
    if scenario == "recorded":
        return
    if scenario != "variation_draft":
        raise ValueError("Scenario must be 'recorded' or 'variation_draft'.")
    flagship = docs["INV-1042"]
    if source_id not in {flagship["source_id"], *flagship["evidence_ids"]}:
        raise ValueError("The variation_draft scenario applies only to INV-1042 and its sources.")


def _effective(doc, scenario):
    if scenario == "variation_draft" and doc["source_id"] == "VAR-1040-A":
        return {**doc, "status": doc["comparison_status"]}
    return doc


def _line_review(line, invoice_id, entries, remaining):
    """Match exact aliases, withhold ambiguous work, then draw down each allowance in order."""
    description, amount = line["description"], line["amount_cents"]
    label = _normalise(description)
    matches = [(doc, item) for doc, item, aliases in entries if label in aliases]
    sources = list(dict.fromkeys([invoice_id, *(doc["source_id"] for doc, item in matches)]))
    works = {item["work"] for doc, item in matches}
    supported = 0
    if not matches:
        reason = "No matching scope item was found for this supplier and job."
    elif len(works) > 1:
        reason = "This wording matches multiple scope items. Ask which item the charge covers."
    else:
        approved = [(doc, item) for doc, item in matches if (doc["kind"], doc["status"]) in APPROVED_EVIDENCE]
        for doc, item in approved:
            key = (doc["source_id"], item["work"])
            draw = min(remaining[key], amount - supported)
            remaining[key] -= draw
            supported += draw
        if supported == amount:
            reason = "The charge fits the documented scope and its remaining allowance."
        elif approved:
            reason = "The charge exceeds the remaining allowance for this work."
        else:
            states = {doc["status"] for doc, item in matches}
            if states == {"requested"}:
                reason = "The buyer requested a price. The packet contains no approval for this charge."
            elif states == {"draft"}:
                reason = "The matching document is still a draft. The packet contains no approval for this charge."
            else:
                reason = "The related documents contain no approved allowance for this charge."
    status = "supported" if supported == amount else "partial" if supported else "query"
    return {
        "description": description, "amount_cents": amount, "supported_cents": supported,
        "query_cents": amount - supported, "status": status, "reason": reason, "source_ids": sources,
    }


def _review(doc, docs, scenario):
    # A repeated attachment in one packet is still one source of funding.
    evidence = [
        _effective(docs[source_id], scenario) for source_id in dict.fromkeys(doc["evidence_ids"])
        if docs[source_id]["supplier"] == doc["supplier"] and docs[source_id]["job"] == doc["job"]
    ]
    entries = [(source, item, {_normalise(alias) for alias in item["aliases"]})
               for source in evidence for item in source["items"]]
    remaining = {(source["source_id"], item["work"]): item["amount_cents"]
                 for source, item, aliases in entries}
    lines = [_line_review(line, doc["source_id"], entries, remaining) for line in doc["lines"]]
    query = sum(line["query_cents"] for line in lines)
    questions = [f"{line['description']} ({_money(line['query_cents'])})"
                 for line in lines if line["query_cents"]]
    draft = ""
    if questions:
        draft = (f"Could you send the approved scope or clarify the basis for these charges on "
                 f"{doc['source_id']}: {', '.join(questions)}? The amount to clarify is {_money(query)} ex GST.")
    return {
        "invoice_id": doc["source_id"], "supplier": doc["supplier"], "job": doc["job"],
        "total_cents": doc["total_cents"], "supported_cents": doc["total_cents"] - query,
        "query_cents": query, "currency": "AUD", "scenario": scenario,
        "quote_cents": sum(item["amount_cents"] for source, item, aliases in entries
                           if source["kind"] == "quote" and source["status"] == "accepted"),
        "invoice_source_id": doc["source_id"], "lines": lines, "draft_question": draft,
    }


def list_invoices() -> list[dict]:
    """List one summary per invoice, largest amount to query first, then invoice ID ascending."""
    invoices, docs = _catalogue()
    summaries = []
    for doc in invoices:
        review = _review(doc, docs, "recorded")
        summaries.append({key: review[key] for key in SUMMARY_FIELDS})
    return sorted(summaries, key=lambda row: (-row["query_cents"], row["invoice_id"]))


def list_invoice_exceptions() -> list[dict]:
    """List invoices with a positive amount to query. Ordering is the same as list_invoices()."""
    return [summary for summary in list_invoices() if summary["query_cents"]]


def get_invoice_review(invoice_id: str, scenario: str = "recorded") -> dict:
    """Return a single review in recorded or comparison mode. No record is altered."""
    _, docs = _catalogue()
    if invoice_id not in docs or docs[invoice_id]["kind"] != "invoice":
        raise KeyError(invoice_id)
    _check_scenario(scenario, invoice_id, docs)
    return _review(docs[invoice_id], docs, scenario)


def get_source_record(source_id: str, scenario: str = "recorded") -> dict:
    """Return the cited source as an excerpt, with its effective status in the requested scenario."""
    _, docs = _catalogue()
    doc = docs[source_id]
    _check_scenario(scenario, source_id, docs)
    doc = _effective(doc, scenario)
    if doc["kind"] == "invoice":
        items = [f"{line['description']}: {_money(line['amount_cents'])}" for line in doc["lines"]]
        excerpt = ". ".join(items) + f". Total {_money(doc['total_cents'])} ex GST."
    else:
        excerpt = doc["excerpt"]
    return {key: doc[key] for key in ("source_id", "kind", "title", "status")} | {"excerpt": excerpt}
