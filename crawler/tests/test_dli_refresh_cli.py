"""Network-free CLI tests for the top-level ``refresh-dli`` verb (STUDY-01, Plan 41-02).

Stdlib ``unittest`` run via pytest; **NO network, NO third-party deps, NO browser**
(per the AGENTS.md test convention). The ``dli_snapshot.fetch`` seam is monkeypatched
with :func:`unittest.mock.patch`, so every test injects the curated
``fixtures/dli/dli-sample.json`` payload instead of contacting the live IRCC endpoint.
The verb exposes NO ``--url``/``--out``/``--from-file``, so the ONLY isolation seam is
the process cwd: each test ``os.chdir`` into a fresh ``TemporaryDirectory`` so the CLI's
fixed ``write(out_dir=Path("corpus/dli"))`` — which anchors containment on
``Path(out_dir).resolve()`` — lands in the temp tree, NEVER the repo's ``corpus/``.

Coverage (mirrors ``test_json_contract._run_json`` in-process invoke + ``json.loads``
round-trip, plus the ``test_snapshot_refusal`` family-untouched discipline):

  * a patched successful fetch → exit 0 + exactly one five-key, PII-free envelope
    keyed ``{out, institutions, campuses, as_of, family_sha256}`` (T-41-05);
  * the generated temp ``corpus/dli/`` family matches the deterministic generator;
  * a patched fetch error (``URLError``) and a patched schema failure each →
    ``ok:false`` / ``invalid_input`` / exit 2, ``result`` null (T-41-01);
  * a refusal leaves a pre-seeded healthy family byte-for-byte unchanged (T-41-03);
  * the verb takes no URL/output arg — ``--url``/``--out``/``--from-file`` raise
    ``SystemExit`` (T-41-02);
  * the tracked tree stays publish-safe (``check_publish_safe`` → 0 violations).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_dli_refresh_cli.py -x -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import crawler.cli as cli
from crawler import contract

# --------------------------------------------------------------------------- #
# Fixture + expected deterministic generator output (ground truth, 41-01)
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = Path(__file__).parent / "fixtures" / "dli" / "dli-sample.json"
_LAST_MODIFIED = "Thu, 16 Jul 2026 18:08:26 GMT"
_AS_OF = "2026-07-16T18:08:26Z"

# The curated fixture has 5 DISTINCT DLI numbers across 11 campus rows.
_EXPECTED_INSTITUTIONS = 5
_EXPECTED_CAMPUSES = 11
_EXPECTED_DLIS = {
    "O110120953397.md",
    "O112937696097.md",
    "O153601941355.md",
    "O19305471522.md",
    "O19332746152.md",
}

# Tokens that MUST NEVER appear in the machine-readable envelope (PII / raw
# institution data / absolute-path / vault evidence-token leak — T-41-05).
_PII_TOKENS = (
    "University of Toronto",
    "Cestar",
    "Solomon College",
    "Eastern College",
    "Conrad Grebel",
    "St. Jerome",
    "Mississauga",
    "Edmonton",
    "ev_",  # vault evidence-token prefix
)


def _load_sample() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _run_json(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process, returning (rc, stdout, stderr).

    Mirrors ``test_json_contract._run_json``: the ``--json`` envelope is the only
    thing on stdout; every human line is routed to stderr.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


class _TempCwdCase(unittest.TestCase):
    """Base case: run every test with cwd isolated to a fresh temp dir.

    ``os.chdir`` (NOT ``contextlib.chdir``, which is 3.11+) is the sole isolation
    seam — the verb exposes no ``--out``, so a relative ``corpus/dli`` resolves
    under the temp cwd and never the repo tree. The original cwd is always
    restored, even on failure.
    """

    def setUp(self) -> None:
        self._prev_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()


class RefreshDliSuccess(_TempCwdCase):
    def test_success_emits_five_key_pii_free_envelope(self) -> None:
        """Patched fetch → exit 0 + a five-key, PII-free contract envelope."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            return_value=(_load_sample(), _LAST_MODIFIED),
        ):
            rc, out, err = _run_json(["--json", "refresh-dli"])

        self.assertEqual(rc, 0)
        # Exactly one json.loads-able object on stdout.
        self.assertEqual(out.count("\n"), 1)
        env = json.loads(out)

        # Frozen five-key envelope shape.
        self.assertEqual(
            set(env), {"schema_version", "ok", "command", "result", "error"})
        self.assertEqual(env["schema_version"], "1.0")
        self.assertIs(env["ok"], True)
        self.assertEqual(env["command"], "refresh-dli")
        self.assertIsNone(env["error"])

        # Result is PII-free provenance ONLY — exactly these five keys.
        result = env["result"]
        self.assertEqual(
            set(result),
            {"out", "institutions", "campuses", "as_of", "family_sha256"})
        self.assertEqual(result["out"], "corpus/dli")
        self.assertFalse(os.path.isabs(result["out"]))  # relative, never abs
        self.assertEqual(result["institutions"], _EXPECTED_INSTITUTIONS)
        self.assertEqual(result["campuses"], _EXPECTED_CAMPUSES)
        self.assertEqual(result["as_of"], _AS_OF)
        # family_sha256 is a 64-hex content fingerprint.
        self.assertRegex(result["family_sha256"], r"^[0-9a-f]{64}$")

        # No PII / no raw institution data / no absolute path / no ev_ token
        # anywhere in the serialized envelope.
        blob = json.dumps(env)
        for token in _PII_TOKENS:
            self.assertNotIn(token, blob, f"leaked PII token: {token!r}")
        self.assertNotIn(str(self.tmp), blob, "leaked absolute temp path")
        self.assertNotIn(self._prev_cwd, blob, "leaked repo cwd path")

    def test_success_generates_deterministic_family(self) -> None:
        """The temp ``corpus/dli/`` family matches the deterministic generator."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            return_value=(_load_sample(), _LAST_MODIFIED),
        ):
            rc, out, _ = _run_json(["--json", "refresh-dli"])
        self.assertEqual(rc, 0)

        family = self.tmp / "corpus" / "dli"
        self.assertTrue(family.is_dir())
        md_files = {p.name for p in family.glob("*.md")}
        # institutions count == distinct DLI numbers in the fixture.
        self.assertEqual(md_files, _EXPECTED_DLIS)
        self.assertEqual(len(md_files), _EXPECTED_INSTITUTIONS)
        # Non-indexed provenance manifest present alongside the docs.
        self.assertTrue((family / "manifest.json").is_file())

    def test_human_mode_keeps_stdout_clean(self) -> None:
        """Non-json mode prints the human summary to stderr, nothing to stdout."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            return_value=(_load_sample(), _LAST_MODIFIED),
        ):
            rc, out, err = _run_json(["refresh-dli"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")           # stdout pure (no JSON, no summary)
        self.assertIn("corpus/dli", err)    # human summary → stderr


class RefreshDliRefusal(_TempCwdCase):
    def test_fetch_error_refuses_invalid_input_exit2(self) -> None:
        """A fetch failure → ok:false / invalid_input / exit 2, no result."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            side_effect=urllib.error.URLError("boom"),
        ):
            rc, out, _ = _run_json(["--json", "refresh-dli"])

        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)  # exit 2
        env = json.loads(out)
        self.assertIs(env["ok"], False)
        self.assertIsNone(env["result"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
        self.assertEqual(env["command"], "refresh-dli")
        # No family was written on a refusal.
        self.assertFalse((self.tmp / "corpus" / "dli").exists())

    def test_empty_data_schema_failure_refuses(self) -> None:
        """A payload that fails normalize (empty data) → invalid_input / exit 2."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            return_value=({"data": []}, _LAST_MODIFIED),
        ):
            rc, out, _ = _run_json(["--json", "refresh-dli"])

        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        env = json.loads(out)
        self.assertIs(env["ok"], False)
        self.assertIsNone(env["result"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)

    def test_missing_last_modified_refuses(self) -> None:
        """A missing ``Last-Modified`` (None) → as_of fail-closed / exit 2."""
        with mock.patch(
            "crawler.dli_snapshot.fetch",
            return_value=(_load_sample(), None),
        ):
            rc, out, _ = _run_json(["--json", "refresh-dli"])

        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        env = json.loads(out)
        self.assertIs(env["ok"], False)
        self.assertIsNone(env["result"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)

    def test_refusal_preserves_prior_healthy_family_byte_for_byte(self) -> None:
        """A fetch/schema refusal never touches a pre-existing healthy family.

        Seed a temp ``corpus/dli/`` with a known doc + manifest, trigger both a
        fetch error AND a schema failure, and assert the pre-existing files are
        byte-for-byte unchanged (write() is never reached on a refusal, so the
        atomic replace never partially wrote).
        """
        family = self.tmp / "corpus" / "dli"
        family.mkdir(parents=True)
        seed_doc = family / "O99999999.md"
        seed_manifest = family / "manifest.json"
        doc_bytes = b"---\nurl: \"x\"\n---\n\nprior healthy DLI doc body\n"
        manifest_bytes = b'{"family_sha256": "prior", "files": []}\n'
        seed_doc.write_bytes(doc_bytes)
        seed_manifest.write_bytes(manifest_bytes)

        refusals = (
            ("fetch-error", {"side_effect": urllib.error.URLError("boom")}),
            ("schema-error", {"return_value": ({"data": []}, _LAST_MODIFIED)}),
        )
        for label, kwargs in refusals:
            with self.subTest(refusal=label):
                with mock.patch("crawler.dli_snapshot.fetch", **kwargs):
                    rc, _, _ = _run_json(["--json", "refresh-dli"])
                self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
                # Byte-for-byte identical to the pre-seeded family.
                self.assertEqual(seed_doc.read_bytes(), doc_bytes)
                self.assertEqual(seed_manifest.read_bytes(), manifest_bytes)
                # No stray files introduced.
                self.assertEqual(
                    {p.name for p in family.iterdir()},
                    {"O99999999.md", "manifest.json"})


# --------------------------------------------------------------------------- #
# fetch()-stage refusals (CR-01): the size ceiling + decode/JSON faults from a
# non-JSON/truncated CDN response must ALSO map to invalid_input/exit 2 with no
# traceback in either mode, and never touch a prior healthy family. These drive
# the REAL dli_snapshot.fetch() through a controlled network seam so both fetch's
# own normalize-to-SchemaError step AND the CLI's mapping are exercised.
# --------------------------------------------------------------------------- #
class _FakeResp:
    """Minimal ``http.client.HTTPResponse`` stand-in (context manager)."""

    def __init__(self, body: bytes, last_modified: str | None = _LAST_MODIFIED):
        self._body = body
        self.headers = {"Last-Modified": last_modified}

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeOpener:
    def __init__(self, resp: _FakeResp):
        self._resp = resp

    def open(self, req, timeout=None):  # noqa: A003 - mirrors OpenerDirector.open
        return self._resp


# (label, opener-body, max-bytes-override|None) — one per realistic CDN fault.
_FETCH_STAGE_FAULTS = (
    # Oversized: refused by the DoS byte ceiling BEFORE json.loads (T-41-01).
    ("oversized", b"x" * 4096, 16),
    # Non-UTF-8 bytes (garbled/binary body served with 200).
    ("invalid-utf8", b"\xff\xfe\x00\x01 not utf-8 \x80\x81", None),
    # Valid UTF-8 but NOT JSON — a canada.ca HTML maintenance page @ HTTP 200.
    ("non-json-html", b"<html><body>Service temporarily unavailable</body></html>", None),
    # Truncated JSON stream (connection dropped mid-payload).
    ("truncated-json", b'{"data": [{"Province": "Ontario"', None),
)


class RefreshDliFetchStageRefusal(_TempCwdCase):
    def _seed_prior_family(self) -> tuple[Path, Path, bytes, bytes]:
        """Seed a healthy temp ``corpus/dli/`` to assert it survives a refusal."""
        family = self.tmp / "corpus" / "dli"
        family.mkdir(parents=True)
        seed_doc = family / "O99999999.md"
        seed_manifest = family / "manifest.json"
        doc_bytes = b"---\nurl: \"x\"\n---\n\nprior healthy DLI doc body\n"
        manifest_bytes = b'{"family_sha256": "prior", "files": []}\n'
        seed_doc.write_bytes(doc_bytes)
        seed_manifest.write_bytes(manifest_bytes)
        return seed_doc, seed_manifest, doc_bytes, manifest_bytes

    def _patch_seam(self, body: bytes, max_bytes):
        """Return a context stack patching the network seam (+ ceiling)."""
        stack = contextlib.ExitStack()
        stack.enter_context(
            mock.patch("crawler.dli_snapshot._OPENER", _FakeOpener(_FakeResp(body))))
        if max_bytes is not None:
            stack.enter_context(
                mock.patch("crawler.dli_snapshot._MAX_BYTES", max_bytes))
        return stack

    def test_fetch_stage_faults_json_refuse_invalid_input_exit2(self) -> None:
        """Each fetch-stage fault → ok:false / invalid_input / exit 2, no result,
        prior healthy family byte-for-byte unchanged (--json contract)."""
        for label, body, max_bytes in _FETCH_STAGE_FAULTS:
            with self.subTest(fault=label):
                seed_doc, seed_manifest, doc_bytes, manifest_bytes = (
                    self._seed_prior_family())
                with self._patch_seam(body, max_bytes):
                    rc, out, _ = _run_json(["--json", "refresh-dli"])

                self.assertEqual(rc, contract.EXIT_INVALID_INPUT)  # exit 2, never 4
                # Exactly one json.loads-able object on stdout (no traceback leak).
                self.assertEqual(out.count("\n"), 1)
                env = json.loads(out)
                self.assertIs(env["ok"], False)
                self.assertIsNone(env["result"])
                self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
                self.assertEqual(env["command"], "refresh-dli")
                # Prior healthy family untouched (write() never reached).
                self.assertEqual(seed_doc.read_bytes(), doc_bytes)
                self.assertEqual(seed_manifest.read_bytes(), manifest_bytes)
                # Tear down for the next subTest's fresh seed.
                shutil.rmtree(self.tmp / "corpus")

    def test_fetch_stage_faults_human_mode_emit_no_traceback(self) -> None:
        """Each fetch-stage fault in HUMAN mode → exit 2, clean stderr error line,
        NO uncaught traceback (cli.main returns instead of raising), stdout pure,
        prior family unchanged."""
        for label, body, max_bytes in _FETCH_STAGE_FAULTS:
            with self.subTest(fault=label):
                seed_doc, _seed_manifest, doc_bytes, _manifest_bytes = (
                    self._seed_prior_family())
                with self._patch_seam(body, max_bytes):
                    # If the handler let the exception escape, cli.main would raise
                    # here (human mode has no catch-all) — a non-2 rc / raise fails.
                    rc, out, err = _run_json(["refresh-dli"])

                self.assertEqual(rc, contract.EXIT_INVALID_INPUT)  # exit 2, never 1
                self.assertEqual(out, "")               # stdout stays pure
                self.assertIn("error", err)             # single human error line
                self.assertNotIn("Traceback", err)      # no raw traceback dumped
                # Prior family untouched.
                self.assertEqual(seed_doc.read_bytes(), doc_bytes)
                shutil.rmtree(self.tmp / "corpus")


class RefreshDliNoArbitraryInput(unittest.TestCase):
    """The verb takes NO URL/output/input arg (SSRF + publication guard T-41-02)."""

    def test_bare_verb_binds_handler(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["refresh-dli"])
        self.assertEqual(ns.command, "refresh-dli")
        self.assertIs(ns.func, cli._cmd_refresh_dli)
        # No URL/output attributes exist on the namespace.
        self.assertFalse(hasattr(ns, "url"))
        self.assertFalse(hasattr(ns, "from_file"))

    def test_rejects_url_out_and_from_file(self) -> None:
        parser = cli.build_parser()
        for bad in (["--url", "http://evil.example"],
                    ["--out", "/tmp/x"],
                    ["--from-file", "payload.json"]):
            with self.subTest(arg=bad[0]):
                with self.assertRaises(SystemExit):
                    parser.parse_args(["refresh-dli", *bad])

    def test_global_json_must_precede_subcommand(self) -> None:
        parser = cli.build_parser()
        # Global --json BEFORE the subcommand is the contract.
        ns = parser.parse_args(["--json", "refresh-dli"])
        self.assertTrue(ns.json)
        self.assertEqual(ns.command, "refresh-dli")
        # A trailing `refresh-dli --json` is rejected (flag owned by main parser).
        with self.assertRaises(SystemExit):
            parser.parse_args(["refresh-dli", "--json"])


class RefreshDliPublishSafe(unittest.TestCase):
    """The committed tree (incl. fixtures/dli/) stays publish-safe (T-41-05)."""

    def test_check_publish_safe_zero_violations(self) -> None:
        script = _REPO_ROOT / "scripts" / "check_publish_safe.py"
        # Skip-guard: publish-safety is a git-tracked-tree scan.
        if not (_REPO_ROOT / ".git").exists():
            self.skipTest("not a git checkout")
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"publish-safety violations:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("0 violations", proc.stdout)


if __name__ == "__main__":
    unittest.main()
