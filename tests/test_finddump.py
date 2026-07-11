"""Red-spec tests for the inventory-finddump plugin (ROADMAP INV3b id, thin fd-adapter).

Hermetic: tmp_path store + fixture temp trees, no network, no real drives. The
pathspec fallback backend is forced (`monkeypatch.setattr(finddump.shutil,
"which", lambda *_: None)`) so the suite never depends on `fd` being installed.
One optional test exercises the real `fd` backend and skips when absent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import frontmatter
import pytest

import finddump as fd


def _make_tree(root: Path) -> None:
    """A drive-content fixture tree: metafiles-to-skip + a nested dir + a
    findable filename token, sized well under any shard cap."""
    (root / ".git" / "objects").mkdir(parents=True)
    (root / ".git" / "objects" / "deadbeef").write_text("not a real object")
    (root / ".git" / "config").write_text("[core]\n")

    (root / "node_modules" / "leftpad").mkdir(parents=True)
    (root / "node_modules" / "leftpad" / "index.js").write_text("module.exports = 1;")

    (root / "Videos").mkdir()
    (root / "Videos" / "blade-runner-2049.mkv").write_text("fake video bytes")

    (root / "Photos" / "2026").mkdir(parents=True)
    (root / "Photos" / "2026" / "holiday.jpg").write_text("fake photo bytes")


def _drives_config(root: Path, drive_id: str = "example-media") -> dict:
    return {"drives": [{"id": drive_id, "roots": [str(root)]}]}


@pytest.fixture(autouse=True)
def _force_pathspec_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # Hermetic default: never depend on `fd` being installed on the dev box.
    monkeypatch.setattr(fd.shutil, "which", lambda *_args, **_kwargs: None)


def _shard_bodies(store: Path, drive_id: str) -> dict[str, str]:
    shard_dir = store / "inventory" / "find-dump" / drive_id
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(shard_dir.glob("*.md"))}


# --- (1) a known filename token appears in some shard body -----------------

def test_known_filename_token_is_findable(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    bodies = _shard_bodies(store, "example-media")
    haystack = "\n".join(bodies.values())
    assert "blade-runner-2049.mkv" in haystack


# --- (2) .git internals + node_modules are EXCLUDED -------------------------

def test_git_internals_and_node_modules_excluded(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    bodies = _shard_bodies(store, "example-media")
    haystack = "\n".join(bodies.values())
    assert "deadbeef" not in haystack
    assert ".git" not in haystack
    assert "leftpad" not in haystack
    assert "node_modules" not in haystack


# --- (3) every shard <= the cap ---------------------------------------------

def test_every_shard_is_under_the_cap(tmp_path: Path):
    root = tmp_path / "drive"
    root.mkdir()
    big_dir = root / "Bulk"
    big_dir.mkdir()
    # Exceed the ~2000-entries-per-shard target so packing must split.
    for i in range(2500):
        (big_dir / f"file-{i:05d}.dat").write_text("x")
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    bodies = _shard_bodies(store, "example-media")
    assert len(bodies) > 1, "2500 entries in one dir must split into >1 shard"
    for name, body in bodies.items():
        lines = [line for line in body.splitlines() if line]
        assert len(lines) <= fd._SHARD_MAX_ENTRIES, f"{name} has {len(lines)} entries"
        assert len(body.encode("utf-8")) <= fd._SHARD_MAX_BYTES + 1024, (
            f"{name} is {len(body.encode('utf-8'))} bytes"
        )


# --- (4) re-sweep of an unchanged tree is a byte-identical git no-op -------

def test_resweep_unchanged_is_noop_and_last_swept_stable(tmp_path: Path, monkeypatch):
    # Advance the clock BETWEEN sweeps so this catches the real bug (a naive
    # implementation bumps last_swept every run). Subclass datetime so now()
    # advances while fromtimestamp() (used for file mtimes) still works.
    import datetime as _dt

    class _FakeDT(_dt.datetime):
        _n = _dt.datetime(2026, 1, 1, 10, 0, 0)

        @classmethod
        def now(cls, tz=None):
            cur = cls._n
            cls._n = cls._n + _dt.timedelta(hours=1)
            return cur

    monkeypatch.setattr(fd, "datetime", _FakeDT)

    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    summary = store / "inventory" / "find-dump" / "example-media.md"
    before_summary = summary.read_text(encoding="utf-8")
    before_shards = _shard_bodies(store, "example-media")
    before_last_swept = frontmatter.load(summary).metadata["last_swept"]

    second = fd.convert(store, _drives_config(root))  # now() returns a LATER time

    after_summary = summary.read_text(encoding="utf-8")
    after_shards = _shard_bodies(store, "example-media")
    after_last_swept = frontmatter.load(summary).metadata["last_swept"]

    assert second == [], "an unchanged re-sweep must report no created/changed paths"
    assert before_shards == after_shards
    assert before_summary == after_summary
    assert before_last_swept == after_last_swept, (
        "last_swept must not bump when nothing changed, even as wall-clock advances"
    )


# --- (5) inserting one file dirties only its dir's shard --------------------

def test_inserting_one_file_dirties_only_its_shard(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))
    before = _shard_bodies(store, "example-media")

    (root / "Videos" / "another-movie.mkv").write_text("more fake bytes")
    fd.convert(store, _drives_config(root))
    after = _shard_bodies(store, "example-media")

    changed_names = sorted(name for name in before if before[name] != after.get(name))
    # Only shard files whose grouped directory ("Videos") holds the new entry
    # may differ; nothing else should be touched, and no new shard should be
    # required (well under the cap).
    assert len(after) == len(before), "no new shard file expected for one insert"
    assert len(changed_names) == 1, f"expected exactly one dirtied shard, got {changed_names}"
    assert "another-movie.mkv" in after[changed_names[0]]


# --- (6) summary frontmatter -------------------------------------------------

def test_summary_frontmatter_shape(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    summary = store / "inventory" / "find-dump" / "example-media.md"
    post = frontmatter.load(summary)
    assert post.metadata["source"] == "inventory-finddump"
    ents = post.metadata.get("entities") or []
    assert any(
        e.get("scope") == "inventory.drive" and e.get("type") == "drive"
        and e.get("value") == "example-media"
        for e in ents
    ), f"expected shared scope:inventory.drive entity, got {ents}"
    assert post.metadata["file_count"] == 2  # Videos + Photos/2026 files, git/node_modules excluded
    assert "last_swept" in post.metadata


# --- (7) a configured root that doesn't exist is skipped gracefully --------

def test_missing_root_is_skipped_gracefully(tmp_path: Path):
    store = tmp_path / "store"
    missing_root = tmp_path / "not-mounted"
    result = fd.convert(store, _drives_config(missing_root, drive_id="offline-drive"))

    assert result == []
    assert not (store / "inventory" / "find-dump" / "offline-drive.md").exists()
    assert not (store / "inventory" / "find-dump" / "offline-drive").exists()


# --- both plugins still discover --------------------------------------------

def test_both_plugin_docs_discoverable():
    import yaml

    docs = [d for d in yaml.safe_load_all(Path("plugin.yaml").read_text()) if d]
    names = {d["name"] for d in docs}
    assert names == {"inventory", "inventory-finddump"}


# --- optional: real `fd` backend, only when installed -----------------------

def test_fd_backend_matches_pathspec_backend_when_available(tmp_path: Path, monkeypatch):
    if shutil.which("fd") is None and shutil.which("fdfind") is None:
        pytest.skip("fd/fdfind not installed on this host")
    monkeypatch.undo()  # restore real shutil.which for this one test

    root = tmp_path / "drive"
    _make_tree(root)
    entries_fd = fd._list_files(root, backend="fd")
    entries_pathspec = fd._list_files(root, backend="pathspec")
    assert {e[0] for e in entries_fd} == {e[0] for e in entries_pathspec}


# --- INV3d: git-annex pointer exclusion (leg-disjointness, design §Q6) -----
#
# git-annex represents annexed content as a symlink whose target resolves
# through an `annex/objects` path segment into the annex object store. The
# find-dump sweep (lane-c) must exclude these -- lane-a (the future `git
# annex whereis` seam) already covers them -- so an annexed file is never
# double-reported by both legs. Detection must work on a BROKEN pointer too
# (target need not exist -- a drive whose annex content isn't present must
# still have its pointer recognized and excluded), and identically regardless
# of scan backend.


def test_annex_pointer_symlinks_excluded_normal_symlink_included(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)

    # A normal symlink to a regular (non-annex) file must be INCLUDED.
    real_file = root / "Videos" / "blade-runner-2049.mkv"
    normal_link = root / "Videos" / "blade-runner-2049-link.mkv"
    normal_link.symlink_to(real_file.name)

    # git-annex pointer symlink, RELATIVE target through annex/objects.
    # Target need NOT exist on disk.
    annex_link_rel = root / "Videos" / "annexed-relative.mkv"
    annex_link_rel.symlink_to(
        "../../.git/annex/objects/XX/YY/SHA256E-s123--deadbeef/annexed-relative.mkv"
    )

    # git-annex pointer symlink, ABSOLUTE target through annex/objects.
    annex_link_abs = root / "Videos" / "annexed-absolute.mkv"
    annex_link_abs.symlink_to(
        "/mnt/other-drive/.git/annex/objects/AA/BB/SHA256E-s456--cafebabe/annexed-absolute.mkv"
    )

    # git-annex pointer symlink whose target actually RESOLVES (not broken) --
    # must be excluded on detection alone, never merely because the target is
    # missing (the naive "stat-follow fails on a broken link" accident would
    # miss this case).
    annex_objects_dir = root / ".git" / "annex" / "objects" / "ZZ" / "WW"
    annex_objects_dir.mkdir(parents=True)
    (annex_objects_dir / "SHA256E-s789--realcontent.mkv").write_text("real annexed bytes")
    annex_link_resolving = root / "Videos" / "annexed-resolving.mkv"
    annex_link_resolving.symlink_to(
        "../.git/annex/objects/ZZ/WW/SHA256E-s789--realcontent.mkv"
    )

    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    bodies = _shard_bodies(store, "example-media")
    haystack = "\n".join(bodies.values())

    assert "blade-runner-2049-link.mkv" in haystack, "normal symlink must be included"
    assert "annexed-relative.mkv" not in haystack, (
        "relative-target annex pointer symlink must be excluded"
    )
    assert "annexed-absolute.mkv" not in haystack, (
        "absolute-target annex pointer symlink must be excluded"
    )
    assert "annexed-resolving.mkv" not in haystack, (
        "an annex pointer whose target actually resolves must still be excluded"
    )
    assert "realcontent.mkv" not in haystack, (
        "the .git/annex/objects internals themselves must never be swept"
    )


def test_is_annex_pointer_symlink_helper_relative_and_absolute(tmp_path: Path):
    root = tmp_path / "drive"
    root.mkdir()

    relative_link = root / "relative-pointer"
    relative_link.symlink_to("../../.git/annex/objects/XX/YY/SHA256E-s1--abc/file")

    absolute_link = root / "absolute-pointer"
    absolute_link.symlink_to("/mnt/x/.git/annex/objects/AA/BB/SHA256E-s2--def/file")

    normal_file = root / "normal.txt"
    normal_file.write_text("hi")

    normal_link = root / "normal-link.txt"
    normal_link.symlink_to("normal.txt")

    broken_non_annex_link = root / "broken-non-annex"
    broken_non_annex_link.symlink_to("does-not-exist.txt")

    assert fd._is_annex_pointer_symlink(relative_link) is True
    assert fd._is_annex_pointer_symlink(absolute_link) is True
    assert fd._is_annex_pointer_symlink(normal_file) is False
    assert fd._is_annex_pointer_symlink(normal_link) is False
    assert fd._is_annex_pointer_symlink(broken_non_annex_link) is False


# --- INV3c: mount orchestration + online-set resolution ---------------------
#
# A configured drive may declare `mount: {uuid?, label?}` + `content_roots:
# [<relpath>...]` instead of explicit `roots:`. At convert time the currently
# mounted filesystems are enumerated via `_enumerate_mounts()` (injectable —
# tests monkeypatch it to a fixture list, never shelling out to real `lsblk`)
# and matched by uuid (exact) or label (case-insensitive) to find the drive's
# live mountpoint; `content_roots` are then resolved relative to it.


def _mount_drive_config(
    drive_id: str, *, uuid: str | None = None, label: str | None = None, content_roots=None
) -> dict:
    mount: dict = {}
    if uuid is not None:
        mount["uuid"] = uuid
    if label is not None:
        mount["label"] = label
    drive: dict = {"id": drive_id, "mount": mount}
    if content_roots is not None:
        drive["content_roots"] = content_roots
    return {"drives": [drive]}


def test_mount_matched_by_uuid_sweeps_content_roots(tmp_path: Path, monkeypatch):
    mountpoint = tmp_path / "drive"
    _make_tree(mountpoint)
    monkeypatch.setattr(
        fd, "_enumerate_mounts", lambda: [("FAKE-UUID-1234", "MyDrive", mountpoint)]
    )

    store = tmp_path / "store"
    config = _mount_drive_config(
        "media-1", uuid="FAKE-UUID-1234", content_roots=["Videos", "Photos"]
    )
    fd.convert(store, config)

    bodies = _shard_bodies(store, "media-1")
    haystack = "\n".join(bodies.values())
    assert "blade-runner-2049.mkv" in haystack
    assert "holiday.jpg" in haystack


def test_mount_matched_by_label_case_insensitive(tmp_path: Path, monkeypatch):
    mountpoint = tmp_path / "drive"
    _make_tree(mountpoint)
    monkeypatch.setattr(
        fd, "_enumerate_mounts", lambda: [(None, "MyDrive", mountpoint)]
    )

    store = tmp_path / "store"
    config = _mount_drive_config("media-2", label="mydrive", content_roots=["Videos"])
    fd.convert(store, config)

    bodies = _shard_bodies(store, "media-2")
    haystack = "\n".join(bodies.values())
    assert "blade-runner-2049.mkv" in haystack


def test_offline_configured_drive_skipped_no_raise_prior_shards_untouched(
    tmp_path: Path, monkeypatch
):
    mountpoint = tmp_path / "drive"
    _make_tree(mountpoint)
    store = tmp_path / "store"

    # First sweep while online (matched by uuid) to create prior shards.
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [("UUID-ONLINE", None, mountpoint)])
    config = _mount_drive_config("offline-1", uuid="UUID-ONLINE", content_roots=["Videos"])
    fd.convert(store, config)
    before = _shard_bodies(store, "offline-1")
    assert before  # sanity: something was written while online

    # Now the drive is unplugged -- no mount matches its uuid/label at all.
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [])
    result = fd.convert(store, config)  # must not raise

    after = _shard_bodies(store, "offline-1")
    assert result == [], "an offline configured drive must report no changes"
    assert after == before, "prior shards must be left untouched when the drive is offline"


def test_content_roots_restricts_sweep_to_those_subpaths(tmp_path: Path, monkeypatch):
    mountpoint = tmp_path / "drive"
    _make_tree(mountpoint)
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [("UUID-X", None, mountpoint)])

    store = tmp_path / "store"
    config = _mount_drive_config("media-3", uuid="UUID-X", content_roots=["Videos"])
    fd.convert(store, config)

    bodies = _shard_bodies(store, "media-3")
    haystack = "\n".join(bodies.values())
    assert "blade-runner-2049.mkv" in haystack
    assert "holiday.jpg" not in haystack, "Photos/ is outside content_roots and must be excluded"


def test_explicit_roots_still_works_unchanged(tmp_path: Path, monkeypatch):
    # A drive with explicit `roots:` (INV3b style) must keep working even
    # though `_enumerate_mounts` is available/monkeypatched -- explicit roots
    # are an override that bypasses mount resolution entirely.
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [])

    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root, drive_id="explicit-1"))

    bodies = _shard_bodies(store, "explicit-1")
    haystack = "\n".join(bodies.values())
    assert "blade-runner-2049.mkv" in haystack


def test_mount_based_resweep_unchanged_is_noop_and_last_swept_stable(tmp_path: Path, monkeypatch):
    import datetime as _dt

    class _FakeDT(_dt.datetime):
        _n = _dt.datetime(2026, 1, 1, 10, 0, 0)

        @classmethod
        def now(cls, tz=None):
            cur = cls._n
            cls._n = cls._n + _dt.timedelta(hours=1)
            return cur

    monkeypatch.setattr(fd, "datetime", _FakeDT)

    mountpoint = tmp_path / "drive"
    _make_tree(mountpoint)
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [("UUID-STABLE", None, mountpoint)])

    store = tmp_path / "store"
    config = _mount_drive_config("media-stable", uuid="UUID-STABLE", content_roots=["Videos"])
    fd.convert(store, config)

    summary = store / "inventory" / "find-dump" / "media-stable.md"
    before_summary = summary.read_text(encoding="utf-8")
    before_shards = _shard_bodies(store, "media-stable")
    before_last_swept = frontmatter.load(summary).metadata["last_swept"]

    second = fd.convert(store, config)  # now() returns a LATER time

    after_summary = summary.read_text(encoding="utf-8")
    after_shards = _shard_bodies(store, "media-stable")
    after_last_swept = frontmatter.load(summary).metadata["last_swept"]

    assert second == [], "an unchanged mount-based re-sweep must report no changed paths"
    assert before_shards == after_shards
    assert before_summary == after_summary
    assert before_last_swept == after_last_swept


def test_enumerate_mounts_real_lsblk_parsing(monkeypatch, tmp_path: Path):
    """`_enumerate_mounts()` parses real `lsblk -P` output shape correctly.

    Hermetic: monkeypatches `subprocess.run` to return a canned `lsblk -P -n`
    transcript (captured from a real Linux host) rather than shelling out.
    """
    sample_stdout = (
        'UUID="" LABEL="" MOUNTPOINT=""\n'
        'UUID="B4FC7F32FC7EEE4C" LABEL="" MOUNTPOINT=""\n'
        'UUID="E054F82054F7F6DE" LABEL="Cee" MOUNTPOINT="/run/media/tobias/Cee"\n'
        'UUID="e84375a2-3279-4419-ae99-7053088b2f3c" LABEL="Manjaro" '
        'MOUNTPOINT="/run/media/tobias/Manjaro"\n'
    )

    class _FakeCompleted:
        stdout = sample_stdout

    def _fake_run(cmd, **kwargs):
        assert cmd[0] in ("lsblk",) or "lsblk" in cmd[0]
        return _FakeCompleted()

    monkeypatch.setattr(fd.shutil, "which", lambda name: "/usr/bin/lsblk" if name == "lsblk" else None)
    monkeypatch.setattr(fd.subprocess, "run", _fake_run)

    mounts = fd._enumerate_mounts()
    assert (
        "E054F82054F7F6DE",
        "Cee",
        Path("/run/media/tobias/Cee"),
    ) in mounts
    assert (
        "e84375a2-3279-4419-ae99-7053088b2f3c",
        "Manjaro",
        Path("/run/media/tobias/Manjaro"),
    ) in mounts
    # Unmounted block devices (empty MOUNTPOINT) must be omitted entirely.
    assert all(mp != Path("") for _, _, mp in mounts)
