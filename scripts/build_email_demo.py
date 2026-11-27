"""Generate the self-contained email approval walkthrough from the verified model readings."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invoice_review.email_review import build_bundle


def script_json(data):
    payload = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def main(output=None):
    demo = ROOT / "demo"
    template = (demo / "email-approvals.template.html").read_text(encoding="utf-8")
    model = json.loads((ROOT / "invoice_review/data/reply_model.json").read_text(encoding="utf-8"))
    parts = {"{{EMAIL_DATA}}": script_json(build_bundle()), "{{REPLY_MODEL}}": script_json(model),
             "{{REPLY_INTENT_JS}}": (demo / "reply-intent.js").read_text(encoding="utf-8"),
             "{{REPLY_POLICY_JS}}": (demo / "reply-policy.js").read_text(encoding="utf-8")}
    for marker, content in parts.items():
        if template.count(marker) != 1 or "</script" in content.lower():
            raise ValueError(f"Invalid script or template marker: {marker}")
    html = re.sub("|".join(map(re.escape, parts)), lambda match: parts[match[0]], template)
    path = output or demo / "email-approvals.html"
    path.write_text(html, encoding="utf-8", newline="\n")
    print(f"Built {path.name} with recorded readings and the local reply classifier.")


if __name__ == "__main__":
    main()
