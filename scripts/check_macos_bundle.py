#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Reject conflicting OpenSSL libraries in a packaged macOS application.

The hazard is two consumers loading libraries of the same name with different
ABIs: the interpreter's own `_ssl` against the one `cryptography` was built for.
One OpenSSL in the bundle is fine however many things read it. Two are not, and
the loader picks for you.

Which branch applies is read off `cryptography` itself. When its Rust binding
links no libssl it carries OpenSSL statically, and the dylibs in the bundle
belong to `_ssl` alone.
"""

import argparse
import pathlib
import subprocess


def require_one(root: pathlib.Path, name: str) -> pathlib.Path:
    matches = list(root.rglob(name))
    unique = {match.resolve() for match in matches}
    if len(unique) != 1:
        raise RuntimeError(
            f"expected one physical {name}, found {len(unique)}: {matches}"
        )
    return unique.pop()


def otool(binary: pathlib.Path) -> str:
    return subprocess.run(
        ["otool", "-L", str(binary)], check=True, capture_output=True, text=True,
    ).stdout


def exported_symbols(library: pathlib.Path) -> str:
    return subprocess.run(
        ["nm", "-gU", str(library)], check=True, capture_output=True, text=True,
    ).stdout


def inspect(
    application: pathlib.Path,
    *,
    dependencies_of=otool,
    symbols_of=exported_symbols,
) -> str:
    """Return what the bundle carries, or raise saying what is wrong with it.

    The two readers are arguments so the decision can be exercised without a
    Mach-O binary to point the real tools at.
    """
    rust_binding = require_one(application, "_rust.abi3.so")
    dependencies = dependencies_of(rust_binding)
    if "libssl.3.dylib" not in dependencies:
        # cryptography carries its OpenSSL inside the binding and never opens a
        # dylib. Anything named libssl here is the interpreter's, which is one
        # consumer and not a conflict. pywebview makes this the ordinary case:
        # webview.http imports ssl at module level, so the interpreter's
        # OpenSSL ships whether or not anything calls it.
        ssl_library = maybe_one(application, "libssl.3.dylib")
        crypto_library = maybe_one(application, "libcrypto.3.dylib")
        if ssl_library is None:
            return "OpenSSL bundle OK: cryptography is statically linked"
        return (
            "OpenSSL bundle OK: cryptography is statically linked, "
            f"{ssl_library.name} + {crypto_library.name} belong to the interpreter"
        )

    ssl_library = require_one(application, "libssl.3.dylib")
    crypto_library = require_one(application, "libcrypto.3.dylib")
    symbols = symbols_of(ssl_library)
    if "_SSL_get0_group_name" not in symbols:
        raise RuntimeError(f"{ssl_library} does not export SSL_get0_group_name")
    return f"OpenSSL bundle OK: {ssl_library} + {crypto_library}"


def maybe_one(root: pathlib.Path, name: str) -> pathlib.Path | None:
    """The one copy of a library, none, or a refusal.

    Absent is a valid state here. Two copies never are: the loader resolves the
    name once and nothing in the bundle says which one it picked.
    """
    if not list(root.rglob(name)):
        return None
    return require_one(root, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application", type=pathlib.Path)
    args = parser.parse_args()
    # The binding's own dependencies go to the log whatever the verdict: when
    # this fails in CI they are the first thing anyone will want.
    binding = require_one(args.application, "_rust.abi3.so")
    print(otool(binding), end="")
    print(inspect(args.application))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
