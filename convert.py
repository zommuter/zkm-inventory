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

Amender-preserving idempotence (ROADMAP id:86b5): the md *body* here is
single-writer (this plugin owns it entirely), but the frontmatter is
multi-writer per the amendment contract — an amender (e.g. zkm-ner) may write
back extra ``entities[]``/``tags`` between two ``zkm convert inventory`` runs.
``_write_record`` therefore reads any existing doc, PRESERVES frontmatter this
plugin doesn't own (entities outside its own ``scope:inventory.*`` namespace;
tags outside its own small status vocabulary), merges in its own freshly
rendered fields, and compares/writes the MERGED result — never a record-only
render byte-compared against a file an amender may have touched.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import frontmatter

from zkm.atomic import write_atomic

PLUGIN_NAME = "inventory"
PLUGIN_VERSION = "0.3.0"

ProgressCallback = Callable[[int, int | None, str], None]

# The devices lane's own small status vocabulary (ROADMAP INV2 id:5697). Any
# existing tag that is NOT one of these is treated as amender/foreign-owned
# and preserved verbatim; any that IS one of these is this plugin's own and
# is fully recomputed from the current record on every run.
_STATUS_TAG_VALUES = frozenset({"in-use", "idle", "dust-collecting", "retired"})


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

    drives = manifest.get("drives") or []
    devices = manifest.get("devices") or []

    drives_dir = store_path / "inventory" / "drives"
    devices_dir = store_path / "inventory" / "devices"
    drives_dir.mkdir(parents=True, exist_ok=True)
    devices_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    total = len(drives) + len(devices)
    item_num = 0

    seen_drive_ids: set[str] = set()
    for record in drives:
        item_num += 1
        rid = _validate_id(record, "drive", seen_drive_ids)
        path = _write_record(drives_dir, "drive", rid, record)
        if path is not None:
            created.append(path)
        if progress:
            progress(item_num, total, rid)

    seen_device_ids: set[str] = set()
    for record in devices:
        item_num += 1
        rid = _validate_id(record, "device", seen_device_ids)
        path = _write_record(devices_dir, "device", rid, record)
        if path is not None:
            created.append(path)
        if progress:
            progress(item_num, total, rid)

    return created


# ── id validation ───────────────────────────────────────────────────────────

def _validate_id(record: dict, kind: str, seen_ids: set[str]) -> str:
    """Validate and return ``record["id"]``; raise ValueError on any problem.

    Requires a non-empty id, rejects anything that could escape the lane
    directory (path separators, ``..``), and rejects duplicates within the
    same lane.
    """
    rid = record.get("id")
    if rid is None or not str(rid).strip():
        raise ValueError(
            f"inventory manifest: {kind} record missing required 'id' field: {record!r}"
        )
    rid = str(rid).strip()
    if "/" in rid or "\\" in rid or ".." in rid:
        raise ValueError(
            f"inventory manifest: {kind} id {rid!r} is not a safe slug "
            "(must not contain '/', '\\', or '..')"
        )
    if rid in seen_ids:
        raise ValueError(f"inventory manifest: duplicate {kind} id {rid!r}")
    seen_ids.add(rid)
    return rid


# ── shared record -> md helper ──────────────────────────────────────────────

def _write_record(out_dir: Path, kind: str, rid: str, record: dict) -> Path | None:
    """Render *record* to ``<out_dir>/<id>.md``; return the path iff it changed.

    Preserves any amender-owned frontmatter (entities outside this plugin's
    own scope, tags outside its own status vocabulary) already present on
    disk, merging it with the freshly rendered own fields before comparing.
    """
    own_scope = f"inventory.{kind}"
    entities = _build_entities(kind, rid, record)
    body = _render_body(kind, record)

    meta: dict = {
        "source": PLUGIN_NAME,
        "processor": PLUGIN_NAME,
        "processor_version": PLUGIN_VERSION,
        "entities": entities,
    }
    record_date = _record_date(record)
    if record_date is not None:
        meta["date"] = record_date

    own_tags: list[str] = []
    if kind == "device":
        status = record.get("status")
        if status:
            own_tags = [status]
    if own_tags:
        meta["tags"] = own_tags

    out_path = out_dir / f"{rid}.md"

    if out_path.exists():
        existing = frontmatter.load(out_path)
        foreign_entities = [
            e for e in (existing.metadata.get("entities") or [])
            if e.get("scope") != own_scope
        ]
        if foreign_entities:
            meta["entities"] = [*entities, *foreign_entities]

        foreign_tags = [
            t for t in (existing.metadata.get("tags") or [])
            if t not in _STATUS_TAG_VALUES
        ]
        merged_tags = sorted({*own_tags, *foreign_tags})
        if merged_tags:
            meta["tags"] = merged_tags
        elif "tags" in meta:
            del meta["tags"]

    content = frontmatter.dumps(frontmatter.Post(body, **meta))

    if out_path.exists() and out_path.read_text(encoding="utf-8") == content:
        return None  # unchanged: idempotent no-op

    write_atomic(out_path, content)
    return out_path


def _record_date(record: dict) -> str | None:
    """Return a per-record date if the manifest supplies one, else None.

    Git is the temporal index (per-record git history); a manifest-mtime
    stamped onto every record was ROADMAP id:86b5 bug #2 and destroys that
    per-record signal. Only an explicit per-record ``date``/``added`` field
    is used, and only for that one record.
    """
    raw = record.get("date") or record.get("added")
    if raw is None:
        return None
    if hasattr(raw, "isoformat"):
        return raw.isoformat()
    return str(raw)


def _build_entities(kind: str, rid: str, record: dict) -> list[dict]:
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


def _esc_cell(value: object) -> str:
    """Escape a value for safe embedding in a single markdown table cell."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ")


def _render_body(kind: str, record: dict) -> str:
    rid = record["id"]
    if kind == "drive":
        label = record.get("label", rid)
        data_classes = record.get("data_classes") or []
        lines = [
            f"# {_esc_cell(label)}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Capacity | {_esc_cell(record.get('capacity_gb', ''))} GB |",
            f"| Purpose | {_esc_cell(record.get('purpose', ''))} |",
            f"| Data classes | {_esc_cell(', '.join(str(c) for c in data_classes))} |",
            f"| Location | {_esc_cell(record.get('location', ''))} |",
            f"| Last sync | {_esc_cell(record.get('last_sync', ''))} |",
            f"| Offsite | {_esc_cell(record.get('offsite', ''))} |",
            "",
        ]
        return "\n".join(lines)

    # device
    model = record.get("model", rid)
    lines = [
        f"# {_esc_cell(model)}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Kind | {_esc_cell(record.get('kind', ''))} |",
        f"| Location | {_esc_cell(record.get('location', ''))} |",
        f"| Status | {_esc_cell(record.get('status', ''))} |",
        f"| Purpose | {_esc_cell(record.get('purpose', ''))} |",
        "",
    ]
    return "\n".join(lines)
