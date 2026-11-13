"""Worker Staging API for Blind Synthetic Fixtures.

Provides cryptographically random 32-hex opaque ID generation and isolated
temporary directory staging for worker agent evaluation per D-07, D-09, D-10.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from crawler.synthetic.leakage_scanner import (
    scan_blind_artifact_leakage,
    scan_blind_text_leakage,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"


def generate_opaque_32hex_id() -> str:
    """Generate a cryptographically random 32-character hexadecimal opaque ID.

    Uses secrets.token_hex(16) to generate 16 random bytes (32 hex chars).
    Rejects shorter ID formats.
    """
    opaque_id = secrets.token_hex(16)
    if len(opaque_id) != 32 or not re.match(r"^[a-f0-9]{32}$", opaque_id):
        raise ValueError(f"Generated opaque ID '{opaque_id}' is not a valid 32-hex string")
    return opaque_id


def _assert_staged_destination_clean(dest_dir: Path, opaque_case_id: str, has_text: bool) -> None:
    """Assert that staged directory contains ONLY allowed opaque files and no extra artifacts."""
    expected_files = {f"{opaque_case_id}.pdf"}
    if has_text:
        expected_files.add(f"{opaque_case_id}.txt")

    entries = list(dest_dir.iterdir())
    actual_names = set()
    for entry in entries:
        if entry.is_symlink():
            raise ValueError(f"Staged destination contains a symlink: '{entry.name}'")
        if entry.is_dir():
            raise ValueError(f"Staged destination contains a subdirectory: '{entry.name}'")
        if not entry.is_file():
            raise ValueError(f"Staged destination contains a non-regular file: '{entry.name}'")
        actual_names.add(entry.name)

    if actual_names != expected_files:
        raise ValueError(
            f"Staged destination contains unexpected files: {actual_names} (expected {expected_files})"
        )


def stage_case_for_worker(
    opaque_case_id: str,
    pipeline_root: Optional[Path] = None,
    target_dir: Optional[Path] = None,
) -> Path:
    """Stage a single blind synthetic PDF fixture for worker evaluation.

    Locates the PDF associated with opaque_case_id in the privileged pipeline tree,
    copies ONLY the single PDF (and allowed extracted text if present) to an isolated
    target directory outside the pipeline tree, runs an automated leakage scan,
    and returns the staged PDF path.

    Args:
        opaque_case_id: Cryptographically opaque 32-hex case ID.
        pipeline_root: Optional root directory of pipelines.
        target_dir: Optional destination directory; defaults to a fresh temporary directory.

    Returns:
        Path to the staged PDF file outside the privileged pipeline tree.

    Raises:
        ValueError: If opaque_case_id is malformed, path/containment/symlink checks fail,
            duplicate source matches exist, or staged PDF/text fails leakage checks.
        FileNotFoundError: If the pipeline root or source PDF cannot be found.
    """
    if not re.match(r"^[a-f0-9]{32}$", opaque_case_id):
        raise ValueError(f"opaque_case_id '{opaque_case_id}' is not a 32-character hex string")

    root = (pipeline_root or _PIPELINES_DIR).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Pipeline root '{root}' is not a directory")

    dest_dir: Optional[Path] = None

    try:
        if target_dir is not None:
            raw_target = Path(target_dir)
            if raw_target.is_symlink():
                raise ValueError(f"target_dir '{raw_target}' is a symlink")

            resolved_target = raw_target.resolve()
            if resolved_target.is_symlink():
                raise ValueError(f"target_dir '{raw_target}' resolves to a symlink")

            # Must be outside privileged pipeline root
            if (
                resolved_target == root
                or resolved_target.is_relative_to(root)
                or root.is_relative_to(resolved_target)
            ):
                raise ValueError(
                    f"target_dir '{resolved_target}' must be outside privileged pipeline root '{root}'"
                )

            if raw_target.exists():
                if not raw_target.is_dir():
                    raise ValueError(f"target_dir '{raw_target}' exists and is not a directory")
                if any(raw_target.iterdir()):
                    raise ValueError(f"target_dir '{raw_target}' is pre-populated / not empty")
                dest_dir = resolved_target
            else:
                raw_target.mkdir(parents=True, exist_ok=False)
                dest_dir = raw_target.resolve()
        else:
            dest_dir = Path(tempfile.mkdtemp()).resolve()
            if dest_dir == root or dest_dir.is_relative_to(root):
                raise ValueError("Generated temporary staging directory is inside pipeline root")

        pdf_filename = f"{opaque_case_id}.pdf"
        txt_filename = f"{opaque_case_id}.txt"

        # Search pipeline tree for source PDF
        matches: List[Path] = list(root.rglob(pdf_filename))
        if not matches:
            raise FileNotFoundError(
                f"Source PDF for opaque case ID '{opaque_case_id}' not found under '{root}'"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Multiple duplicate source matches found for opaque case ID '{opaque_case_id}' under '{root}': {matches}"
            )

        source_pdf = matches[0]
        if source_pdf.is_symlink():
            raise ValueError(f"Source PDF '{source_pdf}' is a symlink")

        resolved_source_pdf = source_pdf.resolve()
        if not resolved_source_pdf.is_relative_to(root):
            raise ValueError(
                f"Source PDF '{source_pdf}' resolved to '{resolved_source_pdf}', outside pipeline root '{root}'"
            )
        if not resolved_source_pdf.is_file():
            raise FileNotFoundError(f"Source PDF '{resolved_source_pdf}' is not a regular file")

        # Check allowed extracted text if present
        source_txt = source_pdf.with_suffix(".txt")
        has_text = False
        resolved_source_txt: Optional[Path] = None

        if source_txt.exists():
            if source_txt.is_symlink():
                raise ValueError(f"Source text '{source_txt}' is a symlink")
            resolved_source_txt = source_txt.resolve()
            if not resolved_source_txt.is_relative_to(root):
                raise ValueError(
                    f"Source text '{source_txt}' resolved to '{resolved_source_txt}', outside pipeline root '{root}'"
                )
            if not resolved_source_txt.is_file():
                raise FileNotFoundError(f"Source text '{resolved_source_txt}' is not a regular file")

            # Pre-copy leakage scan of source text
            txt_pre_violations = scan_blind_text_leakage(resolved_source_txt, filename=txt_filename)
            if txt_pre_violations:
                raise ValueError(f"Source text failed blind leakage scan: {txt_pre_violations}")

            has_text = True

        # Copy raw bytes without preserving filesystem metadata; normalize permissions & timestamps
        staged_pdf = dest_dir / pdf_filename
        staged_pdf.write_bytes(resolved_source_pdf.read_bytes())
        staged_pdf.chmod(0o644)
        os.utime(staged_pdf, (0, 0))

        if has_text and resolved_source_txt:
            staged_txt = dest_dir / txt_filename
            staged_txt.write_bytes(resolved_source_txt.read_bytes())
            staged_txt.chmod(0o644)
            os.utime(staged_txt, (0, 0))

        # Perform automated leakage scan on staged artifacts
        pdf_violations = scan_blind_artifact_leakage(staged_pdf)
        if pdf_violations:
            raise ValueError(f"Staged PDF failed blind leakage scan: {pdf_violations}")

        if has_text:
            staged_txt = dest_dir / txt_filename
            txt_violations = scan_blind_text_leakage(staged_txt)
            if txt_violations:
                raise ValueError(f"Staged text file failed blind leakage scan: {txt_violations}")

        # Post-staging destination containment & clean file assertion
        _assert_staged_destination_clean(dest_dir, opaque_case_id, has_text)

        return staged_pdf

    except Exception:
        if dest_dir is not None and dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise
