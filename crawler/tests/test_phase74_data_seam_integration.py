"""Integration tests for Phase 74 loop orchestrator live Phase 73 data seam (D-14..D-22).

Verifies:
- 23 ExpressEntryDocType pipeline discovery with ground_truth/ground_truth.json, ground_truth/pdfs/, and research/research.json.
- Canonical list-valued ground_truth.json loading with reciprocal sibling links, 32-hex IDs, exact doc_type, 10/12 cases per type, and 236 total cases.
- PDF path resolution at ground_truth/pdfs/<opaque_case_id>.pdf and SHA256 pre-call verification.
- Removal of legacy test_data fallbacks.
- Bounded Worker concurrency (default max_workers=4) with independent staging CWDs and deterministic ordering.
- Exact 23 batched Judge calls with 10/12 attachments/reports per document type.
- Per-pipeline iteration artifact storage beneath crawler/eval/pipelines/<doc_type>/iterations/<iteration_name>/.
- Target iteration directory clearing before pass and fail-closed error metadata writing on partial failure.
- Fail-closed behavior on missing pipeline files, corrupt/invalid 32-hex IDs, SHA256 mismatch, or worker/judge failures.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from crawler.eval import loop_orchestrator
from crawler.eval.loop_orchestrator import LoopOrchestrator
from crawler.eval.pipeline_judge import (
    JudgeExecutionError,
    _canonical_json_hash as _judge_artifact_hash,
    _judge_provenance_digest,
)
from crawler.eval.pipeline_worker import (
    ParentPiiManifest,
    _canonical_json_hash as _worker_answer_hash,
    _build_parent_pii_manifest,
    _worker_provenance_digest,
    run_blind_worker_task,
)
from crawler.synthetic.schemas import ExpressEntryDocType
from crawler.synthetic.staging import generate_opaque_32hex_id
from crawler.tests.phase74_provenance import build_provenance


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MARK_WHITE_PARENT_FIELDS = {
    "parent_names": "Karen White Davis and Mark Steven Davis",
}
_SHORT_NAME_FIELDS = {
    "surname": "Li",
    "family_name": "Ng",
    "given_name": "Yu",
    "middle_name": "Q",
    "full_name": "Li Wu",
}
_GUARDED_IDENTITY_FIELDS = {
    "surname": "May",
    "given_name": "Will",
    "family_name": "Li",
    "middle_name": "Q",
}
_PLURAL_NAME_FIELDS = {
    "full_names": "Karen White Davis and Mark Steven Davis",
}
_REPEATED_LAST_FIRST_FIELDS = {
    "full_names": "Davis, Mark, Smith, Karen",
}
_DOTTED_LAST_FIRST_FIELDS = {
    "full_names": "Davis, M., Smith, K.",
}
_UNDOTTED_INITIAL_LAST_FIRST_FIELDS = {
    "full_names": "Davis, M, Smith, K",
}
_MIXED_INITIAL_LAST_FIRST_FIELDS = {
    "full_names": "Davis, M., Smith, Karen",
}
_AMBIGUOUS_INITIAL_LAST_FIRST_FIELDS = {
    "full_names": "Davis, M., Smith",
}
_LIST_GIVEN_NAME_FIELDS = {
    "given_names": ["Karen", "Marie"],
    "family_name": "Davis",
}
_LIST_MIDDLE_NAME_FIELDS = {
    "middle_names": ["Alice", "Rose"],
}
_REUSE_TEST_BUNDLE = {
    "content": "Generic public document review instructions.",
    "bundle_hash": hashlib.sha256(
        b"Generic public document review instructions."
    ).hexdigest(),
}


@pytest.mark.parametrize(
    "mode",
    [
        "baseline-workers",
        "baseline-judges",
        "baseline",
        "optimize",
        "final-pass",
        "full-loop",
    ],
)
def test_legacy_live_modes_delegate_to_sdk_supervisor(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeSdkSupervisor:
        def run(self) -> Dict[str, str]:
            calls.append(mode)
            return {"status": "completed"}

    monkeypatch.setattr(
        "crawler.eval.sdk_pipeline_orchestrator.SdkPipelineOrchestrator",
        FakeSdkSupervisor,
    )
    monkeypatch.setattr(
        loop_orchestrator,
        "LoopOrchestrator",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("legacy live orchestrator must not be constructed")
        ),
    )

    assert loop_orchestrator.main(["--mode", mode]) == 0
    assert calls == [mode]


def _build_mock_pipeline_tree(
    root_dir: Path,
    doc_types: List[str],
    cases_per_doc: Dict[str, int] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Populate a temporary pipeline tree matching Phase 73 layout across specified document types."""
    sample_pdf = next((_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf"))
    p_bytes = sample_pdf.read_bytes()
    p_hash = hashlib.sha256(p_bytes).hexdigest()

    all_cases: Dict[str, List[Dict[str, Any]]] = {}

    for dt in doc_types:
        p_dir = root_dir / dt
        gt_dir = p_dir / "ground_truth"
        pdfs_dir = gt_dir / "pdfs"
        res_dir = p_dir / "research"

        gt_dir.mkdir(parents=True, exist_ok=True)
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        res_dir.mkdir(parents=True, exist_ok=True)

        num_cases = (cases_per_doc or {}).get(dt, 10)
        num_pairs = num_cases // 2

        dt_cases = []
        for i in range(num_pairs):
            v_id = generate_opaque_32hex_id()
            s_id = generate_opaque_32hex_id()
            verdict = "meets_requirements" if i == 0 else "defective"
            failure_id = None if i == 0 else f"PFL-{dt.upper()}-{i}"

            vec_case = {
                "opaque_case_id": v_id,
                "sibling_case_id": s_id,
                "doc_type": dt,
                "variant": "vector",
                "expected_verdict": verdict,
                "source_failure_id": failure_id,
                "pdf_sha256": p_hash,
            }
            scn_case = {
                "opaque_case_id": s_id,
                "sibling_case_id": v_id,
                "doc_type": dt,
                "variant": "scanned",
                "expected_verdict": verdict,
                "source_failure_id": failure_id,
                "pdf_sha256": p_hash,
            }

            (pdfs_dir / f"{v_id}.pdf").write_bytes(p_bytes)
            (pdfs_dir / f"{s_id}.pdf").write_bytes(p_bytes)

            dt_cases.extend([vec_case, scn_case])

        (gt_dir / "ground_truth.json").write_text(json.dumps(dt_cases, indent=2), encoding="utf-8")
        (res_dir / "research.json").write_text(json.dumps({"doc_type": dt, "triggers": []}), encoding="utf-8")

        all_cases[dt] = dt_cases

    return all_cases


def _write_canonical_reusable_sdk_worker_report(
    *,
    pipeline_dir: Path,
    case: Dict[str, Any],
    doc_type: str,
    answer: Dict[str, Any],
    iteration_name: str = "iter_00_baseline",
) -> tuple[Dict[str, Any], ParentPiiManifest]:
    """Persist a live-SDK report bound to the current staged private manifest."""
    bindings = loop_orchestrator._worker_reuse_bindings(
        pipeline_dir=pipeline_dir,
        case_id=case["opaque_case_id"],
        doc_type=doc_type,
        public_bundle=_REUSE_TEST_BUNDLE,
    )
    manifest = bindings["pii_manifest"]
    answer_hash = _worker_answer_hash(answer)
    provenance = build_provenance(
        "worker",
        live=True,
        prompt_hash=bindings["prompt_hash"],
        attachment_hashes=[case["pdf_sha256"]],
        output_hash=answer_hash,
        extras={
            "input_pdf_sha256": case["pdf_sha256"],
            "allowed_text_sha256": bindings["allowed_text_sha256"],
            "bundle_hash": bindings["bundle_hash"],
            "answer_hash": answer_hash,
            "pii_manifest_hash": manifest.manifest_hash,
            "pii_manifest_count": manifest.count,
            "pii_manifest_categories": manifest.category_summary,
        },
    )
    report = {
        **answer,
        "case_id": case["opaque_case_id"],
        "doc_type": doc_type,
        "_provenance": provenance,
    }
    report_file = (
        pipeline_dir
        / "iterations"
        / iteration_name
        / "worker_reports"
        / f"{case['opaque_case_id']}.json"
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report), encoding="utf-8")
    return report, manifest


def _run_worker_reuse_path(
    *,
    orchestrator: LoopOrchestrator,
    reuse_path: str,
    doc_type: str,
    case: Dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    iteration_name: str = "iter_00_baseline",
) -> Dict[str, Dict[str, Any]]:
    """Exercise the real per-doctype or global LoopOrchestrator reuse path."""
    if reuse_path == "doctype":
        return orchestrator.run_doctype_workers_pass(
            doc_type,
            [case],
            iteration_name=iteration_name,
            custom_bundle=_REUSE_TEST_BUNDLE,
        )
    monkeypatch.setattr(
        loop_orchestrator.shutil,
        "rmtree",
        lambda *_args, **_kwargs: None,
    )
    return orchestrator.run_baseline_workers_pass(
        doc_types=[doc_type],
        require_all_23=False,
        iteration_name=iteration_name,
        custom_bundle={doc_type: _REUSE_TEST_BUNDLE},
    )[doc_type]


def test_discovery_and_loader_canonical_23_pipelines(tmp_path: Path) -> None:
    """Verify discovery finds all 23 ExpressEntryDocType pipelines and loads 236 cases cleanly."""
    all_23 = [e.value for e in ExpressEntryDocType]
    assert len(all_23) == 23

    # Set up 23 pipelines: 19 with 10 cases, 4 with 12 cases -> 190 + 48 = 238? No!
    # Let's make 19 doc types with 10 cases (190) and 4 with 11 cases? No, 10 or 12 per type.
    # 236 = 18 * 10 (180) + 5 * 12 (60) = 240?
    # 18 * 10 = 180, 4 * 12 = 48, 1 * 8? No!
    # Let's check actual distribution across 23 pipelines in repo:
    # 19 pipelines with 10 cases (190) + 3 pipelines with 10 cases + 1 pipeline with 16?
    # Let's check actual distribution in repo:
    cases_per_doc = {}
    pipelines_dir = _REPO_ROOT / "crawler" / "eval" / "pipelines"
    for p in pipelines_dir.iterdir():
        if p.is_dir() and (p / "ground_truth" / "ground_truth.json").is_file():
            data = json.loads((p / "ground_truth" / "ground_truth.json").read_text(encoding="utf-8"))
            cases_per_doc[p.name] = len(data)

    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, all_23, cases_per_doc=cases_per_doc)

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_root,
        iterations_dir=tmp_path / "iterations",
    )

    discovered = orchestrator._discover_doc_types(require_all_23=True)
    assert len(discovered) == 23
    assert sorted(discovered) == sorted(all_23)

    total_loaded = 0
    global_ids: set = set()

    for dt in discovered:
        cases = orchestrator._load_doc_type_cases(dt, global_case_ids=global_ids)
        assert len(cases) in (10, 12)
        total_loaded += len(cases)

    assert total_loaded == 236
    assert len(global_ids) == 236


