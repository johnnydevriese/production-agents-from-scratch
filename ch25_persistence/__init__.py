"""Chapter 25 — state, memory, and persistence.

The checkpoint that makes the cold-open bug catchable: a decision is not an effect.
A real SQLite store (`store`) replaces the in-memory dict the unit test used, so the
transaction boundary (`boundary`) is a thing that can fail — and the only test that
sees it open a *second connection* and reads the row back. `memory` adds the two
layers that must outlive the process: the persisted transcript and governed,
provenance-carrying episodic memory.

Stdlib `sqlite3`, no server: every `Store.connect()` is an independent transaction,
so an uncommitted write on one connection is genuinely invisible to another — which
is the whole lesson, made executable and offline.
"""
