"""UTF-8 resource-based localization and locale-aware presentation formatting."""

from __future__ import annotations

import json
import locale
import logging
import os
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from string import Formatter
from typing import Any

SUPPORTED_LOCALES = ("en", "ko")
DEFAULT_LOCALE = "en"
log = logging.getLogger(__name__)


def normalize_locale(value: str | None) -> str:
    """Return a supported language code independently of region and time zone."""
    if not value:
        return DEFAULT_LOCALE
    code = value.replace("-", "_").split("_", 1)[0].lower()
    return code if code in SUPPORTED_LOCALES else DEFAULT_LOCALE


def detect_locale() -> str:
    """Detect the initial UI language from OS locale environment and APIs."""
    for name in ("WEBCAMCCTV_LOCALE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(name):
            return normalize_locale(os.environ[name])
    language, _ = locale.getlocale()
    return normalize_locale(language)


def _load(locale_code: str) -> dict[str, str]:
    resource = files("webcamcctv.locales").joinpath(f"{locale_code}.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
    ):
        raise ValueError(f"Malformed locale resource: {locale_code}")
    return raw


class Translator:
    """Translate stable keys with selected-language → English → key fallback."""

    def __init__(self, language: str | None = None, *, development: bool | None = None) -> None:
        self.language = normalize_locale(language or detect_locale())
        self.development = (
            development
            if development is not None
            else os.environ.get("WEBCAMCCTV_I18N_DEBUG") == "1"
        )
        self.english = _load(DEFAULT_LOCALE)
        self.messages = self.english if self.language == DEFAULT_LOCALE else _load(self.language)

    def tr(self, key: str, **values: object) -> str:
        template = self.messages.get(key) or self.english.get(key)
        if template is None:
            log.warning("Missing translation key %s for locale %s", key, self.language)
            return f"⟦{key}⟧" if self.development else key
        if os.environ.get("WEBCAMCCTV_PSEUDO") == "1":
            table = str.maketrans(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
                "ȧƀƈḓḗƒɠħīĵķŀḿƞǿƥɋřşŧŭṽẇẋẏẑȦƁƇḒḖƑƓĦĪĴĶĿḾȠǾƤɊŘŞŦŬṼẆẊẎƵ",
            )
            template = "⟦" + template.translate(table) + "··⟧"
        try:
            return template.format(**values)
        except (KeyError, ValueError) as exc:
            log.warning("Malformed translation %s/%s: %s", self.language, key, exc)
            return f"⟦{key}⟧"

    def plural(self, key: str, count: float, **values: object) -> str:
        category = "one" if self.language == "en" and count == 1 else "other"
        return self.tr(f"{key}.{category}", count=format_number(count, self.language), **values)


def placeholders(value: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(value) if name}


def format_number(value: float, language: str, decimals: int | None = None) -> str:
    """Format numbers without mutating the process-global C locale."""
    if decimals is None:
        text = f"{value:,}" if isinstance(value, int) else f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{value:,.{decimals}f}"
    # Both included locales conventionally use comma grouping and a decimal point.
    return text


def format_datetime(value: datetime | float, language: str, override: str | None = None) -> str:
    moment = (
        datetime.fromtimestamp(value).astimezone()
        if isinstance(value, (int, float))
        else value.astimezone()
    )
    if override:
        return moment.strftime(override)
    if normalize_locale(language) == "ko":
        period = "오전" if moment.hour < 12 else "오후"
        hour = moment.hour % 12 or 12
        return f"{moment:%Y년 %m월 %d일} {period} {hour}:{moment:%M:%S} {moment:%Z}"
    return moment.strftime("%b %d, %Y, %I:%M:%S %p %Z")


def format_size(size: int, language: str) -> str:
    tr = Translator(language)
    units = ((1024**3, "format.gib"), (1024**2, "format.mib"), (1024, "format.kib"))
    for divisor, key in units:
        if size >= divisor:
            return tr.tr(key, value=format_number(size / divisor, language, 1))
    return tr.tr("format.byte", value=format_number(size, language))


def format_duration(seconds: int, language: str) -> str:
    tr = Translator(language)
    if seconds >= 60:
        return tr.plural("format.duration_minutes", seconds // 60)
    return tr.plural("format.duration_seconds", seconds)


def write_utf8_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
