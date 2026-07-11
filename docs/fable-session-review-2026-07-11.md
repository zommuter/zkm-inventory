# Fable red-team review — zkm-inventory design+build session (2026-07-11)

Fresh-eyes pass over the scope meeting (D1–D3e), the plugin repo at v0.2.0
(`/home/tobias/src/zkm/plugins/zkm-inventory/`), the INV3 lane-c design doc, and the
central ledger (ids f22d, d35e, e65e, 8fb4). Read-only; all claims below verified
against the files/commands cited. Tests: 8/8 pass (`uv run pytest`, 0.04s). Plugin
done-gate holds (HEAD == @{u} = be3c12a).

## Verdicts on the 8 decisions

### 1. Merge, no new ids (5ea3→f22d, 4279→d35e) — KEEP
Provenance + admit-rule landed in both items before inbox-done (verified
`~/src/zkm/TODO.md:70` and `:140`); fresh ids would have manufactured exactly the
TODO↔TODO drift the merge avoids. One loose end: **f22d is now fully subsumed by
e65e** (its entire drive-lane payload is the plugin) yet both stay open central items —
f22d should either close with a pointer or carry an explicit `gated on e65e ships`
marker, or it will drift/re-fire in every backlog sweep. d35e is fine (it legitimately
retains the broader BIM umbrella beyond the device roster).

### 2. Plugin over notes-convention — KEEP
Borderline for lanes a+b alone (a YAML→md renderer of hand-authored data mostly moves
*where* you hand-author), but three things tip it: typed `entities[]` in the γ schema,
a refreshable render pipeline, and above all lane-c (mount + `find` is a genuine
external source no notes convention can serve). The ARCHITECTURE.md "rejected
alternatives" section states this honestly. Sound.

### 3. git-annex boundary (D3a) — KEEP
sync≠backup (manifest owns `last_sync` freshness, annex owns copy-count redundancy) is
the correct partition; read-only `whereis`/`info` avoids a second instantly-stale
location log; reading the SAME named-remote registry as `zkm push`/`fetch` (id:998b)
avoids a private parallel registry. No objection.

### 4. Annex seam dormant (D3b) — KEEP
Textbook observe-before-preventing: 0 annex drives today means the enrichment code has
literally nothing to enrich; the ≥2 gate is cheap to check. Routing whole-disk
onboarding to it-infra is right — zkm as *observer* of backup topology, never its
setter, and the coupling is acknowledged in BOTH directions (routed:cfc1 outbound;
it-infra's ack came back as routed:50d7 in the inbox — verified). zkm is not dodging a
decision; the decision genuinely belongs to the 3-2-1-backup meeting.

### 5. Manifest = source, .md = rendered view — RECONSIDER
The inversion is acceptable *in principle* — it mirrors every plugin's source→md flow,
and the REVIEW_ME box frames it correctly. **But the implementation breaks zkm's
amendment contract, which is the operative half of "md is source of truth".**
CLAUDE.md: "DB-derived metadata (auto-tags, NER) **must be written back** to
frontmatter." `zkm.amendments` does exactly that (`amendments.py:455-490` merges into
frontmatter and `write_atomic`s the md). But `_write_record` (`convert.py:109`)
byte-compares the existing file against a *fresh* render — so the moment ANY amender
writes anything back, the next `zkm convert inventory`:
  1. sees bytes differ → rewrites, **clobbering the amendment**,
  2. reports the file as created/changed → amenders re-run → write back → goto 1.
Permanent non-converging churn, **independent of NER quality** — a perfectly correct
`place: example living room` entity triggers it just as surely as the table-header
garbage. The unit-level idempotence test passes only because it runs with no amenders.
Fix options (any one): compare against the fresh render *merged with* preserved
amended frontmatter; key idempotence on the source record (manifest-slice hash stored
in frontmatter) instead of whole-file bytes; or declare `inventory/**` amender-excluded
(weakest — gives up enrichment). This must be decided before lane-c, where the same
collision applies to thousands of shards.

### 6. v1 implementation — RECONSIDER (works as tested, four real smells)
- **(a) `date` = manifest mtime poisons the temporal index.** `date_str` is the
  manifest file's mtime, stamped into EVERY record (`convert.py:53`). Edit one drive's
  `last_sync` (or merely `touch` the manifest) → every record's `date` changes → **all
  N files rewrite**. This defeats per-record idempotence, makes every one-line edit an
  N-file commit, and destroys the very "git log = which asset changed when" signal the
  plugin exists to provide. Use a per-record date, or drop `date` from the
  change-comparison. No test catches this (there is no "edit one record → only that
  file changes" test).
- **(b) `id` is unvalidated and used raw as a filename.** `record["id"]` raises a bare
  mid-run KeyError on a missing id (after some files are already written); `out_dir /
  f"{rid}.md"` accepts `id: ../../x` (path escape out of `inventory/`) and silently
  last-write-wins on duplicate ids across records. One `_validate_id` (present,
  string, no separators, unique) fixes all three.
- **(c) the amendment-clobber cycle** — see #5.
- **(d) cosmetic:** a `|` in any field value breaks the rendered table row; missing
  `capacity_gb` renders "` GB`". Harmless but sloppy.
- **Test coverage:** the 8 tests cover the happy path, no-amender idempotence, and
  missing-manifest — a fair RED floor for two ROUTINE items. Gaps: none of (a)/(b)/(c)
  above, no empty-manifest test, no single-record-edit granularity test, no assertion
  on the first run's *returned* created list (only the re-run's `== []`), no
  `canonical` assertion, no unicode. (a) and (b) are the ones worth adding tests for.

