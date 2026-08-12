#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu

failed=0
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/rx3-preflight.XXXXXX")
trap 'rm -rf "$temp_dir"' EXIT HUP INT TERM
candidate_list="$temp_dir/candidates"
git ls-files --cached --others --exclude-standard > "$candidate_list"
count=0

while IFS= read -r path; do
    [ -f "$path" ] || continue
    count=$((count + 1))
    case "$path" in
        *.key|*.pem|*.p12|*.pfx|*.jks|*.keystore|*.UPD|*.upd|*.bin|*.iso|*.img|*.so|*.rx3stem|*.wav|*.aif|*.aiff|*.flac|*.mp3)
            printf 'REJECTED sensitive or generated artifact: %s\n' "$path" >&2
            failed=1
            ;;
    esac
    size=$(wc -c < "$path" | tr -d ' ')
    if [ "$size" -gt 2097152 ]; then
        printf 'REJECTED unusually large source file: %s (%s bytes)\n' "$path" "$size" >&2
            failed=1
    fi
    if [ "$path" != "scripts/preflight.sh" ] && \
       grep -IEnE '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,})' \
         "$path" > "$temp_dir/matches" 2>/dev/null; then
        sed "s|^|$path:|" "$temp_dir/matches" >&2
        printf 'REJECTED secret pattern: %s\n' "$path" >&2
        failed=1
    fi
done < "$candidate_list"

[ "$failed" -eq 0 ] || exit 1
printf 'Publication preflight: OK (%s candidate files)\n' "$count"
