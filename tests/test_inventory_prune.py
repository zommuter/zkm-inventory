"""RED spec for INV6 (id:d0a5): prune rendered records removed from the manifest.

roadmap:d0a5 -- convert() must delete `inventory/{drives,devices}/<id>.md` files this plugin
rendered (`source: inventory`) whose id is no longer in the manifest, with their sidecars;
never anything it did not render. Hermetic tmp_path stores, placeholder assets only.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

import convert as inv


def _convert(store: Path, manifest: dict) -> list[Path]:
    path = store / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return inv.convert(store, {"manifest": str(path)})


def _dev(rid: str) -> dict:
    return {"id": rid, "kind": "raspberry-pi", "model": f"Example {rid}", "status": "idle"}


def _drive(rid: str) -> dict:
    return {"id": rid, "label": f"Example {rid}", "capacity_gb": 1000}


def test_removed_device_md_is_deleted_and_others_untouched(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-keep"), _dev("pi-gone")]})
    devices = tmp_path / "inventory" / "devices"
    keep_before = (devices / "pi-keep.md").read_text(encoding="utf-8")

    _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert not (devices / "pi-gone.md").exists()
    assert (devices / "pi-keep.md").read_text(encoding="utf-8") == keep_before


def test_removed_path_is_reported(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-keep"), _dev("pi-gone")]})
    changed = _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert tmp_path / "inventory" / "devices" / "pi-gone.md" in changed


def test_renamed_id_replaces_old_file(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-old-name")]})
    _convert(tmp_path, {"devices": [_dev("pi-new-name")]})

    devices = tmp_path / "inventory" / "devices"
    assert not (devices / "pi-old-name.md").exists()
    assert (devices / "pi-new-name.md").exists()


def test_removed_drive_md_is_deleted(tmp_path: Path):
    _convert(tmp_path, {"drives": [_drive("d-keep"), _drive("d-gone")]})
    _convert(tmp_path, {"drives": [_drive("d-keep")]})

    drives = tmp_path / "inventory" / "drives"
    assert not (drives / "d-gone.md").exists()
    assert (drives / "d-keep.md").exists()


def test_foreign_md_in_lane_dir_is_never_pruned(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-keep")]})
    devices = tmp_path / "inventory" / "devices"
    foreign = devices / "hand-written-note.md"
    foreign.write_text(frontmatter.dumps(frontmatter.Post("my note", source="notes")))
    bare = devices / "no-frontmatter.md"
    bare.write_text("# just text\n")

    _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert foreign.exists()
    assert bare.exists()


def test_sidecars_of_pruned_record_are_removed_kept_ones_untouched(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-keep"), _dev("pi-gone")]})
    devices = tmp_path / "inventory" / "devices"
    for rid in ("pi-keep", "pi-gone"):
        (devices / f"{rid}.md.amendments.json").write_text('{"schema": 2}')
        (devices / f"{rid}.md.amendments.json.lock").write_text("")

    _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert not (devices / "pi-gone.md.amendments.json").exists()
    assert not (devices / "pi-gone.md.amendments.json.lock").exists()
    assert (devices / "pi-keep.md.amendments.json").read_text() == '{"schema": 2}'
    assert (devices / "pi-keep.md.amendments.json.lock").exists()


def test_roster_removed_when_no_devices_and_no_attestation(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-gone")]})
    roster = tmp_path / "inventory" / "devices.md"
    assert roster.exists()

    _convert(tmp_path, {"drives": [_drive("d-keep")]})

    assert not roster.exists()


def test_roster_kept_when_attested_with_zero_devices(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-gone")]})
    _convert(tmp_path, {"complete_as_of": "2026-11-10", "devices": []})

    roster = tmp_path / "inventory" / "devices.md"
    assert roster.exists()
    assert "pi-gone" not in frontmatter.load(roster).content


def test_find_dump_dir_is_never_pruned(tmp_path: Path):
    shard = tmp_path / "inventory" / "find-dump" / "some-drive.md"
    shard.parent.mkdir(parents=True)
    shard.write_text(frontmatter.dumps(frontmatter.Post("x", source="inventory-finddump")))

    _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert shard.exists()


def test_unchanged_manifest_after_prune_reports_nothing(tmp_path: Path):
    _convert(tmp_path, {"devices": [_dev("pi-keep"), _dev("pi-gone")]})
    _convert(tmp_path, {"devices": [_dev("pi-keep")]})

    assert _convert(tmp_path, {"devices": [_dev("pi-keep")]}) == []
