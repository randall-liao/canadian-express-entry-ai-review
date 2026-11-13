"""SAFE-11 authoritative v5 retrieve-what-you-cite conformance.

The static proof names every MEC, POLICY, STUDY, and DLI row and checks it
against the real index.  The dynamic proof drives the public study review,
then independently binds every transient citation to the tracked golden,
local snapshot manifest/file, and canonical SQLite rows.  Focused runs may
skip unavailable ignored evidence; a release run may not.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import pytest
import yaml

from crawler import auditor, crs_rules, searchindex, study_review, vault
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor


pytestmark = pytest.mark.conformance

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "crawler" / "data" / "crs_rules"
_REAL_DB = _ROOT / "corpus" / "index.db"
_DLI_ROOT = _ROOT / "corpus" / "dli"
_DLI_MANIFEST = _DLI_ROOT / "manifest.json"
_DLI = "O19332746152"
_DLI_DOCUMENT = _DLI_ROOT / f"{_DLI}.md"
_GOLDEN_DLI_ROOT = _ROOT / "crawler" / "tests" / "fixtures" / "dli" / "golden" / "dli"
_GOLDEN_DLI_MANIFEST = _GOLDEN_DLI_ROOT / "manifest.json"
_GOLDEN_DLI_DOCUMENT = _GOLDEN_DLI_ROOT / f"{_DLI}.md"
_DLI_RELPATH = f"dli/{_DLI}.md"
_DYNAMIC_FIELDS = frozenset({
    "rule_id",
    "kind",
    "chunk_id",
    "quote",
    "crawl_date",
    "observed_values",
})

_MEC_RULE_IDS = frozenset({
    "fsw.work.primary_noc",
    "fsw.work.teer",
    "fsw.work.paid",
    "fsw.work.recency",
    "fsw.work.continuity_duration_hours",
    "fsw.work.noc_duties",
    "fsw.language.first",
    "fsw.education.minimum",
    "fsw.grid.language",
    "fsw.grid.education",
    "fsw.grid.experience",
    "fsw.grid.age",
    "fsw.grid.arranged_employment",
    "fsw.grid.adaptability",
    "fsw.grid.pass_mark",
    "fsw.funds.requirement",
    "fsw.destination.outside_quebec",
    "fst.work.trade_noc",
    "fst.work.same_noc",
    "fst.work.paid",
    "fst.work.qualified_to_practise",
    "fst.work.student_exclusion",
    "fst.work.recency_duration_hours",
    "fst.work.noc_duties_requirements",
    "fst.language.minimum",
    "fst.offer_or_certificate",
    "fst.funds.requirement",
    "fst.destination.outside_quebec",
    "cec.work.teer",
    "cec.work.in_canada",
    "cec.work.authorized_tr_status",
    "cec.work.paid",
    "cec.work.recency_duration_hours",
    "cec.work.student_exclusion",
    "cec.work.self_employment_exclusion",
    "cec.work.noc_duties",
    "cec.language.minimum",
    "cec.destination.outside_quebec",
})
_POLICY_RULE_IDS = frozenset({
    "additional.job_offer.current",
    "additional.job_offer.legacy",
    "additional.job_offer.physician",
})
_STUDY_DLI_RULE_IDS = frozenset({
    "additional.study",
    "study.dli.designation",
    "study.r73_definition",
})
_STATIC_RULE_IDS = _MEC_RULE_IDS | _POLICY_RULE_IDS | _STUDY_DLI_RULE_IDS

_STUDY_VALUES = {
    "institution_name": "University of Toronto",
    "dli_number": _DLI,
    "credential_level": "3+",
    "program_start": "2022-09-15",
    "program_end": "2026-04-30",
    "study_status": "graduated",
}


def _release_prerequisite(path: Path, label: str) -> None:
    """Skip ignored local evidence normally, but fail a release with no path leak."""
    if path.is_file():
        return
    message = f"SAFE-11 release prerequisite unavailable: {label}"
    if os.environ.get("PR_CONFORMANCE_RUNNER") == "1":
        raise AssertionError(message)
    pytest.skip(f"LOCAL-ONLY SAFE-11: {label} unavailable")


def _registry_rows(registry, expected: frozenset[str]):
    by_id = {row.rule_id: row for row in registry.rows}
    assert expected <= set(by_id)
    return [by_id[rule_id] for rule_id in sorted(expected)]


def _frontmatter_and_body(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    prefix, separator, body = raw.partition(b"\n---\n\n")
    assert separator and prefix.startswith(b"---\n")
    metadata = yaml.safe_load(prefix.removeprefix(b"---\n").decode("utf-8"))
    assert isinstance(metadata, dict)
    return metadata, body


def _manifest_entry(manifest: dict, filename: str) -> dict:
    matches = [
        entry for entry in manifest["files"]
        if isinstance(entry, dict) and entry.get("file") == filename
    ]
    assert len(matches) == 1
    assert set(matches[0]) == {"file", "content_sha256"}
    return matches[0]


def _canonical_sqlite_rows(db: Path, relpath: str) -> list[dict]:
    uri = f"file:{db}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT chunk_id, relpath, source_url, title, section, crawl_date, "
            "source_type, chunk_sha, ordinal, text FROM chunks "
            "WHERE relpath = ? ORDER BY id",
            (relpath,),
        ).fetchall()
    return [dict(row) for row in rows]


def _designation_quote(text: str) -> str:
    prefixes = (f"DLI number: {_DLI}", "Designation status:", "Status scope:")
    selected = [
        [line for line in text.splitlines() if line.startswith(prefix)]
        for prefix in prefixes
    ]
    assert all(len(lines) == 1 for lines in selected)
    return "\n".join(lines[0] for lines in selected)


def _pgwp_values(table: str) -> list[str]:
    lines = [line for line in table.splitlines() if line.strip()]
    assert len(lines) >= 3
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    assert "PGWP" in header
    index = header.index("PGWP")
    values: list[str] = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == len(header)
        if cells[index] not in values:
            values.append(cells[index])
    assert values
    return values


def _seed_study_vault(root: Path) -> vault.Vault:
    candidate = "safe11-dynamic-lineage"
    opened = vault.open_vault(candidate)
    vault.create_candidate(opened, candidate)
    vault.upsert_profile_factor(opened, CrsProfileFactor(
        factor_id="review.study",
        factor_group="additional_points",
        claimed_value={},
    ))
    source = root / "study-proof.pdf"
    source.write_bytes(b"%PDF-1.4\n% SAFE-11 synthetic study evidence\n")
    document = vault.import_document(
        opened, candidate, source, doc_type="study_proof")
    run_id = vault.record_extraction_run(
        opened,
        document_id=document.document_id,
        parser_version=vault.current_parser_version(),
        status="complete",
    )
    page_id = vault.add_document_page(
        opened,
        document_id=document.document_id,
        page_number=1,
        image_relpath=f"files/rendered/{document.document_id}/page-0001.png",
        render_sha256="b" * 64,
        extraction_run_id=run_id,
    )
    for field, value in _STUDY_VALUES.items():
        value_id = vault.add_extracted_value(
            opened,
            document_id=document.document_id,
            page_id=page_id,
            factor_id="review.study",
            field_name=field,
            raw_text=str(value),
            normalized_value=value,
            bbox=None,
            extractor_confidence=1.0,
            quality_flag="ok",
            extraction_run_id=run_id,
        )
        vault.confirm_value(opened, value_id, "confirm")
    return opened


def _write_synthetic_document(
        corpus: Path, relpath: str, title: str, body: str) -> None:
    path = corpus / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'url: "https://www.canada.ca/{relpath}"\n'
        f'title: "{title}"\n'
        'crawl_date: "2026-07-19"\n'
        f'source_type: "{relpath.split("/", 1)[0]}"\n'
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _synthetic_rule(
    rule_id: str,
    *,
    query: str,
    family: str = "pr-pdi",
    marker: str | None = None,
    citation_id: str,
    quote: str,
    deny_families: tuple[str, ...] = (),
) -> RuleRow:
    return RuleRow(
        rule_id=rule_id,
        factor_group="additional_points",
        factor_ids=[rule_id],
        check_type="admissibility",
        query=query,
        selector=Selector(
            family=family,
            marker=marker,
            deny_families=list(deny_families),
        ),
        claim_text="A synthetic SAFE-11 grounding claim.",
        citations=[Citation(chunk_id=citation_id, quote=quote)],
        machine_check=MachineCheck(kind="accepted_enum", field="synthetic"),
        volatility=VolatilityMeta(
            volatility="stable", source_family=family),
    )


class TestNonVacuousSyntheticControls:
    _CURRENT = {
        "family": (
            "pr-pdi/family-current.md#000",
            "familyauthority",
            "Current family authority controls this claim.",
        ),
        "quote": (
            "pr-pdi/quote-current.md#000",
            "quotegrounding",
            "The exact current quote grounds this claim.",
        ),
        "marker": (
            "pr-pdi/marker-current.md#000",
            "markerabstention",
            "The present marker selects this current rule.",
        ),
        "coordinate": (
            "pr-pdi/coordinate-current.md#000",
            "coordinatebinding",
            "The current coordinate binds this exact claim.",
        ),
        "adjacent": (
            "pr-pdi/adjacent-current.md#000",
            "adjacentselector",
            "The current marker distinguishes the intended adjacent rule.",
        ),
        "superseded": (
            "pr-pdi/superseded-current.md#000",
            "supersededselector",
            "The current source remains authoritative.",
        ),
    }

    def setup_method(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.corpus = Path(self._temporary.name) / "corpus"
        for label, (chunk_id, query, quote) in self._CURRENT.items():
            relpath = chunk_id.rsplit("#", 1)[0]
            _write_synthetic_document(
                self.corpus,
                relpath,
                f"Current {label} authority",
                f"{query}. {quote}",
            )
        _write_synthetic_document(
            self.corpus,
            "legislation-irpr/family-decoy.md",
            "Wrong family decoy",
            "familyauthority. A lexical hit from the wrong authority family.",
        )
        _write_synthetic_document(
            self.corpus,
            "pr-pdi/coordinate-decoy.md",
            "Wrong coordinate decoy",
            "coordinatebinding coordinatebinding. "
            "A real but uncited adjacent coordinate.",
        )
        _write_synthetic_document(
            self.corpus,
            "pr-pdi/adjacent-decoy.md",
            "Adjacent decoy",
            "adjacentselector adjacentselector adjacentselector. "
            "An adjacent rule ranks ahead without the marker.",
        )
        _write_synthetic_document(
            self.corpus,
            "pr-pdi/superseded-decoy.md",
            "Superseded decoy",
            "supersededselector supersededselector supersededselector. "
            "A superseded source ranks ahead unless explicitly denied.",
        )
        self.db = Path(self._temporary.name) / "synthetic.db"
        searchindex.build_index(self.corpus, self.db)

    def teardown_method(self) -> None:
        self._temporary.cleanup()

    def _entry(self, row: RuleRow) -> dict:
        return crs_rules.retrieve_what_you_cite(
            Registry(rows=[row]), self.db)[row.rule_id]

    def _hits(self, query: str, family: str = "pr-pdi") -> list[dict]:
        return searchindex.search(
            self.db, query, family=family, limit=20)["hits"]

    def _valid(self, label: str, *, deny: tuple[str, ...] = ()) -> dict:
        chunk_id, query, quote = self._CURRENT[label]
        return self._entry(_synthetic_rule(
            f"{label}.valid",
            query=query,
            marker=quote,
            citation_id=chunk_id,
            quote=quote,
            deny_families=deny,
        ))

    def test_wrong_family_rejects_after_both_families_have_positive_hits(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["family"]
        correct_hits = self._hits(query)
        wrong_hits = self._hits(query, "legislation-irpr")
        assert len(correct_hits) > 0
        assert len(wrong_hits) > 0
        mirror = self._valid("family")
        assert mirror["selected_chunk_id"] == chunk_id
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "family.wrong",
            query=query,
            family="legislation-irpr",
            marker=None,
            citation_id=chunk_id,
            quote=quote,
        ))
        assert wrong["selected_chunk_id"].startswith("legislation-irpr/")
        assert not wrong["agrees_with_citation"]
        assert not wrong["grounds"]

    def test_wrong_quote_rejects_after_selected_span_and_valid_mirror(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["quote"]
        hits = self._hits(query)
        assert len(hits) > 0
        selected = searchindex.resolve(self.db, chunk_id)
        assert selected is not None
        assert selected["text"].count(quote) == 1
        mirror = self._valid("quote")
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "quote.wrong",
            query=query,
            marker=quote,
            citation_id=chunk_id,
            quote="A fabricated quote absent from the selected chunk.",
        ))
        assert wrong["selected_chunk_id"] == chunk_id
        assert wrong["agrees_with_citation"]
        assert not wrong["grounds"]

    def test_absent_marker_abstains_after_query_and_valid_marker_hit(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["marker"]
        hits = self._hits(query)
        assert len(hits) > 0
        assert sum(
            quote in searchindex.resolve(self.db, hit["chunk_id"])["text"]
            for hit in hits
        ) == 1
        mirror = self._valid("marker")
        assert mirror["selected_chunk_id"] == chunk_id
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "marker.absent",
            query=query,
            marker="A marker absent from every reachable chunk.",
            citation_id=chunk_id,
            quote=quote,
        ))
        assert wrong["selected_chunk_id"] is None
        assert not wrong["agrees_with_citation"]
        assert not wrong["grounds"]

    def test_wrong_citation_coordinate_rejects_with_reachable_decoy(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["coordinate"]
        decoy_id = "pr-pdi/coordinate-decoy.md#000"
        hits = self._hits(query)
        assert len(hits) >= 2
        assert sum(hit["chunk_id"] == decoy_id for hit in hits) == 1
        mirror = self._valid("coordinate")
        assert mirror["selected_chunk_id"] == chunk_id
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "coordinate.wrong",
            query=query,
            marker=quote,
            citation_id=decoy_id,
            quote=searchindex.resolve(self.db, decoy_id)["text"],
        ))
        assert wrong["selected_chunk_id"] == chunk_id
        assert not wrong["agrees_with_citation"]
        assert not wrong["grounds"]

    def test_adjacent_top_hit_rejects_until_marker_selects_current(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["adjacent"]
        decoy_id = "pr-pdi/adjacent-decoy.md#000"
        hits = self._hits(query)
        assert len(hits) >= 2
        assert hits[0]["chunk_id"] == decoy_id
        mirror = self._valid("adjacent")
        assert mirror["selected_chunk_id"] == chunk_id
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "adjacent.wrong",
            query=query,
            citation_id=chunk_id,
            quote=quote,
        ))
        assert wrong["selected_chunk_id"] == decoy_id
        assert not wrong["agrees_with_citation"]
        assert not wrong["grounds"]

    def test_undenied_superseded_hit_rejects_and_deny_mirror_grounds(
            self) -> None:
        chunk_id, query, quote = self._CURRENT["superseded"]
        decoy_prefix = "pr-pdi/superseded-decoy"
        decoy_id = f"{decoy_prefix}.md#000"
        hits = self._hits(query)
        assert len(hits) >= 2
        assert hits[0]["chunk_id"] == decoy_id
        assert sum(
            hit["chunk_id"].startswith(decoy_prefix) for hit in hits) == 1
        mirror = self._valid("superseded", deny=(decoy_prefix,))
        assert mirror["selected_chunk_id"] == chunk_id
        assert mirror["agrees_with_citation"] and mirror["grounds"]

        wrong = self._entry(_synthetic_rule(
            "superseded.undenied",
            query=query,
            citation_id=chunk_id,
            quote=quote,
        ))
        assert wrong["selected_chunk_id"] == decoy_id
        assert not wrong["agrees_with_citation"]
        assert not wrong["grounds"]


class TestExactStaticV5Manifest:
    def test_exact_nonempty_family_rows_and_citation_counts(self) -> None:
        registry = crs_rules.load_registry(_DATA_DIR)
        mec_actual = {
            row.rule_id for row in registry.rows
            if row.rule_id.split(".", 1)[0] in {"fsw", "fst", "cec"}
        }
        policy_actual = {
            row.rule_id for row in registry.rows
            if row.rule_id.startswith("additional.job_offer.")
        }
        study_dli_actual = {
            row.rule_id for row in registry.rows
            if row.rule_id == "additional.study" or row.rule_id.startswith("study.")
        }

        assert mec_actual == _MEC_RULE_IDS
        assert policy_actual == _POLICY_RULE_IDS
        assert study_dli_actual == _STUDY_DLI_RULE_IDS
        assert all((mec_actual, policy_actual, study_dli_actual))

        for expected, row_count, citation_count in (
            (_MEC_RULE_IDS, 38, 75),
            (_POLICY_RULE_IDS, 3, 5),
            (_STUDY_DLI_RULE_IDS, 3, 4),
        ):
            rows = _registry_rows(registry, expected)
            assert len(rows) == row_count
            assert sum(len(row.citations) for row in rows) == citation_count
            assert all(not row.gap and row.citations for row in rows)

    def test_every_exact_static_row_retrieves_and_grounds_real_citation(self) -> None:
        _release_prerequisite(_REAL_DB, "corpus index")
        registry = crs_rules.load_registry(_DATA_DIR)
        rows = _registry_rows(registry, _STATIC_RULE_IDS)
        report = crs_rules.retrieve_what_you_cite(
            type(registry)(rows=rows), _REAL_DB)

        covered: set[str] = set()
        for row in rows:
            entry = report[row.rule_id]
            assert entry["selected_chunk_id"] in {
                citation.chunk_id for citation in row.citations
            }, row.rule_id
            assert entry["agrees_with_citation"], row.rule_id
            assert entry["grounds"], row.rule_id
            covered.add(row.rule_id)
        assert covered == _STATIC_RULE_IDS
        assert set(report) == _STATIC_RULE_IDS

    def test_release_prerequisite_failure_is_stable_and_path_free(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PR_CONFORMANCE_RUNNER", "1")
        missing = tmp_path / "private" / "missing.db"
        with pytest.raises(AssertionError) as raised:
            _release_prerequisite(missing, "corpus index")
        assert str(raised.value) == (
            "SAFE-11 release prerequisite unavailable: corpus index")
        assert str(tmp_path) not in str(raised.value)


class TestDynamicDliLineage:
    def test_public_flow_binds_every_dynamic_citation_to_golden_file_manifest_and_index(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        for path, label in (
            (_REAL_DB, "corpus index"),
            (_DLI_MANIFEST, "DLI manifest"),
            (_DLI_DOCUMENT, "required DLI document"),
            (_GOLDEN_DLI_MANIFEST, "tracked DLI golden manifest"),
            (_GOLDEN_DLI_DOCUMENT, "tracked DLI golden document"),
        ):
            _release_prerequisite(path, label)

        local_manifest = json.loads(_DLI_MANIFEST.read_text(encoding="utf-8"))
        golden_manifest = json.loads(
            _GOLDEN_DLI_MANIFEST.read_text(encoding="utf-8"))
        local_metadata, local_body = _frontmatter_and_body(_DLI_DOCUMENT)
        golden_metadata, golden_body = _frontmatter_and_body(_GOLDEN_DLI_DOCUMENT)
        filename = _DLI_DOCUMENT.name
        local_entry = _manifest_entry(local_manifest, filename)
        golden_entry = _manifest_entry(golden_manifest, filename)

        for manifest in (local_manifest, golden_manifest):
            assert manifest["source_url"].startswith("https://www.canada.ca/")
            assert manifest["as_of"] == manifest["last_modified"]
            assert manifest["generator"] == "ircc-dli-json"
            assert manifest["status_scope"] == "current-only"
            assert manifest["files"]
            assert len({entry["file"] for entry in manifest["files"]}) == len(
                manifest["files"])
            family_payload = json.dumps(
                manifest["files"], ensure_ascii=False, sort_keys=True).encode()
            assert hashlib.sha256(family_payload).hexdigest() == (
                manifest["family_sha256"])
        for metadata in (local_metadata, golden_metadata):
            assert metadata["dli_number"] == _DLI
            assert metadata["source_type"] == "dli"
            assert metadata["generator"] == "ircc-dli-json"
            assert metadata["status_scope"] == "current-only"
            assert f"DLI number: {_DLI}".encode() in (
                local_body if metadata is local_metadata else golden_body)

        assert {
            key: local_metadata[key]
            for key in (
                "url", "crawl_date", "source_type", "dli_number",
                "status_scope", "generator",
            )
        } == {
            key: golden_metadata[key]
            for key in (
                "url", "crawl_date", "source_type", "dli_number",
                "status_scope", "generator",
            )
        }
        assert local_manifest["as_of"] == local_metadata["crawl_date"]
        assert golden_manifest["as_of"] == golden_metadata["crawl_date"]
        assert (
            hashlib.sha256(local_body).hexdigest()
            == local_entry["content_sha256"]
            == local_metadata["content_sha256"]
        )
        assert (
            hashlib.sha256(golden_body).hexdigest()
            == golden_entry["content_sha256"]
            == golden_metadata["content_sha256"]
        )

        canonical = _canonical_sqlite_rows(_REAL_DB, _DLI_RELPATH)
        assert len(canonical) >= 2
        assert [row["ordinal"] for row in canonical] == list(range(len(canonical)))
        assert [row["chunk_id"] for row in canonical] == [
            f"{_DLI_RELPATH}#{ordinal:03d}"
            for ordinal in range(len(canonical))
        ]
        assert all(row["relpath"] == _DLI_RELPATH for row in canonical)
        assert all(row["source_url"] == local_metadata["url"] for row in canonical)
        assert all(row["title"] == local_metadata["title"] for row in canonical)
        assert all(
            row["crawl_date"] == local_manifest["as_of"] for row in canonical)
        assert all(row["source_type"] == "dli" for row in canonical)
        for row in canonical:
            assert hashlib.sha1(row["text"].encode()).hexdigest()[:12] == (
                row["chunk_sha"])
            assert row["text"].encode() in local_body

        with tempfile.TemporaryDirectory() as directory:
            monkeypatch.setenv("PR_PERSONAL_DIR", directory)
            opened = _seed_study_vault(Path(directory))
            try:
                with (
                    mock.patch.object(
                        study_review, "_today", return_value=date(2026, 7, 19)),
                    mock.patch(
                        "crawler.auditor.gate_subset",
                        wraps=auditor.gate_subset,
                    ) as gate,
                ):
                    result = study_review.review_study(
                        opened,
                        _REAL_DB,
                        candidate_id="safe11-dynamic-lineage",
                        max_age_days=30,
                    )
                gate.assert_called_once()
                temporary = gate.call_args.args[0]
                report_path = (
                    opened.root / "output" / "study-review" / "latest.json")
                report = json.loads(report_path.read_text(encoding="utf-8"))
            finally:
                opened.con.close()

        assert result["status"] == "AT-RISK"
        assert result["reason"] == "designation_historical_unproven"
        assert result["as_of"] == local_manifest["as_of"]
        assert [row.rule_id for row in temporary.rows[:2]] == [
            "additional.study",
            "study.r73_definition",
        ]

        dynamic_rows = temporary.rows[2:]
        dynamic_report = report["dynamic_citations"]
        expected_chunk_ids = [row["chunk_id"] for row in canonical]
        assert len(dynamic_rows) == len(canonical) == len(dynamic_report)
        assert [row.citations[0].chunk_id for row in dynamic_rows] == (
            expected_chunk_ids)
        assert [entry["chunk_id"] for entry in dynamic_report] == (
            expected_chunk_ids)
        assert len(set(expected_chunk_ids)) == len(expected_chunk_ids)
        assert all(set(entry) == _DYNAMIC_FIELDS for entry in dynamic_report)
        assert {entry["crawl_date"] for entry in dynamic_report} == {
            local_manifest["as_of"]}

        expected_quotes = [
            _designation_quote(canonical[0]["text"]),
            *[row["text"] for row in canonical[1:]],
        ]
        expected_values = [
            [_DLI],
            *[_pgwp_values(row["text"]) for row in canonical[1:]],
        ]
        expected_kinds = [
            "designation_current",
            *(["pgwp_current"] * (len(canonical) - 1)),
        ]
        expected_rule_ids = [
            f"study.dynamic.{_DLI}.designation",
            *[
                f"study.dynamic.{_DLI}.pgwp.{row['ordinal']:03d}"
                for row in canonical[1:]
            ],
        ]
        assert [entry["rule_id"] for entry in dynamic_report] == expected_rule_ids
        assert [entry["kind"] for entry in dynamic_report] == expected_kinds
        assert [entry["quote"] for entry in dynamic_report] == expected_quotes
        assert [entry["observed_values"] for entry in dynamic_report] == (
            expected_values)

        for rule, entry, canonical_row in zip(
                dynamic_rows, dynamic_report, canonical):
            assert rule.rule_id == entry["rule_id"]
            assert rule.selector.family == "dli"
            assert f"DLI {_DLI}" == rule.selector.require_title_contains
            assert len(rule.citations) == 1
            assert rule.citations[0].chunk_id == canonical_row["chunk_id"]
            assert rule.citations[0].quote == entry["quote"]
            assert rule.volatility.crawl_date == local_manifest["as_of"]

        grounding = crs_rules.retrieve_what_you_cite(temporary, _REAL_DB)
        assert set(grounding) == {row.rule_id for row in temporary.rows}
        for row in temporary.rows:
            assert grounding[row.rule_id]["agrees_with_citation"], row.rule_id
            assert grounding[row.rule_id]["grounds"], row.rule_id
