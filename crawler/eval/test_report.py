"""Deterministic Markdown rendering for Phase 75 release evidence."""

from __future__ import annotations

from crawler.eval.release_orchestrator import (
    ReleaseAssessment,
    ReleaseEvidence,
    release_evidence_hash,
)


def _metric(value: float) -> str:
    return f"{value:.4f}"


def _delta(value: float) -> str:
    return f"{value:+.4f}"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _prose(value: str) -> str:
    return value.replace("|", "\\|")


def render_test_report(
    evidence: ReleaseEvidence,
    assessment: ReleaseAssessment,
) -> str:
    """Render measured evidence without delegating facts to model prose."""
    if assessment.phase74_run_id != evidence.phase74_run_id:
        raise ValueError("Assessment run binding does not match evidence")
    if (
        assessment.evidence_manifest_hash
        != evidence.phase74_evidence_manifest_hash
        or assessment.release_evidence_hash != release_evidence_hash(evidence)
    ):
        raise ValueError("Assessment binding does not match release evidence")

    lines = [
        "# Canadian Express Entry Document Review Test Report",
        "",
        "## Release Evidence",
        "",
        f"- **Phase 74 run:** `{evidence.phase74_run_id}`",
        f"- **Final revision:** `{evidence.phase74_final_revision}`",
        (
            "- **Final manifest:** "
            f"`{evidence.phase74_final_manifest_hash}`"
        ),
        (
            "- **Committed evidence manifest:** "
            f"`{evidence.phase74_evidence_manifest_hash}`"
        ),
        f"- **Release evidence hash:** `{release_evidence_hash(evidence)}`",
        (
            "- **SDK/runtime/protocol:** "
            f"`{evidence.sdk_version}` / `{evidence.runtime_version}` / "
            f"`{evidence.protocol_version}`"
        ),
        f"- **Workers:** `{evidence.worker_model}`",
        (
            "- **Judges:** "
            f"`{evidence.judge_model}` (`{evidence.judge_effort}`, "
            f"`{evidence.context_tier}`)"
        ),
        f"- **Optimizers:** `{evidence.optimizer_model}`",
        (
            "- **Release orchestrator:** "
            f"`{evidence.orchestrator_model}` (`xhigh`, "
            f"`{evidence.context_tier}`)"
        ),
        "",
        "## Coverage",
        "",
        "| Measure | Result |",
        "|---|---:|",
        (
            f"| Phase 72 research documents | "
            f"{evidence.phase72_research_documents} |"
        ),
        f"| Phase 73 logical cases | {evidence.phase73_logical_cases} |",
        f"| Phase 73 PDFs | {evidence.phase73_pdf_count} |",
        f"| Final Workers | {evidence.worker_count} |",
        f"| Final Judges | {evidence.judge_count} |",
        f"| Optimizers | {evidence.optimizer_count} |",
        (
            f"| Shared evaluations | "
            f"{evidence.shared_evaluation_count} |"
        ),
        f"| Peak concurrency | {evidence.peak_concurrency} |",
        (
            f"| Imported model artifacts | "
            f"{evidence.imported_model_artifact_count} |"
        ),
        (
            f"| Cleanup survivors / errors | "
            f"{evidence.cleanup_survivor_count} / "
            f"{evidence.cleanup_error_count} |"
        ),
        (
            f"| Accepted / rejected patches | "
            f"{evidence.accepted_patch_count} / "
            f"{evidence.rejected_patch_count} |"
        ),
        "",
        "## Per-Document Results",
        "",
        (
            "The shared baseline and final rerun are independent post-patch "
            "evaluations of the same frozen source. Their delta measures "
            "repeatability variance, not patch acceptance."
        ),
        "",
        (
            "| Document | Status | Cases | Workers | Judge | Shared baseline | "
            "Final rerun | Rerun delta | Patches A/R | Blockers |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for document in evidence.documents:
        lines.append(
            "| "
            + " | ".join(
                [
                    document.doc_type,
                    document.status,
                    str(document.case_count),
                    str(document.worker_count),
                    str(document.judge_count),
                    _metric(document.baseline_metrics.overall_score),
                    _metric(document.final_metrics.overall_score),
                    _delta(document.metric_deltas.overall_score),
                    (
                        f"{document.accepted_patch_count}/"
                        f"{document.rejected_patch_count}"
                    ),
                    _cell("; ".join(document.blockers) or "None"),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Accepted Self-Improvement Patches",
            "",
            (
                "These are the measured acceptance deltas used by the "
                "self-improvement gate."
            ),
            "",
            "| Sequence | Document | Commit | Target | Training delta | Holdout delta |",
            "|---:|---|---|---|---:|---:|",
        ]
    )
    for patch in evidence.accepted_patches:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(patch.sequence),
                    patch.doc_type,
                    f"`{patch.commit}`",
                    f"`{patch.target_file}`",
                    _delta(patch.training_overall_delta),
                    _delta(patch.holdout_overall_delta),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Validation Results",
            "",
            "| Gate | Status | Duration | Detail | Command |",
            "|---|---|---:|---|---|",
        ]
    )
    for validation in evidence.validation_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    validation.name,
                    validation.status,
                    f"{validation.duration_seconds:.2f}s",
                    _cell(validation.detail),
                    f"`{_cell(validation.command)}`",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Release Blockers",
            "",
        ]
    )
    if evidence.blockers:
        lines.extend(f"- {_cell(blocker)}" for blocker in evidence.blockers)
    else:
        lines.append("- None in measured evidence.")

    lines.extend(
        [
            "",
            "## GPT-5.6 Sol Assessment",
            "",
            (
                f"**Verdict:** `{assessment.verdict}`  "
                "(interpretive; measured tables above are authoritative)"
            ),
            "",
            _prose(assessment.summary),
            "",
            "### Strengths",
            "",
        ]
    )
    lines.extend(
        f"- {_cell(item)}" for item in assessment.strengths
    )
    if not assessment.strengths:
        lines.append("- None stated.")
    lines.extend(["", "### Assessment Blockers", ""])
    lines.extend(f"- {_cell(item)}" for item in assessment.blockers)
    if not assessment.blockers:
        lines.append("- None stated.")
    lines.extend(["", "### Recommendations", ""])
    lines.extend(
        f"- {_cell(item)}" for item in assessment.recommendations
    )
    if not assessment.recommendations:
        lines.append("- None stated.")
    lines.append("")
    return "\n".join(lines)
