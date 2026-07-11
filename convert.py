"""zkm-inventory — convert a hand-authored asset-inventory manifest to markdown.

Reads a single YAML manifest describing external drives and hardware devices
(RPis / IoT / etc.) and renders one searchable ``inventory/<lane>/<id>.md`` per
record, with typed ``entities[]`` so ``zkm search`` can locate an asset.

Two v1 lanes (both manifest-driven, no git-annex required):
  - **drives**   -> ``inventory/drives/<id>.md``   (scope:inventory.drive)
  - **devices**  -> ``inventory/devices/<id>.md``  (scope:inventory.device)

A third **find-dump drive-content index** lane (lane-c, fast-follow, git-annex
independent) is scoped in ROADMAP.md id:46b6 and NOT implemented here.

The git-annex redundancy-enrichment seam for the drives lane is DORMANT (0
annex-managed drives today) — see ARCHITECTURE.md. sync != backup: the manifest
owns ``last_sync`` freshness; git-annex (later) owns copy-count redundancy.

See docs/plugin-spec.md in the zkm core repo for the full plugin contract, and
``../../docs/meeting-notes/2026-07-11-2132-inventory-data-scope.md`` for scope.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import frontmatter

from zkm.atomic import write_atomic

PLUGIN_NAME = "inventory"
PLUGIN_VERSION = "0.2.0"

ProgressCallback = Callable[[int, int | None, str], None]


def convert(store_path: Path, config: dict, *, progress: ProgressCallback | None = None) -> list[Path]:
    """Render the inventory manifest into ``inventory/{drives,devices}/<id>.md``.

    Returns the list of newly created/updated .md paths. Re-running against an
    unchanged manifest is a git no-op (records are keyed by their stable ``id``).
    """
    manifest_path = Path(config["manifest"])
    if not manifest_path.is_absolute():
        manifest_path = store_path / manifest_path
    if not manifest_path.exists():
        raise FileNotFoundError(f"inventory manifest not found: {manifest_path}")

    import yaml  # deferred: keep module import light

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    date_str = _iso_local(manifest_path.stat().st_mtime)

    drives = manifest.get("drives") or []
    devices = manifest.get("devices") or []

    drives_dir = store_path / "inventory" / "drives"
    devices_dir = store_path / "inventory" / "devices"
    drives_dir.mkdir(parents=True, exist_ok=True)
    devices_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    total = len(drives) + len(devices)
    item_num = 0

    for record in drives:
        item_num += 1
        path = _write_record(drives_dir, "drive", record, date_str)
        if path is not None:
            created.append(path)
        if progress:
            progress(item_num, total, str(record.get("id", "")))

    for record in devices:
        item_num += 1
        path = _write_record(devices_dir, "device", record, date_str)
        if path is not None:
            created.append(path)
        if progress:
            progress(item_num, total, str(record.get("id", "")))

    return created


# ── shared record -> md helper ──────────────────────────────────────────────

def _write_record(out_dir: Path, kind: str, record: dict, date_str: str) -> Path | None:
    """Render *record* to ``<out_dir>/<id>.md``; return the path iff it changed."""
    rid = record["id"]
    entities = _build_entities(kind, record)
    body = _render_body(kind, record)

    meta: dict = {
        "source": PLUGIN_NAME,
        "date": date_str,
        "processor": PLUGIN_NAME,
        "processor_version": PLUGIN_VERSION,
        "entities": entities,
    }
    if kind == "device":
        status = record.get("status")
        if status:
            meta["tags"] = [status]

    content = frontmatter.dumps(frontmatter.Post(body, **meta))

    out_path = out_dir / f"{rid}.md"
    if out_path.exists() and out_path.read_text(encoding="utf-8") == content:
        return None  # unchanged: idempotent no-op

    write_atomic(out_path, content)
    return out_path


def _build_entities(kind: str, record: dict) -> list[dict]:
    rid = record["id"]
    entities: list[dict] = []
    if kind == "drive":
        entity: dict = {"scope": "inventory.drive", "type": "drive", "value": rid}
        label = record.get("label")
        if label:
            entity["canonical"] = label
        entities.append(entity)
        location = record.get("location")
        if location:
            entities.append({"scope": "inventory.drive", "type": "place", "value": location})
    else:  # device
        entity = {"scope": "inventory.device", "type": "device", "value": rid}
        model = record.get("model")
        if model:
            entity["canonical"] = model
        entities.append(entity)
        location = record.get("location")
        if location:
            entities.append({"scope": "inventory.device", "type": "place", "value": location})
    return entities


def _render_body(kind: str, record: dict) -> str:
    rid = record["id"]
    if kind == "drive":
        label = record.get("label", rid)
        data_classes = record.get("data_classes") or []
        lines = [
            f"# {label}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Capacity | {record.get('capacity_gb', '')} GB |",
            f"| Purpose | {record.get('purpose', '')} |",
            f"| Data classes | {', '.join(str(c) for c in data_classes)} |",
            f"| Location | {record.get('location', '')} |",
            f"| Last sync | {record.get('last_sync', '')} |",
            f"| Offsite | {record.get('offsite', '')} |",
            "",
        ]
        return "\n".join(lines)

    # device
    model = record.get("model", rid)
    lines = [
        f"# {model}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Kind | {record.get('kind', '')} |",
        f"| Location | {record.get('location', '')} |",
        f"| Status | {record.get('status', '')} |",
        f"| Purpose | {record.get('purpose', '')} |",
        "",
    ]
    return "\n".join(lines)


def _iso_local(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds")
