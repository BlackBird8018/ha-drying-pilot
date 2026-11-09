# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Config and options flow."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.drying_pilot.const import DOMAIN

from .conftest import WEATHER


async def test_user_flow_creates_entry(hass: HomeAssistant, weather_state) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"weather_entity": WEATHER}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "DryingPilot"
    assert result["data"]["weather_entity"] == WEATHER


async def test_single_instance(hass: HomeAssistant, setup_entry) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(hass: HomeAssistant, setup_entry) -> None:
    hass.services.async_register("notify", "mobile_app_test", lambda call: None)
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "weather_entity": WEATHER,
            "pv_peak_w": 1000,
            "notify_targets": ["notify.mobile_app_test"],
            "notify_types": ["bring_in", "dry"],
            "a": 2.0,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.data["pv_peak_w"] == 1000
    assert setup_entry.options["notify_targets"] == ["notify.mobile_app_test"]
    assert setup_entry.options["a"] == 2.0
