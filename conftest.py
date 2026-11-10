"""Pytest configuration for the zkm-inventory worktree.

Ensures that `import convert` resolves to this worktree's convert.py rather than
the editable-install path that the .pth file adds to sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).parent.resolve())
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_lsblk_serials: run finddump._enumerate_serials itself (still against a "
        "monkeypatched subprocess), instead of the hermetic {} stub",
    )


@pytest.fixture(autouse=True)
def _no_real_disk_serials(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Hermetic default (roadmap:3423): no test may shell out to the real `lsblk` for
    disk serials. `raising=False` keeps this a no-op before `_enumerate_serials` exists."""
    if request.node.get_closest_marker("real_lsblk_serials"):
        return
    import finddump

    monkeypatch.setattr(finddump, "_enumerate_serials", lambda: {}, raising=False)
