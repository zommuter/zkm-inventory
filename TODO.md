# zkm-inventory TODO

Tactical ledger. Executor specs live in `ROADMAP.md` (single source of truth);
this file carries summary lines only. See core `id:e65e` for the umbrella item.

## Current

- [x] INV1 (id:82a2) — drives lane → `inventory/drives/<id>.md`, shipped v0.2.0. See ROADMAP.
- [x] INV2 (id:5697) — devices lane → `inventory/devices/<id>.md` + searchable status, shipped v0.2.0. See ROADMAP.
- [ ] INV3 (id:46b6) — find-dump drive-content index (lane-c, fast-follow, HARD, gated on v1). See ROADMAP.

## Deferred

- git-annex redundancy-enrichment seam for the drives lane — dormant, gated on ≥2 annex-managed
  drives existing (0 today). Whole-disk annex-onboarding is the it-infra 3-2-1-backup meeting's
  call (core routed:cfc1). See ARCHITECTURE.md.

## Scope

Meeting: `../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`.
Merges the drive lane of core `id:f22d` + the device-roster lane of core `id:d35e`.