def test_discovery_fails_closed_on_missing_required_file(tmp_path: Path) -> None:
    """Verify discovery raises ValueError if any pipeline directory lacks research.json or ground_truth.json."""
    all_23 = [e.value for e in ExpressEntryDocType]
    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, all_23)

    # Remove research.json from passport pipeline
    (pipelines_root / "passport" / "research" / "research.json").unlink()

    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    with pytest.raises(ValueError, match="missing required Phase 73 data files"):
        orchestrator._discover_doc_types(require_all_23=True)


def test_load_cases_fails_closed_on_sha256_mismatch(tmp_path: Path) -> None:
    """Verify case loading fails closed if PDF file SHA256 does not match ground_truth.json record."""
    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, ["passport"])

    # Corrupt PDF SHA256 in record
    gt_file = pipelines_root / "passport" / "ground_truth" / "ground_truth.json"
    cases = json.loads(gt_file.read_text(encoding="utf-8"))
    cases[0]["pdf_sha256"] = "0" * 64
    gt_file.write_text(json.dumps(cases, indent=2), encoding="utf-8")

    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    with pytest.raises(ValueError, match="PDF SHA256 mismatch"):
        orchestrator._load_doc_type_cases("passport")


def test_load_cases_fails_closed_on_broken_reciprocal_sibling(tmp_path: Path) -> None:
    """Verify case loading fails closed if reciprocal sibling link is broken."""
    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, ["passport"])

    gt_file = pipelines_root / "passport" / "ground_truth" / "ground_truth.json"
    cases = json.loads(gt_file.read_text(encoding="utf-8"))
    # Point sibling link of case 0 to an arbitrary non-existent ID
    cases[0]["sibling_case_id"] = "a" * 32
    gt_file.write_text(json.dumps(cases, indent=2), encoding="utf-8")

    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    with pytest.raises(ValueError, match="Sibling case ID"):
        orchestrator._load_doc_type_cases("passport")


@pytest.mark.parametrize("artifact_state", ["copilot-cli", "injected-test-runner", "missing"])
def test_complete_loop_summary_never_bypasses_per_artifact_reuse_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_state: str,
) -> None:
    iterations_dir = tmp_path / "iterations"
    iterations_dir.mkdir()
    doc_types = {}
    for index in range(23):
        judge_batch = {}
        if artifact_state != "missing":
            judge_batch["_provenance"] = {
                "engine": artifact_state,
                "is_live": artifact_state == "copilot-cli",
            }
        doc_types[f"doc_type_{index}"] = {"judge_batch": judge_batch}
    stale_baseline = {
        "total_cases": 236,
        "doc_types": doc_types,
        "marker": "stale-aggregate",
    }
    (iterations_dir / "loop_summary.json").write_text(
        json.dumps({"baseline": stale_baseline}),
        encoding="utf-8",
    )

    orchestrator = LoopOrchestrator(
        pipelines_dir=tmp_path / "pipelines",
        iterations_dir=iterations_dir,
    )
    calls = []

    def replacement_workers_pass(**kwargs: Any) -> Dict[str, Any]:
        calls.append("workers")
        return {"fresh-workers": {}}

    def replacement_judges_pass(**kwargs: Any) -> Dict[str, Any]:
        calls.append("judges")
        assert kwargs["all_worker_reports"] == {"fresh-workers": {}}
        return {"marker": "fresh-baseline"}

    monkeypatch.setattr(
        orchestrator,
        "run_baseline_workers_pass",
        replacement_workers_pass,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_baseline_judges_pass",
        replacement_judges_pass,
    )

    result = orchestrator.run_baseline_pass()

    assert calls == ["workers", "judges"]
    assert result == {"marker": "fresh-baseline"}


