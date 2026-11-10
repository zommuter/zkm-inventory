# zkm-inventory TODO

## Current

- [x] [HARD] INV5 drive identity by hardware serial <!-- id:3423 -->
- [x] [ROUTINE] INV6 prune rendered records removed from the manifest <!-- id:d0a5 -->
- [x] [ROUTINE] INV7 scrub real identifiers from tracked tests/docs (public repo) <!-- id:a124 -->
- [x] [INPUT - decision] INV7b history rewrite: no (owner 2026-11-10), scrub current state only <!-- id:d142 -->

- [x] [HARD] relay review of the 2026-11-10 self-authored work from d33d1e6 -- DONE 2026-11-10: review relay-20261110-202900-570 widened its audit window to d33d1e6..HEAD and covered id:52cf/id:4654 (INV4), id:3423 (INV5) and id:003c (pilot) <!-- id:e16e -->
- [x] [HARD] reviewer: minor bump to v0.8.0 at the next integrate (INV5 serial matching is user-visible) -- DONE: tag v0.8.0 and pyproject 0.8.0 landed 2026-11-10 <!-- id:5225 -->
- [x] [INPUT - decision] push v0.8.0 + v0.8.1 (main + tags) to the public GitHub mirror? pool left them ratification-pending on fievel only (filed unattended by /wrapup relay-20261110-202900-570) <!-- id:b556 -->
- [ ] [ROUTINE] INV8 finddump: a failing lsblk is loud, never every-drive-offline <!-- id:0a98 -->
- [ ] [HARD] INV9 drive identity = hardware serial + partition number, linked across both plugins <!-- id:1441 -->
## Done

- [x] INV1 drives lane, shipped v0.2.0 <!-- id:82a2 -->
- [x] INV2 devices lane, shipped v0.2.0 <!-- id:5697 -->
- [x] INV-FIX v1 correctness fixes, shipped v0.3.0 <!-- id:86b5 -->
- [x] INV3 find-dump content index (`inventory-finddump`), shipped v0.4.0 to v0.6.0 <!-- id:46b6 -->
- [x] INV3-PILOT drive calibration pilots, closed v0.7.0 <!-- id:003c -->
- [x] INV4 device repurposing fields + roster, shipped v0.7.0 <!-- routed:ee27 --> <!-- id:52cf -->
- [x] INV4-WALK device manifest written and converted in the store <!-- id:4654 -->

## Parked

- [ ] @owner-gated git-annex redundancy enrichment for the drives lane, dormant until >=2 annex-managed drives exist <!-- id:e85b -->


