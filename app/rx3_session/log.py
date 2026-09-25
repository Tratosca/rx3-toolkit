# SPDX-License-Identifier: MPL-2.0
"""Read back what the deck said it was running, from the log it leaves on the drive.

The runtime writes `RX3_RUNTIME/session.txt` on every insertion and keeps the
previous one beside it. That log is the only place the deck states what it
actually loaded, so it is the only honest answer to "what does this drive
support". Everything else is inference from a version number, which goes wrong
in exactly the case that matters: a drive prepared by a newer toolkit and last
played on a deck that ran an older mod.

Nothing here guesses. A capability the log does not mention is reported as
unknown, not as absent.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field


RUNTIME_DIRECTORY = "RX3_RUNTIME"
SESSION_NAME = "session.txt"
PREVIOUS_NAME = "session-previous.txt"

# A log is a few kilobytes of prose. A file far past that is not one, and is not
# worth reading into memory to find out.
MAXIMUM_BYTES = 1 << 20

MODULE_LINE = "loaded modules:"
# What each module says once it is up. A line is a claim by the deck itself,
# which is the point: the module that could not prepare never writes one.
STEMS_PAD_LINE = "SLIP LOOP:"
# Present only once the deck can load a third and fourth container beside the
# vocal. Until the deck side lands, a drive carrying `.rx3drums` files is a
# drive whose extra containers nothing will read.
MULTI_STEM_MARKER = "6=bass"
SAMPLE_MODE_LINE = "SAMPLE pad modes:"
SAMPLE_SHIFT_LINE = "SAMPLE shift.silence:"

READY = "ready"
# The module loaded but said nothing about this particular capability, which is
# what an older build of the same module looks like.
DECLARED = "declared"
DISABLED = "disabled"
ABSENT = "absent"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Session:
    """One insertion, as the deck described it."""

    modules: tuple[str, ...] = field(default=())
    # False when the log carried no module list at all, which is the difference
    # between "this deck ran nothing" and "this file tells us nothing".
    listed: bool = False
    disabled: tuple[str, ...] = field(default=())
    source: pathlib.Path | None = None

    stems: str = UNKNOWN
    multi_stems: str = UNKNOWN
    samples: str = UNKNOWN
    sample_modes: str = UNKNOWN
    shift_silence: str = UNKNOWN

    def supports(self, capability: str) -> bool:
        """Whether the deck will act on this, with unknown counting as no.

        A caller writing files to a drive needs one answer, and the safe one is
        to treat what has not been declared as not there.
        """
        return getattr(self, capability, UNKNOWN) == READY

    def loaded(self, module: str) -> bool:
        return module in self.modules


def _capability(present: bool, module_loaded: bool, module_disabled: bool) -> str:
    if module_disabled:
        return DISABLED
    if present:
        return READY
    if module_loaded:
        return DECLARED
    return ABSENT


def parse(text: str, source: pathlib.Path | None = None) -> Session:
    """Read one session log into what it says the deck can do."""
    lines = [line.strip() for line in text.splitlines()]
    modules: tuple[str, ...] = ()
    listed = False
    disabled: list[str] = []
    for line in lines:
        if line.startswith(MODULE_LINE):
            listed = True
            named = line[len(MODULE_LINE):].split()
            modules = () if named == ["none"] else tuple(named)
        # `<id> disabled: <reason>` is what a kill switch and a missing
        # dependency both write, and either way the module is not running.
        elif " disabled:" in line:
            disabled.append(line.split(" disabled:", 1)[0].strip())

    if not listed:
        # Without the list there is no way to tell a module that failed from one
        # that was never selected, so nothing is claimed about any of them.
        return Session(source=source)

    def has(prefix: str, marker: str | None = None) -> bool:
        for line in lines:
            if line.startswith(prefix) and (marker is None or marker in line):
                return True
        return False

    stems_loaded = "stems" in modules
    stems_off = "stems" in disabled
    samples_loaded = "samples" in modules
    samples_off = "samples" in disabled
    return Session(
        modules=modules,
        listed=True,
        disabled=tuple(dict.fromkeys(disabled)),
        source=source,
        stems=_capability(has(STEMS_PAD_LINE), stems_loaded, stems_off),
        multi_stems=_capability(
            has(STEMS_PAD_LINE, MULTI_STEM_MARKER), stems_loaded, stems_off
        ),
        samples=_capability(has(SAMPLE_MODE_LINE), samples_loaded, samples_off),
        sample_modes=_capability(
            has(SAMPLE_MODE_LINE), samples_loaded, samples_off
        ),
        shift_silence=_capability(
            has(SAMPLE_SHIFT_LINE), samples_loaded, samples_off
        ),
    )


def read(root: pathlib.Path) -> Session:
    """Read the most recent usable log under a drive root.

    The current log is preferred, and the previous one answers the case that
    matters in practice: a drive pulled and put straight into a computer, where
    the current log belongs to an insertion that never reached a deck.
    """
    directory = pathlib.Path(root) / RUNTIME_DIRECTORY
    for name in (SESSION_NAME, PREVIOUS_NAME):
        path = directory / name
        try:
            if not path.is_file() or path.stat().st_size > MAXIMUM_BYTES:
                continue
            session = parse(path.read_text(encoding="utf-8", errors="replace"), path)
        except OSError:
            continue
        if session.listed:
            return session
    return Session()
