# zkm-inventory

zkm plugin: convert a hand-authored asset-inventory manifest (external drives +
hardware) into searchable markdown with typed `entities[]`.

**Store dirs**: `inventory/` (`inventory/drives/`, `inventory/devices/`)
**Fetch boundary**: ingest-only — reads a local YAML manifest via `manifest` config; never fetches remotely, never writes to drives.

## Commands

```bash
uv sync --extra dev          # env (zkm core is an editable path dep: ../../)
uv run pytest                # full suite (hermetic — tmp_path stores, no network)
uv run pytest -k <expr>      # one roadmap item's done-check
uv run ruff check convert.py tests/   # lint (line-length 100, py311)
```

The repo must sit at `plugins/zkm-inventory/` inside a zkm core checkout (or a
host worktree) for the `zkm = { path = "../../", editable = true }` source to
resolve.

## Architecture (intended — see ARCHITECTURE.md)

```
manifest.yaml (drives:/devices:)  →  convert()
                                       ├── _render_drive()  →  inventory/drives/<id>.md  (scope:inventory.drive)
                                       └── _render_device() →  inventory/devices/<id>.md (scope:inventory.device)
```

One md per record. Dedup/idempotence key: the record's stable `id`. Re-running
an unchanged manifest is a git no-op.

## Scope

- **v1 lanes**: drives (a) + devices (b), manifest-driven. Buildable with **0**
  git-annex drives — the annex-enrichment path is a **dormant seam** gated on
  ≥2 annex-managed drives existing.
- **lane-c (fast-follow)**: `find`-dump drive-content index (`zkm search` →
  which drive holds file X). git-annex INDEPENDENT — covers bulk non-annex
  content. ROADMAP id:46b6. Heaviest lane (large manifests, mount orchestration).
- **Out of scope**: floor plans / 3D / BIM (core `id:d35e` umbrella), live
  smarthome state, write-back to drives, whole-disk annex-onboarding (it-infra
  3-2-1-backup meeting owns that).

## Gotchas

- **sync ≠ backup**: `last_sync` (manifest) is freshness; git-annex copy-count
  (later) is redundancy. Never conflate.
- **Published-generic**: this repo is PUBLIC — fixtures/tests use placeholder
  assets only, no real serials/locations/personal data.
- **Hermetic tests**: `tmp_path` stores, no network, no real `~/knowledge`.
- **conftest.py** prepends the worktree root to `sys.path` so `import convert`
  resolves here, not the editable-install .pth copy.

## Related

- Scope meeting: `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`
- Core ledger: `id:e65e` (this plugin), `id:f22d` (drive lane origin), `id:d35e`
  (device-roster origin), `id:998b` (unified `zkm push` / shared remote registry).

## Relay contract <!-- relay-executor contract v6 -->

This repo is managed by a reviewer/executor relay. Load `/relay executor` before
working on any item, then follow its rules exactly.
