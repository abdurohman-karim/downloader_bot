from __future__ import annotations

from app.core.config import settings
from app.locales.texts import TEXTS

_FALLBACK = "ru"


def t(lang: str | None, key: str, **kwargs: object) -> str:
    """Перевод по ключу с откатом на язык по умолчанию."""
    table = TEXTS.get(lang or "") or TEXTS.get(settings.default_lang) or TEXTS[_FALLBACK]
    template = table.get(key) or TEXTS[_FALLBACK].get(key, key)
    return template.format(**kwargs) if kwargs else template


__all__ = ["t", "TEXTS"]