### 7. INV3 lane-c design — KEEP, one significant gap
The design doc is the strongest artifact of the session: deterministic
locality-anchored shard packing (kills the "one insert dirties every shard" trap),
plain-lines-not-tables, per-drive summary carrying the shared drive entity, read-only
UUID/label identity (marker-file correctly rejected on the no-write fence), and the
dense-leg blowup identified and pre-solved as a central item (INV3a id:8fb4, filed in
the right ledger per boundary rule #1 — verified `TODO.md:145`). **Weakest link: Q5
excludes find-dump from the *dense* leg but says nothing about the *amender* leg.**
Per the amender-scoping contract (id:63bb), `zkm convert inventory-finddump` will pass
every created shard to zkm-ner → NER over millions of filename tokens (movie titles
are a person/org-mention minefield) = extraction cost blowup + garbage entities +
sidecar churn + the #5 clobber cycle at shard scale. Needs an `amender_skip_prefixes`
(or per-plugin amender opt-out) sibling to `dense_skip_prefixes` — arguably the same
central item as INV3a. Minor: the pilot script bakes advisory thresholds (300k/2M)
into code before the human decision it feeds — label them clearly as placeholders or
they'll be quoted as ratified later.

### 8. NER-table finding routed to zkm-ner — RECONSIDER (routing right, diagnosis incomplete)
The routing itself is correct and landed (verified: routed:fa25 in
`~/.claude/todo-inbox.md:101`, targeted `[zkm-ner]`, conforming one-liner) — pipe-table
header cells parsed as org/person mentions is a genuine zkm-ner precision bug whose fix
benefits every table-rendering plugin; changing inventory's rendering to dodge one
consumer's bug would be backwards. **But both executor and reviewer misdiagnosed the
idempotence break as a consequence of the NER bug.** It isn't: per #5, the churn cycle
survives a perfect NER. Fixing zkm-ner's table parsing removes the *garbage* entities
but the first *legitimate* write-back re-opens the loop. Inventory needs its own fix
(see #5) — file it in the plugin's ledger now, not after the ner fix "doesn't help".

## OPINION — storage tier for find-dump listings (HUMAN DECISION #1)

**Recommendation: T1 git shards as the default, with a per-drive flip to
annex-raw + thin-git-summary at ~1M files or ~100 MB estimated raw listing per drive
(whichever hits first).**

Why that threshold:
- Path listings delta- and zlib-compress extremely well (shared prefixes): ~100 MB raw
  ≈ 10–25 MB packed on first commit, and subsequent sweeps cost only churn lines. Below
  ~1M files the whole history stays comfortably inside what `~/knowledge` tolerates —
  and that repo has *already had* bloat surgery (memory: knowledge-.git-bloat,
  id:5636), so its headroom is not hypothetical.
- Above ~1M files the *temporal-diff value density collapses*: multi-million-file
  drives are camera dumps / backup trees whose line-level move history nobody will ever
  query, while the git, `status`, and BM25-tokenize costs keep scaling linearly. You'd
  be paying real repo weight for diff history of noise.
- BM25 doc-count is fine either way (~2000-entry shards → even 5M files ≈ 2.5k docs);
  the binding constraints are repo size and index/tokenize time, both roughly linear in
  listing bytes — hence a bytes/file-count threshold, not a doc-count one.

**Sharper lever the session missed: per-drive prune/exclude globs.** Most
multi-million-file counts come from a handful of directories (`node_modules`-shaped
trees, photo-cache dirs, backup mirrors of *other already-inventoried drives*). A
`find_dump.exclude` config gives you the T1-git benefit on the content you actually
want to locate, and may make the annex-raw escape hatch unnecessary entirely.
Cheaper than a second storage tier; decide it now.

**Is the pilot the right gate? Only half.** As a cheap measurement it's fine, and it's
correctly HUMAN-run. But gating **INV3b–d** on it over-blocks:
- The *default* (T1 git) and the *threshold policy* can — and should — be decided now;
  the pilot only calibrates whether any currently-owned drive exceeds the threshold.
- **INV3b (the deterministic shard renderer) is needed under BOTH outcomes** — even
  the annex-raw variant keeps a thin git summary, and the plausible resolution is
  "T1 default + per-drive escape", under which INV3b ships unchanged. Gating it wastes
  the sequencing.
- Building the annex-raw escape *before* a real drive exceeds the threshold would
  violate observe-before-preventing — the *same rule the session correctly applied to
  the annex seam (D3b)*. Consistency says: decide T1-git default now, dispatch INV3b
  (and INV3a, already ungated), run the pilot in parallel, and build the annex-raw
  path only when a real drive crosses the line.

## TOP 3 THINGS TO FIX/RECONSIDER

1. **The convert↔amender clobber cycle** (findings #5/#6c/#8): `_write_record`'s
   whole-file byte-compare destroys amender write-backs and creates a permanent
   rewrite/re-amend loop — misdiagnosed this session as an NER-quality issue. Decide
   the merge/keying fix (and its lane-c analog) before dispatching INV3b; the zkm-ner
   routing alone will not resolve it.
2. **Manifest-mtime `date` mass-rewrite** (#6a): a one-record edit (or a bare `touch`)
   rewrites every record's md, defeating per-record git temporal granularity — the
   plugin's own headline rationale. Per-record dating or date-excluded comparison; add
   the missing "edit one record → one file changes" test. Also harden `id`
   (missing/duplicate/path-separator).
3. **Un-gate INV3b and decide the storage default now** (opinion above): T1 git
   default + ~1M-files/100 MB per-drive annex flip + prune-glob config; pilot
   calibrates, doesn't gate. And extend INV3a's skip mechanism to the **amender leg**
   (find-dump shards must be NER-excluded, not just dense-excluded) — the biggest
   unpriced cost in the lane-c design.
