#!/usr/bin/env bash
# INV3-PILOT — measure a real external drive's contents to choose the find-dump
# listing storage tier (T1 git shards vs. annex-raw + thin git summary).
#
# Usage:  scripts/pilot-drive-count.sh <mount-point> [<mount-point> ...]
# Example: scripts/pilot-drive-count.sh /run/media/$USER/MEDIA-2
#
# Read-only: it never writes to the drive (honors the no-write-to-drives fence).
# Reports, per drive: file count, an estimate of the git-tracked listing size
# (one `path\tsize\tmtime` line per file ~ path length + ~30 B), and the biggest
# top-level directories — so you can judge T1-git viability per design §Q2.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <mount-point> [<mount-point> ...]" >&2
  exit 2
fi

fmt_bytes() { numfmt --to=iec --suffix=B "${1:-0}" 2>/dev/null || echo "${1:-0} B"; }

for mnt in "$@"; do
  if [[ ! -d "$mnt" ]]; then
    echo "!! not a directory / not mounted: $mnt" >&2
    continue
  fi
  echo "=== $mnt ==="
  uuid=$(lsblk -no UUID "$(findmnt -no SOURCE --target "$mnt" 2>/dev/null)" 2>/dev/null | head -1 || true)
  label=$(lsblk -no LABEL "$(findmnt -no SOURCE --target "$mnt" 2>/dev/null)" 2>/dev/null | head -1 || true)
  echo "  fs UUID:  ${uuid:-<unknown>}"
  echo "  fs LABEL: ${label:-<unknown>}"

  # Single pass: count files and sum (path-length + 30) as the listing-line estimate.
  read -r nfiles est_bytes < <(
    find "$mnt" -type f -printf '%P\n' 2>/dev/null \
      | awk '{ n++; b += length($0) + 30 } END { print n+0, b+0 }'
  )
  echo "  files:            ${nfiles}"
  echo "  est. listing size: $(fmt_bytes "$est_bytes")  (git-tracked, pre-compression)"

  # Rough tiering hint (thresholds are advisory — confirm against design §Q2).
  if   (( nfiles >= 2000000 )); then hint="VERY LARGE — favour annex-raw + thin git summary";
  elif (( nfiles >= 300000 ));  then hint="LARGE — T1 git viable but watch first-commit size";
  else                               hint="OK for T1 git shards";
  fi
  echo "  tier hint:        ${hint}"

  echo "  biggest top-level dirs by file count:"
  find "$mnt" -mindepth 1 -maxdepth 1 -type d -printf '%P\n' 2>/dev/null \
    | while IFS= read -r d; do
        c=$(find "$mnt/$d" -type f 2>/dev/null | wc -l)
        printf '%s\t%s\n' "$c" "$d"
      done | sort -rn | head -10 | sed 's/^/    /'
  echo
done
