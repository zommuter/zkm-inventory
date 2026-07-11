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
| **find-dump** (c, fast-follow) | **Independent.** Mount a drive, record its file listing → searchable per-drive content index (`zkm search "<title>"` → which drive). Exists *for* the bulk non-annex content annex-`whereis` never sees; complementary to lane-a's seam. ROADMAP id:46b6. |

**sync ≠ backup.** git-annex `whereis`/`numcopies` tells you *redundancy*
(copy-count). It does **not** tell you *freshness* of a one-way mirror — a drive
can hold a year-stale copy. `last_sync` is a manifest field, orthogonal to annex
copy-count. The manifest owns freshness; git-annex owns redundancy.

**Shared remote registry.** When the annex seam activates, the drives it reads
are the SAME named annex remotes that `zkm push` (core id:998b) and the future
`zkm fetch` (routed:12fc) use — one registry, not a private one.

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
