from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class Handler(BaseHTTPRequestHandler):
    source: Path
    request_log: Path

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        with self.request_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

        messages = payload.get("messages") or []
        tool_result_seen = any(
            isinstance(item, dict) and item.get("role") == "tool" for item in messages
        )
        tools = payload.get("tools") or []
        advertised = {
            str(((item or {}).get("function") or {}).get("name") or "")
            for item in tools
            if isinstance(item, dict)
        }

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()

        if tool_result_seen:
            self._event({"role": "assistant", "content": "PI_MCP_SMOKE_OK"}, None)
            self._event({}, "stop")
            self._done()
            return

        if "mcp" not in advertised:
            self._event({"role": "assistant", "content": "MCP_TOOL_MISSING"}, None)
            self._event({}, "stop")
            self._done()
            return

        # pi-mcp-adapter namespaces each remote MCP tool as <server>_<tool>
        # inside its generic `mcp` proxy. TraceCite itself keeps the canonical
        # `tracecite_*` MCP names; this extra prefix belongs only to the Pi adapter.
        arguments: dict[str, Any] = {
            "server": "tracecite",
            "tool": "tracecite_tracecite_retrieve",
            "args": {
                "session_id": "pi-host-smoke",
                "target": {
                    "kind": "query",
                    "source": str(self.source),
                    "query": "target",
                    "segmenter": "rawtext",
                },
            },
        }
        self._event(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_tracecite_smoke",
                        "type": "function",
                        "function": {
                            "name": "mcp",
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }
                ],
            },
            None,
        )
        self._event({}, "tool_calls")
        self._done()

    def _event(self, delta: dict[str, Any], finish_reason: str | None) -> None:
        chunk = {
            "id": "chatcmpl-tracecite-smoke",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "smoke-model",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def _done(self) -> None:
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: pi_fake_openai_server.py SOURCE PORT_FILE REQUEST_LOG"
        )
    source = Path(sys.argv[1]).resolve()
    port_file = Path(sys.argv[2]).resolve()
    request_log = Path(sys.argv[3]).resolve()
    if not source.is_file():
        raise SystemExit(f"missing smoke source: {source}")
    request_log.parent.mkdir(parents=True, exist_ok=True)
    request_log.write_text("", encoding="utf-8")

    Handler.source = source
    Handler.request_log = request_log
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text(str(server.server_address[1]), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
