from __future__ import annotations

import os
from pathlib import Path

import pytest

from tracecite_mcp import server
from tracecite_mcp.source_policy import available_evidence_sources


@pytest.fixture(autouse=True)
def isolate_source_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.delenv("TRACECITE_EVIDENCE_FILES", raising=False)


def test_missing_source_returns_host_declared_available_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "containerd.log"
    second = tmp_path / "kubelet.log"
    first.write_text("alpha\n", encoding="utf-8")
    second.write_text("beta\n", encoding="utf-8")
    missing = tmp_path / "containerd-6772.log"
    monkeypatch.setenv(
        "TRACECITE_EVIDENCE_FILES",
        os.pathsep.join([str(first), str(second), str(first)]),
    )

    result = server.tracecite_retrieve(
        "investigation-a",
        {"kind": "query", "source": str(missing), "query": "error"},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "source_not_found"
    assert result["source"] == str(missing.resolve())
    assert result["available_sources"] == [str(first.resolve()), str(second.resolve())]


def test_successful_source_read_does_not_echo_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    monkeypatch.setenv("TRACECITE_EVIDENCE_FILES", str(source))

    result = server.tracecite_retrieve(
        "investigation-a",
        {
            "kind": "query",
            "source": str(source),
            "query": "target",
            "segmenter": "rawtext",
        },
    )

    assert result["status"] == "ok"
    assert "available_sources" not in result
    assert "error_code" not in result


def test_inventory_never_widens_allowed_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inside = tmp_path / "inside.log"
    inside.write_text("allowed\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.log"
    outside.write_text("secret\n", encoding="utf-8")
    try:
        monkeypatch.setenv(
            "TRACECITE_EVIDENCE_FILES",
            os.pathsep.join([str(outside), str(inside)]),
        )

        assert available_evidence_sources() == (str(inside.resolve()),)
        with pytest.raises(PermissionError, match="TRACECITE_MCP_ALLOWED_ROOTS"):
            server.tracecite_retrieve(
                "investigation-a",
                {"kind": "query", "source": str(outside), "query": "secret"},
            )
    finally:
        outside.unlink(missing_ok=True)


def test_inventory_is_deduplicated_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[Path] = []
    for index in range(55):
        path = tmp_path / f"evidence-{index:02d}.log"
        path.write_text(f"{index}\n", encoding="utf-8")
        paths.append(path)
    monkeypatch.setenv(
        "TRACECITE_EVIDENCE_FILES",
        os.pathsep.join([str(paths[0]), *map(str, paths), str(paths[1])]),
    )

    result = available_evidence_sources()

    assert len(result) == 50
    assert result[0] == str(paths[0].resolve())
    assert len(set(result)) == len(result)
