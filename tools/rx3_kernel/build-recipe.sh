#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu

usage()
{
    cat >&2 <<'EOF'
usage: build-recipe.sh FIRMWARE KERNEL_SOURCE RECIPE SOURCE_CACHE OUTPUT

Build one RX3 kernel recipe. A recipe may provide fetch-sources.sh,
sources.sha256, and prepare-recipe.sh when it needs pinned external source.
EOF
}

if [ "$#" -ne 5 ]; then
    usage
    exit 2
fi

firmware=$1
kernel_source=$2
recipe_directory=$(realpath "$3")
source_directory=$(realpath -m "$4")
output_directory=$5
tool_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

fetch=$recipe_directory/fetch-sources.sh
checksums=$recipe_directory/sources.sha256
prepare=$recipe_directory/prepare-recipe.sh
temporary=

cleanup()
{
    [ -z "$temporary" ] || rm -rf "$temporary"
}
trap cleanup EXIT HUP INT TERM

present=0
[ -e "$fetch" ] && present=$((present + 1))
[ -e "$checksums" ] && present=$((present + 1))
[ -e "$prepare" ] && present=$((present + 1))
if [ "$present" -ne 0 ] && [ "$present" -ne 3 ]; then
    echo "kernel recipe source hooks must include fetch-sources.sh, sources.sha256, and prepare-recipe.sh" >&2
    exit 1
fi

if [ "$present" -eq 3 ]; then
    [ -x "$fetch" ] || {
        echo "kernel recipe source fetcher is not executable: $fetch" >&2
        exit 1
    }
    [ -x "$prepare" ] || {
        echo "kernel recipe source preparer is not executable: $prepare" >&2
        exit 1
    }

    mkdir -p "$source_directory"
    "$fetch" "$source_directory"
    (cd "$source_directory" && sha256sum -c "$checksums")

    temporary=$(mktemp -d "${TMPDIR:-/tmp}/rx3-kernel-recipe.XXXXXX")
    cp -a "$recipe_directory/." "$temporary/"
    "$temporary/prepare-recipe.sh" "$source_directory" "$temporary"
    recipe_directory=$temporary
fi

"$tool_directory/build-modules.sh" \
    "$firmware" "$kernel_source" "$recipe_directory" "$output_directory"
