"""Private pytest reporting plugin for the authoritative conformance runner."""

from __future__ import annotations

import json
import os
from pathlib import Path


_REPORT_ENV = "PR_CONFORMANCE_REPORT"
_collected: list[str] = []
_deselected: list[str] = []
_reports: list[dict[str, object]] = []


def pytest_sessionstart(session) -> None:
    """Reset process-local state before collection."""
    del session
    _collected.clear()
    _deselected.clear()
    _reports.clear()


def pytest_collection_finish(session) -> None:
    """Record the final selected node manifest in pytest's stable order."""
    _collected.extend(item.nodeid for item in session.items)


def pytest_deselected(items) -> None:
    """Record every node removed by a selector or plugin."""
    _deselected.extend(item.nodeid for item in items)


def pytest_runtest_logreport(report) -> None:
    """Record setup/call/teardown outcomes without test output or paths."""
    _reports.append(
        {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": bool(getattr(report, "wasxfail", False)),
            "subtest": hasattr(report, "context"),
        }
    )


def pytest_sessionfinish(session, exitstatus) -> None:
    """Persist one machine-readable report for the parent runner."""
    del session
    destination = os.environ.get(_REPORT_ENV)
    if not destination:
        return
    Path(destination).write_text(
        json.dumps(
            {
                "collected": _collected,
                "deselected": _deselected,
                "reports": _reports,
                "exitstatus": int(exitstatus),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
