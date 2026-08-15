"""Convert the emulator's mmap-backed framebuffer to a portable PNG.

Two paths, deliberately. The stdlib path has no dependencies, so a clean clone
always produces the `framebuffer.png` that `report.json` cites -- but it is a
per-pixel Python loop over 921 600 pixels and cannot drive a live window. When
Pillow is importable the same unpacking runs in C, which is what makes the
emulator window watchable.

The fast path is an accelerator and nothing else: it decodes and counts, while
the PNG itself is always written by `encode_png` here, so the archived bytes do
not depend on whether Pillow happens to be installed. `tests/test_rx3_emulator`
pins the two paths to the same output.
"""

from __future__ import annotations

import json
import pathlib
import struct
import zlib


try:  # Optional accelerator. Absence is a slower window, never a failure.
    from PIL import Image as _Image, ImageChops as _ImageChops
except ImportError:  # pragma: no cover - exercised by the no-Pillow path
    _Image = None
    _ImageChops = None


# Pillow's `BGR;16` unpacks little-endian 5-6-5 with red in the high bits, and
# `BGRX` matches the shim's BGRA8888 with the alpha byte dropped like
# `_bgra_row`. `BGRX` is exact; `BGR;16` is not. Pillow widens each short
# channel with its own rounding, which disagrees with the high-bit replication
# `_rgb565_row` performs on 15 of the 32 red and blue levels and 30 of the 64
# green ones -- differences of one unit, invisible on screen but enough to move
# the archived PNG.
_RAW_MODES = {16: "BGR;16", 32: "BGRX"}


def _expansion_table() -> list[int]:
    """Invert Pillow's 5-6-5 widening so it agrees with `_rgb565_row` exactly.

    Measured rather than hard-coded: every channel mapping is injective, so
    feeding Pillow one pixel per level and reading back what it produced gives
    an exact inverse -- and one that stays exact if Pillow ever changes its
    rounding. Levels Pillow never emits map to themselves and are never hit.
    """
    table = list(range(256)) * 3
    for band, (shift, bits) in enumerate(((11, 5), (5, 6), (0, 5))):
        levels = 1 << bits
        probe = struct.pack("<%dH" % levels, *(level << shift for level in range(levels)))
        unpacked = _Image.frombytes(
            "RGB", (levels, 1), probe, "raw", _RAW_MODES[16], levels * 2, 1
        ).tobytes()
        for level in range(levels):
            expanded = (
                (level << 3) | (level >> 2) if bits == 5 else (level << 2) | (level >> 4)
            )
            table[band * 256 + unpacked[level * 3 + band]] = expanded
    return table


_EXPAND_565 = _expansion_table() if _Image is not None else None


class FramebufferError(ValueError):
    """The framebuffer metadata or payload is incomplete."""


