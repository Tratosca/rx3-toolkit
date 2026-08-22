#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Write the files a new module is made of, so that none of them is guessed.

A module is a manifest the build engine validates, a shell contract the
orchestrator sources, guards `make test` picks up beside the manifest, and a
README. Their names, their namespacing and the order field are conventions
discoverable only by reading a module that already exists, and each of them has
been got wrong that way. This writes them correct and refuses to touch anything
that is already there.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.rx3_runtime.build import discover_patches, repository_root


# The manifest allows an id to start with a digit; a shell namespace cannot, and
# the namespace is derived from the id. Refuse here rather than at build time.
MODULE_ID = re.compile(r"[a-z][a-z0-9-]*")

MANIFEST_TEMPLATE = {
    "id": "@ID@",
    "name": "@NAME@",
    "description": "TODO: one sentence, read in the module list, by a DJ.",
    "firmware": "@FIRMWARE@",
    "default": False,
    "order": 0,
    "runtime_directory": "@ID@",
    "namespace": "@NS@",
    "requires": [],
    "conflicts": [],
    "files": [{"source": "module.sh", "target": "module.sh", "executable": False}],
}

MODULE_SH = """#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# @NAME@.
# TODO: one line saying what this changes on the deck.

module_begin @ID@ @NS@

@NS@_prepare()
{
    say "@NAME@ prepared"
}

register_prepare_hook @NS@_prepare
"""

CORE_MODULE_SH = """#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# @NAME@.
# The code lives in the performance core's shared object; this module decides
# whether it runs, and owns its documentation and tests.

module_begin @ID@ @NS@

@NS_UPPER@_READY=0

@NS@_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "@NAME@ disabled: the performance core is not selected"
        return 1
    }
    export RX3_@NS_UPPER@=1
    @NS_UPPER@_READY=1
    running=$(rbp_environment_value RX3_@NS_UPPER@)
    if [ "$running" != "1" ]; then
        say "@NAME@ needs a restart: running rbp carries RX3_@NS_UPPER@=[${running:-none}]"
        request_rbp_restart
    fi
    say "@NAME@ prepared"
}

@NS@_after_launch()
{
    [ "$@NS_UPPER@_READY" = "1" ] || return 0
    say "@NAME@ active"
}

register_prepare_hook @NS@_prepare
register_after_launch_hook @NS@_after_launch
"""

FEATURE_HEADER = """/* SPDX-License-Identifier: MPL-2.0
 * @NAME@ implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_@NS_UPPER@_FEATURE_H
#define RX3_@NS_UPPER@_FEATURE_H

static int @NS@_feature_configured(void)
{
    return getenv("RX3_@NS_UPPER@") != 0;
}

static int @NS@_feature_install(void)
{
    /* Return 0 to refuse. The core then logs the refusal and leaves the
       feature inactive rather than running it half-installed. */
    return 1;
}

static void @NS@_feature_remove(void)
{
    /* Undo exactly what install() did, and nothing another feature owns. A
       thread started above is stopped here, not left running. */
}

#endif /* RX3_@NS_UPPER@_FEATURE_H */
"""

README = """<!-- SPDX-License-Identifier: MPL-2.0 -->
# @NAME@

TODO: what this changes on the deck, for someone who knows their equipment and
not our internals.

TODO: how it is turned on, and what to press.

TODO: what is not demonstrated yet. Say it plainly.
"""

GUARDS = '''#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for the @NAME@ module, all of them measured facts."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
MODULE = (ROOT / "module.sh").read_text()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
@FEATURE_READ@

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "module_begin @ID@ @NS@" in MODULE,
    "the orchestrator loads this module under the id and namespace it declares",
)
require(
    MANIFEST["runtime_directory"] == "@ID@",
    "the directory written into the image is the one module.sh is read from",
)
@CORE_GUARDS@
# TODO: replace the guards above with what would actually break. One that pins
# a fact somebody got wrong is worth more than five that restate the manifest.

print("@NAME@ regression guards: OK")
'''

FEATURE_READ = 'FEATURE = (ROOT / "rx3_@NS@_feature.h").read_text()\n'

