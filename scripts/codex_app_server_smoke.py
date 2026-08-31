from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_TOOLS = {
    "tracecite_retrieve",
    "tracecite_materialize",
    "tracecite_replay",
    "tracecite_aggregate",
    "tracecite_traverse",
    "tracecite_verify",
}


class AppServerClient:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["codex", "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self.next_id = 1

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self.next_id
        self.next_id += 1
        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.stdin.write(json.dumps(payload) + "\n")
        self.stdin.flush()
        return self._read_response(request_id)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        self.stdin.write(json.dumps(payload) + "\n")
        self.stdin.flush()

    def _read_response(self, request_id: int) -> Any:
        while True:
            line = self.stdout.readline()
            if not line:
                stderr = ""
                if self.proc.stderr is not None:
                    stderr = self.proc.stderr.read()
                raise RuntimeError(
                    f"codex app-server exited before response {request_id}: {stderr}"
                )
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(
                    f"codex app-server request failed: {json.dumps(message['error'])}"
                )
            return message.get("result")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: codex_app_server_smoke.py WORKSPACE")
    workspace = Path(sys.argv[1]).resolve()
    source = workspace / "app.log"
    if not source.is_file():
        raise SystemExit(f"missing smoke source: {source}")

    client = AppServerClient()
    try:
        initialized = client.send(
            "initialize",
            {
                "clientInfo": {
                    "name": "tracecite-mcp-host-smoke",
                    "title": "TraceCite MCP Host Smoke",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        if not isinstance(initialized, dict):
            raise AssertionError(f"unexpected initialize response: {initialized!r}")
        client.notify("initialized")

        inventory = client.send(
            "mcpServerStatus/list",
            {"detail": "toolsAndAuthOnly", "threadId": None},
        )
        servers = {
            item.get("name"): item
            for item in (inventory or {}).get("data", [])
            if isinstance(item, dict)
        }
        tracecite = servers.get("tracecite")
        if tracecite is None:
            raise AssertionError(f"TraceCite MCP server missing from Codex inventory: {servers}")
        tools = set((tracecite.get("tools") or {}).keys())
        if tools != EXPECTED_TOOLS:
            raise AssertionError(f"unexpected Codex-visible TraceCite tools: {sorted(tools)}")

        thread_result = client.send(
            "thread/start",
            {
                "model": "mock-model",
                "modelProvider": "smoke",
                "cwd": str(workspace),
                "ephemeral": True,
                "approvalPolicy": "never",
            },
        )
        thread_id = str(((thread_result or {}).get("thread") or {}).get("id") or "")
        if not thread_id:
            raise AssertionError(f"thread/start did not return a thread id: {thread_result!r}")

        arguments = {
            "session_id": "codex-host-smoke",
            "target": {
                "kind": "query",
                "source": str(source),
                "query": "target",
                "segmenter": "rawtext",
            },
        }
        first = client.send(
            "mcpServer/tool/call",
            {
                "threadId": thread_id,
                "server": "tracecite",
                "tool": "tracecite_retrieve",
                "arguments": arguments,
            },
        )
        if first.get("isError"):
            raise AssertionError(f"Codex MCP call failed: {first!r}")
        first_payload = first.get("structuredContent") or {}
        if first_payload.get("status") != "ok" or not first_payload.get("evidence"):
            raise AssertionError(f"Codex MCP retrieve returned no evidence: {first_payload!r}")
        if ((first_payload.get("mcp_session") or {}).get("session_id")) != "codex-host-smoke":
            raise AssertionError(f"Codex MCP session mapping failed: {first_payload!r}")

        repeated = client.send(
            "mcpServer/tool/call",
            {
                "threadId": thread_id,
                "server": "tracecite",
                "tool": "tracecite_retrieve",
                "arguments": arguments,
            },
        )
        repeated_payload = repeated.get("structuredContent") or {}
        coverage = repeated_payload.get("coverage") or {}
        if coverage.get("new_evidence") != 0 or int(coverage.get("repeated_evidence") or 0) < 1:
            raise AssertionError(f"Codex MCP repeated-evidence semantics failed: {repeated_payload!r}")

        print(
            json.dumps(
                {
                    "host": "codex-cli",
                    "status": "ok",
                    "tools": sorted(tools),
                    "session_id": "codex-host-smoke",
                    "repeated_evidence": coverage.get("repeated_evidence"),
                },
                sort_keys=True,
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
