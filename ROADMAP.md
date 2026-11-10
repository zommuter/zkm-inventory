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

## Deferred / dormant (not dispatchable yet)

- **git-annex redundancy enrichment for the drives lane** — read-only `git annex whereis`/`info`
  to add copy-count/location for the annex-managed subset, graceful-degrade if annex missing or
  drive offline. **Dormant: gated on ≥2 annex-managed drives existing** (0 today). Whole-disk
  annex-onboarding is the it-infra 3-2-1-backup meeting's decision (core routed:cfc1), not this
  repo's. Build only once the gate is met.
