FROM ghcr.io/astral-sh/uv:0.11.21 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY invoice_review ./invoice_review
RUN uv sync --locked --no-dev --no-editable && useradd --create-home reviewer
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER reviewer
CMD ["invoice-review-mcp"]
