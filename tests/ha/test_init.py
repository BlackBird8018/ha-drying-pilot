# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Setup, entities, actions and notifications."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.drying_pilot.const import DOMAIN


def _entity_id(hass: HomeAssistant, entry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, f"{platform}.{key} not registered"
    return entity_id


async def test_setup_creates_entities(hass: HomeAssistant, setup_entry) -> None:
    assert setup_entry.state is ConfigEntryState.LOADED
    mode = hass.states.get(_entity_id(hass, setup_entry, "sensor", "mode"))
    # November sample forecast: no full window, a partial one for pre-drying
    assert mode.state in ("pre_dry", "later", "indoor")
    assert mode.attributes["title"]
    assert mode.attributes["live_sensors"] is False

    nxt = hass.states.get(_entity_id(hass, setup_entry, "sensor", "next_opportunity"))
    assert nxt.state in ("window", "pre_dry", "none")
    assert "start" in nxt.attributes and "gain" in nxt.attributes

    rate = hass.states.get(_entity_id(hass, setup_entry, "sensor", "rate"))
    assert float(rate.state) >= 0
    assert isinstance(rate.attributes["forecast"], list)

    for platform, key in [
        ("sensor", "status"),
        ("sensor", "vpd"),
        ("sensor", "progress"),
        ("binary_sensor", "bring_in"),
        ("binary_sensor", "dry"),
        ("select", "location"),
        ("select", "laundry_type"),
        ("button", "start"),
        ("button", "stop"),
        ("sensor", "calibration"),
        ("switch", "calibration_enabled"),
    ]:
        assert hass.states.get(_entity_id(hass, setup_entry, platform, key))


async def test_start_and_stop_actions(hass: HomeAssistant, setup_entry) -> None:
    mode_id = _entity_id(hass, setup_entry, "sensor", "mode")

    await hass.services.async_call(
        DOMAIN,
        "start",
        {"location": "covered", "laundry_type": "heavy"},
        blocking=True,
    )
    await hass.async_block_till_done()
    mode = hass.states.get(mode_id)
    assert mode.attributes["hanging"] is True
    assert mode.attributes["location"] == "covered"
    assert hass.states.get(_entity_id(hass, setup_entry, "select", "location")).state == "covered"
    assert hass.states.get(_entity_id(hass, setup_entry, "select", "laundry_type")).state == "heavy"
    assert hass.states.get(_entity_id(hass, setup_entry, "sensor", "progress")).state == "0"

    await hass.services.async_call(DOMAIN, "stop", {}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(mode_id).attributes["hanging"] is False


async def test_buttons_and_select(hass: HomeAssistant, setup_entry) -> None:
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": _entity_id(hass, setup_entry, "select", "laundry_type"), "option": "light"},
        blocking=True,
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": _entity_id(hass, setup_entry, "button", "start")}, blocking=True
    )
    await hass.async_block_till_done()
    mode = hass.states.get(_entity_id(hass, setup_entry, "sensor", "mode"))
    assert mode.attributes["hanging"] is True
    assert mode.attributes["laundry_type"] == "light"


async def test_dry_notification_without_calibration(hass: HomeAssistant, setup_entry) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.config_entries.async_update_entry(
        setup_entry,
        options={"notify_targets": ["notify.mobile_app_test"], "notify_types": ["dry"]},
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_off",
        {"entity_id": _entity_id(hass, setup_entry, "switch", "calibration_enabled")},
        blocking=True,
    )

    await hass.services.async_call(DOMAIN, "start", {}, blocking=True)
    coordinator = setup_entry.runtime_data
    coordinator.state.progress = 1000
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["title"] == "Laundry is dry"
    assert calls[0].data["data"]["actions"][0]["action"] == "DRYING_PILOT_STOP"

    # The action button in the notification brings the laundry in
    hass.bus.async_fire("mobile_app_notification_action", {"action": "DRYING_PILOT_STOP"})
    await hass.async_block_till_done()
    assert coordinator.state.hanging is False


async def test_feedback_question_and_answers(hass: HomeAssistant, setup_entry) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    hass.config_entries.async_update_entry(
        setup_entry,
        options={"notify_targets": ["notify.mobile_app_test"], "notify_types": ["dry"]},
    )
    await hass.async_block_till_done()
    mode_id = _entity_id(hass, setup_entry, "sensor", "mode")

    await hass.services.async_call(DOMAIN, "start", {}, blocking=True)
    coordinator = setup_entry.runtime_data
    coordinator.state.progress = 1000
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Question on the phone with four buttons and on the tile
    assert len(calls) == 1
    assert calls[0].data["title"] == "Is the laundry dry?"
    assert len(calls[0].data["data"]["actions"]) == 4
    assert hass.states.get(mode_id).attributes["question"] == "dry_check"

    # "Ask later" via the notification button: question disappears, no data
    hass.bus.async_fire("mobile_app_notification_action", {"action": "DRYING_PILOT_FB_LATER"})
    await hass.async_block_till_done()
    assert hass.states.get(mode_id).attributes["question"] is None
    assert coordinator.state.snooze_until is not None

    # "Still damp" via the action: one observation, progress below target
    coordinator.state.snooze_until = None
    await coordinator.async_refresh()
    await hass.services.async_call(DOMAIN, "feedback", {"answer": "damp"}, blocking=True)
    await hass.async_block_till_done()
    assert len(coordinator.state.run.observations) == 1
    assert coordinator.state.progress < 100
    assert hass.states.get(mode_id).state != "dry"

    # Bring in with "dry": run is stored and used for calibration
    await hass.services.async_call(DOMAIN, "stop", {"feedback": "dry"}, blocking=True)
    await hass.async_block_till_done()
    assert len(coordinator.history) == 1
    assert len(coordinator.history[0].observations) == 2
    cal = hass.states.get(_entity_id(hass, setup_entry, "sensor", "calibration"))
    assert cal.state == "learning"
    assert cal.attributes["line_answers"] == 2


async def test_reset_calibration_in_options(hass: HomeAssistant, setup_entry) -> None:
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"weather_entity": "weather.home", "reset_calibration": True}
    )
    await hass.async_block_till_done()
    assert "calibration_since" in setup_entry.options
    assert "reset_calibration" not in setup_entry.options


async def test_german_texts(hass: HomeAssistant, config_entry, weather_state) -> None:
    hass.config.language = "de"
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    mode = hass.states.get(_entity_id(hass, config_entry, "sensor", "mode"))
    assert mode.attributes["title"].startswith(("Vortrocknen", "Heute drinnen"))


async def test_unload(hass: HomeAssistant, setup_entry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
