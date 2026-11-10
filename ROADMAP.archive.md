# ROADMAP Archive

- [x] **INV1 — drives lane: render `inventory/drives/<id>.md`** [ROUTINE] <!-- id:82a2 -->
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

- [x] **INV2 — devices lane: render `inventory/devices/<id>.md`** [ROUTINE] <!-- id:5697 -->
  Same pipeline for the manifest's `devices:` list → `inventory/devices/<id>.md`. Frontmatter
  `source: inventory`; typed `entities[]` including `{scope: inventory.device, type: device,
  value: <id>, canonical: <model>}`; put `status` (in-use|idle|dust-collecting|retired) into
  BOTH a `tags:` entry and the rendered body so `zkm search dust-collecting` surfaces an idle
  device. Body table: model/kind/location/status/purpose. Keyed by `id`, idempotent. Reuse the
  INV1 helpers (shared record→md rendering). **Done-check:**
  `uv run pytest tests/test_inventory.py -k "device or dust"` green, then FULL suite green.

- [x] **INV-FIX — v1 correctness fixes (convert↔amender clobber, global date, id validation, table escaping)** [ROUTINE] <!-- id:86b5 -->
  Fable review (2026-07-11) found 4 real bugs the green v1 tests miss. Fix ALL, each with a NEW red test:
  1. **Amender-preserving idempotence (#5, the important one):** `_write_record` byte-compares a
     record-only render, so any amender frontmatter write-back (zkm-ner entities/tags) is CLOBBERED on
     the next `zkm convert inventory` → permanent rewrite/re-amend churn (violates the amendment
     contract — md is source of truth). Fix: read the existing doc, PRESERVE frontmatter the plugin
     doesn't own (amender-added `entities[]` beyond this plugin's own `scope:inventory.*`, extra
     `tags`), merge the plugin's own fields, and compare/write the MERGED result. RED: convert →
     simulate an amender adding a `scope:body` entity + a tag → convert again → the amender's
     entity/tag SURVIVE and the second convert returns no created paths.
  2. **Per-record temporal signal (#6a):** `date` is a single manifest-mtime value stamped on EVERY
     record, so editing one record (or `touch`ing the manifest) rewrites ALL records → destroys the
     per-record git temporal signal the plugin exists for. Fix: drop the manifest-mtime `date`
     (git IS the temporal index); use a per-record `date`/`added` field only if the manifest supplies
     one, else omit. RED: edit ONE record in a 2-record manifest → re-convert → exactly ONE file changes.
  3. **`id` validation (#6b):** `record["id"]` is used raw as a filename → KeyError mid-run if missing,
     `../` path escape, silent duplicate collision. Fix: require `id` (clear error naming the record),
     sanitize to a safe slug confined to the lane dir, and error on duplicate ids. RED: missing-id →
     clear error; `id: "../evil"` cannot escape `inventory/`; duplicate ids → error.
  4. **Table cell escaping (#6d):** a `|` (or newline) in a value breaks the markdown table. Fix:
     escape/replace `|` and newlines in cell values (or render a definition list). RED: a value with `|`
     renders without breaking the table and remains searchable.
  **Bump minor → 0.3.0** (frontmatter output shape changes: `date` dropped). Full suite green + ruff.

- [x] **INV3 — find-dump drive-content index (lane-c, fast-follow)** [HARD] <!-- id:46b6 -->
  Mount each drive + record its file listing (paths/sizes/mtimes) → searchable per-drive
  content so `zkm search "<title>"` names which drive holds a file. **git-annex INDEPENDENT**
  (covers bulk non-annex content). **Design pass DONE 2026-07-11 → `docs/inv3-lane-c-design.md`.**
  Decomposed into sub-items (dispatch order `INV3a ∥ INV3b → INV3c → INV3d`):
  - **INV3a** — [CENTRAL/core, in `~/src/zkm`] dense-leg per-path opt-out in `src/zkm/embed.py`
    (`dense_skip_prefixes`, default incl. `inventory/find-dump/`). Prereq: find-dump md shards
    must NOT hit the dense index. Independent of the pilot — dispatchable NOW. Tracked centrally.
  - [x] **INV3b** — find-dump sweep core = a THIN `fd`-ADAPTER (RATIFIED 2026-07-11): reuse `fd`/`ripgrep
    --files` (+ `git ls-files` inside repos) as the scan+ignore engine — NO bespoke walker/ignore/prune
    code (fd already skips `.git`/`node_modules`/caches/hidden + honors `.gitignore`). `fd` is an OPTIONAL
    dep, graceful-degrade to pure-Python `pathspec`+os.walk when absent. Render the already-filtered listing
    into deterministic, size-capped, locality-preserving md shards `inventory/find-dump/<id>/NNNN.md` +
    per-drive summary md carrying the shared `scope:inventory.drive` entity + `last_swept`. Idempotent
    (byte-identical re-render = git no-op). zkm's existing BM25+git is the catalog+search+temporal layer —
    NOT rebuilt. Config: per-drive `content_roots` (opt-in) so we index `Videos/`, not `/usr`. See
    `docs/inv3-lane-c-design.md` §Prior art (RATIFIED).
    **Shipped v0.4.0** as a second plugin `inventory-finddump` (multi-doc `plugin.yaml`, module
    `finddump.py`): `_list_files()` resolves `fd`/`fdfind` when on PATH, else a `pathspec`-driven
    `os.walk` fallback (hermetic tests force the fallback via `shutil.which` monkeypatch); config
    `drives: [{id, roots: [...]}]`, a root absent on disk is skipped gracefully (no raise);
    `_pack_shards()` groups entries by top-level directory (locality anchor) and splits only an
    oversized group, so one inserted file dirties only its own dir's shard; `_write_summary()`
    bumps `last_swept` only when a shard changed or the summary's non-timestamp fields differ,
    so a true no-op re-sweep leaves it untouched. `git ls-files` tracked-only listing NOT
    implemented (deferred — `fd`'s default `.gitignore`+hidden skip already covers the
    git-objects case for v1; left as a note for INV3c/INV3d if a real repo-inside-drive case
    needs it). Ordering: `INV3a` (core, dense-leg opt-out) still tracked separately in `~/src/zkm`.
  - [x] **INV3c** — mount orchestration + read-only UUID/label online-set resolution; sweep only online
    drives; absent drives left as last-known; never raise on absence. **Shipped v0.5.0**: a
    drive may declare `mount: {uuid?, label?}` + `content_roots: [<relpath>...]` instead of
    explicit `roots:`; `_enumerate_mounts()` (injectable — real impl shells out to
    `lsblk -o UUID,LABEL,MOUNTPOINT -P -n`, never requires root, degrades to `[]` on any
    failure) enumerates the online set once per `convert()` call, `_resolve_mount()` matches
    by `uuid` (exact) OR `label` (case-insensitive); an unmatched/offline drive is skipped
    (no raise, prior shards untouched); explicit `roots:` still bypasses mount resolution
    entirely (INV3b unchanged).
  - [x] **INV3d** — annex-pointer exclusion (leg-disjointness). **Shipped v0.6.0**:
    `_is_annex_pointer_symlink()` detects a symlink whose raw `os.readlink()` target
    contains an `annex/objects` path segment (relative OR absolute, target need NOT
    exist — a broken pointer on a drive without the annex object store present is
    still recognized and excluded); `_build_entry()` applies it as a single
    backend-agnostic post-filter shared by both `_list_files_fd()` and
    `_list_files_pathspec()`, so behavior is identical regardless of which scan
    backend surfaced the path (`fd --type f --type l` now explicitly requests
    symlinks so the filter has something to see on that backend too). A NORMAL
    symlink to a regular (non-annex) file is still included. `git ls-files`
    tracked-only listing (the ROADMAP's optional secondary) is DEFERRED, not
    built: `fd`'s default `.gitignore`+hidden-dir skip (and the pathspec
    fallback's matching `.*` rule) already excludes `.git` internals, so a
    tracked-only mode would add complexity (a nested-git-repo detection pass)
    for no behavioral gain over what's already shipped — revisit only if a real
    repo-inside-drive case needs finer-grained tracked/untracked distinction.
    Staleness legibility (the ROADMAP's other optional secondary) was not
    scoped by this session's dispatch — `last_swept` on the per-drive summary
    already carries the freshness signal; a dedicated staleness UI/warning is
    left for a future item if wanted.

  **Decisions (this session):** packaging = a SEPARATE plugin `inventory-finddump` (multi-doc
  `plugin.yaml`, `zkm convert inventory-finddump`) so the light manifest render stays fast;
  mount-identity = read-only filesystem UUID/label (NO marker-file — honors the no-write-to-drives
  fence); dense+amender opt-out = config path-prefix skip (core INV3a id:8fb4). **Storage tier =
  T1 git-tracked shards — RATIFIED DEFAULT (2026-07-11)** + per-drive prune/exclude globs; the
  annex-raw+thin-summary path is an EVIDENCE-GATED escape-hatch, built ONLY if a real drive exceeds
  ~1M files / ~100 MB raw listing (Fable review). **INV3b (the shard renderer) is UN-GATED** — it
  ships identically under either storage outcome; gating it on the pilot would itself violate
  observe-before-preventing. Only the annex escape-hatch waits on evidence. Dispatch order once
  INV3a lands: **INV3b (un-gated now that v1 ✅) → INV3c → INV3d**; the pilot merely CALIBRATES the
  flip-to-annex threshold + prune globs, it does not gate.

## Pilot (CALIBRATES the annex threshold — does NOT gate INV3b)
- [x] **INV3-PILOT — measure real HDD contents to calibrate the annex flip-threshold + prune globs.** <!-- id:003c -->
  Mount ≥1 real external drive and measure file count + total listing size
  (`scripts/pilot-drive-count.sh <mount>`) to tune where T1-git-shards flip to
  annex-raw+thin-summary (default threshold ~1M files / ~100 MB) and which prune/exclude globs
  are worth it. HUMAN-run (needs a physical drive). **Calibration only — INV3b ships regardless**
  (T1-git is the ratified default). Feeds `docs/inv3-lane-c-design.md` §Q2.
  - **Done 2026-11-10** (owner-closed): two pilots recorded in `docs/inv3-lane-c-design.md`:
    2026-07-11 SSD system partitions (1.6M to 3.0M files: annex escape-hatch needed) and 2026-11-10
    media HDD content roots (54,356 files / ~6.4 MB: T1 git). Threshold unchanged.

## Open items (handoff 2026-11-10)
- [x] [HARD] **INV5 — finddump drive identity by hardware serial** <!-- id:3423 -->
  - **Acceptance**: a drive's `mount:` block accepts an optional `serial:` (the disk's
    `ID_SERIAL_SHORT`). A partition inherits its parent disk's serial. With `serial:` set,
    only partitions on that disk are candidates; `label` (case-insensitive) or `uuid` then
    picks one, either suffices; with neither, exactly one mounted candidate is used and two or
    more raise `ValueError` naming the drive id. A serial with no mounted candidate (or no
    candidate matching label/uuid) is offline: skipped, no raise, prior shards untouched.
    Without `serial:` matching is unchanged (uuid OR label). The summary frontmatter records
    `disk_serial` for every mount-resolved drive whose serial is known.
  - **Design**: owner ruling 2026-11-10, ARCHITECTURE.md §Drive identity. Keep
    `_enumerate_mounts()` returning `(uuid, label, mountpoint)` triples (existing tests pin
    it); add `_enumerate_serials() -> dict[Path, str]` (mountpoint → disk serial, one
    read-only `lsblk -o NAME,PKNAME,SERIAL,MOUNTPOINT -P -n`), monkeypatched to `{}` by an
    autouse conftest fixture so no test shells out.
  - **Tests**: `tests/test_finddump_serial.py` (`# roadmap:3423`), currently RED.
  - **Done-check**: `pytest tests/test_finddump_serial.py` then the FULL suite + ruff.
  - **Context**: `finddump.py` `_enumerate_mounts`/`_resolve_mount`/summary render;
    `plugin.yaml` inventory-finddump config description. Origin: core id:3423, it-infra id:a28d.

- [x] [ROUTINE] **INV6 — prune rendered records removed from the manifest** <!-- id:d0a5 -->
  - **Acceptance**: after rendering, `convert()` deletes every `inventory/{drives,devices}/<id>.md`
    whose `id` is not in the manifest AND whose frontmatter `source` is `inventory`, plus that
    md's `<md>.*` sidecar files (`.amendments.json`, its `.lock`). Files without
    `source: inventory` are never touched. Deleted paths are included in the returned list
    (so core's scoped `git add` stages the removal). `inventory/devices.md` is deleted too when
    the manifest has no devices and no `complete_as_of`. A renamed id = old file removed, new
    file written. An unchanged manifest still returns `[]`.
  - **Tests**: `tests/test_inventory_prune.py` (`# roadmap:d0a5`), currently RED.
  - **Done-check**: `pytest tests/test_inventory_prune.py` then the FULL suite + ruff.
  - **Context**: `convert.py` `convert()`; ARCHITECTURE.md §Known gap. Never prune inside
    `inventory/find-dump/` (finddump's dir, different plugin).

- [x] [ROUTINE] **INV7 — scrub real identifiers from tracked tests and docs** <!-- id:a124 -->
  - **Acceptance**: no tracked file contains the owner's user name, a real filesystem UUID
    or a real disk serial. Replace them with obvious placeholders that keep every assertion
    meaning the same: `tests/test_finddump.py::test_enumerate_mounts_real_lsblk_parsing`
    (UUIDs and `/run/media/<user>/…` paths in the canned lsblk transcript AND its asserts,
    changed together), `docs/fable-session-review-2026-07-11.md` and
    `docs/inv3-lane-c-design.md` (home-directory paths). The test must still pass unchanged
    in what it checks (parsing shape, unmounted rows dropped).
  - **Tests**: `tests/test_published_generic.py` (`# roadmap:a124`), currently RED: greps
    tracked files for the owner's identifiers.
  - **Done-check**: `pytest tests/test_published_generic.py` then the FULL suite + ruff.
  - **Context**: this repo is PUBLIC. Rewriting already-published history is NOT part of this
    item; that is the owner decision id:d142.

- [x] [INPUT - decision] **INV7b — rewrite published history to drop the real identifiers?** Owner 2026-11-10: no history rewrite; scrub the current state only (INV7), the old commits may keep it. <!-- id:d142 -->
  - **Question for the owner**: the identifiers INV7 scrubs from HEAD are already on GitHub in
    older commits (the lsblk test transcript since v0.5.0, two docs since 2026-07-11).
    Rewrite and force-push history, or accept them as public? Force-pushing a published repo
    breaks any existing clone.
