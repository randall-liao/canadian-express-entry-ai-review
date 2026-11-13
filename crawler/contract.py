"""Versioned machine-readable JSON output contract for ``corpus-crawler`` (AGENT-01).

This module defines the *stable* envelope every subcommand emits on stdout when
the global ``--json`` flag is supplied, so an external CLI agent can shell out and
``json.loads(stdout)`` deterministically instead of scraping human text.

The envelope has exactly five top-level keys (field names are STABLE — Plan 2's
``CONTRACT.md`` is the canonical reference, mirrored here)::

    {
      "schema_version": "1.0",        # bumped on any breaking schema change
      "ok": true | false,             # false iff an execution error occurred
      "command": "crawl" | "apply-verdicts" | "completeness" | "report" | "index" | "search" | "ground" | "checklist" | "vault",
      "result": { ... } | null,       # per-command payload on success, else null
      "error":  { "type": str, "message": str } | null  # set iff ok is false
    }

Contract rules:

* In ``--json`` mode the command prints EXACTLY ONE ``json.dumps`` object to
  stdout (``ensure_ascii=False``) and routes every human/progress/log line to
  stderr. ``json.loads(stdout)`` must succeed.
* A *verdict* of fail (e.g. ``report`` finding a failing corpus) is NOT an
  execution error: it is ``ok:true`` with ``result.verdict == "fail"`` and the
  established exit code 1. ``error`` is reserved for execution failures (missing
  optional dependency, bad input path).
* Failures are machine-readable: ``ok:false`` plus an ``error`` object and a
  documented non-zero exit code (see ``EXIT_*`` below).

No third-party dependencies — pure stdlib so the contract adds no install
surface to the lean core.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Bump ONLY on a breaking change to the envelope or per-command result shape.
SCHEMA_VERSION = "1.0"

# --- Error type constants (the machine-readable ``error.type`` values) -------
# Optional crawl driver (crawl4ai) absent on a lean install.
MISSING_DEPENDENCY = "missing_dependency"
# Caller-supplied input is unusable (e.g. corpus dir missing / not a directory,
# or "no live docs to sample").
INVALID_INPUT = "invalid_input"
# Last-resort bucket for any UNEXPECTED exception that escapes the compute layer
# in --json mode (e.g. a corrupt JSON file inside the corpus). The catch-all in
# ``cli.main`` converts such failures into this machine-readable envelope so
# stdout is NEVER an empty/traceback stream when ``--json`` was requested.
INTERNAL_ERROR = "internal_error"

# --- Exit-code constants -----------------------------------------------------
# 0 = ok, 1 = report verdict not pass (still ok:true). These name the failure codes:
EXIT_INVALID_INPUT = 2
EXIT_MISSING_DEPENDENCY = 3
# Any otherwise-unhandled exception in --json mode → ok:false / internal_error.
EXIT_INTERNAL_ERROR = 4


def envelope(command: str,
             result: dict[str, Any] | None = None,
             error: tuple[str, str] | None = None) -> dict[str, Any]:
    """Build the stable five-key contract envelope.

    Args:
        command: subcommand name (``crawl``/``apply-verdicts``/``completeness``/``report``/``index``/``search``/``ground``/``checklist``/``vault``).
        result: success payload dict, or ``None`` on error.
        error: ``(type, message)`` tuple on failure, or ``None`` on success.

    ``ok`` is derived solely from ``error`` (``ok = error is None``). On error
    ``result`` is forced to ``None``; on success ``error`` is ``None``.
    """
    err_obj: dict[str, str] | None = None
    if error is not None:
        err_type, err_message = error
        err_obj = {"type": err_type, "message": err_message}
    ok = err_obj is None
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "command": command,
        "result": result if ok else None,
        "error": err_obj,
    }


def emit(obj: dict[str, Any]) -> None:
    """Write exactly one ``json.dumps`` line to stdout and nothing else.

    ``ensure_ascii=False`` keeps non-ASCII characters human-readable; the result
    is still ``json.loads``-able. The trailing newline is the only extra byte.
    """
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
