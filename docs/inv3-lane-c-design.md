# INV3 (id:46b6) — lane-c "find-dump drive-content index" design pass

Reviewer design pass (no implementation). Repo untouched — output is this file only.
INV3 stays **GATED** until v1 (INV1 id:82a2 + INV2 id:5697) ships; the sub-items below
are for the reviewer to dispatch **after** the drives + devices lanes are green.

## What lane-c is (recap)

Mount an external drive that happens to be online, record its file listing
(path / size / mtime) into searchable per-drive markdown so `zkm search "<a movie
title>"` names which drive holds the file. It is **git-annex INDEPENDENT** — it exists
precisely for the bulk NON-annex content that `git annex whereis` never covers
(favorite movies / bulk media not worth annexing). Complementary to lane-a's annex
seam; the two must stay non-overlapping. It is the heaviest lane: large listings, mount
orchestration, index-budget pressure.

Key facts verified against current core (2026-07-11, `src/zkm/index.py`, `src/zkm/embed.py`):
- BM25 indexer walks `store.rglob("*.md")` skipping `_SKIP_DIRS = {plugins, .zkm-index,
  originals, .git}` — so `inventory/**` **is** indexed. `tokenize()` splits on
  `\w[\w'-]+`, so `Blade.Runner.2049.mkv` → `blade runner 2049 mkv` (dots/slashes are
  token boundaries — good for filename search). Each `.md` file is **one BM25 document**.
- BM25 is incremental (git-diff + mtime cache) and delta-friendly.
- **Dense embeddings consume the SAME `docs` list** the BM25 index produced
  (`build_embed_store(store, docs, …)`), chunked into 2000-char windows. There is
  **no per-doc dense opt-out today** — `zkm index --no-embed` is global-only. A
  multi-thousand-line path-listing md would explode into hundreds of useless chunks per
  file × thousands of files. **This is the single biggest risk and needs a core change.**

---

## Q1 — Manifest / output shape & size

**Options**
- **(A) One md per drive, full listing in body.** Simplest render. Fails: a 100k-file
  drive → multi-MB single md → huge `bm25.pkl` doc, slow tokenize, and (fatally) a dense
  chunker explosion. One BM25 "document" per drive also saturates term frequencies.
- **(B) Per-directory / size-capped md shards.** Bounded md size, natural git-diff
  granularity (a moved file = one changed line in one shard), BM25 ranks shards. Risk:
  a 100k-file drive with 10k dirs → 10k tiny docs (index-count bloat) if sharded strictly
  per-dir.
- **(C) Compact data sidecar (jsonl/tsv) = source of truth + thin rendered index md.**
  Smallest git footprint, but reintroduces a "which artifact is source of truth"
  ambiguity the plugin deliberately avoids (the *drive* is the source; the md is the
  render), and BM25 can't search a non-md sidecar.

**Recommendation: (B) with a size/line budget, not strict per-dir.**
- Layout: `inventory/find-dump/<drive-id>/NNNN.md` rendered shards + one per-drive
  summary `inventory/find-dump/<drive-id>.md`.
- **Shard body = one compact line per file**: `<relpath>\t<size>\t<mtime-iso>`. Plain
  lines (NOT a fenced markdown table) — fenced-table pipes/backticks add tokenizer noise
  and bytes; plain lines diff and tokenize cleanly.
- **Deterministic, locality-preserving shard packing** (see Q4): anchor shards on the
  top-level directory, sorted by path, splitting only oversized directories into
  `NNNN` sub-shards by a size cap (default target ~2000 entries / ≤~256 KB per shard).
  A single-file insert then rewrites only that directory's shard, not every downstream
  shard.
- **Per-drive summary md** carries frontmatter `source: inventory`, the **shared**
  `{scope: inventory.drive, type: drive, value: <id>, canonical: <label>}` entity (same
  entity lane-a INV1 emits — so a search resolves both legs to the same drive),
  `last_swept` (ISO), file count, total bytes, and a body list of shard pointers.
