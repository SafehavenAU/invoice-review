# Invoice Review

An operations manager has a $5,400 supplier invoice and a $4,800 quote. Which extra charges have supporting paperwork? This small, read-only application puts each invoice line beside its evidence and drafts a question for the supplier.

**[Open the live business demo](https://safehavenau.github.io/invoice-review/demo/)** · **[Download the example invoice and evidence](samples/INV-1042.pdf)** · **[Read the architecture, stack choices and pilot plan](docs/v1-plan.md)**

The live demo opens directly in a browser and uses fictional records. For an offline presentation, download the repo and open `demo/index.html`.

![Example review showing a $200 disposal line and the underlying request](docs/demo-preview.png)

## The two-minute walkthrough

1. Open the electrical invoice, **INV-1042**. Of the $5,400 billed, the recorded paperwork supports $5,200.
2. Select the $200 disposal line. The source asks the supplier to **price** removal. The reviewer still needs evidence that the buyer agreed to pay for it. Open the draft supplier question.
3. Select the $400 after-hours line and inspect the approved variation. Switch to the draft-variation scenario. The same work description now leaves $600 to query. Switch back to restore the recorded view.
4. Open the painting invoice for a clean match, or the joinery invoice to see a shared allowance and an ambiguous line.

“Supported” describes the scope and price visible in this packet. The person reviewing the invoice still decides whether the work was delivered and what happens next.

| Sample packet | Billed | Supported | To query | What it exercises |
| --- | ---: | ---: | ---: | --- |
| [INV-1042 · Electrical](samples/INV-1042.pdf) | $5,400 | $5,200 | $200 | An approved variation and an unapproved request |
| [INV-1043 · Painting](samples/INV-1043.pdf) | $980 | $980 | $0 | Two lines covered by an accepted quote |
| [INV-1044 · Joinery](samples/INV-1044.pdf) | $940 | $800 | $140 | $100 over a shared allowance and $40 with an ambiguous description |

All names and records are fictional. Amounts are AUD excluding GST. Page two of each PDF contains the purchasing evidence. The two JSON files under `invoice_review/data/` are the canonical inputs. The PDFs and the browser snapshot are generated from them.

## Connect an assistant

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). In the repo directory, run `uv sync --locked`. An MCP host launches the local server with `uv run --locked invoice-review-mcp` and communicates over standard input and output.

For Claude Code, run the following once in the project where you want to use the connection. Replace the quoted path with the absolute directory containing this README. The command registers the server with local scope. [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)

```sh
claude mcp add --transport stdio --scope local invoice-review -- uv --directory "/absolute/path/to/invoice-review" run --locked invoice-review-mcp
```

Then ask: **“Which invoice has the largest amount to query? Show the amount, the source record for each disputed line and a draft supplier question.”** Follow up with **“On INV-1042, treat the after-hours variation as a draft. Which figures changed and why?”**

| MCP tool | Returns |
| --- | --- |
| `list_invoice_exceptions()` | Recorded exceptions, sorted by amount to query |
| `get_invoice_review(invoice_id, scenario="recorded")` | Amounts in integer cents, each line's reason and source IDs, and a draft question |
| `get_source_record(source_id, scenario="recorded")` | Document type, effective status and the underlying excerpt |

Pass `variation_draft` on both the review and the source lookup to inspect the hypothetical state for INV-1042. The assistant can retrieve evidence and explain it. The deterministic matcher uses known descriptions, and Python calculates the supported amount from recorded approvals and remaining allowances. The packaged demo runs without a model call. Free-text matching by a model is a proposed experiment in the plan.

## Try the API, SQL report and tests

```sh
uv run --locked invoice-review-api
```

The API starts on `127.0.0.1:8000`. Visit `/docs` for Swagger UI or `/openapi.json` for the contract. The Swagger interface loads its browser assets from a CDN. Example: `GET /invoices/INV-1042?scenario=variation_draft`. Use `GET /sources/VAR-1040-A?scenario=variation_draft` to inspect the matching state.

```sh
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/evaluate.py
uv run --locked python scripts/report.py
```

The evaluation compares supported cents and cited evidence IDs against four labelled fixture cases covering twelve line decisions. The SQL report aggregates the recorded cases by supplier using SQLite. The three invoices have $340 to query in total. The hypothetical draft scenario is excluded from the report.

## Run the server in Docker

```sh
docker build -t invoice-review-demo:0.1 .
docker run --rm -i invoice-review-demo:0.1
```

The default process is the stdio MCP server, so a terminal will wait for protocol input. To run the HTTP API instead:

```sh
docker run --rm -p 127.0.0.1:8000:8000 invoice-review-demo:0.1 uvicorn invoice_review.http_api:app --host 0.0.0.0 --port 8000
```

## Repo map

```text
invoice_review/core.py         matching, money and source rules
invoice_review/data/           three invoices and six evidence documents
invoice_review/mcp_server.py   local MCP tools
invoice_review/http_api.py     read-only HTTP interface and OpenAPI schema
demo/                          self-contained browser demo and template
samples/                       printable invoice and evidence packets
eval/cases.json                labelled line amounts and expected references
sql/exception_report.sql       supplier exception report
scripts/                       evaluation, reporting and artifact generation
tests/                         business rules, HTTP contract and MCP protocol
docs/v1-plan.md                architecture, integrations and next experiment
```

After editing fixtures, regenerate the browser demo with `python scripts/build_demo.py` and the PDFs with `uv run --no-project --script scripts/build_samples.py`. The browser generator needs only the Python standard library.
