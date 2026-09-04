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


def require_allowed_path(
    value: str | Path,
    *,
    must_exist: bool = True,
) -> str:
    """Resolve one caller path inside the Host/TraceCite-owned allowlist."""

    candidate = Path(value).expanduser().resolve()
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
        if not any(candidate == root or root in candidate.parents for root in evidence_roots):
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
