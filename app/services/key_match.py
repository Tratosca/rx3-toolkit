# SPDX-License-Identifier: MPL-2.0
"""Optional Browse suggestions; bit flags are data, never executable settings."""
from app.localization import LocalizedError
GUIDE_URL = "https://mixedinkey.com/book/use-advanced-harmonic-mixing-techniques/"
DEFAULT_RULES = 0

def rules(value=DEFAULT_RULES):
    if type(value) is not int or not 0 <= value <= 15:
        raise LocalizedError("error.keyMatchRules")
    # Retire diagonals without changing the remaining saved bit assignments.
    return value & 14

def files(value=DEFAULT_RULES):
    return {"rules.txt": f"{rules(value)}\n".encode("ascii")}
