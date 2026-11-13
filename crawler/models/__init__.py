"""Pydantic models package for the candidate vault (Phase 29 — v4.0).

These are boundary models only: they validate/shape data crossing into and out of
the private ``vault.sqlite`` store. The persisted format stays plain SQLite + JSON
text (ARCHITECTURE-v4.0 "SQLite Schema Option"); pydantic is used at the module
boundary for typed construction and PII-light summaries.
"""
