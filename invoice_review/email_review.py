"""Build a source-checked replay of a model reading fictional purchasing emails."""

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path


DATA_DIR = Path(__file__).with_name("data")


def _load(filename):
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"), parse_float=Decimal)


def _cents(value):
    cents = Decimal(str(value)) * 100
    if not cents.is_finite() or cents < 0 or cents != cents.to_integral_value():
        raise ValueError("Expected a non-negative amount in whole cents.")
    return int(cents)


def _dollars(cents):
    value = f"${cents // 100:,}"
    return value + (f".{cents % 100:02}" if cents % 100 else "")


def _bill(xero, mail):
    invoice, = xero["Invoices"]
    if (invoice["Type"], invoice["CurrencyCode"], invoice["LineAmountTypes"]) != (
        "ACCPAY", "AUD", "Exclusive"
    ):
        raise ValueError("This fixture expects an AUD supplier bill with tax-exclusive lines.")
    number = invoice["InvoiceNumber"]
    supplier = invoice["Contact"]["Name"]
    if supplier != mail["supplier"]:
        raise ValueError(f"The mailbox packet does not match the supplier on {number}.")
    date.fromisoformat(invoice["DateString"].split("T")[0])
    lines = []
    for raw in invoice["LineItems"]:
        job_ids = [tag["Option"] for tag in raw.get("Tracking", []) if tag["Name"] == "Job"]
        if job_ids != [mail["job_ref"]]:
            raise ValueError(f"Each line on {number} needs the same tracked job.")
        lines.append({"id": mail["line_keys"][raw["LineItemID"]],
                      "description": raw["Description"], "cents": _cents(raw["LineAmount"])})
    if len({line["id"] for line in lines}) != len(lines):
        raise ValueError("Bill line identifiers must be unique.")
    total = _cents(invoice["SubTotal"])
    if total != sum(line["cents"] for line in lines):
        raise ValueError("The bill lines do not add up to its tax-exclusive subtotal.")
    base, = [line for line in lines if line["id"] == "base"]
    quote = mail["base_source"]
    if (base["description"], base["cents"]) != (quote["description"], quote["cents"]):
        raise ValueError("The base line does not match the accepted sample quote.")
    return {"number": number, "supplier": supplier, "job_ref": mail["job_ref"],
            "issued_on": invoice["DateString"].split("T")[0], "currency": invoice["CurrencyCode"],
            "total_cents": total, "base_cents": base["cents"], "lines": lines,
            "base_source": {"id": quote["id"], "excerpt": quote["excerpt"]}}


def _threads(mail, scenario):
    threads = []
    ids = set()
    messages = set()
    for original in mail["threads"]:
        thread = {**original, **scenario["overrides"].get(original["id"], {})}
        if thread["id"] != original["id"] or thread["id"] in ids:
            raise ValueError("Each sample conversation must have a unique stable identifier.")
        ids.add(thread["id"])
        for message in thread["messages"]:
            if message["id"] in messages:
                raise ValueError("Message identifiers must be unique within a scenario.")
            messages.add(message["id"])
        same_job = thread["job_ref"] == mail["job_ref"]
        same_supplier = thread["supplier"] == mail["supplier"]
        if not same_job:
            reason = f"Different job reference ({thread['job_ref']})."
        elif not same_supplier:
            reason = "Different supplier."
        else:
            reason = "Same job and supplier as the bill."
        threads.append({**thread, "eligible": same_job and same_supplier, "reason": reason})
    if set(scenario["overrides"]) - ids:
        raise ValueError("The scenario refers to an unknown email thread.")
    return threads


def _input(bill, threads):
    """Expose only the bill's extra charges and messages eligible for retrieval."""
    return {
        "bill": {key: bill[key] for key in ("number", "supplier", "job_ref", "issued_on", "currency")},
        "lines": [line for line in bill["lines"] if line["id"] != "base"],
        "threads": [
            {key: thread[key] for key in ("id", "subject", "job_ref", "supplier", "messages")}
            for thread in threads if thread["eligible"]
        ],
    }


def model_input(scenario_id):
    mail = _load("approval_mail.json")
    scenario = next((item for item in mail["scenarios"] if item["id"] == scenario_id), None)
    if scenario is None:
        raise ValueError(f"Unknown email scenario: {scenario_id}")
    return _input(_bill(_load("xero_bill.json"), mail), _threads(mail, scenario))


