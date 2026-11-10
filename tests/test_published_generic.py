"""RED spec for INV7 (id:a124): tracked files stay published-generic (this repo is PUBLIC).

roadmap:a124 -- no tracked file may carry a real user's home/media-mount path or a real
filesystem UUID. The checks match SHAPES, never the real values, so this test itself
publishes nothing. Placeholders that pass: `/home/user/...`, `/run/media/$USER/...`,
`<user>`, and UUIDs / 16-hex NTFS serials made of at most two distinct hex digits
(`00000000-0000-...`, `AAAA...`). Disk serials have no fixed shape; review catches those.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# A real-looking account name directly under a home or media-mount prefix, with or
# without the leading slash (`home/<name>/Videos` relative to a mounted root counts too).
_USER_PATH = re.compile(
    r"(?<![\w.-])/?(?:home|run/media)/"
    r"(?!user\b|<user>|\$USER\b|\$\{USER\}|example\b)[a-z][\w.-]*/"
)
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_NTFS_SERIAL = re.compile(r"\b[0-9A-F]{16}\b")

# Lockfiles are machine-generated (hashes, registry URLs) and carry no owner data.
_SKIP = {"uv.lock"}

# This file IS scanned, except the body of its own triangulation test, which spells out
# made-up real-LOOKING values on purpose (owner ruling 2026-11-10: narrow the old
# whole-file self-skip, so a real value pasted anywhere else here is still caught).
_SELF = "tests/test_published_generic.py"
_SELF_EXEMPT_FUNC = "test_shape_checks_flag_real_looking_values_and_spare_placeholders"


def _self_exempt_lines() -> range:
    """1-based line range of the triangulation test's definition in this file."""
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _SELF_EXEMPT_FUNC:
            return range(node.lineno, (node.end_lineno or node.lineno) + 1)
    raise AssertionError(f"{_SELF_EXEMPT_FUNC} not found; the self-exemption would be void")


def _tracked_text_files() -> list[tuple[Path, str]]:
    if not shutil.which("git"):
        pytest.skip("git not available")
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    files = []
    for rel in out.split("\0"):
        if not rel or rel in _SKIP:
            continue
        path = REPO / rel
        try:
            files.append((path, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # binary or deleted-in-worktree: nothing textual to leak
    return files


def _is_placeholder(token: str) -> bool:
    return len(set(token.replace("-", "").lower())) <= 2


def _line_hits(line: str) -> list[str]:
    """Kinds of real-looking identifier on one line (empty list = clean)."""
    kinds = []
    if _USER_PATH.search(line):
        kinds.append("user path")
    kinds += ["uuid" for m in _UUID.finditer(line) if not _is_placeholder(m.group(0))]
    kinds += [
        "16-hex serial" for m in _NTFS_SERIAL.finditer(line) if not _is_placeholder(m.group(0))
    ]
    return kinds


def _findings() -> list[str]:
    hits = []
    exempt = _self_exempt_lines()
    for path, text in _tracked_text_files():
        rel = path.relative_to(REPO)
        for lineno, line in enumerate(text.splitlines(), 1):
            if str(rel) == _SELF and lineno in exempt:
                continue
            hits += [f"{rel}:{lineno}: {kind}" for kind in _line_hits(line)]
    return hits


def test_self_exemption_covers_only_the_triangulation_test():
    # roadmap:a124 follow-up (owner 2026-11-10): the guard's own file is scanned except one
    # function. The exempt range must be that function and nothing more.
    exempt = _self_exempt_lines()
    source = Path(__file__).read_text(encoding="utf-8").splitlines()
    assert source[exempt.start - 1].startswith(f"def {_SELF_EXEMPT_FUNC}(")
    assert len(exempt) < len(source) // 4, "exemption grew beyond the triangulation test"
    assert _SELF not in _SKIP


def test_a_real_looking_value_outside_the_exemption_would_be_caught():
    # Built at runtime so this line itself never contains the literal it checks.
    fake_uuid = "-".join(["3f2a9c1e", "7b4d", "4e8a", "9c2f", "1a2b3c4d5e6f"])
    assert _line_hits(f'uuid: "{fake_uuid}"') == ["uuid"]
    assert _line_hits("path " + "/home/" + "alice" + "/notes") == ["user path"]


def test_no_tracked_file_carries_real_user_paths_or_uuids():
    hits = _findings()
    assert hits == [], "real identifiers in tracked files (PUBLIC repo):\n" + "\n".join(hits)


def test_shape_checks_flag_real_looking_values_and_spare_placeholders():
    # Triangulation: the regexes must fire on real-looking values and not on placeholders.
    assert _USER_PATH.search("/home/alice/src/x")
    assert _USER_PATH.search('MOUNTPOINT="/run/media/bob/Data"')
    assert not _USER_PATH.search("/home/user/src/x")
    assert not _USER_PATH.search("/run/media/$USER/MEDIA-2")
    assert _USER_PATH.search("index `home/carol/Videos`, not `/usr`")
    assert not _USER_PATH.search("Users/<user>/Documents and home/<user>/Videos")
    assert not _USER_PATH.search("inventory/home/devices.md")
    assert not _is_placeholder("3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f")
    assert _is_placeholder("00000000-0000-0000-0000-000000000000")
    assert _is_placeholder("AAAAAAAAAAAAAAAA")
    assert not _is_placeholder("9C4F1B2E7A3D5F60")
