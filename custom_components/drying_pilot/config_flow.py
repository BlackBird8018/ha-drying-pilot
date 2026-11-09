# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""UI configuration flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_A,
    CONF_B,
    CONF_HUMIDITY,
    CONF_MIN_RATE,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TYPES,
    CONF_PV_PEAK,
    CONF_PREDRY_MIN_HOURS,
    CONF_PV_POWER,
    CONF_RAIN_MM,
    CONF_RAIN_PROBABILITY,
    CONF_CALIBRATION_SINCE,
    CONF_DEW_MARGIN,
    CONF_RESET_CALIBRATION,
    CONF_REWET_RH,
    CONF_REWET_RH_EXIT,
    CONF_SPIN_RPM,
    CONF_SUN_GAIN,
    CONF_TARGET_HEAVY,
    CONF_TARGET_LIGHT,
    CONF_TARGET_NORMAL,
    CONF_TEMPERATURE,
    CONF_WEATHER,
    DEFAULT_PV_PEAK,
    DOMAIN,
)
from .model import ModelParams
from .notify import DEFAULT_NOTIFY_TYPES, NotifyType


def _num(min_: float, max_: float, step: float, unit: str | None = None):
    config = selector.NumberSelectorConfig(
        min=min_, max=max_, step=step, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _entity_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_WEATHER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(CONF_TEMPERATURE): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Optional(CONF_HUMIDITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Optional(CONF_PV_POWER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_PV_PEAK, default=DEFAULT_PV_PEAK): _num(50, 50000, 10, "W"),
        }
    )


def _params_schema() -> vol.Schema:
    d = ModelParams()
    return vol.Schema(
        {
            vol.Optional(CONF_A, default=d.a): _num(0, 20, 0.05),
            vol.Optional(CONF_B, default=d.b): _num(0, 5, 0.01),
            vol.Optional(CONF_SUN_GAIN, default=d.sun_gain): _num(0, 100, 0.5, "%/h"),
            vol.Optional(CONF_MIN_RATE, default=d.min_rate): _num(0, 50, 0.5, "%/h"),
            vol.Optional(CONF_RAIN_MM, default=d.rain_mm): _num(0, 10, 0.05, "mm"),
            vol.Optional(CONF_RAIN_PROBABILITY, default=d.rain_probability): _num(
                0, 100, 1, "%"
            ),
            vol.Optional(CONF_REWET_RH, default=d.rewet_rh): _num(70, 100, 1, "%"),
            vol.Optional(CONF_REWET_RH_EXIT, default=d.rewet_rh_exit): _num(
                60, 100, 1, "%"
            ),
            vol.Optional(CONF_DEW_MARGIN, default=d.dew_margin): _num(0, 10, 0.5, "K"),
            vol.Optional(CONF_SPIN_RPM, default=1400): _num(400, 2000, 100, "rpm"),
            vol.Optional(CONF_PREDRY_MIN_HOURS, default=d.predry_min_hours): _num(
                1, 12, 0.5, "h"
            ),
            vol.Optional(CONF_TARGET_LIGHT, default=70.0): _num(10, 500, 5, "%"),
            vol.Optional(CONF_TARGET_NORMAL, default=100.0): _num(10, 500, 5, "%"),
            vol.Optional(CONF_TARGET_HEAVY, default=150.0): _num(10, 500, 5, "%"),
        }
    )


class DryingPilotConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="DryingPilot", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_entity_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> DryingPilotOptionsFlow:
        return DryingPilotOptionsFlow()


class DryingPilotOptionsFlow(OptionsFlow):
    """Change entities, notifications and model parameters."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # entities go to data so that cleared fields really become empty
            entity_keys = (CONF_WEATHER, CONF_TEMPERATURE, CONF_HUMIDITY, CONF_PV_POWER, CONF_PV_PEAK)
            reset = user_input.pop(CONF_RESET_CALIBRATION, False)
            data = {k: v for k, v in user_input.items() if k in entity_keys}
            options = {k: v for k, v in user_input.items() if k not in entity_keys}
            since = self.config_entry.options.get(CONF_CALIBRATION_SINCE)
            if reset:
                since = dt_util.utcnow().isoformat()
            if since:
                options[CONF_CALIBRATION_SINCE] = since
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            return self.async_create_entry(data=options)

        notify_services = sorted(
            f"notify.{name}"
            for name in self.hass.services.async_services_for_domain("notify")
            if name not in ("send_message", "persistent_notification", "notify")
        )
        notify_schema = {
            vol.Optional(CONF_NOTIFY_TARGETS, default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(
                CONF_NOTIFY_TYPES, default=[t.value for t in DEFAULT_NOTIFY_TYPES]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[t.value for t in NotifyType],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="notify_types",
                )
            ),
        }
        schema = vol.Schema(
            {
                **_entity_schema().schema,
                **notify_schema,
                **_params_schema().schema,
                vol.Optional(
                    CONF_RESET_CALIBRATION, default=False
                ): selector.BooleanSelector(),
            }
        )
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )
