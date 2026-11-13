"""Shared personal-path resolver + anchored containment guard (Phase 29 — VAULT-01).

ONE resolver owns every "where does PII live" decision for the v4.0 candidate
vault. Centralizing it here — instead of letting each caller re-derive a
personal/ path — prevents a second privacy boundary from drifting into existence
(locked constraint: the shared resolver rejects symlink/``..`` escapes before any
write). Threats mitigated: T-29-01 (path traversal into/around the vault) and
T-29-03 (regression of the frozen v3.x ground/checklist write-gate anchor).

Two DISTINCT anchors, deliberately kept separate:

* ``repo_personal_root()`` — the FROZEN v3.x write-gate anchor: unconditionally
  ``<repo>/personal`` (resolved), NEVER consulting ``$PR_PERSONAL_DIR``. This is
  what ``cli._personal_root`` (the ``ground``/``checklist`` containment) delegates
  to; its behaviour must stay byte-identical.
* ``personal_root(explicit=None)`` — the NEW v4.0 vault root with full precedence
  (explicit arg > ``$PR_PERSONAL_DIR`` > repo checkout > packaged-install
  ``platformdirs`` fallback). The vault modules use THIS one.

``legacy_personal_dir()`` reproduces ``checklist.personal_dir()`` verbatim (the
relative ``Path("personal")`` default) so that frozen behaviour is centralized
without change.

Design constraints:
* STDLIB + LAZY ``platformdirs`` only — importing this module never requires
  ``platformdirs`` to be installed (it is imported inside the fallback branch
  only), so the resolver loads on a lean install.
* Containment is resolve-THEN-check: ``.resolve()`` collapses symlinks and ``..``
  BEFORE the ``is_within`` comparison, so a symlink under the root that points
  outside is caught.
"""

from __future__ import annotations

import errno
import os
import re
from pathlib import Path


