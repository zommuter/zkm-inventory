# Relay log <!-- merge=union; append-only — never edit or reorder past entries -->

## 2026-07-11 21:32 — reviewer (claude-opus-4-8, /meeting handoff)

Initial skeleton + handoff for **zkm-inventory** (v0.1.0 baseline), created from the
scope meeting `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md` (core
id:e65e). Skeleton: `plugin.yaml` (name `inventory`, `creates_dirs: [inventory]`, required
`manifest` config), `convert.py` stub (raises NotImplementedError — RED), `pyproject.toml`
(editable `zkm>=0.16,<1.0`, pyyaml + python-frontmatter), README/CLAUDE/ARCHITECTURE,
conftest sys.path shim, published-generic fixture `tests/fixtures/inventory.yaml`
(placeholder assets only — repo is PUBLIC), 8 red specs in `tests/test_inventory.py`, and
`@manual`/`@future` Gherkin in `features/inventory.feature`.

Two dispatchable ROUTINE items, both backed by red tests: **INV1 (id:82a2)** drives lane →
`inventory/drives/<id>.md` with `scope:inventory.drive` entities; **INV2 (id:5697)** devices
lane → `inventory/devices/<id>.md` with `scope:inventory.device` entities + searchable status.
One HARD gated fast-follow: **INV3 (id:46b6)** find-dump drive-content index (git-annex
independent; needs its own design pass before dispatch). One dormant seam: git-annex
redundancy enrichment for the drives lane, gated on ≥2 annex-managed drives (0 today).

Key boundary fixed at scope time: git-annex touches ONLY the drives lane's redundancy column,
and only for annex-managed content — the hardware roster and the manifest-driven drive map are
fully buildable today at 0 annex drives. sync ≠ backup (manifest owns `last_sync` freshness;
annex owns copy-count). Whole-disk annex-onboarding is the it-infra 3-2-1-backup meeting's call
(core routed:cfc1), not this repo's — this plugin observes the backup topology, never sets it.

