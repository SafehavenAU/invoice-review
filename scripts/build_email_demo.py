"""Generate the self-contained email approval walkthrough from the verified model readings."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invoice_review.email_review import build_bundle


def main():
    template = (ROOT / "demo/email-approvals.template.html").read_text(encoding="utf-8")
    marker = "{{EMAIL_DATA}}"
    if template.count(marker) != 1:
        raise ValueError("Expected exactly one email data marker in the walkthrough template.")
    payload = json.dumps(build_bundle(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    with (ROOT / "demo/email-approvals.html").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(template.replace(marker, payload))
    print("Built demo/email-approvals.html from the source-checked email readings.")


if __name__ == "__main__":
    main()
