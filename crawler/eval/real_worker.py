"""Live Gemini Worker document-review execution engine."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from pdfminer.high_level import extract_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_OUTPUTS_DIR = _REPO_ROOT / "reports" / "worker_outputs"
_COPILOT_PATH = shutil.which("copilot") or "copilot"
_WORKER_MODEL = "gemini-3.6-flash"
_LLM_TIMEOUT_SECONDS = 600
_ANSWER_FIELDS = {"question", "claims", "basis", "abstentions", "prose"}
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

logger = logging.getLogger(__name__)


class CopilotExecutionError(RuntimeError):
    """Raised when a live Copilot model call does not yield valid JSON."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    partial.replace(path)


def _extract_json_object(
    output: str,
    required_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Extract a JSON object from plain, fenced, JSONL stream, or decorated LLM output."""
    cleaned = _ANSI_ESCAPE.sub("", output).strip()
    required = set(required_keys or ())
    candidates = [cleaned]

    # Try extracting message content from assistant.message JSONL lines
    jsonl_messages = []
    for line in cleaned.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            evt = json.loads(line_str)
            if isinstance(evt, dict):
                evt_type = evt.get("type") or evt.get("event")
                if evt_type == "assistant.message" and "content" in evt:
                    jsonl_messages.append(str(evt["content"]))
                elif "message" in evt and isinstance(evt["message"], dict):
                    msg = evt["message"]
                    if msg.get("role") == "assistant" and "content" in msg:
                        jsonl_messages.append(str(msg["content"]))
        except json.JSONDecodeError:
            pass

    if jsonl_messages:
        combined = "\n".join(jsonl_messages)
        candidates.insert(0, combined)

    for match in _JSON_FENCE.findall(cleaned):
        candidates.append(match.strip())

    decoder = json.JSONDecoder()
    parsed_objects: list[Dict[str, Any]] = []

    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            parsed_objects.append(value)

        for start in (match.start() for match in re.finditer(r"\{", candidate)):
            try:
                value, _ = decoder.raw_decode(candidate[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                parsed_objects.append(value)

    for value in parsed_objects:
        if required.issubset(value):
            return value

    expected = f" containing keys {sorted(required)}" if required else ""
    raise ValueError(f"Copilot output did not contain a JSON object{expected}")


def _validate_answer_object(answer: Dict[str, Any]) -> None:
    missing = _ANSWER_FIELDS.difference(answer)
    if missing:
        raise ValueError(f"AnswerObject is missing required fields: {sorted(missing)}")
    if not isinstance(answer["question"], str) or not isinstance(answer["prose"], str):
        raise ValueError("AnswerObject question and prose must be strings")
    for field in ("claims", "basis", "abstentions"):
        if not isinstance(answer[field], list):
            raise ValueError(f"AnswerObject {field} must be an array")
    for claim in answer["claims"]:
        if not isinstance(claim, dict):
            raise ValueError("Every AnswerObject claim must be an object")
        missing = {"id", "text", "citations", "quote"}.difference(claim)
        if missing:
            raise ValueError(f"AnswerObject claim is missing fields: {sorted(missing)}")
        if not isinstance(claim["id"], str) or not isinstance(claim["text"], str):
            raise ValueError("AnswerObject claim id and text must be strings")
        if not isinstance(claim["citations"], list) or not all(
            isinstance(citation, str) for citation in claim["citations"]
        ):
            raise ValueError("AnswerObject claim citations must be an array of strings")
        if not isinstance(claim["quote"], str):
            raise ValueError("AnswerObject claim quote must be a string")
    if not all(isinstance(item, str) for item in answer["basis"]):
        raise ValueError("Every AnswerObject basis item must be a string")
    if not all(isinstance(item, dict) for item in answer["abstentions"]):
        raise ValueError("Every AnswerObject abstention must be an object")


def extract_document_text(pdf_path: Path | str) -> str:
    """Extract plain text from a PDF document fixture."""
    pdf = Path(pdf_path)
    if not pdf.is_file():
        return ""
    try:
        return extract_text(str(pdf)) or ""
    except Exception as exc:  # noqa: BLE001 - the caller decides whether empty text is usable
        logger.warning("Failed to extract text from %s: %s", pdf_path, exc)
        return ""


def _worker_prompt(doc_type: str, case_id: str, document_text: str) -> str:
    return f"""You are the live LLM Worker for a blind Canadian Express Entry document review.

Before reviewing, read and follow the repository's AGENTS.md and skills/pdf/SKILL.md.
You may use repository tools and the authoritative local corpus as directed there.
You have no access to the judge-only ground truth or injected-defect labels. Evaluate
only the document evidence below. Keep all applicant-specific facts and PII exclusively
inside basis[]; claims, quotes, abstentions, and prose must remain PII-free. Never invent
a citation or quote. If authoritative corpus evidence is unavailable, abstain with zero
claims as required by AGENTS.md.

Document type: {doc_type}
Opaque case ID: {case_id}
Document text:
<document>
{document_text}
</document>

Return ONLY one valid JSON AnswerObject with exactly these canonical fields:
question, claims, basis, abstentions, prose. Do not use Markdown fences or commentary.
"""


def _record_worker_failure(case_id: str, exc: BaseException) -> None:
    _WORKER_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    success_path = _WORKER_OUTPUTS_DIR / f"{case_id}.json"
    success_path.unlink(missing_ok=True)
    _write_json(
        _WORKER_OUTPUTS_DIR / f"{case_id}.error.json",
        {
            "case_id": case_id,
            "status": "failed",
            "engine": "copilot-cli",
            "model": _WORKER_MODEL,
            "timestamp": _utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )


def run_worker_review_task(
    doc_type: str,
    pdf_path: Path | str,
    case_id: str,
    extracted_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Disabled legacy entrypoint. Unisolated repository-root execution is prohibited.

    Use crawler.eval.pipeline_worker.run_blind_worker_task for isolated blind execution.
    """
    raise RuntimeError(
        "Legacy real_worker.run_worker_review_task is disabled to enforce isolated blind execution. "
        "Use crawler.eval.pipeline_worker.run_blind_worker_task instead."
    )
