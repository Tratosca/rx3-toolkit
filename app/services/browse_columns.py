# SPDX-License-Identifier: MPL-2.0
"""Native semantic field IDs; configuration is inert, strictly validated data."""
from app.localization import LocalizedError
FIELDS = (7, 11, 13, 15)
DEFAULT_FIELD = 13

def field(value=DEFAULT_FIELD):
    if type(value) is not int or value not in FIELDS:
        raise LocalizedError("error.browseColumn")
    return value

def files(value=DEFAULT_FIELD):
    return {"column.txt": f"{field(value)}\n".encode("ascii")}
