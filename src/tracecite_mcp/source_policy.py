"""Server-owner local source access policy."""

from __future__ import annotations

import os
from pathlib import Path


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


def require_allowed_path(value: str | Path) -> str:
    candidate = Path(value).expanduser().resolve()
    for root in allowed_roots():
        if candidate == root or root in candidate.parents:
            return str(candidate)
    raise PermissionError(
        f"path is outside TRACECITE_MCP_ALLOWED_ROOTS: {candidate}"
    )


def require_safe_glob(value: str) -> str:
    pattern = str(value or "*")
    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise PermissionError("glob must remain inside the selected source root")
    return pattern
