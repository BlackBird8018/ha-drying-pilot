# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Smoke test of the coordinator with minimal Home Assistant stubs.

Checks the data flow (forecast, live values, progress, texts, notifications),
not real HA behaviour.
"""

import asyncio
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generic, TypeVar
from zoneinfo import ZoneInfo

import importlib.util

import pytest

if importlib.util.find_spec("homeassistant") is not None:
    pytest.skip(
        "real Home Assistant installed; covered by tests/ha", allow_module_level=True
    )

FIXTURES = Path(__file__).parent / "fixtures"
T = TypeVar("T")


class _Clock:
    now = datetime(2026, 11, 6, 15, 20, tzinfo=timezone.utc)


def _install_stubs() -> None:
    def mod(name: str, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class ConfigEntry(Generic[T]):
        pass

    class DataUpdateCoordinator(Generic[T]):
        def __init__(self, hass, logger, config_entry=None, name=None, update_interval=None):
            self.hass = hass
            self.config_entry = config_entry
            self.data = None

        async def async_refresh(self):
            self.data = await self._async_update_data()

    class Store(Generic[T]):
        def __init__(self, hass, version, key):
            self.saved = None

        async def async_load(self):
            return None

        def async_delay_save(self, fn, delay):
            self.saved = fn()

    class HomeAssistantError(Exception):
        pass

    class UpdateFailed(Exception):
        pass

    mod("homeassistant")
    mod("homeassistant.config_entries", ConfigEntry=ConfigEntry)
    mod("homeassistant.const", STATE_UNAVAILABLE="unavailable", STATE_UNKNOWN="unknown")
    mod("homeassistant.core", HomeAssistant=object)
    mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    mod("homeassistant.helpers")
    mod("homeassistant.helpers.storage", Store=Store)
    mod(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=DataUpdateCoordinator,
        UpdateFailed=UpdateFailed,
    )
    mod("homeassistant.util")
    mod(
        "homeassistant.util.dt",
        utcnow=lambda: _Clock.now,
        parse_datetime=datetime.fromisoformat,
        get_default_time_zone=lambda: ZoneInfo("Europe/Berlin"),
    )
    sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]


@pytest.fixture
def coordinator_cls():
    saved = {k: v for k, v in sys.modules.items() if k.startswith("homeassistant")}
    _install_stubs()
    sys.modules.pop("cdt.coordinator", None)
    from cdt.coordinator import DryingPilotCoordinator

    yield DryingPilotCoordinator
    for k in [k for k in sys.modules if k.startswith("homeassistant")]:
        del sys.modules[k]
    sys.modules.update(saved)
    sys.modules.pop("cdt.coordinator", None)


class _State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class _Hass:
    def __init__(self, states, forecast):
        self._states = states
        self._forecast = forecast
        self.states = self
        self.services = self
        self.calls = 0
        self.config = types.SimpleNamespace(language="de")
        self.sent = []

    def get(self, entity_id):
        return self._states.get(entity_id)

    async def async_call(self, domain, service, data, blocking=False, return_response=False):
        if domain == "notify":
            self.sent.append((service, data))
            return None
        self.calls += 1
        return {data["entity_id"]: {"forecast": self._forecast}}


class _Entry:
    entry_id = "abc"
    data = {
        "weather_entity": "weather.home",
        "temperature_entity": "sensor.t",
        "humidity_entity": "sensor.h",
        "pv_power_entity": "sensor.pv",
        "pv_peak_w": 800,
        "notify_targets": ["notify.mobile_app_test"],
        "notify_types": ["bring_in", "dry", "window_ending", "good_window"],
    }
    options = {}


def test_coordinator_flow(coordinator_cls):
    forecast = json.loads((FIXTURES / "forecast_sample_november.json").read_text())
    hass = _Hass(
        {
            "weather.home": _State("cloudy", {"wind_speed": 18.0, "wind_speed_unit": "km/h"}),
            "sensor.t": _State("6.0"),
            "sensor.h": _State("85"),
            "sensor.pv": _State("0"),
        },
        forecast,
    )
    c = coordinator_cls(hass, _Entry())

    async def run():
        await c.async_refresh()
        assert c.data.evaluation.mode.value == "later"  # pre-drying only tomorrow
        assert c.data.live is not None
        assert c.data.tile.title.startswith("Vortrocknen")

        await c.async_start()
        assert c.state.hanging and c.state.progress == 0
        # 30 minutes later: progress grows by about rate * 0.5 h
        _Clock.now += timedelta(minutes=30)
        await c.async_refresh()
        rate = c.data.evaluation.rate
        assert c.state.progress == pytest.approx(rate * 0.5, rel=0.01)
        assert c.data.evaluation.mode.value in ("bring_in", "tight", "drying", "paused")
        assert hass.calls == 2  # refetched after 30 min (interval 15 min)

        # sensor unavailable: calculation continues with the forecast
        hass._states["sensor.t"] = _State("unavailable")
        _Clock.now += timedelta(minutes=5)
        await c.async_refresh()
        assert c.data.live is None

        assert c.live_source is None

        # temperature only: humidity from the forecast dew point
        hass._states["sensor.t"] = _State("8.0")
        hass._states["sensor.h"] = _State("unavailable")
        await c.async_refresh()
        assert c.live_source == "temperature_dew_point"
        assert c.data.live is not None
        assert 0 < c.data.live.humidity < 100

        # force progress to the target -> exactly one "dry" notification
        c.state.progress = 200
        await c.async_refresh()
        await c.async_refresh()
        questions = [m for m in hass.sent if m[1]["title"] == "Ist die Wäsche trocken?"]
        assert len(questions) == 1
        assert [a["action"] for a in questions[0][1]["data"]["actions"]] == [
            "DRYING_PILOT_FB_DRY", "DRYING_PILOT_FB_DAMP", "DRYING_PILOT_FB_UNKNOWN", "DRYING_PILOT_FB_LATER"
        ]
        assert c.state.question == "dry_check"

        # "still damp": learns, lowers progress, asks again later
        await c.async_feedback("damp")
        assert c.state.question is None
        assert c.state.progress < c.data.evaluation.target
        assert len(c.state.run.observations) == 1

        # with calibration off the plain "dry" notification is sent instead
        await c.async_set_calibration(False)
        c.state.progress = 200
        await c.async_refresh()
        dry_msgs = [m for m in hass.sent if m[1]["title"] == "Wäsche ist trocken"]
        assert len(dry_msgs) == 1
        assert dry_msgs[0][0] == "mobile_app_test"

        await c.async_stop()
        assert not c.state.hanging
        assert c._store.saved["hanging"] is False

    asyncio.run(run())
