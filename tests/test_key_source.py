# SPDX-License-Identifier: MPL-2.0
"""Getting the key from the manufacturer's package keeps exactly one thing.

Everything here runs on a package built in the test: a fake key, in a fake
filesystem, in a tar.bz2 cut in two and wrapped in Deflate64 archives the way
the real one is. No test reaches the network or sees the real key.
"""
import bz2
import dataclasses
import hashlib
import io
import pathlib
import stat
import struct
import sys
import tarfile
import tempfile
import unittest
import zlib

import inflate64

from app.localization import LocalizedError
from app.firmware import key_source


KEY = b"not-the-deck-key-0123456789abcdefghij\n"


def tar_bytes(members, mode):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def deflate64_zip(name, payload):
    """One member, Deflate64, laid out as the manufacturer's archives are."""
    deflater = inflate64.Deflater()
    body = deflater.deflate(payload) + deflater.flush()
    crc = zlib.crc32(payload)
    encoded = name.encode()
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 21, 0, 9, 0, 0x21,
                        crc, len(body), len(payload), len(encoded), 0) + encoded
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 21, 21, 0, 9, 0, 0x21,
                          crc, len(body), len(payload), len(encoded), 0, 0, 0, 0, 0, 0) + encoded
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central),
                      len(local) + len(body), 0)
    return local + body + central + end


def build_package(folder, key=KEY):
    """Two archives in `folder`, and the Source that describes them."""
    filesystem = tar_bytes([("initramfs/etc/motd", b"hello\n"),
                            ("initramfs/usr/local/pdj/aes256.key", key)], "w:gz")
    tree = tar_bytes([("pioneerdj_xdj_rx3/readme.txt", bytes(range(256)) * 400),
                      ("pioneerdj_xdj_rx3/initramfs.tar.gz", filesystem)], "w")
    stream = bz2.compress(tree)
    half = len(stream) // 2
    parts = []
    for index, piece in enumerate((stream[:half], stream[half:])):
        name = f"PART{index}.zip"
        data = deflate64_zip(f"pioneerdj_xdj_rx3.tar.bz2.0{index}", piece)
        (folder / name).write_bytes(data)
        parts.append(key_source.Part(
            url=f"https://example.invalid/{name}", name=name, size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            member=f"pioneerdj_xdj_rx3.tar.bz2.0{index}",
        ))
    return key_source.Source(
        page="https://example.invalid/",
        parts=tuple(parts),
        filesystem_member="pioneerdj_xdj_rx3/initramfs.tar.gz",
        filesystem_sha256=hashlib.sha256(filesystem).hexdigest(),
        key_member="initramfs/usr/local/pdj/aes256.key",
        key_sha256=hashlib.sha256(key_source.effective(KEY)).hexdigest(),
    )


class Served:
    """A stand-in for the manufacturer's server, reading from a folder."""

    def __init__(self, folder):
        self.folder = folder
        self.ranges = []

    def __call__(self, request):
        name = request.full_url.rsplit("/", 1)[1]
        header = request.get_header("Range")
        start = int(header[6:-1]) if header else 0
        self.ranges.append(start)
        data = (self.folder / name).read_bytes()[start:]
        response = io.BytesIO(data)
        response.status = 206 if start else 200
        return response


class KeySourceTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.scratch.name)
        self.server = root / "server"
        self.server.mkdir()
        self.home = root / "home"
        self.source = build_package(self.server)

    def tearDown(self):
        self.scratch.cleanup()

    def test_keeps_the_key_and_nothing_else(self):
        path = key_source.obtain(folder=self.home, opener=Served(self.server), source=self.source)
        self.assertEqual(path.read_bytes(), KEY)
        self.assertEqual([item.name for item in self.home.iterdir()], [key_source.KEY_NAME])
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(key_source.stored(self.home, self.source), path)

    def test_a_kept_key_is_not_fetched_again(self):
        key_source.obtain(folder=self.home, opener=Served(self.server), source=self.source)
        server = Served(self.server)
        key_source.obtain(folder=self.home, opener=server, source=self.source)
        self.assertEqual(server.ranges, [])

    def test_a_changed_archive_is_refused_and_not_kept(self):
        part = self.source.parts[1]
        data = bytearray((self.server / part.name).read_bytes())
        data[len(data) // 2] ^= 0xFF
        (self.server / part.name).write_bytes(bytes(data))
        with self.assertRaises(LocalizedError) as raised:
            key_source.obtain(folder=self.home, opener=Served(self.server), source=self.source)
        self.assertEqual(raised.exception.message.key, "error.keyPackage")
        self.assertIsNone(key_source.stored(self.home, self.source))
        self.assertFalse(any(self.home.rglob("*.partial")))

    def test_a_different_key_inside_a_matching_package_is_refused(self):
        other = dataclasses.replace(self.source, key_sha256="0" * 64)
        with self.assertRaises(LocalizedError):
            key_source.obtain(folder=self.home, opener=Served(self.server), source=other)
        self.assertFalse((self.home / key_source.KEY_NAME).exists())

    def test_an_interrupted_download_resumes_where_it_stopped(self):
        part = self.source.parts[0]
        downloads = self.home / "download"
        downloads.mkdir(parents=True)
        head = (self.server / part.name).read_bytes()[: part.size // 3]
        (downloads / (part.name + ".partial")).write_bytes(head)
        server = Served(self.server)
        key_source.obtain(folder=self.home, opener=server, source=self.source)
        self.assertEqual(server.ranges[0], len(head))

    def test_cancelling_keeps_no_key(self):
        with self.assertRaises(key_source.Cancelled):
            key_source.obtain(folder=self.home, opener=Served(self.server),
                              source=self.source, stopped=lambda: True)
        self.assertFalse((self.home / key_source.KEY_NAME).exists())

    def test_a_wrong_stored_key_is_not_reported_as_kept(self):
        self.home.mkdir()
        (self.home / key_source.KEY_NAME).write_bytes(b"something else\n")
        self.assertIsNone(key_source.stored(self.home, self.source))

    def test_forgetting_removes_the_key_and_partial_downloads(self):
        key_source.obtain(folder=self.home, opener=Served(self.server), source=self.source)
        downloads = self.home / "download"
        downloads.mkdir()
        (downloads / "PART0.zip.partial").write_bytes(b"half")
        removed = key_source.forget(self.home)
        self.assertIn(key_source.KEY_NAME, removed)
        self.assertIn("download/PART0.zip.partial", removed)
        self.assertIsNone(key_source.stored(self.home, self.source))
        self.assertFalse(self.home.exists())

    def test_forgetting_leaves_what_the_app_did_not_write(self):
        key_source.obtain(folder=self.home, opener=Served(self.server), source=self.source)
        mine = self.home / "notes.txt"
        mine.write_text("operator's own file")
        key_source.forget(self.home)
        self.assertTrue(mine.is_file())
        self.assertFalse((self.home / key_source.KEY_NAME).exists())

    def test_forgetting_nothing_is_not_an_error(self):
        self.assertEqual(key_source.forget(self.home), ())

    def test_the_shipped_source_is_complete(self):
        source = key_source.load_source()
        self.assertEqual(len(source.parts), 2)
        for part in source.parts:
            self.assertTrue(part.url.startswith("https://"), part.url)
            self.assertTrue(part.url.endswith(part.name), part.url)
            self.assertRegex(part.sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(source.filesystem_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(source.key_sha256, r"^[0-9a-f]{64}$")


class TermsTests(unittest.TestCase):
    def test_the_bridge_refuses_a_download_without_accepted_terms(self):
        from app.ui import bridge

        surface = bridge.Bridge()
        for answer in (None, False, "yes", 1):
            with self.subTest(answer=answer):
                response = surface.mod_key_fetch(answer)
                self.assertFalse(response["ok"])
                self.assertEqual(response["errorMessage"]["key"], "error.keyTerms")

    def test_the_bridge_forgets_the_kept_key(self):
        import os
        from unittest import mock
        from app.ui import bridge

        with tempfile.TemporaryDirectory() as folder:
            home = pathlib.Path(folder) / "home"
            home.mkdir()
            (home / key_source.KEY_NAME).write_bytes(KEY)
            with mock.patch.dict(os.environ, {"RX3_TOOLKIT_HOME": str(home)}):
                response = bridge.Bridge().mod_key_forget()
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["value"]["removed"], [key_source.KEY_NAME])
            self.assertFalse(home.exists())


if __name__ == "__main__":
    unittest.main()
