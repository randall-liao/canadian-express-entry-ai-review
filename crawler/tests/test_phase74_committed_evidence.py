from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from crawler.eval import phase74_evidence
from crawler.eval.phase74_evidence import (
    EXPECTED_WORKER_SOURCE_PATHS,
    EvidenceValidationError,
    ScoreMetrics,
    _validate_frozen_worker_source,
    canonical_evidence_hash,
    validate_committed_phase74_evidence,
)
from crawler.eval.pipeline_worker import _worker_provenance_digest
from crawler.eval.pipeline_judge import _judge_provenance_digest
from crawler.eval.genuine_optimizer import optimizer_provenance_digest
from crawler.eval.genuine_optimizer import derive_optimizer_candidate_id


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE_ROOT = _REPO_ROOT / "crawler" / "eval" / "phase74_evidence"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _sync_links(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text())
    links_root = root.parent / "links"
    for link_path in links_root.glob("*/committed_evidence.json"):
        doc_type = link_path.parent.name
        prefix = f"documents/{doc_type}/"
        link = json.loads(link_path.read_text())
        link["evidence_manifest_hash"] = manifest["manifest_hash"]
        link["document_files"] = {
            path: digest
            for path, digest in manifest["files"].items()
            if path.startswith(prefix)
        }
        link["final_revision"] = manifest["final_revision"]
        link["final_manifest_hash"] = manifest["final_manifest_hash"]
        _write_json(link_path, link)


