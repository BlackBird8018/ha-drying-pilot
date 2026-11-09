# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Scenario simulation: drive the real coordinator through thousands of
random but realistic situations and check that only logical states appear.

Weather regimes (sunny, humid, showers, clear dewy nights, sensor outages)
and a random user (hangs out, brings in, answers, ignores questions, changes
location, toggles calibration) are combined. After every 15-minute step all
invariants are checked. Uses the same minimal Home Assistant stubs as the
smoke test and is skipped where the real Home Assistant is installed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

if importlib.util.find_spec("homeassistant") is not None:
    pytest.skip("real Home Assistant installed", allow_module_level=True)

from test_coordinator_smoke import _Clock, _install_stubs, _State  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
HANGING = {"drying", "tight", "paused", "bring_in", "dry"}
IDLE = {"indoor", "later", "pre_dry", "hang_now"}
REGIMES = ["sunny", "mixed", "humid", "showers", "clear_night", "cold"]


def make_forecast(rng: random.Random, start: datetime, hours: int = 72) -> list[dict]:
    regime_days = [rng.choice(REGIMES) for _ in range(4)]
    out = []
    for i in range(hours):
        t = start + timedelta(hours=i)
        local = t.astimezone(TZ)
        regime = regime_days[i // 24]
        day = 7 <= local.hour <= 18
        sunh = max(0.0, math.sin(math.pi * (local.hour - 6) / 14)) if day else 0.0
        base_t = {"sunny": 22, "mixed": 15, "humid": 12, "showers": 14, "clear_night": 18, "cold": 4}[regime]
        temp = base_t + (6 * sunh if day else -4) + rng.uniform(-1.5, 1.5)
        rh = {"sunny": 50, "mixed": 68, "humid": 92, "showers": 80, "clear_night": 60, "cold": 85}[regime]
        rh = rh - 15 * sunh + (14 if not day else 0) + rng.uniform(-5, 5)
        cloud = {"sunny": 10, "mixed": 50, "humid": 95, "showers": 80, "clear_night": 5, "cold": 90}[regime]
        rain = regime == "showers" and rng.random() < 0.35
        out.append(
            {
                "datetime": t.isoformat(),
                "temperature": round(temp, 1),
                "humidity": round(min(max(rh, 20), 100)),
                "wind_speed": round(max(0.0, rng.gauss(12, 7)), 1),
                "cloud_coverage": cloud,
                "uv_index": round(6 * sunh * (1 - cloud / 130), 1),
                "precipitation": round(rng.uniform(0.3, 3), 1) if rain else 0.0,
                "precipitation_probability": rng.choice([60, 80, 90]) if rain else rng.choice([0, 5, 10]),
            }
        )
    return out


class Hass:
    def __init__(self, forecast):
        self.forecast = forecast
        self._states = {}
        self.states = self
        self.services = self
        self.sent: list[tuple[str, dict]] = []
        self.config = type("C", (), {"language": "de"})()

    def get(self, entity_id):
        return self._states.get(entity_id)

    async def async_call(self, domain, service, data, blocking=False, return_response=False):
        if domain == "notify":
            self.sent.append((service, data))
            return None
        return {data["entity_id"]: {"forecast": self.forecast}}


class Entry:
    entry_id = "sim"
    data = {
        "weather_entity": "weather.home",
        "temperature_entity": "sensor.t",
        "humidity_entity": "sensor.h",
        "pv_power_entity": "sensor.pv",
        "pv_peak_w": 800,
        "notify_targets": ["notify.mobile_app_test"],
        "notify_types": [
            "bring_in", "dry", "window_ending", "good_window",
            "iron_damp", "predry_window", "predry_end",
        ],
    }
    options: dict = {}


TIME_RE = re.compile(r"(?:(morgen|Mo|Di|Mi|Do|Fr|Sa|So) )?(\d\d):(\d\d)")


def shown_times(text: str, now: datetime) -> list[datetime]:
    """Times shown in a German tile text, resolved to datetimes.

    In a range "A–B" a bare end time B belongs to the day of A.
    """
    out = []
    local_now = now.astimezone(TZ)
    days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    prev_day = None
    for m in TIME_RE.finditer(text):
        prefix, hh, mm = m.groups()
        in_range_end = m.start() > 0 and text[m.start() - 1] == "–"
        day = local_now.date()
        if prefix == "morgen":
            day += timedelta(days=1)
        elif prefix in days:
            ahead = (days.index(prefix) - local_now.weekday()) % 7
            day += timedelta(days=ahead)
        elif in_range_end and prev_day is not None:
            day = prev_day
        prev_day = day
        out.append(datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=TZ))
    return out