- **No separate binary data artifact in v1** — the md shards ARE both the searchable
  render and the temporal record; keeping a parallel jsonl "truth" file would duplicate
  and drift. Revisit only if md volume proves painful (the HUMAN DECISION in Q2).

Rationale: BM25 wants filename tokens present in an md whose path/frontmatter names the
drive — (B) delivers that with bounded, diff-friendly, git-cheap files, and dodges (A)'s
dense-chunk blowup at the shard level while (C)'s ambiguity is avoided.

## Q2 — Storage tier for the file-list artifacts

Map onto the 4-tier policy (`project_storage_tiering_policy.md`, 2026-06-24):
T1 git (md/text) · T2 annex (binaries) · T3 synced (embeddings) · T4 regenerate (bm25).

- The listings are *derivable* (re-sweepable) → tempting T4/regenerate. **But the entire
  point of lane-c is the git-diff temporal signal** ("when did this file move / vanish").
  Regenerate-tier discards history → wrong.
- The shards are text/markdown → the T1 rule ("markdown/text → git") applies directly.
- Cost is bounded: ~80 bytes/line × 100k files ≈ 8 MB first commit for a big drive, but
  git delta-compresses subsequent sweeps to just the changed lines → cheap over time.

**Recommendation: T1 git** for the find-dump shards + summary (they live in `~/knowledge`,
already a T1 store — NOT the tool repo). The derived BM25 index stays T4/regenerate; the
find-dump shards are **excluded from the T3 dense/embeddings tier entirely** (Q5).

Caveat surfaced to the human (Q "HUMAN DECISIONS"): a *multi-million-file* drive makes even
the delta-compressed history heavy. The escape hatch — raw listing in annex + only the thin
summary in git — trades away line-level temporal diff. Default is T1 git; the user signs off
on the bloat trade-off for very large drives.

## Q3 — Mount orchestration & the online-set

Drives are usually OFFLINE; a sweep must handle "whatever happens to be plugged in now" and
never block on an absent drive.

**Enumerate online drives:** config `find_dump.roots` = list of mount parents to scan
(default candidates `/run/media/$USER`, `/media`, `/mnt`); each immediate subdir that is a
mountpoint is a candidate. Never scan the whole FS.

**Map mounted path → drive `id`:** two read-only options —
- **(i) Marker file `.zkm-drive-id` at the drive root.** Robust across mountpoints/OS —
  **BUT writing it to the drive VIOLATES the plugin's "no write-back to drives" boundary**
  (ARCHITECTURE.md §Boundaries). **Rejected on that ground.**
- **(ii) Filesystem UUID / label, read-only.** The lane-a manifest drive record carries a
  `mount:` block (`uuid:` and/or `label:`); the sweep reads the mounted device's UUID/label
  (`/proc/mounts` + `/dev/disk/by-uuid`, or `lsblk -no UUID,LABEL`, no privilege) and matches
  it to a manifest id. **Recommended** — read-only, honors the boundary.

**Partial coverage / graceful degrade:** sweep ONLY the resolved online set. An unmatched
mountpoint → logged + skipped (never errors). An absent drive → its prior shards are left
untouched (last-known); the command never blocks or fails on absence. Mirrors the
`--no-dense` / annex graceful-degrade pattern the scope meeting fixed.

**Cadence separation (recommended):** do **not** fold the heavy, mount-dependent sweep into
`zkm convert inventory` (which must stay fast + mount-free so a one-line manifest edit
re-renders instantly). Declare find-dump as a **second plugin in a multi-doc `plugin.yaml`**
(`inventory` + `inventory-finddump`, the pattern zkm-stt uses), dispatched explicitly as
`zkm convert inventory-finddump`. Clean concern + cadence split; this is a HUMAN DECISION
(alternative: one converter behind a `find_dump.enabled` config gate).

## Q4 — Snapshot refresh & temporal semantics

