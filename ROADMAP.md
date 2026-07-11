# Roadmap <!-- relay-executor contract v6 -->

Executor-facing task spec. Each item is sized for ONE Sonnet session. Items are
the single source of truth — TODO.md carries only a summary line. Executors tick
checkboxes; only the reviewer adds, removes, or re-scopes items.

Shared rules for every item below:
- Load `/relay executor` first; follow it exactly. Do NOT weaken/skip/delete a test to make it pass.
- Run the FULL suite (`uv run pytest`) after your item goes green — no regressions.
- `uv run ruff check convert.py tests/` clean on files you touch.
- Fixtures must be published-generic: placeholder names only, no real personal data (this repo is PUBLIC).
- Bump `version` in `pyproject.toml` + `plugin.yaml` + `PLUGIN_VERSION` and tag `vX.Y.Z`
  in the same commit when behavior changes (loose-0.x: minor for features). One bump per
  session is fine if you complete multiple items. A bump regenerates `uv.lock` — commit it.
- Append a one-paragraph self-report to `RELAY_LOG.md` and commit it.

## Items

- [ ] **INV1 — drives lane: render `inventory/drives/<id>.md`** [ROUTINE] <!-- id:82a2 -->
  Implement `convert(store_path, config, *, progress=None)` for the manifest's `drives:` list.
  Read the YAML manifest at `config["manifest"]` (relative paths resolve against `store_path`;
  raise `FileNotFoundError` if absent). For each drive record write `inventory/drives/<id>.md`
  via `zkm.atomic.write_atomic` with: frontmatter `source: inventory`, `date` (manifest mtime,
  ISO-8601 local), `processor`/`processor_version`, a typed `entities[]` list including
  `{scope: inventory.drive, type: drive, value: <id>, canonical: <label>}` (and a
  `{scope: inventory.drive, type: place, value: <location>}` when `location` is set); and a
  rendered markdown body table carrying label/capacity/purpose/data_classes/location/last_sync/offsite
  so BM25 can find a drive by purpose or data class. Keyed by `id` (idempotent re-run = git
  no-op; return only newly created/changed paths). **Done-check:**
  `uv run pytest tests/test_inventory.py -k "drives or idempotent or missing_manifest"` green.

- [ ] **INV2 — devices lane: render `inventory/devices/<id>.md`** [ROUTINE] <!-- id:5697 -->
  Same pipeline for the manifest's `devices:` list → `inventory/devices/<id>.md`. Frontmatter
  `source: inventory`; typed `entities[]` including `{scope: inventory.device, type: device,
  value: <id>, canonical: <model>}`; put `status` (in-use|idle|dust-collecting|retired) into
  BOTH a `tags:` entry and the rendered body so `zkm search dust-collecting` surfaces an idle
  device. Body table: model/kind/location/status/purpose. Keyed by `id`, idempotent. Reuse the
  INV1 helpers (shared record→md rendering). **Done-check:**
  `uv run pytest tests/test_inventory.py -k "device or dust"` green, then FULL suite green.

- [ ] **INV3 — find-dump drive-content index (lane-c, fast-follow)** [HARD] 🚧 GATED (DEP: v1 lanes INV1+INV2 shipped) <!-- id:46b6 -->
  Mount each drive + record its file listing (paths/sizes/mtimes) → a searchable per-drive
  content manifest so `zkm search "<title>"` names which drive holds a file. **git-annex
  INDEPENDENT** (covers bulk non-annex content). Needs its OWN design pass before dispatch:
  manifest size strategy (per-drive chunking / compact format), mount orchestration + which
  drives are online, snapshot refresh (re-sweep = git diff = "when did a file move/vanish"),
  and how a huge file list is indexed without blowing the BM25 budget. Demonstrated need:
  locate favorite movies/media across drives (2026-07-11). Do NOT start until INV1+INV2 are
  green and the reviewer has scoped the sub-items. See ARCHITECTURE.md.

## Deferred / dormant (not dispatchable yet)

- **git-annex redundancy enrichment for the drives lane** — read-only `git annex whereis`/`info`
  to add copy-count/location for the annex-managed subset, graceful-degrade if annex missing or
  drive offline. **Dormant: gated on ≥2 annex-managed drives existing** (0 today). Whole-disk
  annex-onboarding is the it-infra 3-2-1-backup meeting's decision (core routed:cfc1), not this
  repo's. Build only once the gate is met.
