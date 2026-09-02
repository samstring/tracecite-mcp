"""Server-owner local source access policy."""

from __future__ import annotations

import errno
import os
from pathlib import Path


_MAX_AVAILABLE_SOURCES = 50


def allowed_roots() -> tuple[Path, ...]:
    """Return local roots that MCP evidence tools may access.

    The default is the MCP process working directory. Hosts can widen the
    policy with TRACECITE_MCP_ALLOWED_ROOTS using the platform path separator.
    """
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


def require_allowed_path(
    value: str | Path,
    *,
    must_exist: bool = True,
) -> str:
    """Resolve one caller path inside the Host allowlist.

    Permission roots and task evidence inventory are deliberately separate:
    this function never scans an allowed root to discover evidence.
    """

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
        f"path is outside TRACECITE_MCP_ALLOWED_ROOTS: {candidate}"
    )


def available_evidence_sources(
    *,
    limit: int = _MAX_AVAILABLE_SOURCES,
) -> tuple[str, ...]:
    """Return the bounded Host-declared evidence inventory for this task.

    ``TRACECITE_EVIDENCE_FILES`` is an explicit inventory, not an access
    control. Values use the platform path separator (``os.pathsep``). Entries
    are de-duplicated in Host order and are returned only when they currently
    exist and also fall inside ``TRACECITE_MCP_ALLOWED_ROOTS``. The function
    never walks directories or infers additional files from allowed roots.
    """

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    configured = os.environ.get("TRACECITE_EVIDENCE_FILES")
    if not configured:
        return ()

    result: list[str] = []
    seen: set[str] = set()
    for raw in configured.split(os.pathsep):
        item = raw.strip()
        if not item:
            continue
        try:
            resolved = require_allowed_path(item, must_exist=False)
        except PermissionError:
            # Misconfigured inventory entries must not widen the MCP boundary or
            # leak paths outside the Host's explicit allowlist.
            continue
        candidate = Path(resolved)
        if not candidate.exists() or not candidate.is_file():
            continue
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
