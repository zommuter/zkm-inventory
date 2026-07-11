"""Red-spec tests for zkm-inventory v1 (drives + devices lanes).

Hermetic: tmp_path store, no network, no real inventory. These assert the
contract the executor must satisfy (ROADMAP INV1 id:82a2 / INV2 id:5697).
All FAIL against the handoff skeleton (convert() raises NotImplementedError).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import frontmatter
import pytest
import yaml

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


# --- ROADMAP INV-FIX (id:86b5) — v1 correctness fixes ----------------------


def test_amender_frontmatter_survives_reconvert(tmp_path: Path):
    """Bug #1 (the important one): an amender's frontmatter write-back (extra
    entities[]/tags beyond this plugin's own scope) must survive a re-convert,
    and the re-convert must report no created paths (true idempotence)."""
    _run(tmp_path)
    md = tmp_path / "inventory" / "drives" / "example-media.md"
    post = frontmatter.load(md)
    post.metadata["entities"] = [*post.metadata.get("entities", []),
                                 {"scope": "body", "type": "org", "value": "Foo"}]
    post.metadata["tags"] = [*post.metadata.get("tags", []), "amender-tag"]
    md.write_text(frontmatter.dumps(post), encoding="utf-8")

    second = _run(tmp_path)

    reloaded = frontmatter.load(md)
    ents = reloaded.metadata.get("entities") or []
    assert any(
        e.get("scope") == "body" and e.get("type") == "org" and e.get("value") == "Foo"
        for e in ents
    ), f"amender-added entity was clobbered: {ents}"
    assert "amender-tag" in (reloaded.metadata.get("tags") or []), (
        "amender-added tag was clobbered"
    )
    assert second == [], "re-convert after an amender write-back must report no created paths"


def test_editing_one_record_changes_only_that_file(tmp_path: Path):
    """Bug #2: date must be per-record (or absent), never a manifest-mtime
    stamped onto every record — editing one record (and touching the
    manifest's mtime) must change exactly that one rendered file."""
    manifest = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    os.utime(manifest_path, (1_700_000_000, 1_700_000_000))

    inv.convert(tmp_path, {"manifest": str(manifest_path)})
    before = {p: p.read_text() for p in (tmp_path / "inventory").rglob("*.md")}

    manifest["drives"][0]["last_sync"] = "2026-06-01"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    # Bump the manifest's mtime far into the future too — a per-record temporal
    # signal must NOT be derived from this, or every record would "change".
    os.utime(manifest_path, (1_800_000_000, 1_800_000_000))

    changed = inv.convert(tmp_path, {"manifest": str(manifest_path)})
    after = {p: p.read_text() for p in (tmp_path / "inventory").rglob("*.md")}

    diffs = sorted(p for p in before if before[p] != after.get(p))
    expected = tmp_path / "inventory" / "drives" / "example-media.md"
    assert diffs == [expected], f"expected exactly one changed file, got {diffs}"
    assert changed == [expected], f"expected only the edited record reported, got {changed}"


def test_missing_id_raises_clear_error(tmp_path: Path):
    manifest = {"drives": [{"label": "no id drive"}]}
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="id"):
        inv.convert(tmp_path, {"manifest": str(manifest_path)})


def test_path_escaping_id_cannot_escape_lane_dir(tmp_path: Path):
    manifest = {"drives": [{"id": "../evil", "label": "evil"}]}
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        inv.convert(tmp_path, {"manifest": str(manifest_path)})
    assert not (tmp_path / "evil.md").exists()
    assert not (tmp_path.parent / "evil.md").exists()
    assert not (tmp_path / "inventory").exists() or not list(
        (tmp_path / "inventory").rglob("evil.md")
    )


def test_duplicate_ids_raise(tmp_path: Path):
    manifest = {"drives": [
        {"id": "dup-example", "label": "one"},
        {"id": "dup-example", "label": "two"},
    ]}
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="dup-example"):
        inv.convert(tmp_path, {"manifest": str(manifest_path)})


def test_pipe_in_value_does_not_break_table(tmp_path: Path):
    manifest = {"drives": [{
        "id": "pipey-example",
        "label": "Pipey Drive",
        "purpose": "movies | tv shows",
        "location": "shelf",
    }]}
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    inv.convert(tmp_path, {"manifest": str(manifest_path)})
    md = tmp_path / "inventory" / "drives" / "pipey-example.md"
    body_lines = frontmatter.load(md).content.splitlines()
    purpose_line = next(line for line in body_lines if "Purpose" in line)
    unescaped = re.findall(r"(?<!\\)\|", purpose_line)
    assert len(unescaped) == 3, f"unescaped '|' in value broke the table row: {purpose_line!r}"
    assert "movies" in purpose_line and "tv shows" in purpose_line
