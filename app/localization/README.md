# Localization

`en.json` and `fr.json` are the UTF-8 source catalogs for the desktop application. Edit text here, not in Python, HTML or JavaScript. English is the fallback locale. The native RX3 labels in `mock.*` intentionally retain the wording displayed on the hardware. User filenames, bank names, track metadata and third-party technical diagnostics are not translations.

## Messages

Use semantic, stable keys (`samples.trimHint`), complete sentences and named parameters (`{count}`, `{path}`). Do not concatenate translated sentence fragments. A plural message is an object with `one` and `other` variants and a numeric `count` parameter. Browser selection uses `Intl.PluralRules`; visible numbers use `Intl.NumberFormat`. Python currently supports the two shipped locales. Extend its plural handling if introducing another language.

HTML uses `data-t`, `data-t-label`, `data-t-title` or `data-t-placeholder`. JavaScript uses `i18n.t(key, params)` and `i18n.message(value)` for structured backend messages. Values are inserted as text, never HTML. Keep paths and identifiers as strings so they are not number-formatted.

Python emits `Message(key, **params)` or raises `LocalizedError(key, **params)`. A message remains English-readable in logs and CLI tools; the bridge sends its key and parameters to the UI. Do not translate inside a worker thread or match English error sentences to infer a key. External tool output is diagnostic data, retained separately from the localized progress label.

## Adding a language

Copy the English catalog, translate every value while preserving keys and parameters, then add the locale to `SUPPORTED` in `__init__.py` and to the language selector. Native file-dialog filters use the same catalogs. The bridge loads catalog data without browser file-URL fetch restrictions; PyInstaller includes the JSON files explicitly. The chosen language is stored locally and regional locales fall back to their supported base language.

Run `.venv/bin/python -m unittest discover -s tests -p 'test_localization.py'` for key coverage, duplicate keys, parameters, plurals, module metadata and browser locale switching. Run `.venv/bin/python app/ui/shell.py --self-test` to verify packaged resources. A missing catalog fails that self-test; a missing message falls back to English, then to its key.