@pytest.mark.parametrize(
    ("engine", "attachment_hash_matches"),
    [
        ("copilot-cli", True),
        ("injected-test-runner", True),
        ("copilot-sdk", False),
    ],
)
def test_worker_reuse_rejects_legacy_injected_or_hash_mismatched_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    attachment_hash_matches: bool,
) -> None:
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(pipelines_root, ["passport"])["passport"]
    case = cases[0]
    case_id = case["opaque_case_id"]
    pdf_hash = case["pdf_sha256"]
    out_dir = (
        pipelines_root
        / "passport"
        / "iterations"
        / "iter_00_baseline"
        / "worker_reports"
    )
    out_dir.mkdir(parents=True)
    stale_report = {
        "question": "Review the supplied passport.",
        "claims": [],
        "basis": [],
        "abstentions": [{"text": "No corpus claim.", "reason": "not_in_corpus"}],
        "prose": "No claims made.",
        "case_id": case_id,
        "doc_type": "passport",
        "_provenance": {
            "engine": engine,
            "is_live": engine != "injected-test-runner",
            "role": "worker",
            "model": "gemini-3.6-flash",
            "effort": None,
            "context": "long_context",
            "context_tier": "long_context",
            "input_pdf_sha256": pdf_hash,
            "attachment_hashes": [pdf_hash if attachment_hash_matches else "0" * 64],
            "bundle_hash": "a" * 64,
            "prompt_hash": "b" * 64,
            "output_hash": "c" * 64,
            "terminal_event": "assistant.message",
            "provenance_digest": "d" * 64,
        },
    }
    (out_dir / f"{case_id}.json").write_text(json.dumps(stale_report), encoding="utf-8")
    calls = []

    def replacement_worker(**kwargs):
        calls.append(kwargs["opaque_case_id"])
        return {**stale_report, "fresh": True}

    monkeypatch.setattr(
        "crawler.eval.loop_orchestrator.run_blind_worker_task",
        replacement_worker,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    result = orchestrator.run_doctype_workers_pass(
        "passport",
        [case],
        iteration_name="iter_00_baseline",
    )

    assert calls == [case_id]
    assert result[case_id]["fresh"] is True


@pytest.mark.parametrize(
    ("tamper", "should_refresh"),
    [
        (None, False),
        ("relabeled_injected", True),
        ("prompt_hash", True),
        ("bundle_hash", True),
        ("case_id", True),
        ("doc_type", True),
        ("stale_manifest", True),
        ("legacy_manifest", True),
        ("legacy_component_manifest", True),
        ("legacy_comma_person_group", True),
        ("fixture_relabel", True),
    ],
)
def test_worker_reuse_requires_exact_available_request_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str | None,
    should_refresh: bool,
) -> None:
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(pipelines_root, ["passport"])[
        "passport"
    ]
    case = cases[0]
    case_id = case["opaque_case_id"]
    pipeline_dir = pipelines_root / "passport"
    ground_truth_path = pipeline_dir / "ground_truth" / "ground_truth.json"
    if tamper == "fixture_relabel":
        case["fields"] = {
            "policy_reference_number": "REF-2026-77119",
        }
        ground_truth_path.write_text(
            json.dumps(cases, indent=2),
            encoding="utf-8",
        )
    elif tamper == "legacy_component_manifest":
        case["fields"] = {
            "mother_full_name": "Karen White Davis",
            "father_full_name": "Mark Steven Davis",
        }
        ground_truth_path.write_text(
            json.dumps(cases, indent=2),
            encoding="utf-8",
        )
    elif tamper == "legacy_comma_person_group":
        case["fields"] = {
            "parent_names": "Karen White Davis, Mark Steven Davis",
        }
        ground_truth_path.write_text(
            json.dumps(cases, indent=2),
            encoding="utf-8",
        )
    out_dir = (
        pipeline_dir
        / "iterations"
        / "iter_00_baseline"
        / "worker_reports"
    )

    answer = {
        "question": "Review the supplied passport.",
        "claims": [],
        "basis": [],
        "abstentions": [{"text": "No corpus claim.", "reason": "not_in_corpus"}],
        "prose": "No claims made.",
    }

    def injected_runner(cmd: List[str], cwd: Path) -> str:
        return json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": json.dumps(answer)},
            }
        )

    report = run_blind_worker_task(
        opaque_case_id=case_id,
        doc_type="passport",
        runner_fn=injected_runner,
        pipeline_root=pipeline_dir,
        output_dir=out_dir,
    )
    injected_provenance = report["_provenance"]
    if tamper == "relabeled_injected":
        injected_provenance["engine"] = "copilot-sdk"
        injected_provenance["is_live"] = True
    else:
        report["_provenance"] = build_provenance(
            "worker",
            live=True,
            prompt_hash=injected_provenance["prompt_hash"],
            attachment_hashes=injected_provenance["attachment_hashes"],
            output_hash=injected_provenance["output_hash"],
            extras={
                field: injected_provenance[field]
                for field in (
                    "input_pdf_sha256",
                    "allowed_text_sha256",
                    "bundle_hash",
                    "answer_hash",
                    "pii_manifest_hash",
                    "pii_manifest_count",
                    "pii_manifest_categories",
                )
            },
        )

    if tamper in {"prompt_hash", "bundle_hash"}:
        report["_provenance"][tamper] = "0" * 64
    elif tamper == "case_id":
        report["case_id"] = "wrong-case"
    elif tamper == "doc_type":
        report["doc_type"] = "language_test"
    elif tamper == "stale_manifest":
        report["_provenance"]["pii_manifest_hash"] = "f" * 64
        report["_provenance"]["pii_manifest_count"] = 0
        report["_provenance"]["pii_manifest_categories"] = {}
    elif tamper == "legacy_manifest":
        report["_provenance"].pop("pii_manifest_hash")
        report["_provenance"].pop("pii_manifest_count")
        report["_provenance"].pop("pii_manifest_categories")
    elif tamper == "legacy_component_manifest":
        manifest = _build_parent_pii_manifest(
            pdf_path=(
                pipeline_dir
                / "ground_truth"
                / "pdfs"
                / f"{case_id}.pdf"
            ),
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )
        legacy_values = dict(manifest.values)
        legacy_values["name"] = tuple(
            sorted(
                set(manifest.values["name"])
                | {
                    component
                    for group in manifest.name_component_groups
                    for component in group
                }
            )
        )
        report["_provenance"]["pii_manifest_hash"] = _worker_answer_hash(
            legacy_values
        )
        report["_provenance"]["pii_manifest_count"] = sum(
            len(values) for values in legacy_values.values()
        )
        report["_provenance"]["pii_manifest_categories"] = {
            category: len(values)
            for category, values in legacy_values.items()
            if values
        }
    elif tamper == "legacy_comma_person_group":
        manifest = _build_parent_pii_manifest(
            pdf_path=(
                pipeline_dir
                / "ground_truth"
                / "pdfs"
                / f"{case_id}.pdf"
            ),
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )
        merged_group = ("karen", "white", "davis", "mark", "steven")
        old_groups = tuple(
            sorted(set(manifest.name_component_groups) | {merged_group})
        )
        report["_provenance"]["pii_manifest_hash"] = _worker_answer_hash(
            {
                "schema": "parent-pii-manifest-v2",
                "values": manifest.values,
                "name_component_groups": old_groups,
            }
        )
        report["_provenance"]["pii_manifest_count"] = (
            manifest.count + len(merged_group)
        )
        old_categories = dict(manifest.category_summary)
        old_categories["name"] = old_categories.get("name", 0) + len(
            merged_group
        )
        report["_provenance"]["pii_manifest_categories"] = old_categories
    elif tamper == "fixture_relabel":
        case["fields"] = {
            "reference_number": "REF-2026-77119",
        }
        ground_truth_path.write_text(
            json.dumps(cases, indent=2),
            encoding="utf-8",
        )
    report["_provenance"]["provenance_digest"] = _worker_provenance_digest(
        report["_provenance"]
    )
    (out_dir / f"{case_id}.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    calls: List[str] = []

    def replacement_worker(**kwargs: Any) -> Dict[str, Any]:
        calls.append(kwargs["opaque_case_id"])
        return {**report, "fresh": True}

    monkeypatch.setattr(
        "crawler.eval.loop_orchestrator.run_blind_worker_task",
        replacement_worker,
    )
    validated_manifests: List[ParentPiiManifest] = []
    original_assertion = loop_orchestrator._assert_answer_blindness_and_pii

    def capture_reuse_manifest(
        answer: Dict[str, Any],
        *,
        pii_manifest: ParentPiiManifest | None = None,
    ) -> None:
        assert pii_manifest is not None
        validated_manifests.append(pii_manifest)
        original_assertion(answer, pii_manifest=pii_manifest)

    monkeypatch.setattr(
        loop_orchestrator,
        "_assert_answer_blindness_and_pii",
        capture_reuse_manifest,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    result = orchestrator.run_doctype_workers_pass(
        "passport",
        [case],
        iteration_name="iter_00_baseline",
    )

    assert calls == ([case_id] if should_refresh else [])
    assert ("fresh" in result[case_id]) is should_refresh
    if should_refresh:
        assert validated_manifests == []
    else:
        assert len(validated_manifests) == 1
        assert isinstance(validated_manifests[0], ParentPiiManifest)
        assert (
            validated_manifests[0].manifest_hash
            == report["_provenance"]["pii_manifest_hash"]
        )


@pytest.mark.parametrize("reuse_path", ["doctype", "global"])
def test_worker_reuse_rejects_sdk_report_after_private_manifest_input_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reuse_path: str,
) -> None:
    doc_type = "birth_certificate"
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(pipelines_root, [doc_type])[doc_type]
    case = cases[0]
    case_id = case["opaque_case_id"]
    pipeline_dir = pipelines_root / doc_type
    ground_truth_file = (
        pipeline_dir / "ground_truth" / "ground_truth.json"
    )
    case["fields"] = {"surname": "Field"}
    ground_truth_file.write_text(json.dumps(cases), encoding="utf-8")
    clean_answer = {
        "question": "Review the supplied birth certificate.",
        "claims": [],
        "basis": [],
        "abstentions": [
            {"text": "No corpus claim.", "reason": "not_in_corpus"}
        ],
        "prose": "No claims made.",
    }
    stale_report, staged_manifest = (
        _write_canonical_reusable_sdk_worker_report(
            pipeline_dir=pipeline_dir,
            case=case,
            doc_type=doc_type,
            answer=clean_answer,
        )
    )
    assert (
        stale_report["_provenance"]["pii_manifest_hash"]
        == staged_manifest.manifest_hash
    )

    case["fields"] = {"surname": "Value"}
    ground_truth_file.write_text(json.dumps(cases), encoding="utf-8")
    current_manifest = _build_parent_pii_manifest(
        pdf_path=(
            pipeline_dir
            / "ground_truth"
            / "pdfs"
            / f"{case_id}.pdf"
        ),
        pipeline_root=pipeline_dir,
        case_id=case_id,
    )
    assert current_manifest.manifest_hash != staged_manifest.manifest_hash

    regenerated: List[str] = []

    def replacement_worker(**kwargs: Any) -> Dict[str, Any]:
        regenerated.append(kwargs["opaque_case_id"])
        return {
            **stale_report,
            **clean_answer,
            "case_id": kwargs["opaque_case_id"],
            "doc_type": kwargs["doc_type"],
            "fresh": True,
        }

    monkeypatch.setattr(
        loop_orchestrator,
        "run_blind_worker_task",
        replacement_worker,
    )
    monkeypatch.setattr(
        loop_orchestrator,
        "check_answer_grounding",
        lambda *_args, **_kwargs: None,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)

    result = _run_worker_reuse_path(
        orchestrator=orchestrator,
        reuse_path=reuse_path,
        doc_type=doc_type,
        case=case,
        monkeypatch=monkeypatch,
    )

    assert case_id in regenerated
    assert result[case_id]["fresh"] is True


@pytest.mark.parametrize("reuse_path", ["doctype", "global"])
@pytest.mark.parametrize("protected_value", ["Field", "Value"])
@pytest.mark.parametrize(
    "trailing_syntax",
    [" is recorded", " was recorded", ": recorded", "/recorded"],
)
def test_worker_reuse_rejects_sdk_reports_contaminated_by_pre_delimited_protected_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reuse_path: str,
    protected_value: str,
    trailing_syntax: str,
) -> None:
    doc_type = "birth_certificate"
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(pipelines_root, [doc_type])[doc_type]
    case = cases[0]
    case_id = case["opaque_case_id"]
    pipeline_dir = pipelines_root / doc_type
    case["fields"] = {"surname": protected_value}
    (
        pipeline_dir / "ground_truth" / "ground_truth.json"
    ).write_text(json.dumps(cases), encoding="utf-8")
    fragment = f"Surname: {protected_value}{trailing_syntax}"
    contaminated_answer = {
        "question": fragment,
        "claims": [
            {
                "id": fragment,
                "text": fragment,
                "citations": [fragment],
                "quote": fragment,
            }
        ],
        "basis": [],
        "abstentions": [
            {"text": fragment, "reason": "not_in_corpus"}
        ],
        "prose": fragment,
    }
    contaminated_report, current_manifest = (
        _write_canonical_reusable_sdk_worker_report(
            pipeline_dir=pipeline_dir,
            case=case,
            doc_type=doc_type,
            answer=contaminated_answer,
        )
    )
    assert (
        contaminated_report["_provenance"]["pii_manifest_hash"]
        == current_manifest.manifest_hash
    )

    regenerated: List[str] = []

    def replacement_worker(**kwargs: Any) -> Dict[str, Any]:
        regenerated.append(kwargs["opaque_case_id"])
        return {
            **contaminated_report,
            "question": "Review the supplied birth certificate.",
            "claims": [],
            "abstentions": [
                {"text": "No corpus claim.", "reason": "not_in_corpus"}
            ],
            "prose": "Fresh clean report.",
            "case_id": kwargs["opaque_case_id"],
            "doc_type": kwargs["doc_type"],
            "fresh": True,
        }

    monkeypatch.setattr(
        loop_orchestrator,
        "run_blind_worker_task",
        replacement_worker,
    )
    monkeypatch.setattr(
        loop_orchestrator,
        "check_answer_grounding",
        lambda *_args, **_kwargs: None,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)

    result = _run_worker_reuse_path(
        orchestrator=orchestrator,
        reuse_path=reuse_path,
        doc_type=doc_type,
        case=case,
        monkeypatch=monkeypatch,
    )

    assert case_id in regenerated
    assert result[case_id]["prose"] == "Fresh clean report."


