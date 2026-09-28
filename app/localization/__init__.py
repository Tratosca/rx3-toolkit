# SPDX-License-Identifier: MPL-2.0
"""Locale-independent messages; translate only at the presentation boundary."""
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import sys

DEFAULT = "en"
SUPPORTED = ("en", "fr")


def normalize(locale):
    code = str(locale or DEFAULT).replace("_", "-").split("-")[0].lower()
    return code if code in SUPPORTED else DEFAULT


@lru_cache(maxsize=1)
def catalogs():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    if hasattr(sys, "_MEIPASS"):
        root /= "localization"
    from app.runtime.metadata import module_messages, categories, category_messages

    result = {locale: json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))
              for locale in SUPPORTED}
    resources = Path(sys._MEIPASS) / "resources" if hasattr(sys, "_MEIPASS") else Path(__file__).resolve().parents[2]
    manifests = sorted((resources / "mod/modules").glob("*/manifest.json"))
    if not manifests:
        raise ValueError("Module manifests missing from application resources")
    category_definitions = categories(resources)
    if not category_definitions:
        raise ValueError("Module category registry missing from application resources")
    sources = [(resources / "mod/categories.json", category_messages(category_definitions))]
    sources.extend((manifest, module_messages(json.loads(manifest.read_text(encoding="utf-8")))) for manifest in manifests)
    for source, messages in sources:
        for locale in SUPPORTED:
            for key, value in messages[locale].items():
                if key in result[locale]:
                    raise ValueError(f"{source}: conflicting message {key}")
                result[locale][key] = value
    return result


def translate(key, locale=DEFAULT, **params):
    locale = normalize(locale)
    if key not in catalogs()[locale]:
        locale = DEFAULT
    text = catalogs()[locale].get(key, key)
    if isinstance(text, dict):
        count = params.get("count", 0)
        one = math.floor(count) in (0, 1) if locale == "fr" else count == 1
        text = text.get("one" if one else "other", text["other"])
    return re.sub(r"\{(\w+)\}", lambda match: str(params.get(match[1], match[0])), text)


class Message(str):
    """English-readable in CLI/logs, structured when sent across the UI bridge."""
    def __new__(cls, key, **params):
        obj = super().__new__(cls, translate(key, **params))
        obj.key, obj.params = key, params
        return obj


class LocalizedError(ValueError):
    def __init__(self, key, **params):
        self.message = Message(key, **params)
        super().__init__(self.message)


def wire(value):
    if isinstance(value, Message):
        return {"key": value.key, "params": wire(value.params)}
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire(item) for item in value]
    return value


def error_message(error):
    return getattr(error, "message", Message("error.detail", detail=str(error) or type(error).__name__))
