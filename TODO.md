# zkm-inventory TODO

Tactical ledger. Executor specs live in `ROADMAP.md` (single source of truth);
this file carries summary lines only. See core `id:e65e` for the umbrella item.

## Current

- [x] INV1 (id:82a2) — drives lane → `inventory/drives/<id>.md`, shipped v0.2.0. See ROADMAP.
- [x] INV2 (id:5697) — devices lane → `inventory/devices/<id>.md` + searchable status, shipped v0.2.0. See ROADMAP.
- [x] INV-FIX (id:86b5) — v1 correctness fixes: amender-clobber idempotence, per-record date, id validation, table escaping (Fable review). Shipped v0.3.0. See ROADMAP + docs/fable-session-review-2026-07-11.md.
- [x] INV3 (id:46b6) — find-dump drive-content index (lane-c). ALL sub-items shipped: INV3a
  (core id:8fb4, dense/amender per-path opt-out, zkm v0.17.0), INV3b v0.4.0 (`inventory-finddump`
  plugin, `fd`/`pathspec` scan+ignore adapter, git-tracked shards), INV3c v0.5.0 (mount
  orchestration — `mount: {uuid?, label?}` + `content_roots:` auto-detects the online mountpoint,
  offline drives skipped no-raise), INV3d v0.6.0 (git-annex pointer exclusion — leg-disjointness
  with the future `git annex whereis` seam; `git ls-files` tracked-only listing deferred as
  unnecessary given `fd`'s default `.gitignore`+hidden skip). Storage = T1-git shards (RATIFIED
  default) + prune globs; annex escape-hatch evidence-gated (still open, see INV3-PILOT). See
  ROADMAP.
- [ ] INV3-PILOT — measure a real HDD's file count/size (scripts/pilot-drive-count.sh) to CALIBRATE the annex flip-threshold + prune globs. HUMAN-run. Does NOT gate INV3b.

## Deferred

- git-annex redundancy-enrichment seam for the drives lane — dormant, gated on ≥2 annex-managed
  drives existing (0 today). Whole-disk annex-onboarding is the it-infra 3-2-1-backup meeting's
  call (core routed:cfc1). See ARCHITECTURE.md.

## Scope

Meeting: `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`.
Merges the drive lane of core `id:f22d` + the device-roster lane of core `id:d35e`.
