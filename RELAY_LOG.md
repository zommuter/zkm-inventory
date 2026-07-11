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

## 2026-07-11 22:30 — executor (sonnet)

Worked id:82a2 (INV1) and id:5697 (INV2) — implemented `convert()`: loads the YAML manifest
(`config["manifest"]`, resolved against `store_path`; raises `FileNotFoundError` when absent),
renders `inventory/drives/<id>.md` and `inventory/devices/<id>.md` via a shared `_write_record`
helper (`_build_entities`/`_render_body` dispatch on `kind`) using `zkm.atomic.write_atomic`.
Drives get a `scope:inventory.drive` `type:drive` entity (+ `type:place` when `location` is
set) and a body table (label/capacity/purpose/data_classes/location/last_sync/offsite); devices
get a `scope:inventory.device` `type:device` entity, `status` in both `tags:` and the body table.
Idempotence: `_write_record` compares the rendered content against the existing file and skips
the write (returns `None`, excluded from the created-paths result) when unchanged — verified by
`test_rerun_is_idempotent`. All 8 red tests pass; full suite green; ruff clean.

Smoke-tested via the real CLI (`zkm init` + `zkm-config.yaml` with a top-level `inventory:`
section — NOT `plugins: {inventory: ...}`, per `StoreConfig.for_plugin`'s bare-name lookup —
+ `zkm convert inventory`) against the fixture manifest: both `inventory/drives/` and
`inventory/devices/` .md render correctly with the expected frontmatter/body. Observed (not
fixed, out of scope for this session): the zkm-ner amender that runs as part of `zkm convert`
picks up spurious `scope:body` entities from the rendered markdown table syntax (e.g. treating
the "Value"/"Location"/"Status" table-header cells as org/person mentions) and its write-back
then defeats CLI-level idempotence on a second `zkm convert inventory` (our own `_write_record`
idempotence — verified in isolation by the unit test with no amenders — is unaffected; the
churn is the amender rewriting the file between runs, a pre-existing NER-quality/amender
interaction, not an INV1/INV2 regression).

Bumped 0.1.0 → 0.2.0 (`pyproject.toml`, `plugin.yaml`, `PLUGIN_VERSION`), `uv lock`, tagged
`v0.2.0` in the same commit. Friction: none — the spec matched the red tests cleanly; the only
surprise was the `zkm-config.yaml` top-level-key convention (not nested under `plugins:`),
discovered during the CLI smoke test rather than from written docs.

## 2026-07-11 22:35 — reviewer (claude-opus-4-8, /meeting follow-up)

INV3 (id:46b6) design pass landed → `docs/inv3-lane-c-design.md`. Decomposed into INV3a
(CENTRAL — dense-leg per-path opt-out in core `src/zkm/embed.py`; the find-dump md shards would
otherwise blow the embed index — filed in `~/src/zkm` ledger, not here), INV3b (deterministic
size-capped shard sweep), INV3c (mount orchestration + read-only UUID/label online-set), INV3d
(annex-pointer exclusion, small). User decisions: packaging = SEPARATE plugin `inventory-finddump`;
mount-identity = read-only UUID/label (marker-file rejected — no-write-to-drives fence); dense
opt-out = config path-prefix. **Storage tier is GATED on an HDD-content pilot** (INV3-PILOT +
`scripts/pilot-drive-count.sh`) — measure a real drive's file count before choosing T1-git-shards
vs annex-raw+thin-summary. INV3b–d gated on that pilot; INV3a independent/dispatchable now. The
NER-amender-trips-on-md-tables finding (from the executor's CLI smoke test) is routed to zkm-ner.
A Fable pass will sanity-review this session's decisions.
