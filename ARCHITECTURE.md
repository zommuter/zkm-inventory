# zkm-inventory — architecture

Design decisions, with rationale and the boundaries fixed by the scope meeting
(`../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`, core id:e65e).

## Problem

Descriptive/mutable *asset* data — external drives (capacity, purpose, offsite
location, last-sync) and hardware (RPis/IoT: model, location, in-use vs.
dust-collecting) — was routed into zkm from it-infra under the "admit rule":
descriptive/mutable data is *knowledge*, not infra-as-code. It must be
**searchable** ("which drive holds the photo masters?", "which Pi is idle?").

## Model: manifest → rendered markdown

The manifest is the **source** (like any plugin's source); the per-record `.md`
files are the **rendered, searchable output**. You edit the manifest and
re-convert; git records the mutation (HEAD = current, `git log` = history). This
is zkm's git-as-temporal-index working as intended — and unlike plugin-converted
*content* (mail, messages), the manifest is a first-class hand-authored source,
so editing it is expected.

- **Idempotence key** = each record's stable `id`. Re-running an unchanged
  manifest changes no bytes and reports no created paths.
- **Output layout**: `inventory/drives/<id>.md`, `inventory/devices/<id>.md`.
- **Typed entities** (γ schema): drives emit `scope:inventory.drive`, devices
  emit `scope:inventory.device`; location may emit a `type:place` entity. The
  descriptive fields also land in the rendered body so BM25 finds an asset by
  purpose / data class / status.

## Three lanes; git-annex touches only one

| Lane | git-annex role |
|------|----------------|
| **drives** (a, v1) | OPTIONAL redundancy enrichment for the *annex-managed subset* of drive contents, via read-only `git annex whereis`/`info`. **Dormant** — 0 annex-managed drives today; built only once ≥2 exist (observe-before-preventing). |
| **devices** (b, v1) | **None, ever.** A Raspberry Pi is not annexed content. Pure hand-authored descriptive md. |
| **find-dump** (c, shipped as the `inventory-finddump` plugin) | **Independent.** Mount a drive, record its file listing → searchable per-drive content index (`zkm search "<title>"` → which drive). Exists *for* the bulk non-annex content annex-`whereis` never sees; complementary to lane-a's seam. Design: `docs/inv3-lane-c-design.md`. |

**sync ≠ backup.** git-annex `whereis`/`numcopies` tells you *redundancy*
(copy-count). It does **not** tell you *freshness* of a one-way mirror — a drive
can hold a year-stale copy. `last_sync` is a manifest field, orthogonal to annex
copy-count. The manifest owns freshness; git-annex owns redundancy.

**Shared remote registry.** When the annex seam activates, the drives it reads
are the SAME named annex remotes that `zkm push` (core id:998b) and the future
`zkm fetch` (routed:12fc) use — one registry, not a private one.

## Manifest strictness: unknown keys are an error (owner ruling 2026-11-10)

Every key the manifest may carry is allowlisted (`_MANIFEST_KEYS`, `_RECORD_KEYS`); any
other key raises `ValueError` naming it. **Why:** the md is a pure render of the manifest,
so a silently-dropped key is silently-lost data, and the commonest manifest error is a
typo (`conditon:`, a singular `device:` that would drop the whole list). **Cost accepted:**
a new field must be added to the allowlist before a manifest may use it. **Rejected:**
warn-and-render (easy to miss in a convert log); silent drop (the pre-2026-11-10
behaviour, which is how the gap was found).

## Device roster and the completeness attestation

Besides one md per device, the devices lane renders `inventory/devices.md`: one table row
per device plus the manifest-level `complete_as_of` date. **Why:** a downstream decision
(project_manager's hardware repurposing, its id:62bb) needs "not listed" to mean "not
owned", and only the owner can assert that. So the attestation is an owner-set date that
code never infers; without it the roster says "NOT attested". The roster sits BESIDE
`devices/`, not inside it, so no record `id` can collide with it. **Rejected:** stamping
the date onto every device md (a one-field change would rewrite every record and blur
per-record git history); inferring completeness from manifest mtime (that is exactly the
claim only the owner can make).

## Drive identity for mount matching (INV5, owner ruling 2026-11-10)

finddump finds an online drive by matching its `mount:` block against `lsblk`. Labels are
reused across disks, and the FS-UUID changes on a reformat (observed 2026-11-10 on a
reformatted media HDD: only the label match kept its sweep working). The hardware serial
(`ID_SERIAL_SHORT`) is the durable key, but `lsblk` reports it on the DISK only, never on
its partitions, and one disk can carry several swept partitions. **Decision:** a partition
inherits its parent disk's serial (via `lsblk` `PKNAME`); `mount: {serial: ...}` narrows
to that disk, then `label`/`uuid` picks the partition; serial alone suffices when the disk
has exactly one mounted partition. **Rejected:** serial + partition number (survives a
relabel, but breaks when the partition table is redone, and is invisible to the owner);
serial as display metadata only (leaves the reuse/reformat failure in place).

## Records removed from the manifest (INV6, shipped v0.8.0)

`convert()` prunes, so a device or drive removed (or renamed) in the manifest no longer
leaves a stale md behind to be searched. After rendering, every
`inventory/{drives,devices}/<id>.md` whose id is absent from the manifest is deleted
together with its `<md>.*` sidecars, and the deleted paths are returned so core's scoped
`git add` stages the removal. The prune is confined by ownership and by directory: only a
file whose frontmatter `source` is `inventory` is ever touched (a hand-written note or an
unparseable file in the lane dir is left alone), and only the two lane dirs are swept,
never `inventory/find-dump/` (a different plugin's output). `inventory/devices.md` goes
too when the manifest has neither devices nor a `complete_as_of` attestation. A deleted
record's amender write-back goes with it: a sidecar for a non-existent md has no reader
(the alternative, orphan sidecars left for core `zkm gc`, was rejected).

## Boundaries (out of scope)

- Floor plans / 3D / BIM / warranties — the broader core `id:d35e` umbrella; this
  plugin only takes the flat device roster.
- Live smarthome device state (snapshot only, if ever).
- Any write-back to drives.
- **Whole-disk annex-onboarding** of external HDDs — an it-infra 3-2-1-backup
  architecture decision (core routed:cfc1). This plugin is an *observer* of the
  backup topology, never its setter; it consumes whatever annex topology exists,
  and never blocks on it.

## Rejected alternatives

- **Notes-only convention** (hand-edited `notes/inventory/` md, no code): viable
  for the hardware roster alone, but loses typed entities, a refreshable render
  pipeline, and the lane-c content index. Rejected in favour of a real plugin.
- **Hand-authoring redundancy** in the manifest: would duplicate and drift from
  git-annex's location log. Rejected — query annex, don't reinvent `whereis`.
- **Annex-only model** (no manifest): blind to the bulk of drive contents and to
  every descriptive/physical/hardware field annex can't know. Rejected.