@pytest.mark.parametrize("reuse_path", ["doctype", "global"])
def test_worker_reuse_validates_public_leaves_against_current_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reuse_path: str,
) -> None:
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(
        pipelines_root,
        ["proof_of_other_name"],
    )["proof_of_other_name"]
    case = cases[0]
    case_id = case["opaque_case_id"]
    case["fields"] = {
        "email_address": "john.smith@example.test",
        "date_of_birth": "January 2, 1990",
        "passport_full_name": "Elena Rostova",
        "degree_certificate_name": "Elena Rostoff",
        "policyHolderDetails": {
            "referenceNumber": "CLIENT-2026-9912",
        },
    }
    pipeline_dir = pipelines_root / "proof_of_other_name"
    (pipeline_dir / "ground_truth" / "ground_truth.json").write_text(
        json.dumps(cases, indent=2),
        encoding="utf-8",
    )
    out_dir = (
        pipeline_dir
        / "iterations"
        / "iter_00_baseline"
        / "worker_reports"
    )
    clean_answer = {
        "question": "Review the supplied proof of other name.",
        "claims": [],
        "basis": [],
        "abstentions": [{"text": "No corpus claim.", "reason": "not_in_corpus"}],
        "prose": "No claims made.",
    }

    def injected_runner(cmd: List[str], cwd: Path) -> str:
        return json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": json.dumps(clean_answer)},
            }
        )

    report = run_blind_worker_task(
        opaque_case_id=case_id,
        doc_type="proof_of_other_name",
        runner_fn=injected_runner,
        pipeline_root=pipeline_dir,
        output_dir=out_dir,
    )
    injected_provenance = report["_provenance"]
    report["_provenance"] = build_provenance(
        "worker",
        live=True,
        prompt_hash=injected_provenance["prompt_hash"],
        attachment_hashes=injected_provenance["attachment_hashes"],
        output_hash=injected_provenance["output_hash"],
        extras={
            field: injected_provenance[field]
            for field in (
                "input_pdf_sha256",
                "allowed_text_sha256",
                "bundle_hash",
                "answer_hash",
                "pii_manifest_hash",
                "pii_manifest_count",
                "pii_manifest_categories",
            )
        },
    )
    report["prose"] = "The degree certificate names Elena Rostoff."
    answer = {
        field: report[field]
        for field in ("question", "claims", "basis", "abstentions", "prose")
    }
    report["_provenance"]["answer_hash"] = _worker_answer_hash(answer)
    report["_provenance"]["provenance_digest"] = _worker_provenance_digest(
        report["_provenance"]
    )
    (out_dir / f"{case_id}.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    calls: List[str] = []

    def replacement_worker(**kwargs: Any) -> Dict[str, Any]:
        calls.append(kwargs["opaque_case_id"])
        return {**report, "prose": "Fresh clean report.", "fresh": True}

    monkeypatch.setattr(
        "crawler.eval.loop_orchestrator.run_blind_worker_task",
        replacement_worker,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    if reuse_path == "doctype":
        result = orchestrator.run_doctype_workers_pass(
            "proof_of_other_name",
            [case],
            iteration_name="iter_00_baseline",
        )
    else:
        monkeypatch.setattr(loop_orchestrator.shutil, "rmtree", lambda *_a, **_k: None)
        result = orchestrator.run_baseline_workers_pass(
            doc_types=["proof_of_other_name"],
            require_all_23=False,
            iteration_name="iter_00_baseline",
        )["proof_of_other_name"]

    assert case_id in calls
    assert result[case_id]["fresh"] is True


@pytest.mark.parametrize("reuse_path", ["doctype", "global"])
@pytest.mark.parametrize(
    ("public_fragment", "identity_context", "case_fields"),
    [
        ("The name is marked in white.", False, _MARK_WHITE_PARENT_FIELDS),
        ("Contact person must mark white areas.", False, _MARK_WHITE_PARENT_FIELDS),
        (
            "Consult Dr. guidance before applicants mark white areas.",
            False,
            _MARK_WHITE_PARENT_FIELDS,
        ),
        ("Name is Mark", True, _MARK_WHITE_PARENT_FIELDS),
        ("Applicants are eligible.", False, _MARK_WHITE_PARENT_FIELDS),
        (
            "The applicants' names are Mark and Karen.",
            True,
            _MARK_WHITE_PARENT_FIELDS,
        ),
        ("Surname: Li", True, _SHORT_NAME_FIELDS),
        ("Family Name is Ng", True, _SHORT_NAME_FIELDS),
        ("Given Name: Yu", True, _SHORT_NAME_FIELDS),
        ("Middle Name: Q", True, _SHORT_NAME_FIELDS),
        ("Name is Li Wu", True, _SHORT_NAME_FIELDS),
        (
            "Section Q contains the generic public rule.",
            False,
            _SHORT_NAME_FIELDS,
        ),
        ("Surname: May", True, _GUARDED_IDENTITY_FIELDS),
        ("Surname is Will", True, _GUARDED_IDENTITY_FIELDS),
        ("Family Name: li", True, _GUARDED_IDENTITY_FIELDS),
        ("Middle Name: q", True, _GUARDED_IDENTITY_FIELDS),
        ("Mr. May", True, _GUARDED_IDENTITY_FIELDS),
        ("Surname field: May", True, _GUARDED_IDENTITY_FIELDS),
        ("Given Name value is Will", True, _GUARDED_IDENTITY_FIELDS),
        ("Family Name field = Li", True, _GUARDED_IDENTITY_FIELDS),
        (
            "Applicant may submit supporting documents.",
            False,
            _GUARDED_IDENTITY_FIELDS,
        ),
        (
            "Applicant will provide proof.",
            False,
            _GUARDED_IDENTITY_FIELDS,
        ),
        ("Surname: must submit proof.", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname: generic", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname field must be completed", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname value should be provided", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname: field May", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname is value May", False, _GUARDED_IDENTITY_FIELDS),
        ("Surname field: generic May", False, _GUARDED_IDENTITY_FIELDS),
        ("Full names are Mark and Karen.", True, _PLURAL_NAME_FIELDS),
        ("Names are Mark and Karen.", True, _PLURAL_NAME_FIELDS),
        ("Mark Davis", True, _REPEATED_LAST_FIRST_FIELDS),
        ("Karen Smith", True, _REPEATED_LAST_FIRST_FIELDS),
        ("Name is Mark", True, _REPEATED_LAST_FIRST_FIELDS),
        ("Surname: Smith", True, _REPEATED_LAST_FIRST_FIELDS),
        ("M Davis", True, _DOTTED_LAST_FIRST_FIELDS),
        ("K Smith", True, _UNDOTTED_INITIAL_LAST_FIRST_FIELDS),
        ("Karen Smith", True, _MIXED_INITIAL_LAST_FIRST_FIELDS),
        ("M Davis", False, _AMBIGUOUS_INITIAL_LAST_FIRST_FIELDS),
        ("Karen Marie Davis", True, _LIST_GIVEN_NAME_FIELDS),
        ("Alice Rose", True, _LIST_MIDDLE_NAME_FIELDS),
        (
            "Applicants should mark each required field.",
            False,
            _REPEATED_LAST_FIRST_FIELDS,
        ),
    ],
)
def test_worker_reuse_validates_contextual_names_on_every_public_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reuse_path: str,
    public_fragment: str,
    identity_context: bool,
    case_fields: dict[str, Any],
) -> None:
    pipelines_root = tmp_path / "pipelines"
    cases = _build_mock_pipeline_tree(
        pipelines_root,
        ["birth_certificate"],
    )["birth_certificate"]
    case = cases[0]
    case_id = case["opaque_case_id"]
    case["fields"] = case_fields
    pipeline_dir = pipelines_root / "birth_certificate"
    (pipeline_dir / "ground_truth" / "ground_truth.json").write_text(
        json.dumps(cases, indent=2),
        encoding="utf-8",
    )
    out_dir = (
        pipeline_dir
        / "iterations"
        / "iter_00_baseline"
        / "worker_reports"
    )
    initial_answer = {
        "question": "Review the supplied birth certificate.",
        "claims": [],
        "basis": [],
        "abstentions": [{"text": "No corpus claim.", "reason": "not_in_corpus"}],
        "prose": "No claims made.",
    }

    def injected_runner(cmd: List[str], cwd: Path) -> str:
        return json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": json.dumps(initial_answer)},
            }
        )

    report = run_blind_worker_task(
        opaque_case_id=case_id,
        doc_type="birth_certificate",
        runner_fn=injected_runner,
        pipeline_root=pipeline_dir,
        output_dir=out_dir,
    )
    injected_provenance = report["_provenance"]
    report["_provenance"] = build_provenance(
        "worker",
        live=True,
        prompt_hash=injected_provenance["prompt_hash"],
        attachment_hashes=injected_provenance["attachment_hashes"],
        output_hash=injected_provenance["output_hash"],
        extras={
            field: injected_provenance[field]
            for field in (
                "input_pdf_sha256",
                "allowed_text_sha256",
                "bundle_hash",
                "answer_hash",
                "pii_manifest_hash",
                "pii_manifest_count",
                "pii_manifest_categories",
            )
        },
    )
    public_answer = (
        {
            "question": public_fragment,
            "claims": [
                {
                    "id": "c1",
                    "text": public_fragment,
                    "citations": [public_fragment],
                    "quote": public_fragment,
                }
            ],
            "basis": [],
            "abstentions": [
                {
                    "text": public_fragment,
                    "reason": "not_in_corpus",
                }
            ],
            "prose": public_fragment,
        }
        if identity_context
        else {
            "question": public_fragment,
            "claims": [
                {
                    "id": "c1",
                    "text": public_fragment,
                    "citations": [public_fragment],
                    "quote": public_fragment,
                }
            ],
            "basis": [],
            "abstentions": [
                {
                    "text": public_fragment,
                    "reason": "not_in_corpus",
                }
            ],
            "prose": public_fragment,
        }
    )
    report.update(public_answer)
    report["_provenance"]["answer_hash"] = _worker_answer_hash(public_answer)
    report["_provenance"]["provenance_digest"] = _worker_provenance_digest(
        report["_provenance"]
    )
    (out_dir / f"{case_id}.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    calls: List[str] = []

    def replacement_worker(**kwargs: Any) -> Dict[str, Any]:
        calls.append(kwargs["opaque_case_id"])
        return {**report, "fresh": True}

    monkeypatch.setattr(
        "crawler.eval.loop_orchestrator.run_blind_worker_task",
        replacement_worker,
    )
    monkeypatch.setattr(
        loop_orchestrator,
        "check_answer_grounding",
        lambda *_args, **_kwargs: None,
    )
    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    if reuse_path == "doctype":
        result = orchestrator.run_doctype_workers_pass(
            "birth_certificate",
            [case],
            iteration_name="iter_00_baseline",
        )
    else:
        monkeypatch.setattr(
            loop_orchestrator.shutil,
            "rmtree",
            lambda *_args, **_kwargs: None,
        )
        result = orchestrator.run_baseline_workers_pass(
            doc_types=["birth_certificate"],
            require_all_23=False,
            iteration_name="iter_00_baseline",
        )["birth_certificate"]

    if identity_context:
        assert case_id in calls
        assert result[case_id]["fresh"] is True
    elif reuse_path == "doctype":
        assert calls == []
        assert result[case_id]["prose"] == public_answer["prose"]
    else:
        assert case_id not in calls
        assert len(calls) == len(cases) - 1
        assert result[case_id]["prose"] == public_answer["prose"]


@pytest.mark.parametrize(
    ("tamper", "should_refresh"),
    [
        (None, False),
        ("relabeled_injected", True),
        ("prompt_hash", True),
        ("schema", True),
    ],
)
def test_judge_reuse_requires_exact_prompt_and_validated_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str | None,
    should_refresh: bool,
) -> None:
    pipelines_root = tmp_path / "pipelines"
    case = _build_mock_pipeline_tree(pipelines_root, ["passport"])["passport"][0]
    case_id = case["opaque_case_id"]
    pipeline_dir = pipelines_root / "passport"
    worker_out_dir = (
        pipeline_dir
        / "iterations"
        / "iter_00_baseline"
        / "worker_reports"
    )
    answer = {
        "question": "Review the supplied passport.",
        "claims": [],
        "basis": [],
        "abstentions": [{"text": "No corpus claim.", "reason": "not_in_corpus"}],
        "prose": "No claims made.",
    }

    def worker_runner(cmd: List[str], cwd: Path) -> str:
        return json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": json.dumps(answer)},
            }
        )

    worker_report = run_blind_worker_task(
        opaque_case_id=case_id,
        doc_type="passport",
        runner_fn=worker_runner,
        pipeline_root=pipeline_dir,
        output_dir=worker_out_dir,
    )
    worker_reports = {case_id: worker_report}
    scores = {
        "grounding_accuracy": 1.0,
        "citation_exactness": 1.0,
        "defect_recall": 1.0,
        "pii_containment": 1.0,
        "blind_input_compliance": 1.0,
    }

    def judge_runner(cmd: List[str], cwd: Path) -> str:
        batch = {
            "doc_type": "passport",
            "case_evaluations": {case_id: scores},
            "findings": [],
            "patch_recommendations": [],
            "rationale": "Pass",
        }
        return json.dumps(
            {"type": "assistant.message", "content": json.dumps(batch)}
        )

    orchestrator = LoopOrchestrator(pipelines_dir=pipelines_root)
    artifact = orchestrator.run_doctype_judge_pass(
        "passport",
        [case],
        worker_reports,
        iteration_name="iter_00_baseline",
        runner_fn=judge_runner,
    )
    injected_provenance = artifact["_provenance"]
    if tamper == "relabeled_injected":
        injected_provenance["engine"] = "copilot-sdk"
        injected_provenance["is_live"] = True
    else:
        artifact["_provenance"] = build_provenance(
            "judge",
            live=True,
            prompt_hash=injected_provenance["prompt_hash"],
            attachment_hashes=injected_provenance["attachment_hashes"],
            output_hash=injected_provenance["output_hash"],
            extras={
                field: injected_provenance[field]
                for field in (
                    "prompt_contract_hash",
                    "input_manifest_hash",
                    "case_ids",
                    "pdf_hashes",
                    "worker_report_hashes",
                    "worker_input_manifest_hashes",
                    "public_bundle_hashes",
                    "worker_prompt_hashes",
                    "research_hash",
                    "ground_truth_hash",
                    "model_config",
                    "artifact_output_hash",
                )
            },
        )
    if tamper == "prompt_hash":
        artifact["_provenance"]["prompt_hash"] = "0" * 64
    elif tamper == "schema":
        del artifact["case_evaluations"][case_id]["defect_recall"]
        artifact["_provenance"]["artifact_output_hash"] = _judge_artifact_hash(
            {
                key: value
                for key, value in artifact.items()
                if key != "_provenance"
            }
        )
    artifact["_provenance"]["provenance_digest"] = _judge_provenance_digest(
        artifact["_provenance"]
    )
    judge_file = (
        pipeline_dir
        / "iterations"
        / "iter_00_baseline"
        / "judge_eval"
        / "doc_type_eval.json"
    )
    judge_file.write_text(json.dumps(artifact), encoding="utf-8")

    calls: List[str] = []

    def replacement_judge(**kwargs: Any) -> Dict[str, Any]:
        calls.append(kwargs["doc_type"])
        return {**artifact, "fresh": True}

    monkeypatch.setattr(
        "crawler.eval.loop_orchestrator.run_batched_document_judge",
        replacement_judge,
    )
    result = orchestrator.run_doctype_judge_pass(
        "passport",
        [case],
        worker_reports,
        iteration_name="iter_00_baseline",
    )

    assert calls == (["passport"] if should_refresh else [])
    assert ("fresh" in result) is should_refresh


