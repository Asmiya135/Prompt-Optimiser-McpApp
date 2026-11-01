"""End-to-end test of the intake widget in a real browser, against the official host bridge.

The page under test is the exact HTML the server serves. The host side is the
official AppBridge from @modelcontextprotocol/ext-apps, so the handshake,
tool-input/tool-result notifications, tools/call and ui/message all go over
the real MCP Apps protocol. Tool calls are forwarded to the MCP server running
in-process.

Needs: playwright with Chromium, and a host bundle built once with
    cd tests/host && npm install && npx esbuild entry.js --bundle --format=iife --outfile=hostkit.js
Skips cleanly if either is missing.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

HOSTKIT = Path(os.environ.get("HOSTKIT_JS", Path(__file__).parent / "host" / "hostkit.js"))
pw = pytest.importorskip("playwright.async_api")

HOST_PAGE = """<!doctype html><html><body>
<iframe id="app" sandbox="allow-scripts" style="width:800px;height:1400px;border:0"></iframe>
<script>%(hostkit)s</script>
<script>
window.sentMessages = [];
const iframe = document.getElementById("app");
const { AppBridge, PostMessageTransport } = window.HostKit;
const bridge = new AppBridge(null, { name: "TestHost", version: "1.0.0" },
  { serverTools: {}, logging: {}, message: { text: {} } });
bridge.oncalltool = async (params) => JSON.parse(await window.pyCallTool(params.name, JSON.stringify(params.arguments || {})));
bridge.onmessage = async (params) => { window.sentMessages.push(params); return {}; };
bridge.oninitialized = async () => {
  await bridge.sendToolInput({ arguments: { draft: %(draft)s } });
  await bridge.sendToolResult(%(tool_result)s);
  window.widgetReady = true;
};
bridge.connect(new PostMessageTransport(iframe.contentWindow, iframe.contentWindow));
iframe.srcdoc = %(widget)s;
</script></body></html>"""


def _js(value) -> str:
    """JSON that is safe inside an inline <script> (no early </script> end)."""
    return json.dumps(value).replace("</", "<\\/")


@pytest.mark.skipif(not HOSTKIT.exists(), reason="host bundle not built (see module docstring)")
def test_widget_round_trip(tmp_path):
    os.environ["AUTH_MODE"] = "none"
    from mcp import Client
    from server.app import create_server, load_widget_html
    from server.config import Settings

    draft = "write a blog post about climate change"

    async def run():
        server = create_server(Settings())
        async with Client(server) as client:
            first = await client.call_tool("start_intake", {"draft": draft})
            tool_result = {
                "content": [c.model_dump(by_alias=True, exclude_none=True) for c in first.content],
                "structuredContent": first.structured_content,
            }
            page_html = HOST_PAGE % {
                "hostkit": HOSTKIT.read_text(encoding="utf-8").replace("</script", "<\\/script"),
                "draft": _js(draft),
                "tool_result": _js(tool_result),
                "widget": _js(load_widget_html()),
            }
            host_file = tmp_path / "host.html"
            host_file.write_text(page_html, encoding="utf-8")

            async def py_call_tool(name: str, args_json: str) -> str:
                res = await client.call_tool(name, json.loads(args_json))
                return json.dumps({
                    "content": [c.model_dump(by_alias=True, exclude_none=True) for c in res.content],
                    "structuredContent": res.structured_content,
                    "isError": res.is_error,
                })

            async with pw.async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                await page.expose_function("pyCallTool", py_call_tool)
                await page.goto(host_file.as_uri())
                await page.wait_for_function("window.widgetReady === true", timeout=15000)
                frame = page.frame_locator("#app")

                # Prefill from the draft arrived over the protocol.
                await frame.locator("#draft").wait_for()
                assert await frame.locator("#draft").input_value() == draft
                await page.wait_for_timeout(300)
                assert await frame.locator("#outputType").input_value() == "written_piece"

                # Fill question 3 and build through tools/call.
                await frame.locator('#constraintChips .chip[data-key="length"]').click()
                await frame.locator("#c-length").fill("500 words")
                await frame.locator('#constraintChips .chip[data-key="must_include"]').click()
                await frame.locator("#c-must_include").fill("Mumbai, Jakarta, Miami")
                await frame.locator("#build").click()
                await frame.locator("#result:not(.hidden)").wait_for(timeout=10000)
                prompt = await frame.locator("#prompt").input_value()
                assert "Must include: Mumbai, Jakarta, Miami." in prompt
                assert "Length: 500 words." in prompt

                # Conflict banner: pick a different output type than the draft suggests.
                await frame.locator("#outputType").select_option("code")
                assert await frame.locator("#conflict:not(.hidden)").count() == 1
                await frame.locator("#outputType").select_option("written_piece")

                # Send to chat goes out as ui/message.
                await frame.locator("#send").click()
                await page.wait_for_function("window.sentMessages.length === 1", timeout=5000)
                sent = await page.evaluate("window.sentMessages[0]")
                assert sent["role"] == "user" and "Mumbai" in sent["content"][0]["text"]
                await page.screenshot(path=str(tmp_path / "widget.png"), full_page=True)
                os.environ.setdefault("WIDGET_SCREENSHOT", str(tmp_path / "widget.png"))
                await browser.close()
                assert not errors, errors

    asyncio.run(run())
