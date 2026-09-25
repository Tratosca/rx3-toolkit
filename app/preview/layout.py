# SPDX-License-Identifier: MPL-2.0
"""Where the controls of the pad row sit, in the computer's copy.

This is the same arithmetic as the block between the markers in
`mod/modules/core/1.19/rx3_pad_layout.h`, and it exists because the preview has
to place a control exactly where a deck would. `tests/test_module_consistency.py`
compiles that block and runs it against this one, so the two cannot drift.

Every division below is floor division over values already known to be
positive, which is what the C's unsigned division does. Signed division is
avoided on both sides: on the deck it is a call to `__aeabi_idiv`, which `rbp`
does not export.
"""

from __future__ import annotations

from dataclasses import dataclass

# The row, in the pad window's own coordinates.
GROUND_TOP = 17
GROUND_BOTTOM = 63
CTRL_TOP = 21
CTRL_BOTTOM = 59
GROUND_BLEED = 4

DECK_ORIGIN = 19
DECK_SPAN = 595
SCREEN_ORIGIN = 20
SCREEN_SPAN = 1240
DECK_STRIDE = 640

LOCAL_TO_SCREEN_Y = 500
TOUCH_TOP = CTRL_TOP + LOCAL_TO_SCREEN_Y
TOUCH_BOTTOM = CTRL_BOTTOM + LOCAL_TO_SCREEN_Y

CELL_MAX = 8

STEP_END_MIN = 40
STEP_END_MAX = 96
STEP_INNER_GAP = 6
STEP_VALUE_MIN = 16

# The gap between controls, by how many there are. See the C for why the first
# five are measurements and not a formula.
GAP = (0, 0, 19, 17, 13, 11, 11, 9, 9)


@dataclass(frozen=True)
class Cell:
    x1: int
    x2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1 + 1


def solve(weights, origin: int = DECK_ORIGIN, span: int = DECK_SPAN) -> list[Cell]:
    """Lay len(weights) cells across span, in proportion to their weights."""
    count = len(weights)
    if count <= 0 or count > CELL_MAX:
        return []
    gap = GAP[count]
    free_width = span - gap * (count - 1)
    if free_width < count:
        return []
    shares = sum(weight or 1 for weight in weights)
    unit = free_width // shares
    spare = free_width - unit * shares

    cells: list[Cell] = []
    x = origin
    for index, weight in enumerate(weights):
        width = unit * (weight or 1)
        # The pixels that did not divide go to the last cells, so the row ends
        # on origin + span - 1 whatever the count.
        if index >= count - spare:
            width += 1
        cells.append(Cell(x, x + width - 1))
        x += width + gap
    return cells


def stepper_parts(cell: Cell) -> list[Cell]:
    """Decrement, value, increment."""
    width = cell.width
    end = width >> 2
    end = max(end, STEP_END_MIN)
    end = min(end, STEP_END_MAX)
    if end * 2 + STEP_INNER_GAP * 2 + STEP_VALUE_MIN > width:
        end = (width - STEP_INNER_GAP * 2 - STEP_VALUE_MIN) >> 1
        end = max(end, 8)
    left = Cell(cell.x1, cell.x1 + end - 1)
    right = Cell(cell.x2 - end + 1, cell.x2)
    middle = Cell(left.x2 + 1 + STEP_INNER_GAP, right.x1 - 1 - STEP_INNER_GAP)
    return [left, middle, right]


def hit(cells, x: int) -> int:
    """Which cell an x lands on, or -1 for the gap between two."""
    for index, cell in enumerate(cells):
        if cell.x1 <= x <= cell.x2:
            return index
    return -1


def slider_value(cell: Cell, x: int, maximum: int) -> int:
    """Where a slider sits when the finger is at x, rounded to nearest."""
    if maximum <= 0 or cell.width <= 1:
        return 0
    if x <= cell.x1:
        return 0
    if x >= cell.x2:
        return maximum
    travel = cell.width - 1
    return ((x - cell.x1) * maximum + travel // 2) // travel


def slider_x(cell: Cell, value: int, maximum: int) -> int:
    """The inverse, for drawing the filled part of a track."""
    if maximum <= 0 or cell.width <= 1:
        return cell.x1
    if value <= 0:
        return cell.x1
    if value >= maximum:
        return cell.x2
    travel = cell.width - 1
    return cell.x1 + (value * travel + maximum // 2) // maximum
