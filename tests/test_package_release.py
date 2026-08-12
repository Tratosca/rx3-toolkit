# SPDX-License-Identifier: MPL-2.0

import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "scripts/package_release.py"


class PackageReleaseTests(unittest.TestCase):
    def test_zip_and_tar_include_legal_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            application = work / "application"
            application.write_text("test\n", encoding="utf-8")

            for suffix in ("zip", "tar.gz"):
                archive = work / f"release.{suffix}"
                subprocess.run([
                    sys.executable,
                    str(PACKAGER),
                    str(application),
                    str(archive),
                    "--include",
                    str(ROOT / "LICENSE"),
                    "--include",
                    str(ROOT / "THIRD_PARTY_NOTICES.md"),
                ], check=True)

                if suffix == "zip":
                    with zipfile.ZipFile(archive) as package:
                        names = set(package.namelist())
                else:
                    with tarfile.open(archive) as package:
                        names = set(package.getnames())

                self.assertIn("application", names)
                self.assertIn("LICENSE", names)
                self.assertIn("THIRD_PARTY_NOTICES.md", names)


if __name__ == "__main__":
    unittest.main()