- **Re-sweep of an online drive** = regenerate its shards from the current listing → the
  git diff of the rewritten shards is the temporal record (added / removed / moved lines).
- **Absent drive** = leave its shards exactly as-is (last-known). Do **not** delete and do
  **not** rewrite to mark "stale" — a destructive edit both loses the record and churns git
  history. Staleness is *inferred* from the per-drive summary's `last_swept` date (a query
  can see it's old). (You physically cannot mutate an offline drive's real listing anyway.)
- **Idempotence key = (drive-id, relpath).** A re-sweep of an unchanged drive MUST produce
  byte-identical shards → git no-op → `convert()` returns no created paths. This requires:
  1. **Deterministic entry order** — sort entries by path within a shard.
  2. **Stable, locality-preserving shard boundaries** — anchor on top-level directory
     (Q1), so inserting/removing one file rewrites only that directory's shard(s), never
     cascading a boundary shift across all downstream shards (the classic "one insert
     dirties every file" off-by-one trap). Split an oversized directory into `NNNN`
     sub-shards by a deterministic rule (sorted-path prefix), so the split point doesn't
     wobble between sweeps.
  3. **mtime rendering must be stable** — render mtime at a fixed resolution (e.g. ISO
     seconds) so sub-second jitter doesn't produce spurious diffs.

## Q5 — Indexing budget

- **BM25:** each shard = one document of filename tokens. Lexically correct (the point) and
  cheap TF — acceptable added doc-count. Keep BM25-indexed by default (that IS the feature).
- **Dense embeddings:** semantically useless over file paths AND catastrophic in cost — a
  2000-line shard × 2000-char windows → hundreds of chunks per shard × thousands of shards.
  **find-dump must be excluded from the dense leg.**
- **Gap:** no per-doc dense opt-out exists; `--no-embed` is global. **Fix = a core change**
  (`src/zkm/embed.py` + config) → this is a **CENTRAL** item under boundary rule #1 (edits
  `src/zkm/**`), NOT plugin-local.
  - **Recommended mechanism:** a config-driven **path-prefix skip** for the dense leg —
    `build_embed_store` (or its `cmd_index` caller) filters out docs whose `rel_path` starts
    with any prefix in a `dense_skip_prefixes` set that defaults to include
    `inventory/find-dump/`. Least-magic, no frontmatter churn on thousands of shards.
  - **Alternative** (lighter-touch but per-file): honor a frontmatter `no_dense: true` /
    `index: {dense: false}` flag in the dense doc-selection. More general but writes the
    flag into every shard. Recommend the path-prefix default; expose the frontmatter flag
    later only if a second use-case appears.
- Provide a plugin/config opt-out to also exclude find-dump from **BM25** for users who
  don't want it searchable, but default = BM25-on.

## Q6 — Relationship to lane-a & the annex seam

- The two legs are complementary **by construction**: `git annex whereis` locates
  annex-managed keys; find-dump locates everything else on the drive. A future "where is X"
  query fuses `whereis` (annexed) + `zkm search` over find-dump (non-annex).
- **Keep them disjoint:** during the sweep, detect annex pointer files (symlinks resolving
  into an `annex/objects` / `.git/annex` object store) and **exclude** them from the
  find-dump listing (v1) — so an annexed file is never double-reported by both legs. (At 0
  annex drives today this is a thin guard, not a full integration; low priority — can trail.)
- Both legs emit the **same** `{scope: inventory.drive, value: <id>}` entity, so a fused
  query resolves both to the same drive label. The query-time fusion mechanism itself is
  out of scope for this plugin — lane-c's only obligation is that its output carries the
  drive id so fusion is *possible*.

---

## Decomposition into dispatchable executor sub-items

Sized for one Sonnet session each. Ids to be minted by the reviewer at dispatch. **All gated
on INV1+INV2 green** (INV3 gate). Ordering + dependencies noted.

