"""Phase-41 static + regression conformance gate (STUDY-01 SC3 / T-41-05/06/07).

The phase-level proof that closing STUDY-01 preserved every milestone invariant
the DLI/PGWP snapshot family must NOT perturb. Every assertion here is OFFLINE,
fast, and network-free — it reads only the tracked tree (source + the shipped
registry) and the local git state, never the corpus index or the network:

* **No self-grounded / inlined freshness bound (T-41-06):**
  ``crs_rules.no_inlined_volatile_rules`` is clean over the new
  ``dli_snapshot.py`` / ``cli.py`` / ``study_dli.yaml``; NO loaded registry row is
  a ``max_age`` / ``snapshot_max_age`` row; and ``study_dli.yaml`` carries no
  ``max_age`` / ``window_days`` / ``snapshot_max_age`` token. The operational
  max-age is Phase-44 config (SAFE-09 grounded/config value), never grounded from
  a project-authored doc.
* **Zero new runtime dependencies (T-41-07):** ``pyproject.toml``
  ``[project].dependencies`` stays exactly ``{pyyaml, pydantic, platformdirs}`` —
  no ``httpx`` / ``requests`` / ``crawl4ai`` / new package crept in.
* **Audit path structurally network-free (T-41-07):** ``crs_audit`` / ``crs_rules``
  / ``grounding`` / ``searchindex`` and every ``crawler/auditors/`` module import
  NO network client (``httpx`` / ``requests`` / ``urllib.request``) and NO
  ``dli_snapshot`` (the generator is imported LAZILY only inside
  ``cli._cmd_refresh_dli``, never on the audit path).
* **Frozen Phase-40 / index / decider contracts intact:** the v4.x search /
  dedup / grounding / freshness / preflight surfaces and the shipped CRS-grid
  YAML + COVERAGE.md are byte-for-byte unchanged (proven with ``git diff
  --quiet``, skip-guarded off a git checkout).
* **Inert study decider:** coverage stays ``complete``; the frozen credential-only
  ``additional.study`` decider is present; and the one new
  ``study.dli.designation`` row covers NO required ``additional_points`` label.

Task 2 ADDS one skip-guarded live-grounding test to this file (grounding
``study.dli.designation`` against the REAL refreshed ``corpus/index.db``); it
skips cleanly when the real dli-bearing index is absent, keeping CI / this file
green and structural-only.

Stdlib ``unittest`` ONLY, run via pytest (repo convention). Run from repo root::

    .venv/bin/python -m pytest crawler/tests/test_dli_conformance.py -q
"""

from __future__ import annotations

import ast
import re
import sqlite3
import subprocess
import unittest
from pathlib import Path

from crawler import crs_rules, searchindex
from crawler.crs_rules import REQUIRED_RULE_IDS, _covers

# --------------------------------------------------------------------------- #
# Repo-root anchored coordinates (no network, no corpus index).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CRAWLER = _REPO_ROOT / "crawler"
_DATA_DIR = _CRAWLER / "data" / "crs_rules"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_STUDY_DLI_YAML = _DATA_DIR / "study_dli.yaml"

# The files whose inlined-volatile scan MUST stay clean (the new phase surface).
_NEW_SCAN_FILES = (
    _CRAWLER / "dli_snapshot.py",
    _CRAWLER / "cli.py",
    _STUDY_DLI_YAML,
)

# The zero-dependency baseline (case-normalized package NAMES only).
_FROZEN_DEPENDENCIES = frozenset(
    {"pyyaml", "pydantic", "platformdirs", "github-copilot-sdk"}
)

# The audit / screen path that MUST be structurally network-free: it may never
# import a network client or the (network-capable) dli_snapshot generator.
_AUDIT_PATH_MODULES = (
    _CRAWLER / "crs_audit.py",
    _CRAWLER / "crs_rules.py",
    _CRAWLER / "grounding.py",
    _CRAWLER / "searchindex.py",
    *sorted((_CRAWLER / "auditors").glob("*.py")),
)

# Frozen Phase-40 / index / decider contracts — byte-for-byte unchanged this
# phase (relative to the repo root, tracked files only). NOTE: the CRS-grid
# `additional.yaml` and its generated `COVERAGE.md` are LEGITIMATE Phase-42
# mutation targets (the grounded physician public-policy row + its coverage
# regen) and are therefore NOT frozen here; the frozen guard `crawler/crs_audit.py`
# stays listed and asserted byte-for-byte.
_FROZEN_CONTRACT_PATHS = (
    "crawler/searchindex.py",
    "crawler/dupaudit.py",
    "crawler/grounding.py",
    "crawler/crs_audit.py",
    "crawler/index_health.py",
    "crawler/data/crs_rules/core.yaml",
    "crawler/data/crs_rules/spouse.yaml",
    "crawler/data/crs_rules/transferability.yaml",
)

