"""Unit and integration tests for PDF skill documentation, synthetic PDF generation,
and dataset ground-truth fixtures (Phase 48 Plan 03).
"""

import json
import unittest
from pathlib import Path

import pypdfium2 as pdfium

from unittest.mock import MagicMock, patch

from crawler.synthetic.generator import render_vector_pdf_bytes
from crawler.synthetic.rasterizer import rasterize_pdf_to_scanned_pdf
from crawler.synthetic.schemas import ExpressEntryDocType, TestCaseSpec

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPDFSkillAndSyntheticData(unittest.TestCase):
    """Verifies skills/pdf/SKILL.md, generated test dataset, and .gitignore rules."""

    def test_pdf_skill_markdown_exists_and_valid(self) -> None:
        """Verify skills/pdf/SKILL.md exists, contains valid YAML frontmatter and tool instructions."""
        skill_path = _REPO_ROOT / "skills" / "pdf" / "SKILL.md"
        self.assertTrue(skill_path.is_file(), f"Expected skill file at {skill_path}")

        content = skill_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter '---'")

        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "SKILL.md must have valid frontmatter delimiters")

        frontmatter_text = parts[1]
        body_text = parts[2]

        self.assertIn("name: pdf", frontmatter_text)
        self.assertIn("description:", frontmatter_text)
        self.assertIn("300 DPI", frontmatter_text)

        # Verify python tool instructions exist in body
        required_tools = ["reportlab", "pypdfium2", "pdfplumber", "Pillow", "pytesseract"]
        for tool in required_tools:
            self.assertIn(tool, body_text, f"SKILL.md instructions missing required Python tool: {tool}")

    def test_generated_pdf_fixtures_and_metadata_exist(self) -> None:
        """Verify the Phase 73 per-document blind fixture layout."""
        pipelines_dir = _REPO_ROOT / "crawler" / "eval" / "pipelines"
        self.assertTrue(
            pipelines_dir.is_dir(),
            f"Expected pipeline directory at {pipelines_dir}",
        )

        doc_types = list(ExpressEntryDocType)
        self.assertEqual(len(doc_types), 23, "Expected 22 Express Entry document types plus Letter of Explanation (23 total)")

        pdf_files = list(
            pipelines_dir.glob("*/ground_truth/pdfs/*.pdf")
        )
        gt_files = list(
            pipelines_dir.glob("*/ground_truth/ground_truth.json")
        )

        self.assertEqual(
            len(pdf_files),
            236,
            f"Expected 236 Phase 73 PDF fixtures, found {len(pdf_files)}",
        )
        self.assertEqual(
            len(gt_files),
            23,
            f"Expected 23 per-document ground-truth manifests, found {len(gt_files)}",
        )

        for pdf_file in pdf_files:
            self.assertGreater(pdf_file.stat().st_size, 0, f"PDF fixture {pdf_file.name} is empty")
        for manifest in gt_files:
            cases = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn(len(cases), {10, 12})

    def test_test_data_directory_is_git_ignored(self) -> None:
        """Verify crawler/eval/test_data/ is listed in .gitignore."""
        gitignore_path = _REPO_ROOT / ".gitignore"
        self.assertTrue(gitignore_path.is_file(), f"Expected .gitignore at {gitignore_path}")

        gitignore_content = gitignore_path.read_text(encoding="utf-8")
        ignored_lines = [line.strip() for line in gitignore_content.splitlines()]

        self.assertIn(
            "crawler/eval/test_data/",
            ignored_lines,
            "crawler/eval/test_data/ must be explicitly ignored in .gitignore",
        )

    def test_vector_pdf_rendering_and_metadata_sanitization(self) -> None:
        """Verify vector PDF rendering produces valid PDF bytes with sanitized metadata per D-07."""
        spec = TestCaseSpec(
            case_kind="valid_control",
            doc_type=ExpressEntryDocType.PASSPORT,
            title="Passport Document",
            issuing_authority="Passport Canada",
            issue_date="2022-01-01",
            fields={"passport_number": "ZE123456", "full_name": "Jane Doe"},
        )
        vector_bytes = render_vector_pdf_bytes(spec)
        self.assertGreater(len(vector_bytes), 1000, "Vector PDF byte stream should exceed 1000 bytes")

        pdf = pdfium.PdfDocument(vector_bytes)
        self.assertEqual(len(pdf), 1, "Vector PDF should contain 1 page")

        metadata = pdf.get_metadata_dict()
        self.assertEqual(metadata.get("Title", ""), "", "PDF Title metadata must be empty")
        self.assertEqual(metadata.get("Author", ""), "", "PDF Author metadata must be empty")
        self.assertEqual(metadata.get("Subject", ""), "", "PDF Subject metadata must be empty")
        self.assertEqual(metadata.get("Keywords", ""), "", "PDF Keywords metadata must be empty")

    def test_scanned_pdf_rasterization_and_text_layer_removal(self) -> None:
        """Verify 300 DPI scanned rasterizer produces image-only PDF with zero text layer per D-05, D-07."""
        spec = TestCaseSpec(
            case_kind="valid_control",
            doc_type=ExpressEntryDocType.EMPLOYMENT_REFERENCE,
            title="Employment Reference Letter",
            issuing_authority="Acme Software Solutions Ltd.",
            issue_date="2023-05-10",
            fields={
                "employer_name": "Acme Software Solutions Ltd.",
                "job_title": "Software Engineer",
                "noc_code": "21231",
            },
            narrative_blocks=["Jane Doe was employed full-time performing NOC 21231 duties."],
        )
        vector_bytes = render_vector_pdf_bytes(spec)
        scanned_bytes = rasterize_pdf_to_scanned_pdf(
            vector_pdf_bytes=vector_bytes, dpi=300, rotation_angle=1.0, add_noise=True
        )
        self.assertGreater(len(scanned_bytes), 5000, "Scanned PDF byte stream should exceed 5000 bytes")

        vec_doc = pdfium.PdfDocument(vector_bytes)
        scan_doc = pdfium.PdfDocument(scanned_bytes)
        self.assertEqual(len(scan_doc), len(vec_doc), "Scanned PDF page count must match vector sibling")

        # Verify page 0 text layer in scanned PDF is completely empty
        textpage = scan_doc[0].get_textpage()
        extracted_text = textpage.get_text_range().strip()
        self.assertEqual(extracted_text, "", "Scanned sibling PDF must contain zero vector text layer per D-07")

        # Verify metadata dictionary in scanned PDF is sanitized
        scan_meta = scan_doc.get_metadata_dict()
        self.assertEqual(scan_meta.get("Title", ""), "", "Scanned PDF Title metadata must be empty")
        self.assertEqual(scan_meta.get("Author", ""), "", "Scanned PDF Author metadata must be empty")
        self.assertEqual(scan_meta.get("Subject", ""), "", "Scanned PDF Subject metadata must be empty")

    def test_narrative_blocks_rendering_and_annotation_prohibition(self) -> None:
        """Verify narrative blocks render dynamically and explanatory defect annotations are prohibited per D-08."""
        valid_spec = TestCaseSpec(
            case_kind="valid_control",
            doc_type=ExpressEntryDocType.LETTER_OF_EXPLANATION,
            title="Letter of Explanation",
            issuing_authority="Applicant",
            issue_date="2024-08-01",
            fields={"topic": "bank_balance_fluctuation"},
            narrative_blocks=["Detailed explanation regarding savings transfer."],
        )
        valid_bytes = render_vector_pdf_bytes(valid_spec)
        self.assertGreater(len(valid_bytes), 1000)

        # Attempt to pass an explanatory defect label and verify ValueError is raised per D-08
        invalid_spec = TestCaseSpec(
            case_kind="defective_case",
            doc_type=ExpressEntryDocType.PASSPORT,
            title="Passport Document",
            issuing_authority="Passport Canada",
            issue_date="2022-01-01",
            fields={"passport_number": "ZE123456", "status": "synthetic test defect"},
        )
        with self.assertRaises(ValueError):
            render_vector_pdf_bytes(invalid_spec)


