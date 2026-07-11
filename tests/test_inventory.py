"""Red-spec tests for zkm-inventory v1 (drives + devices lanes).

Hermetic: tmp_path store, no network, no real inventory. These assert the
contract the executor must satisfy (ROADMAP INV1 id:82a2 / INV2 id:5697).
All FAIL against the handoff skeleton (convert() raises NotImplementedError).
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

import convert as inv

FIXTURE = Path(__file__).parent / "fixtures" / "inventory.yaml"


def _run(store: Path) -> list[Path]:
    return inv.convert(store, {"manifest": str(FIXTURE)})


def _entities(md: Path) -> list[dict]:
    post = frontmatter.load(md)
    return list(post.metadata.get("entities") or [])


# --- ROADMAP INV1 (id:82a2) — drives lane ---------------------------------

def test_drives_lane_creates_one_md_per_drive(tmp_path: Path):
    _run(tmp_path)
    drives = tmp_path / "inventory" / "drives"
    assert (drives / "example-media.md").exists()
    assert (drives / "example-backup.md").exists()


def test_drive_md_has_source_and_typed_entity(tmp_path: Path):
    _run(tmp_path)
    md = tmp_path / "inventory" / "drives" / "example-media.md"
    post = frontmatter.load(md)
    assert post.metadata.get("source") == "inventory"
    ents = _entities(md)
    drive_ents = [e for e in ents if e.get("type") == "drive"]
    assert any(
        e.get("scope") == "inventory.drive" and e.get("value") == "example-media"
        for e in drive_ents
    ), f"expected a scope:inventory.drive entity for example-media, got {ents}"


def test_drive_body_is_searchable_for_purpose(tmp_path: Path):
    # The rendered body must carry the human-readable descriptive fields so BM25
    # can locate a drive by its purpose / data classes.
    _run(tmp_path)
    md = tmp_path / "inventory" / "drives" / "example-media.md"
    body = frontmatter.load(md).content.lower()
    assert "media archive" in body
    assert "movies" in body


# --- ROADMAP INV2 (id:5697) — devices lane --------------------------------

def test_devices_lane_creates_one_md_per_device(tmp_path: Path):
    _run(tmp_path)
    devices = tmp_path / "inventory" / "devices"
    assert (devices / "pi-example.md").exists()
    assert (devices / "pi-idle-example.md").exists()


def test_device_md_has_typed_entity_and_status(tmp_path: Path):
    _run(tmp_path)
    md = tmp_path / "inventory" / "devices" / "pi-example.md"
    post = frontmatter.load(md)
    assert post.metadata.get("source") == "inventory"
    ents = _entities(md)
    assert any(
        e.get("scope") == "inventory.device" and e.get("value") == "pi-example"
        for e in ents
    ), f"expected a scope:inventory.device entity for pi-example, got {ents}"


def test_dust_collecting_device_is_findable_by_status(tmp_path: Path):
    # The idle/dust-collecting status must be searchable (tag or body) so
    # `zkm search dust-collecting` surfaces the drawer RPi.
    _run(tmp_path)
    md = tmp_path / "inventory" / "devices" / "pi-idle-example.md"
    post = frontmatter.load(md)
    haystack = (post.content + " " + " ".join(post.metadata.get("tags") or [])).lower()
    assert "dust-collecting" in haystack


# --- shared contract -------------------------------------------------------

def test_rerun_is_idempotent(tmp_path: Path):
    _run(tmp_path)
    before = {p: p.read_text() for p in (tmp_path / "inventory").rglob("*.md")}
    second = _run(tmp_path)
    after = {p: p.read_text() for p in (tmp_path / "inventory").rglob("*.md")}
    assert before == after, "re-running an unchanged manifest must not change any md"
    assert second == [], "re-run with no manifest change must report no created paths"


def test_missing_manifest_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        inv.convert(tmp_path, {"manifest": str(tmp_path / "nope.yaml")})
