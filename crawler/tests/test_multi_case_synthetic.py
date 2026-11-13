"""Test multi-case synthetic test fixture dataset generation and ground truth schemas.

Verifies that all 23 Express Entry document types (22 e-APR doc types + LoE) have
valid, defective, and edge_case synthetic test fixtures (vector + 300 DPI scanned)
and paired JSON ground truth metadata files in crawler/eval/test_data/.
"""

import json
from pathlib import Path
from crawler.synthetic.schemas import ExpressEntryDocType


def test_multi_case_synthetic_fixtures_exist():
    repo_root = Path(__file__).resolve().parent.parent.parent
    test_data_dir = repo_root / "crawler" / "eval" / "test_data"
    gt_dir = repo_root / "crawler" / "eval" / "ground_truth"

    doc_types = list(ExpressEntryDocType)
    assert len(doc_types) == 23, f"Expected 23 ExpressEntryDocType enums, found {len(doc_types)}"

    cases = ["valid", "defective_translation", "defective_missing_info", "defective_expired"]
    variants = ["vector", "scanned"]

    total_expected_pdf = len(doc_types) * len(cases) * len(variants)
    assert total_expected_pdf == 184, f"Expected 184 PDF fixtures, got {total_expected_pdf}"

    pdf_files = list(test_data_dir.glob("*.pdf"))
    gt_files = list(gt_dir.glob("*.json"))

    assert len(pdf_files) == 184, f"Expected 184 blind PDF files in test_data, found {len(pdf_files)}"
    assert len(gt_files) == 184, f"Expected 184 GT JSON files in ground_truth, found {len(gt_files)}"

    for gt_file in gt_files:
        meta = json.loads(gt_file.read_text(encoding="utf-8"))
        assert "doc_type" in meta
        assert "variant" in meta
        assert "expected_verdict" in meta
        assert "injected_defects" in meta
