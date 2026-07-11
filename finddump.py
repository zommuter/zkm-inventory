"""zkm-inventory — inventory-finddump: sweep drive content-roots into shards.

Second plugin shipped from this repo (multi-doc ``plugin.yaml``, the zkm-stt
``stt``/``stt-wa`` pattern) — ROADMAP INV3b. **Thin `fd`-adapter, not a
cataloger** (RATIFIED 2026-07-11, ``docs/inv3-lane-c-design.md`` §Prior art):
zkm already owns the catalog+search+temporal layer via its BM25 index + git
store; this module reuses only the half zkm lacks — scan+ignore — by shelling
out to `fd` (optional dep, graceful-degrade to pure-Python ``pathspec`` +
``os.walk`` when absent). No bespoke walker/ignore engine/search engine is
written here, only glue + the shard renderer.

Config: ``drives: [{id: <drive-id>, roots: [<mounted path>, ...]}, ...]`` for
explicit mount paths (INV3b), OR ``drives: [{id, mount: {uuid?, label?},
content_roots: [<relpath>...]}, ...]`` for automatic online-drive detection
(INV3c) — the currently-mounted filesystems are enumerated (read-only
UUID/label, no marker-file write-back) and matched against ``mount:`` to find
the drive's live mountpoint; ``content_roots`` (optional — omit to sweep the
whole mountpoint) are then resolved relative to it. A drive with explicit
``roots:`` always uses them directly, bypassing mount resolution entirely. A
configured root/drive that is not currently online (path absent on disk, or no
mounted filesystem matches its ``mount:`` block) is skipped gracefully —
never raised, prior shards left untouched (last-known).

Idempotence (design §Q4): entries are sorted, shards are packed
deterministically (grouped by top-level directory under the root, split only
when a group exceeds the size/line cap), and mtimes are rendered at a fixed
ISO-seconds resolution so sub-second jitter never produces a spurious diff. A
re-sweep of an unchanged tree writes nothing and reports no created paths; the
per-drive summary's ``last_swept`` is bumped only when something actually
changed (never on a true no-op re-sweep).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import frontmatter
import pathspec

from zkm.atomic import write_atomic

PLUGIN_NAME = "inventory-finddump"
PLUGIN_VERSION = "0.6.0"


def _validate_id(record: dict, kind: str, seen_ids: set[str]) -> str:
    """Validate and return ``record["id"]``; raise ValueError on any problem.

    Self-contained copy of the INV1/INV2 helper (ROADMAP id:86b5) — a plugin
    module loaded by file path via ``spec_from_file_location`` cannot ``import
    convert`` (its sibling is not on ``sys.path`` under real CLI dispatch), so
    this must not depend on ``convert.py``.
    """
    rid = record.get("id")
    if rid is None or not str(rid).strip():
        raise ValueError(f"inventory-finddump: {kind} record missing required 'id': {record!r}")
    rid = str(rid).strip()
    if "/" in rid or "\\" in rid or ".." in rid:
        raise ValueError(
            f"inventory-finddump: {kind} id {rid!r} is not a safe slug (no '/', '\\', '..')"
        )
    if rid in seen_ids:
        raise ValueError(f"inventory-finddump: duplicate {kind} id {rid!r}")
    seen_ids.add(rid)
    return rid

# Shard packing budget (design §Q1/§Q4): bounded md size, natural git-diff
# granularity. A group (top-level directory) exceeding either limit is split
# into consecutive sub-shards.
_SHARD_MAX_ENTRIES = 2000
_SHARD_MAX_BYTES = 256 * 1024

# Pure-Python fallback ignore-set (gitignore semantics via `pathspec`), used
# only when `fd`/`fdfind` is not on PATH. ``.*`` covers hidden files/dirs
# (including ``.git``) at any depth, matching `fd`'s default hidden-skip.
_DEFAULT_IGNORE_PATTERNS = [
    ".*",
    "node_modules/",
    ".cache/",
    "__pycache__/",
    ".venv/",
    "site-packages/",
]


def convert(store_path: Path, config: dict, *, progress=None) -> list[Path]:
    """Sweep each configured drive's online roots into find-dump md shards.

    Returns only the paths that were newly created or changed (git-no-op
    contract) — an unchanged re-sweep returns ``[]``.
    """
    drives = config.get("drives") or []
    created: list[Path] = []
    total = len(drives)
    seen_ids: set[str] = set()
    mounts: list[tuple[str | None, str | None, Path]] | None = None

    for idx, drive in enumerate(drives):
        drive_id = _validate_id(drive, "drive", seen_ids)
        if progress:
            progress(idx, total, drive_id)

        roots = _resolve_drive_roots(drive)
        if roots is None:
            # `mount:`-configured drive with no currently-matching mounted
            # filesystem (drive offline) — never raise, never touch its
            # existing shards (design §Q3/§Q4: absent drive = last-known).
            # Resolve the online set lazily and only once per convert() call.
            if mounts is None:
                mounts = _enumerate_mounts()
            mountpoint = _resolve_mount(drive, mounts)
            if mountpoint is None:
                continue
            content_roots = drive.get("content_roots")
            if content_roots:
                roots = [mountpoint / cr for cr in content_roots]
            else:
                roots = [mountpoint]

        online_roots = [r for r in roots if r.exists()]
        if not online_roots:
            # Drive not currently mounted — never raise, never touch its
            # existing shards (design §Q3/§Q4: absent drive = last-known).
            continue

        entries: list[tuple[str, int, int]] = []
        seen_rel: set[str] = set()
        for root in online_roots:
            for rel, size, mtime in _list_files(root):
                if rel in seen_rel:
                    continue
                seen_rel.add(rel)
                entries.append((rel, size, mtime))
        entries.sort(key=lambda e: e[0])

        shard_changed, shard_names = _render_drive_shards(store_path, drive_id, entries)
        created.extend(shard_changed)

        summary_path = _write_summary(
            store_path, drive_id, entries, shard_names, shards_changed=bool(shard_changed)
        )
        if summary_path is not None:
            created.append(summary_path)

    return created


# ── INV3c: mount orchestration + online-set resolution ──────────────────────


def _resolve_drive_roots(drive: dict) -> list[Path] | None:
    """Explicit `roots:` (INV3b style) as an override/fallback.

    Returns the configured roots verbatim when present, else ``None`` to
    signal the caller should fall back to `mount:`-based auto-resolution
    (INV3c) instead.
    """
    roots_cfg = drive.get("roots")
    if roots_cfg:
        return [Path(r) for r in roots_cfg]
    return None


def _enumerate_mounts() -> list[tuple[str | None, str | None, Path]]:
    """Read-only enumeration of currently-mounted filesystems.

    Returns a list of ``(uuid, label, mountpoint)`` triples for every
    block device `lsblk` reports as currently mounted (rows with an empty
    ``MOUNTPOINT`` — i.e. not mounted — are omitted). Implemented via
    ``lsblk -o UUID,LABEL,MOUNTPOINT -P -n``, a read-only query that never
    requires root and never writes to any drive (honors the plugin's
    no-write-back-to-drives boundary, design §Q3).

    Never raises: any failure (missing `lsblk`, non-Linux host, parse
    error) yields an empty list rather than blocking a sweep — mount
    orchestration must degrade gracefully, exactly like an absent drive.
    This function is deliberately injectable (tests monkeypatch it wholesale
    with fixture triples) so the suite never shells out to real `lsblk` or
    touches real mounts.
    """
    lsblk_bin = shutil.which("lsblk")
    if not lsblk_bin:
        return []
    try:
        proc = subprocess.run(
            [lsblk_bin, "-o", "UUID,LABEL,MOUNTPOINT", "-P", "-n"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    results: list[tuple[str | None, str | None, Path]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        kv: dict[str, str] = {}
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        for field in fields:
            key, sep, value = field.partition("=")
            if sep:
                kv[key] = value
        mountpoint = kv.get("MOUNTPOINT") or ""
        if not mountpoint:
            continue
        results.append((kv.get("UUID") or None, kv.get("LABEL") or None, Path(mountpoint)))
    return results


def _resolve_mount(
    drive: dict, mounts: list[tuple[str | None, str | None, Path]]
) -> Path | None:
    """Match *drive*'s `mount:` block against the enumerated online set.

    Matches by ``uuid`` (exact) OR ``label`` (case-insensitive) — either
    identifier suffices. Returns the matching mountpoint, or ``None`` when
    no currently-mounted filesystem matches (drive offline) — the caller
    treats that as "skip gracefully", never as an error.
    """
    mount_cfg = drive.get("mount") or {}
    want_uuid = mount_cfg.get("uuid")
    want_label = mount_cfg.get("label")
    if not want_uuid and not want_label:
        return None
    for uuid, label, mountpoint in mounts:
        if want_uuid and uuid and uuid == want_uuid:
            return mountpoint
        if want_label and label and label.lower() == str(want_label).lower():
            return mountpoint
    return None


# ── scanner: fd backend / pathspec fallback ─────────────────────────────────


def _resolve_backend() -> str:
    if shutil.which("fd") or shutil.which("fdfind"):
        return "fd"
    return "pathspec"


def _list_files(root: Path, backend: str | None = None) -> list[tuple[str, int, int]]:
    """Return ``(relpath, size, mtime_epoch)`` for every real file under *root*.

    Prefers shelling out to `fd` (already `.gitignore`/hidden/`.git`-aware);
    falls back to a pure-Python `pathspec`-driven `os.walk` when `fd`/`fdfind`
    is not on PATH. Both backends apply the same skip semantics.
    """
    resolved = backend or _resolve_backend()
    if resolved == "fd":
        fd_bin = shutil.which("fd") or shutil.which("fdfind")
        if fd_bin:
            return sorted(_list_files_fd(root, fd_bin))
    return sorted(_list_files_pathspec(root))


def _is_annex_pointer_symlink(path: Path) -> bool:
    """True iff *path* is a git-annex pointer symlink (design §Q6, INV3d).

    git-annex represents annexed file content as a symlink whose target
    resolves through an ``annex/objects`` path segment (bare repos use
    ``annex/objects``, working trees ``.git/annex/objects``) into the annex
    object store. Detected via the RAW ``os.readlink`` target string — never
    via ``Path.resolve()``/``.exists()`` — so a **broken** annex pointer (the
    annex object store not present on this drive/host) is still recognized
    and excluded; only lane-a (the future `git annex whereis` seam) is
    responsible for annexed content, never lane-c (find-dump). Works for
    both relative and absolute targets. Returns ``False`` (never raises) for
    a non-symlink, an unreadable symlink, or a plain non-annex symlink
    (including a broken one) — those are left to the caller's normal
    stat-based inclusion/exclusion.
    """
    try:
        target = os.readlink(path)
    except OSError:
        return False
    target_posix = target.replace(os.sep, "/")
    return "annex/objects" in target_posix


def _build_entry(root: Path, rel: str) -> tuple[str, int, int] | None:
    """Build a ``(relpath, size, mtime_epoch)`` entry for *rel* under *root*.

    Shared by both scan backends (fd + pathspec) so the git-annex-pointer
    exclusion (INV3d) is applied IDENTICALLY regardless of which backend
    surfaced the path — `fd --type f` may or may not surface a symlink
    depending on flags, so this post-filter is the single source of truth,
    not a backend-specific detail. Returns ``None`` when the entry should be
    dropped: it is an annex pointer symlink (excluded on detection alone,
    never merely because a broken target fails to stat), or the path is
    otherwise unreadable (broken non-annex symlink, permission error, race
    with a deleted file).
    """
    full = root / rel
    if _is_annex_pointer_symlink(full):
        return None
    try:
        st = full.stat()
    except OSError:
        return None
    return (rel, st.st_size, int(st.st_mtime))


def _list_files_fd(root: Path, fd_bin: str) -> list[tuple[str, int, int]]:
    proc = subprocess.run(
        [fd_bin, "--type", "f", "--type", "l", "--strip-cwd-prefix"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    results: list[tuple[str, int, int]] = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        rel = rel.replace(os.sep, "/")
        entry = _build_entry(root, rel)
        if entry is not None:
            results.append(entry)
    return results


def _list_files_pathspec(root: Path) -> list[tuple[str, int, int]]:
    spec = pathspec.PathSpec.from_lines("gitignore", _DEFAULT_IGNORE_PATTERNS)
    results: list[tuple[str, int, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        keep = []
        for d in dirnames:
            rel = (rel_dir / d).as_posix() if str(rel_dir) != "." else d
            if spec.match_file(rel + "/"):
                continue
            keep.append(d)
        dirnames[:] = sorted(keep)

        for f in sorted(filenames):
            rel = (rel_dir / f).as_posix() if str(rel_dir) != "." else f
            if spec.match_file(rel):
                continue
            entry = _build_entry(root, rel)
            if entry is not None:
                results.append(entry)
    return results


# ── shard packing + rendering ────────────────────────────────────────────────


def _shard_line(relpath: str, size: int, mtime_epoch: int) -> str:
    mtime_iso = datetime.fromtimestamp(mtime_epoch).replace(microsecond=0).isoformat()
    return f"{relpath}\t{size}\t{mtime_iso}"


def _group_key(relpath: str) -> str:
    """Top-level directory a path lives under (design §Q1/§Q4 locality anchor).

    Root-level files (no subdirectory) share the "" group, sorted first.
    """
    parts = relpath.split("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _pack_shards(entries: list[tuple[str, int, int]]) -> list[str]:
    """Deterministically pack entries into shard body strings.

    Grouped by top-level directory (sorted), each group's entries (sorted by
    path) are split into size/line-capped chunks in order. Because grouping +
    ordering depend only on which top-level directories exist (not on the
    exact file set within an unaffected group), inserting one file into an
    existing, under-cap group changes only that group's chunk(s) — it never
    shifts shard numbering for other groups.
    """
    groups: dict[str, list[tuple[str, int, int]]] = {}
    for entry in entries:
        groups.setdefault(_group_key(entry[0]), []).append(entry)

    shard_bodies: list[str] = []
    for key in sorted(groups.keys()):
        group_entries = sorted(groups[key], key=lambda e: e[0])
        chunk_lines: list[str] = []
        chunk_bytes = 0
        for entry in group_entries:
            line = _shard_line(*entry)
            line_bytes = len(line.encode("utf-8")) + 1
            if chunk_lines and (
                len(chunk_lines) >= _SHARD_MAX_ENTRIES
                or chunk_bytes + line_bytes > _SHARD_MAX_BYTES
            ):
                shard_bodies.append("\n".join(chunk_lines) + "\n")
                chunk_lines = []
                chunk_bytes = 0
            chunk_lines.append(line)
            chunk_bytes += line_bytes
        if chunk_lines:
            shard_bodies.append("\n".join(chunk_lines) + "\n")

    return shard_bodies


def _render_drive_shards(
    store_path: Path, drive_id: str, entries: list[tuple[str, int, int]]
) -> tuple[list[Path], list[str]]:
    """Write ``inventory/find-dump/<drive_id>/NNNN.md`` shards; return
    (changed paths, ordered shard filenames)."""
    shard_dir = store_path / "inventory" / "find-dump" / drive_id
    shard_dir.mkdir(parents=True, exist_ok=True)

    bodies = _pack_shards(entries)
    changed: list[Path] = []
    names: list[str] = []
    for i, body in enumerate(bodies):
        name = f"{i:04d}.md"
        names.append(name)
        path = shard_dir / name
        if path.exists() and path.read_text(encoding="utf-8") == body:
            continue
        write_atomic(path, body)
        changed.append(path)

    return changed, names


def _write_summary(
    store_path: Path,
    drive_id: str,
    entries: list[tuple[str, int, int]],
    shard_names: list[str],
    *,
    shards_changed: bool,
) -> Path | None:
    """Write the per-drive summary md; return its path iff it changed.

    ``last_swept`` is bumped ONLY when something actually changed (a shard
    changed, or the summary's own non-timestamp fields differ) — an unchanged
    re-sweep must leave the prior ``last_swept`` untouched (design §Q4).
    """
    summary_path = store_path / "inventory" / "find-dump" / f"{drive_id}.md"

    file_count = len(entries)
    total_bytes = sum(e[1] for e in entries)
    entity = {"scope": "inventory.drive", "type": "drive", "value": drive_id}

    body_lines = [f"# find-dump: {drive_id}", "", "## Shards", ""]
    for name in shard_names:
        body_lines.append(f"- inventory/find-dump/{drive_id}/{name}")
    body_lines.append("")
    body = "\n".join(body_lines)

    candidate_meta = {
        "source": PLUGIN_NAME,
        "processor": PLUGIN_NAME,
        "processor_version": PLUGIN_VERSION,
        "entities": [entity],
        "file_count": file_count,
        "total_bytes": total_bytes,
    }

    new_ts = datetime.now().replace(microsecond=0).isoformat()

    # No-op detection that survives the frontmatter dumps->load round-trip AND is
    # immune to time advancing: render a TRIAL with the PRIOR last_swept and
    # byte-compare against the file on disk. If identical (and no shard changed),
    # nothing actually changed -> leave the file (and its old last_swept) untouched.
    if summary_path.exists() and not shards_changed:
        prior_ts = frontmatter.load(summary_path).metadata.get("last_swept", new_ts)
        trial = frontmatter.dumps(frontmatter.Post(body, **{**candidate_meta, "last_swept": prior_ts}))
        if summary_path.read_text(encoding="utf-8") == trial:
            return None

    content = frontmatter.dumps(frontmatter.Post(body, **{**candidate_meta, "last_swept": new_ts}))
    write_atomic(summary_path, content)
    return summary_path