### INV3a — [CENTRAL / core] dense-leg per-path opt-out
*(touches `src/zkm/embed.py` (+ `src/zkm/config.py`) → central per boundary rule #1; lives in
`~/src/zkm` ROADMAP/TODO, not the plugin.)*
- **Scope:** add a `dense_skip_prefixes` mechanism so the dense/embeddings leg skips docs
  whose `rel_path` starts with a configured prefix; default set includes `inventory/find-dump/`.
  BM25 unchanged.
- **RED test asserts:** build an index over a store containing (a) a normal doc and (b) a doc
  under `inventory/find-dump/…`; BM25 index includes BOTH `rel_path`s; the built `EmbedStore`
  `.paths` includes the normal doc but **NOT** the find-dump doc. `zkm index` still succeeds
  with no embed endpoint (graceful).
- **Deps:** none — independent of the plugin; can run in parallel with INV3b. Do this
  first/parallel so the dense blowup is impossible the moment shards land.

### INV3b — [plugin] find-dump sweep core (deterministic shard render)
- **Scope:** pure function over a *directory tree + drive id* → size-capped, deterministically
  packed, sorted rendered md shards `inventory/find-dump/<id>/NNNN.md` + per-drive summary md
  with the shared `scope:inventory.drive` entity, `last_swept`, file count, total bytes. No
  real mounts (fixture temp tree). Reuse INV1/INV2 render helpers where shared.
- **RED test asserts:** given a fixture tree, (1) a known filename token appears in some shard
  body; (2) every shard ≤ the byte/line cap; (3) re-render of the unchanged tree is
  **byte-identical** (idempotent → git no-op → no created paths returned); (4) inserting one
  file dirties only its directory's shard(s), not all shards; (5) summary md frontmatter
  carries `source: inventory`, the `scope:inventory.drive` entity, `last_swept`, file count.
- **Deps:** INV1+INV2 shipped (shared helpers). The heavy core; one full session.

### INV3c — [plugin] mount orchestration + online-set resolution
- **Scope:** enumerate candidate mount roots (`find_dump.roots`, sensible defaults), map a
  mounted path → drive id via read-only **UUID/label** match against the manifest `mount:`
  block (NO marker-file write — boundary), sweep ONLY the online set, skip+log unmatched
  mounts, leave absent drives' shards untouched, never raise on absence.
- **RED test asserts:** two fixture "drives" (temp dirs), one whose manifest record matches
  (via injected/fake uuid-or-label resolver) and one absent; only the present drive is swept;
  the absent drive's pre-existing shards are unchanged; no exception raised for the absent one;
  an unmatched mountpoint is skipped (logged), not errored.
- **Deps:** INV3b (consumes its sweep).

### INV3d — [plugin] annex-pointer exclusion (leg-disjointness) + staleness polish  *(optional/small)*
- **Scope:** exclude annex pointer files (symlinks resolving into an `annex/objects`-shaped
  store) from find-dump listings so lane-a and lane-c stay disjoint; ensure `last_swept`
  staleness is legible in the summary. Low priority (0 annex drives today) — may fold into
  INV3b if trivial; kept separate for sizing.
- **RED test asserts:** a fixture tree containing a symlink resolving into an
  `annex/objects/...` path is **excluded** from (or tagged in) the shard, while a normal file
  and a normal symlink are included.
- **Deps:** INV3b.

**Order:** `INV3a ∥ INV3b` → `INV3c` → `INV3d`. (3a and 3b parallel; 3c and 3d both need 3b.)

---

## HUMAN DECISIONS REQUIRED

*(Excludes the git-annex whole-disk-onboarding question — already routed to it-infra
routed:cfc1.)*

1. **Storage tier for very large drives.** Keep full listings in **git (T1)** for the
   line-level "when did this file move/vanish" temporal diff — accepting first-commit bloat
   (~8 MB per 100k-file drive, delta-cheap thereafter, but heavy at multi-million files) — OR
   for such giant drives put the raw listing in **annex + keep only a thin summary in git**
   (loses line-level temporal diff). Recommended default: **T1 git**; confirm the bloat
   trade-off / where the "too big for git" threshold sits.

