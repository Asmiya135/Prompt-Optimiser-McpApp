"""Vendor the official MCP Apps SDK (@modelcontextprotocol/ext-apps) into the widget.

The widget must be ONE self-contained HTML file, and hosts may block scripts
from CDNs. So we take the SDK's pre-bundled ES module (app-with-deps.js),
turn its final `export{...}` into `globalThis.McpExtApps = {...}`, and the
server inlines it into intake.html.

Usage (needs internet once; the result is already committed in server/widget/vendor):
    python scripts/vendor_ext_apps.py                 # downloads the pinned version from unpkg
    python scripts/vendor_ext_apps.py path/to/app-with-deps.js
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

VERSION = "2.0.4"
URL = f"https://unpkg.com/@modelcontextprotocol/ext-apps@{VERSION}/dist/src/app-with-deps.js"
OUT = Path(__file__).resolve().parent.parent / "server" / "widget" / "vendor" / "ext-apps-app-with-deps.js"
WANTED = ["App", "PostMessageTransport"]


def convert(src: str) -> str:
    m = re.search(r"export\s*\{([^}]*)\}\s*;?\s*$", src)
    if not m:
        raise SystemExit("Could not find the bundle's final export statement; has the package format changed?")
    mapping = {}
    for part in m.group(1).split(","):
        bits = part.strip().split(" as ")
        local, exported = (bits[0], bits[1]) if len(bits) == 2 else (bits[0], bits[0])
        mapping[exported.strip()] = local.strip()
    missing = [w for w in WANTED if w not in mapping]
    if missing:
        raise SystemExit(f"Bundle does not export {missing}")
    exports = ",".join(f"{name}:{local}" for name, local in mapping.items())
    header = f"/* @modelcontextprotocol/ext-apps {VERSION} (MIT). Vendored by scripts/vendor_ext_apps.py */\n"
    # Wrapped in a function so the bundle's minified names do not leak into the page.
    return header + "(function(){\n" + src[: m.start()] + f"\nglobalThis.McpExtApps={{{exports}}};\n}})();\n"


def main() -> None:
    if len(sys.argv) > 1:
        src = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:  # noqa: S310 - pinned https URL
            src = r.read().decode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(convert(src), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
