"""Server-owner local source access policy."""

from __future__ import annotations

import errno
import os
from pathlib import Path


_MAX_AVAILABLE_SOURCES = 50


def _host_evidence_roots() -> tuple[Path, ...]:
    configured = os.environ.get("TRACECITE_MCP_ALLOWED_ROOTS")
    if not configured:
        return (Path.cwd().resolve(),)
    roots = tuple(
        Path(item).expanduser().resolve()
        for item in configured.split(os.pathsep)
        if item.strip()
    )
    if not roots:
        raise ValueError("TRACECITE_MCP_ALLOWED_ROOTS must contain at least one path")
    return roots


def _managed_state_root() -> Path | None:
    raw = str(os.environ.get("TRACECITE_MCP_STATE_DIR") or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def allowed_roots() -> tuple[Path, ...]:
    """Return roots that MCP evidence tools may read.

    Host evidence roots authorize caller-selected source files. The configured
    TraceCite state directory is additionally trusted for Runtime-created
    immutable snapshots/segments so an EvidencePointer's `materialize_source`
    can be recovered without widening the caller evidence inventory.
    """

    result = list(_host_evidence_roots())
    managed = _managed_state_root()
    if managed is not None and managed not in result:
        result.append(managed)
    return tuple(result)


def _is_within(candidate: Path, roots: tuple[Path, ...]) -> bool:
    return any(candidate == root or root in candidate.parents for root in roots)


def _relative_inventory_matches(value: Path) -> tuple[Path, ...]:
    """Resolve a caller logical name only through the Host-declared inventory.

    A basename such as ``kubelet.log`` is common in Agent prompts. If the Host
    declared that exact evidence file, the Agent should not need to know the
    benchmark/container absolute path. No directory walking is performed.
    """

    parts = value.parts
    if not parts or any(part == ".." for part in parts):
        return ()
    matches: list[Path] = []
    for item in available_evidence_sources():
        candidate = Path(item)
        candidate_parts = candidate.parts
        if len(parts) <= len(candidate_parts) and tuple(candidate_parts[-len(parts) :]) == tuple(parts):
            matches.append(candidate)
    return tuple(matches)


def _relative_root_matches(value: Path, *, must_exist: bool) -> tuple[Path, ...]:
    """Resolve a safe relative path directly inside Host-authorized roots."""

    if value.is_absolute() or any(part == ".." for part in value.parts):
        return ()
    roots = _host_evidence_roots()
    matches: list[Path] = []
    for root in roots:
        candidate = (root / value).resolve()
        if not (candidate == root or root in candidate.parents):
            continue
        if must_exist and not candidate.exists():
            continue
        matches.append(candidate)
    return tuple(matches)


def _unique_relative_match(value: Path, *, must_exist: bool) -> Path | None:
    candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in (*_relative_inventory_matches(value), *_relative_root_matches(value, must_exist=must_exist)):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise ValueError(
            f"ambiguous evidence source {value!s}; use one exact Host-allowed path"
        )
    return None


def require_allowed_path(
    value: str | Path,
    *,
    must_exist: bool = True,
) -> str:
    """Resolve one caller path inside the Host/TraceCite-owned allowlist.

    Relative logical paths are resolved against Host-authorized evidence roots
    and the explicit evidence inventory. This keeps container-specific absolute
    paths out of Agent reasoning while preserving the same access boundary.
    """

    raw = Path(value).expanduser()
    if not raw.is_absolute():
        if any(part == ".." for part in raw.parts):
            raise PermissionError("relative evidence paths cannot contain '..'")
        relative = _unique_relative_match(raw, must_exist=must_exist)
        if relative is not None:
            return str(relative)
        roots = _host_evidence_roots()
        missing = (roots[0] / raw).resolve() if roots else raw.resolve()
        if must_exist:
            raise FileNotFoundError(
                errno.ENOENT,
                "evidence path does not exist in Host-allowed roots",
                str(missing),
            )

    candidate = raw.resolve()
    for root in allowed_roots():
        if candidate == root or root in candidate.parents:
            if must_exist and not candidate.exists():
                raise FileNotFoundError(
                    errno.ENOENT,
                    "evidence path does not exist",
                    str(candidate),
                )
            return str(candidate)
    raise PermissionError(
        f"path is outside TRACECITE_MCP_ALLOWED_ROOTS and managed state: {candidate}"
    )


def available_evidence_sources(
    *,
    limit: int = _MAX_AVAILABLE_SOURCES,
) -> tuple[str, ...]:
    """Return the bounded Host-declared evidence inventory for this task.

    ``TRACECITE_EVIDENCE_FILES`` is an explicit inventory, not an access
    control. Managed TraceCite state files are deliberately never discovered or
    advertised here even though exact Runtime-created snapshot paths may later
    be materialized.
    """

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    configured = os.environ.get("TRACECITE_EVIDENCE_FILES")
    if not configured:
        return ()

    evidence_roots = _host_evidence_roots()
    result: list[str] = []
    seen: set[str] = set()
    for raw in configured.split(os.pathsep):
        item = raw.strip()
        if not item:
            continue
        candidate = Path(item).expanduser().resolve()
        if not _is_within(candidate, evidence_roots):
            continue
        if not candidate.exists() or not candidate.is_file():
            continue
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
        if len(result) >= limit:
            break
    return tuple(result)


def require_safe_glob(value: str) -> str:
    pattern = str(value or "*")
    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise PermissionError("glob must remain inside the selected source root")
    return pattern


__all__ = [
    "allowed_roots",
    "available_evidence_sources",
    "require_allowed_path",
    "require_safe_glob",
]
