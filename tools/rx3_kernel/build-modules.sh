#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu

usage()
{
    cat >&2 <<'EOF'
usage: build-modules.sh FIRMWARE KERNEL_SOURCE RECIPE_DIRECTORY OUTPUT_DIRECTORY

Build and validate one feature's kernel modules for an RX3 production kernel.
The recipe directory must contain build.sh, modules.list, production.symvers,
and production.symvers.sha256.
EOF
}

if [ "$#" -ne 4 ]; then
    usage
    exit 2
fi

firmware=$1
kernel_source=$(realpath "$2")
recipe_directory=$(realpath "$3")
output_directory=$(realpath -m "$4")
tool_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
profile=$tool_directory/firmware/$firmware.conf
builder_image=localhost/rx3-kernel-builder:bookworm

[ -f "$profile" ] || {
    echo "unsupported kernel firmware profile: $firmware" >&2
    exit 1
}
. "$profile"

for required in COPYING .config include/config/kernel.release; do
    [ -f "$kernel_source/$required" ] || {
        echo "missing kernel build input: $kernel_source/$required" >&2
        exit 1
    }
done
for required in modules.list production.symvers production.symvers.sha256; do
    [ -f "$recipe_directory/$required" ] || {
        echo "missing kernel recipe input: $recipe_directory/$required" >&2
        exit 1
    }
done
[ -x "$recipe_directory/build.sh" ] || {
    echo "kernel recipe is not executable: $recipe_directory/build.sh" >&2
    exit 1
}

[ "$(cat "$kernel_source/include/config/kernel.release")" = "$RX3_KERNEL_SOURCE_RELEASE" ] || {
    echo "unexpected kernel release: $(cat "$kernel_source/include/config/kernel.release")" >&2
    exit 1
}

python3 "$tool_directory/validate-symvers.py" profile \
    "$recipe_directory/production.symvers" \
    "$recipe_directory/production.symvers.sha256"
for setting in CONFIG_MODULES=y CONFIG_MODVERSIONS=y; do
    grep -q "^${setting}$" "$kernel_source/.config" || {
        echo "kernel tree does not provide required setting $setting" >&2
        exit 1
    }
done

awk '
    /^[[:space:]]*($|#)/ { next }
    $0 !~ /^[A-Za-z0-9][A-Za-z0-9_.-]*\.ko$/ { exit 1 }
    seen[$0]++ { exit 1 }
' "$recipe_directory/modules.list" || {
    echo "modules.list must contain unique output .ko filenames" >&2
    exit 1
}

work=$(mktemp -d "${TMPDIR:-/tmp}/rx3-kernel-build.XXXXXX")
cleanup()
{
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$work/kernel" "$work/output"

podman run --rm --network=none \
    -e RX3_KERNEL_RELEASE="$RX3_KERNEL_RELEASE" \
    -e RX3_KERNEL_VERMAGIC="$RX3_KERNEL_VERMAGIC" \
    -e RX3_KERNEL_LOCALVERSION_APPEND="$RX3_KERNEL_LOCALVERSION_APPEND" \
    -e RX3_KERNEL_TREE=/build/kernel \
    -e RX3_KERNEL_PRODUCTION_SYMVERS=/recipe/production.symvers \
    -v "$kernel_source:/kernel:ro" \
    -v "$recipe_directory:/recipe:ro" \
    -v "$tool_directory:/tool:ro" \
    -v "$work:/build:rw" \
    "$builder_image" sh -eu -c '
        cp -a /kernel/. "$RX3_KERNEL_TREE/"
        /recipe/build.sh "$RX3_KERNEL_TREE" /build/output

        while IFS= read -r module; do
            case "$module" in ""|\#*) continue ;; esac
            output=/build/output/$module
            test -f "$output"
            readelf -h "$output" | grep -q "Machine:.*ARM"
            readelf -p .modinfo "$output" | grep -Fq "vermagic=$RX3_KERNEL_VERMAGIC"
            readelf -S "$output" | grep -Eq "__versions.*[[:space:]][0-9a-fA-F]{6,}[[:space:]]"
            readelf -x __versions "$output" | grep -Fq module_layou
            ! readelf -sW "$output" | grep -Fq _GLOBAL_OFFSET_TABLE_
        done < /recipe/modules.list

        python3 /tool/validate-symvers.py modules \
            /recipe/production.symvers /recipe/modules.list /build/output
    '

mkdir -p "$output_directory"
while IFS= read -r module; do
    case "$module" in ""|\#*) continue ;; esac
    cp "$work/output/$module" "$output_directory/$module"
done < "$recipe_directory/modules.list"
cp "$kernel_source/COPYING" "$output_directory/COPYING.linux"
sha256sum "$output_directory"/*.ko
