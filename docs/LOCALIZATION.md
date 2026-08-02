# Localization contribution guide

WebcamCCTV uses stable keys in external UTF-8 JSON resources under `src/webcamcctv/locales/`. English (`en.json`) is the canonical key set; Korean (`ko.json`) is bundled and production-ready. Application logic calls `Translator.tr("stable.key", name=value)` and never uses English source text as an identifier.

## Add a language

1. Copy `en.json` to `<ISO-639-1>.json`, translate every value, and preserve keys and `{placeholders}` exactly.
2. Add its code to `SUPPORTED_LOCALES` in `i18n.py` and to the GUI `LANGUAGES` list. Add plural rules in `Translator.plural` when the language has categories beyond English `one/other`.
3. Add native language documentation under `docs/<code>/` and update packaging choices.
4. Run `python tools/validate_translations.py`, `pytest`, and the GUI in pseudo-localization mode with `WEBCAMCCTV_PSEUDO=1 webcamcctv-gui`. Pseudo-localization expands/wraps text to expose clipping and hard-coded strings. Set `WEBCAMCCTV_I18N_DEBUG=1` to show missing keys as `⟦key⟧`; missing keys are also logged.
5. Review every primary screen at 100%, 150%, and 200% scaling with a native speaker. Verify shortcuts, screen-reader names, mixed-script paths, notifications, installer output, and search.

The validator rejects malformed JSON, duplicate/missing/extra keys, and placeholder mismatches, then emits a machine-readable unused-key report. Dynamic `service.*` and `event.*` keys are intentionally recognized. Runtime fallback order is selected locale, English, then the stable key with a development warning.

Date/time formatting follows the selected UI locale but retains the operating-system time zone. `date_time_format` is an independent optional `strftime` override. UI language, notification language, region/time zone, and future recording schedules remain separate configuration concerns. Qt layouts use dynamic sizing, stretch factors, wrapping, high-DPI scaling, and system font fallback; no unlicensed font is bundled. Qt can mirror these layouts when an RTL locale is introduced.