def input_digest(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _explicit_amounts(text):
    amounts = re.findall(
        r"(?:\$|\bAUD\s+)\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?!\d|,\d|\.\d)",
        text, re.I,
    )
    return {_cents(amount.replace(",", "")) for amount in amounts}


def _approval_check(line, item, messages, approvers):
    """Conservatively require an authorised, cited reply that confirms this bill amount."""
    approver_id = item.get("approver_message_id")
    reply = messages.get(approver_id)
    cited = [q["text"] for q in item["quotes"] if q["message_id"] == approver_id]
    if not reply or not cited:
        return "The AI did not cite the buyer's approval message."
    limit = approvers.get(reply["sender"])
    if limit is None:
        return "The sender of the cited reply is outside the authorised approver list."
    if type(limit) is not int or limit < line["cents"]:
        return "The charge is above this sender's approval limit."
    if type(item.get("approved_cents")) is not int or item["approved_cents"] != line["cents"]:
        return "The amount the AI found does not match the bill line."
    if _explicit_amounts(reply["body"]) != {line["cents"]} or not any(
        line["cents"] in _explicit_amounts(quote) for quote in cited
    ):
        return "The buyer's cited reply needs to name the amount for this charge."
    # Limit automatic support to plainly worded, unconditional confirmations in this sample.
    affirmative = r"(?:^|[.!]\s+)(?:yes[,\s]+)?(?:i |we )?(?:approve[d]?|authori[sz]e[d]?|go ahead|please proceed)\b"
    qualified = r"\b(?:not|unless|if|pending|until|cancelled|subject to|conditional)\b|\?"
    if not re.search(affirmative, reply["body"], re.I) or re.search(qualified, reply["body"], re.I):
        return "The cited reply needs a reviewer to confirm whether it authorises this charge."
    return None


def _decision(line, item, threads, approvers):
    fallback = {
        "line_id": line["id"], "amount_cents": line["cents"], "status": "review",
        "reason": "The email evidence needs a reviewer.", "thread_id": None, "quotes": [],
        "draft_question": f"Could you confirm the agreed scope and price for {line['description'].lower()}?",
    }
    thread = next((t for t in threads if t["id"] == item.get("thread_id") and t["eligible"]), None)
    if thread is None:
        return {**fallback, "reason": "No matching email for this supplier and job supports the suggestion."}
    messages = {msg["id"]: msg for msg in thread["messages"]}
    quotes = item.get("quotes")
    if not isinstance(quotes, list) or not quotes or any(
        not isinstance(q, dict) or q.get("message_id") not in messages
        or not isinstance(q.get("text"), str) or not q["text"].strip()
        or q["text"] not in messages[q["message_id"]]["body"]
        for q in quotes
    ):
        return {**fallback, "thread_id": thread["id"],
                "reason": "The recorded quotation could not be verified in this conversation."}

    result = {**fallback, "thread_id": thread["id"], "quotes": quotes}
    kind = item.get("interpretation")
    if kind == "explicit_approval":
        issue = _approval_check(line, item, messages, approvers)
        if issue:
            return {**result, "reason": issue}
        reply = messages[item["approver_message_id"]]
        limit = approvers[reply["sender"]]
        note = (f"{reply['name']} can approve up to {_dollars(limit)}. "
                f"Their reply names the billed amount of {_dollars(line['cents'])}.")
        return {**result, "status": "supported", "reason": item["reason"], "draft_question": "",
                "authority_note": note}
    if kind in {"ambiguous", "price_request"}:
        return {**result, "status": "unclear" if kind == "ambiguous" else "price_only",
                "reason": item["reason"],
                "draft_question": item.get("draft_question") or fallback["draft_question"]}
    return result


def review_scenario(bill, threads, approvers, recording):
    if recording["input_sha256"] != input_digest(_input(bill, threads)):
        raise ValueError("The saved AI reading belongs to different bill or email text. Record a new reading.")
    extras = [line for line in bill["lines"] if line["id"] != "base"]
    items = {item["line_id"]: item for item in recording["items"]}
    if len(items) != len(recording["items"]) or set(items) != {line["id"] for line in extras}:
        raise ValueError("The AI reading must address each extra bill line exactly once.")
    decisions = [_decision(line, items[line["id"]], threads, approvers) for line in extras]
    # One approval message cannot be claimed twice by separate bill lines in this demonstration.
    approvals = [items[d["line_id"]]["approver_message_id"] for d in decisions if d["status"] == "supported"]
    for d in decisions:
        if d["status"] == "supported" and approvals.count(items[d["line_id"]]["approver_message_id"]) > 1:
            d.update(status="review", reason="The same approval was claimed for two different charges.",
                     draft_question="Which charge does this approval cover?")
            d.pop("authority_note", None)
    supported = bill["base_cents"] + sum(d["amount_cents"] for d in decisions if d["status"] == "supported")
    return {"supported_cents": supported, "query_cents": bill["total_cents"] - supported, "items": decisions}


def build_bundle():
    mail = _load("approval_mail.json")
    bill = _bill(_load("xero_bill.json"), mail)
    recordings = _load("approval_ai_reads.json")["scenarios"]
    scenarios = []
    for scenario in mail["scenarios"]:
        threads = _threads(mail, scenario)
        result = review_scenario(bill, threads, mail["approvers"], recordings[scenario["id"]])
        scenarios.append({"id": scenario["id"], "label": scenario["label"],
                          "threads": threads, "result": result})
    return {"bill": bill, "scenarios": scenarios}
