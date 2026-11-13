"""Doctor / preflight — dependency + scan-quality diagnostics (Phase 30 — Plan 04).

Surfaces, instead of failing silently (EXTRACT-05):

* which extraction dependencies are present/missing, with an install hint — the
  required ``doc-extract`` stack (pypdfium2, Pillow, pdfminer.six) and the
  OPTIONAL OCR stack (the ``pytesseract`` wrapper + a local ``tesseract`` binary);
* per-document scan-quality problems (scanned / rotated / password-protected /
  low-text) read from the ``document_pages.quality_json`` the engine already
  persisted — WITHOUT re-rendering.

A missing REQUIRED dependency makes the overall status ``missing_dependency``
(CLI exit 3, never ``internal_error``); an absent OPTIONAL OCR stack is a
reported warning, never a failure. All output is PII-light (names / counts /
booleans only).

Importing this module is cheap: it reuses ``crawler.extraction``'s lazy
dependency probes (heavy libs are imported only when actually present).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

from crawler import extraction, vault


@dataclass
class DepStatus:
    name: str
    required: bool
    present: bool
    hint: str

    def to_dict(self) -> dict:
        return {"name": self.name, "required": self.required,
                "present": self.present, "hint": self.hint}


@dataclass
class DoctorReport:
    required: list = field(default_factory=list)
    optional: list = field(default_factory=list)
    overall: str = "ok"
    quality_counts: "dict | None" = None

    def missing_required(self) -> list:
        return [d.name for d in self.required if not d.present]

    def to_result(self) -> dict:
        """PII-light machine result: names/booleans/counts only."""
        return {
            "overall": self.overall,
            "deps": [d.to_dict() for d in self.required],
            "optional": [d.to_dict() for d in self.optional],
            "quality_counts": self.quality_counts,
        }


_DOC_EXTRACT_HINT = "pip install 'corpus-crawler[doc-extract]'"
_OCR_HINT = "pip install 'corpus-crawler[ocr]'"
_TESSERACT_HINT = "install the tesseract-ocr OS package (e.g. apt-get install tesseract-ocr)"


def _probe(importer) -> bool:
    """True iff the lazy *importer* succeeds (dependency present)."""
    try:
        importer()
        return True
    except extraction.MissingExtractionDependency:
        return False


def _tesseract_binary_present() -> bool:
    """True iff the ``tesseract`` binary is on PATH and answers ``--version``."""
    if shutil.which("tesseract") is None:
        return False
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True,
                       check=False)
        return True
    except (FileNotFoundError, OSError):
        return False


def probe_dependencies() -> tuple[list, list]:
    """Return (required, optional) :class:`DepStatus` lists.

    Required: pypdfium2, Pillow, pdfminer.six (the ``doc-extract`` extra).
    Optional: the ``pytesseract`` wrapper and the ``tesseract`` OS binary.
    """
    required = [
        DepStatus("pypdfium2", True, _probe(extraction._import_pdfium),
                  _DOC_EXTRACT_HINT),
        DepStatus("Pillow", True, _probe(extraction._import_pil),
                  _DOC_EXTRACT_HINT),
        DepStatus("pdfminer.six", True, _probe(extraction._import_pdfminer),
                  _DOC_EXTRACT_HINT),
    ]
    optional = [
        DepStatus("pytesseract", False, _probe(extraction._import_pytesseract),
                  _OCR_HINT),
        DepStatus("tesseract", False, _tesseract_binary_present(),
                  _TESSERACT_HINT),
    ]
    return required, optional


def scan_quality_report(v: vault.Vault, document_id: str) -> dict:
    """Aggregate per-page scan-quality flags for a document (PII-light).

    Reads the persisted ``document_pages.quality_json`` (does NOT re-render) and
    returns page + per-flag counts.
    """
    rows = v.con.execute(
        "SELECT quality_json FROM document_pages WHERE document_id = ?",
        (document_id,)).fetchall()
    counts = {"pages": 0, "scanned": 0, "low_text": 0, "rotated": 0,
              "password_protected": 0}
    for r in rows:
        counts["pages"] += 1
        quality = json.loads(r["quality_json"]) if r["quality_json"] else {}
        for key in ("scanned", "low_text", "rotated", "password_protected"):
            if quality.get(key):
                counts[key] += 1
    return counts


def run_doctor(candidate: "str | None" = None,
               document_id: "str | None" = None) -> DoctorReport:
    """Combine dependency preflight + (optional) per-document scan-quality.

    ``overall`` is ``missing_dependency`` iff any REQUIRED dep is absent, else
    ``ok``. Scan-quality problems are REPORTED but never by themselves fail the
    exit — surfacing them is the whole point of ``doctor``.
    """
    required, optional = probe_dependencies()
    overall = ("missing_dependency"
               if any(not d.present for d in required) else "ok")
    quality_counts = None
    if candidate is not None and document_id is not None:
        v = vault.open_vault(candidate)
        try:
            quality_counts = scan_quality_report(v, document_id)
        finally:
            v.con.close()
    return DoctorReport(required=required, optional=optional, overall=overall,
                        quality_counts=quality_counts)
