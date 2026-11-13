#!/usr/bin/env python3
"""Publish-safety checker (SAFE-02).

A repeatable, pure-stdlib check that any maintainer (or CI later) can run before
sharing this repository publicly. It scans only the git-tracked tree for:

* machine-specific absolute paths (home dirs, project venv, pinned interpreter),
* secret patterns (private-key headers, AWS access keys, assigned credentials),
* tracked personal/trial corpora (content that must stay local).

It prints a per-violation ``file:line: category: snippet`` report and exits
non-zero on any violation; on a clean tree it prints a publish-safe message and
exits 0.

The scan is always pinned to the git repository root, so results are identical
no matter which subdirectory the checker is invoked from::

    python scripts/check_publish_safe.py

Per-line escape hatch: append ``# publish-safe: allow`` to a line to whitelist a
legitimate reference. The only excluded tree is ``.github/`` — the vendored,
third-party GSD framework, which carries generic placeholder paths (e.g.
``/Users/john``) and no real machine paths. The project-authored ``.planning/``
tree IS scanned, because it can contain real developer paths that must not ship
publicly. The checker also self-excludes its own source and the project's test
trees (``scripts/tests/`` and ``crawler/tests/``) — they literally contain the
tokens being hunted (abs-path / secret fixtures asserting the guards catch them).

HTTP(S) URL pathnames can legitimately contain ``/home/``. Only those pathname
spans are exempt from the home-directory patterns; local text, URL queries and
fragments, fixed machine markers, and all credential patterns remain scanned.

Pure stdlib only: subprocess, re, sys, os, dataclasses, urllib.parse.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

# --- Exclusions -------------------------------------------------------------

# Vendored third-party framework: generic placeholder paths only (verified no
# real machine paths). Scoped to the exact ``.github/`` directory prefix so it
# cannot accidentally match e.g. ``x.github_notes``. Project-authored
# ``.planning/`` is deliberately NOT excluded — it is scanned like any other
# publishable content.
EXCLUDE_PREFIXES = (".github/",)
SELF_EXCLUDE_FILES = ("scripts/check_publish_safe.py",)
# Project test trees legitimately contain the hunted tokens as fixtures
# (abs-path / secret strings asserting the guards catch them).
SELF_EXCLUDE_PREFIXES = ("scripts/tests/", "crawler/tests/")
CORPORA_PREFIXES = ("trial/", "personal/", "corpus_new/")

# --- Vault artifact detection (VAULT-04) ------------------------------------
# The private candidate-vault namespace segment. personal/candidates/... is
# covered by BOTH the CORPORA_PREFIXES scan (any tracked personal/...) and this
# category — defense in depth, and it also catches a stray "candidates" segment
# anywhere else in the tree.
VAULT_NAMESPACE_SEGMENT = "candidates"
# Vault DB + WAL/SHM sidecar basename suffixes.
VAULT_DB_SUFFIXES = (
    ".sqlite", ".sqlite-wal", ".sqlite-shm", ".db-wal", ".db-shm",
)
# Vault subtrees that hold raw docs / rendered pages / OCR text / private reports.
# Phase 30 extraction writes rendered page images under ``files/rendered/`` and
# extracted/OCR text under ``files/text/`` — listed explicitly here (in addition
# to the bare ``rendered/``/``text/`` catch-alls) so coverage of the engine's
# exact artifact paths is self-documenting. Phase 32 writes the evidence-bearing
# CRS audit report (``<run_id>.json`` + ``<run_id>.md``) under ``output/crs-audit/``
# — a vault-only artifact type covered by the same VAULT_ARTIFACT category.
VAULT_SUBTREES = (
    "files/raw/", "files/rendered/", "files/text/",
    "rendered/", "pages/", "text/", "output/crs-audit/", "output/remediation/", "output/review-packet/",
)
# Document / render / OCR / report extensions — flagged ONLY inside a vault
# subtree, so ordinary repo .md/.png/.json files are NOT false-positives.
VAULT_ARTIFACT_EXTS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".txt", ".json", ".md",
)

# Append this marker to a line to suppress a legitimate match on that line.
ALLOW_MARKER = "# publish-safe:" " allow"

# --- Detection patterns -----------------------------------------------------

_HOME_PATH_PATTERNS = (
    # Home directories for any username shape (capital, digit, underscore),
    # case-insensitive, on Linux and macOS, plus root's home.
    re.compile(r"(?i)/home/[^/\s'\"]"),
    re.compile(r"(?i)/Users/[^/\s'\"]"),
    re.compile(r"(?i)/root/"),
)
ABS_PATH_PATTERNS = _HOME_PATH_PATTERNS + (
    re.compile(r"pr-ai-venv"),
    # Pinned system interpreter, with or without a minor version.
    re.compile(r"/usr/bin/python3(?:\.\d+)?"),
)

# Stop at Markdown/HTML delimiters rather than swallowing adjacent local text.
_HTTP_URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>\"'`()\[\]\\]+")

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # AWS long-term (AKIA) and STS temporary (ASIA) access key ids.
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    # GitHub personal access tokens (classic ghp_ and fine-grained pat).
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    # Slack tokens.
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    # Bearer tokens in an Authorization header / value.
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    # JWT shape: three base64url segments separated by dots.
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"),
    # Assigned credential, value optionally quoted (catches .env-style
    # unquoted assignments). Key must look like a credential field.
    re.compile(
        r"(?i)(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|token|password)"
        r"\s*[:=]\s*['\"]?([^'\"\s]{12,})['\"]?"
    ),
)

# Categories scanned line-by-line, in deterministic report order.
_LINE_CATEGORIES = (
    ("ABS_PATH", ABS_PATH_PATTERNS),
    ("SECRET", SECRET_PATTERNS),
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    category: str
    snippet: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.category}: {self.snippet}"


def is_excluded(path: str) -> bool:
    """True if *path* is outside the publishable surface and must be skipped."""
    if path in SELF_EXCLUDE_FILES:
        return True
    if path.startswith(SELF_EXCLUDE_PREFIXES):
        return True
    if path.startswith(EXCLUDE_PREFIXES):
        return True
    return False


def _http_path_spans(line: str) -> list[tuple[int, int]]:
    """Locate HTTP(S) pathnames, excluding userinfo, queries, and fragments."""
    spans = []
    for match in _HTTP_URL_RE.finditer(line):
        try:
            parts = urlsplit(match.group())
            if not parts.hostname or parts.username is not None or parts.password is not None:
                continue
        except ValueError:
            continue
        start = match.start() + len(parts.scheme) + 3 + len(parts.netloc)
        spans.append((start, start + len(parts.path)))
    return spans


def scan_text(path: str, text: str) -> list:
    """Scan *text* (the contents of *path*) for abs-path and secret matches.

    Returns a list of :class:`Violation`. Excluded paths always return ``[]``.
    A line carrying the allow marker is skipped. At most one violation per
    category per line is emitted, in (ABS_PATH, SECRET) order.
    """
    if is_excluded(path):
        return []
    violations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        snippet = line.strip()
        # A home pattern consumes the next character, even '?' in /home/?L=1.
        # Its start identifies the pathname without masking a later query leak.
        http_paths = _http_path_spans(line)
        for category, patterns in _LINE_CATEGORIES:
            if any(
                not (
                    category == "ABS_PATH"
                    and pattern in _HOME_PATH_PATTERNS
                    and any(start <= match.start() < end for start, end in http_paths)
                )
                for pattern in patterns
                for match in pattern.finditer(line)
            ):
                violations.append(Violation(path, lineno, category, snippet))
    return violations


def scan_path_name(path: str) -> list:
    """Flag tracked personal/trial corpora purely from the path name."""
    if is_excluded(path):
        return []
    if path.startswith(CORPORA_PREFIXES):
        return [Violation(path, 0, "TRACKED_CORPORA", path)]
    return []


def scan_vault_artifact(path: str) -> list:
    """Flag any tracked candidate-vault artifact purely from the path name (VAULT-04).

    A tracked path is a ``VAULT_ARTIFACT`` when ANY of:

    * (a) a path SEGMENT equals ``candidates`` (the private vault namespace —
      defense in depth even outside ``personal/``);
    * (b) the basename is a vault DB or WAL/SHM sidecar (``vault.sqlite``,
      ``*.sqlite``, ``*.sqlite-wal``, ``*.sqlite-shm``, ``*.db-wal``, ``*.db-shm``);
    * (c) the path lies under a vault subtree (``files/raw/``, ``rendered/``,
      ``pages/``, ``text/``, ``output/crs-audit/``) AND carries a
      document/render/OCR/report extension — scoped to those subtrees ONLY, so an
      ordinary repo ``.md``/``.png``/``.json`` elsewhere is NOT flagged.

    This complements ``scan_path_name`` (a tracked ``personal/candidates/…`` file
    trips BOTH ``TRACKED_CORPORA`` and ``VAULT_ARTIFACT``).
    """
    if is_excluded(path):
        return []
    segments = path.split("/")
    basename = segments[-1].lower()
    # (a) the private vault namespace segment, anywhere in the path.
    if VAULT_NAMESPACE_SEGMENT in segments:
        return [Violation(path, 0, "VAULT_ARTIFACT", path)]
    # (b) a vault DB or its WAL/SHM sidecar, by basename suffix.
    if basename.endswith(VAULT_DB_SUFFIXES):
        return [Violation(path, 0, "VAULT_ARTIFACT", path)]
    # (c) a vault-subtree render/OCR/report file (scoped to the subtrees only).
    anchored = "/" + path
    if (any(("/" + sub) in anchored for sub in VAULT_SUBTREES)
            and basename.endswith(VAULT_ARTIFACT_EXTS)):
        return [Violation(path, 0, "VAULT_ARTIFACT", path)]
    return []


def exit_code(violations) -> int:
    """Map a violation list to a process exit code (1 if any, else 0)."""
    return 1 if violations else 0


def repo_root() -> str:
    """Return the absolute path of the git repository root.

    Raises ``RuntimeError`` (fail closed) if git is unavailable or the cwd is
    not inside a git repository.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "could not locate the git repository root "
            "(is this a git repo?)"
        ) from exc
    root = out.stdout.strip()
    if not root:
        raise RuntimeError("git returned an empty repository root")
    return root