class TestRasterizerDoSBounds(unittest.TestCase):
    """Unit tests for T-73-12 PDF rasterization DoS fail-closed bounds enforcement."""

    def setUp(self) -> None:
        spec = TestCaseSpec(
            case_kind="valid_control",
            doc_type=ExpressEntryDocType.PASSPORT,
            title="Passport Document",
            issuing_authority="Passport Canada",
            issue_date="2022-01-01",
            fields={"passport_number": "ZE123456"},
        )
        self.sample_vector_bytes = render_vector_pdf_bytes(spec)

    def test_normal_300_dpi_generation_passes(self) -> None:
        """Verify normal 300 DPI rasterization passes without error."""
        scanned_bytes = rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=300)
        self.assertGreater(len(scanned_bytes), 1000)

    def test_excessive_dpi_rejected(self) -> None:
        """Verify DPI outside accepted range [72, 600] raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=1200)
        self.assertIn("outside accepted range", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=30)
        self.assertIn("outside accepted range", str(ctx.exception))

    def test_oversized_pdf_bytes_rejected(self) -> None:
        """Verify input PDF bytes exceeding 20 MB raise ValueError."""
        oversized_bytes = b"%PDF-1.4 " + b"0" * (20 * 1024 * 1024 + 10)
        with self.assertRaises(ValueError) as ctx:
            rasterize_pdf_to_scanned_pdf(oversized_bytes, dpi=300)
        self.assertIn("exceeds maximum allowed", str(ctx.exception))

    def test_non_finite_or_negative_page_dimensions_rejected(self) -> None:
        """Verify non-finite or non-positive page dimensions raise ValueError."""
        mock_page = MagicMock()
        mock_page.get_size.return_value = (float("nan"), 792.0)
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page

        with patch("pypdfium2.PdfDocument", return_value=mock_doc):
            with self.assertRaises(ValueError) as ctx:
                rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=300)
            self.assertIn("invalid non-finite or non-positive dimensions", str(ctx.exception))

    def test_oversized_page_dimensions_rejected(self) -> None:
        """Verify page pixel dimensions exceeding 10,000x10,000 px raise ValueError."""
        mock_page = MagicMock()
        mock_page.get_size.return_value = (5000.0, 5000.0)  # at 300 DPI = 20833 px
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page

        with patch("pypdfium2.PdfDocument", return_value=mock_doc):
            with self.assertRaises(ValueError) as ctx:
                rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=300)
            self.assertIn("exceed maximum per-page pixel bounds", str(ctx.exception))

    def test_excessive_page_count_rejected(self) -> None:
        """Verify PDF page count exceeding 50 pages raises ValueError."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 100

        with patch("pypdfium2.PdfDocument", return_value=mock_doc):
            with self.assertRaises(ValueError) as ctx:
                rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=300)
            self.assertIn("exceeds maximum allowed", str(ctx.exception))

    def test_excessive_aggregate_pixels_rejected(self) -> None:
        """Verify aggregate pixels across pages exceeding 100 MP raise ValueError."""
        mock_page = MagicMock()
        mock_page.get_size.return_value = (2000.0, 2000.0)  # at 300 DPI = 8333x8333 px = ~69.4 MP per page
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 5  # 5 * 69.4 MP = ~347 MP > 100 MP limit
        mock_doc.__getitem__.return_value = mock_page

        with patch("pypdfium2.PdfDocument", return_value=mock_doc):
            with self.assertRaises(ValueError) as ctx:
                rasterize_pdf_to_scanned_pdf(self.sample_vector_bytes, dpi=300)
            self.assertIn("exceeds maximum aggregate pixel bound", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
