# Localization

`en.json` and `fr.json` contain shared desktop application text. Module text belongs in `mod/modules/<id>/manifest.json`, never in the application catalogs. Edit text in these JSON sources, not in Python, HTML or JavaScript. English is the fallback locale. The native RX3 labels in `mock.*` intentionally retain the wording displayed on the hardware. User filenames, bank names, track metadata and third-party technical diagnostics are not translations.

## Messages

Use semantic, stable keys (`samples.trimHint`), complete sentences and named parameters (`{count}`, `{path}`). Do not concatenate translated sentence fragments. A plural message is an object with `one` and `other` variants and a numeric `count` parameter. Browser selection uses `Intl.PluralRules`; visible numbers use `Intl.NumberFormat`. Python currently supports the two shipped locales. Extend its plural handling if introducing another language.

HTML uses `data-t`, `data-t-label`, `data-t-title` or `data-t-placeholder`. JavaScript uses `i18n.t(key, params)` and `i18n.message(value)` for structured backend messages. Values are inserted as text, never HTML. Keep paths and identifiers as strings so they are not number-formatted.

Python emits `Message(key, **params)` or raises `LocalizedError(key, **params)`. A message remains English-readable in logs and CLI tools; the bridge sends its key and parameters to the UI. Do not translate inside a worker thread or match English error sentences to infer a key. External tool output is diagnostic data, retained separately from the localized progress label.

## Adding a language

Copy the English catalog, translate every value while preserving keys and parameters, then add the locale to `SUPPORTED` in `__init__.py` and to the language selector. Native file-dialog filters use the same catalogs. The bridge loads catalog data without browser file-URL fetch restrictions; PyInstaller includes the JSON files explicitly. The chosen language is stored locally and regional locales fall back to their supported base language.

Run `.venv/bin/python -m unittest discover -s tests -p 'test_localization.py'` for key coverage, duplicate keys, parameters, plurals, module metadata and browser locale switching. Run `.venv/bin/python app/ui/shell.py --self-test` to verify packaged resources. A missing catalog fails that self-test; a missing message falls back to English, then to its key.

## Module manifests

`name` and `description` in each module manifest contain `en` and `fr` strings. For selectable modules, `category` is only an identifier referencing `mod/categories.json`. That registry alone owns category names, optional descriptions, display order and collapsed state. No category definition belongs in a module manifest or in application code.

Module-specific controls and help belong in the manifest's `messages`, with `en` and `fr` objects keyed by semantic message IDs. The localization loader combines module text, the category registry and shared catalogs in source and packaged builds. It generates `module.<id>.name`, `module.<id>.description` and `modules.category.<id>` (plus `<id>Hint` when present). Keep parameters and plural variants identical between languages. Duplicate message ownership is rejected.

The CLI uses the English module name and description. `make new-module` requires an explicit `CATEGORY` identifier and creates bilingual metadata; replace its TODO descriptions before shipping. Internal modules such as the core do not need a category. A new category is declared once in `mod/categories.json` and needs no application code change.

A module can set `advanced: true` to appear in the collapsed Advanced section instead of its regular category. `selectable` still controls whether it can be requested directly. Required advanced modules stay locked while selected dependents need them.
