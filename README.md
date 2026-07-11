# zkm-inventory

A [zkm](https://github.com/zommuter/zkm) plugin that turns a hand-authored
**asset-inventory manifest** into searchable markdown: external drives and
hardware devices (Raspberry Pis, IoT gadgets, …) become documents you can find
with `zkm search`.

> Status: **pre-alpha / handoff skeleton.** `convert()` is not yet implemented —
> the drives and devices lanes are specified as red tests in `tests/` and
> `ROADMAP.md`.

## Why

Descriptive, mutable asset data ("which drive holds the photo masters?", "which
RPi is gathering dust in a drawer?") doesn't belong in infra-as-code — it's
*knowledge*. zkm's git-as-temporal-index model fits it: you edit the manifest,
re-convert, commit; `git log` is the history of what was true when.

## Lanes

| Lane | Source | Output | git-annex |
|------|--------|--------|-----------|
| **drives** (v1) | manifest `drives:` | `inventory/drives/<id>.md` | optional dormant enrichment seam |
| **devices** (v1) | manifest `devices:` | `inventory/devices/<id>.md` | never (a device is not annexed content) |
| **find-dump** (fast-follow) | mounted drive file listing | per-drive content index | independent — covers bulk non-annex content |

The **drives** lane can *later* enrich each drive with git-annex redundancy
(`git annex whereis`/`info`) for the annex-managed subset — dormant today (0
annex-managed drives). **sync ≠ backup:** the manifest owns `last_sync`
freshness; git-annex owns copy-count redundancy. Whole-disk annex-onboarding is
an it-infra 3-2-1-backup decision, not this plugin's.

## Manifest

```yaml
drives:
  - id: media-2
    label: "Media Archive 4TB"
    capacity_gb: 4000
    location: "drawer / offsite"
    purpose: "movies, series, photo masters"
    data_classes: [movies, series, photos]
    last_sync: 2026-07-09
    offsite: true
devices:
  - id: pi-livingroom
    kind: raspberry-pi
    model: "Raspberry Pi 4B 8GB"
    location: "living room"
    status: in-use          # in-use | idle | dust-collecting | retired
    purpose: "Kodi media player"
```

## Install / develop

```bash
uv sync --extra dev          # zkm core is an editable path dep (../../)
uv run pytest                # hermetic red-spec suite
```

The repo must sit at `plugins/zkm-inventory/` inside a zkm core checkout (or a
host worktree) so `zkm = { path = "../../", editable = true }` resolves.

## Config

Set the manifest path in `$ZKM_STORE/zkm-config.yaml`:

```yaml
plugins:
  inventory:
    manifest: inventory.yaml   # relative to store root, or an absolute path
```

Then `zkm convert inventory && zkm index`.

## License

MIT © 2026 Tobias Kienzler (Zommuter / Tobias Kienzler Solutions)
