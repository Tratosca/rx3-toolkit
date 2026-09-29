#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: fetch-source.sh FIRMWARE DESTINATION" >&2
    exit 2
fi

firmware=$1
destination=$(realpath -m "$2")
tool_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
profile=$tool_directory/firmware/$firmware.conf

[ -f "$profile" ] || {
    echo "unsupported kernel firmware profile: $firmware" >&2
    exit 1
}
. "$profile"

[ ! -e "$destination" ] || {
    echo "kernel source destination already exists: $destination" >&2
    exit 1
}

work=$(mktemp -d "${TMPDIR:-/tmp}/rx3-kernel-source.XXXXXX")
cleanup()
{
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM

fetch()
{
    expected=$1
    url=$2
    output=$3
    curl -fL --retry 3 -o "$output" "$url"
    printf '%s  %s\n' "$expected" "$output" | sha256sum -c -
}

fetch "$RX3_KERNEL_SOURCE_PART_00_SHA256" \
    "$RX3_KERNEL_SOURCE_PART_00_URL" "$work/source-00.zip"
fetch "$RX3_KERNEL_SOURCE_PART_01_SHA256" \
    "$RX3_KERNEL_SOURCE_PART_01_URL" "$work/source-01.zip"

if command -v 7zz >/dev/null 2>&1; then
    seven_zip=7zz
elif command -v 7z >/dev/null 2>&1; then
    seven_zip=7z
else
    echo "7-Zip command not found; install 7zz or 7z" >&2
    exit 1
fi

mkdir "$work/parts"
"$seven_zip" x -y -o"$work/parts" "$work/source-00.zip" >/dev/null
"$seven_zip" x -y -o"$work/parts" "$work/source-01.zip" >/dev/null
cat "$work/parts/pioneerdj_xdj_rx3.tar.bz2.00" \
    "$work/parts/pioneerdj_xdj_rx3.tar.bz2.01" > \
    "$work/pioneerdj_xdj_rx3.tar.bz2"
printf '%s  %s\n' "$RX3_KERNEL_SOURCE_ARCHIVE_SHA256" \
    "$work/pioneerdj_xdj_rx3.tar.bz2" | sha256sum -c -

mkdir "$work/source"
tar -xjf "$work/pioneerdj_xdj_rx3.tar.bz2" -C "$work/source"
source_directory=$work/source/$RX3_KERNEL_SOURCE_DIRECTORY

mkdir -p "$destination"
cp -a "$source_directory/." "$destination/"

printf '%s\n' "$destination"
