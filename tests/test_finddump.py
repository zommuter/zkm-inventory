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

def test_resweep_unchanged_is_noop_and_last_swept_stable(tmp_path: Path):
    root = tmp_path / "drive"
    _make_tree(root)
    store = tmp_path / "store"
    fd.convert(store, _drives_config(root))

    summary = store / "inventory" / "find-dump" / "example-media.md"
    before_summary = summary.read_text(encoding="utf-8")
    before_shards = _shard_bodies(store, "example-media")
    before_last_swept = frontmatter.load(summary).metadata["last_swept"]

    second = fd.convert(store, _drives_config(root))

    after_summary = summary.read_text(encoding="utf-8")
    after_shards = _shard_bodies(store, "example-media")
    after_last_swept = frontmatter.load(summary).metadata["last_swept"]

    assert second == [], "an unchanged re-sweep must report no created/changed paths"
    assert before_shards == after_shards
    assert before_summary == after_summary
    assert before_last_swept == after_last_swept, "last_swept must not bump when nothing changed"


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
