# SPDX-License-Identifier: MPL-2.0
"""Keep the prose within the scope the code occupies.

The toolkit authors one thing: the `autoexec.bin` image the player's own
maintenance path already looks for. That format stays documented, because a
reader cannot follow the build without it.

The update-container format is a different matter. Nothing in the tree reads or
writes it, `tests/test_firmware_image.py` asserts the codec is gone, and prose
outlives code: a description of the trailer layout, its checksum, or of what the
container does not verify would be a specification for forging one long after
the last line that could have produced it was deleted. This test fails the build
if that description comes back.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]

# Prose is checked; the changelog is history and is rewritten, not policed here.
DOCUMENTS = sorted(
    {
        *ROOT.glob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / "mod").rglob("*.md"),
    }
    - {ROOT / "CHANGELOG.md"}
)

# Each pattern carries the reason it is refused, so a failure reads as an
# explanation rather than as a rule someone has to go and look up.
FORBIDDEN = (
    (
        re.compile(r"\bcrc[\s_-]?32\b", re.I),
        "the container's integrity field: naming it describes how to satisfy it",
    ),
    (
        re.compile(r"\btrailers?\b", re.I),
        "the model/version record appended to an update container",
    ),
    (
        re.compile(
            r"\b(?:no|not|without|lacks?|absent|absence\s+of|neither|never)\b"
            r"(?:\W+\w+){0,4}?\W+"
            r"(?:asymmetric\s+|public[\s-]key\s+|digital\s+)?"
            r"(?:signature|signing|signed|hmac|\bmacs?\b|"
            r"authentication\s+(?:tag|code))",
            re.I,
        ),
        "a statement of what the container does not verify",
    ),
    (
        re.compile(r"\bunsigned\b(?:\W+\w+){0,3}\W+"
                   r"(?:image|container|firmware|update|payload|package)", re.I),
        "a statement of what the container does not verify",
    ),
)

# One narrow exemption, kept explicit so it cannot quietly widen: desktop
# operating systems refuse applications they have no developer signature for.
# That is a distribution problem of ours and says nothing about any device
# format, so it is exempted only where the line is plainly about the app.
EXEMPT_SIGNING = re.compile(r"unsigned\s+application|code[-\s]?sign", re.I)
EXEMPT_CONTEXT = re.compile(
    r"\b(?:app|application|installer|download|quarantine|"
    r"macos|windows|gatekeeper|notaris|notariz)", re.I
)


def _is_exempt(line):
    return bool(EXEMPT_SIGNING.search(line) and EXEMPT_CONTEXT.search(line))


class DocumentationHygieneTests(unittest.TestCase):
    def test_no_update_container_specification_in_prose(self):
        offences = []
        for document in DOCUMENTS:
            for number, line in enumerate(
                document.read_text(encoding="utf-8").splitlines(), 1
            ):
                if _is_exempt(line):
                    continue
                for pattern, reason in FORBIDDEN:
                    found = pattern.search(line)
                    if found:
                        relative = document.relative_to(ROOT)
                        offences.append(
                            f"{relative}:{number}: {found.group(0)!r} — {reason}"
                        )
        self.assertEqual(
            offences,
            [],
            "update-container specification found in documentation:\n"
            + "\n".join(offences),
        )

    def test_the_guard_would_actually_catch_a_regression(self):
        """A guard nobody has seen fail is a guard nobody knows works."""
        regressions = (
            "the trailer holds the model string",
            "verified with a CRC32 over the body",
            "the image carries no asymmetric signature",
            "there is no MAC over the payload",
            "an unsigned firmware image is accepted",
        )
        for line in regressions:
            with self.subTest(line=line):
                self.assertTrue(
                    any(pattern.search(line) for pattern, _ in FORBIDDEN),
                    f"guard failed to catch {line!r}",
                )

    def test_the_exemption_stays_narrow(self):
        """It must clear the app's own signing, and nothing on the device."""
        self.assertTrue(_is_exempt("The app is not code-signed yet"))
        self.assertFalse(_is_exempt("the update image is not code-signed"))

    def test_the_autoexec_format_stays_documented(self):
        """The complement of the rule above: this one must not be swept up."""
        reference = (ROOT / "REFERENCES.md").read_text(encoding="utf-8")
        self.assertIn("autoexec", reference.lower())


if __name__ == "__main__":
    unittest.main()
