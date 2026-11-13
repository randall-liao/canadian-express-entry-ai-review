# Portable Skills Interface

This directory contains CLI-agnostic, portable agent skills formatted in plain Markdown following the open **AGENTS.md** and **Agent Skills** specifications.

## Architecture

The skills directory is organized into two core categories:

1. **`skills/document-agents/`** — 22 grounded document review agents for Express Entry e-APR documents (passport, police certificate, reference letters, proof of funds, ECA, etc.), sharing the contract in `skills/document-agents/_contract.md`.
2. **`skills/crs-auditors/`** — 4 factor substantiation auditor agents (spouse/common-law, skill transferability, additional points, etc.), sharing the contract in `skills/crs-auditors/_contract.md`.

## CLI Compatibility

Skills are vendor-neutral and contain no proprietary LLM framework dependencies, vendor tags, or API locks. Any AI agent CLI (Claude, Copilot, Codex, Cursor, Windsurf, Antigravity) reads these markdown files directly to perform grounded document reviews and CRS audits.
