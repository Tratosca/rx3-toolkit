#!/usr/bin/env python3
"""Build SAMPLES tabs from the bundled native tab frames and glyph atlas."""
from pathlib import Path
import struct
import sys
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.preview.atlas import Atlas, INACTIVE


def generate():
    assets = ROOT / 'mod/modules/core/assets'
    output = ROOT / 'mod/modules/samples/assets'
    atlas = Atlas.load(assets / 'glyph-atlas-dark.rgb565')
    glyphs = Image.new('RGB', (atlas.width('SAMPLES') + 16, atlas.cell_height), atlas.ground(INACTIVE))
    atlas.draw(glyphs, 'SAMPLES', 8, 0, INACTIVE)
    mask = ImageChops.difference(glyphs, Image.new('RGB', glyphs.size, atlas.ground(INACTIVE))).convert('L')
    mask = mask.crop(mask.getbbox()).resize((76, 15), Image.Resampling.LANCZOS)
    peak = max(mask.getextrema()[1], 1)
    mask = mask.point(lambda p: min(255, p * 255 / peak))
    for suffix in ('', '-light'):
        def read(name):
            owner = {'key-selected': 'keyshift', 'none-selected': 'keyshift',
                     'stems-selected': 'stems'}.get(name, 'core')
            path = ROOT / 'mod/modules' / owner / 'assets' / (name + suffix + '.rgb565')
            return Image.frombytes('RGB', (180, 50), path.read_bytes(), 'raw', 'BGR;16')
        neutral = read('status-none-selected')
        ground = neutral.getpixel((8, 8))
        ink = max((neutral.getpixel((x, y)) for y in range(8, 43) for x in range(5, 88)),
                  key=lambda pixel: sum(abs(pixel[i] - ground[i]) for i in range(3)))
        # Keep each theme's original border and selected fill.
        for state, template in [('selected', 'key-selected'), ('none-selected', 'none-selected'), ('beatfx-selected', 'stems-selected')]:
            out = read(template)
            left_ground = out.getpixel((8, 8))
            right_ground = out.getpixel((100, 8))
            out.paste(left_ground, (5, 8, 88, 43))
            out.paste(right_ground, (93, 8, 178, 43))
            left_ink = ground if state == 'selected' else ink
            out.paste(left_ink, (7, 17, 83, 32), mask)
            # Preserve native BEAT FX lettering, invert only its selected state.
            right = neutral.crop((93, 8, 178, 43))
            if state == 'beatfx-selected':
                delta = ImageChops.difference(right, Image.new('RGB', right.size, ground)).convert('L')
                peak = max(delta.getextrema()[1], 1)
                delta = delta.point(lambda p: min(255, p * 255 / peak))
                out.paste(ground, (93, 8, 178, 43), delta)
            else:
                out.paste(right, (93, 8))
            data = b''.join(struct.pack('<H', ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)) for r, g, b in (out.getpixel((x, y)) for y in range(50) for x in range(180)))
            (output / ('samples-' + state + suffix + '.rgb565')).write_bytes(data)


if __name__ == '__main__':
    generate()
