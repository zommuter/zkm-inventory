# Human review queue <!-- budget: 15 min -->
Judgment calls encoded in red tests — confirm or correct the interpretation.
Max ~10 open boxes; the reviewer prunes resolved ones each review turn.

## v1 handoff (2026-07-11)

- [ ] **`id` is the dedup/idempotence key (not sha256).** Records are keyed by their
  stable `id` field; there is one manifest, not per-item source files, so re-running
  rewrites-in-place and is a git no-op when unchanged. Confirm `id` is the right key (vs.
  a content hash). Encoded in: `test_rerun_is_idempotent`. (handoff 2026-07-11)

  Owner asked for a recommendation 2026-11-10. Reviewer view: keep `id`. A content hash
  changes on every edit, so each edit would read as delete+create: per-record git history
  (zkm's temporal index) breaks, amender sidecars keyed by path are orphaned, and
  `zkm search` results jump between file names. `id` is identity, the hash is version.
  The real weakness of `id`-keying is renames/removals leaving stale files, which INV6
  (id:d0a5) now covers. Still open: the owner decides.

## Handoff 2026-11-10

- [x] **INV6 prune also deletes the removed record's amender sidecars.** When a record
  leaves the manifest, its `<md>.amendments.json` (+ `.lock`) go with the md, so any NER
  or tag write-back for that asset is gone too. Alternative: keep sidecars as orphans for
  core `zkm gc` to sweep. Chosen: delete, since a sidecar for a non-existent md has no
  reader. Encoded in: `test_sidecars_of_pruned_record_are_removed_kept_ones_untouched`.

  Owner 2026-11-10 (relay human batch 1): delete with the md, as shipped in v0.8.0.

- [x] **INV5 ambiguous serial raises, aborting the whole finddump convert.** A `serial:`
  that matches two or more mounted partitions with no `label`/`uuid` is a `ValueError`
  naming the drive id, which stops the sweep of every other drive in that run too.
  Alternative: skip that one drive with a warning. Chosen: raise, matching the manifest
  strictness ruling (a config error should fail loudly). Encoded in:
  `test_serial_with_two_partitions_and_no_selector_raises`.

  Owner 2026-11-10 (relay human batch 1): raise and abort the run, consistent with the strict-manifest ruling.

- [x] **A failing `lsblk` reads as "every drive offline", silently.** Pre-existing design
  (`_enumerate_mounts` returns `[]` on any failure; INV5's `_enumerate_serials` is specced
  the same way, returning `{}`). A missing or broken `lsblk` therefore produces a sweep
  that changes nothing and says nothing, which conflicts with the owner's "never make a
  failing command look like success" rule. Keep (graceful degrade, design §Q3), or make
  enumeration failure loud? Not encoded in a test yet.

  Owner 2026-11-10 (relay human batch 1): make it loud. Specced as [ROUTINE] INV8 id:0a98 (tests/test_finddump_lsblk_loud.py, RED).

- [ ] **INV7 scan matches shapes, not values, and cannot see its own file.**
  `tests/test_published_generic.py` flags home/media-mount paths under a real-looking user
  name and UUID/16-hex serials with more than two distinct hex digits; it cannot recognise
  arbitrary disk serials (no fixed shape), and never spells out the real values (that would
  republish them). It also skips ITSELF, because its triangulation test spells out
  real-LOOKING examples on purpose: a real identifier pasted into that one file would be
  invisible to the guard. Acceptable as the guard (disk serials and that one file left to
  review), or narrow the self-skip to the triangulation lines?

- [ ] **id:003c (INV3-PILOT) was closed without an owner-accept marker.** A human-run,
  user-visible item needs an explicit dated `@owner-accepted:` line to count into the
  user-observable-close set that feeds the version bump (review.md 5c); the close carries
  only the prose "owner-closed". The deliverable IS present and verifiable (two pilot
  measurements recorded in `docs/inv3-lane-c-design.md`: 2026-07-11 SSD system partitions
  1.6M to 3.0M files, 2026-11-10 media HDD content roots 54,356 files / ~6.4 MB, threshold
  unchanged), so the review did not reopen it. It is excluded from this integrate's
  user-observable-close set. Confirm the close, or add the marker. (review
  relay-20261110-202900-570)

- [ ] **115 persisting relay-doctor findings present (not re-boxed); revisit when convenient** -- updated 2026-11-10; ids: id:ddb9, id:6ed1, id:2147, id:a760, id:f14e, id:2b4b, id:ba95, id:8a76, id:73c9, id:4224, id:2799, id:2e1f, id:82d7, id:8699, id:a26b, id:f1a4, id:d67f, id:9225, id:24be, id:a742, id:6065, id:db1d, id:3c5a, id:9298, id:adfe, id:dd62, id:62bb, id:1d70, id:5acf, id:ecce, id:9efd, id:678e; 81 without an id; see them in full: `~/.claude/skills/relay/scripts/relay-doctor.sh "$(pwd)"` (review.md 4b, owner-ratified 2026-10-08, decision 33) <!-- relay-doctor-persisting -->
