from __future__ import annotations

from pathlib import Path

import pytest

from tracecite_mcp import server


@pytest.fixture(autouse=True)
def isolate_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))


def test_broad_query_returns_too_broad_until_agent_refines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "large.log"
    source.write_text(
        "".join(
            f"line={index} level=error worker={index} " + ("x" * 120) + "\n"
            for index in range(100)
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_TOKENS", "100")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_BYTES", "1024")

    broad = server.tracecite_run("incident-a", str(source), "search level=error")
    focused = server.tracecite_run(
        "incident-a", str(source), "search level=error | search worker=42"
    )

    assert broad["status"] == "too_broad"
    assert broad["evidence"] == []
    assert broad["data"]["refine_query"] is True
    assert focused["status"] == "ok"
    assert len(focused["evidence"]) == 1


def test_materialize_transport_is_host_capped_not_agent_configurable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "app.log"
    source.write_text(
        "".join(f"{index} " + ("x" * 400) + "\n" for index in range(100)),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_TOKENS", "1000")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_BYTES", "4096")
    monkeypatch.setenv("TRACECITE_MATERIALIZE_MAX_CHARS", "2048")

    result = server.tracecite_materialize(
        "incident-a",
        str(source),
        1,
        end_line=100,
        before=0,
        after=0,
    )

    body = result.get("data", {}).get("text") or result.get("data", {}).get("new_text") or ""
    assert body
    assert len(body) <= 2049
    assert not ({"text", "new_text"} <= set(result.get("data", {})))