def tracked_files(root: str) -> list:
    """Return git-tracked files as repo-root-relative paths.

    The scan is pinned to *root* via ``git -C`` so the returned paths always
    match the exclusion prefixes regardless of the caller's cwd. Raises
    ``RuntimeError`` (fail closed) on any git failure.
    """
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "could not enumerate tracked files (is this a git repo?)"
        ) from exc
    return [line for line in out.stdout.splitlines() if line]


def decode_for_scan(raw: bytes):
    """Return decoded text to line-scan, or ``None`` for genuinely binary data.

    A NUL byte is the standard heuristic for binary content; such files are
    skipped. Everything else is decoded tolerantly with ``errors="replace"`` so
    a text file carrying a single stray non-UTF-8 byte is STILL scanned (WR-03)
    rather than silently dropped.
    """
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def main() -> int:
    try:
        root = repo_root()
        files = tracked_files(root)
    except RuntimeError as exc:
        print(f"\u2717 publish-safety check could not run: {exc}", file=sys.stderr)
        return 2
    violations = []
    scanned = 0
    for path in files:
        if is_excluded(path):
            continue
        scanned += 1
        violations.extend(scan_path_name(path))
        violations.extend(scan_vault_artifact(path))
        abspath = os.path.join(root, path)
        try:
            with open(abspath, "rb") as handle:
                raw = handle.read()
        except OSError:
            # Missing/unreadable file: nothing to line-scan.
            continue
        text = decode_for_scan(raw)
        if text is None:
            continue
        violations.extend(scan_text(path, text))

    if violations:
        for v in violations:
            print(v.render())
        print(
            f"\u2717 publish-unsafe: {len(violations)} violation(s) across "
            f"{scanned} tracked files scanned"
        )
        return 1

    print(f"\u2713 publish-safe: {scanned} tracked files scanned, 0 violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
