# zkm-inventory

zkm plugin repo shipping TWO plugins (one multi-document `plugin.yaml`):

- **`inventory`** (`convert.py`): a hand-authored YAML manifest of external drives +
  hardware devices → one searchable markdown file per record, plus a one-list device roster.
- **`inventory-finddump`** (`finddump.py`): sweeps the configured content roots of
  currently-mounted drives into per-drive file-listing shards (`zkm search "<title>"` →
  which drive holds it, even while the drive is unplugged).

**Store dirs**: `inventory/` (`drives/`, `devices/`, `devices.md`, `find-dump/`)
**Fetch boundary**: ingest-only. Reads a local manifest and local mounts; never fetches
remotely, never writes to a drive.

## Commands

```bash
uv sync --extra dev          # env (zkm core is an editable path dep: ../../)
uv run pytest                # full suite (hermetic: tmp_path stores, no network)
uv run pytest -k <expr>      # one roadmap item's done-check
uv run ruff check convert.py finddump.py tests/   # lint (line-length 100, py311)
scripts/pilot-drive-count.sh <dir>...             # read-only drive measurement (INV3-PILOT)
```

The repo must sit at `plugins/zkm-inventory/` inside a zkm core checkout for the
`zkm = { path = "../../", editable = true }` source to resolve. **A relay worktree under
`~/.cache/relay/worktrees/` does NOT satisfy that** (`../../` points into the cache), so
`uv run` there fails to resolve zkm. Run the suite with the main checkout's venv instead,
from the worktree root: `<main checkout>/.venv/bin/python -m pytest` and
`<main checkout>/.venv/bin/ruff check ...`. `conftest.py` prepends the CWD repo root to
`sys.path`, so the worktree's `convert`/`finddump` are the ones under test.

## Architecture (see ARCHITECTURE.md for the why)

```
store manifest (drives:/devices:/complete_as_of)  ->  convert()
    ├── drives[]   -> inventory/drives/<id>.md    (scope:inventory.drive)
    ├── devices[]  -> inventory/devices/<id>.md   (scope:inventory.device, status tag)
    └── devices[]  -> inventory/devices.md        (roster: one row per device + attestation)

zkm-config.yaml `inventory-finddump: drives: [...]`  ->  finddump.convert()
    └── per online drive -> inventory/find-dump/<id>.md + <id>/NNNN.md shards
```

- One md per record; the record's stable `id` is the idempotence key. Re-running an
  unchanged manifest is a git no-op.
- Store config sections are **top-level keys named after the plugin** (`inventory:`,
  `inventory-finddump:`), never under a `plugins:` wrapper: zkm's `StoreConfig.for_plugin`
  reads `data[<name>]`.

## Scope

- **Shipped**: drives + devices lanes, device roster with owner attestation, find-dump
  content index with mount auto-detection. Item status lives in `TODO.md` / `ROADMAP.md`.
- **Dormant seam**: git-annex redundancy enrichment for drives, gated on ≥2 annex-managed
  drives existing.
- **Out of scope**: floor plans / 3D / BIM (core `id:d35e` umbrella), live smarthome state,
  write-back to drives, whole-disk annex-onboarding (it-infra 3-2-1-backup owns that).

## Gotchas

- **Unknown manifest keys are a hard error** (`_MANIFEST_KEYS` / `_RECORD_KEYS` in
  `convert.py`). Adding a field means adding it to the allowlist AND rendering it, or the
  owner's manifest stops converting.
- **`complete_as_of` is owner-only.** Never infer, default or set it in code or tooling;
  absent means the roster says "NOT attested".
- **sync ≠ backup**: `last_sync` (manifest) is freshness; git-annex copy-count (later) is
  redundancy. Never conflate.
- **Published-generic**: this repo is PUBLIC. Fixtures, tests and docs use placeholder
  assets only: no real serials, UUIDs, locations, folder names or personal data. Pilot
  results go in as counts only.
- **Hermetic tests**: `tmp_path` stores, no network, no real `~/knowledge`, no real
  `lsblk` (tests monkeypatch `finddump._enumerate_mounts`).
- **Version in lockstep**: `pyproject.toml`, both `plugin.yaml` docs and both
  `PLUGIN_VERSION` constants move together; finddump stamps its version into every shard,
  so a bump re-stamps all shards on the next sweep.

## Related

- Scope meeting: `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`
- Core ledger: `id:e65e` (this plugin), `id:f22d` (drive lane origin), `id:d35e`
  (device-roster origin), `id:998b` (unified `zkm push` / shared remote registry).

## Relay contract <!-- relay-executor contract v28 -->

This repo is managed by a reviewer/executor relay. Load `/relay executor` before
working on any item, then follow its rules exactly.