2. **Cadence & dispatch surface.** find-dump as a **separate declared plugin**
   `inventory-finddump` (explicit, mount-gated `zkm convert inventory-finddump`; keeps the
   light manifest render fast) — **recommended** — vs. folded into `zkm convert inventory`
   behind a `find_dump.enabled` config gate.

3. **Mount-identity mechanism.** Confirm **read-only filesystem UUID/label** matching from
   the manifest `mount:` block (recommended — honors the "no write-back to drives" boundary).
   The alternative, a `.zkm-drive-id` marker file at the drive root, is **rejected** here
   because writing to a drive violates the plugin's scope fence — flagged in case the user
   wants to revisit that boundary specifically for an opt-in marker.

4. *(Lighter — design default, not blocking)* dense opt-out as a **config path-prefix skip**
   (recommended) vs. a general per-file frontmatter `no_dense` flag. Noted for awareness; the
   reviewer can default to the path-prefix without a user turn unless the user prefers the
   general flag.

---

## Gate reminder

INV3 (id:46b6) stays **GATED** until INV1 (id:82a2) + INV2 (id:5697) are green and pushed.
Do not dispatch INV3a–d until then. INV3a is central (core repo) even though it unblocks a
plugin lane — file it in `~/src/zkm`'s ledger, not the plugin's, per the boundary rule.

---

## Pilot calibration (2026-07-11 — external SSD `/dev/sda`, USB)

First real measurement (via `scripts/pilot-drive-count.sh`). Three subtrees:

| Subtree | Files | Est. listing | Character |
|---|---|---|---|
| `Manjaro` (1 TB ext4, full OS install) | **3,025,462** | 362 MB | rootfs — `home` 1.89M · `usr` 1.04M · `opt` 55k · `var` 30k |
| `Cee` (256 GB NTFS, Windows data) | **1,568,845** | 197 MB | software — `Program Files` 216k · `gcdev64` 109k · `Program Files (x86)` 108k · MiKTeX · msys64 |
| `Manjaro/home` only | **1,893,957** | ~230 MB | dev churn (see below) |

**home-only prune breakdown** (dominant noise): `.cache` 350k · `node_modules` 229k · `.cargo` 78k
· `.rustup` 49k · `site-packages` 42k · `.npm` 31k · `__pycache__` 20k · `.venv` 13k. Residual after
pruning ALL of those = **1,125,925** — still >1M.

**Calibration conclusions:**
1. **The ~1M-file annex threshold is well-calibrated** — every real partition measured sits at/above
   it, so T1-git-only (no escape hatch) would bloat. The annex-raw+thin-summary escape-hatch is
   **confirmed needed**, not hypothetical.
2. **These are system/software drives, not the media drives find-dump targets.** find-dump's value is
   locating movies/photos; pointing it at an OS or a Windows `Program Files` tree is mostly noise.
   → INV3b needs a **per-drive content-root(s)** config (index `home/tobias/Videos`, not all of `/usr`)
   AND a heavy default **prune-set**.
3. **Pruning helps but is insufficient alone** (home 1.9M → 1.1M) → content-roots + prune-set + annex
   escape-hatch are all warranted; none alone suffices.
4. **Calibrated default prune-set for INV3b:** `node_modules`, `.cache`, `.cargo`, `.rustup`, `.npm`,
   `site-packages`, `__pycache__`, `.venv`, `.git/` internals, `.mozilla`; plus system trees when a
   whole partition is swept: `Program Files*`, `Windows`, `$Recycle.Bin`, `System Volume Information`,
   `/usr`, `/var`, `/opt`, `/proc`, `/sys`. User-overridable per drive.

Net: **INV3b default = content-roots (opt-in per drive) + prune-set, T1-git shards; auto-fall-back to
annex-raw+thin-summary when a swept root still exceeds ~1M files / ~100 MB.**