def percents(text: str) -> list[int]:
    return [int(p) for p in re.findall(r"(\d+) %", text)]


QUESTION_TITLES = {"Ist die Wäsche trocken?", "Is the laundry dry?", "Le linge est-il sec ?", "¿Está seca la ropa?"}


class Violation(AssertionError):
    pass


def check(c, hass, now, run_info, step_sent):
    ev, tile, st = c.data.evaluation, c.data.tile, c.state
    mode = ev.mode.value
    errors = []

    def err(msg):
        errors.append(f"{now.astimezone(TZ):%a %H:%M} mode={mode}: {msg} | {tile.title} | {tile.subtitle}")

    # 1. mode matches whether laundry is out
    if st.hanging and mode not in HANGING:
        err("idle mode while laundry is out")
    if not st.hanging and mode not in IDLE:
        err("hanging mode while nothing is out")

    # 2. no timestamps in the past (sensors)
    for name in ("possible_until", "dry_at", "window_end", "next_rain"):
        v = getattr(ev, name)
        if v is not None and v < now - timedelta(seconds=1):
            err(f"{name} in the past: {v}")
    if mode == "later" and not (
        (ev.next_window and ev.next_window.start > now)
        or (ev.predry_window and ev.predry_window.end > now)
    ):
        err("'later' without a future window")
    if mode == "pre_dry" and not (
        ev.predry_window and ev.predry_window.start <= now < ev.predry_window.end
    ):
        err("'pre_dry' without a running pre-dry window")
    if mode == "tight" and not (ev.window_end and ev.dry_at is None):
        err("'tight' without window end")
    if mode == "hang_now" and ev.possible_until is not None and ev.possible_until <= now:
        err("'hang_now' with window already over")

    # 3. texts: no placeholders, no 'None', sane percents, no past times
    for text in (tile.title, tile.subtitle):
        if "{" in text or "None" in text:
            err("placeholder in text")
        if any(not 0 <= p <= 100 for p in percents(text)):
            err("percent out of range")
    if mode != "dry" and hass.config.language == "de":  # "Seit 13:35" is meant to be past
        for t in shown_times(tile.title + " " + tile.subtitle, now):
            if t < now.astimezone(TZ).replace(second=0, microsecond=0) - timedelta(minutes=1):
                err(f"shown time in the past: {t:%a %H:%M}")

    # 4. progress shown never goes backwards within a run (except after 'damp'
    #    or a change of location / laundry type)
    shown = percents(tile.title)
    if st.hanging and shown and mode in ("drying", "paused"):
        if run_info["last_pct"] is not None and shown[0] + 1 < run_info["last_pct"] and not run_info["reset_ok"]:
            err(f"progress went back {run_info['last_pct']} -> {shown[0]}")
        run_info["last_pct"] = shown[0]
        run_info["reset_ok"] = False

    # 5. question only when 'dry', laundry out and calibration on
    if st.question and not (st.hanging and mode == "dry" and st.calibration_enabled):
        err("question asked in an illogical state")

    # 6. rain warnings only on the clothesline
    if ev.bring_in_reason is not None and ev.bring_in_reason.value == "rain" and st.location.value != "line":
        err("rain warning for covered laundry")

    # 7. notifications: no placeholders, each key once per run, phone question only in 'dry'
    for service, data in step_sent:
        if "{" in data["title"] + data["message"] or "None" in data["message"]:
            err("placeholder in notification")
        if data["title"] in QUESTION_TITLES and mode != "dry":
            err("dry question sent outside 'dry'")
    if len(st.notified) != len(set(st.notified)):
        err(f"duplicate notifications in one run: {st.notified}")

    # 8. no new question after a final answer; humid 'bring in' only after 30 %
    if st.question and run_info.get("final_answer"):
        err("asked again after a final answer")
    if ev.bring_in_reason is not None and ev.bring_in_reason.value == "humid":
        if st.progress < 0.3 * ev.target - 1e-6:
            err("'bring in' for humid air although laundry has barely dried")
    for service, data in step_sent:
        if data["title"] in ("Gutes Trockenwetter", "Vortrocknen möglich"):
            key = (data["title"], now.astimezone(TZ).date())
            if key in run_info["daily"]:
                err(f"'{data['title']}' twice on one day")
            run_info["daily"].add(key)

    # 9. internal sanity
    if not math.isfinite(st.progress) or st.progress < 0:
        err("invalid progress")
    if not st.hanging and (st.run is not None or st.question is not None):
        err("leftover run state after bringing in")

    if errors:
        raise Violation("\n".join(errors))


