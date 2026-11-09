# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for tests in a real Home Assistant instance."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.drying_pilot.const import DOMAIN  # noqa: E402
from custom_components.drying_pilot.coordinator import DryingPilotCoordinator  # noqa: E402

FIXTURE = Path(__file__).parents[1] / "fixtures" / "forecast_sample_november.json"
WEATHER = "weather.home"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/drying_pilot."""
    yield


@pytest.fixture
def forecast() -> list[dict]:
    return json.loads(FIXTURE.read_text())


@pytest.fixture(autouse=True)
def mock_forecast(forecast):
    """Serve the sample forecast instead of calling weather.get_forecasts."""

    async def _fetch(self: DryingPilotCoordinator, now) -> None:
        # shift the sample so that it always starts at the current hour
        first = datetime.fromisoformat(forecast[0]["datetime"])
        offset = now.replace(minute=0, second=0, microsecond=0) - first
        self._forecast_raw = [
            {
                **item,
                "datetime": (datetime.fromisoformat(item["datetime"]) + offset).isoformat(),
            }
            for item in forecast
        ]
        self._forecast_fetched = now

    with patch.object(DryingPilotCoordinator, "_async_fetch_forecast", _fetch):
        yield


@pytest.fixture
def weather_state(hass: HomeAssistant) -> None:
    hass.states.async_set(
        WEATHER, "cloudy", {"wind_speed": 15.0, "wind_speed_unit": "km/h"}
    )


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="DryingPilot",
        data={"weather_entity": WEATHER, "pv_peak_w": 800},
        options={},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, weather_state
) -> MockConfigEntry:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
