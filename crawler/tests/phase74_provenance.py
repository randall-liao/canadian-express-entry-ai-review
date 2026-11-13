from __future__ import annotations

from typing import Any

from crawler.eval.genuine_optimizer import optimizer_provenance_digest
from crawler.eval.pipeline_judge import _judge_provenance_digest
from crawler.eval.pipeline_worker import _worker_provenance_digest


def build_provenance(
    role: str,
    *,
    live: bool,
    prompt_hash: str,
    attachment_hashes: list[str],
    output_hash: str,
    extras: dict[str, Any],
) -> dict[str, Any]:
    is_judge = role == "judge"
    provenance: dict[str, Any] = {
        "engine": "copilot-sdk" if live else "injected-test-runner",
        "sdk_version": "1.0.8" if live else "injected-test-runner",
        "runtime_protocol_version": "3" if live else "injected-test-protocol",
        "role": role,
        "model": "claude-opus-4.8" if is_judge else "gemini-3.6-flash",
        "effort": "xhigh" if is_judge else None,
        "context_tier": "long_context",
        "session_id": (
            f"sdk-{role}-session-123"
            if live
            else f"injected-{role}-session-123"
        ),
        "prompt_hash": prompt_hash,
        "attachment_hashes": attachment_hashes,
        "output_hash": output_hash,
        "started_at": "2026-07-25T12:00:00+00:00",
        "completed_at": "2026-07-25T12:00:01+00:00",
        "duration_seconds": 1.0,
        "terminal_event": "assistant.message",
        "is_live": live,
        "retry_classification": None,
        "turn_count": 1,
        "format_correction_count": 0,
        "initial_prompt_hash": prompt_hash,
        "correction_prompt_hashes": [],
        "assistant_response_hash_chain": [output_hash],
        "turn_session_ids": [
            (
                f"sdk-{role}-session-123"
                if live
                else f"injected-{role}-session-123"
            )
        ],
        **extras,
    }
    digest_fn = {
        "worker": _worker_provenance_digest,
        "judge": _judge_provenance_digest,
        "optimizer": optimizer_provenance_digest,
    }[role]
    provenance["provenance_digest"] = digest_fn(provenance)
    return provenance


def build_worker_provenance(
    pdf_hash: str,
    *,
    live: bool = False,
    prompt_hash: str = "a" * 64,
    output_hash: str = "b" * 64,
    answer_hash: str = "c" * 64,
    bundle_hash: str = "d" * 64,
) -> dict[str, Any]:
    return build_provenance(
        "worker",
        live=live,
        prompt_hash=prompt_hash,
        attachment_hashes=[pdf_hash],
        output_hash=output_hash,
        extras={
            "input_pdf_sha256": pdf_hash,
            "allowed_text_sha256": None,
            "bundle_hash": bundle_hash,
            "answer_hash": answer_hash,
            "pii_manifest_hash": "e" * 64,
            "pii_manifest_count": 0,
            "pii_manifest_categories": {},
        },
    )
