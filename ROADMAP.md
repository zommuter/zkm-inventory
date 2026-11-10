# Roadmap <!-- relay-executor contract v6 -->
Executor-facing task spec. Each item is sized for ONE Sonnet session. Items are
the single source of truth; TODO.md carries only a summary line. The integrator ticks
checkboxes from your `worked_ids`; only the reviewer adds, removes, or re-scopes items.

Shared rules for every item below:
- Load `/relay executor` first; follow it exactly. Do NOT weaken/skip/delete a test to make it pass.
- Run the FULL suite after your item goes green: no regressions. In a relay worktree under
  `~/.cache/relay/worktrees/` `uv run` cannot resolve the `../../` zkm path dep; use the main
  checkout's venv from the worktree root (`<main>/.venv/bin/python -m pytest`), see CLAUDE.md.
- `ruff check convert.py finddump.py tests/` clean.
- Fixtures must be published-generic: placeholder names only, no real serials, UUIDs, user
  names, paths or personal data (this repo is PUBLIC).
- **Executors never bump the version.** The reviewer bumps at integrate (zkm relay rule).
- Append a one-paragraph self-report to `RELAY_LOG.md` and commit it.

## Items

- [ ] [ROUTINE] **INV8 — finddump: a failing `lsblk` is loud, never "every drive offline"** <!-- id:0a98 -->
  - **Acceptance**: when at least one configured drive uses `mount:` and drive enumeration
    cannot run (`lsblk` not on PATH, or it exits non-zero), `finddump.convert()` raises
    `RuntimeError` whose message names `lsblk` and the cause. Same for the serial lookup when a
    drive uses `mount: {serial: ...}`. A drive that is simply not plugged in (lsblk works,
    nothing matches) still skips quietly with `[]`; a config with only explicit `roots:` never
    calls lsblk. Unparsable individual lines may still be skipped.
  - **Tests**: `tests/test_finddump_lsblk_loud.py` (`# roadmap:0a98`), currently RED (3 red,
    2 constraints that already pass).
  - **Done-check**: `pytest tests/test_finddump_lsblk_loud.py` then the FULL suite + ruff.
  - **Context**: owner ruling 2026-11-10 (relay human, REVIEW_ME batch 1). `finddump.py`
    `_lsblk_rows` (shared by `_enumerate_mounts` / `_enumerate_serials`) currently returns `[]`
    on any failure; update its docstring and ARCHITECTURE/design §Q3 wording to match. Existing
    tests monkeypatch `_enumerate_mounts` / `_enumerate_serials` and must stay green unchanged.

## Deferred / dormant (not dispatchable yet)

- **git-annex redundancy enrichment for the drives lane** — read-only `git annex whereis`/`info`
  to add copy-count/location for the annex-managed subset, graceful-degrade if annex missing or
  drive offline. **Dormant: gated on ≥2 annex-managed drives existing** (0 today). Whole-disk
  annex-onboarding is the it-infra 3-2-1-backup meeting's decision (core routed:cfc1), not this
  repo's. Build only once the gate is met.