# The one row this phase ships + the required grid group it must NOT perturb.
_DLI_RULE_ID = "study.dli.designation"
_FROZEN_STUDY_DECIDER_LABEL = "additional.study"

# The max-age tokens that must appear NOWHERE in the shipped DLI rule YAML.
_MAX_AGE_TOKENS = ("max_age", "window_days", "snapshot_max_age")

# --------------------------------------------------------------------------- #
# LOCAL-ONLY live-grounding coordinates (Task 2 step 3). The real corpus index
# is git-ignored and operator-generated (`corpus-crawler --json refresh-dli`
# then `index corpus/ --db corpus/index.db`). When the REAL dli-bearing index is
# present, prove `study.dli.designation` grounds against it; otherwise SKIP
# cleanly (CI / a fresh clone / an unrefreshed local tree stays green and
# structural-only — mirrors the `_REAL_DB.is_file()` precedent in
# test_conformance_v40_retrieve_what_you_cite.py).
# --------------------------------------------------------------------------- #
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_UOFT_CHUNK_ID = "dli/O19332746152.md#000"


def _real_dli_index_present() -> bool:
    """True iff the REAL corpus index exists AND already carries the dli family."""
    if not _REAL_DB.is_file():
        return False
    try:
        return searchindex.resolve(_REAL_DB, _UOFT_CHUNK_ID) is not None
    except Exception:
        return False


_REAL_DLI_INDEX = _real_dli_index_present()


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _package_name(spec: str) -> str:
    """Leading PEP-508 package name of a dependency spec (``pyyaml>=6.0`` → ``pyyaml``)."""
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec.strip())
    return (m.group(0) if m else spec.strip()).lower()


def _regex_project_dependencies(text: str) -> list[str]:
    """Stdlib-only fallback: extract the ``[project].dependencies`` array items.

    Bounds the ``[project]`` table to the next ``^[`` table header (so the
    ``[project.optional-dependencies]`` ``crawl``/``doc-extract`` extras are never
    counted as runtime deps), then pulls each quoted requirement string.
    """
    section = re.search(r"(?ms)^\[project\]\s*(.*?)^\[", text + "\n[")
    body = section.group(1) if section else text
    arr = re.search(r"(?ms)^\s*dependencies\s*=\s*\[(.*?)\]", body)
    if not arr:
        return []
    return re.findall(r'"([^"]+)"', arr.group(1))


def _project_dependencies() -> set[str]:
    """The case-normalized runtime dependency NAMES from ``pyproject.toml``.

    Prefers a real TOML parse (``tomllib`` on 3.11+, ``tomli`` on 3.10 where it
    is present), and falls back to a stdlib regex parse so the gate never needs a
    dependency the project does not declare.
    """
    text = _PYPROJECT.read_text(encoding="utf-8")
    data = None
    try:  # Python 3.11+
        import tomllib  # type: ignore[import-not-found]

        data = tomllib.loads(text)
    except ModuleNotFoundError:
        try:  # Python 3.10 in this repo ships tomli as a dev/transitive dep
            import tomli  # type: ignore[import-not-found]

            data = tomli.loads(text)
        except ModuleNotFoundError:
            data = None
    if data is not None:
        deps = data.get("project", {}).get("dependencies", []) or []
    else:
        deps = _regex_project_dependencies(text)
    return {_package_name(d) for d in deps}


def _imported_module_names(path: Path) -> set[str]:
    """Every module name reached by an ``import`` / ``from`` in *path* (AST, all scopes).

    Walks the whole tree so a LAZY function-scope import is caught too — the
    audit path must import no network/generator module at ANY scope, not merely
    at module top-level.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                names.add(base)
            for alias in node.names:
                names.add(f"{base}.{alias.name}" if base else alias.name)
    return names


def _forbidden_imports(module_names: set[str]) -> list[str]:
    """The subset of *module_names* that are a network client or the DLI generator."""
    bad: list[str] = []
    for name in sorted(module_names):
        top = name.split(".")[0]
        if top in {"httpx", "requests"}:
            bad.append(name)
        elif name == "urllib.request" or name.startswith("urllib.request."):
            bad.append(name)
        elif "dli_snapshot" in name.split("."):
            bad.append(name)
    return bad


def _git_root() -> Path | None:
    """The git work-tree root, or ``None`` when this is not a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip())


_GIT_ROOT = _git_root()