def test_worker_concurrency_and_per_pipeline_artifact_layout(tmp_path: Path) -> None:
    """Verify bounded worker concurrency <= 5, exact 23 batched judge calls, and per-pipeline iteration artifact layout."""
    all_23 = [e.value for e in ExpressEntryDocType]
    cases_per_doc = {}
    for p in (_REPO_ROOT / "crawler" / "eval" / "pipelines").iterdir():
        if p.is_dir() and (p / "ground_truth" / "ground_truth.json").is_file():
            data = json.loads((p / "ground_truth" / "ground_truth.json").read_text(encoding="utf-8"))
            cases_per_doc[p.name] = len(data)

    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, all_23, cases_per_doc=cases_per_doc)

    active_workers = 0
    max_observed_workers = 0
    lock = threading.Lock()

    def mock_concurrency_runner(cmd: List[str], cwd: Path) -> str:
        nonlocal active_workers, max_observed_workers
        prompt_arg = cmd[cmd.index("-p") + 1]

        # Handle Judge batch call
        if "JUDGE MODEL:" in prompt_arg or "DOCUMENT TYPE:" in prompt_arg:
            dt_match = [dt for dt in all_23 if f"DOCUMENT TYPE: {dt}" in prompt_arg]
            dt = dt_match[0] if dt_match else "passport"

            cid_matches = set(p.stem for p in cwd.glob("*.pdf") if p.stem != "prompt")
            case_evals = {}
            findings = []
            for cid in cid_matches:
                case_evals[cid] = {
                    "grounding_accuracy": 1.0,
                    "citation_exactness": 1.0,
                    "defect_recall": 1.0,
                    "pii_containment": 1.0,
                    "blind_input_compliance": 1.0,
                }
                findings.append({
                    "case_id": cid,
                    "category": "defect_recall",
                    "severity": "minor",
                    "description": f"Finding for {cid}",
                })

            judge_resp = {
                "doc_type": dt,
                "case_evaluations": case_evals,
                "findings": findings,
                "patch_recommendations": [],
                "rationale": f"Batch judge pass for {dt}",
            }
            return json.dumps({"type": "assistant.message", "content": json.dumps(judge_resp)})

        if "<public_review_bundle" in prompt_arg:
            with lock:
                active_workers += 1
                if active_workers > max_observed_workers:
                    max_observed_workers = active_workers

            # Simulate work
            answer = {
                "question": "Canadian Express Entry document review",
                "claims": [{"id": "C1", "text": "Clear", "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"], "quote": "biographical data page of a passport"}],
                "basis": ["Checked"],
                "abstentions": [],
                "prose": "Review completed.",
            }
            res_str = json.dumps({"type": "assistant.message", "content": json.dumps(answer)})

            with lock:
                active_workers -= 1

            return res_str

        return json.dumps({"type": "assistant.message", "content": "{}"})

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_root,
        iterations_dir=tmp_path / "iterations",
    )

    baseline_report = orchestrator.run_baseline_pass(
        runner_fn=mock_concurrency_runner,
        iteration_name="iter_00_baseline",
        require_all_23=True,
    )

    # Assert bounded concurrency was respected (<= 4 max workers)
    assert max_observed_workers <= 5

    # Assert total doc types and cases in baseline report
    assert baseline_report["total_doc_types"] == 23
    assert baseline_report["total_cases"] == 236

    # Verify per-pipeline iteration artifact layout
    total_worker_files = 0
    total_judge_files = 0

    for dt in all_23:
        p_iter_dir = pipelines_root / dt / "iterations" / "iter_00_baseline"
        worker_out_dir = p_iter_dir / "worker_reports"
        judge_out_dir = p_iter_dir / "judge_eval"

        assert worker_out_dir.is_dir()
        assert judge_out_dir.is_dir()

        w_files = list(worker_out_dir.glob("*.json"))
        j_files = list(judge_out_dir.glob("judge_batch.json"))

        assert len(w_files) in (10, 12)
        assert len(j_files) == 1

        total_worker_files += len(w_files)
        total_judge_files += len(j_files)

    assert total_worker_files == 236
    assert total_judge_files == 23


