#!/usr/bin/env bash
# INV3-PILOT — measure a real external drive's contents to choose the find-dump
# listing storage tier (T1 git shards vs. annex-raw + thin git summary).
#
# Usage:  scripts/pilot-drive-count.sh <dir> [<dir> ...]
# Example: scripts/pilot-drive-count.sh /run/media/$USER/MEDIA-2
#          scripts/pilot-drive-count.sh /mnt/Ell/Movies /mnt/Ell/Series   # content_roots only
#
# Read-only: it never writes to the drive (honors the no-write-to-drives fence).
# Reports, per directory: file count, an estimate of the git-tracked listing size
# (one `path\tsize\tmtime` line per file ~ path length + ~30 B), and the biggest
# top-level directories — so you can judge T1-git viability per design §Q2.
#
# The walk's listing is a temp file: set TMPDIR to a directory ON DISK for big
# drives (the default /tmp is tmpfs = RAM).
#
# Errors are never hidden: every path `find` could not read is counted and the
# first ones are printed; the directory is then marked INCOMPLETE and the script
# exits 1, because an undercount would silently skew the calibration.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <dir> [<dir> ...]" >&2
  exit 2
fi

fmt_bytes() { numfmt --to=iec --suffix=B "${1:-0}"; }

incomplete=0
for mnt in "$@"; do
  if [[ ! -d "$mnt" ]]; then
    echo "!! not a directory / not mounted: $mnt" >&2
    incomplete=1
    continue
  fi
  echo "=== $mnt ==="
  uuid="" label=""
  if src=$(findmnt -no SOURCE --target "$mnt"); then
    # btrfs subvolumes report `/dev/sdX1[/subvol]`; lsblk wants the bare device.
    dev=${src%%\[*}
    if ! uuid=$(lsblk -no UUID "$dev" | awk 'NR == 1'); then
      echo "  !! lsblk could not read UUID for $dev" >&2
    fi
    if ! label=$(lsblk -no LABEL "$dev" | awk 'NR == 1'); then
      echo "  !! lsblk could not read LABEL for $dev" >&2
    fi
  else
    echo "  !! findmnt could not resolve the device for $mnt" >&2
  fi
  echo "  fs UUID:  ${uuid:-<unknown>}"
  echo "  fs LABEL: ${label:-<unknown>}"

  # ONE walk to a temp file, then cheap text ops (avoids a per-dir find storm that
  # trips on huge trees). find's stderr goes to its own file so unreadable paths
  # are reported, not dropped.
  tmp=$(mktemp)
  errs=$(mktemp)
  find_rc=0
  find "$mnt" -type f -printf '%P\n' > "$tmp" 2> "$errs" || find_rc=$?
  nfiles=$(wc -l < "$tmp")
  nerrs=$(wc -l < "$errs")
  est_bytes=$(awk '{ b += length($0) + 30 } END { print b+0 }' "$tmp")
  echo "  files:            ${nfiles}"
  echo "  est. listing size: $(fmt_bytes "$est_bytes")  (git-tracked, pre-compression)"

  # Rough tiering hint (thresholds are advisory — confirm against design §Q2).
  if   (( nfiles >= 2000000 )); then hint="VERY LARGE — favour annex-raw + thin git summary";
  elif (( nfiles >= 300000 ));  then hint="LARGE — T1 git viable but watch first-commit size";
  else                               hint="OK for T1 git shards";
  fi
  echo "  tier hint:        ${hint}"

  echo "  biggest top-level dirs by file count:"
  # awk 'NR<=10' instead of head: it drains the pipe, so sort never gets SIGPIPE.
  awk -F/ '{ c[$1]++ } END { for (d in c) print c[d] "\t" d }' "$tmp" \
    | sort -rn | awk 'NR <= 10 { print "    " $0 }'

  if (( find_rc != 0 || nerrs > 0 )); then
    incomplete=1
    echo "  !! INCOMPLETE: find exited ${find_rc} with ${nerrs} error line(s); counts are a LOWER bound" >&2
    awk 'NR <= 10 { print "     " $0 }' "$errs" >&2
  fi
  rm -- "$tmp" "$errs"
  echo
done

exit "$incomplete"
