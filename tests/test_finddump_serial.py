"""RED spec for INV5 (id:3423): finddump drive identity by hardware serial.

roadmap:3423 -- owner ruling 2026-11-10 (ARCHITECTURE.md §Drive identity): a partition
inherits its parent disk's serial; `mount: {serial}` narrows to that disk, then `label` or
`uuid` picks the partition; serial alone suffices for a single mounted partition.

Hermetic: fixture trees under tmp_path; `_enumerate_mounts` and `_enumerate_serials` are
monkeypatched (the conftest stubs serials to {} by default). Placeholder serials only.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

import finddump as fd


@pytest.fixture(autouse=True)
def _force_pathspec_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fd.shutil, "which", lambda *_args, **_kwargs: None)


def _tree(root: Path, token: str) -> Path:
    (root / "Videos").mkdir(parents=True)
    (root / "Videos" / f"{token}.mkv").write_text("fake video bytes")
    return root


def _online(monkeypatch, mounts, serials) -> None:
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: mounts)
    monkeypatch.setattr(fd, "_enumerate_serials", lambda: serials, raising=False)


def _cfg(drive_id: str, **mount) -> dict:
    return {"drives": [{"id": drive_id, "mount": mount, "content_roots": ["Videos"]}]}


def _haystack(store: Path, drive_id: str) -> str:
    shard_dir = store / "inventory" / "find-dump" / drive_id
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(shard_dir.glob("*.md")))


def test_serial_alone_matches_single_partition_disk(tmp_path: Path, monkeypatch):
    mp = _tree(tmp_path / "a1", "only-partition-token")
    _online(monkeypatch, [("UUID-A1", "DATA", mp)], {mp: "SERIAL-AAAA"})

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a", serial="SERIAL-AAAA"))

    assert "only-partition-token" in _haystack(store, "disk-a")


def test_serial_plus_label_picks_partition_on_shared_disk(tmp_path: Path, monkeypatch):
    # A decoy DATA partition on disk B is enumerated first: label-only would pick it.
    decoy = _tree(tmp_path / "b1", "decoy-token")
    sys_mp = _tree(tmp_path / "a1", "system-token")
    data_mp = _tree(tmp_path / "a2", "data-token")
    _online(
        monkeypatch,
        [("UUID-B1", "DATA", decoy), ("UUID-A1", "SYS", sys_mp), ("UUID-A2", "DATA", data_mp)],
        {decoy: "SERIAL-BBBB", sys_mp: "SERIAL-AAAA", data_mp: "SERIAL-AAAA"},
    )

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a-data", serial="SERIAL-AAAA", label="data"))

    hay = _haystack(store, "disk-a-data")
    assert "data-token" in hay
    assert "system-token" not in hay
    assert "decoy-token" not in hay


def test_serial_plus_uuid_picks_partition_on_shared_disk(tmp_path: Path, monkeypatch):
    sys_mp = _tree(tmp_path / "a1", "system-token")
    data_mp = _tree(tmp_path / "a2", "data-token")
    _online(
        monkeypatch,
        [("UUID-A1", "SYS", sys_mp), ("UUID-A2", "DATA", data_mp)],
        {sys_mp: "SERIAL-AAAA", data_mp: "SERIAL-AAAA"},
    )

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a-sys", serial="SERIAL-AAAA", uuid="UUID-A1"))

    hay = _haystack(store, "disk-a-sys")
    assert "system-token" in hay
    assert "data-token" not in hay


def test_uuid_on_a_different_disk_is_not_used_when_serial_is_set(tmp_path: Path, monkeypatch):
    # The configured uuid exists, but on disk B: with serial A set it must not match.
    on_b = _tree(tmp_path / "b1", "token-on-disk-b")
    _online(monkeypatch, [("UUID-X", "DATA", on_b)], {on_b: "SERIAL-BBBB"})

    store = tmp_path / "store"
    result = fd.convert(store, _cfg("disk-a", serial="SERIAL-AAAA", uuid="UUID-X"))

    assert result == []
    assert not (store / "inventory" / "find-dump" / "disk-a").exists()


def test_label_reused_on_another_disk_is_not_matched(tmp_path: Path, monkeypatch):
    # Disk B is enumerated FIRST and carries the same label: label-only matching would
    # pick it. With serial A configured, only disk A's partition may match.
    on_b = _tree(tmp_path / "b1", "token-on-disk-b")
    on_a = _tree(tmp_path / "a1", "token-on-disk-a")
    _online(
        monkeypatch,
        [("UUID-B1", "MEDIA", on_b), ("UUID-A1", "MEDIA", on_a)],
        {on_b: "SERIAL-BBBB", on_a: "SERIAL-AAAA"},
    )

    store = tmp_path / "store"
    fd.convert(store, _cfg("media-a", serial="SERIAL-AAAA", label="MEDIA"))

    hay = _haystack(store, "media-a")
    assert "token-on-disk-a" in hay
    assert "token-on-disk-b" not in hay


def test_stale_uuid_after_reformat_still_found_via_serial_and_label(
    tmp_path: Path, monkeypatch
):
    # Disk A was reformatted (new uuid); a decoy on disk B, enumerated first, still carries
    # the same label. Only serial A + label may match.
    decoy = _tree(tmp_path / "b1", "decoy-token")
    mp = _tree(tmp_path / "a1", "reformatted-token")
    _online(
        monkeypatch,
        [("UUID-B1", "DATA", decoy), ("UUID-NEW", "DATA", mp)],
        {decoy: "SERIAL-BBBB", mp: "SERIAL-AAAA"},
    )

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a", serial="SERIAL-AAAA", uuid="UUID-OLD", label="DATA"))

    hay = _haystack(store, "disk-a")
    assert "reformatted-token" in hay
    assert "decoy-token" not in hay


def test_serial_with_two_partitions_and_no_selector_raises(tmp_path: Path, monkeypatch):
    sys_mp = _tree(tmp_path / "a1", "system-token")
    data_mp = _tree(tmp_path / "a2", "data-token")
    _online(
        monkeypatch,
        [("UUID-A1", "SYS", sys_mp), ("UUID-A2", "DATA", data_mp)],
        {sys_mp: "SERIAL-AAAA", data_mp: "SERIAL-AAAA"},
    )

    with pytest.raises(ValueError, match="ambiguous-disk"):
        fd.convert(tmp_path / "store", _cfg("ambiguous-disk", serial="SERIAL-AAAA"))


def test_serial_not_online_is_skipped_without_raising(tmp_path: Path, monkeypatch):
    other = _tree(tmp_path / "b1", "other-token")
    _online(monkeypatch, [("UUID-B1", "OTHER", other)], {other: "SERIAL-BBBB"})

    store = tmp_path / "store"
    result = fd.convert(store, _cfg("disk-a", serial="SERIAL-AAAA"))

    assert result == []
    assert not (store / "inventory" / "find-dump" / "disk-a").exists()


def test_serial_online_but_no_partition_matches_selector_is_offline(
    tmp_path: Path, monkeypatch
):
    sys_mp = _tree(tmp_path / "a1", "system-token")
    _online(monkeypatch, [("UUID-A1", "SYS", sys_mp)], {sys_mp: "SERIAL-AAAA"})

    store = tmp_path / "store"
    result = fd.convert(store, _cfg("disk-a-data", serial="SERIAL-AAAA", label="DATA"))

    assert result == []
    assert not (store / "inventory" / "find-dump" / "disk-a-data").exists()


def test_disk_serial_recorded_in_summary_even_without_serial_config(
    tmp_path: Path, monkeypatch
):
    mp = _tree(tmp_path / "a1", "token")
    _online(monkeypatch, [("UUID-A1", "DATA", mp)], {mp: "SERIAL-AAAA"})

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a", uuid="UUID-A1"))

    summary = frontmatter.load(store / "inventory" / "find-dump" / "disk-a.md")
    assert summary.metadata.get("disk_serial") == "SERIAL-AAAA"


def test_summary_has_no_disk_serial_when_unknown(tmp_path: Path, monkeypatch):
    mp = _tree(tmp_path / "a1", "token")
    _online(monkeypatch, [("UUID-A1", "DATA", mp)], {})

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a", uuid="UUID-A1"))

    summary = frontmatter.load(store / "inventory" / "find-dump" / "disk-a.md")
    assert "disk_serial" not in summary.metadata


def test_without_serial_config_label_matching_is_unchanged(tmp_path: Path, monkeypatch):
    # regression-guard (passes today): roadmap:3423 must not change serial-less configs.
    mp = _tree(tmp_path / "a1", "label-token")
    _online(monkeypatch, [("UUID-A1", "DATA", mp)], {mp: "SERIAL-AAAA"})

    store = tmp_path / "store"
    fd.convert(store, _cfg("disk-a", label="data"))

    assert "label-token" in _haystack(store, "disk-a")


@pytest.mark.real_lsblk_serials
def test_enumerate_serials_inherits_parent_disk_serial(monkeypatch):
    sample_stdout = (
        'NAME="sdx" PKNAME="" SERIAL="SERIAL-AAAA" MOUNTPOINT=""\n'
        'NAME="sdx1" PKNAME="sdx" SERIAL="" MOUNTPOINT="/mnt/example-sys"\n'
        'NAME="sdx2" PKNAME="sdx" SERIAL="" MOUNTPOINT="/mnt/example-data"\n'
        'NAME="sdy" PKNAME="" SERIAL="SERIAL-BBBB" MOUNTPOINT="/mnt/example-whole"\n'
        'NAME="sdz" PKNAME="" SERIAL="SERIAL-CCCC" MOUNTPOINT=""\n'
        'NAME="sdz1" PKNAME="sdz" SERIAL="" MOUNTPOINT=""\n'
    )

    class _Completed:
        stdout = sample_stdout

    def _fake_run(cmd, **kwargs):
        assert "lsblk" in cmd[0]
        assert "PKNAME" in ",".join(cmd) and "SERIAL" in ",".join(cmd)
        return _Completed()

    monkeypatch.setattr(fd.shutil, "which", lambda name: "/usr/bin/lsblk" if name == "lsblk" else None)
    monkeypatch.setattr(fd.subprocess, "run", _fake_run)

    assert fd._enumerate_serials() == {
        Path("/mnt/example-sys"): "SERIAL-AAAA",
        Path("/mnt/example-data"): "SERIAL-AAAA",
        Path("/mnt/example-whole"): "SERIAL-BBBB",
    }