_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(
    value
    for value in (
        errno.EBADF,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if value is not None
)


def fsync_dir(directory: Path) -> None:
    """Durably flush directory entries, failing closed when unsupported."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            raise OSError(errno.EIO, "directory durability unavailable") from None
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
                raise OSError(
                    errno.EIO, "directory durability unavailable") from None
            raise
    finally:
        os.close(descriptor)


def mkdir_durable(directory: Path) -> None:
    """Create missing path components and durably record each new child."""
    missing: list[Path] = []
    cursor = directory
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for child in reversed(missing):
        try:
            child.mkdir()
        except FileExistsError:
            if not child.is_dir():
                raise
            fsync_dir(child.parent)
            continue
        fsync_dir(child.parent)


class PathEscapeError(ValueError):
    """Raised when a requested path would escape its containment root.

    A :class:`ValueError` subclass (mirroring ``checklist.ProfileError``) so the
    CLI can map it to the ``invalid_input`` / exit-2 contract. Raised on: an
    absolute path part, a ``..`` traversal component, a resolved join that lands
    outside the root (including via a symlink), or a candidate id that slugifies
    to the empty string.
    """


def repo_root() -> Path:
    """Return the repository root, anchored at ``crawler/``'s parent.

    ``crawler/paths.py`` lives at ``<repo-root>/crawler/paths.py`` so
    ``Path(__file__).resolve().parents[1]`` is the repo root. Identical anchor to
    the frozen ``cli._personal_root`` (which used its own ``crawler/cli.py``
    ``parents[1]``) — both resolve to the same directory.
    """
    return Path(__file__).resolve().parents[1]


def repo_personal_root() -> Path:
    """FROZEN write-gate anchor: ``<repo-root>/personal`` resolved, UNCONDITIONALLY.

    Never consults ``$PR_PERSONAL_DIR``. This is the exact boundary the v3.x
    ``ground``/``checklist`` write-gate confines rendered output to; it must stay
    byte-identical to the old ``cli._personal_root`` return value.
    """
    return (repo_root() / "personal").resolve()


def legacy_personal_dir() -> Path:
    """Reproduce ``checklist.personal_dir()`` VERBATIM: env override, ``personal`` default.

    Returns ``Path($PR_PERSONAL_DIR)`` when the env var is set, else the RELATIVE
    ``Path("personal")`` — NOT resolved — exactly as the frozen checklist did.
    """
    return Path(os.environ.get("PR_PERSONAL_DIR", "personal"))


def running_from_repo_checkout() -> bool:
    """True iff we are running from a git checkout (``<repo-root>/.git`` exists)."""
    return (repo_root() / ".git").exists()


def personal_root(explicit: "str | os.PathLike[str] | None" = None) -> Path:
    """Resolve the v4.0 personal/vault root, always as a resolved absolute Path.

    Precedence (first match wins):

    1. ``explicit`` argument (caller-supplied override);
    2. ``$PR_PERSONAL_DIR`` environment override;
    3. ``repo_personal_root()`` when :func:`running_from_repo_checkout`;
    4. packaged-install fallback: ``platformdirs.user_data_path("pr-review-agents")
       / "personal"``.

    ``platformdirs`` is imported LAZILY inside branch 4 so this module imports
    even when ``platformdirs`` is absent (lean install / branches 1–3).
    """
    if explicit is not None:
        return Path(explicit).resolve()
    env = os.environ.get("PR_PERSONAL_DIR")
    if env:
        return Path(env).resolve()
    if running_from_repo_checkout():
        return repo_personal_root()
    # Packaged install: no repo checkout → OS-correct per-user data dir.
    import platformdirs  # lazy: only needed off a repo checkout
    return (platformdirs.user_data_path("pr-review-agents") / "personal").resolve()


def is_within(root: "str | os.PathLike[str]", target: "str | os.PathLike[str]") -> bool:
    """True iff *target* resolves to *root* itself or a descendant of it.

    Both operands are ``.resolve()``-d first (collapsing symlinks / ``..``), so
    the comparison is between two fully-resolved absolute paths.
    """
    root_r = Path(root).resolve()
    target_r = Path(target).resolve()
    return target_r == root_r or root_r in target_r.parents


def resolve_within(root: "str | os.PathLike[str]", *parts: str) -> Path:
    """Join *parts* under *root* and return the resolved child, or fail closed.

    Raises :class:`PathEscapeError` when:

    * any part is an absolute path, or
    * any part contains a ``..`` traversal component, or
    * the resolved join is not :func:`is_within` *root* (catches symlink escapes,
      because ``.resolve()`` follows the symlink before the containment check).

    A part whose name merely *starts with* ``..`` (e.g. ``..hidden``) is allowed —
    only a genuine ``..`` path component is a traversal.
    """
    root_r = Path(root).resolve()
    for part in parts:
        p = Path(part)
        if p.is_absolute():
            raise PathEscapeError("absolute path parts are not permitted")
        if ".." in p.parts:
            raise PathEscapeError("'..' traversal is not permitted")
    resolved = root_r.joinpath(*parts).resolve()
    if not is_within(root_r, resolved):
        raise PathEscapeError("resolved path escapes its containment root")
    return resolved


def safe_candidate_id(raw: str) -> str:
    """Slugify an untrusted candidate id to ``[a-z0-9-]``, or fail closed.

    Lowercases, maps every run of non ``[a-z0-9-]`` characters to a single ``-``,
    strips leading/trailing ``-``, and raises :class:`PathEscapeError` on an empty
    result. This guarantees the id can never contain a path separator or ``..``
    traversal, so it is safe to use as a single directory name; it also declines
    to accept raw name/UCI/passport-shaped strings as-is.
    """
    slug = re.sub(r"[^a-z0-9-]+", "-", str(raw).lower()).strip("-")
    if not slug:
        raise PathEscapeError("candidate id slugified to the empty string")
    return slug


def candidate_root(candidate_id: str,
                   explicit: "str | os.PathLike[str] | None" = None) -> Path:
    """Return ``personal_root(explicit)/"candidates"/safe_candidate_id(candidate_id)``.

    The id is slugified first, then joined through :func:`resolve_within` so the
    candidate directory can never escape the personal root.
    """
    return resolve_within(personal_root(explicit),
                          "candidates", safe_candidate_id(candidate_id))
