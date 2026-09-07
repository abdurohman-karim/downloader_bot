"""Разбор и нормализация ссылок."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from app.core.config import SUPPORTED_DOMAINS

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_TRAILING = ".,);:!?\"'»"


def extract_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    return match.group().rstrip(_TRAILING) if match else None


def is_supported(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    return any(host == d or host.endswith("." + d) for d in SUPPORTED_DOMAINS)


def platform_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "tiktok" in host:
        return "TikTok"
    if "instagr" in host:
        return "Instagram"
    return "Video"


def cache_key(url: str) -> str:
    """
    Ключ кэша: схема, www и трекинговые параметры не влияют.
    Регистр пути сохраняем — у Instagram shortcode регистрозависимый.
    https://www.tiktok.com/@user/video/123?is_from_webapp=1 -> tiktok.com/@user/video/123
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return urlunsplit(("", host, path, "", "")).lstrip("/")
