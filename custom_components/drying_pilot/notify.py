# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Decides which notifications are due (no HA dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from enum import StrEnum

from .i18n import Strings
from .model import BlockReason, Evaluation, Mode
from .texts import fmt_duration, fmt_time, pct


class NotifyType(StrEnum):
    BRING_IN = "bring_in"
    DRY = "dry"
    WINDOW_ENDING = "window_ending"
    GOOD_WINDOW = "good_window"
    IRON_DAMP = "iron_damp"
    PREDRY_WINDOW = "predry_window"
    PREDRY_END = "predry_end"


DEFAULT_NOTIFY_TYPES = [NotifyType.BRING_IN, NotifyType.DRY, NotifyType.WINDOW_ENDING]

ACTION_STOP = "DRYING_PILOT_STOP"
ACTION_START = "DRYING_PILOT_START"
ACTION_FB_DRY = "DRYING_PILOT_FB_DRY"
ACTION_FB_DAMP = "DRYING_PILOT_FB_DAMP"
ACTION_FB_UNKNOWN = "DRYING_PILOT_FB_UNKNOWN"
ACTION_FB_LATER = "DRYING_PILOT_FB_LATER"

FEEDBACK_ACTIONS = {
    ACTION_FB_DRY: "dry",
    ACTION_FB_DAMP: "damp",
    ACTION_FB_UNKNOWN: "unknown",
    ACTION_FB_LATER: "later",
}

WINDOW_ENDING_LEAD = timedelta(hours=1)
IRON_DAMP_PCT = 85  # displayed dryness at which shirts are ideal for ironing


@dataclass(frozen=True)
class Notification:
    key: str  # used to avoid repeats
    title: str
    message: str
    action: str | None = None  # first action, e.g. ACTION_STOP / ACTION_START
    action_title: str | None = None
    more_actions: tuple[tuple[str, str], ...] = ()

    @property
    def actions(self) -> list[tuple[str, str]]:
        first = [(self.action, self.action_title or "")] if self.action else []
        return first + list(self.more_actions)


def feedback_question(key: str, language: str | None = None) -> Notification:
    """'Is the laundry dry?' with the four answer buttons."""
    s = Strings(language)
    return Notification(
        key,
        s("q_title"),
        s("q_message"),
        ACTION_FB_DRY,
        s("fb_dry"),
        (
            (ACTION_FB_DAMP, s("fb_damp")),
            (ACTION_FB_UNKNOWN, s("fb_unknown")),
            (ACTION_FB_LATER, s("fb_later")),
        ),
    )


def due_notifications(
    ev: Evaluation,
    hanging: bool,
    enabled: set[str],
    sent: set[str],
    last_good_window: date | None,
    now: datetime,
    tz: tzinfo,
    language: str | None = None,
    last_predry: date | None = None,
) -> list[Notification]:
    """Notifications to send now.

    `sent` holds the keys already sent in this drying run; the caller
    records the new keys.
    """
    s = Strings(language)
    out: list[Notification] = []
    p = pct(ev.progress, ev.target)

    def t(moment: datetime) -> str:
        return fmt_time(moment, now, tz, s)

    if hanging:
        if NotifyType.BRING_IN in enabled and ev.mode is Mode.BRING_IN:
            if ev.bring_in_reason is BlockReason.RAIN and ev.next_rain is not None:
                key, msg = "bring_in_rain", s("n_rain", time=t(ev.next_rain), p=p)
            else:
                key, msg = "bring_in_humid", s("n_humid", p=p)
            if key not in sent:
                out.append(
                    Notification(
                        key, s("n_bring_in_title"), msg, ACTION_STOP, s("action_stop")
                    )
                )

        if (
            NotifyType.IRON_DAMP in enabled
            and ev.mode is not Mode.DRY
            and p >= IRON_DAMP_PCT
            and "iron_damp" not in sent
        ):
            out.append(
                Notification(
                    "iron_damp",
                    s("n_iron_title"),
                    s("n_iron"),
                    ACTION_STOP,
                    s("action_stop"),
                )
            )

        if (
            NotifyType.PREDRY_END in enabled
            and ev.mode is Mode.PAUSED
            and p >= 10
            and "predry_end" not in sent
        ):
            out.append(
                Notification(
                    "predry_end",
                    s("n_predry_end_title"),
                    s("n_predry_end", p=p),
                    ACTION_STOP,
                    s("action_stop"),
                )
            )

        if NotifyType.DRY in enabled and ev.mode is Mode.DRY and "dry" not in sent:
            out.append(
                Notification(
                    "dry", s("n_dry_title"), s("n_dry"), ACTION_STOP, s("action_stop")
                )
            )

        if (
            NotifyType.WINDOW_ENDING in enabled
            and ev.mode is Mode.TIGHT
            and ev.window_end is not None
            and ev.window_end - now <= WINDOW_ENDING_LEAD
            and "window_ending" not in sent
        ):
            at_end = pct(ev.progress_at_window_end, ev.target)
            out.append(
                Notification(
                    "window_ending",
                    s("n_end_title"),
                    s("n_end", time=t(ev.window_end), p=at_end),
                    ACTION_STOP,
                    s("action_stop"),
                )
            )
    elif (
        NotifyType.PREDRY_WINDOW in enabled
        and ev.mode is Mode.PRE_DRY
        and ev.predry_window is not None
        and ev.predry_window.start <= now
        and last_predry != now.astimezone(tz).date()
    ):
        w = ev.predry_window
        out.append(
            Notification(
                "predry_window",
                s("n_predry_title"),
                s("n_predry", p=pct(w.total, ev.target), time=t(w.end)),
                ACTION_START,
                s("action_start"),
            )
        )
    elif (
        NotifyType.GOOD_WINDOW in enabled
        and ev.mode is Mode.HANG_NOW
        and last_good_window != now.astimezone(tz).date()
    ):
        dur = (
            s("n_good_dur", dur=fmt_duration(ev.target / ev.rate, s))
            if ev.rate > 0
            else ""
        )
        until = (
            s("n_good_until", time=t(ev.possible_until)) if ev.possible_until else ""
        )
        out.append(
            Notification(
                "good_window",
                s("n_good_title"),
                s("n_good", label=s.category(ev.category.value), dur=dur, until=until),
                ACTION_START,
                s("action_start"),
            )
        )
    return out
