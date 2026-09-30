#!/usr/bin/env python3
"""Extend the native KEY/STEMS artwork into one full-width feature tab."""
from pathlib import Path
from struct import pack
from PIL import Image

MODULES = Path(__file__).resolve().parents[1] / "mod/modules"

def assets(name):
    owner = "stems" if "stems" in name else "keyshift"
    return MODULES / owner / "assets"


def read(name):
    return Image.frombytes("RGB", (180, 50), (assets(name) / name).read_bytes(),
                           "raw", "BGR;16")


def write(name, image):
    pixels = bytearray()
    for red, green, blue in image.get_flattened_data():
        pixels += pack("<H", (red >> 3) << 11 | (green >> 2) << 5 | (blue >> 3))
    (assets(name) / name).write_bytes(pixels)


for light in (False, True):
    suffix = "-light" if light else ""
    for feature in ("key", "stems"):
        for state in ("none", "selected"):
            original = ("none-selected" if state == "none" else
                        feature + "-selected") + suffix + ".rgb565"
            source = read(original)
            image = source.copy()
            # Retain the native outer frame and the original fill texture.
            # The narrow untouched strip contains no lettering in either half.
            sample_x = 8 if feature == "key" else 94
            for y in range(4, 46):
                for x in range(4, 176):
                    image.putpixel((x, y), source.getpixel((sample_x + (x - 4) % 8, y)))
                # The right-hand native tab has no outer edge when selected.
                image.putpixel((176, y), source.getpixel((3, y)))
                image.putpixel((177, y), source.getpixel((2, y)))
            # Copy the firmware's own glyphs without stretching the typeface.
            label = (25, 12, 66, 40) if feature == "key" else (101, 12, 170, 40)
            glyphs = source.crop(label)
            image.paste(glyphs, ((180 - glyphs.width) // 2, label[1]))
            write(f"single-{feature}-{state}{suffix}.rgb565", image)
