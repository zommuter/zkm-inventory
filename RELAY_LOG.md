# Relay log <!-- merge=union; append-only — never edit or reorder past entries -->

## 2026-07-11 21:32 — reviewer (claude-opus-4-8, /meeting handoff)

Initial skeleton + handoff for **zkm-inventory** (v0.1.0 baseline), created from the
scope meeting `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md` (core
id:e65e). Skeleton: `plugin.yaml` (name `inventory`, `creates_dirs: [inventory]`, required
`manifest` config), `convert.py` stub (raises NotImplementedError — RED), `pyproject.toml`
(editable `zkm>=0.16,<1.0`, pyyaml + python-frontmatter), README/CLAUDE/ARCHITECTURE,
conftest sys.path shim, published-generic fixture `tests/fixtures/inventory.yaml`
(placeholder assets only — repo is PUBLIC), 8 red specs in `tests/test_inventory.py`, and
`@manual`/`@future` Gherkin in `features/inventory.feature`.

Two dispatchable ROUTINE items, both backed by red tests: **INV1 (id:82a2)** drives lane →
`inventory/drives/<id>.md` with `scope:inventory.drive` entities; **INV2 (id:5697)** devices
lane → `inventory/devices/<id>.md` with `scope:inventory.device` entities + searchable status.
One HARD gated fast-follow: **INV3 (id:46b6)** find-dump drive-content index (git-annex
independent; needs its own design pass before dispatch). One dormant seam: git-annex
redundancy enrichment for the drives lane, gated on ≥2 annex-managed drives (0 today).

Key boundary fixed at scope time: git-annex touches ONLY the drives lane's redundancy column,
and only for annex-managed content — the hardware roster and the manifest-driven drive map are
fully buildable today at 0 annex drives. sync ≠ backup (manifest owns `last_sync` freshness;
annex owns copy-count). Whole-disk annex-onboarding is the it-infra 3-2-1-backup meeting's call
(core routed:cfc1), not this repo's — this plugin observes the backup topology, never sets it.

Not budgeted this turn: implementation (INV1/INV2 are the executor's), INV3 design decomposition,
the annex enrichment seam (dormant).