CORE_GUARDS = '''require(
    '[ -r "$CORE_OBJECT" ]' in MODULE,
    "the module must decline when the performance core is not selected",
)
require(
    'getenv("RX3_@NS_UPPER@")' in FEATURE,
    "the feature must gate on its own environment flag",
)
'''


def render(template: str, module_id: str, name: str, firmware: str) -> str:
    namespace = module_id.replace("-", "_")
    return (
        template.replace("@NS_UPPER@", namespace.upper())
        .replace("@NS@", namespace)
        .replace("@ID@", module_id)
        .replace("@NAME@", name)
        .replace("@FIRMWARE@", firmware)
    )


def next_order(root: pathlib.Path, firmware: str) -> int:
    """Load last, which is always valid. Dependencies must sort earlier, and
    the contributor is told to move it if the load order matters."""
    existing = [patch.order for patch in discover_patches(root, firmware)]
    return max(existing, default=0) + 5


def scaffold(
    root: pathlib.Path, module_id: str, name: str, firmware: str, core: bool
) -> list[pathlib.Path]:
    if not MODULE_ID.fullmatch(module_id):
        raise ValueError(
            f"{module_id!r}: a module id is lower case, starts with a letter, and "
            f"holds only letters, digits and hyphens"
        )
    directory = root / "mod/modules" / module_id / firmware
    if directory.exists():
        raise ValueError(f"{directory}: this module already exists")

    namespace = module_id.replace("-", "_")
    manifest = dict(MANIFEST_TEMPLATE)
    manifest["order"] = next_order(root, firmware)
    if core:
        manifest["requires"] = ["core"]
        manifest["build_files"] = [f"rx3_{namespace}_feature.h"]

    guards = GUARDS.replace(
        "@FEATURE_READ@", FEATURE_READ if core else ""
    ).replace("@CORE_GUARDS@", CORE_GUARDS if core else "")

    written = {
        "manifest.json": render(
            json.dumps(manifest, indent=2), module_id, name, firmware
        )
        + "\n",
        "module.sh": render(
            CORE_MODULE_SH if core else MODULE_SH, module_id, name, firmware
        ),
        "README.md": render(README, module_id, name, firmware),
        "test_regressions.py": render(guards, module_id, name, firmware),
    }
    if core:
        written[f"rx3_{namespace}_feature.h"] = render(
            FEATURE_HEADER, module_id, name, firmware
        )

    directory.mkdir(parents=True)
    for filename, content in written.items():
        (directory / filename).write_text(content, encoding="utf-8", newline="\n")
    return [directory / filename for filename in sorted(written)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="module id, e.g. browse-lock")
    parser.add_argument("--name", default="", help="module name shown in the app")
    parser.add_argument("--firmware", default="1.19")
    parser.add_argument(
        "--core",
        action="store_true",
        help="the feature runs inside the player's application, reacting to "
        "what it does while it plays: a track loading, audio, a pad, the "
        "screen. Key shift and stems do",
    )
    args = parser.parse_args()

    root = pathlib.Path(repository_root())
    name = args.name or args.id.replace("-", " ").capitalize()
    try:
        written = scaffold(root, args.id, name, args.firmware, args.core)
    except ValueError as failure:
        print(failure, file=sys.stderr)
        return 2

    for path in written:
        print(path.relative_to(root))

    manifest = json.loads((written[0].parent / "manifest.json").read_text())
    namespace = args.id.replace("-", "_")
    steps = ["fill in the TODOs: the manifest description, module.sh, the README"]
    if args.core:
        steps.append(
            f"declare the feature in mod/modules/core/{args.firmware}/"
            f"rx3_core_hook.c: forward-declare the three {namespace}_feature_* "
            f"functions, raise RUNTIME_FEATURE_COUNT, add the runtime_features "
            f"entry, and include the header beside the other features"
        )
        steps.append(
            "every libc name the header calls must be in ALLOWED in "
            "tests/test_hook_symbols.py. The hook is -nostdlib: a name rbp does "
            "not export loads nothing and silences every module, not just yours"
        )
    steps.append("make test")

    print()
    print(
        f"It is off by default and loads last, at order {manifest['order']}. "
        f"Lower it if a module must load after it."
    )
    print("\nNext, in order:")
    for number, step in enumerate(steps, 1):
        print(f"  {number}. {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
