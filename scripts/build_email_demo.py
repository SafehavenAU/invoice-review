"""Build the email walkthrough and its interactive case study from the same evidence."""

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


def write_page(template_path, output_path, parts):
    template = template_path.read_text(encoding="utf-8")
    for marker, content in parts.items():
        if template.count(marker) != 1 or "</script" in content.lower():
            raise ValueError(f"Invalid script or template marker: {marker}")
    html = re.sub("|".join(map(re.escape, parts)), lambda match: parts[match[0]], template)
    output_path.write_text(html, encoding="utf-8", newline="\n")
    print(f"Built {output_path.name} from {template_path.name}.")


def main(output=None, case_output=None):
    demo = ROOT / "demo"
    study = ROOT / "case-study"
    model = json.loads((ROOT / "invoice_review/data/reply_model.json").read_text(encoding="utf-8"))
    evidence = {"{{EMAIL_DATA}}": script_json(build_bundle()), "{{REPLY_MODEL}}": script_json(model)}
    walkthrough = {**evidence,
                   "{{REPLY_INTENT_JS}}": (demo / "reply-intent.js").read_text(encoding="utf-8"),
                   "{{REPLY_POLICY_JS}}": (demo / "reply-policy.js").read_text(encoding="utf-8")}
    write_page(demo / "email-approvals.template.html", output or demo / "email-approvals.html", walkthrough)
    if output is None or case_output is not None:
        write_page(study / "index.template.html", case_output or study / "index.html", evidence)


if __name__ == "__main__":
    main()
