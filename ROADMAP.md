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

- [ ] **INV3 — find-dump drive-content index (lane-c, fast-follow)** [HARD] 🚧 GATED <!-- id:46b6 -->
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
  - **INV3c** — mount orchestration + read-only UUID/label online-set resolution; sweep only online
    drives; absent drives left as last-known; never raise on absence.
  - **INV3d** — (small/optional) annex-pointer exclusion (leg-disjointness) + staleness legibility.

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

- [ ] **INV3-PILOT — measure real HDD contents to calibrate the annex flip-threshold + prune globs.**
  Mount ≥1 real external drive and measure file count + total listing size
  (`scripts/pilot-drive-count.sh <mount>`) to tune where T1-git-shards flip to
  annex-raw+thin-summary (default threshold ~1M files / ~100 MB) and which prune/exclude globs
  are worth it. HUMAN-run (needs a physical drive). **Calibration only — INV3b ships regardless**
  (T1-git is the ratified default). Feeds `docs/inv3-lane-c-design.md` §Q2.

## Deferred / dormant (not dispatchable yet)

- **git-annex redundancy enrichment for the drives lane** — read-only `git annex whereis`/`info`
  to add copy-count/location for the annex-managed subset, graceful-degrade if annex missing or
  drive offline. **Dormant: gated on ≥2 annex-managed drives existing** (0 today). Whole-disk
  annex-onboarding is the it-infra 3-2-1-backup meeting's decision (core routed:cfc1), not this
  repo's. Build only once the gate is met.