## Prior art (surveyed 2026-07-11) — do NOT reinvent

The observed prune-set above is *noise data*, not a mechanism. Two distinct solved problems, each with a
mature reuse target:

**A. "Real files vs metafiles" (git objects, node_modules, caches) = the gitignore-aware walker.**
- **`ignore` crate** (BurntSushi/ripgrep) — a fast recursive directory iterator that respects `.gitignore`
  / `.ignore` / global ignore, skips `.git` and hidden by default; **`fd` is built on it**. This IS the
  canonical answer to "skip metafiles." → zkm reuse options: shell out to **`fd --type f`** / `rg --files`
  (already ignore-filtered + extremely fast on millions of entries), or pure-Python **`pathspec`** (the
  gitignore-matcher used by black/pre-commit — no new binary dep, slower).
- **`git ls-files`** inside a detected git repo → lists only TRACKED working files, never `.git/objects`.
  The precise answer to "git objects etc." Fold: on hitting a `.git` dir, index via `git ls-files`, skip the
  `.git/` internals entirely.

**B. "Catalog offline volumes → search which drive holds file X" = the disk-catalog genre (decades old).**
- **`dcat`** (CLI, closest to zkm) — one named catalog per volume, stored as **gzipped-JSON**, search a
  single catalog OR the whole collection by name/regex. Same shape as our per-drive-shards + summary.
- **GWhere / Basenji** (GTK), **VVV / Cathy / WhereIsIt / GCstar / DiskCatalogMaker / abeMeda** (GUI) —
  all: scan a volume, store its tree keyed by volume label, search offline across volumes, some extract
  EXIF/ID3 metadata. Validates the per-volume-keyed catalog + offline cross-volume search pattern.
- **`plocate` / `lolcate`** — fast filename-index (`updatedb` DB); "instant filename search" primitive.
  zkm already has BM25 over the shards = our search layer; these confirm filename-index is the right primitive.

**Decision for INV3b (supersedes the hand-rolled prune-set):**
1. **Walker + ignore = reuse gitignore semantics**, not a bespoke prune list. Prefer shelling out to `fd`
   (optional dep, graceful-degrade to `pathspec`+`os.walk` if absent) so `.git`/`node_modules`/caches/hidden
   are skipped by the same engine everything else uses; honor a repo's own `.gitignore` + a small zkm global-ignore.
2. **`git ls-files` for tracked-only listing inside repos** (never index `.git/objects`).
3. **Catalog model = per-volume, keyed by UUID/label** (dcat/VVV pattern — already our design), but stored as
   git-tracked md shards (for the temporal diff) instead of gzipped-JSON.
4. **Recalibration note:** my crude 1.9M→1.1M home prune only removed ~8 patterns; a real gitignore-aware
   walk (fd defaults + `git ls-files`) drops far more, so a *media-focused content-root* likely lands WELL
   under the ~1M threshold — the annex escape-hatch is then only for genuinely huge media libraries.

**RATIFIED 2026-07-11 — INV3b is a THIN `fd`-ADAPTER, not a cataloger.** Key realization: a disk-cataloger
does (scan+ignore) + (store+search), but **zkm already owns (store+search)** via its BM25 index + git store
+ `zkm search` — that layer is what fuses drive-contents with mail/messages, gives the git temporal diff, and
links to the lane-a drive entity. So we reuse ONLY the half zkm lacks — **scan+ignore = `fd`/`ripgrep --files`
(+ `git ls-files` inside repos)** — and keep zkm for the rest. Wrapping a full cataloger (dcat/Basenji) is
backwards: it duplicates zkm's store+search and most lack the ignore layer (the actual hard part). INV3b
therefore = **shell out to `fd --type f <content-roots>` (optional dep; graceful-degrade to pure-Python
`pathspec`+os.walk when absent) → render the already-filtered listing into git-tracked md shards keyed by
UUID/label**. No bespoke walker, ignore engine, or search engine is written — only glue + the renderer.