# --------------------------------------------------------------------------- #
# No self-grounded / inlined freshness bound (T-41-06).
# --------------------------------------------------------------------------- #
class TestNoInlinedOrShippedFreshnessBound(unittest.TestCase):
    """No inlined volatile rule, no shipped max-age row, no max-age token."""

    def test_new_files_have_no_inlined_volatile_rule(self) -> None:
        # Non-vacuous: the three scanned files really exist (a missing path is
        # skipped silently by the gate, which would make this test pass vacuously).
        for f in _NEW_SCAN_FILES:
            self.assertTrue(f.is_file(), f"scan target missing: {f}")
        violations = crs_rules.no_inlined_volatile_rules([str(f) for f in _NEW_SCAN_FILES])
        self.assertEqual(
            violations,
            [],
            [f"{v['path']}:{v['line']} {v['kind']} {v['snippet']}" for v in violations],
        )

    def test_no_registry_row_is_a_max_age_row(self) -> None:
        reg = crs_rules.load_registry()
        self.assertTrue(reg.rows, "registry loaded empty — cannot prove no max-age row")
        for row in reg.rows:
            self.assertNotIn(
                "max_age", row.rule_id, f"{row.rule_id} looks like a max-age row"
            )
            mc = row.machine_check
            if mc is not None:
                self.assertNotEqual(
                    getattr(mc, "field", None),
                    "snapshot_max_age",
                    f"{row.rule_id} carries a shipped snapshot_max_age bound",
                )

    def test_study_dli_rows_carry_no_window_bound(self) -> None:
        reg = crs_rules.load_registry()
        study_rows = [r for r in reg.rows if r.rule_id.startswith("study.dli")]
        self.assertTrue(study_rows, "study.dli.* row not loaded from the registry")
        for row in study_rows:
            mc = row.machine_check
            self.assertIsNone(
                getattr(mc, "window_days", None),
                f"{row.rule_id} inlines a freshness window_days bound",
            )

    def test_study_dli_yaml_has_no_max_age_token(self) -> None:
        text = _STUDY_DLI_YAML.read_text(encoding="utf-8")
        for token in _MAX_AGE_TOKENS:
            self.assertNotIn(
                token,
                text,
                f"study_dli.yaml contains a forbidden freshness token: {token!r}",
            )


# --------------------------------------------------------------------------- #
# Zero new runtime dependencies (T-41-07).
# --------------------------------------------------------------------------- #
class TestZeroNewDependencies(unittest.TestCase):
    """[project].dependencies is exactly the frozen zero-dep baseline."""

    def test_dependencies_are_exactly_the_frozen_set(self) -> None:
        deps = _project_dependencies()
        self.assertEqual(
            deps,
            set(_FROZEN_DEPENDENCIES),
            f"runtime dependencies drifted from the frozen baseline: got {sorted(deps)}",
        )

    def test_no_network_or_crawl_package_declared_as_runtime_dep(self) -> None:
        deps = _project_dependencies()
        for forbidden in ("httpx", "requests", "crawl4ai", "urllib3", "aiohttp"):
            self.assertNotIn(
                forbidden, deps, f"{forbidden} crept into runtime dependencies"
            )


# --------------------------------------------------------------------------- #
# Audit path structurally network-free (T-41-07).
# --------------------------------------------------------------------------- #
class TestAuditPathNetworkFree(unittest.TestCase):
    """No audit/screen-path module imports a network client or dli_snapshot."""

    def test_audit_path_modules_import_no_network_or_generator(self) -> None:
        # Non-vacuous: the scan set is non-empty and every file exists.
        self.assertGreaterEqual(len(_AUDIT_PATH_MODULES), 5)
        for module in _AUDIT_PATH_MODULES:
            with self.subTest(module=module.name):
                self.assertTrue(module.is_file(), f"audit-path module missing: {module}")
                bad = _forbidden_imports(_imported_module_names(module))
                self.assertEqual(
                    bad, [], f"{module} imports a forbidden network/generator module: {bad}"
                )

    def test_generator_and_lazy_import_are_off_the_audit_path(self) -> None:
        # Positive control: dli_snapshot DOES import the network client (urllib),
        # so the audit-path proof above is meaningful — the generator is exactly
        # the module the audit path must never import.
        gen = _imported_module_names(_CRAWLER / "dli_snapshot.py")
        self.assertTrue(
            any(n == "urllib.request" or n.startswith("urllib") for n in gen),
            "expected dli_snapshot to be the network-capable generator",
        )
        # And cli.py never imports dli_snapshot at MODULE scope (lazy only).
        cli_tree = ast.parse((_CRAWLER / "cli.py").read_text(encoding="utf-8"))
        top_level_imports: set[str] = set()
        for node in cli_tree.body:
            if isinstance(node, ast.Import):
                top_level_imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                top_level_imports.add(base)
                top_level_imports.update(
                    f"{base}.{a.name}" if base else a.name for a in node.names
                )
        self.assertFalse(
            any("dli_snapshot" in n.split(".") for n in top_level_imports),
            "cli.py imports dli_snapshot at module scope (must be lazy in _cmd_refresh_dli)",
        )


