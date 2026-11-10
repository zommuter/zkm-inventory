"""RED spec for id:0a98: a failing `lsblk` must be loud, never "every drive offline".

roadmap:0a98 -- owner ruling 2026-11-10 (relay human, REVIEW_ME batch 1): when any drive uses
`mount:` and drive enumeration cannot run (no `lsblk`, or it exits non-zero), finddump raises
`RuntimeError` naming `lsblk`, instead of reporting a silent no-op sweep. A drive that is merely
not plugged in (lsblk works, nothing matches) still skips quietly, and configs with only
explicit `roots:` never need lsblk at all. Hermetic: subprocess/which are monkeypatched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import finddump as fd


@pytest.fixture(autouse=True)
def _force_pathspec_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # `fd` lookups resolve to nothing; lsblk lookups are set per test below.
    monkeypatch.setattr(fd.shutil, "which", lambda *_args, **_kwargs: None)


def _mount_cfg(**mount) -> dict:
    return {"drives": [{"id": "disk-a", "mount": mount, "content_roots": ["Videos"]}]}


def _lsblk_present(monkeypatch) -> None:
    monkeypatch.setattr(
        fd.shutil, "which", lambda name: "/usr/bin/lsblk" if name == "lsblk" else None
    )


def test_missing_lsblk_with_mount_drive_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match="lsblk"):
        fd.convert(tmp_path / "store", _mount_cfg(label="DATA"))


def test_failing_lsblk_with_mount_drive_raises(tmp_path: Path, monkeypatch):
    _lsblk_present(monkeypatch)

    def _boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="lsblk: failed to access sysfs")

    monkeypatch.setattr(fd.subprocess, "run", _boom)

    with pytest.raises(RuntimeError, match="lsblk"):
        fd.convert(tmp_path / "store", _mount_cfg(uuid="UUID-A1"))


def test_explicit_roots_only_never_needs_lsblk(tmp_path: Path):
    root = tmp_path / "drive"
    (root / "Videos").mkdir(parents=True)
    (root / "Videos" / "token.mkv").write_text("x")

    # lsblk is absent (autouse fixture); a roots-only config must still sweep.
    fd.convert(tmp_path / "store", {"drives": [{"id": "explicit", "roots": [str(root)]}]})

    assert (tmp_path / "store" / "inventory" / "find-dump" / "explicit.md").exists()


def test_working_lsblk_with_unplugged_drive_still_skips_quietly(tmp_path: Path, monkeypatch):
    _lsblk_present(monkeypatch)

    class _Completed:
        stdout = 'UUID="UUID-OTHER" LABEL="OTHER" MOUNTPOINT="/mnt/example-other"\n'

    monkeypatch.setattr(fd.subprocess, "run", lambda cmd, **kwargs: _Completed())

    assert fd.convert(tmp_path / "store", _mount_cfg(label="DATA")) == []


@pytest.mark.real_lsblk_serials
def test_failing_serial_lookup_with_serial_drive_raises(tmp_path: Path, monkeypatch):
    # Mount enumeration works; only the serial query fails. A `serial:` config must not
    # silently read as offline either.
    mp = tmp_path / "a1"
    (mp / "Videos").mkdir(parents=True)
    monkeypatch.setattr(fd, "_enumerate_mounts", lambda: [("UUID-A1", "DATA", mp)])
    _lsblk_present(monkeypatch)

    def _serial_boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(fd.subprocess, "run", _serial_boom)

    with pytest.raises(RuntimeError, match="lsblk"):
        fd.convert(tmp_path / "store", _mount_cfg(serial="SERIAL-AAAA"))
