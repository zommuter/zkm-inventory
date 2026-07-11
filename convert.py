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
from pathlib import Path

PLUGIN_NAME = "inventory"
PLUGIN_VERSION = "0.1.0"

ProgressCallback = Callable[[int, int | None, str], None]


def convert(store_path: Path, config: dict, *, progress: ProgressCallback | None = None) -> list[Path]:
    """Render the inventory manifest into ``inventory/{drives,devices}/<id>.md``.

    Returns the list of newly created/updated .md paths. Re-running against an
    unchanged manifest is a git no-op (records are keyed by their stable ``id``).

    NOT YET IMPLEMENTED — the executor implements the drives lane (ROADMAP INV1,
    id:82a2) and the devices lane (ROADMAP INV2, id:5697) against the red tests
    in ``tests/test_inventory.py``.
    """
    raise NotImplementedError(
        "zkm-inventory convert() is a handoff skeleton — implement the drives "
        "lane (ROADMAP INV1 id:82a2) and devices lane (ROADMAP INV2 id:5697); "
        "make tests/test_inventory.py green."
    )