Not budgeted this turn: implementation (INV1/INV2 are the executor's), INV3 design decomposition,
the annex enrichment seam (dormant).

## 2026-07-11 22:30 — executor (sonnet)

Worked id:82a2 (INV1) and id:5697 (INV2) — implemented `convert()`: loads the YAML manifest
(`config["manifest"]`, resolved against `store_path`; raises `FileNotFoundError` when absent),
renders `inventory/drives/<id>.md` and `inventory/devices/<id>.md` via a shared `_write_record`
helper (`_build_entities`/`_render_body` dispatch on `kind`) using `zkm.atomic.write_atomic`.
Drives get a `scope:inventory.drive` `type:drive` entity (+ `type:place` when `location` is
set) and a body table (label/capacity/purpose/data_classes/location/last_sync/offsite); devices
get a `scope:inventory.device` `type:device` entity, `status` in both `tags:` and the body table.
Idempotence: `_write_record` compares the rendered content against the existing file and skips
the write (returns `None`, excluded from the created-paths result) when unchanged — verified by
`test_rerun_is_idempotent`. All 8 red tests pass; full suite green; ruff clean.

Smoke-tested via the real CLI (`zkm init` + `zkm-config.yaml` with a top-level `inventory:`
section — NOT `plugins: {inventory: ...}`, per `StoreConfig.for_plugin`'s bare-name lookup —
+ `zkm convert inventory`) against the fixture manifest: both `inventory/drives/` and
`inventory/devices/` .md render correctly with the expected frontmatter/body. Observed (not
fixed, out of scope for this session): the zkm-ner amender that runs as part of `zkm convert`
picks up spurious `scope:body` entities from the rendered markdown table syntax (e.g. treating
the "Value"/"Location"/"Status" table-header cells as org/person mentions) and its write-back
then defeats CLI-level idempotence on a second `zkm convert inventory` (our own `_write_record`
idempotence — verified in isolation by the unit test with no amenders — is unaffected; the
churn is the amender rewriting the file between runs, a pre-existing NER-quality/amender
interaction, not an INV1/INV2 regression).

Bumped 0.1.0 → 0.2.0 (`pyproject.toml`, `plugin.yaml`, `PLUGIN_VERSION`), `uv lock`, tagged
`v0.2.0` in the same commit. Friction: none — the spec matched the red tests cleanly; the only
surprise was the `zkm-config.yaml` top-level-key convention (not nested under `plugins:`),
discovered during the CLI smoke test rather than from written docs.

## 2026-07-11 22:35 — reviewer (claude-opus-4-8, /meeting follow-up)

INV3 (id:46b6) design pass landed → `docs/inv3-lane-c-design.md`. Decomposed into INV3a
(CENTRAL — dense-leg per-path opt-out in core `src/zkm/embed.py`; the find-dump md shards would
otherwise blow the embed index — filed in `~/src/zkm` ledger, not here), INV3b (deterministic
size-capped shard sweep), INV3c (mount orchestration + read-only UUID/label online-set), INV3d
(annex-pointer exclusion, small). User decisions: packaging = SEPARATE plugin `inventory-finddump`;
mount-identity = read-only UUID/label (marker-file rejected — no-write-to-drives fence); dense
opt-out = config path-prefix. **Storage tier is GATED on an HDD-content pilot** (INV3-PILOT +
`scripts/pilot-drive-count.sh`) — measure a real drive's file count before choosing T1-git-shards
vs annex-raw+thin-summary. INV3b–d gated on that pilot; INV3a independent/dispatchable now. The
NER-amender-trips-on-md-tables finding (from the executor's CLI smoke test) is routed to zkm-ner.
A Fable pass will sanity-review this session's decisions.

## 2026-07-11 22:45 — reviewer (claude-fable-5 review, integrated by opus)

Fable red-team of the session (`docs/fable-session-review-2026-07-11.md`) confirmed the scope/design
decisions (KEEP) but found 4 REAL v1 correctness bugs the green tests miss → filed as INV-FIX
(id:86b5), ship-before-real-use: (#5) `_write_record` byte-compares a record-only render so amender
frontmatter write-backs are CLOBBERED next convert → churn cycle (verified src/zkm/amendments.py) —
this, NOT the NER-table bug alone, is the idempotence root cause; (#6a) `date` = manifest mtime stamped
on every record → editing one record rewrites ALL, destroying the per-record temporal signal; (#6b)
`record["id"]` raw → KeyError / `../` path escape / dup collision; (#6d) `|` in a value breaks the
table. Also: find-dump shards must skip the AMENDER leg too (id:63bb), not just the dense leg → INV3a
(core id:8fb4) extended with `amender_skip_prefixes`. Closed central id:f22d (subsumed by e65e).
Storage-tier opinion: T1-git default, flip to annex-raw+thin-summary at ~1M files / ~100 MB raw
listing, add per-drive prune/exclude globs; pilot should CALIBRATE the threshold, not GATE INV3b
(the shard renderer ships either way). Surfaced to the human for ratification.

## 2026-07-11 — executor (Sonnet)

Worked id:86b5 (INV-FIX) — fixed all 4 v1 correctness bugs the Fable review found, each with a
new RED test confirmed failing before the fix: `test_amender_frontmatter_survives_reconvert`
(bug #1, amender-clobber), `test_editing_one_record_changes_only_that_file` (bug #2, per-record
date), `test_missing_id_raises_clear_error` + `test_path_escaping_id_cannot_escape_lane_dir` +
`test_duplicate_ids_raise` (bug #3, id validation), `test_pipe_in_value_does_not_break_table`
(bug #4, table escaping). `_write_record` now reads any existing doc and preserves frontmatter
this plugin doesn't own (entities outside `scope:inventory.<kind>`, tags outside the devices
lane's fixed status vocabulary) before comparing/writing the merged result. Dropped the
manifest-mtime `date` entirely; a record now gets a `date` only if it explicitly supplies one.
`id` is now validated (required, no `/`/`\`/`..`, unique per lane) before use as a filename.
Table cells escape `|` and newlines. All 8 original tests still green, all 14 tests green,
ruff clean. Bumped to v0.3.0 (frontmatter output shape changed: `date` no longer stamped on
every record) and tagged. Friction: none — the 4 bugs and their fixes were each independently
verifiable against a single RED test; no ambiguity encountered.

## 2026-07-11 — executor (Sonnet)

Worked ROADMAP id:46b6 sub-item INV3b — find-dump sweep core, shipped as a second plugin
`inventory-finddump` in this repo's multi-doc `plugin.yaml` (the zkm-stt `stt`/`stt-wa`
pattern), module `finddump.py`. Per the RATIFIED design (`docs/inv3-lane-c-design.md`
§Prior art), this is a thin `fd`-adapter, not a cataloger: `_list_files()` shells out to
`fd --type f --strip-cwd-prefix` when `fd`/`fdfind` is on PATH (already `.gitignore`/
hidden/`.git`-aware), else falls back to a pure-Python `pathspec`-driven `os.walk` with a
small default ignore set (`.*`, `node_modules/`, `.cache/`, `__pycache__/`, `.venv/`,
`site-packages/`); zkm's existing BM25+git remains the catalog+search+temporal layer.
Wrote 9 RED tests first (`tests/test_finddump.py`, confirmed failing on
`ModuleNotFoundError: finddump` before implementing), all green after: a known filename
token is findable in a shard, `.git` internals + `node_modules` are excluded, a 2500-file
directory splits into >1 shard each under the ~2000-entry/~256 KB cap, an unchanged
re-sweep is a byte-identical no-op AND leaves `last_swept` untouched, inserting one file
dirties only its own directory's shard (locality-preserving packing anchored on the
top-level directory, per design §Q4), the per-drive summary carries `source:
inventory-finddump` + the shared `scope:inventory.drive` entity + `file_count`, a
configured root absent on disk is skipped gracefully (no raise, no partial shards
written), both `plugin.yaml` docs still discover (`inventory` + `inventory-finddump`
confirmed via `zkm.convert.list_plugins()`), and one optional test exercises the real
`fd` backend against the pathspec fallback (skipped — no `fd`/`fdfind` on this host).
Added `pathspec>=0.12` to `pyproject.toml` + regenerated `uv.lock`. `_validate_id` is
reused from `convert.py` (INV1/INV2 helper) for the finddump `drives:` config too.
`git ls-files` tracked-only listing was NOT implemented — deferred per the task's own
guidance, since `fd`'s default `.gitignore`+hidden skip already covers the git-objects
case for v1; left as a note for INV3c/INV3d if a real repo-inside-a-drive case demands
it. Bumped to v0.4.0 (new plugin/feature) across `pyproject.toml`, both `plugin.yaml`
docs, and `PLUGIN_VERSION` in both `convert.py` and `finddump.py`; tagged `v0.4.0`.
Full suite 23 passed / 1 skipped, ruff clean on `convert.py finddump.py tests/
conftest.py`. Friction: none of substance — the one subtlety was confirming core's
`_load_plugin_module` always loads `<plugin-dir>/convert.py` regardless of which
declared plugin name is invoked (the `module:` key in a non-primary doc is not yet
wired to dispatch, matching zkm-stt's `stt-wa` which is likewise only exercised via a
direct `import stt_wa` in its own tests, never through `zkm convert stt-wa`); this repo's
tests follow the same proven pattern (`import finddump as fd`, direct unit-level calls)
rather than assuming an unbuilt core dispatch path — a pre-existing core-level gap, out
of scope for this item.

## 2026-07-11 — reviewer (claude-opus-4-8, live-verify + fix, v0.4.1)

After the core `module:` dispatch gap was fixed (core id:3f86), I ran `inventory-finddump`
end-to-end via the REAL CLI (`zkm convert inventory-finddump` on a synthetic content-root) —
which the direct-import unit tests could not exercise. Two bugs those tests masked:
(1) `finddump.py` did `from convert import _validate_id` — works under conftest's sys.path shim
but ModuleNotFound's under real `spec_from_file_location` dispatch → inlined a self-contained
`_validate_id` (no sibling import). (2) `_write_summary` bumped `last_swept` on EVERY re-sweep
(its `existing.content == body` check is fragile across the frontmatter dumps→load round-trip),
so each no-op sweep produced a noise commit → replaced with a render-trial-using-prior-timestamp
+ byte-compare, so a true no-op leaves the file untouched. Strengthened
`test_resweep_unchanged_is_noop_and_last_swept_stable` to advance a faked clock between sweeps
(subclassed datetime so `now()` moves while `fromtimestamp()` still works) — it was false-green
because both sweeps landed in the same wall-clock second. Verified live: first convert ingests 2
files (`.git/objects` + `node_modules` skipped by the pathspec fallback), re-convert reports
"Converted 0 file(s)" with a clean tree. 22 passed + 1 skipped; ruff clean. Bumped 0.4.0 → 0.4.1
(patch: two shipped-bug fixes).
