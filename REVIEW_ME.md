# Human review queue <!-- budget: 15 min -->

Judgment calls encoded in red tests — confirm or correct the interpretation.
Max ~10 open boxes; the reviewer prunes resolved ones each review turn.

- [ ] **Manifest is source-of-truth; the `.md` is a rendered view.** Unlike most
  zkm content (md = source of truth), the inventory `.md` files are *derived* from the
  hand-authored YAML manifest — editing an asset means editing the manifest and
  re-converting, not editing the `.md`. Confirm this inversion is acceptable (it mirrors
  every other plugin's source→md flow; the manifest is a first-class hand-authored source).
  Encoded in: `test_rerun_is_idempotent`. (handoff 2026-07-11)

- [ ] **`id` is the dedup/idempotence key (not sha256).** Records are keyed by their
  stable `id` field; there is one manifest, not per-item source files, so re-running
  rewrites-in-place and is a git no-op when unchanged. Confirm `id` is the right key (vs.
  a content hash). Encoded in: `test_rerun_is_idempotent`. (handoff 2026-07-11)

- [ ] **Device `status` lives in BOTH tags and body.** So `zkm search dust-collecting`
  hits via BM25 whether it matches a tag or body text. Confirm dual placement is wanted
  (vs. a single canonical location). Encoded in:
  `test_dust_collecting_device_is_findable_by_status`. (handoff 2026-07-11)
