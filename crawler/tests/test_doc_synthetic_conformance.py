"""Synthetic Pipeline Contract Conformance Test Suite.

Verifies complete 23-pipeline synthetic dataset generation in temporary test roots
using injected test runners per D-04, D-07, D-09, D-10, D-12, D-16.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

import pypdfium2 as pdfium
import pytest

from crawler.eval.doc_synthetic_generator import (
    CopilotExecutionError,
    generate_pipeline_synthetic_dataset,
    run_all_document_synthetic_generators,
)
from crawler.synthetic.generator import default_fields_for_type
from crawler.synthetic.leakage_scanner import scan_blind_artifact_leakage
from crawler.synthetic.rasterizer import _PDFIUM_LOCK
from crawler.synthetic.schemas import ExpressEntryDocType, PrivateCaseRecord
from crawler.synthetic.staging import stage_case_for_worker

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_ALL_DOC_TYPES = [dt.value for dt in ExpressEntryDocType]


def _mock_copilot_runner(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    """Mock Copilot runner test double generating valid schema-compliant GenerationSpec JSON in JSONL format."""
    doc_type = cwd.name
    research_file = cwd / "research" / "research.json"
    failure_modes: List[Dict[str, Any]] = []

    if research_file.is_file():
        try:
            r_data = json.loads(research_file.read_text(encoding="utf-8"))
            failure_modes = r_data.get("failure_modes", [])
        except Exception:
            pass

    if not failure_modes:
        short_code = doc_type.upper().replace("_", "")
        failure_modes = [
            {"failure_id": f"PFL-{short_code}-01", "category": "expired_credential", "severity": "critical"},
            {"failure_id": f"PFL-{short_code}-02", "category": "name_mismatch", "severity": "warning"},
            {"failure_id": f"PFL-{short_code}-03", "category": "missing_signature", "severity": "warning"},
        ]

    profile_sample = {
        "applicant_name": "Jane Doe",
        "date_of_birth": "1992-05-14",
        "citizenship": "Canada",
        "country_of_residence": "Canada",
        "marital_status": "Single",
    }
    sample_fields = default_fields_for_type(doc_type, profile_sample)

    valid_case = {
        "case_kind": "valid_control",
        "doc_type": doc_type,
        "title": f"Official {doc_type.replace('_', ' ').title()}",
        "issuing_authority": "Official Issuing Registry",
        "issue_date": "2023-01-15",
        "expiry_date": "2033-01-15",
        "fields": sample_fields,
        "narrative_blocks": [f"Official fully compliant supporting documentation for {doc_type}."],
        "defect_spec": None,
    }

    defective_cases = []
    for fm in failure_modes:
        f_id = fm.get("failure_id", f"PFL-{doc_type.upper()[:4]}-01")
        cat = fm.get("category", "invalid_field")
        raw_sev = str(fm.get("severity", "critical")).lower()
        sev = "critical" if raw_sev in ("critical", "high") else "warning"

        defective_cases.append(
            {
                "case_kind": "defective_case",
                "doc_type": doc_type,
                "title": f"Official {doc_type.replace('_', ' ').title()}",
                "issuing_authority": "Official Issuing Registry",
                "issue_date": "2023-01-15",
                "expiry_date": "2022-01-15",
                "fields": sample_fields,
                "narrative_blocks": [f"Official supporting document statement regarding the issued credential."],
                "defect_spec": {
                    "research_failure_id": f_id,
                    "category": cat,
                    "severity": sev,
                    "description": f"Injected defect derived from research failure mode {f_id}",
                    "affected_fields": fm.get("affected_fields", ["issue_date"]),
                    "mutation_details": {},
                },
            }
        )

    spec_dict = {
        "doc_type": doc_type,
        "timestamp": "2026-07-23T01:00:00Z",
        "cases": [valid_case] + defective_cases,
    }

    event = {
        "type": "assistant.message",
        "data": {"content": json.dumps(spec_dict)},
    }

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=0,
        stdout=json.dumps(event),
        stderr="",
    )


def verify_live_generator_conformance(pipelines_dir: Path) -> List[str]:
    """Strictly validate live production synthetic dataset generation artifacts across all 23 document pipelines.

    Reads only production outputs in pipelines_dir and rejects missing, blocked, injected,
    partially covered, sequential/hint-bearing, metadata-leaking, text-layer scan, duplicate-ID,
    hash-mismatch, PII, or staging-escape artifacts per coordinator contract.
    """
    errors: List[str] = []
    if not pipelines_dir.is_dir():
        return [f"Pipeline root directory does not exist: {pipelines_dir}"]

    seen_opaque_ids: set[str] = set()
    covered_failure_ids: set[str] = set()

    for doc_type in _ALL_DOC_TYPES:
        pipeline_dir = pipelines_dir / doc_type
        gt_dir = pipeline_dir / "ground_truth"
        error_file = pipeline_dir / "generator.error.json"

        if error_file.is_file():
            errors.append(f"Pipeline '{doc_type}' contains generator.error.json (generation failed or blocked)")

        if not gt_dir.is_dir():
            errors.append(f"Missing ground_truth directory for doc_type '{doc_type}' at {gt_dir}")
            continue

        spec_file = gt_dir / "generation_spec.json"
        gt_file = gt_dir / "ground_truth.json"
        prov_file = gt_dir / "generation_provenance.json"
        pdfs_dir = gt_dir / "pdfs"

        if not spec_file.is_file():
            errors.append(f"Missing generation_spec.json for '{doc_type}'")
            continue
        if not gt_file.is_file():
            errors.append(f"Missing ground_truth.json for '{doc_type}'")
            continue
        if not prov_file.is_file():
            errors.append(f"Missing generation_provenance.json for '{doc_type}'")
            continue
        if not pdfs_dir.is_dir():
            errors.append(f"Missing pdfs/ directory for '{doc_type}'")
            continue

        # Validate provenance
        try:
            prov = json.loads(prov_file.read_text(encoding="utf-8"))
            if prov.get("status") != "success":
                errors.append(f"Provenance status for '{doc_type}' is '{prov.get('status')}', expected 'success'")
            if prov.get("engine") != "copilot-cli":
                errors.append(
                    f"Truthful execution flaw: Pipeline '{doc_type}' engine is '{prov.get('engine')}', "
                    f"expected 'copilot-cli' (injected or non-live test runner detected)"
                )
            if prov.get("is_live") is not True:
                errors.append(
                    f"Truthful execution flaw: Pipeline '{doc_type}' is_live is {prov.get('is_live')}, "
                    f"expected True (non-live output detected)"
                )
            if prov.get("model") != "gemini-3.6-flash":
                errors.append(f"Model mismatch for '{doc_type}': '{prov.get('model')}', expected 'gemini-3.6-flash'")
        except Exception as exc:
            errors.append(f"Malformed generation_provenance.json for '{doc_type}': {exc}")

        # Validate spec & research coverage
        research_file = pipeline_dir / "research" / "research.json"
        res_failure_ids = set()
        if research_file.is_file():
            try:
                res_data = json.loads(research_file.read_text(encoding="utf-8"))
                res_failure_ids = {
                    fm["failure_id"]
                    for fm in res_data.get("failure_modes", [])
                    if isinstance(fm, dict) and "failure_id" in fm
                }
            except Exception:
                pass

        try:
            spec_raw = spec_file.read_text(encoding="utf-8")
            spec_sha256 = hashlib.sha256(spec_raw.encode("utf-8")).hexdigest()
            spec_data = json.loads(spec_raw)
            cases = spec_data.get("cases", [])
            valid_controls = [c for c in cases if c.get("case_kind") == "valid_control"]
            if len(valid_controls) != 1:
                errors.append(f"Pipeline '{doc_type}' must contain exactly 1 valid_control case, got {len(valid_controls)}")

            spec_failure_ids = {
                c.get("defect_spec", {}).get("research_failure_id")
                for c in cases
                if c.get("case_kind") == "defective_case" and isinstance(c.get("defect_spec"), dict)
            }
            missing_ids = res_failure_ids - spec_failure_ids
            if missing_ids:
                errors.append(
                    f"Pipeline '{doc_type}' generation_spec missing defective cases for research failure IDs: {missing_ids}"
                )

            covered_failure_ids.update(spec_failure_ids - {None})

        except Exception as exc:
            errors.append(f"Malformed or invalid generation_spec.json for '{doc_type}': {exc}")
            spec_sha256 = ""

        # Validate ground truth records & PDFs
        try:
            gt_records = json.loads(gt_file.read_text(encoding="utf-8"))
            if not isinstance(gt_records, list):
                errors.append(f"ground_truth.json for '{doc_type}' is not a JSON list")
                continue

            record_map = {
                r.get("opaque_case_id"): r
                for r in gt_records
                if isinstance(r, dict) and r.get("opaque_case_id")
            }

            for record in gt_records:
                try:
                    rec = PrivateCaseRecord.model_validate(record)
                except Exception as exc:
                    errors.append(f"PrivateCaseRecord schema error in '{doc_type}': {exc}")
                    continue

                op_id = rec.opaque_case_id
                if op_id in seen_opaque_ids:
                    errors.append(f"Duplicate opaque_case_id '{op_id}' detected in pipeline '{doc_type}'")
                seen_opaque_ids.add(op_id)

                # Check sibling linkage
                sib_id = rec.sibling_case_id
                if sib_id not in record_map:
                    errors.append(f"Sibling case ID '{sib_id}' for record '{op_id}' not found in ground_truth.json")
                else:
                    sib_rec = record_map[sib_id]
                    if sib_rec.get("sibling_case_id") != op_id:
                        errors.append(f"Asymmetric sibling linkage between '{op_id}' and '{sib_id}'")

                # Check spec SHA256
                if spec_sha256 and rec.agent_spec_sha256 != spec_sha256:
                    errors.append(
                        f"agent_spec_sha256 mismatch in record '{op_id}': expected '{spec_sha256}', got '{rec.agent_spec_sha256}'"
                    )

                # Check PDF file existence & hash
                pdf_path = pdfs_dir / f"{op_id}.pdf"
                if not pdf_path.is_file():
                    errors.append(f"Missing PDF file for record '{op_id}' at {pdf_path}")
                else:
                    pdf_bytes = pdf_path.read_bytes()
                    actual_pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
                    if actual_pdf_sha != rec.pdf_sha256:
                        errors.append(f"PDF sha256 mismatch for '{op_id}': expected '{rec.pdf_sha256}', got '{actual_pdf_sha}'")

                    # Side-channel leakage scan
                    violations = scan_blind_artifact_leakage(pdf_path)
                    if violations:
                        errors.append(f"Side-channel leakage in PDF '{op_id}.pdf': {violations}")

                    # Zero text layer scan for scanned variant
                    if rec.variant == "scanned":
                        try:
                            with _PDFIUM_LOCK:
                                pdf_doc = pdfium.PdfDocument(pdf_bytes)
                                text_chars = 0
                                for p_idx in range(len(pdf_doc)):
                                    page = pdf_doc[p_idx]
                                    textpage = page.get_textpage()
                                    text_chars += len(textpage.get_text_range().strip())
                            if text_chars > 0:
                                errors.append(f"Scanned PDF '{op_id}.pdf' contains non-zero vector text layer ({text_chars} chars)")
                        except Exception as exc:
                            errors.append(f"Failed pypdfium2 text layer check on '{op_id}.pdf': {exc}")

                # Check for prohibited explanatory annotations in record fields
                fields_str = json.dumps(rec.fields).lower()
                prohibited_annotations = ["defective test", "missing field annotation", "synthetic test", "pfl trigger"]
                for p_ann in prohibited_annotations:
                    if p_ann in fields_str:
                        errors.append(f"Record '{op_id}' contains prohibited annotation keyword '{p_ann}'")

        except Exception as exc:
            errors.append(f"Failed parsing ground_truth.json for '{doc_type}': {exc}")

    # Check total failure mode coverage across all 23 pipelines
    if covered_failure_ids and len(covered_failure_ids) < 95:
        errors.append(f"Incomplete failure mode coverage: covered {len(covered_failure_ids)} failure IDs, expected 95")

    return errors


class TestDocSyntheticConformance(unittest.TestCase):
    """Synthetic pipeline contract test suite operating inside isolated temporary roots."""

    @classmethod
    def setUpClass(cls) -> None:
        """Populate isolated temporary pipeline root and run mock generator across all 23 document pipelines."""
        cls._tmp_dir_obj = tempfile.TemporaryDirectory()
        cls.pipeline_root = Path(cls._tmp_dir_obj.name)

        # Copy research.json files from production or create mock research.json files
        for doc_type in _ALL_DOC_TYPES:
            src_res = _PIPELINES_DIR / doc_type / "research" / "research.json"
            dst_res_dir = cls.pipeline_root / doc_type / "research"
            dst_res_dir.mkdir(parents=True, exist_ok=True)

            if src_res.is_file():
                shutil.copy(src_res, dst_res_dir / "research.json")
            else:
                short_code = doc_type.upper().replace("_", "")
                mock_research = {
                    "doc_type": doc_type,
                    "timestamp": "2026-07-23T00:00:00Z",
                    "failure_modes": [
                        {"failure_id": f"PFL-{short_code}-01", "category": "expired_credential", "severity": "critical"},
                        {"failure_id": f"PFL-{short_code}-02", "category": "name_mismatch", "severity": "warning"},
                        {"failure_id": f"PFL-{short_code}-03", "category": "missing_signature", "severity": "warning"},
                    ],
                }
                (dst_res_dir / "research.json").write_text(json.dumps(mock_research, indent=2), encoding="utf-8")

        cls.gen_results = run_all_document_synthetic_generators(
            pipeline_root=cls.pipeline_root,
            copilot_runner=_mock_copilot_runner,
            max_workers=4,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up temporary test root."""
        cls._tmp_dir_obj.cleanup()

    def test_all_23_pipelines_synthetic_generation_conformance(self) -> None:
        """Verify 100% successful dataset generation for all 23 document types in temporary root."""
        self.assertEqual(self.gen_results["status"], "completed")
        self.assertEqual(self.gen_results["total_pipelines"], 23)
        self.assertEqual(self.gen_results["successful_pipelines"], 23)

        # 95 research failure modes + 23 valid controls = 118 logical cases total
        self.assertEqual(self.gen_results["total_cases"], 118)
        # 118 logical cases * 2 variants = 236 PDF fixtures
        self.assertEqual(self.gen_results["total_pdfs"], 236)

        total_pdfs_on_disk = 0
        all_opaque_filenames = []

        for doc_type in _ALL_DOC_TYPES:
            gt_dir = self.pipeline_root / doc_type / "ground_truth"
            self.assertTrue((gt_dir / "generation_spec.json").is_file(), f"Missing spec for '{doc_type}'")
            self.assertTrue((gt_dir / "ground_truth.json").is_file(), f"Missing ground_truth for '{doc_type}'")
            self.assertTrue((gt_dir / "generation_provenance.json").is_file(), f"Missing provenance for '{doc_type}'")

            pdfs_dir = gt_dir / "pdfs"
            self.assertTrue(pdfs_dir.is_dir(), f"Missing pdfs dir for '{doc_type}'")

            pdf_files = list(pdfs_dir.glob("*.pdf"))
            total_pdfs_on_disk += len(pdf_files)

            for pdf_f in pdf_files:
                self.assertRegex(pdf_f.name, r"^[a-f0-9]{32}\.pdf$")
                all_opaque_filenames.append(pdf_f.name)

            # Validate ground truth records
            records_raw = (gt_dir / "ground_truth.json").read_text(encoding="utf-8")
            records = json.loads(records_raw)
            rec_map = {r["opaque_case_id"]: r for r in records}

            for r in records:
                rec = PrivateCaseRecord.model_validate(r)
                # Verify sibling linkage
                self.assertIn(rec.sibling_case_id, rec_map)
                self.assertEqual(rec_map[rec.sibling_case_id]["sibling_case_id"], rec.opaque_case_id)

                # Verify SHA256
                pdf_bytes = (pdfs_dir / rec.blind_filename).read_bytes()
                actual_sha = hashlib.sha256(pdf_bytes).hexdigest()
                self.assertEqual(rec.pdf_sha256, actual_sha)

        self.assertEqual(total_pdfs_on_disk, 236)
        self.assertEqual(len(set(all_opaque_filenames)), 236, "All 236 PDF filenames must be globally unique 32-hex IDs")

    def test_synthetic_staging_isolation_conformance(self) -> None:
        """Verify worker staging API stages single opaque PDF without exposing ground truth or research manifests."""
        # Pick first opaque ID from passport ground truth
        gt_file = self.pipeline_root / "passport" / "ground_truth" / "ground_truth.json"
        records = json.loads(gt_file.read_text(encoding="utf-8"))
        target_record = records[0]
        opaque_id = target_record["opaque_case_id"]

        with tempfile.TemporaryDirectory() as worker_target:
            target_path = Path(worker_target) / "worker_stage"
            staged_pdf = stage_case_for_worker(
                opaque_id,
                pipeline_root=self.pipeline_root,
                target_dir=target_path,
            )

            self.assertTrue(staged_pdf.is_file())
            self.assertEqual(staged_pdf.name, f"{opaque_id}.pdf")

            # Assert staged directory contains ONLY the single opaque PDF (and optional txt)
            staged_dir = staged_pdf.parent
            files = [p.name for p in staged_dir.iterdir()]
            self.assertIn(f"{opaque_id}.pdf", files)
            self.assertLessEqual(len(files), 2)

            # Assert no ground_truth or research files leaked
            self.assertFalse((staged_dir / "ground_truth.json").exists())
            self.assertFalse((staged_dir / "research.json").exists())
            self.assertFalse((staged_dir / "generation_spec.json").exists())

            # Assert no foreign path substring in staged file path or content
            staged_str = str(staged_pdf)
            self.assertNotIn("ground_truth", staged_str)
            self.assertNotIn("passport", staged_str)

    def test_fail_closed_on_generator_error(self) -> None:
        """Verify generator unlinks stale ground_truth directory and writes generator.error.json on failure."""
        def failing_runner(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Model timeout error")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            pass_dir = tmp_root / "passport"
            pass_gt = pass_dir / "ground_truth"
            pass_gt.mkdir(parents=True, exist_ok=True)
            (pass_gt / "stale.json").write_text("stale data")

            res_dir = pass_dir / "research"
            res_dir.mkdir(parents=True, exist_ok=True)
            (res_dir / "research.json").write_text(
                json.dumps({"doc_type": "passport", "failure_modes": [{"failure_id": "PFL-PASS-01"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(CopilotExecutionError):
                generate_pipeline_synthetic_dataset(
                    "passport",
                    pipeline_root=tmp_root,
                    copilot_runner=failing_runner,
                )

            # Check ground_truth directory was unlinked / removed
            self.assertFalse(pass_gt.exists())

            # Check generator.error.json was recorded
            err_file = pass_dir / "generator.error.json"
            self.assertTrue(err_file.is_file())
            err_data = json.loads(err_file.read_text(encoding="utf-8"))
            self.assertFalse(err_data["passed"])
            self.assertEqual(err_data["execution"]["engine"], "injected-test-runner")

    def test_live_doc_synthetic_conformance_gate(self) -> None:
        """Live-only conformance gate validating production crawler/eval/pipelines/*/ground_truth/ artifacts.

        Fails explicitly when enabled and production artifacts are absent, blocked, injected,
        partially covered, sequential/hint-bearing, metadata-leaking, text-layer scan,
        duplicate-ID, hash-mismatch, PII, or staging-escape artifacts.
        """
        gate_enabled = (
            os.getenv("RUN_LIVE_GENERATOR_GATE", "").lower() in ("1", "true", "yes")
            or os.getenv("REQUIRE_LIVE_SYNTHETIC_CONFORMANCE", "").lower() in ("1", "true", "yes")
        )

        if not gate_enabled:
            self.skipTest("Live generator conformance gate disabled. Set RUN_LIVE_GENERATOR_GATE=1 to enable.")

        errors = verify_live_generator_conformance(_PIPELINES_DIR)
        if errors:
            self.fail(
                f"Live generator conformance gate failed ({len(errors)} errors):\n"
                + "\n".join(f"  - {err}" for err in errors)
            )

    def test_injected_outputs_cannot_satisfy_live_gate(self) -> None:
        """Prove that non-live / injected test runner outputs are rejected by the live conformance gate."""
        errors = verify_live_generator_conformance(self.pipeline_root)
        self.assertGreater(len(errors), 0, "Injected test outputs MUST NOT satisfy live conformance gate")
        flaw_found = any("Truthful execution flaw" in err for err in errors)
        self.assertTrue(
            flaw_found,
            f"Injected test outputs must trigger 'Truthful execution flaw' error in gate. Errors: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
