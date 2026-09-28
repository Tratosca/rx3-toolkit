# SPDX-License-Identifier: MPL-2.0
"""Configuration carried by the Key Shift module in the generated runtime."""
from app.localization import LocalizedError


def sync_range(value=1) -> int:
    if type(value) is not int or not 1 <= value <= 12:
        raise LocalizedError("error.keySyncRange")
    return value


def sync_mode(value="harmonic") -> str:
    if value not in ("identical", "harmonic"):
        raise LocalizedError("error.keySyncMode")
    return value


def files(value=1, mode="harmonic") -> dict[str, bytes]:
    return {"sync-range.txt": f"{sync_range(value)}\n".encode("ascii"),
            "sync-mode.txt": f"{sync_mode(mode)}\n".encode("ascii")}


def _accepts(reference, candidate, native_keys, rules):
    if candidate in native_keys:
        return True
    if reference % 2 != candidate % 2:
        return False
    delta = (candidate // 2 - reference // 2) % 12
    return any(rules & bit and delta == step for bit, step in ((2, 2), (4, 7), (8, 4)))


def preview_delta(source, reference, native_keys, rules, limit, mode, current_shift=0):
    """Mirror the shared runtime solver; exhaustive C parity is tested."""
    if not 0 <= source < 24 or not 0 <= reference < 24:
        return 0
    here = (source + 14 * current_shift) % 24
    if here == reference or mode == 'harmonic' and _accepts(reference, here, native_keys, rules):
        return 0
    for distance in range(1, limit + 1):
        fallback = 0
        for delta in (distance, -distance):
            if not -12 <= current_shift + delta <= 12:
                continue
            target = (source + 14 * (current_shift + delta)) % 24
            if target == reference:
                return delta
            if not fallback and mode == 'harmonic' and _accepts(reference, target, native_keys, rules):
                fallback = delta
        if fallback:
            return fallback
    return 0


def preview(limit=1, mode='harmonic', rules=0):
    """Fictional BROWSE example; no device, library or filesystem access."""
    from app.services.key_match import rules as validate_rules
    limit, mode, rules = sync_range(limit), sync_mode(mode), validate_rules(rules)
    reference, native_keys = 14, (12, 14, 15, 16)
    def camelot(key):
        return f'{key // 2 + 1}{"AB"[key % 2]}'
    # The browser explains every marker; the sync calculation still uses saved rules.
    rows = []
    for key in (12, 15, 2, 18, 4, 22, 8, 12, 14, 15, 18, 22):
        colour = 'green' if key in native_keys else None
        for step, tint in ((2, 'yellow'), (7, 'orange'), (4, 'red')):
            if not colour and key % 2 == reference % 2 and (key // 2 - reference // 2) % 12 == step:
                colour = tint
        rows.append(dict(number=len(rows)+1, key=camelot(key), colour=colour))
    delta = preview_delta(2, reference, native_keys, rules, limit, mode)
    return dict(master='8A', rows=rows, selected=2, shift=delta,
                source='2A', target=camelot((2 + delta * 14) % 24) if delta else None)
