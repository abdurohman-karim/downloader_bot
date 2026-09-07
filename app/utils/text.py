"""Хелперы для форматирования сообщений."""

from __future__ import annotations

import html


def format_duration(secs: int | None) -> str:
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def esc(value: object) -> str:
    """Экранирование пользовательских/внешних данных для parse_mode=HTML."""
    return html.escape(str(value), quote=False)


def build_caption(
    title: str | None, duration: int | None, platform: str, emoji: str
) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"<b>{esc(title[:100])}</b>")
    dur = format_duration(duration)
    if dur:
        lines.append(f"⏱ {dur}")
    lines.append(f"{emoji} {esc(platform)}")
    return "\n".join(lines)