async def simulate(seed: int, steps: int = 144, language: str = "de") -> int:
    rng = random.Random(seed)
    start = datetime(2026, rng.randint(3, 10), rng.randint(1, 28), rng.randint(0, 23), tzinfo=timezone.utc)
    _Clock.now = start
    forecast = make_forecast(rng, start.replace(minute=0))
    hass = Hass(forecast)
    hass.config.language = language
    from cdt.coordinator import DryingPilotCoordinator
    from cdt.model import LaundryType, Location

    c = DryingPilotCoordinator(hass, Entry())
    daily: set = set()
    run_info = {"last_pct": None, "reset_ok": True, "daily": daily}
    checks = 0
    for _ in range(steps):
        # live sensors follow the forecast with noise, sometimes unavailable
        hour = int((_Clock.now - start.replace(minute=0)).total_seconds() // 3600)
        fc = forecast[min(hour, len(forecast) - 1)]
        hass._states["weather.home"] = _State("x", {"wind_speed": fc["wind_speed"], "wind_speed_unit": "km/h"})
        hass._states["sensor.t"] = _State("unavailable" if rng.random() < 0.05 else str(fc["temperature"] + rng.uniform(-1, 1)))
        hass._states["sensor.h"] = _State("unavailable" if rng.random() < 0.05 else str(min(100, fc["humidity"] + rng.uniform(-4, 4))))
        hass._states["sensor.pv"] = _State(str(round(800 * fc["uv_index"] / 6)))

        # random user
        r = rng.random()
        if not c.state.hanging and r < 0.06:
            await c.async_start(rng.choice(list(Location)), rng.choice(list(LaundryType)))
            run_info = {"last_pct": None, "reset_ok": True, "daily": daily}
        elif c.state.hanging and r < 0.02:
            await c.async_stop(rng.choice([None, "dry", "damp", "unknown"]))
        elif c.state.question and r < 0.5:
            answer = rng.choice(["dry", "damp", "unknown", "later"])
            await c.async_feedback(answer)
            run_info["reset_ok"] = run_info["reset_ok"] or answer == "damp"
            if answer in ("dry", "unknown"):
                run_info["final_answer"] = True
        elif c.state.hanging and r < 0.03:
            await c.async_set_location(rng.choice(list(Location)))
            run_info["reset_ok"] = True
        elif r > 0.995:
            await c.async_set_calibration(not c.state.calibration_enabled)
            if c.state.calibration_enabled is False:
                run_info["final_answer"] = False

        before = len(hass.sent)
        await c.async_refresh()
        check(c, hass, _Clock.now, run_info, hass.sent[before:])
        checks += 1
        _Clock.now += timedelta(minutes=15)
    return checks


@pytest.fixture
def coordinator_env():
    saved = {k: v for k, v in sys.modules.items() if k.startswith("homeassistant")}
    _install_stubs()
    sys.modules.pop("cdt.coordinator", None)
    yield
    for k in [k for k in sys.modules if k.startswith("homeassistant")]:
        del sys.modules[k]
    sys.modules.update(saved)
    sys.modules.pop("cdt.coordinator", None)


def test_random_scenarios_stay_logical(coordinator_env):
    total = 0
    failures = []
    for seed in range(150):
        try:
            total += asyncio.run(simulate(seed))
        except Violation as exc:
            failures.append(f"seed {seed}:\n{exc}")
    assert not failures, "\n\n".join(failures[:5]) + f"\n\n({len(failures)} of 150 scenarios failed)"
    assert total == 150 * 144


def test_random_scenarios_other_languages(coordinator_env):
    failures = []
    for seed in range(200, 260):
        lang = ["en", "fr", "es"][seed % 3]
        try:
            asyncio.run(simulate(seed, language=lang))
        except Violation as exc:
            failures.append(f"seed {seed} ({lang}):\n{exc}")
    assert not failures, "\n\n".join(failures[:5])
