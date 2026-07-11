"""Pytest configuration for the zkm-inventory worktree.

Ensures that `import convert` resolves to this worktree's convert.py rather than
the editable-install path that the .pth file adds to sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).parent.resolve())
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
