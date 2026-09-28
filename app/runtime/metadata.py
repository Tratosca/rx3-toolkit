# SPDX-License-Identifier: MPL-2.0
"""Presentation metadata owned by module manifests, independent of the UI."""
import re
import json


def localized(value, field):
    if not isinstance(value, dict) or any(
        not isinstance(value.get(locale), str) or not value[locale].strip()
        for locale in ("en", "fr")
    ):
        raise ValueError(f"{field}: non-empty en and fr text required")
    return value


def category_metadata(value):
    # Older external manifests remain buildable; shipped manifests are bilingual.
    if isinstance(value, str):
        value = {"id": value, "name": {"en": value, "fr": value}, "order": 100}
    if not isinstance(value, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(value.get("id", ""))):
        raise ValueError("category: valid id required")
    localized(value.get("name"), "category.name")
    if "description" in value:
        localized(value["description"], "category.description")
    if type(value.get("order", 100)) is not int or type(value.get("collapsed", False)) is not bool:
        raise ValueError("category: integer order and boolean collapsed required")
    return {**value, "order": value.get("order", 100), "collapsed": value.get("collapsed", False)}


def module_messages(data):
    result = {"en": {}, "fr": {}}
    for field in ("name", "description"):
        values = localized(data[field], field)
        for locale in result:
            result[locale][f"module.{data['id']}.{field}"] = values[locale]
    messages = data.get("messages", {"en": {}, "fr": {}})
    if set(messages) != set(result) or any(not isinstance(v, dict) for v in messages.values()):
        raise ValueError(f"{data['id']}: messages require en and fr objects")
    if set(messages['en']) != set(messages['fr']):
        raise ValueError(f"{data['id']}: message keys differ between languages")
    for locale in result:
        for key, value in messages[locale].items():
            if key in result[locale]:
                raise ValueError(f"{data['id']}: duplicate message {key}")
            result[locale][key] = value
    return result


def categories(root):
    path = root / "mod/categories.json"
    if not path.is_file():
        return {}
    result = {}
    for entry in json.loads(path.read_text(encoding="utf-8")):
        category = category_metadata(entry)
        if category["id"] in result:
            raise ValueError(f"{path}: duplicate category {category['id']}")
        result[category["id"]] = category
    return result


def category_messages(definitions):
    result = {"en": {}, "fr": {}}
    for category in definitions.values():
        for field, suffix in (("name", ""), ("description", "Hint")):
            if field in category:
                for locale in result:
                    result[locale][f"modules.category.{category['id']}{suffix}"] = category[field][locale]
    return result