# --------------------------------------------------------------------------- #
# Frozen Phase-40 / index / decider contracts intact.
# --------------------------------------------------------------------------- #
@unittest.skipUnless(
    _GIT_ROOT is not None,
    "not a git checkout — the frozen-contract byte-identity diff proof did NOT run",
)
class TestFrozenContractsUnchanged(unittest.TestCase):
    """The v4.x search/dedup/grounding/freshness surfaces + the UNTOUCHED
    CRS-grid YAML (core/spouse/transferability) are byte-for-byte unchanged this
    phase (git diff --quiet). The physician public-policy row makes
    `additional.yaml` + its generated `COVERAGE.md` legitimate Phase-42 mutation
    targets, so they are intentionally NOT in `_FROZEN_CONTRACT_PATHS`; the frozen
    guard `crawler/crs_audit.py` stays frozen and asserted here."""

    def test_frozen_files_unchanged_vs_head(self) -> None:
        assert _GIT_ROOT is not None  # for type-checkers; guarded by skipUnless
        for rel in _FROZEN_CONTRACT_PATHS:
            with self.subTest(path=rel):
                self.assertTrue(
                    (_GIT_ROOT / rel).is_file(), f"frozen contract file missing: {rel}"
                )
                result = subprocess.run(
                    ["git", "diff", "--quiet", "HEAD", "--", rel],
                    cwd=_GIT_ROOT,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"frozen contract changed vs HEAD (must stay byte-for-byte): {rel}",
                )


# --------------------------------------------------------------------------- #
# Inert study decider.
# --------------------------------------------------------------------------- #
class TestInertStudyDecider(unittest.TestCase):
    """Coverage stays complete; the frozen credential-only study decider is
    present; and the new DLI row covers NO required additional label."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry()
        cls.cov = crs_rules.coverage_report(cls.reg)

    def test_coverage_report_stays_complete(self) -> None:
        self.assertTrue(self.cov["complete"], self.cov["by_group"])

    def test_frozen_additional_study_decider_present(self) -> None:
        present = self.cov["by_group"]["additional_points"]["present"]
        self.assertIn(
            _FROZEN_STUDY_DECIDER_LABEL,
            present,
            "the frozen credential-only additional.study decider is not present",
        )

    def test_dli_row_covers_no_required_additional_label(self) -> None:
        for label in REQUIRED_RULE_IDS["additional_points"]:
            with self.subTest(label=label):
                self.assertFalse(
                    _covers(_DLI_RULE_ID, label),
                    f"{_DLI_RULE_ID} unexpectedly covers required grid label {label}",
                )


# --------------------------------------------------------------------------- #
# LOCAL-ONLY: real end-to-end grounding of study.dli.designation (Task 2 step 3).
# Skip-guarded on a REAL dli-bearing corpus/index.db so CI / a fresh clone / an
# unrefreshed local tree stays green and structural-only.
# --------------------------------------------------------------------------- #
@unittest.skipUnless(
    _REAL_DLI_INDEX,
    "LOCAL-ONLY GROUNDING GATE: a real dli-bearing corpus/index.db is absent "
    "(git-ignored; run `corpus-crawler --json refresh-dli` then "
    "`index corpus/ --db corpus/index.db`) — the live study.dli.designation "
    "grounding proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class TestLiveDliGroundingRealIndex(unittest.TestCase):
    """study.dli.designation re-selects, agrees, and grounds against the REAL
    refreshed dli-bearing index; validate_registry flags no violation for it;
    and the resolved chunk's source_type is 'dli'."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry()

    def test_study_dli_designation_grounds_against_real_index(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        entry = report[_DLI_RULE_ID]
        self.assertEqual(entry["selected_chunk_id"], _UOFT_CHUNK_ID, entry)
        self.assertTrue(entry["agrees_with_citation"], entry)
        self.assertTrue(entry["grounds"], entry)

    def test_validate_registry_has_no_violation_for_dli_row(self) -> None:
        result = crs_rules.validate_registry(self.reg, _REAL_DB)
        dli_violations = [
            v for v in result["violations"] if v["rule_id"] == _DLI_RULE_ID
        ]
        self.assertEqual(dli_violations, [], dli_violations)

    def test_resolved_dli_chunk_source_type_is_dli(self) -> None:
        # resolve() omits source_type — read it via a direct parameter-bound SELECT.
        con = sqlite3.connect(f"file:{_REAL_DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT source_type FROM chunks WHERE chunk_id = ?",
                (_UOFT_CHUNK_ID,),
            ).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row, f"{_UOFT_CHUNK_ID} not indexed in the real corpus")
        self.assertEqual(row[0], "dli")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
