"""Shared exact-shape validation for PII-light private-output locators."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import StringConstraints


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

AuditRunId = Annotated[
    str,
    StringConstraints(pattern=r"^aud_[0-9a-f]{12}$"),
]
RemediationRunId = Annotated[
    str,
    StringConstraints(pattern=r"^rem_[0-9a-f]{12}$"),
]
PacketRunId = Annotated[
    str,
    StringConstraints(pattern=r"^pkt_[0-9a-f]{12}$"),
]
MecRunId = Annotated[
    str,
    StringConstraints(pattern=r"^mec_[0-9a-f]{32}$"),
]


def require_exact_output_locator(
    value: str,
    *components: str,
) -> str:
    """Require exactly one relative POSIX ``output/...`` locator shape.

    Callers supply model-derived components, so equality simultaneously rejects
    URI, drive, UNC, traversal, candidate-root, extension, and extra-segment
    variants without scanning arbitrary candidate strings.
    """
    if not components or any(
        not _SAFE_COMPONENT.fullmatch(component)
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        for component in components
    ):
        raise ValueError("public locator components must be safe path segments")
    expected = "/".join(("output", *components))
    if value != expected:
        raise ValueError(
            f"private_output_path must exactly match {expected!r}"
        )
    return value
