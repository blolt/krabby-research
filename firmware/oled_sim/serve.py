#!/usr/bin/env python3
"""Local live-reload viewer for the krab OLED render.

Run it, open the URL, and edit krab.py — the page re-renders on refresh, and
auto-reloads in the browser a moment after you save (it polls the mtime of the
render source). Pixel-accurate: what you see is what the panel shows.

    firmware/oled_sim/serve.py               # -> http://127.0.0.1:8080
    firmware/oled_sim/serve.py 9000          # custom port

No dependencies (Python stdlib only). Ctrl-C to stop.
"""
from __future__ import annotations

import http.server
import importlib
import io
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ssd1306  # noqa: E402
import krab      # noqa: E402
import viewer    # noqa: E402

# Files whose changes should trigger a browser reload.
_WATCH = [HERE / "krab.py", HERE / "ssd1306.py", HERE / "viewer.py"]

_LIVE_JS = """
<script>
(function () {
  let last = null;
  async function tick() {
    try {
      const t = await (await fetch('/mtime', {cache: 'no-store'})).text();
      if (last !== null && t !== last) return location.reload();
      last = t;
    } catch (e) { /* server restarting; ignore */ }
    setTimeout(tick, 700);
  }
  tick();
})();
</script>
"""


def _mtime() -> str:
    return str(max((f.stat().st_mtime for f in _WATCH if f.exists()), default=0))


def _render_page() -> bytes:
    """Reload the render modules and rebuild the gallery from the current source."""
    importlib.reload(ssd1306)
    importlib.reload(krab)
    importlib.reload(viewer)
    try:
        html = viewer.build(viewer.default_scenes())
    except Exception:
        # Show the traceback in the browser instead of a blank 500 — keeps the
        # edit/refresh loop tight when krab.py has a syntax/render error.
        tb = traceback.format_exc()
        html = (f"<pre style='color:#f66;background:#0a0e12;padding:24px;"
                f"font:13px ui-monospace,monospace;white-space:pre-wrap'>"
                f"render error — fix krab.py and save:\n\n{tb}</pre>")
    return ("<!doctype html><meta charset='utf-8'>" + _LIVE_JS + html).encode("utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/mtime"):
            self._send(_mtime().encode(), "text/plain")
        else:
            self._send(_render_page())

    def log_message(self, *args):
        pass  # quiet


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"krab render viewer -> {url}")
    print("edit krab.py and save; the browser auto-reloads. Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
