#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build and inspect the runtime image this toolkit writes to a USB volume.

The image is an ISO 9660 filesystem carrying `autoexec.sh` and the runtime it
launches, encrypted independently per 512-byte sector with AES-256-CBC. The IV
is the sector index encoded as a 32-bit little-endian integer followed by 12
zero bytes, matching the cryptoloop implementation in util-linux-ng 2.14.2:

    cat KEYFILE | losetup -e aes -p 0 DEVICE IMAGE

The key is supplied by the operator and is never held in this repository.

This module builds the toolkit's own runtime image and reads back one it built.
It handles no update container: there is no trailer parser, no CRC check
against a model and version field, and no path that produces or consumes a
vendor update package.
"""

import argparse
import io
import pathlib
import struct
import subprocess
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SECTOR = 512
ISO_BLOCK = 2048
ISO_PADDING_BLOCKS = 150


def load_key(path):
    """Reproduce xgetpass followed by xstrncpy(dst, src, 32).

    Only the first line is used. xstrncpy copies at most 31 bytes and writes a
    terminating NUL byte, yielding the effective 32-byte AES key.
    """
    lines = pathlib.Path(path).read_bytes().splitlines()
    if not lines:
        raise ValueError("key file is empty")
    return lines[0][:31].ljust(32, b"\0")


def crypt(body, key, decrypt):
    """Apply AES-256-CBC independently to each 512-byte sector."""
    if len(body) % SECTOR:
        raise ValueError(f"payload is not aligned to {SECTOR} bytes")
    algorithm = algorithms.AES(key)
    output = bytearray(len(body))
    for sector, offset in enumerate(range(0, len(body), SECTOR)):
        iv = struct.pack("<I", sector & 0xFFFFFFFF) + bytes(12)
        cipher = Cipher(algorithm, modes.CBC(iv))
        operation = cipher.decryptor() if decrypt else cipher.encryptor()
        block = body[offset:offset + SECTOR]
        output[offset:offset + SECTOR] = operation.update(block) + operation.finalize()
    return bytes(output)


def read_autoexec(path, key_path):
    """Decrypt a raw autoexec image without an update trailer."""
    body = pathlib.Path(path).read_bytes()
    if not body or len(body) % SECTOR:
        raise ValueError(f"autoexec image is not aligned to {SECTOR} bytes")
    return crypt(body, load_key(key_path), True)


def autoexec_iso_metadata(plain):
    """Return the ISO volume name from crypto sector 64."""
    pvd_offset = 64 * SECTOR
    pvd = plain[pvd_offset:pvd_offset + 2048]
    if len(pvd) != 2048 or pvd[1:6] != b"CD001":
        raise ValueError("ISO 9660 signature is missing; key or image is incorrect")
    return pvd[40:72].decode("ascii", "replace").rstrip(" \0")


def cmd_verify_autoexec(args):
    plain = read_autoexec(args.file, args.key)
    volume = autoexec_iso_metadata(plain)
    print(f"Autoexec       : {len(plain):,} bytes ({len(plain) // SECTOR} sectors)")
    print(f"ISO 9660       : OK, volume {volume!r}")


def cmd_decrypt_autoexec(args):
    plain = read_autoexec(args.input, args.key)
    volume = autoexec_iso_metadata(plain)
    pathlib.Path(args.output).write_bytes(plain)
    print(f"{args.output}: {len(plain):,} bytes, ISO 9660 volume {volume!r}")


def build_autoexec_iso(source):
    """Build a portable Rock Ridge ISO from a runtime staging directory.

    pycdlib is used by the desktop builder on every supported host OS. The
    mkisofs fallback keeps the developer CLI compatible with older setups.
    """
    source = pathlib.Path(source)
    if not (source / "autoexec.sh").is_file():
        raise ValueError(f"{source}/autoexec.sh is missing")

    try:
        import pycdlib
    except ImportError:
        with tempfile.TemporaryDirectory(prefix="rx3-autoexec-") as directory:
            iso_path = pathlib.Path(directory) / "autoexec.iso"
            subprocess.run(
                ["mkisofs", "-quiet", "-R", "-V", "UsbAuto", "-o", str(iso_path), str(source)],
                check=True,
            )
            return iso_path.read_bytes()

    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, vol_ident="UsbAuto", rock_ridge="1.09")
    iso_directories = {pathlib.Path(): ""}
    directory_number = 0
    file_number = 0

    for path in sorted((item for item in source.rglob("*") if item.is_dir())):
        relative = path.relative_to(source)
        parent_iso = iso_directories[relative.parent]
        directory_number += 1
        iso_path = f"{parent_iso}/D{directory_number:07d}"
        iso.add_directory(
            iso_path=iso_path,
            rr_name=relative.name,
            file_mode=0o40555,
        )
        iso_directories[relative] = iso_path

    for path in sorted((item for item in source.rglob("*") if item.is_file())):
        relative = path.relative_to(source)
        parent_iso = iso_directories[relative.parent]
        file_number += 1
        iso_path = f"{parent_iso}/F{file_number:07d};1"
        mode = 0o100755 if path.suffix == ".sh" else 0o100644
        iso.add_file(
            str(path),
            iso_path=iso_path,
            rr_name=relative.name,
            file_mode=mode,
        )

    output = io.BytesIO()
    iso.write_fp(output)
    iso.close()
    image = bytearray(output.getvalue())
    image.extend(bytes(ISO_PADDING_BLOCKS * ISO_BLOCK))

    # Match the padded images produced by mkisofs. Some ISO readers inspect
    # sectors beyond the logical filesystem before accepting a loop image.
    volume_blocks = len(image) // ISO_BLOCK
    pvd = 16 * ISO_BLOCK
    struct.pack_into("<I", image, pvd + 80, volume_blocks)
    struct.pack_into(">I", image, pvd + 84, volume_blocks)
    return bytes(image)


def write_autoexec(source, output, key_path):
    """Build, encrypt, and write a raw autoexec image."""
    source = pathlib.Path(source)
    plain = build_autoexec_iso(source)

    if len(plain) % SECTOR:
        plain += b"\0" * (SECTOR - len(plain) % SECTOR)

    pathlib.Path(output).write_bytes(crypt(plain, load_key(key_path), False))
    return len(plain)


def cmd_autoexec(args):
    """Build an encrypted Rock Ridge ISO without an update trailer."""
    size = write_autoexec(args.dir, args.output, args.key)
    print(f"{args.output}: {size:,} bytes ({size // SECTOR} sectors)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("verify-autoexec", help="verify a raw autoexec image")
    command.add_argument("file")
    command.add_argument("--key", required=True)
    command.set_defaults(function=cmd_verify_autoexec)

    command = commands.add_parser("decrypt-autoexec", help="decrypt a raw autoexec image")
    command.add_argument("input")
    command.add_argument("output")
    command.add_argument("--key", required=True)
    command.set_defaults(function=cmd_decrypt_autoexec)

    command = commands.add_parser("autoexec", help="build autoexec.bin from a directory")
    command.add_argument("dir")
    command.add_argument("output")
    command.add_argument("--key", required=True)
    command.set_defaults(function=cmd_autoexec)

    args = parser.parse_args()
    try:
        return args.function(args) or 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