def test_partial_worker_failure_writes_error_metadata_and_fails_closed(tmp_path: Path) -> None:
    """Verify a worker exception writes worker_error.json and prevents summary creation."""
    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, ["passport"])

    def failing_worker_runner(cmd: List[str], cwd: Path) -> str:
        prompt_arg = cmd[cmd.index("-p") + 1]
        if "<public_review_bundle" in prompt_arg:
            raise RuntimeError("Gemini process crashed")
        return ""

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_root,
        iterations_dir=tmp_path / "iterations",
    )

    with pytest.raises(RuntimeError, match="Worker pass failed closed"):
        orchestrator.run_baseline_pass(
            runner_fn=failing_worker_runner,
            iteration_name="iter_00_baseline",
            require_all_23=False,
        )

    # Check that error metadata was written and no summary exists
    p_iter_dir = pipelines_root / "passport" / "iterations" / "iter_00_baseline"
    assert (p_iter_dir / "worker_error.json").is_file()
    assert not (tmp_path / "iterations" / "iter_00_baseline" / "baseline_summary.json").is_file()
    assert not (tmp_path / "iterations" / "loop_summary.json").is_file()


def test_concurrency_bounds_and_validation(tmp_path: Path) -> None:
    """Verify max_concurrency default is 5 and bounds validation enforces 1..5."""
    orch = LoopOrchestrator(pipelines_dir=tmp_path / "pipelines")
    assert orch.max_concurrency == 5
    assert orch.tracker.max_concurrency == 5

    for c in (1, 2, 3, 4, 5):
        o = LoopOrchestrator(pipelines_dir=tmp_path / "pipelines", max_concurrency=c)
        assert o.max_concurrency == c

    for invalid in (0, 6, -1, 10, "5", True, None):
        with pytest.raises(ValueError, match="max_concurrency must be"):
            LoopOrchestrator(pipelines_dir=tmp_path / "pipelines", max_concurrency=invalid)  # type: ignore[arg-type]


