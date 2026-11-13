"""Offline unit slice for the grounded NOC-2021 duty worksheet (Phase 43 — Plan 01).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Each test points
``$PR_PERSONAL_DIR`` at a throwaway ``tempfile.TemporaryDirectory`` (mirrors
``test_extract_confirm_cli.py``). The worksheet cases resolve against the PINNED,
git-ignored ``corpus/index.db`` via the frozen ``searchindex.resolve`` path (never
a second reader over ``corpus/``, never ``search()``/BM25); they are skip-guarded
so a fresh clone without the local corpus does not report a false green.

Deterministic fixtures come straight from the pinned corpus (verified this
session): ``noc-21232`` -> 7 duties, ``noc-53124`` -> grouped sub-occupation
headers preserved verbatim, ``noc-99999`` -> ``None`` (fail-closed). No duty text
is hand-written (that would fork the grounding path).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_noc_review.py -q
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pydantic import ValidationError

from crawler import crs_rules, grounding, noc_review, paths, searchindex, vault
from crawler.models.vault import CrsProfileFactor, ExtractedValue

# The pinned corpus index is git-ignored (regenerated locally). Resolve it once
# from the repo root; skip the worksheet slice when it is absent so CI on a fresh
# clone stays green-STRUCTURAL-only rather than falsely failing.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_CORPUS_MISSING = (
    "LOCAL-ONLY: corpus/index.db is git-ignored — the grounded NOC worksheet slice "
    "did NOT run; a green suite here is STRUCTURAL ONLY"
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return _Rows(self._rows)


class TestNocSnapshotComposition(unittest.TestCase):
    def test_snapshot_fingerprint_reaches_every_five_key_eligibility_check(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[]),
        )
        fake_vault = SimpleNamespace(
            candidate_id="candidate",
            con=_FakeConnection([{"value_id": "lead"}, {"value_id": "duty"}]),
        )
        values = {
            "lead": SimpleNamespace(
                normalized_value={"duty_id": "21232:1:00", "duty_sha": "lead"}
            ),
            "duty": SimpleNamespace(
                normalized_value={"duty_id": "21232:00", "duty_sha": "duty"}
            ),
        }
        current = {
            "duty_keys": {("21232:00", "duty")},
            "lead_key": ("21232:1:00", "lead"),
            "duty_count": 1,
            "citations": ["noc-2021/noc-21232.md#001"],
        }
        with (
            mock.patch("crawler.noc_review._current_key_sets", return_value=current),
            mock.patch(
                "crawler.noc_review.vault.is_audit_eligible",
                return_value=True,
            ) as eligible,
            mock.patch(
                "crawler.noc_review.vault.get_extracted_value",
                side_effect=lambda _vault, value_id: values[value_id],
            ),
            mock.patch("crawler.noc_review._layer2_fresh", return_value=True),
            mock.patch(
                "crawler.noc_review._rejected_current_duty_ids",
                return_value=set(),
            ),
            mock.patch(
                "crawler.noc_review.crs_rules.load_registry_snapshot",
                side_effect=AssertionError("NOC must not reload the registry"),
                create=True,
            ) as loader,
            mock.patch(
                "crawler.noc_review.crs_rules.registry_fingerprint",
                side_effect=AssertionError("NOC must not recompute the fingerprint"),
                create=True,
            ) as fingerprint,
        ):
            result = noc_review.review_noc_duties(
                fake_vault,
                "unused.db",
                "21232",
                registry_snapshot=snapshot,
            )

        self.assertEqual(result["confirmed_count"], 1)
        self.assertEqual(result["reason"], "duty_review_manual")
        self.assertEqual(eligible.call_count, 2)
        self.assertTrue(all(
            call.kwargs == {"registry_fingerprint": snapshot.fingerprint}
            for call in eligible.call_args_list
        ))
        loader.assert_not_called()
        fingerprint.assert_not_called()

    def test_explicit_fingerprint_is_supported_and_drift_fails_closed(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[]),
        )
        fake_vault = SimpleNamespace(candidate_id="candidate", con=_FakeConnection([]))
        result = noc_review.review_noc_duties(
            fake_vault,
            "unused.db",
            "21232",
            registry_snapshot=snapshot,
            registry_fingerprint="d" * 64,
        )
        self.assertEqual(
            (result["status"], result["reason"]),
            ("AT-RISK", "registry_fingerprint_mismatch"),
        )


def _review_noc_factor() -> CrsProfileFactor:
    """The inert ``review.noc`` FK-parent row (never in FULL_GRID_FACTORS)."""
    return CrsProfileFactor(
        factor_id="review.noc", factor_group="additional_points",
        claimed_points=None, claimed_level=None, claimed_value={},
        source="user_entry")


def _list_review_noc(v: vault.Vault) -> list[ExtractedValue]:
    """All ``review.noc`` extracted values in the vault (id-ordered)."""
    rows = v.con.execute(
        "SELECT value_id FROM extracted_values WHERE factor_id='review.noc' "
        "ORDER BY value_id").fetchall()
    out = []
    for r in rows:
        val = vault.get_extracted_value(v, r["value_id"])
        assert val is not None
        out.append(val)
    return out


# --------------------------------------------------------------------------- #
# Plan-02 sidecar seeding helpers. Every confirmed/rejected/stale/drifted value is
# minted by the SHIPPED Plan-01 generator + the SHIPPED ``vault.confirm_value``
# path (no new confirmation surface); the stale / Layer-2-drift cases then perturb
# ONE binding / stored span exactly as a re-crawl or a corpus edit would. No duty
# text is hand-written (that would fork the grounding path).
# --------------------------------------------------------------------------- #
def _confirm(v: vault.Vault, value_id: str, decision: str = "confirm") -> None:
    """Confirm/correct/reject one value through the shipped verb (never a new path)."""
    vault.confirm_value(v, value_id, decision, confirmed_by="tester")


def _confirm_all(v: vault.Vault) -> None:
    """Confirm EVERY review.noc value in the vault via the shipped confirm verb."""
    for val in _list_review_noc(v):
        _confirm(v, val.value_id, "confirm")


def _make_layer1_stale(v: vault.Vault, value_id: str) -> None:
    """Force a CONFIRMED value 5-key stale (Layer 1) by drifting its source file sha.

    Mutates the backing document's ``file_sha256`` AFTER confirmation so the current
    binding no longer matches the captured one — exactly what ``vault.is_stale``
    (and therefore ``is_audit_eligible``) detects. No status is mutated.
    """
    doc_id = vault.get_extracted_value(v, value_id).document_id
    v.con.execute(
        "UPDATE documents SET file_sha256 = 'drifted_source_sha' "
        "WHERE document_id = ?", (doc_id,))
    v.con.commit()


def _drift_layer2_quote(v: vault.Vault, value_id: str) -> None:
    """Corrupt a value's stored citation quote so Layer-2 grounding fails (drift sim).

    Keeps ``normalized_value`` (duty_id, duty_sha) — so Layer 1 + current-key
    membership still pass — but replaces EVERY stored citation ``quote`` fragment
    with a sentinel that can never be a substring of any live chunk, so
    ``grounding.quote_is_grounded`` returns False on Layer-2 re-check (the duty must
    demote to unresolved). ``raw_text`` is corrupted too for good measure (the
    legacy back-compat path grounds ``raw_text``).
    """
    row = v.con.execute(
        "SELECT normalized_value_json FROM extracted_values WHERE value_id = ?",
        (value_id,)).fetchone()
    nv = json.loads(row["normalized_value_json"])
    for frag in nv.get("citations", []):
        frag["quote"] = "ZZ_DRIFT_SENTINEL_NOT_IN_CORPUS_ZZ"
    v.con.execute(
        "UPDATE extracted_values SET raw_text = 'ZZ_DRIFT_SENTINEL_NOT_IN_CORPUS_ZZ', "
        "normalized_value_json = ? WHERE value_id = ?",
        (json.dumps(nv), value_id))
    v.con.commit()


def _drift_layer2_citation_miss(v: vault.Vault, value_id: str) -> None:
    """Point a value's stored citation(s) at a chunk_id that cannot resolve (miss sim).

    Keeps (duty_id, duty_sha) current so Layer 1 + membership pass, but every stored
    citation ``chunk_id`` now resolves to ``None`` on re-check, demoting the duty.
    """
    row = v.con.execute(
        "SELECT normalized_value_json FROM extracted_values WHERE value_id = ?",
        (value_id,)).fetchone()
    nv = json.loads(row["normalized_value_json"])
    nv["citation"] = "noc-2021/noc-00000.md#999"  # unresolvable chunk_id
    for frag in nv.get("citations", []):
        frag["chunk_id"] = "noc-2021/noc-00000.md#999"  # unresolvable chunk_id
    v.con.execute(
        "UPDATE extracted_values SET normalized_value_json = ? WHERE value_id = ?",
        (json.dumps(nv), value_id))
    v.con.commit()


def _review_noc_rows(v: vault.Vault) -> list:
    """Raw (value_id, normalized_value_json, confirmation_status) review.noc rows."""
    return v.con.execute(
        "SELECT value_id, normalized_value_json, confirmation_status "
        "FROM extracted_values WHERE factor_id='review.noc' ORDER BY value_id"
    ).fetchall()


def _duty_value_ids(v: vault.Vault, duty_id: str) -> list[str]:
    """All review.noc value_ids whose parsed ``duty_id`` equals *duty_id*."""
    return [r["value_id"] for r in _review_noc_rows(v)
            if json.loads(r["normalized_value_json"]).get("duty_id") == duty_id]


def _current_duty_value_id(v: vault.Vault, db: str, code: str, duty_id: str) -> str:
    """The review.noc value_id whose (duty_id, duty_sha) is in the LIVE worksheet.

    The current key set is lead statement (``<code>:1:00``) + every duty from the
    deterministic Plan-01 split, so this resolves BOTH the lead and duty items.
    """
    from crawler import noc_worksheet
    spans = noc_worksheet.resolve_noc_spans(db, code)
    cur = {(d["duty_id"], d["duty_sha"])
           for d in noc_worksheet.split_duties(db, code, spans["main"])}
    cur.add((f"{code}:1:00", searchindex.chunk_sha(spans["lead"]["text"])))
    for r in _review_noc_rows(v):
        nv = json.loads(r["normalized_value_json"])
        if nv.get("duty_id") == duty_id and (nv.get("duty_id"), nv.get("duty_sha")) in cur:
            return r["value_id"]
    raise AssertionError(f"no current value for {duty_id}")


class NocFieldNameVocab(unittest.TestCase):
    """(a) The closed-enum extension is the ONLY field_name enforcement (NOC-02)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def test_vocab_noc_fields_accepted_at_boundary(self) -> None:
        for fn in ("noc_lead_statement", "noc_duty"):
            ev = ExtractedValue(
                value_id="v", document_id="d", page_id=None,
                factor_id="review.noc", field_name=fn, raw_text="x",
                normalized_value={}, bbox=None, extractor_confidence=None,
                quality_flag="ok", extraction_run_id="r",
                confirmation_status="pending")
            self.assertEqual(ev.field_name, fn)

    def test_boundary_unknown_field_name_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ExtractedValue(
                value_id="v", document_id="d", page_id=None,
                factor_id="review.noc", field_name="noc_bogus", raw_text="x",
                normalized_value={}, bbox=None, extractor_confidence=None,
                quality_flag="ok", extraction_run_id="r",
                confirmation_status="pending")

    def test_vocab_add_extracted_value_born_pending(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        # Seed the inert FK parent, a carrier document + a run, then capture.
        vault.upsert_profile_factor(v, _review_noc_factor())
        src = Path(self._tmp.name) / "ws.md"
        src.write_text("# worksheet\n", encoding="utf-8")
        doc = vault.import_document(v, "default", src, doc_type="noc_worksheet")
        run = vault.record_extraction_run(
            v, document_id=doc.document_id, parser_version="1")
        vid = vault.add_extracted_value(
            v, document_id=doc.document_id, page_id=None, factor_id="review.noc",
            field_name="noc_duty", raw_text="Design, write and test code",
            normalized_value={"duty_id": "21232:00", "duty_sha": "deadbeef0000",
                              "citations": [{"chunk_id": "noc-2021/noc-21232.md#002",
                                             "quote": "Design, write and test code"}],
                              "citation": "noc-2021/noc-21232.md#002"},
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=run)
        self.assertTrue(vid.startswith("val_"))
        stored = vault.get_extracted_value(v, vid)
        self.assertIsNotNone(stored)
        # QUARANTINE INVARIANT: born pending, never confirmed (T-30-01).
        self.assertEqual(stored.confirmation_status, "pending")
        self.assertEqual(stored.factor_id, "review.noc")


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class NocWorksheetSlice(unittest.TestCase):
    """(b) Grounded worksheet retrieval / split / citation / fail-closed / vault-only
    RED tests — go green in Tasks 2 (retrieval+split) and 3 (artifact+capture)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- retrieval / citation ------------------------------------------------ #
    def test_worksheet_resolve_spans_exact_citations(self) -> None:
        from crawler import noc_worksheet
        spans = noc_worksheet.resolve_noc_spans(self.db, "21232")
        self.assertIsNotNone(spans)
        # main / reqs are now the ordinal-ordered LISTS of section-classified spans
        # (one Main-duties + one Employment-requirements chunk for this normal NOC).
        self.assertEqual(spans["lead"]["chunk_id"], "noc-2021/noc-21232.md#001")
        self.assertEqual([m["chunk_id"] for m in spans["main"]],
                         ["noc-2021/noc-21232.md#002"])
        self.assertEqual([r["chunk_id"] for r in spans["reqs"]],
                         ["noc-2021/noc-21232.md#003"])

    def test_citation_invalid_code_fails_closed_before_lookup(self) -> None:
        from crawler import noc_worksheet
        # Non-5-digit claims never build a chunk_id (V5 input validation).
        for bad in ("abc", "123", "212321", "2123x", ""):
            self.assertIsNone(noc_worksheet.resolve_noc_spans(self.db, bad))

    # -- deterministic per-duty split --------------------------------------- #
    def test_duties_split_deterministic_seven(self) -> None:
        from crawler import noc_worksheet
        spans = noc_worksheet.resolve_noc_spans(self.db, "21232")
        first = noc_worksheet.split_duties(self.db, "21232", spans["main"])
        second = noc_worksheet.split_duties(self.db, "21232", spans["main"])
        self.assertEqual(len(first), 7)
        # duty_id keys off the SOURCE-section item ordinal (not a chunk ordinal).
        self.assertEqual([d["duty_id"] for d in first],
                         [f"21232:{i:02d}" for i in range(7)])
        # Stable across repeated runs (ids + content fingerprints).
        self.assertEqual([d["duty_id"] for d in first],
                         [d["duty_id"] for d in second])
        self.assertEqual([d["duty_sha"] for d in first],
                         [d["duty_sha"] for d in second])
        main_text = spans["main"][0]["text"]
        for d in first:
            self.assertEqual(len(d["duty_sha"]), 12)
            # duty_sha fingerprints the FULL source item text.
            self.assertEqual(d["duty_sha"], searchindex.chunk_sha(d["text"]))
            # a normal single-chunk duty carries exactly one citation fragment
            # cited to its OWN source chunk (#002 here); primary compat field agrees.
            self.assertEqual(len(d["citations"]), 1)
            self.assertEqual(d["citations"][0]["chunk_id"],
                             "noc-2021/noc-21232.md#002")
            self.assertEqual(d["citation"], "noc-2021/noc-21232.md#002")
            # retrieve-what-you-cite: every fragment is verbatim in the cited chunk.
            self.assertTrue(
                grounding.quote_is_grounded(d["citations"][0]["quote"], main_text))
            self.assertTrue(grounding.quote_is_grounded(d["text"], main_text))
            # boilerplate lead line dropped; no "essential" invention.
            self.assertFalse(d["text"].lower().startswith("this group performs"))

    def test_split_grouped_headers_preserved_verbatim(self) -> None:
        from crawler import noc_worksheet
        spans = noc_worksheet.resolve_noc_spans(self.db, "53124")
        items = noc_worksheet.split_duties(self.db, "53124", spans["main"])
        texts = [d["text"] for d in items]
        # Sub-occupation header bullet kept verbatim as an item (NO classification).
        self.assertIn("Carvers", texts)
        self.assertIn("Potters", texts)
        self.assertEqual(len(items), 18)

    # -- fail-closed absent NOC (Task 2: resolution) ------------------------ #
    def test_absent_noc_spans_none_fail_closed(self) -> None:
        from crawler import noc_worksheet
        # A well-formed 5-digit code with no corpus file -> None (never fabricate).
        self.assertIsNone(noc_worksheet.resolve_noc_spans(self.db, "99999"))

    # -- fail-closed generate refusal (Task 3: capture) --------------------- #
    def test_worksheet_generate_refuses_unresolved_noc(self) -> None:
        from crawler import noc_worksheet
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        res = noc_worksheet.generate_worksheet(v, self.db, "default", "99999")
        self.assertIsNone(res["worksheet_doc_id"])
        self.assertEqual(res["value_ids"], [])
        self.assertEqual(res["duty_count"], 0)
        # zero artifacts, zero values.
        self.assertEqual(_list_review_noc(v), [])
        docs = v.con.execute(
            "SELECT COUNT(*) c FROM documents WHERE doc_type='noc_worksheet'"
        ).fetchone()["c"]
        self.assertEqual(docs, 0)

    # -- vault-only artifact + born-pending capture ------------------------- #
    def test_worksheet_vault_only_and_pending_capture(self) -> None:
        from crawler import noc_worksheet
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        res = noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        self.assertEqual(res["noc_code"], "21232")
        self.assertEqual(res["duty_count"], 7)
        self.assertEqual(len(res["value_ids"]), 8)  # 1 lead + 7 duties
        self.assertTrue(res["worksheet_doc_id"].startswith("doc_"))
        # Artifact written strictly UNDER the vault (never corpus/).
        artifact = paths.resolve_within(
            v.root, "output", "noc-worksheets", "noc-21232.md")
        self.assertTrue(artifact.is_file())
        self.assertTrue(paths.is_within(v.root, artifact))
        body = artifact.read_text(encoding="utf-8")
        self.assertIn("substantiation screening", body.lower())  # SCREENING_NOTICE
        self.assertIn("noc-2021/noc-21232.md#002", body)  # cited span
        # PII-light summary: no raw duty text, no absolute path.
        blob = json.dumps(res)
        self.assertNotIn("Design, write", blob)
        self.assertNotIn(str(v.root), blob)
        # exactly one noc_worksheet document imported.
        docs = v.con.execute(
            "SELECT COUNT(*) c FROM documents WHERE doc_type='noc_worksheet'"
        ).fetchone()["c"]
        self.assertEqual(docs, 1)
        # 1 lead + 7 duties on the inert review.noc factor, all born pending.
        vals = _list_review_noc(v)
        self.assertEqual(len(vals), 8)
        self.assertTrue(all(x.confirmation_status == "pending" for x in vals))
        self.assertTrue(all(x.factor_id == "review.noc" for x in vals))
        fields = sorted(x.field_name for x in vals)
        self.assertEqual(fields.count("noc_lead_statement"), 1)
        self.assertEqual(fields.count("noc_duty"), 7)
        # B1 isolation: core.work never sees a duty value (all pending anyway).
        self.assertEqual(vault.audit_eligible_values(v, "core.work"), [])
        self.assertEqual(vault.audit_eligible_values(v, "review.noc"), [])

    # -- idempotent regeneration -------------------------------------------- #
    def test_idempotent_exact_rerun_reuses_values(self) -> None:
        from crawler import noc_worksheet
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        res1 = noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        res2 = noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        # Stable identity: no duplicate confirm surface.
        self.assertEqual(res2["worksheet_doc_id"], res1["worksheet_doc_id"])
        self.assertEqual(res2["value_ids"], res1["value_ids"])
        self.assertEqual(res2["duty_count"], res1["duty_count"])
        # No new document, no new value on an exact rerun.
        docs = v.con.execute(
            "SELECT COUNT(*) c FROM documents WHERE doc_type='noc_worksheet'"
        ).fetchone()["c"]
        self.assertEqual(docs, 1)
        self.assertEqual(len(_list_review_noc(v)), 8)

    def test_idempotent_rerun_changed_sha_inserts_one_new_pending(self) -> None:
        from crawler import noc_worksheet
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        # Pre-seed a DRIFTED value: same duty_id, a DIFFERENT (stale) duty_sha.
        vault.upsert_profile_factor(v, _review_noc_factor())
        src = Path(self._tmp.name) / "prior.md"
        src.write_text("# prior worksheet\n", encoding="utf-8")
        prior = vault.import_document(v, "default", src, doc_type="noc_worksheet")
        run = vault.record_extraction_run(
            v, document_id=prior.document_id, parser_version="1")
        stale_id = vault.add_extracted_value(
            v, document_id=prior.document_id, page_id=None, factor_id="review.noc",
            field_name="noc_duty", raw_text="stale drifted duty text",
            normalized_value={"duty_id": "21232:00", "duty_sha": "0000stale000",
                              "citation": "noc-2021/noc-21232.md#002"},
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=run)

        res = noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        self.assertEqual(res["duty_count"], 7)
        # The drifted duty_id now has EXACTLY two rows (old stale + one new current).
        rows = v.con.execute(
            "SELECT value_id, normalized_value_json, confirmation_status "
            "FROM extracted_values WHERE factor_id='review.noc'").fetchall()
        by_duty00 = [r for r in rows
                     if json.loads(r["normalized_value_json"]).get("duty_id") == "21232:00"]
        self.assertEqual(len(by_duty00), 2)
        # The old drifted value is UNTOUCHED (same id, same stale sha, still pending).
        stale = vault.get_extracted_value(v, stale_id)
        self.assertIsNotNone(stale)
        self.assertEqual(stale.normalized_value["duty_sha"], "0000stale000")
        self.assertEqual(stale.confirmation_status, "pending")
        # 8 new (1 lead + 7 duties) + 1 pre-seeded stale = 9 total review.noc rows.
        self.assertEqual(len(rows), 9)


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class NocSidecarRollup(unittest.TestCase):
    """(c) Plan 02 Task 1 — the inert ``noc_review`` sidecar: a closed PII-light
    dict whose status is structurally ``{AT-RISK, GAP, N/A}`` and NEVER
    ``SUBSTANTIATED`` / scored, even on a fully-confirmed+fresh duty set."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _fresh_vault(self) -> vault.Vault:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    # -- structurally never-green ------------------------------------------- #
    def test_sidecar_never_green_no_confirmations(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        # Nothing confirmed yet -> fail-closed unresolved, never green.
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertIn(res["status"], ("AT-RISK", "GAP", "N/A"))
        self.assertNotEqual(res["status"], "SUBSTANTIATED")
        self.assertEqual(res["status"], "AT-RISK")
        self.assertEqual(res["reason"], "unresolved_noc")
        self.assertEqual(res["duty_count"], 7)
        self.assertEqual(res["confirmed_count"], 0)

    def test_sidecar_never_green_all_confirmed_caps_at_manual(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)  # confirm lead + all 7 duties via the shipped verb
        res = noc_review.review_noc_duties(v, self.db, "21232")
        # THE headline invariant (Pitfall 1): full confirmation is STILL not green.
        self.assertNotEqual(res["status"], "SUBSTANTIATED")
        self.assertEqual(res["status"], "AT-RISK")
        self.assertEqual(res["reason"], "duty_review_manual")
        self.assertEqual(res["confirmed_count"], res["duty_count"])
        self.assertEqual(res["confirmed_count"], 7)
        # No score / crs-points field can ever cross the boundary.
        self.assertNotIn("crs_points", res)
        self.assertNotIn("score", res)

    def test_sidecar_na_when_no_current_worksheet(self) -> None:
        from crawler import noc_review
        v = self._fresh_vault()
        # A well-formed code with no corpus file -> no current worksheet -> N/A.
        res = noc_review.review_noc_duties(v, self.db, "99999")
        self.assertEqual(res["status"], "N/A")
        self.assertEqual(res["duty_count"], 0)
        self.assertEqual(res["confirmed_count"], 0)
        self.assertEqual(res["citations"], [])

    # -- closed PII-light contract ------------------------------------------ #
    def test_sidecar_closed_pii_light_field_set(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)
        res = noc_review.review_noc_duties(v, self.db, "21232")
        # Keys equal the closed constant EXACTLY (no raw_text / ev_ id / abs path).
        self.assertEqual(tuple(res.keys()), noc_review.PUBLIC_FIELDS)
        self.assertEqual(
            set(res.keys()),
            {"noc_code", "duty_count", "confirmed_count",
             "status", "reason", "citations"})
        blob = json.dumps(res)
        self.assertNotIn("Design, write", blob)   # no raw duty text
        self.assertNotIn("ev_", blob)             # no evidence id
        self.assertNotIn(str(v.root), blob)       # no absolute path
        # Citations are the PII-light chunk_id set only.
        self.assertEqual(res["citations"], [
            "noc-2021/noc-21232.md#001",
            "noc-2021/noc-21232.md#002",
            "noc-2021/noc-21232.md#003"])

    # -- inert by construction ---------------------------------------------- #
    def test_sidecar_inert_imports_no_auditors_no_score(self) -> None:
        import ast as _ast

        import crawler.noc_review as noc_review
        src = Path(noc_review.__file__).read_text(encoding="utf-8")
        tree = _ast.parse(src)
        # Structural (prose-immune) import check: no ACTUAL import references
        # crawler/auditors — a docstring that says "not wired into crawler.auditors"
        # must not false-trip (the authoritative AST scan lives in Task 2).
        imported: list[str] = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom) and node.module:
                imported.append(node.module)
                for alias in node.names:
                    imported.append(f"{node.module}.{alias.name}")
            elif isinstance(node, _ast.Import):
                imported.extend(a.name for a in node.names)
        self.assertFalse(
            any(m == "crawler.auditors" or m.startswith("crawler.auditors.")
                for m in imported),
            f"noc_review must import nothing from crawler.auditors; saw {imported}")
        # No CRS points / score primitive is defined/exported anywhere.
        self.assertFalse(hasattr(noc_review, "crs_points"))
        self.assertFalse(hasattr(noc_review, "score"))
        assigned = {
            t.id
            for node in _ast.walk(tree) if isinstance(node, _ast.Assign)
            for t in node.targets if isinstance(t, _ast.Name)
        }
        self.assertNotIn("crs_points", assigned)


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class NocTwoLayerStaleness(unittest.TestCase):
    """(d) Plan 02 Task 2 — two-layer staleness (Layer 1 = 5-key is_audit_eligible,
    Layer 2 = corpus resolve/quote drift) + current-key dedup; an exhaustive input
    sweep proving NO case is ever ``SUBSTANTIATED`` and ``confirmed_count <=
    duty_count``; and an AST-aware no-scoring source scan over BOTH NOC modules."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _fresh_vault(self) -> vault.Vault:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    # -- partial / rejected -------------------------------------------------- #
    def test_confirm_partial_set_stays_at_risk(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        # Confirm the lead + only 3 of 7 duties.
        _confirm(v, _current_duty_value_id(v, self.db, "21232", "21232:1:00"))
        for i in range(3):
            _confirm(v, _current_duty_value_id(v, self.db, "21232", f"21232:{i:02d}"))
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertEqual(res["status"], "AT-RISK")
        self.assertEqual(res["reason"], "unresolved_noc")
        self.assertEqual(res["confirmed_count"], 3)
        self.assertLess(res["confirmed_count"], res["duty_count"])
        self.assertNotEqual(res["status"], "SUBSTANTIATED")

    def test_confirm_rejected_current_duty_is_gap(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)
        # Reject one CURRENT duty through the shipped verb -> a genuine GAP.
        _confirm(v, _current_duty_value_id(v, self.db, "21232", "21232:03"), "reject")
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertEqual(res["status"], "GAP")
        self.assertNotEqual(res["status"], "SUBSTANTIATED")

    # -- Layer 1 (5-key) staleness demotion --------------------------------- #
    def test_stale_layer1_confirmation_demoted(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)
        # Drift the backing source sha of ONE confirmed duty -> 5-key stale (Layer 1).
        target = _current_duty_value_id(v, self.db, "21232", "21232:00")
        self.assertTrue(vault.is_audit_eligible(v, target))  # eligible before drift
        _make_layer1_stale(v, target)
        self.assertFalse(vault.is_audit_eligible(v, target))  # 5-key stale after
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertLess(res["confirmed_count"], res["duty_count"])
        self.assertEqual(res["reason"], "unresolved_noc")
        self.assertNotEqual(res["status"], "SUBSTANTIATED")

    # -- Layer 2 (corpus) drift demotion ------------------------------------ #
    def test_drift_layer2_quote_mismatch_demoted(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)
        target = _current_duty_value_id(v, self.db, "21232", "21232:00")
        # Layer 1 STILL passes (status/quality/5-key unchanged) but the stored quote
        # no longer grounds in the live chunk -> Layer 2 must demote.
        _drift_layer2_quote(v, target)
        self.assertTrue(vault.is_audit_eligible(v, target))  # Layer 1 unaffected
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertEqual(res["confirmed_count"], 6)
        self.assertLess(res["confirmed_count"], res["duty_count"])
        self.assertEqual(res["reason"], "unresolved_noc")
        self.assertNotEqual(res["status"], "SUBSTANTIATED")

    def test_drift_layer2_citation_miss_demoted(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        _confirm_all(v)
        target = _current_duty_value_id(v, self.db, "21232", "21232:01")
        _drift_layer2_citation_miss(v, target)  # citation now resolves to None
        self.assertTrue(vault.is_audit_eligible(v, target))  # Layer 1 unaffected
        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertEqual(res["confirmed_count"], 6)
        self.assertNotEqual(res["status"], "SUBSTANTIATED")

    # -- changed-sha replacement: count the duty exactly ONCE (old ignored) -- #
    def test_replaced_changed_sha_counts_duty_once(self) -> None:
        from crawler import noc_review, noc_worksheet
        v = self._fresh_vault()
        # OLD confirmed value for duty 00 with a SUPERSEDED (non-current) duty_sha.
        vault.upsert_profile_factor(v, _review_noc_factor())
        src = Path(self._tmp.name) / "prior.md"
        src.write_text("# prior worksheet\n", encoding="utf-8")
        prior = vault.import_document(v, "default", src, doc_type="noc_worksheet")
        run = vault.record_extraction_run(
            v, document_id=prior.document_id, parser_version="1")
        old_id = vault.add_extracted_value(
            v, document_id=prior.document_id, page_id=None, factor_id="review.noc",
            field_name="noc_duty", raw_text="old drifted duty text",
            normalized_value={"duty_id": "21232:00", "duty_sha": "0000oldsha00",
                              "citation": "noc-2021/noc-21232.md#002"},
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=run)
        _confirm(v, old_id)  # the OLD value is confirmed+eligible, but NON-current

        # New current worksheet inserts the fresh duty-00 value (born pending).
        noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
        new_id = _current_duty_value_id(v, self.db, "21232", "21232:00")
        self.assertNotEqual(new_id, old_id)
        _confirm(v, new_id)

        res = noc_review.review_noc_duties(v, self.db, "21232")
        self.assertEqual(res["duty_count"], 7)
        # Duty 00 is counted EXACTLY once (via the current value); old sha ignored.
        self.assertEqual(res["confirmed_count"], 1)
        self.assertLessEqual(res["confirmed_count"], res["duty_count"])
        self.assertNotEqual(res["status"], "SUBSTANTIATED")
        # The old drifted value is UNTOUCHED (same stale sha, still confirmed).
        old = vault.get_extracted_value(v, old_id)
        self.assertEqual(old.normalized_value["duty_sha"], "0000oldsha00")
        self.assertEqual(old.confirmation_status, "confirmed")

    # -- exhaustive input-class sweep: never SUBSTANTIATED ------------------ #
    def test_confirm_sweep_input_classes_never_substantiated(self) -> None:
        from crawler import noc_review, noc_worksheet

        def _scenario(build) -> dict:
            with tempfile.TemporaryDirectory() as td:
                with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                    v = vault.open_vault("default")
                    vault.create_candidate(v, "default")
                    return build(v)

        def _no_worksheet(v):
            return noc_review.review_noc_duties(v, self.db, "99999")

        def _pending_only(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _partial(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            _confirm(v, _current_duty_value_id(v, self.db, "21232", "21232:1:00"))
            _confirm(v, _current_duty_value_id(v, self.db, "21232", "21232:00"))
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _all_rejected(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            for val in _list_review_noc(v):
                _confirm(v, val.value_id, "reject")
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _layer1_stale(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            _confirm_all(v)
            _make_layer1_stale(
                v, _current_duty_value_id(v, self.db, "21232", "21232:00"))
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _layer2_drift(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            _confirm_all(v)
            _drift_layer2_quote(
                v, _current_duty_value_id(v, self.db, "21232", "21232:00"))
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _changed_sha(v):
            # Seed an OLD non-current confirmed value for duty 00 (superseded sha).
            vault.upsert_profile_factor(v, _review_noc_factor())
            doc = vault.import_document(
                v, "default", _write_tmp("# prior\n"), doc_type="noc_worksheet")
            run = vault.record_extraction_run(
                v, document_id=doc.document_id, parser_version="1")
            old_id = vault.add_extracted_value(
                v, document_id=doc.document_id, page_id=None,
                factor_id="review.noc", field_name="noc_duty",
                raw_text="old drifted duty text",
                normalized_value={"duty_id": "21232:00",
                                  "duty_sha": "0000oldsha00",
                                  "citation": "noc-2021/noc-21232.md#002"},
                bbox=None, extractor_confidence=None, quality_flag="ok",
                extraction_run_id=run)
            _confirm(v, old_id)
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            _confirm(v, _current_duty_value_id(v, self.db, "21232", "21232:00"))
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _all_confirmed_fresh(v):
            noc_worksheet.generate_worksheet(v, self.db, "default", "21232")
            _confirm_all(v)
            return noc_review.review_noc_duties(v, self.db, "21232")

        def _write_tmp(text: str) -> Path:
            import tempfile as _tf
            p = Path(_tf.mkdtemp()) / "prior.md"
            p.write_text(text, encoding="utf-8")
            return p

        cases = {
            "no_worksheet": _no_worksheet,
            "pending_only": _pending_only,
            "partial": _partial,
            "all_rejected": _all_rejected,
            "layer1_stale": _layer1_stale,
            "layer2_drift": _layer2_drift,
            "changed_sha": _changed_sha,
            "all_confirmed_fresh": _all_confirmed_fresh,
        }
        for name, build in cases.items():
            with self.subTest(case=name):
                res = _scenario(build)
                # THE never-green invariant across every input class.
                self.assertNotEqual(res["status"], "SUBSTANTIATED", name)
                self.assertIn(res["status"], ("AT-RISK", "GAP", "N/A"), name)
                # confirmed_count can NEVER exceed the current duty_count.
                self.assertLessEqual(
                    res["confirmed_count"], res["duty_count"], name)
        # Spot-check the two poles are correctly labelled.
        self.assertEqual(_scenario(_no_worksheet)["status"], "N/A")
        term = _scenario(_all_confirmed_fresh)
        self.assertEqual((term["status"], term["reason"]),
                         ("AT-RISK", "duty_review_manual"))

    # -- AST-aware no-scoring source scan over BOTH NOC modules ------------- #
    def test_no_scoring_source_scan_both_noc_modules(self) -> None:
        import ast as _ast

        import crawler.noc_review as _nr
        import crawler.noc_worksheet as _nw

        _BANNED_LIBS = {
            "difflib", "numpy", "scipy", "sklearn", "torch", "tensorflow",
            "gensim", "spacy", "transformers", "sentence_transformers",
            "rapidfuzz", "fuzzywuzzy", "Levenshtein", "nltk",
        }
        _BANNED_CALLS = {
            "SequenceMatcher", "ratio", "quick_ratio", "real_quick_ratio",
            "get_close_matches",
        }

        def _docstring_constant_ids(tree) -> set:
            ids: set = set()
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Module, _ast.FunctionDef,
                                     _ast.AsyncFunctionDef, _ast.ClassDef)):
                    body = getattr(node, "body", [])
                    if (body and isinstance(body[0], _ast.Expr)
                            and isinstance(body[0].value, _ast.Constant)
                            and isinstance(body[0].value.value, str)):
                        ids.add(id(body[0].value))
            return ids

        for mod in (_nr, _nw):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            tree = _ast.parse(src)
            # (1) No scoring/vector/fuzzy import.
            imported: set = set()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, _ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported & _BANNED_LIBS,
                f"{mod.__name__} imports a scoring lib: {imported & _BANNED_LIBS}")
            # (2) No match-score call.
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Call):
                    fn = node.func
                    name = (fn.attr if isinstance(fn, _ast.Attribute)
                            else fn.id if isinstance(fn, _ast.Name) else "")
                    self.assertNotIn(
                        name, _BANNED_CALLS,
                        f"{mod.__name__} calls a match-score primitive: {name}")
            # (3) No `return "SUBSTANTIATED"` and no code-level "SUBSTANTIATED"
            #     constant — docstrings are EXCLUDED so prose does not false-trip.
            doc_ids = _docstring_constant_ids(tree)
            for node in _ast.walk(tree):
                if (isinstance(node, _ast.Return)
                        and isinstance(node.value, _ast.Constant)
                        and node.value.value == "SUBSTANTIATED"):
                    self.fail(f"{mod.__name__} has a `return \"SUBSTANTIATED\"` branch")
                if (isinstance(node, _ast.Constant)
                        and isinstance(node.value, str)
                        and node.value == "SUBSTANTIATED"
                        and id(node) not in doc_ids):
                    self.fail(f"{mod.__name__} uses a code-level SUBSTANTIATED literal")


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class NocCandidateScopingSharedDb(unittest.TestCase):
    """(e) WR-02 — cross-candidate isolation in a SHARED (multi-candidate) vault DB.

    The shipped ``open_vault`` mints a per-candidate ``vault.sqlite`` (so only one
    candidate's rows ever exist), which masked an inconsistency: the sidecar's
    eligible/rejected reads filtered by ``factor_id`` alone. This drives BOTH
    candidates through ONE vault connection (a shared DB) and proves candidate B's
    confirmations / rejections NEVER leak into candidate A's ``review_noc_duties``
    roll-up now that every read is scoped by ``candidate_id``.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _candidate_review_noc_rows(self, v: vault.Vault, candidate_id: str) -> list:
        """review.noc value_ids scoped to ONE candidate in the shared DB."""
        cid = paths.safe_candidate_id(candidate_id)
        return [
            r["value_id"]
            for r in v.con.execute(
                "SELECT ev.value_id FROM extracted_values ev "
                "JOIN documents d ON d.document_id = ev.document_id "
                "WHERE d.candidate_id = ? AND ev.factor_id = 'review.noc' "
                "ORDER BY ev.value_id",
                (cid,),
            ).fetchall()
        ]

    def test_candidate_b_confirmations_and_rejection_do_not_leak_to_a(self) -> None:
        from crawler import noc_review, noc_worksheet

        # ONE vault connection ("shared"), two candidates whose documents + values
        # all live in the SAME vault.sqlite (the multi-candidate DB WR-02 warns of).
        v = vault.open_vault("shared")
        vault.create_candidate(v, "alice")
        vault.create_candidate(v, "bob")

        # Both candidates get the same NOC worksheet captured (born pending).
        noc_worksheet.generate_worksheet(v, self.db, "alice", "21232")
        noc_worksheet.generate_worksheet(v, self.db, "bob", "21232")

        alice_ids = self._candidate_review_noc_rows(v, "alice")
        bob_ids = self._candidate_review_noc_rows(v, "bob")
        self.assertEqual(len(alice_ids), 8)   # 1 lead + 7 duties each
        self.assertEqual(len(bob_ids), 8)
        self.assertFalse(set(alice_ids) & set(bob_ids))  # disjoint value ids

        # Confirm EVERY one of BOB's values; confirm NONE of alice's.
        for vid in bob_ids:
            vault.confirm_value(v, vid, "confirm", confirmed_by="tester")

        # ALICE has zero confirmations of her own — bob's 8 must NOT leak in.
        res_a = noc_review.review_noc_duties(v, self.db, "21232", "alice")
        self.assertEqual(res_a["confirmed_count"], 0)
        self.assertEqual(res_a["reason"], "unresolved_noc")
        self.assertNotEqual(res_a["status"], "SUBSTANTIATED")

        # BOB, correctly scoped, sees his full confirmed set (still never green).
        res_b = noc_review.review_noc_duties(v, self.db, "21232", "bob")
        self.assertEqual(res_b["confirmed_count"], res_b["duty_count"])
        self.assertEqual(res_b["confirmed_count"], 7)
        self.assertEqual((res_b["status"], res_b["reason"]),
                         ("AT-RISK", "duty_review_manual"))

        # A REJECTION on one of bob's CURRENT duties must not turn alice's review
        # into a GAP (the rejected-rows read is candidate-scoped too).
        vault.confirm_value(v, bob_ids[1], "reject", confirmed_by="tester")
        res_a2 = noc_review.review_noc_duties(v, self.db, "21232", "alice")
        self.assertNotEqual(res_a2["status"], "GAP")
        self.assertEqual(res_a2["confirmed_count"], 0)
        # Bob's own review now reflects HIS rejection as a GAP.
        res_b2 = noc_review.review_noc_duties(v, self.db, "21232", "bob")
        self.assertEqual(res_b2["status"], "GAP")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
