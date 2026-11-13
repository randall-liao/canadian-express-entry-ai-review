"""Generate synthetic test PDF fixtures and ground-truth metadata.

Renders clean vector PDFs and 300 DPI scanned PDFs for all 22 Express Entry document
types plus Letters of Explanation (LoE) into crawler/eval/test_data/, alongside
ground-truth metadata JSON files for evaluation and benchmarking.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from crawler.synthetic.generator import default_fields_for_type, generate_synthetic_document
from crawler.synthetic.rasterizer import rasterize_pdf_to_scanned_pdf
from crawler.synthetic.schemas import ExpressEntryDocType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_PROFILE: Dict[str, Any] = {
    "applicant_name": "Jane Doe",
    "date_of_birth": "1992-05-14",
    "citizenship": "Canada",
    "country_of_residence": "Canada",
    "marital_status": "Single",
}


def generate_test_dataset(output_dir: Path) -> None:
    """Generate clean vector and 300 DPI scanned PDFs + ground truth JSON for all doc types.

    Args:
        output_dir: Directory where generated PDFs and ground truth JSON files will be written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_types = list(ExpressEntryDocType)

    logger.info("Generating synthetic test dataset for %d document types in %s", len(doc_types), output_dir)

    for doc_type_enum in doc_types:
        dt_str = doc_type_enum.value
        fields = default_fields_for_type(dt_str, DEFAULT_PROFILE)

        # 1. Vector PDF & Metadata
        vector_bytes = generate_synthetic_document(dt_str, profile_data=DEFAULT_PROFILE)
        vector_pdf_path = output_dir / f"{dt_str}_vector.pdf"
        vector_json_path = output_dir / f"{dt_str}_vector.json"

        vector_pdf_path.write_bytes(vector_bytes)
        vector_meta = {
            "doc_type": dt_str,
            "variant": "vector",
            "file_name": vector_pdf_path.name,
            "title": f"Synthetic {dt_str.replace('_', ' ').title()}",
            "fields": fields,
            "expected_verdict": "meets_requirements",
            "injected_defects": [],
            "must_abstain": False,
        }
        vector_json_path.write_text(json.dumps(vector_meta, indent=2), encoding="utf-8")

        # 2. Scanned 300 DPI PDF & Metadata
        scanned_bytes = rasterize_pdf_to_scanned_pdf(
            vector_bytes, dpi=300, rotation_deg=1.0, add_noise=True
        )
        scanned_pdf_path = output_dir / f"{dt_str}_scanned.pdf"
        scanned_json_path = output_dir / f"{dt_str}_scanned.json"

        scanned_pdf_path.write_bytes(scanned_bytes)
        scanned_meta = {
            "doc_type": dt_str,
            "variant": "scanned",
            "dpi": 300,
            "file_name": scanned_pdf_path.name,
            "title": f"Synthetic {dt_str.replace('_', ' ').title()} (Scanned 300 DPI)",
            "fields": fields,
            "expected_verdict": "meets_requirements",
            "injected_defects": [],
            "must_abstain": False,
        }
        scanned_json_path.write_text(json.dumps(scanned_meta, indent=2), encoding="utf-8")

        logger.info("Generated %s (vector & scanned)", dt_str)

    logger.info("Synthetic dataset generation complete: %d fixtures generated.", len(doc_types) * 2)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    target_dir = repo_root / "crawler" / "eval" / "test_data"
    generate_test_dataset(target_dir)


if __name__ == "__main__":
    main()
