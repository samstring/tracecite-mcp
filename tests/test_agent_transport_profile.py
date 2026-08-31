from __future__ import annotations

from pathlib import Path

import pytest

from tracecite_mcp import server


@pytest.fixture(autouse=True)
def isolate_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))


def test_broad_queries_are_bounded_then_focused(tmp_path: Path) -> None:
    source = tmp_path / "large.log"
    source.write_text(
        "".join(
            f"line={index} level=error msg=failed worker={index} " + ("x" * 120) + "\n"
            for index in range(100)
        ),
        encoding="utf-8",
    )

    first = server.tracecite_retrieve(
        "incident-a",
        {
            "kind": "query",
            "source": str(source),
            "query": "level=error",
            "max_evidence": 100,
            "max_line_chars": 5000,
        },
    )
    second = server.tracecite_retrieve(
        "incident-a",
        {
            "kind": "query",
            "source": str(source),
            "query": "failed",
            "max_evidence": 100,
            "max_line_chars": 5000,
        },
    )

    assert len(first["evidence"]) <= 8
    assert first["data"]["routing"]["mode"] == "bounded"
    assert len(second["evidence"]) <= 5
    assert second["data"]["routing"]["mode"] == "focused"
    assert "unmatched" not in second["coverage"]


def test_materialize_default_transport_is_smaller_than_old_twenty_k(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text(
        "".join(f"{index} " + ("x" * 400) + "\n" for index in range(100)),
        encoding="utf-8",
    )

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
    # Core preserves the final line terminator when the bounded body lands
    # exactly on max_chars, so the serialized text can be one character over.
    assert len(body) <= 8_001
    assert not ({"text", "new_text"} <= set(result.get("data", {})))
