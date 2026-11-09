# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Tile texts, icons and colors (no HA dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo

from .i18n import Strings
from .model import BlockReason, Evaluation, Location, Mode, dryness


@dataclass(frozen=True)
class TileText:
    title: str
    subtitle: str
    icon: str
    color: str  # HA color name


def fmt_time(moment: datetime, now: datetime, tz: tzinfo, s: Strings | None = None) -> str:
    """'14:30', 'tomorrow 09:00' or 'Sat 10:00' (localized)."""
    s = s or Strings(None)
    local = moment.astimezone(tz)
    today = now.astimezone(tz).date()
    hhmm = local.strftime("%H:%M")
    days = (local.date() - today).days
    if days == 0:
        return hhmm
    if days == 1:
        return f"{s('tomorrow')} {hhmm}"
    return f"{s.weekdays[local.weekday()]} {hhmm}"


def fmt_range(
    start: datetime, end: datetime, now: datetime, tz: tzinfo, s: Strings | None = None
) -> str:
    """'10:00–15:00', 'tomorrow 10:00–15:00', 'Sat 22:00–Sun 03:00'.

    The end gets its own day prefix when it is on another day than the start,
    so windows across midnight never look as if they ended before they began.
    """
    start_local, end_local = start.astimezone(tz), end.astimezone(tz)
    if end_local.date() == start_local.date():
        end_text = end_local.strftime("%H:%M")
    else:
        end_text = fmt_time(end, now, tz, s)
    return f"{fmt_time(start, now, tz, s)}–{end_text}"


def fmt_duration(hours: float, s: Strings | None = None) -> str:
    s = s or Strings(None)
    if hours < 1:
        return f"{max(round(hours * 60 / 15) * 15, 15)} min"
    if hours < 10:
        return f"{round(hours * 2) / 2:g} h".replace(".", s("decimal"))
    return f"{round(hours)} h"


def pct(value: float | None, target: float) -> int:
    """Displayed progress: share of water removed (two-phase drying curve)."""
    if value is None or target <= 0:
        return 0
    return int(round(100 * dryness(value / target)))


def tile_text(
    ev: Evaluation,
    location: Location,
    now: datetime,
    tz: tzinfo,
    dry_since: datetime | None = None,
    language: str | None = None,
) -> TileText:
    s = Strings(language)
    label = s.category(ev.category.value)
    p = pct(ev.progress, ev.target)

    def t(moment: datetime) -> str:
        return fmt_time(moment, now, tz, s)

    if ev.mode is Mode.INDOOR:
        return TileText(s("indoor_title"), s("indoor_sub"), "mdi:home-outline", "grey")

    if ev.mode is Mode.LATER and ev.next_window is not None:
        w = ev.next_window
        pre = ev.predry_window
        sub = (
            s("later_predry_sub", time=t(pre.end), p=pct(pre.total, ev.target))
            if pre is not None
            else s("now_label", label=label)
        )
        return TileText(
            s("later_title", range=fmt_range(w.start, w.end, now, tz, s)),
            sub,
            "mdi:calendar-clock",
            "blue",
        )

    if ev.mode is Mode.LATER and ev.predry_window is not None:
        # only a pre-drying window ahead
        w = ev.predry_window
        return TileText(
            s("predry_later", range=fmt_range(w.start, w.end, now, tz, s)),
            s("predry_later_sub", p=pct(w.total, ev.target), label=label),
            "mdi:calendar-clock",
            "blue",
        )

    if ev.mode is Mode.PRE_DRY and ev.predry_window is not None:
        w = ev.predry_window
        gain = pct(w.total, ev.target)
        if w.start <= now:
            return TileText(
                s("predry_now", p=gain),
                s("until", time=t(w.end)),
                "mdi:weather-partly-cloudy",
                "lime",
            )
        return TileText(
            s("predry_later", range=fmt_range(w.start, w.end, now, tz, s)),
            s("predry_later_sub", p=gain, label=label),
            "mdi:weather-partly-cloudy",
            "lime",
        )

    if ev.mode is Mode.PAUSED:
        sub = (
            s("paused_done", time=t(ev.dry_at))
            if ev.dry_at is not None
            else s("paused_none")
        )
        return TileText(
            s("paused_title", p=p), sub, "mdi:pause-circle-outline", "grey"
        )

    if ev.mode is Mode.HANG_NOW:
        title = (
            s("approx", label=label, dur=fmt_duration(ev.target / ev.rate, s))
            if ev.rate > 0
            else label
        )
        until = (
            s("until", time=t(ev.possible_until))
            if ev.possible_until is not None
            else s("until_open")
        )
        icon = "mdi:weather-sunny" if location is Location.LINE else "mdi:hanger"
        return TileText(title, until, icon, "green")

    if ev.mode is Mode.DRYING:
        sub = (
            s("drying_sub", time=t(ev.dry_at))
            if ev.dry_at is not None
            else s("now_label", label=label)
        )
        return TileText(s("drying_title", p=p), sub, "mdi:tshirt-crew-outline", "teal")

    if ev.mode is Mode.TIGHT:
        at_end = pct(ev.progress_at_window_end, ev.target)
        end = t(ev.window_end) if ev.window_end else s("soon")
        return TileText(
            s("tight_title", p=at_end),
            s("tight_sub", time=end, p=p),
            "mdi:timer-sand",
            "amber",
        )

    if ev.mode is Mode.BRING_IN:
        if ev.bring_in_reason is BlockReason.RAIN and ev.next_rain is not None:
            sub = s("rain_sub", time=t(ev.next_rain), p=p)
            icon = "mdi:weather-pouring"
        else:
            sub = s("humid_sub", p=p)
            icon = "mdi:water-percent-alert"
        return TileText(s("bring_in_title"), sub, icon, "red")

    if ev.mode is Mode.DRY:
        sub = s("dry_since", time=t(dry_since)) if dry_since else s("dry_reached")
        return TileText(s("dry_title"), sub, "mdi:check-circle-outline", "green")

    return TileText(label, "", "mdi:tshirt-crew-outline", "grey")
