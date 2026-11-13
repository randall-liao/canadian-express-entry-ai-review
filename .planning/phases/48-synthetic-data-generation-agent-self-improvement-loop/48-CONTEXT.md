# Phase 48: Synthetic Data Generation & Agent Self-Improvement Loop - Context

**Gathered:** 2026-07-21
**Status:** Ready for research

<domain>
## Phase Boundary

Phase 48 establishes a comprehensive synthetic data generation pipeline and automated evaluation loop covering ALL 22 Express Entry e-APR supporting document types plus Letters of Explanation (LoE). It benchmark-scores agent review accuracy against synthetic ground truth (text, layout, and image-based PDFs/scans with realistic errors/ambiguities) and uses evaluation findings to iteratively optimize system prompts (`AGENTS.md`), review skills (`skills/`), and tool error handling.
</domain>

<decisions>
## Implementation Decisions

### Synthetic Document Coverage (All 22 Express Entry Document Types + LoE)
- **Full e-APR Document Suite**: Synthetic generator MUST produce test fixtures for all 22 Express Entry document types:
  1. Passports & Travel Documents
  2. Language Test Results (IELTS / CELPIP / TEF / TCF)
  3. Educational Credential Assessment (ECA)
  4. Employment Reference Letters & Work Experience Proof
  5. Proof of Funds / Bank Letters & Statements
  6. Immigration Medical Examination (IME) Receipts / eMedical
  7. Police Certificates (Multiple countries, clear & non-clear)
  8. Digital Photos
  9. Certified Translations & Translator Affidavits
  10. Written Job Offers & LMIA Documentation
  11. Proof of Studies (Canadian & Foreign Diplomas/Transcripts)
  12. Certificate of Qualification (Trade Certification)
  13. Birth Certificates
  14. Marriage Certificates
  15. Statutory Declaration of Common-Law Union (IMM 5409)
  16. Divorce Certificates / Legal Separation
  17. Death Certificates
  18. Adoption Certificates
  19. Use of Representative (IMM 5476)
  20. Relative in Canada Evidence (Proof of status, residency, relationship)
  21. Proof of Other Name / Legal Name Change
  22. Authority to Release Personal Information (IMM 5475)
  23. **Letters of Explanation (LoE)**: Synthetic LoEs addressing common post-ITA discrepancies (e.g., bank balance fluctuations, missing job duties, police certificate delays, gift deed explanations).

### Image-Based PDF & Multimodal Vision Testing
- **Text & Image PDF Generation**: Generate both clean text-based PDFs and image-based/scanned PDF fixtures (utilizing `reportlab`, `Pillow`, and `pdfplumber`/`pypdfium2`).
- **OCR & Vision Verification**: Ensure testing covers image-based PDF extraction (`pytesseract`, `pypdfium2` 300 DPI page renders, and `claude-office-skills` / `pdf-extraction`).

### Benchmark Evaluation & Prompt Optimization Loop
- **Ground-Truth Evaluation Harness**: Compare agent review outputs against structured JSON ground truth for each synthetic document/LoE fixture.
- **Metric Scoring**: Compute grounding accuracy, citation exactness (`relpath#ordinal`), PII containment, and edge-case defect detection rate.
- **Feedback-Driven Optimization**: Automatically surface failing benchmark cases and iteratively refine system prompts (`AGENTS.md`), document review skills (`skills/`), and CLI tool error handling to minimize mistake rates.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` — Core value, constraints, and architecture
- `.planning/REQUIREMENTS.md` — Requirements SELF-01, SELF-02, SELF-03
- `.planning/ROADMAP.md` — Phase 48 goal and success criteria
- `skills/document-agents/` — 22 document review agent skills
</canonical_refs>

---

*Phase: 48-synthetic-data-generation-agent-self-improvement-loop*