def _rehash_object(path: Path, root: Path) -> None:
    value = json.loads(path.read_text())
    value["evidence_hash"] = canonical_evidence_hash(value)
    _write_json(path, value)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rel = path.relative_to(root).as_posix()
    manifest["files"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    _rehash_manifest(root, manifest)
    _sync_links(root)


def _rehash_manifest(root: Path, manifest: dict) -> None:
    manifest["manifest_hash"] = canonical_evidence_hash(manifest)
    _write_json(root / "manifest.json", manifest)
    _sync_links(root)


@pytest.fixture
def evidence_root(tmp_path: Path) -> Path:
    target = tmp_path / "evidence"
    shutil.copytree(_EVIDENCE_ROOT, target)
    links = tmp_path / "links"
    links.mkdir()
    for source in _REPO_ROOT.glob(
        "crawler/eval/pipelines/*/iterations/iter_sdk_final/committed_evidence.json"
    ):
        destination = links / source.parents[2].name / "committed_evidence.json"
        destination.parent.mkdir()
        shutil.copy2(source, destination)
    return target


def _validate(root: Path) -> None:
    validate_committed_phase74_evidence(
        root,
        source_root=_REPO_ROOT,
        committed_links_root=root.parent / "links",
    )


def _first_worker(root: Path) -> Path:
    return sorted(root.glob("documents/*/workers/*.json"))[0]


def _first_judge(root: Path) -> Path:
    return sorted(root.glob("documents/*/judge.json"))[0]


def test_fresh_evidence_validates_without_ignored_raw_reports(
    evidence_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes

    def guarded_read_text(path: Path, *args, **kwargs):
        if "reports" in path.parts:
            raise AssertionError("gate attempted to read ignored raw reports")
        return original_read_text(path, *args, **kwargs)

    def guarded_read_bytes(path: Path, *args, **kwargs):
        if "reports" in path.parts:
            raise AssertionError("gate attempted to read ignored raw reports")
        return original_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    _validate(evidence_root)


def test_frozen_source_inventory_is_exactly_all_worker_visible_skills() -> None:
    expected_document_skills = {
        f"skills/document-agents/{stem}.md"
        for stem in {
            "passport",
            "language-test",
            "eca",
            "employment-reference-letter",
            "proof-of-funds",
            "medical",
            "police-certificate",
            "digital-photos",
            "translation",
            "job-offer",
            "proof-of-studies",
            "certificate-of-qualification",
            "birth-certificate",
            "marriage-certificate",
            "common-law-union",
            "divorce-certificate",
            "death-certificate",
            "adoption-certificate",
            "use-of-representative",
            "relative-in-canada",
            "other-name",
            "authority-to-release",
            "letter-of-explanation",
        }
    }
    assert EXPECTED_WORKER_SOURCE_PATHS == (
        expected_document_skills | {"skills/pdf/SKILL.md"}
    )
    assert len(EXPECTED_WORKER_SOURCE_PATHS) == 24


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_frozen_source_inventory_rejects_missing_or_extra_keys(
    mutation: str,
) -> None:
    source_hashes = {path: "a" * 64 for path in EXPECTED_WORKER_SOURCE_PATHS}
    if mutation == "missing":
        source_hashes.pop(sorted(source_hashes)[0])
    else:
        source_hashes["skills/document-agents/unexpected.md"] = "b" * 64

    with pytest.raises(EvidenceValidationError, match="inventory mismatch"):
        _validate_frozen_worker_source(
            _REPO_ROOT,
            "a" * 40,
            source_hashes,
        )


def test_frozen_source_rejects_current_worktree_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_hashes = {path: "a" * 64 for path in EXPECTED_WORKER_SOURCE_PATHS}
    mutated_target = "skills/document-agents/passport.md"
    monkeypatch.setattr(
        phase74_evidence,
        "_git_blob_hash",
        lambda source_root, revision, target: source_hashes[target],
    )
    monkeypatch.setattr(
        phase74_evidence,
        "_file_hash",
        lambda path: (
            "b" * 64
            if path.relative_to(_REPO_ROOT).as_posix() == mutated_target
            else source_hashes[path.relative_to(_REPO_ROOT).as_posix()]
        ),
    )

    with pytest.raises(EvidenceValidationError, match="source hash mismatch"):
        _validate_frozen_worker_source(
            _REPO_ROOT,
            "a" * 40,
            source_hashes,
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_gate_rejects_missing_or_duplicate_worker(
    evidence_root: Path,
    mutation: str,
) -> None:
    worker = _first_worker(evidence_root)
    manifest_path = evidence_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "missing":
        manifest["files"].pop(worker.relative_to(evidence_root).as_posix())
        worker.unlink()
    else:
        duplicate = worker.with_name("duplicate.json")
        shutil.copy2(worker, duplicate)
        manifest["files"][duplicate.relative_to(evidence_root).as_posix()] = (
            hashlib.sha256(duplicate.read_bytes()).hexdigest()
        )
    _rehash_manifest(evidence_root, manifest)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "wrong-model"),
        ("runtime_protocol_version", "999"),
        ("provenance_digest", "0" * 64),
        ("input_pdf_sha256", "1" * 64),
    ],
)
def test_gate_rejects_worker_provenance_tampering(
    evidence_root: Path,
    field: str,
    value: str,
) -> None:
    path = _first_worker(evidence_root)
    data = json.loads(path.read_text())
    data["provenance"][field] = value
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_worker_correction_chain_tampering(
    evidence_root: Path,
) -> None:
    path = next(
        path
        for path in sorted(evidence_root.glob("documents/*/workers/*.json"))
        if json.loads(path.read_text())["provenance"]["turn_count"] == 2
    )
    data = json.loads(path.read_text())
    data["provenance"]["assistant_response_hash_chain"][0] = "2" * 64
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    ("manifest_field", "provenance_field", "value"),
    [
        ("sdk_version", "sdk_version", "9.9.9"),
        ("protocol_version", "runtime_protocol_version", "999"),
        ("runtime_version", None, "9.9.9"),
    ],
)
def test_gate_rejects_coordinated_runtime_identity_tampering(
    evidence_root: Path,
    manifest_field: str,
    provenance_field: str | None,
    value: str,
) -> None:
    worker_path = _first_worker(evidence_root)
    worker = json.loads(worker_path.read_text())
    worker["runtime_version"] = (
        value if manifest_field == "runtime_version" else worker["runtime_version"]
    )
    if provenance_field is not None:
        worker["provenance"][provenance_field] = value
        worker["provenance"]["provenance_digest"] = _worker_provenance_digest(
            worker["provenance"]
        )
    _write_json(worker_path, worker)
    _rehash_object(worker_path, evidence_root)
    manifest_path = evidence_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[manifest_field] = value
    _rehash_manifest(evidence_root, manifest)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_missing_judge(evidence_root: Path) -> None:
    path = _first_judge(evidence_root)
    manifest = json.loads((evidence_root / "manifest.json").read_text())
    manifest["files"].pop(path.relative_to(evidence_root).as_posix())
    path.unlink()
    _rehash_manifest(evidence_root, manifest)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("field", ["final_manifest_hash", "final_revision"])
