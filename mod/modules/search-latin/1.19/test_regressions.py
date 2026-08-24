# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import hashlib
import re

HERE = Path(__file__).resolve().parent
MODULE = HERE / "module.sh"

PATCH_RE = re.compile(
    r"^register_patch\s+(\d+)\s+'([^']+)'\s+'([^']+)'\s+(\S+)\s*$",
    re.MULTILINE,
)


def _decode_octal(value: str) -> bytes:
    chunks = re.findall(r"\\([0-7]{3})", value)
    assert "".join("\\" + item for item in chunks) == value
    return bytes(int(item, 8) for item in chunks)


def _patches():
    text = MODULE.read_text(encoding="utf-8")
    result = []
    for match in PATCH_RE.finditer(text):
        offset = int(match.group(1))
        stock = _decode_octal(match.group(2))
        patched = _decode_octal(match.group(3))
        result.append((offset, stock, patched))
    return result


def test_search_latin_patch_table_is_complete_and_guarded():
    patches = _patches()
    assert len(patches) == 78
    assert len({offset for offset, _, _ in patches}) == len(patches)
    assert all(offset % 4 == 0 for offset, _, _ in patches)
    assert all(len(stock) == 4 and len(patched) == 4 for _, stock, patched in patches)
    assert all(stock != patched for _, stock, patched in patches)
    assert min(offset for offset, _, _ in patches) == 1426684
    assert max(offset for offset, _, _ in patches) == 1426996


def test_search_latin_patch_table_matches_validated_v14_definition():
    payload = b"".join(
        offset.to_bytes(4, "little") + stock + patched
        for offset, stock, patched in _patches()
    )
    assert hashlib.sha1(payload).hexdigest() == "4eca9ea36d1726d2a2a56c504168a575359ea5a8"


def test_scaffold_todos_are_gone():
    for name in ("module.sh", "manifest.json", "README.md"):
        assert "TODO" not in (HERE / name).read_text(encoding="utf-8")
