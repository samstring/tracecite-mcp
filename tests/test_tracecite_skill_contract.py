from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "skills" / "tracecite" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_keeps_direct_tools_and_evidence_boundary_explicit() -> None:
    text = _text()
    assert "use them directly" in text
    assert "Do **not** load MCP scripting/proxy/discovery skills" in text
    assert "Do not bypass a TraceCite-only evidence boundary" in text
    assert "explicitly names a small Evidence source" in text
    assert "`tracecite_run`" in text
    assert "native `cat`/read" in text


def test_skill_distinguishes_literal_search_from_regex() -> None:
    text = _text()
    assert "`search TEXT` is literal text search" in text
    assert "Use `regex PATTERN`" in text
    assert "regex metacharacters inside `search`" in text


def test_skill_requires_lifecycle_evidence_before_fault_attribution() -> None:
    text = _text()
    assert "A suspicious error signature is not automatically the incident trigger" in text
    assert "normal application activity continues across that message" in text
    assert "Do not infer an orchestrator lifecycle state" in text
    assert "retry intervals alone" in text
    assert "keep the external trigger unknown rather than guessing" in text


def test_skill_stops_after_requested_causal_claims_are_sufficient() -> None:
    text = _text()
    assert "## Sufficiency checkpoint and stopping discipline" in text
    assert "Stop gathering new Evidence and answer" in text
    assert "remaining unknowns would only make the explanation more specific" in text
    assert "state that boundary and finish" in text
    assert "ask what decision that call could change" in text
    assert "does not lower the evidentiary standard" in text


def test_skill_guidance_is_not_benchmark_or_fault_specific() -> None:
    lowered = _text().lower()
    for forbidden in (
        "incident_time.txt",
        "ts-route-service",
        "opentelemetry",
        "otel",
        "crashloopbackoff",
        "rcaeval",
    ):
        assert forbidden not in lowered