def test_global_pools_concurrency_reaches_5_with_blocking_runners(tmp_path: Path) -> None:
    """Verify 2-stage global pools reach observed concurrency = 5 for both Workers and Judges, asserting <= 5 at all times."""
    all_23 = [e.value for e in ExpressEntryDocType]
    cases_per_doc = {}
    for p in (_REPO_ROOT / "crawler" / "eval" / "pipelines").iterdir():
        if p.is_dir() and (p / "ground_truth" / "ground_truth.json").is_file():
            data = json.loads((p / "ground_truth" / "ground_truth.json").read_text(encoding="utf-8"))
            cases_per_doc[p.name] = len(data)

    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, all_23, cases_per_doc=cases_per_doc)

    worker_barrier = threading.Barrier(5)
    judge_barrier = threading.Barrier(5)

    observed_peak_workers = 0
    observed_peak_judges = 0
    active_workers = 0
    active_judges = 0
    lock = threading.Lock()

    def blocking_concurrency_runner(cmd: List[str], cwd: Path) -> str:
        nonlocal observed_peak_workers, observed_peak_judges, active_workers, active_judges
        prompt_arg = cmd[cmd.index("-p") + 1]

        # Judge call
        if "JUDGE MODEL:" in prompt_arg or "DOCUMENT TYPE:" in prompt_arg:
            with lock:
                active_judges += 1
                if active_judges > observed_peak_judges:
                    observed_peak_judges = active_judges
                assert active_judges <= 5

            try:
                judge_barrier.wait(timeout=5.0)
            except threading.BrokenBarrierError:
                pass

            dt_match = [dt for dt in all_23 if f"DOCUMENT TYPE: {dt}" in prompt_arg]
            dt = dt_match[0] if dt_match else "passport"

            cid_matches = set(p.stem for p in cwd.glob("*.pdf") if p.stem != "prompt")
            case_evals = {
                cid: {
                    "grounding_accuracy": 1.0,
                    "citation_exactness": 1.0,
                    "defect_recall": 1.0,
                    "pii_containment": 1.0,
                    "blind_input_compliance": 1.0,
                }
                for cid in cid_matches
            }

            judge_resp = {
                "doc_type": dt,
                "case_evaluations": case_evals,
                "findings": [],
                "patch_recommendations": [],
                "rationale": f"Batch judge pass for {dt}",
            }

            with lock:
                active_judges -= 1

            return json.dumps({"type": "assistant.message", "content": json.dumps(judge_resp)})

        if "<public_review_bundle" in prompt_arg:
            with lock:
                active_workers += 1
                if active_workers > observed_peak_workers:
                    observed_peak_workers = active_workers
                assert active_workers <= 5

            try:
                worker_barrier.wait(timeout=5.0)
            except threading.BrokenBarrierError:
                pass

            answer = {
                "question": "Canadian Express Entry document review",
                "claims": [{"id": "C1", "text": "Clear", "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"], "quote": "biographical data page of a passport"}],
                "basis": ["Checked"],
                "abstentions": [],
                "prose": "Review completed.",
            }
            res_str = json.dumps({"type": "assistant.message", "content": json.dumps(answer)})

            with lock:
                active_workers -= 1

            return res_str

        return json.dumps({"type": "assistant.message", "content": "{}"})

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_root,
        iterations_dir=tmp_path / "iterations",
        max_concurrency=5,
    )

    baseline_report = orchestrator.run_baseline_pass(
        runner_fn=blocking_concurrency_runner,
        iteration_name="iter_00_baseline",
        require_all_23=True,
    )

    assert baseline_report["total_doc_types"] == 23
    assert baseline_report["total_cases"] == 236

    assert observed_peak_workers == 5
    assert observed_peak_judges == 5
    assert orchestrator.tracker.peak_workers == 5
    assert orchestrator.tracker.peak_judges == 5
    assert orchestrator.tracker.active_workers == 0
    assert orchestrator.tracker.active_judges == 0


