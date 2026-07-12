# Cataloguing a drive with `inventory-finddump`

A practical walkthrough for turning a mounted external drive's content into
searchable per-drive markdown, using the lane-c `inventory-finddump` plugin.
For the *why* (shard sizing, idempotence, index-budget trade-offs) see
[`inv3-lane-c-design.md`](inv3-lane-c-design.md); for the manifest-based
**drives**/**devices** lanes see the top-level [`README.md`](../README.md).
This doc only covers the *how*: naming a drive, configuring the sweep, running
it, and where the full raw listing should live.

## 1. Drive-ID naming scheme

Drives are identified by a short, stable, human-typeable id built from
hardware identity, not a mutable mount path:

- **Disk id** — `<model>-<serial4>`, e.g. `wd-elements-a1b2`. `<serial4>` is
  the **last 4 characters** of the drive's hardware serial (never the full
  serial — see sanitization note below). This is the disk's `UID` in the
  manifest.
- **Per-partition / filesystem id** — `<fs-label>-<serial4>`, e.g.
  `media-a1b2`. The filesystem carries its own `FS-UUID` (the real, full
  filesystem UUID — used for mount matching, see §2), but the *id* reuses the
  same trailing `<serial4>` as its parent disk.
- **Why share `<serial4>` across partitions of one disk:** it's an
  intentional, at-a-glance marker that two ids (`media-a1b2`,
  `docs-a1b2`) are partitions **on the same physical spindle** — i.e. the same
  failure domain. If that disk dies, every id ending in `a1b2` is gone
  together. This matters for backup/redundancy planning (do two "backup
  copies" actually sit on two different spindles, or just two partitions of
  one?) — it's a naming convenience, not a substitute for checking `lsblk`.

Never write a real hardware serial or a real filesystem UUID into a
git-tracked file. Use `<serial4>` / `a1b2`-style placeholders in any example,
and store the real values only in local, non-committed config (see §2).

## 2. Configuring `inventory-finddump`

Add a `drives:` list to the store's `zkm-config.yaml` (or wherever the store's
plugin config lives — this is separate from the `inventory.manifest:` file the
drives/devices lanes read). Each entry is either:

- **Explicit `roots:`** — one or more already-known mount paths to sweep
  directly, no mount detection involved. Useful for a drive that's always
  mounted at a fixed path, or for testing.
- **`mount: {uuid, label}` + `content_roots:`** — the recommended form for a
  drive that moves between mountpoints (`/run/media/$USER/...`, drive letters,
  different hosts). At sweep time, currently-mounted filesystems are
  enumerated read-only (no marker file written to the drive — see
  design doc §Q3) and matched by `uuid` (exact) or `label` (case-insensitive)
  against this block. `content_roots` are then resolved **relative to** the
  resolved mountpoint.

`content_roots` is the scoping lever: point it at media/docs subtrees, not the
whole drive. The 2026-07-11 pilot measurement (design doc, "Pilot
calibration") found that sweeping whole system/OS partitions produces
1–3 **million** files of pure noise (`Program Files`, `Windows`,
`node_modules`, package caches) versus the handful of media/docs directories
that are actually the point of cataloguing a drive. Scope narrowly.

```yaml
# zkm-config.yaml (store-local, not the plugin repo)
plugins:
  inventory-finddump:
    drives:
      # Explicit mount path — always swept at this path.
      - id: media-a1b2
        roots:
          - /mnt/media-archive

      # Mount-detected — matched by filesystem UUID or label when online,
      # skipped gracefully when the drive is unplugged.
      - id: docs-a1b2
        mount:
          uuid: "<FS-UUID>"        # placeholder — real UUID stays local-only
          label: "DOCS"
        content_roots:
          - Documents
          - Pictures

      # A second drive, same physical spindle marker in the id suffix
      # (illustrative — these two ids sharing "a1b2" would mean "same disk").
      - id: media2-a1b2
        mount:
          label: "MEDIA2"
        content_roots:
          - Movies
          - home/<user>/Videos
```

`inventory-finddump` scopes the sweep to `content_roots` and then hands the
walk to `fd` (preferred backend; falls back to a pure-Python `pathspec` walk
if `fd`/`fdfind` isn't on `PATH`). `fd` already honors `.gitignore`, a global
ignore file, and skips hidden entries and `.git/` by default — so common
noise (`node_modules`, caches, dotfiles) is excluded by the same mechanism
everything else uses, with **no bespoke prune-list to maintain**. Still steer
`content_roots` at media/docs trees and away from OS roots (`Program Files*`,
`Windows`, `/usr`, `/var`, `/opt`) — ignore-filtering removes *noise inside* a
tree, it doesn't make sweeping an entire OS install cheap.

## 3. Run and verify

```bash
zkm convert inventory-finddump   # sweep online drives → md shards + summary
zkm index                        # BM25 (+ dense, excluding find-dump shards)
zkm search "<filename or title>" # → names the drive holding it
```

`convert` writes `inventory/find-dump/<drive-id>/NNNN.md` shards (one compact
`<relpath> <size> <mtime>` line per file, size/count-capped, grouped by
top-level directory) plus a per-drive summary
`inventory/find-dump/<drive-id>.md` carrying the shared
`scope:inventory.drive` entity and a `last_swept` date. A re-sweep of an
unchanged tree is byte-identical and is a git no-op — no new commits from
running the sweep repeatedly.

## 4. The raw whole-drive TOC principle

`inventory-finddump`'s git-tracked output is a **scoped** subset — whatever
`content_roots` names. It is deliberately *not* a from-the-root, "don't-miss-
a-file" manifest of the entire drive: that full listing would be far larger
than the media/docs subset and would bloat the git-tracked store for no
searchable benefit.

If you also want a complete, exhaustive table-of-contents of a drive (e.g. for
disaster-recovery "did I actually get everything off this disk" verification),
generate and keep it **separately**, in a durable, backed-up, and *disclosed*
location — a location someone doing recovery would know to look, not a
scratch/temp directory that gets wiped. For a drive large enough that even
this raw TOC is unwieldy in git, the escape hatch is git-annex: keep the raw
listing as annexed content and only the thin summary in git. Never let the
only copy of a whole-drive TOC live in ephemeral/temp storage — that defeats
its purpose as a recovery aid.

## 5. Offline / roaming drives

Drives are usually **not** plugged in. A drive whose `mount:` block doesn't
match any currently-mounted filesystem is skipped gracefully: `convert` never
raises, and its existing shards are left exactly as-is (last-known). There is
no "mark stale" rewrite — mutating a shard to say "stale" would itself be a
spurious git diff for a drive that physically cannot have changed while
offline. Instead, infer staleness by reading the per-drive summary's
`last_swept` date: an old date on a drive you know is often reconnected is
your cue to plug it in and re-sweep.
