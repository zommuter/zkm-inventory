# Changelog

<!-- DERIVED at relay integrate from existing relay state (report.summary + worked ids) by
     relay/scripts/changelog-append.sh (id:b8fa). Newest release first; never hand-edit or
     reorder past buckets. RELEASE-bucketed by version (## vX.Y.Z -- DATE); the reviewer's bump
     at integrate (id:e647) supplies the version. Auto-onboarded on this repo's first release
     (id:7d20). Started from now; history is NOT backfilled. -->

## v0.8.1 -- 2026-11-10

- review: widened window to d33d1e6..HEAD (discharges id:e16e), verified d0a5/a124/3423/52cf/4654 genuine, suite 67 passed + ruff clean, bdd tier skipped (no runner), fixed stale ARCHITECTURE known-gap + README prune docs, drained TODO (e16e, 5225) (id:e16e,5225,d0a5,a124,3423,52cf,4654)

## v0.8.0 -- 2026-11-10

- INV6 d0a5: convert() prunes rendered records and sidecars removed from the manifest (id:d0a5)