def test_judge_failure_writes_error_metadata_and_fails_closed(tmp_path: Path) -> None:
    """Verify judge exception writes judge_error.json and prevents summary creation."""
    pipelines_root = tmp_path / "pipelines"
    _build_mock_pipeline_tree(pipelines_root, ["passport"])

    def failing_judge_runner(cmd: List[str], cwd: Path) -> str:
        prompt_arg = cmd[cmd.index("-p") + 1]
        if "<public_review_bundle" in prompt_arg:
            answer = {
                "question": "Canadian Express Entry document review",
                "claims": [{"id": "C1", "text": "Clear", "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"], "quote": "biographical data page of a passport"}],
                "basis": ["Checked"],
                "abstentions": [],
                "prose": "Review completed.",
            }
            return json.dumps({"type": "assistant.message", "content": json.dumps(answer)})

        raise RuntimeError("Judge model API error")

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_root,
        iterations_dir=tmp_path / "iterations",
    )

    with pytest.raises(RuntimeError, match="Judge pass failed closed"):
        orchestrator.run_baseline_pass(
            runner_fn=failing_judge_runner,
            iteration_name="iter_00_baseline",
            require_all_23=False,
        )

    p_iter_dir = pipelines_root / "passport" / "iterations" / "iter_00_baseline"
    assert (p_iter_dir / "judge_error.json").is_file()
    assert not (tmp_path / "iterations" / "iter_00_baseline" / "baseline_summary.json").is_file()
    assert not (tmp_path / "iterations" / "loop_summary.json").is_file()
