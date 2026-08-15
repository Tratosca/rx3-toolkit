# Pioneer's bitmap font format

Reverse engineered from `gui/pset/fontdata/*.bin` in firmware 1.19. Nothing here
requires the firmware to read -- the format is described in full -- but the files
themselves are Pioneer's and are never committed.

## The typeface

The deck's face is **Helvetica Neue LT W1G** (Linotype). This is named rather
than guessed, from two independent artefacts that agree:

- rekordbox 7 declares `font-family="HelveticaNeueLTW1G"` in its own skin SVGs
  (`Contents/Resources/skins/{zoomReset,Grid_Button_Tap,Grid_Button_11Bars}.svg`).
- W1G is Linotype's "World 1 Glyph set" -- Latin, Greek and Cyrillic -- which is
  exactly the repertoire of `NS_FONT_ID_ISO8859_w.bin`: 422 glyphs covering
  ASCII, Latin-1, Greek, Cyrillic and the euro sign.

rekordbox references the family but does not ship it; a scan of all 2144 files in
the bundle finds four real sfnt headers, all Chromium's `SpiderSymbol` icon font.
The face is licensed and not redistributable, which is why
`tools/rx3_assets/build_labels.py` approximates it with the system cut rather
than bundling it.

## Container layout

There is no header, no offset table and no metrics table. A font file is a flat
array of fixed-size cells, one per glyph, in codepoint order.

| Field | Value for `NS_FONT_ID_ISO8859_w.bin` |
| --- | --- |
| Row stride | 7 bytes |
| Cell width | 14 px (stride x 2) |
| Cell height | 27 rows |
| Cell size | 189 bytes |
| Glyph count | 422 |
| Index | `codepoint - 0x20`, so index 0 is space and ASCII is direct |

Pixels are **4 bpp**, two per byte, high nibble first (leftmost pixel). The value
is coverage 0..15 -- straight anti-aliasing, no palette. This is the source of
the sixteen grey levels observed in `imagedata.dat` artwork, and it is why
`build_labels.py` quantises to sixteen steps.

The file is 79758 bytes where 422 cells would be 79800. The last glyph's six
trailing all-zero rows are simply not written; a reader must zero-fill the tail.

Sibling files use the same scheme with a different stride -- `NS_FONT_ID_JISX0201_w.bin`
is 3 bytes -- so this is a house format with one fixed size per file, not a
one-off.

### Reading a glyph

```python
STRIDE, HEIGHT, WIDTH = 7, 27, 14
CELL = STRIDE * HEIGHT

def coverage(data, codepoint):
    """Return HEIGHT rows of WIDTH coverage values, 0..15."""
    base = (codepoint - 0x20) * CELL
    rows = []
    for r in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            byte = data[base + r * STRIDE + x // 2] if base + r * STRIDE + x // 2 < len(data) else 0
            row.append(byte >> 4 if x % 2 == 0 else byte & 0x0F)
        rows.append(row)
    return rows
```

## What is *not* in the file

Advance widths. The file carries only bitmaps, and glyphs sit left-aligned in the
cell with the remainder blank, so a proportional advance has to come from
somewhere else. In `rbp` it comes from the font library's metrics entry point,
reached through a table that is populated at runtime:

```
FONT_GetCharMetrics @0025dc68  ->  (*(s_apstFontLib + lib*0x28 + 0x1c))(...)
FONT_GetCharGlyph   @0025dcb0  ->  (*(s_apstFontLib + lib*0x28 + 0x20))(...)
s_apstFontLib       @0257d1a8
FONT_AddLib         @0025d860   (no in-binary callers)
```

`FONT_AddLib` has no static caller and `s_apstFontLib` lives in writable memory,
so the backend cannot be identified by cross-reference alone -- recovering the
width table means observing it live rather than reading it out. Deriving the
advance from the ink extent plus a fixed side bearing is a usable approximation
but is visibly tight on pairs like `Y -` and `+1`.

The chain that reaches these, for anyone picking this up:

```
NS_FontTable_CreateFontTable @001ce6b8
  -> GS_FONT_Create          @001a14ec
  -> DS_Task_SetupFont       @001b1a58
  -> DS_MIF_SetupFont        @001b0974
  -> DS_HW_SetupFont         @001a8f48
  -> FONT_Setup              @0025db94
NS_FontTable_GetFontData     @001ce21c   (data pointer, size, size) per font id
```

## Two sizes, not one

`NS_FONT_ID_ISO8859_w.bin` is **not** the face used by the BEAT FX caption
artwork in `imagedata.dat`. Measured on `FILTER`:

| Source | Ink extent |
| --- | --- |
| `imagedata.dat` id `0x1442` | 76 x 16 |
| `NS_FONT_ID_ISO8859_w.bin` | 39 x 19 |

The `.bin` is a condensed cut at roughly half the width and greater height. It is
what `rbp` draws live -- browse lists, track titles -- while the captions beside
the KEY/STEMS controls are pre-rendered artwork in the normal width. Mod labels
that sit in the BEAT FX row should match the artwork, not the `.bin`.

## Fitting against Pioneer's own glyphs

The fourteen BEAT FX captions (`0x1439`..`0x1470`, four variants each: dim or
white on black or blue) segment cleanly into individual letters by blank-column
runs, yielding ground truth for nineteen capitals: `A B C E F G H I K L N O P R
S T V X Y`. Cap height is a consistent 16 px with `O C G S` overshooting to 17,
which is itself confirmation that these are real font renderings rather than
hand artwork.

Sweeping face against size over that ground truth, as mean absolute per-pixel
error:

| Face | Size | MAE |
| --- | --- | --- |
| Regular | 22 | **29.3** |
| Regular | 21 | 38.0 |
| Medium | 22 | 40.9 |
| Light | 22 | 41.9 |
| Light | 24 | 61.3 |

`build_labels.py` uses Regular 22. The earlier Light 24 was fitted on whole-word
ink extents, which is a weaker signal because weight and size can trade off
against each other and still match a bounding box.
