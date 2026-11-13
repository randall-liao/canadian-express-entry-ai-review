# Phase 52 Plan: Multi-Case Synthetic Test Fixture Generation Engine

## Goal
Expand the synthetic PDF test generator (`crawler/synthetic/`) to generate multi-case test fixtures (clean/valid, defective/missing fields/expired/un-translated, edge-case/formatted/scanned) for all 23 Express Entry document types (22 e-APR doc types + LoE), storing paired vector PDFs, 300 DPI scanned PDFs, and ground truth JSON files in git-ignored `crawler/eval/test_data/`.

## Requirements
- `GEN-01`: Multi-case synthetic document generator creates valid, defective, and edge-case PDF test fixtures for all 23 Express Entry document types.
- `GEN-02`: All synthetic test cases produce paired vector PDFs and 300 DPI scanned PDFs with ground truth JSON schemas stored in git-ignored `crawler/eval/test_data/`.

## Tasks
1. Extend `crawler/synthetic/defects.py` and `generator.py` to support multi-case variant generation per document type (`valid`, `defective`, `edge_case`).
2. Update `crawler/synthetic/generate_test_dataset.py` to generate 3 cases x 2 formats (vector + 300 DPI scanned) = 6 PDF fixtures + 6 JSON ground truth files per document type (138 total fixtures).
3. Execute `generate_test_dataset.py` and verify all 138 PDF fixtures and 138 JSON ground truth files are produced in `crawler/eval/test_data/`.
4. Create and run `crawler/tests/test_multi_case_synthetic.py` to confirm 100% fixture validity and schema compliance.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_multi_case_synthetic.py -q`
