# Phase 47: Canonical AGENTS.md & Multi-CLI Adapter Layer - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 47 establishes the canonical `AGENTS.md` system specification and thin pointer adapters for all supported AI CLI runtimes (Copilot, Claude, Codex, Cursor, Antigravity, Windsurf). It defines how agents orchestrate search, grounding, vault auditing, and remediation tools to review applicant documents while enforcing strict fail-closed grounding and PII containment.
</domain>

<decisions>
## Implementation Decisions

### Agent Instructions & System Specification
- **Canonical AGENTS.md**: Define system prompt, tool contracts (`corpus-crawler`, `vault`), multi-agent roles, and step-by-step review workflows in a single portable `AGENTS.md`.
- **Fail-Closed Grounding**: The agent MUST refuse to answer or make claims that cannot be verbatim-grounded in the curated corpus/repo content.
- **Prompt Engineering Best Practices**: Structure agent prompts with role definition, explicit inputs/outputs, negative constraints, and verification loops to minimize hallucinations and mistake rates.

### Multi-CLI Adapter Layer
- **Thin Pointer Files**: `.github/copilot-instructions.md`, `CLAUDE.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, etc., delegate directly to `AGENTS.md`.
- **Portable Skills**: `skills/` directory formatted in CLI-agnostic Markdown accessible without proprietary API locks.

### Evaluation & Sample Documents
- **Synthetic Sample Documents**: Create sample applicant document fixtures to benchmark and evaluate agent instructions and error rates.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` — Core value, constraints, and architecture
- `.planning/REQUIREMENTS.md` — Active requirements AGENT-01..03, ADAPT-01..02
- `.planning/ROADMAP.md` — Phase 47 goal and success criteria
</canonical_refs>

---

*Phase: 47-canonical-agents-md-multi-cli-adapter-layer*
