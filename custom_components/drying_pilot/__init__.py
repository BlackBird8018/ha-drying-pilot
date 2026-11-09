# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""DryingPilot: tells you whether laundry will dry outside."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    ATTR_ANSWER,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FEEDBACK,
    ATTR_LAUNDRY_TYPE,
    ATTR_LOCATION,
    DOMAIN,
    SERVICE_FEEDBACK,
    SERVICE_START,
    SERVICE_STOP,
)
from .coordinator import ANSWERS, DryingPilotConfigEntry, DryingPilotCoordinator
from .model import LaundryType, Location
from .notify import ACTION_START, ACTION_STOP, FEEDBACK_ACTIONS

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

START_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_LOCATION): vol.In([loc.value for loc in Location]),
        vol.Optional(ATTR_LAUNDRY_TYPE): vol.In([t.value for t in LaundryType]),
    }
)
STOP_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_FEEDBACK): vol.In(["dry", "damp", "unknown"]),
    }
)
FEEDBACK_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_ANSWER): vol.In(list(ANSWERS)),
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> DryingPilotCoordinator:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_found"
        )
    return entries[0].runtime_data


CARD_URL = f"/{DOMAIN}/drying-pilot-card.js"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card and register it with the frontend."""
    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / "frontend" / "drying-pilot-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), False)]
    )
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions and the dashboard card."""
    await _async_register_card(hass)

    async def handle_start(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        loc = call.data.get(ATTR_LOCATION)
        laundry = call.data.get(ATTR_LAUNDRY_TYPE)
        await coordinator.async_start(
            Location(loc) if loc else None,
            LaundryType(laundry) if laundry else None,
        )

    async def handle_stop(call: ServiceCall) -> None:
        await _coordinator(hass, call).async_stop(call.data.get(ATTR_FEEDBACK))

    async def handle_feedback(call: ServiceCall) -> None:
        await _coordinator(hass, call).async_feedback(call.data[ATTR_ANSWER])

    hass.services.async_register(DOMAIN, SERVICE_START, handle_start, START_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop, STOP_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_FEEDBACK, handle_feedback, FEEDBACK_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DryingPilotConfigEntry) -> bool:
    coordinator = DryingPilotCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    @callback
    def _on_action(event: Event) -> None:
        action = event.data.get("action")
        if action == ACTION_STOP:
            hass.async_create_task(coordinator.async_stop())
        elif action == ACTION_START:
            hass.async_create_task(coordinator.async_start())
        elif action in FEEDBACK_ACTIONS:
            hass.async_create_task(
                coordinator.async_feedback(FEEDBACK_ACTIONS[action])
            )

    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", _on_action)
    )
    return True


async def _async_reload(hass: HomeAssistant, entry: DryingPilotConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DryingPilotConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
