"""Convert the emulator's mmap-backed framebuffer to a portable PNG."""

from __future__ import annotations

import json
import pathlib
import struct
import zlib


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


def read_rgb(raw_path: pathlib.Path, metadata: dict[str, int]) -> bytes:
    payload = raw_path.read_bytes()
    stride = metadata["stride"]
    height = metadata["height"]
    start = metadata["yoffset"] * stride
    end = start + height * stride
    if len(payload) < end:
        raise FramebufferError(
            f"incomplete framebuffer: got {len(payload)} bytes, need {end}"
        )
    width = metadata["width"]
    converter = _rgb565_row if metadata["bpp"] == 16 else _bgra_row
    rows = []
    for row in range(height):
        offset = start + row * stride
        rows.append(converter(payload[offset : offset + stride], width))
    return b"".join(rows)


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


def export_png(
    raw_path: pathlib.Path, metadata_path: pathlib.Path, output_path: pathlib.Path
) -> dict[str, int | str]:
    metadata = read_metadata(metadata_path)
    rgb = read_rgb(raw_path, metadata)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_bytes(encode_png(rgb, metadata["width"], metadata["height"]))
    temporary.replace(output_path)
    black = sum(
        1
        for offset in range(0, len(rgb), 3)
        if rgb[offset] == rgb[offset + 1] == rgb[offset + 2] == 0
    )
    pixels = metadata["width"] * metadata["height"]
    return {
        **metadata,
        "pixels": pixels,
        "non_black_pixels": pixels - black,
        "png": str(output_path),
    }