def test_gate_rejects_wrong_frozen_manifest_or_revision(
    evidence_root: Path,
    field: str,
) -> None:
    manifest = json.loads((evidence_root / "manifest.json").read_text())
    manifest[field] = "0" * (64 if field.endswith("hash") else 40)
    _rehash_manifest(evidence_root, manifest)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("peak", [4, 6])
def test_gate_rejects_wrong_concurrency_peak(
    evidence_root: Path,
    peak: int,
) -> None:
    path = evidence_root / "concurrency.json"
    data = json.loads(path.read_text())
    data["declared_peak"] = peak
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_missing_shared_document(evidence_root: Path) -> None:
    path = sorted(evidence_root.glob("documents/*/shared_evaluation.json"))[0]
    manifest = json.loads((evidence_root / "manifest.json").read_text())
    manifest["files"].pop(path.relative_to(evidence_root).as_posix())
    path.unlink()
    _rehash_manifest(evidence_root, manifest)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("field", ["survivor_count", "error_count"])
def test_gate_rejects_cleanup_survivor_or_error(
    evidence_root: Path,
    field: str,
) -> None:
    path = evidence_root / "cleanup.json"
    data = json.loads(path.read_text())
    data[field] = 1
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_missing_cumulative_accepted_audit(
    evidence_root: Path,
) -> None:
    path = evidence_root / "accepted_patches.json"
    data = json.loads(path.read_text())
    data["records"].pop()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_metric_regression(evidence_root: Path) -> None:
    path = evidence_root / "accepted_patches.json"
    data = json.loads(path.read_text())
    data["records"][0]["holdout_deltas"]["grounding_accuracy"] = -0.01
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_rejected_decision_with_coordinated_accepting_metrics(
    evidence_root: Path,
) -> None:
    path = evidence_root / "rejected_patches.json"
    data = json.loads(path.read_text())
    record = next(
        item
        for item in data["records"]
        if item["reason_code"] == "metric_gate_rejected"
    )
    record["candidate_train"] = dict(record["baseline_train"])
    record["candidate_holdout"] = dict(record["baseline_holdout"])
    for field in record["candidate_train"]:
        record["candidate_train"][field] = min(
            1.0,
            record["baseline_train"][field] + 0.01,
        )
    record["training_deltas"] = {
        field: record["candidate_train"][field] - record["baseline_train"][field]
        for field in record["baseline_train"]
    }
    record["holdout_deltas"] = {
        field: 0.0 for field in record["baseline_holdout"]
    }
    record["evidence_hash"] = canonical_evidence_hash(record)
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_coordinated_shared_acceptance_relabelled_rejected(
    evidence_root: Path,
) -> None:
    path = evidence_root / "shared_decision.json"
    data = json.loads(path.read_text())
    data["candidate_train"] = dict(data["baseline_train"])
    data["candidate_holdout"] = dict(data["baseline_holdout"])
    for field in data["candidate_train"]:
        data["candidate_train"][field] = min(
            1.0,
            data["baseline_train"][field] + 0.01,
        )
    data["training_deltas"] = {
        field: data["candidate_train"][field] - data["baseline_train"][field]
        for field in data["baseline_train"]
    }
    data["holdout_deltas"] = {
        field: 0.0 for field in data["baseline_holdout"]
    }
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["target", "hash", "trailer"])
def test_gate_rejects_patch_target_hash_or_trailer(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "accepted_patches.json"
    data = json.loads(path.read_text())
    record = data["records"][0]
    if mutation == "target":
        record["target_file"] = "README.md"
    elif mutation == "hash":
        record["source_after_hash"] = "0" * 64
    else:
        record["commit"] = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("sentinel", ["Jane Doe", "/home/private/project"])
def test_gate_rejects_pii_or_absolute_path_sentinel(
    evidence_root: Path,
    sentinel: str,
) -> None:
    path = evidence_root / "cleanup.json"
    data = json.loads(path.read_text())
    data["unexpected"] = sentinel
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    ("selector", "nested", "extra_key"),
    [
        ("manifest.json", (), "prose"),
        ("worker", (), "basis"),
        ("worker", ("provenance",), "raw_prompt"),
        ("judge", (), "findings"),
        ("judge", ("provenance",), "reasoning"),
        (
            "judge",
            ("sanitized_evaluation_payload", "case_evaluations", "*"),
            "unexpected_metric",
        ),
        ("shared", (), "rationale"),
        ("shared", ("baseline_train",), "extra_score"),
        ("accepted_patches.json", (), "unexpected"),
        ("accepted_patches.json", ("records", 0), "basis"),
        ("accepted_patches.json", ("records", 0, "optimizer_provenance"), "content"),
        ("rejected_patches.json", ("records", 0), "prose"),
        ("concurrency.json", (), "pid"),
        ("concurrency.json", ("events", 0), "path"),
        ("cleanup.json", (), "findings"),
        ("frozen_manifest.json", ("final_manifest",), "unexpected"),
        ("shared_decision.json", (), "basis"),
    ],
)
def test_gate_forbids_extra_fields_at_every_evidence_level(
    evidence_root: Path,
    selector: str,
    nested: tuple,
    extra_key: str,
) -> None:
    path = {
        "worker": _first_worker(evidence_root),
        "judge": _first_judge(evidence_root),
        "shared": sorted(
            evidence_root.glob("documents/*/shared_evaluation.json")
        )[0],
    }.get(selector, evidence_root / selector)
    data = json.loads(path.read_text())
    target: object = data
    for part in nested:
        if part == "*":
            target = next(iter(target.values()))  # type: ignore[union-attr]
        else:
            target = target[part]  # type: ignore[index]
    target[extra_key] = "innocent-looking value"  # type: ignore[index]
    _write_json(path, data)
    if path.name == "manifest.json":
        _rehash_manifest(evidence_root, data)
    else:
        _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("bad_hash", ["not-hex", "a" * 63, "A" * 64])
