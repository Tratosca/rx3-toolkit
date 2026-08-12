#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Reject conflicting OpenSSL libraries in a packaged macOS application."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application", type=pathlib.Path)
    args = parser.parse_args()

    rust_binding = require_one(args.application, "_rust.abi3.so")
    dependencies = subprocess.run(
        ["otool", "-L", str(rust_binding)], check=True,
        capture_output=True, text=True,
    ).stdout
    print(dependencies, end="")

    ssl_matches = list(args.application.rglob("libssl.3.dylib"))
    crypto_matches = list(args.application.rglob("libcrypto.3.dylib"))
    if "libssl.3.dylib" not in dependencies:
        if ssl_matches or crypto_matches:
            raise RuntimeError(
                "statically linked cryptography bundle contains unexpected "
                f"OpenSSL libraries: {ssl_matches + crypto_matches}"
            )
        print("OpenSSL bundle OK: cryptography is statically linked")
        return 0

    ssl_library = require_one(args.application, "libssl.3.dylib")
    crypto_library = require_one(args.application, "libcrypto.3.dylib")
    symbols = subprocess.run(
        ["nm", "-gU", str(ssl_library)], check=True,
        capture_output=True, text=True,
    ).stdout
    if "_SSL_get0_group_name" not in symbols:
        raise RuntimeError(f"{ssl_library} does not export SSL_get0_group_name")

    print(f"OpenSSL bundle OK: {ssl_library} + {crypto_library}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
