#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Write the files a new module is made of, so that none of them is guessed.

A module is a manifest the build engine validates, a shell contract the
orchestrator sources, and a README. Their names, their namespacing and the order field are conventions
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

from app.runtime.build import available_versions, discover_patches, repository_root


# The manifest allows an id to start with a digit; a shell namespace cannot, and
# the namespace is derived from the id. Refuse here rather than at build time.
MODULE_ID = re.compile(r"[a-z][a-z0-9-]*")

MANIFEST_TEMPLATE = {
    "id": "@ID@",
    "name": {"en": "@NAME@", "fr": "@NAME@"},
    "description": {
        "en": "TODO: one sentence explaining what this module does.",
        "fr": "TODO: une phrase expliquant ce que fait ce module.",
    },
    "firmwares": [],
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
        return 0
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

MODULE_SOURCE = """/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"

static int configured(void)
{
    const char *value = getenv("RX3_@NS_UPPER@");
    return value && value[0] == '1';
}
static int start(const struct rx3_services *services)
{
    (void)services;
    /* Request shared services here; return 0 on partial failure. */
    return 1;
}
static void stop(void)
{
    /* Must also accept a partially completed start. No hot unload. */
}
const struct rx3_module rx3_@NS@_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "@ID@", .configured = configured, .start = start, .stop = stop
};
"""

README = """<!-- SPDX-License-Identifier: MPL-2.0 -->
# @NAME@

TODO: what this changes on the deck, for someone who knows their equipment and
not our internals.

TODO: how it is turned on, and what to press.

TODO: what is not demonstrated yet. Say it plainly.
"""


def render(template: str, module_id: str, name: str, firmwares: list[str]) -> str:
    namespace = module_id.replace("-", "_")
    return (
        template.replace("@NS_UPPER@", namespace.upper())
        .replace("@NS@", namespace)
        .replace("@ID@", module_id)
        .replace("@NAME@", name)
        .replace("@FIRMWARES@", json.dumps(firmwares))
    )


def next_order(root: pathlib.Path) -> int:
    """Load last, which is always valid. Dependencies must sort earlier, and
    the contributor is told to move it if the load order matters."""
    existing = [patch.order for patch in discover_patches(root)]
    return max(existing, default=0) + 5


def scaffold(
    root: pathlib.Path, module_id: str, name: str, firmwares: list[str], core: bool, category: str
) -> list[pathlib.Path]:
    if not MODULE_ID.fullmatch(module_id):
        raise ValueError(
            f"{module_id!r}: a module id is lower case, starts with a letter, and "
            f"holds only letters, digits and hyphens"
        )
    directory = root / "mod/modules" / module_id
    if directory.exists():
        raise ValueError(f"{directory}: this module already exists")

    namespace = module_id.replace("-", "_")
    manifest = dict(MANIFEST_TEMPLATE)
    from app.runtime.metadata import categories
    definitions = categories(root)
    if not MODULE_ID.fullmatch(category) or (definitions and category not in definitions):
        raise ValueError(f"Unknown category: {category}")
    manifest["category"] = category
    manifest["order"] = next_order(root)
    manifest["firmwares"] = firmwares
    if core:
        manifest["requires"] = ["core"]
        manifest["build_files"] = [f"rx3_{namespace}_module.c"]

    written = {
        "manifest.json": render(
            json.dumps(manifest, indent=2), module_id, name, firmwares
        )
        + "\n",
        "module.sh": render(
            CORE_MODULE_SH if core else MODULE_SH, module_id, name, firmwares
        ),
        "README.md": render(README, module_id, name, firmwares),
    }
    if core:
        written[f"rx3_{namespace}_module.c"] = render(
            MODULE_SOURCE, module_id, name, firmwares
        )

    directory.mkdir(parents=True)
    for filename, content in written.items():
        (directory / filename).write_text(content, encoding="utf-8", newline="\n")
    return [directory / filename for filename in sorted(written)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="module id, e.g. browse-lock")
    parser.add_argument("--category", required=True, help="category identifier from mod/categories.json")
    parser.add_argument("--name", default="", help="module name shown in the app")
    # Which firmware versions the module is built against. Several can share
    # one module when the addresses it touches are the same in each.
    parser.add_argument("--firmware", action="append", dest="firmwares",
                        help="repeatable; defaults to every version this tree knows")
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
        firmwares = args.firmwares or available_versions(root)
        written = scaffold(root, args.id, name, firmwares, args.core, args.category)
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
            f"add {args.id}/rx3_{namespace}_module.c to arm_hook.sources in "
            "mod/modules/core/manifest.json and register the descriptor "
            f"rx3_{namespace}_module in core/runtime/rx3_composition.c; never include a module "
            "implementation in rx3_core_hook.c"
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