@pytest.mark.parametrize(
    ("selector", "nested", "field"),
    [
        ("manifest.json", (), "final_manifest_hash"),
        ("worker", (), "report_hash"),
        ("worker", ("provenance",), "input_pdf_sha256"),
        ("worker", ("provenance",), "provenance_digest"),
        ("judge", (), "raw_output_hash"),
        ("judge", ("provenance",), "input_manifest_hash"),
        ("shared", (), "shared_candidate_hash"),
        ("accepted_patches.json", ("records", 0), "candidate_content_hash"),
        ("cleanup.json", (), "registry_hash"),
        ("concurrency.json", ("events", 0), "process_instance_hash"),
    ],
)
def test_gate_rejects_noncanonical_hash_scalars(
    evidence_root: Path,
    selector: str,
    nested: tuple,
    field: str,
    bad_hash: str,
) -> None:
    path = {
        "worker": _first_worker(evidence_root),
        "judge": _first_judge(evidence_root),
        "shared": sorted(
            evidence_root.glob("documents/*/shared_evaluation.json")
        )[0],
    }.get(selector, evidence_root / selector)
    data = json.loads(path.read_text())
    target = data
    for part in nested:
        target = target[part]
    target[field] = bad_hash
    _write_json(path, data)
    if path.name == "manifest.json":
        _rehash_manifest(evidence_root, data)
    else:
        _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    "mutation",
    ["model", "pdf", "case", "worker", "research", "ground_truth"],
)
def test_gate_recomputes_judge_input_manifest(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = _first_judge(evidence_root)
    data = json.loads(path.read_text())
    manifest = data["input_manifest"]
    provenance = data["provenance"]
    if mutation == "model":
        manifest["model_config"]["model"] = "gemini-3.6-flash"
        provenance["model_config"]["model"] = "gemini-3.6-flash"
    elif mutation == "pdf":
        manifest["pdf_hashes"][0], manifest["pdf_hashes"][1] = (
            manifest["pdf_hashes"][1],
            manifest["pdf_hashes"][0],
        )
        provenance["pdf_hashes"] = list(manifest["pdf_hashes"])
        provenance["attachment_hashes"] = list(manifest["pdf_hashes"])
    elif mutation == "case":
        manifest["case_ids"].pop()
        provenance["case_ids"] = list(manifest["case_ids"])
    elif mutation == "worker":
        manifest["worker_report_hashes"][0] = "a" * 64
        provenance["worker_report_hashes"] = list(
            manifest["worker_report_hashes"]
        )
    elif mutation == "research":
        manifest["research_hash"] = "b" * 64
        provenance["research_hash"] = "b" * 64
    else:
        manifest["ground_truth_hash"] = "c" * 64
        provenance["ground_truth_hash"] = "c" * 64
    provenance["input_manifest_hash"] = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    provenance["provenance_digest"] = _judge_provenance_digest(provenance)
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["candidate", "run", "target"])
def test_gate_rejects_coordinated_unrelated_proposal_binding(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "accepted_patches.json"
    data = json.loads(path.read_text())
    record = data["records"][0]
    provenance = record["optimizer_provenance"]
    if mutation == "candidate":
        record["candidate_id"] = "candidate_aaaaaaaaaaaa"
        provenance["candidate_id"] = record["candidate_id"]
    elif mutation == "run":
        record["parent_run_id"] = "sdk-20990101T000000Z-aaaaaaaaaaaa"
    else:
        record["target_file"] = "skills/document-agents/passport.md"
        provenance["target_file"] = record["target_file"]
    provenance["provenance_digest"] = optimizer_provenance_digest(provenance)
    record["evidence_hash"] = canonical_evidence_hash(record)
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_requires_all_23_documents_in_concurrency_trace(
    evidence_root: Path,
) -> None:
    path = evidence_root / "concurrency.json"
    data = json.loads(path.read_text())
    keep = set(data["distinct_documents"][:5]) | {"__preflight__"}
    data["events"] = [
        event for event in data["events"] if event["doc_type"] in keep
    ]
    data["distinct_documents"] = sorted(keep - {"__preflight__"})
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_unmatched_concurrency_event(evidence_root: Path) -> None:
    path = evidence_root / "concurrency.json"
    data = json.loads(path.read_text())
    data["events"].pop()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_gate_cross_links_cleanup_process_instances(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "cleanup.json"
    data = json.loads(path.read_text())
    if mutation == "extra":
        data["process_instance_hashes"].append("f" * 64)
        data["registry_record_count"] += 1
        data["registry_reaped_count"] += 1
    else:
        data["process_instance_hashes"].pop()
        data["registry_record_count"] -= 1
        data["registry_reaped_count"] -= 1
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_coordinated_shared_metric_and_candidate_tamper(
    evidence_root: Path,
) -> None:
    shared_path = sorted(
        evidence_root.glob("documents/*/shared_evaluation.json")
    )[0]
    shared = json.loads(shared_path.read_text())
    shared["baseline_train"]["grounding_accuracy"] += 0.01
    shared["training_deltas"]["grounding_accuracy"] = (
        shared["candidate_train"]["grounding_accuracy"]
        - shared["baseline_train"]["grounding_accuracy"]
    )
    shared["shared_candidate_id"] = "candidate_aaaaaaaaaaaa"
    _write_json(shared_path, shared)
    _rehash_object(shared_path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    "entry_kind",
    [
        "txt",
        "md",
        "json",
        "jsonl",
        "binary",
        "hidden",
        "symlink",
        "directory",
        "fifo",
    ],
)
def test_gate_rejects_every_unexpected_filesystem_entry(
    evidence_root: Path,
    entry_kind: str,
) -> None:
    if entry_kind == "directory":
        (evidence_root / "unexpected-dir").mkdir()
    elif entry_kind == "fifo":
        import os

        os.mkfifo(evidence_root / "unexpected.fifo")
    elif entry_kind == "symlink":
        (evidence_root / "unexpected-link").symlink_to(
            evidence_root / "manifest.json"
        )
    else:
        suffix = {
            "txt": ".txt",
            "md": ".md",
            "json": ".json",
            "jsonl": ".jsonl",
            "binary": ".bin",
            "hidden": "",
        }[entry_kind]
        name = ".hidden" if entry_kind == "hidden" else f"unexpected{suffix}"
        payload = b"\x00\xffraw" if entry_kind == "binary" else b"raw model output"
        (evidence_root / name).write_bytes(payload)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_does_not_open_ignored_corpus_db(
    evidence_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = Path.open

    def guarded_open(path: Path, *args, **kwargs):
        if path.name == "index.db":
            raise AssertionError("committed gate opened ignored corpus DB")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    _validate(evidence_root)


def test_gate_rejects_coordinated_wrong_shared_identity(
    evidence_root: Path,
) -> None:
    decision_path = evidence_root / "shared_decision.json"
    decision = json.loads(decision_path.read_text())
    target = "AGENTS.md"
    provenance = decision["optimizer_provenance"]
    candidate_id = derive_optimizer_candidate_id(
        provenance["input_findings_sha256"],
        provenance["prompt_hash"],
        target,
    )
    decision["target_file"] = target
    decision["candidate_id"] = candidate_id
    decision["run_id"] = "sdk-20990101T000000Z-aaaaaaaaaaaa"
    provenance["target_file"] = target
    provenance["candidate_id"] = candidate_id
    provenance["provenance_digest"] = optimizer_provenance_digest(provenance)
    decision["shared_decision_hash"] = "a" * 64
    _write_json(decision_path, decision)
    _rehash_object(decision_path, evidence_root)
    for path in evidence_root.glob("documents/*/shared_evaluation.json"):
        record = json.loads(path.read_text())
        record["shared_candidate_id"] = candidate_id
        record["shared_decision_hash"] = decision["shared_decision_hash"]
        record["shared_optimizer_provenance"] = provenance
        _write_json(path, record)
        _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["target", "source"])
def test_gate_rejects_forged_rejected_target_or_source(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "rejected_patches.json"
    data = json.loads(path.read_text())
    record = data["records"][0]
    if mutation == "target":
        target = "skills/document-agents/passport.md"
        record["target_file"] = target
        record["optimizer_provenance"]["target_file"] = target
        record["candidate_id"] = derive_optimizer_candidate_id(
            record["optimizer_provenance"]["input_findings_sha256"],
            record["optimizer_provenance"]["prompt_hash"],
            target,
        )
        record["optimizer_provenance"]["candidate_id"] = record["candidate_id"]
        record["optimizer_provenance"]["provenance_digest"] = (
            optimizer_provenance_digest(record["optimizer_provenance"])
        )
    else:
        record["source_hash"] = "a" * 64
    record["evidence_hash"] = canonical_evidence_hash(record)
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_coordinated_judge_artifact_hash_tamper(
    evidence_root: Path,
) -> None:
    path = _first_judge(evidence_root)
    data = json.loads(path.read_text())
    data["raw_output_hash"] = "a" * 64
    data["provenance"]["output_hash"] = "a" * 64
    data["provenance"]["provenance_digest"] = _judge_provenance_digest(
        data["provenance"]
    )
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    "mutation",
    ["score", "swap", "missing_payload", "prose", "version"],
)
def test_gate_pins_distinct_judge_raw_and_sanitized_hashes(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = _first_judge(evidence_root)
    data = json.loads(path.read_text())
    if mutation == "score":
        first = data["case_ids"][0]
        data["sanitized_evaluation_payload"]["case_evaluations"][first][
            "grounding_accuracy"
        ] = 0.123
        payload = data["sanitized_evaluation_payload"]
        data["artifact_output_hash"] = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    elif mutation == "swap":
        data["raw_output_hash"], data["artifact_output_hash"] = (
            data["artifact_output_hash"],
            data["raw_output_hash"],
        )
    elif mutation == "missing_payload":
        data.pop("sanitized_evaluation_payload")
    elif mutation == "prose":
        data["sanitized_evaluation_payload"]["prose"] = "not allowed"
    else:
        data["sanitizer_schema_version"] = "phase74-sanitized-judge-payload-v2"
    if "sanitized_evaluation_payload" in data:
        data["sanitization_binding_hash"] = hashlib.sha256(
            json.dumps(
                {
                    "doc_type": data["doc_type"],
                    "raw_output_hash": data["raw_output_hash"],
                    "artifact_output_hash": data["artifact_output_hash"],
                    "input_manifest_hash": data["provenance"][
                        "input_manifest_hash"
                    ],
                    "sanitizer_schema_version": data[
                        "sanitizer_schema_version"
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


def test_gate_rejects_coordinated_92_process_trace_and_cleanup(
    evidence_root: Path,
) -> None:
    concurrency_path = evidence_root / "concurrency.json"
    cleanup_path = evidence_root / "cleanup.json"
    concurrency = json.loads(concurrency_path.read_text())
    cleanup = json.loads(cleanup_path.read_text())
    removed = concurrency["events"][0]["process_instance_hash"]
    concurrency["events"] = [
        event
        for event in concurrency["events"]
        if event["process_instance_hash"] != removed
    ]
    cleanup["process_instance_hashes"].remove(removed)
    cleanup["registry_record_count"] = 92
    cleanup["registry_reaped_count"] = 92
    _write_json(concurrency_path, concurrency)
    _rehash_object(concurrency_path, evidence_root)
    _write_json(cleanup_path, cleanup)
    _rehash_object(cleanup_path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["doc", "phase", "run", "timestamp"])
def test_gate_rejects_mismatched_process_lifecycle_identity(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "concurrency.json"
    data = json.loads(path.read_text())
    start = next(event for event in data["events"] if event["event"] == "start")
    end = next(
        event
        for event in data["events"]
        if event["event"] == "end"
        and event["process_instance_hash"] == start["process_instance_hash"]
    )
    if mutation == "doc":
        end["doc_type"] = "passport"
    elif mutation == "phase":
        end["phase"] = "final"
    elif mutation == "run":
        end["run_id"] = "sdk-20990101T000000Z-aaaaaaaaaaaa-final"
    else:
        end["timestamp"] = start["timestamp"]
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    "mutation",
    [
        "swap",
        "backward",
        "wrong_before",
        "wrong_after",
        "negative",
        "duplicate_sequence",
        "nonzero_final",
    ],
)
def test_gate_rejects_global_lifecycle_order_tampering(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "concurrency.json"
    data = json.loads(path.read_text())
    events = data["events"]
    if mutation == "swap":
        events[0], events[1] = events[1], events[0]
    elif mutation == "backward":
        events[1]["timestamp"] = "2000-01-01T00:00:00+00:00"
    elif mutation == "wrong_before":
        events[0]["active_before"] = 1
    elif mutation == "wrong_after":
        events[0]["active_after"] = 2
    elif mutation == "negative":
        events[0]["event"] = "end"
        events[0]["active_before"] = 0
        events[0]["active_after"] = -1
    elif mutation == "duplicate_sequence":
        events[1]["sequence"] = events[0]["sequence"]
    else:
        events.pop()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("mutation", ["all", "one", "replace", "duplicate"])
def test_gate_pins_exact_25_citation_commitments(
    evidence_root: Path,
    mutation: str,
) -> None:
    path = evidence_root / "corpus_commitment.json"
    data = json.loads(path.read_text())
    original = data["citations"][0]
    if mutation == "all":
        data["citations"] = []
        data["bundle_citation_ids"] = {
            doc_type: [] for doc_type in data["bundle_citation_ids"]
        }
    elif mutation == "one":
        data["citations"].pop(0)
    elif mutation == "duplicate":
        data["citations"].append(dict(original))
    else:
        replacement = "guidance/replacement.md#000"
        replacement_hash = hashlib.sha256(replacement.encode()).hexdigest()
        data["citations"][0] = {
            "citation_id": replacement,
            "citation_id_hash": replacement_hash,
            "chunk_text_hash": "a" * 64,
        }
        for citations in data["bundle_citation_ids"].values():
            if original["citation_id"] in citations:
                citations[citations.index(original["citation_id"])] = replacement
        worker_path = next(
            path
            for path in evidence_root.glob("documents/*/workers/*.json")
            if original["citation_id"] in json.loads(path.read_text())[
                "citation_ids"
            ]
        )
        worker = json.loads(worker_path.read_text())
        index = worker["citation_ids"].index(original["citation_id"])
        worker["citation_ids"][index] = replacement
        worker["citation_id_hashes"][index] = replacement_hash
        _write_json(worker_path, worker)
        _rehash_object(worker_path, evidence_root)
    data["citations"] = sorted(
        data["citations"],
        key=lambda item: item["citation_id"],
    )
    data["citation_set_hash"] = hashlib.sha256(
        json.dumps(
            [
                (
                    record["citation_id"],
                    record["citation_id_hash"],
                    record["chunk_text_hash"],
                )
                for record in data["citations"]
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize(
    ("selector", "nested", "field", "value"),
    [
        ("accepted_patches.json", ("records", 0), "allowlist_passed", "false"),
        ("accepted_patches.json", ("records", 0), "allowlist_passed", 1),
        ("accepted_patches.json", ("records", 0), "non_regression_accepted", 1),
        ("cleanup.json", (), "survivor_count", "0"),
        ("cleanup.json", (), "registry_record_count", "93"),
        ("worker", ("provenance",), "is_live", "true"),
        ("worker", ("provenance",), "is_live", 1),
        ("judge", (), "case_count", "10"),
        (
            "shared",
            ("baseline_train",),
            "grounding_accuracy",
            "0.5",
        ),
    ],
)
def test_gate_rejects_scalar_coercion(
    evidence_root: Path,
    selector: str,
    nested: tuple,
    field: str,
    value: object,
) -> None:
    path = {
        "worker": _first_worker(evidence_root),
        "judge": _first_judge(evidence_root),
        "shared": sorted(
            evidence_root.glob("documents/*/shared_evaluation.json")
        )[0],
    }.get(selector, evidence_root / selector)
    data = json.loads(path.read_text())
    target = data
    for part in nested:
        target = target[part]
    target[field] = value
    _write_json(path, data)
    _rehash_object(path, evidence_root)
    with pytest.raises(EvidenceValidationError):
        _validate(evidence_root)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_metric_schema_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError):
        ScoreMetrics.model_validate(
            {
                "grounding_accuracy": value,
                "citation_exactness": 1.0,
                "defect_recall": 1.0,
                "pii_containment": 1.0,
                "blind_input_compliance": 1.0,
                "overall_score": 1.0,
            }
        )