def read_metadata(path: pathlib.Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="ascii"))
        values = {
            name: int(raw[name])
            for name in ("width", "height", "virtual_height", "bpp", "stride", "yoffset")
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FramebufferError(f"invalid framebuffer metadata: {error}") from error
    if values["width"] <= 0 or values["height"] <= 0:
        raise FramebufferError("invalid framebuffer dimensions")
    if values["bpp"] not in (16, 32):
        raise FramebufferError(f"unsupported framebuffer depth: {values['bpp']}")
    minimum_stride = values["width"] * (values["bpp"] // 8)
    if values["stride"] < minimum_stride:
        raise FramebufferError("framebuffer stride is shorter than one visible row")
    if values["yoffset"] < 0 or values["yoffset"] + values["height"] > values["virtual_height"]:
        raise FramebufferError("visible framebuffer page is outside virtual memory")
    return values


def _rgb565_row(source: bytes, width: int) -> bytes:
    output = bytearray(width * 3)
    for pixel in range(width):
        value = source[pixel * 2] | (source[pixel * 2 + 1] << 8)
        red = (value >> 11) & 0x1F
        green = (value >> 5) & 0x3F
        blue = value & 0x1F
        target = pixel * 3
        output[target] = (red << 3) | (red >> 2)
        output[target + 1] = (green << 2) | (green >> 4)
        output[target + 2] = (blue << 3) | (blue >> 2)
    return bytes(output)


def _bgra_row(source: bytes, width: int) -> bytes:
    output = bytearray(width * 3)
    for pixel in range(width):
        source_offset = pixel * 4
        target = pixel * 3
        output[target] = source[source_offset + 2]
        output[target + 1] = source[source_offset + 1]
        output[target + 2] = source[source_offset]
    return bytes(output)


def _visible_page(raw_path: pathlib.Path, metadata: dict[str, int]) -> bytes:
    """The bytes of the page currently being scanned out, bounds-checked.

    DirectFB may be mid-flip while this file is read, which is why a short
    payload is an expected condition rather than a bug.
    """
    payload = raw_path.read_bytes()
    stride = metadata["stride"]
    start = metadata["yoffset"] * stride
    end = start + metadata["height"] * stride
    if len(payload) < end:
        raise FramebufferError(
            f"incomplete framebuffer: got {len(payload)} bytes, need {end}"
        )
    return payload[start:end]


def _decode_slow(page: bytes, metadata: dict[str, int]) -> bytes:
    stride = metadata["stride"]
    width = metadata["width"]
    converter = _rgb565_row if metadata["bpp"] == 16 else _bgra_row
    return b"".join(
        converter(page[row * stride : (row + 1) * stride], width)
        for row in range(metadata["height"])
    )


def _decode_fast(page: bytes, metadata: dict[str, int]):
    """Unpack the page into a Pillow RGB image, or None when Pillow is absent."""
    if _Image is None:
        return None
    image = _Image.frombytes(
        "RGB",
        (metadata["width"], metadata["height"]),
        page,
        "raw",
        _RAW_MODES[metadata["bpp"]],
        metadata["stride"],
        1,
    )
    return image.point(_EXPAND_565) if metadata["bpp"] == 16 else image


def read_rgb(raw_path: pathlib.Path, metadata: dict[str, int]) -> bytes:
    page = _visible_page(raw_path, metadata)
    image = _decode_fast(page, metadata)
    return _decode_slow(page, metadata) if image is None else image.tobytes()


def _count_non_black(rgb: bytes, image, pixels: int) -> int:
    if image is not None:
        # A pixel is black only when all three channels are zero, so the
        # per-pixel maximum answers it in one histogram bucket.
        red, green, blue = image.split()
        brightest = _ImageChops.lighter(_ImageChops.lighter(red, green), blue)
        return pixels - brightest.histogram()[0]
    black = sum(
        1
        for offset in range(0, len(rgb), 3)
        if rgb[offset] == rgb[offset + 1] == rgb[offset + 2] == 0
    )
    return pixels - black


class Frame:
    """One decoded visible page, plus the metadata it was decoded under."""

    __slots__ = ("metadata", "rgb", "non_black_pixels")

    def __init__(self, metadata: dict[str, int], rgb: bytes, non_black_pixels: int):
        self.metadata = metadata
        self.rgb = rgb
        self.non_black_pixels = non_black_pixels

    @property
    def width(self) -> int:
        return self.metadata["width"]

    @property
    def height(self) -> int:
        return self.metadata["height"]

    @property
    def pixels(self) -> int:
        return self.width * self.height

    def ppm(self) -> bytes:
        """Binary PPM, which Tk's PhotoImage accepts straight from memory.

        This is the whole point of the fast path: no zlib, no temporary file
        and no second decode between rbp's pixels and the window.
        """
        return b"P6\n%d %d\n255\n" % (self.width, self.height) + self.rgb

    def summary(self, png_path: pathlib.Path | None = None) -> dict[str, int | str]:
        report: dict[str, int | str] = {
            **self.metadata,
            "pixels": self.pixels,
            "non_black_pixels": self.non_black_pixels,
        }
        if png_path is not None:
            report["png"] = str(png_path)
        return report


def read_frame(raw_path: pathlib.Path, metadata_path: pathlib.Path) -> Frame:
    metadata = read_metadata(metadata_path)
    page = _visible_page(raw_path, metadata)
    image = _decode_fast(page, metadata)
    rgb = _decode_slow(page, metadata) if image is None else image.tobytes()
    pixels = metadata["width"] * metadata["height"]
    return Frame(metadata, rgb, _count_non_black(rgb, image, pixels))


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_png(rgb: bytes, width: int, height: int) -> bytes:
    expected = width * height * 3
    if len(rgb) != expected:
        raise FramebufferError(f"RGB payload is {len(rgb)} bytes, expected {expected}")
    stride = width * 3
    scanlines = b"".join(
        b"\x00" + rgb[offset : offset + stride]
        for offset in range(0, len(rgb), stride)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, 6))
        + _png_chunk(b"IEND", b"")
    )


def write_png(frame: Frame, output_path: pathlib.Path) -> None:
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_bytes(encode_png(frame.rgb, frame.width, frame.height))
    temporary.replace(output_path)


def export_png(
    raw_path: pathlib.Path, metadata_path: pathlib.Path, output_path: pathlib.Path
) -> dict[str, int | str]:
    frame = read_frame(raw_path, metadata_path)
    write_png(frame, output_path)
    return frame.summary(output_path)
