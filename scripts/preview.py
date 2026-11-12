#!/usr/bin/env python3
"""Build a local preview of a review page with demo data, for screenshots and click-testing.

    python3 scripts/preview.py changes   dev/demo-changes.json   /tmp/preview/changes.html
    python3 scripts/preview.py decisions dev/demo-decisions.json /tmp/preview/decisions.html
    python3 -m http.server 8765 -d /tmp/preview      # then open http://localhost:8765/changes.html

The page is wrapped in the same kind of skeleton the Artifact tool adds at publish time, with
dev/mock-claude.js standing in for the claude.ai runtime. Demo JSON maps "collection/doc" to a
document body, exactly what you would seed with ArtifactData.
"""
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKELETON = (
    '<!doctype html><html><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    "<style>:root{color-scheme:light}body{margin:0;font:14px system-ui}img{max-width:100%}"
    "[hidden]{display:none!important}</style>"
)


def inline_demo_images(value):
    """Turn "demo:<file>" strings into data: URIs of dev/img/<file>, so the preview is one file."""
    if isinstance(value, dict):
        return {k: inline_demo_images(v) for k, v in value.items()}
    if isinstance(value, list):
        return [inline_demo_images(v) for v in value]
    if isinstance(value, str) and value.startswith("demo:"):
        path = ROOT / "dev" / "img" / value[5:]
        mime = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg"}[path.suffix]
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    return value


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    page, demo, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    html = (ROOT / "pages" / f"{page}.html").read_text()
    data = inline_demo_images(json.loads(demo.read_text()))
    repo = data.get("meta/run", {}).get("repo", "demo")
    mock = (ROOT / "dev" / "mock-claude.js").read_text()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        SKELETON
        + f"<script>window.DEMO_DATA={json.dumps(data)};</script><script>{mock}</script>"
        + "</head><body>"
        + html.replace("__REPO__", repo)
        + "</body></html>"
    )
    print(out)


if __name__ == "__main__":
    main()
